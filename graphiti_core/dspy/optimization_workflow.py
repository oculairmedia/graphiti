"""
Temporal Workflow for MIPROv2 DSPy Prompt Optimization.

Runs MIPROv2 optimization on collected training data and stores optimized prompts
as candidates in the PromptRegistry.

Architecture note: Training data is loaded INSIDE the optimize_task activity
(not passed through Temporal). This avoids Temporal's 4MB gRPC payload limit
since training examples average ~10KB each and we may have thousands.
"""

from __future__ import annotations

import importlib
import logging
import random
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

logger = logging.getLogger(__name__)

# Import Temporal modules dynamically to avoid import errors when Temporal not installed
workflow = importlib.import_module('temporalio.workflow')
common = importlib.import_module('temporalio.common')
activity = importlib.import_module('temporalio.activity')


# =============================================================================
# Data Classes for Workflow I/O
# =============================================================================


@dataclass
class OptimizationConfig:
    """Configuration for the optimization workflow."""

    training_data_dir: str = '/data/training_data'
    min_examples_per_task: int = 50
    train_split: float = 0.8
    max_examples: int = 300
    num_candidates: int = 7
    num_threads: int = 4
    tasks: list[str] = field(
        default_factory=lambda: [
            'entity_extraction',
            'edge_extraction',
            'node_resolution',
            'summary_generation',
        ]
    )


@dataclass
class TrainingDataSplit:
    """Split training data for a task."""

    task: str
    train_examples: list[dict[str, Any]]
    val_examples: list[dict[str, Any]]
    total_examples: int


@dataclass
class OptimizationTaskResult:
    """Result from optimizing a single task."""

    task: str
    success: bool
    candidate_id: str | None = None
    candidate_version: int | None = None
    val_score: float | None = None
    docstring: str | None = None
    demos: list[dict[str, Any]] | None = None
    error: str | None = None
    duration_ms: int = 0
    total_examples: int = 0


@dataclass
class OptimizationWorkflowResult:
    """Final result from the optimization workflow."""

    success: bool
    tasks_optimized: int
    tasks_failed: int
    results: list[OptimizationTaskResult] = field(default_factory=list)
    total_duration_ms: int = 0


# =============================================================================
# Activity Functions (internal - called by activity wrappers)
# =============================================================================


async def load_and_split_training_data(
    training_data_dir: str,
    task: str,
    min_examples: int,
    train_split: float,
    max_examples: int = 300,
) -> TrainingDataSplit | None:
    """Load training data from FalkorDB and split into train/val sets.

    Falls back to JSON files if FalkorDB has no data.

    Args:
        max_examples: Cap on total examples to use. MIPROv2 works well with
            200-500 examples. Kept in-process to avoid Temporal payload limits.
    """
    from graphiti_core.dspy.training_storage import get_training_examples

    examples_raw: list[dict] = []

    stored = await get_training_examples(task, limit=10000)
    if stored:
        examples_raw = [{'inputs': ex.inputs, 'expected_output': ex.output} for ex in stored]
        logger.info(f'{task}: Loaded {len(examples_raw)} examples from FalkorDB')
    else:
        import json
        from pathlib import Path

        path = Path(training_data_dir) / f'{task}.json'
        if path.exists():
            with open(path) as f:
                data = json.load(f)
            examples_raw = data.get('examples', [])
            logger.info(f'{task}: Loaded {len(examples_raw)} examples from {path} (fallback)')
        else:
            logger.warning(f'{task}: No training data in FalkorDB or {path}')
            return None

    total_available = len(examples_raw)
    if total_available < min_examples:
        logger.warning(f'{task}: Only {total_available} examples, need {min_examples}')
        return None

    # Shuffle first, then cap to max_examples
    random.shuffle(examples_raw)
    if total_available > max_examples:
        logger.info(
            f'{task}: Sampling {max_examples} of {total_available} examples for optimization'
        )
        examples_raw = examples_raw[:max_examples]

    total = len(examples_raw)
    split_idx = int(total * train_split)
    train_examples = examples_raw[:split_idx]
    val_examples = examples_raw[split_idx:]

    logger.info(
        f'{task}: Split {total} examples (of {total_available} available) into '
        f'{len(train_examples)} train, {len(val_examples)} val'
    )

    return TrainingDataSplit(
        task=task,
        train_examples=train_examples,
        val_examples=val_examples,
        total_examples=total_available,
    )


