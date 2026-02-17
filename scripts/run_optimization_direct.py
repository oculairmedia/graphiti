#!/usr/bin/env python3
"""
Run MIPROv2 optimization directly (bypassing Temporal).

Temporal's activity thread pool interferes with DSPy's MIPROv2 threading.
This script runs optimization in a clean Python process.
"""

import asyncio
import json
import logging
import sys
import time

sys.path.insert(0, '/opt/stacks/graphiti')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)


async def optimize_task(task: str, num_candidates: int = 3, max_examples: int = 100) -> dict:
    """Run MIPROv2 for a single task."""
    import dspy
    import inspect
    from dspy.teleprompt import MIPROv2

    from graphiti_core.dspy.config import configure_lm
    from graphiti_core.dspy.modules import (
        EdgeExtractor,
        NodeExtractor,
        NodeResolver,
        SummaryGenerator,
    )
    from graphiti_core.dspy.optimization import (
        edge_extraction_metric,
        entity_extraction_metric,
        node_resolution_metric,
        summary_metric,
    )
    from graphiti_core.dspy.training_storage import get_training_examples

    # Configure LM (no cache to avoid thread issues)
    configure_lm(cache=False)

    task_config = {
        'entity_extraction': {
            'module_class': NodeExtractor,
            'metric': entity_extraction_metric,
        },
        'edge_extraction': {
            'module_class': EdgeExtractor,
            'metric': edge_extraction_metric,
        },
        'node_resolution': {
            'module_class': NodeResolver,
            'metric': node_resolution_metric,
        },
        'summary_generation': {
            'module_class': SummaryGenerator,
            'metric': summary_metric,
        },
    }

    if task not in task_config:
        return {'task': task, 'success': False, 'error': f'Unknown task: {task}'}

    config = task_config[task]
    start = time.time()

    # Load training data
    stored = await get_training_examples(task, limit=10000)
    if not stored or len(stored) < 20:
        return {
            'task': task,
            'success': False,
            'error': f'Not enough examples: {len(stored or [])}',
        }

    import random

    examples_raw = [{'inputs': ex.inputs, 'expected_output': ex.output} for ex in stored]
    random.shuffle(examples_raw)
    examples_raw = examples_raw[:max_examples]

    split_idx = int(len(examples_raw) * 0.8)
    train_raw = examples_raw[:split_idx]
    val_raw = examples_raw[split_idx:]

    def to_dspy_example(ex):
        inputs = ex.get('inputs', {})
        output = ex.get('expected_output', {})
        example_dict = {**inputs, **output}
        return dspy.Example(**example_dict).with_inputs(*inputs.keys())

    trainset = [to_dspy_example(e) for e in train_raw]
    valset = [to_dspy_example(e) for e in val_raw]

    logger.info(
        f'{task}: {len(stored)} total examples, using {len(trainset)} train / {len(valset)} val'
    )

    # Create module with stateful disabled
    module_class = config['module_class']
    init_params = inspect.signature(module_class.__init__).parameters
    if 'enable_stateful' in init_params:
        module = module_class(enable_stateful=False)
    else:
        module = module_class()

    # MIPROv2 optimization
    num_trials = max(num_candidates + num_candidates // 2, num_candidates + 1)
    minibatch_size = min(len(valset), 20)

    logger.info(
        f'{task}: MIPROv2 with {num_candidates} candidates, {num_trials} trials, '
        f'minibatch={minibatch_size}'
    )

    optimizer = MIPROv2(
        metric=config['metric'],
        auto=None,
        num_candidates=num_candidates,
        num_threads=1,
        verbose=True,
    )

    optimized = optimizer.compile(
        module,
        trainset=trainset,
        valset=valset,
        num_trials=num_trials,
        minibatch_size=minibatch_size,
    )

    # Extract results
    docstring = None
    demos = []
    if hasattr(optimized, 'predictor'):
        predictor = optimized.predictor
        if hasattr(predictor, 'extended_signature'):
            sig = predictor.extended_signature
            docstring = getattr(sig, 'instructions', None) or getattr(sig, '__doc__', '')
        if hasattr(predictor, 'demos'):
            demos = [
                {k: str(v) for k, v in demo.items() if not k.startswith('_')}
                for demo in predictor.demos
            ]

    # Evaluate on validation set
    correct = 0
    for example in valset:
        try:
            prediction = optimized(**{k: getattr(example, k) for k in example._input_keys})
            score = config['metric'](example, prediction)
            if score >= 0.5:
                correct += 1
        except Exception as e:
            logger.warning(f'{task}: Validation example failed: {e}')

    val_score = correct / len(valset) if valset else 0.0
    duration_ms = int((time.time() - start) * 1000)

    result = {
        'task': task,
        'success': True,
        'val_score': val_score,
        'duration_ms': duration_ms,
        'docstring_len': len(docstring) if docstring else 0,
        'num_demos': len(demos),
        'total_examples': len(stored),
    }

    logger.info(f'{task}: DONE — val_score={val_score:.2%}, duration={duration_ms / 1000:.0f}s')

    # Store as candidate in PromptRegistry
    try:
        from graphiti_core.prompts.registry import PromptRegistry, PromptTask

        task_enum = getattr(PromptTask, task.upper(), None)
        if task_enum and docstring:
            registry = PromptRegistry()
            candidate = await registry.create_candidate(
                task=task_enum,
                docstring=docstring,
                demos=demos,
                parent_version=1,
                training_examples=len(stored),
            )
            await registry.update_metrics(
                candidate.id, accuracy=val_score, latency_ms=duration_ms / len(valset)
            )
            result['candidate_id'] = candidate.id
            result['candidate_version'] = candidate.version
            logger.info(
                f'{task}: Stored candidate v{candidate.version} (id={candidate.id[:16]}...)'
            )
    except Exception as e:
        logger.warning(f'{task}: Failed to store candidate: {e}')
        result['registry_error'] = str(e)

    return result


async def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--tasks',
        nargs='+',
        default=['entity_extraction', 'edge_extraction', 'node_resolution'],
    )
    parser.add_argument('--num-candidates', type=int, default=3)
    parser.add_argument('--max-examples', type=int, default=100)
    args = parser.parse_args()

    results = []
    for task in args.tasks:
        logger.info(f'=== Starting {task} ===')
        try:
            result = await optimize_task(task, args.num_candidates, args.max_examples)
            results.append(result)
            logger.info(f'{task}: {json.dumps(result, indent=2)}')
        except Exception as e:
            logger.error(f'{task}: FAILED — {e}', exc_info=True)
            results.append({'task': task, 'success': False, 'error': str(e)})

    print('\n=== FINAL RESULTS ===')
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    asyncio.run(main())
