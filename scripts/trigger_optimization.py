#!/usr/bin/env python3
"""
Trigger MIPROv2 optimization workflow via Temporal.

Usage:
    python3 scripts/trigger_optimization.py
    python3 scripts/trigger_optimization.py --tasks entity_extraction edge_extraction
    python3 scripts/trigger_optimization.py --num-candidates 5
"""

import argparse
import asyncio
import logging
import sys

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def main():
    parser = argparse.ArgumentParser(description='Trigger MIPROv2 optimization')
    parser.add_argument(
        '--tasks',
        nargs='+',
        default=['entity_extraction', 'edge_extraction', 'node_resolution', 'summary_generation'],
        help='Tasks to optimize',
    )
    parser.add_argument('--num-candidates', type=int, default=7, help='MIPROv2 candidates')
    parser.add_argument('--num-threads', type=int, default=4, help='MIPROv2 threads')
    parser.add_argument('--min-examples', type=int, default=50, help='Min examples per task')
    parser.add_argument('--train-split', type=float, default=0.8, help='Train split ratio')
    parser.add_argument('--temporal-address', default='192.168.50.90:7233', help='Temporal address')
    parser.add_argument('--namespace', default='graphiti', help='Temporal namespace')
    parser.add_argument(
        '--task-queue', default='graphiti-dspy-optimization', help='Temporal task queue'
    )
    parser.add_argument('--wait', action='store_true', help='Wait for workflow completion')
    args = parser.parse_args()

    from temporalio.client import Client

    logger.info(f'Connecting to Temporal at {args.temporal_address}...')
    client = await Client.connect(args.temporal_address, namespace=args.namespace)

    import uuid

    workflow_id = f'dspy-optimization-{uuid.uuid4()}'

    config = {
        'training_data_dir': '/data/training_data',
        'min_examples_per_task': args.min_examples,
        'train_split': args.train_split,
        'num_candidates': args.num_candidates,
        'num_threads': args.num_threads,
        'tasks': args.tasks,
    }

    logger.info(f'Starting optimization workflow: {workflow_id}')
    logger.info(f'Tasks: {args.tasks}')
    logger.info(
        f'Config: candidates={args.num_candidates}, threads={args.num_threads}, '
        f'min_examples={args.min_examples}, train_split={args.train_split}'
    )

    # Import workflow class for type-safe execution
    sys.path.insert(0, '/opt/stacks/graphiti')
    from graphiti_core.dspy.optimization_workflow import DSPyOptimizationWorkflow

    handle = await client.start_workflow(
        DSPyOptimizationWorkflow.run,
        config,
        id=workflow_id,
        task_queue=args.task_queue,
    )

    logger.info(f'Workflow started: {workflow_id}')
    logger.info(
        f'Monitor at: http://192.168.50.90:8084/namespaces/graphiti/workflows/{workflow_id}'
    )

    if args.wait:
        logger.info('Waiting for workflow completion...')
        result = await handle.result()
        logger.info(f'Workflow completed!')
        logger.info(f'Results: {result}')
        return result
    else:
        logger.info('Workflow running in background. Use --wait to block until completion.')
        logger.info(f'Or check Temporal UI at http://192.168.50.90:8084')


if __name__ == '__main__':
    asyncio.run(main())