async def run_miprov2_optimization(
    task: str,
    training_data_dir: str,
    min_examples: int,
    train_split: float,
    max_examples: int,
    num_candidates: int,
    num_threads: int,
) -> OptimizationTaskResult:
    """
    Load training data and run MIPROv2 optimization for a single task.

    Data is loaded in-process (not passed through Temporal) to avoid
    gRPC payload size limits.
    """
    import time

    import dspy
    from dspy.teleprompt import MIPROv2

    from graphiti_core.dspy.config import configure_lm
    from graphiti_core.dspy.modules import (
        NodeExtractor,
        EdgeExtractor,
        NodeResolver,
        SummaryGenerator,
    )
    from graphiti_core.dspy.optimization import (
        entity_extraction_metric,
        edge_extraction_metric,
        node_resolution_metric,
        summary_metric,
    )

    start_time = time.time()

    # Configure LM (idempotent)
    configure_lm()

    # Map task to module and metric
    task_config = {
        'entity_extraction': {
            'module_class': NodeExtractor,
            'metric': entity_extraction_metric,
            'output_field': 'extracted_entities',
        },
        'edge_extraction': {
            'module_class': EdgeExtractor,
            'metric': edge_extraction_metric,
            'output_field': 'extracted_edges',
        },
        'node_resolution': {
            'module_class': NodeResolver,
            'metric': node_resolution_metric,
            'output_field': 'entity_resolutions',
        },
        'summary_generation': {
            'module_class': SummaryGenerator,
            'metric': summary_metric,
            'output_field': 'summary',
        },
    }

    if task not in task_config:
        return OptimizationTaskResult(
            task=task,
            success=False,
            error=f'Unknown task: {task}',
            duration_ms=int((time.time() - start_time) * 1000),
        )

    # Step 1: Load training data in-process
    data = await load_and_split_training_data(
        training_data_dir=training_data_dir,
        task=task,
        min_examples=min_examples,
        train_split=train_split,
        max_examples=max_examples,
    )

    if data is None:
        return OptimizationTaskResult(
            task=task,
            success=False,
            error='Insufficient training data',
            duration_ms=int((time.time() - start_time) * 1000),
        )

    config = task_config[task]

    try:
        # Convert examples to DSPy format
        def to_dspy_example(ex: dict) -> dspy.Example:
            inputs = ex.get('inputs', {})
            output = ex.get('expected_output', {})
            example_dict = {**inputs, **output}
            return dspy.Example(**example_dict).with_inputs(*inputs.keys())

        trainset = [to_dspy_example(ex) for ex in data.train_examples]
        valset = [to_dspy_example(ex) for ex in data.val_examples]

        # Create module (sync creation - use baseline signatures)
        module_class = config['module_class']
        module = module_class()

        # Run MIPROv2
        logger.info(
            f'{task}: Starting MIPROv2 with {len(trainset)} train, {len(valset)} val examples'
        )

        # DSPy 3.1.3: auto=None required when setting num_candidates manually,
        # and num_trials must also be provided. Recommended: ~1.5x num_candidates.
        num_trials = max(num_candidates + num_candidates // 2, num_candidates + 1)
        optimizer = MIPROv2(
            metric=config['metric'],
            auto=None,
            num_candidates=num_candidates,
            num_threads=num_threads,
            verbose=True,
        )

        optimized = optimizer.compile(
            module,
            trainset=trainset,
            valset=valset,
            num_trials=num_trials,
        )

        # Extract optimized docstring and demos
        docstring = None
        demos = []

        # Get the predictor from the optimized module
        if hasattr(optimized, 'predictor'):
            predictor = optimized.predictor
            if hasattr(predictor, 'extended_signature'):
                sig = predictor.extended_signature
                docstring = getattr(sig, 'instructions', None) or getattr(sig, '__doc__', '')
            if hasattr(predictor, 'demos'):
                demos = [
                    {
                        'inputs': {k: getattr(demo, k, None) for k in demo._input_keys}
                        if hasattr(demo, '_input_keys')
                        else {},
                        'outputs': {k: getattr(demo, k, None) for k in demo._output_keys}
                        if hasattr(demo, '_output_keys')
                        else {},
                    }
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

        duration_ms = int((time.time() - start_time) * 1000)
        logger.info(
            f'{task}: Optimization complete. Val score: {val_score:.3f}, Duration: {duration_ms}ms'
        )

        return OptimizationTaskResult(
            task=task,
            success=True,
            val_score=val_score,
            docstring=docstring or '',
            demos=demos,
            duration_ms=duration_ms,
            total_examples=data.total_examples,
        )

    except Exception as e:
        logger.error(f'{task}: Optimization failed: {e}')
        return OptimizationTaskResult(
            task=task,
            success=False,
            error=str(e),
            duration_ms=int((time.time() - start_time) * 1000),
            total_examples=data.total_examples if data else 0,
        )


async def store_candidate(
    task: str,
    docstring: str,
    demos: list[dict[str, Any]],
    val_score: float,
    training_examples: int,
) -> tuple[str, int]:
    """
    Store optimized prompt as a candidate in PromptRegistry.

    Returns (candidate_id, version).
    """
    from graphiti_core.prompts.registry import (
        PromptRegistry,
        PromptTask,
        get_prompt_registry,
    )

    registry = get_prompt_registry()

    # Get current live prompt version as parent
    task_enum = PromptTask(task)
    live_prompt = await registry.get_live_prompt(task_enum)
    parent_version = live_prompt.version if live_prompt else None

    # Create candidate
    candidate = await registry.create_candidate(
        task=task_enum,
        docstring=docstring,
        demos=demos,
        parent_version=parent_version,
        training_examples=training_examples,
    )

    # Update metrics
    await registry.update_metrics(
        prompt_id=candidate.id,
        accuracy=val_score,
    )

    logger.info(
        f'{task}: Stored candidate v{candidate.version} (id={candidate.id[:8]}...) with score {val_score:.3f}'
    )

    return candidate.id, candidate.version


# =============================================================================
# Temporal Activities
# =============================================================================


class OptimizationActivities:
    """Activity implementations for the optimization workflow.

    Note: Training data is loaded INSIDE optimize_task (not passed as args)
    to avoid Temporal's 4MB gRPC payload limit. Each training example averages
    ~10KB, so even 250 examples would be ~2.5MB - too close to the limit.
    """

    @activity.defn
    async def optimize_task(
        self,
        task: str,
        training_data_dir: str,
        min_examples: int,
        train_split: float,
        max_examples: int,
        num_candidates: int,
        num_threads: int,
    ) -> dict:
        """Load data + run MIPROv2 optimization for a task (all in-process)."""
        result = await run_miprov2_optimization(
            task=task,
            training_data_dir=training_data_dir,
            min_examples=min_examples,
            train_split=train_split,
            max_examples=max_examples,
            num_candidates=num_candidates,
            num_threads=num_threads,
        )
        return {
            'task': result.task,
            'success': result.success,
            'candidate_id': result.candidate_id,
            'candidate_version': result.candidate_version,
            'val_score': result.val_score,
            'docstring': result.docstring,
            'demos': result.demos,
            'error': result.error,
            'duration_ms': result.duration_ms,
            'total_examples': result.total_examples,
        }

    @activity.defn
    async def store_optimized_candidate(
        self,
        task: str,
        docstring: str,
        demos: list[dict[str, Any]],
        val_score: float,
        training_examples: int,
    ) -> dict:
        """Store optimized prompt as candidate."""
        candidate_id, version = await store_candidate(
            task=task,
            docstring=docstring,
            demos=demos,
            val_score=val_score,
            training_examples=training_examples,
        )
        return {
            'candidate_id': candidate_id,
            'version': version,
        }


# =============================================================================
# Temporal Workflow
# =============================================================================


@workflow.defn(name='DSPyOptimizationWorkflow')
class DSPyOptimizationWorkflow:
    """
    Temporal workflow for running MIPROv2 optimization on DSPy modules.

    Flow:
    1. For each task: load data + run MIPROv2 (single activity, avoids payload limits)
    2. Store optimized prompts as candidates
    3. Return results summary
    """

    @workflow.run
    async def run(self, config_dict: dict[str, Any]) -> dict:
        """Execute the optimization workflow."""
        start_ns = workflow.time_ns()

        # Parse config
        config = OptimizationConfig(
            training_data_dir=config_dict.get('training_data_dir', '/data/training_data'),
            min_examples_per_task=config_dict.get('min_examples_per_task', 50),
            train_split=config_dict.get('train_split', 0.8),
            max_examples=config_dict.get('max_examples', 300),
            num_candidates=config_dict.get('num_candidates', 7),
            num_threads=config_dict.get('num_threads', 4),
            tasks=config_dict.get(
                'tasks',
                ['entity_extraction', 'edge_extraction', 'node_resolution', 'summary_generation'],
            ),
        )

        results: list[dict] = []
        tasks_optimized = 0
        tasks_failed = 0

        # Process each task sequentially (MIPROv2 is already parallelized internally)
        for task in config.tasks:
            # Single activity: load data + optimize (avoids gRPC payload limits)
            opt_result = await workflow.execute_activity(
                'optimize_task',
                args=[
                    task,
                    config.training_data_dir,
                    config.min_examples_per_task,
                    config.train_split,
                    config.max_examples,
                    config.num_candidates,
                    config.num_threads,
                ],
                start_to_close_timeout=timedelta(hours=2),
                retry_policy=common.RetryPolicy(
                    initial_interval=timedelta(seconds=10),
                    backoff_coefficient=2.0,
                    maximum_attempts=2,
                ),
            )

            if not opt_result['success']:
                results.append(opt_result)
                tasks_failed += 1
                continue

            # Store as candidate
            store_result = await workflow.execute_activity(
                'store_optimized_candidate',
                args=[
                    task,
                    opt_result['docstring'] or '',
                    opt_result['demos'] or [],
                    opt_result['val_score'] or 0.0,
                    opt_result['total_examples'],
                ],
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=common.RetryPolicy(
                    initial_interval=timedelta(seconds=2),
                    backoff_coefficient=2.0,
                    maximum_attempts=3,
                ),
            )

            opt_result['candidate_id'] = store_result['candidate_id']
            opt_result['candidate_version'] = store_result['version']
            results.append(opt_result)
            tasks_optimized += 1

        total_duration_ms = (workflow.time_ns() - start_ns) // 1_000_000

        return {
            'success': tasks_failed == 0,
            'tasks_optimized': tasks_optimized,
            'tasks_failed': tasks_failed,
            'results': results,
            'total_duration_ms': total_duration_ms,
        }


# =============================================================================
# Workflow Client Helper
# =============================================================================


async def start_optimization_workflow(
    temporal_address: str = '192.168.50.90:7233',
    temporal_namespace: str = 'graphiti',
    task_queue: str = 'graphiti-dspy-optimization',
    config: OptimizationConfig | None = None,
) -> str:
    """
    Start the optimization workflow and return the workflow ID.

    This is the entry point called by the optimization trigger.
    """
    from temporalio.client import Client

    config = config or OptimizationConfig()

    client = await Client.connect(temporal_address, namespace=temporal_namespace)

    workflow_id = f'dspy-optimization-{workflow.uuid4()}'

    handle = await client.start_workflow(
        DSPyOptimizationWorkflow.run,
        {
            'training_data_dir': config.training_data_dir,
            'min_examples_per_task': config.min_examples_per_task,
            'train_split': config.train_split,
            'max_examples': config.max_examples,
            'num_candidates': config.num_candidates,
            'num_threads': config.num_threads,
            'tasks': config.tasks,
        },
        id=workflow_id,
        task_queue=task_queue,
    )

    logger.info(f'Started optimization workflow: {workflow_id}')
    return workflow_id
