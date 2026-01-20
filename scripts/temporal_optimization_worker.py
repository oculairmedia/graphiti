#!/usr/bin/env python3
"""
Temporal Worker for DSPy MIPROv2 Optimization.

This worker handles the optimization workflow that runs MIPROv2 on collected
training data and stores optimized prompts as candidates.
"""

import asyncio
import logging
import os
import signal


def _configure_logging() -> None:
    log_level_str = os.getenv('LOG_LEVEL', 'INFO').upper()
    log_level = getattr(logging, log_level_str, logging.INFO)
    logging.basicConfig(
        level=log_level, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )


async def main() -> None:
    _configure_logging()
    logger = logging.getLogger(__name__)

    temporal_address = os.getenv('TEMPORAL_VISIBILITY_ADDRESS', '192.168.50.90:7233')
    temporal_namespace = os.getenv('TEMPORAL_VISIBILITY_NAMESPACE', 'graphiti')
    task_queue = os.getenv('TEMPORAL_OPTIMIZATION_TASK_QUEUE', 'graphiti-dspy-optimization')

    # Concurrency limits - optimization is resource-intensive
    max_concurrent_workflow_tasks = int(os.getenv('TEMPORAL_MAX_CONCURRENT_WORKFLOW_TASKS', '2'))
    max_concurrent_activities = int(os.getenv('TEMPORAL_MAX_CONCURRENT_ACTIVITIES', '2'))

    import importlib

    try:
        temporalio_client = importlib.import_module('temporalio.client')
        temporalio_worker = importlib.import_module('temporalio.worker')
    except ModuleNotFoundError as e:
        raise RuntimeError(
            'temporalio is not installed. Install with: pip install temporalio'
        ) from e

    from graphiti_core.dspy.optimization_workflow import (
        DSPyOptimizationWorkflow,
        OptimizationActivities,
    )

    Client = temporalio_client.Client
    Worker = temporalio_worker.Worker

    client = await Client.connect(temporal_address, namespace=temporal_namespace)

    activities_instance = OptimizationActivities()

    logger.info(
        'Starting Temporal optimization worker (address=%s namespace=%s task_queue=%s)',
        temporal_address,
        temporal_namespace,
        task_queue,
    )
    logger.info(
        'Concurrency limits: max_workflow_tasks=%d, max_activities=%d',
        max_concurrent_workflow_tasks,
        max_concurrent_activities,
    )

    # Disable workflow sandbox to avoid import issues
    from temporalio.worker import UnsandboxedWorkflowRunner

    worker = Worker(
        client,
        task_queue=task_queue,
        workflows=[DSPyOptimizationWorkflow],
        activities=[
            activities_instance.load_training_data,
            activities_instance.optimize_task,
            activities_instance.store_optimized_candidate,
        ],
        max_concurrent_workflow_tasks=max_concurrent_workflow_tasks,
        max_concurrent_activities=max_concurrent_activities,
        workflow_runner=UnsandboxedWorkflowRunner(),
    )

    stop_event = asyncio.Event()

    def _stop(*_args):
        logger.info('Shutdown signal received; stopping optimization worker...')
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _stop)
        except NotImplementedError:
            signal.signal(sig, lambda *_: _stop())

    async with worker:
        await stop_event.wait()


if __name__ == '__main__':
    asyncio.run(main())
