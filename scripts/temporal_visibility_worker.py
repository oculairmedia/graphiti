#!/usr/bin/env python3

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

    temporal_address = os.getenv('TEMPORAL_VISIBILITY_ADDRESS', 'temporal:7233')
    temporal_namespace = os.getenv('TEMPORAL_VISIBILITY_NAMESPACE', 'default')
    task_queue = os.getenv('TEMPORAL_VISIBILITY_TASK_QUEUE', 'graphiti-visibility')

    import importlib

    try:
        temporalio_client = importlib.import_module('temporalio.client')
        temporalio_worker = importlib.import_module('temporalio.worker')
    except ModuleNotFoundError as e:
        raise RuntimeError(
            'temporalio is not installed. Install with: pip install temporalio'
        ) from e

    from temporalio.worker import UnsandboxedWorkflowRunner
    from graphiti_core.utils.temporal_visibility.workflow import EpisodeIngestionVisibilityWorkflow

    Client = temporalio_client.Client
    Worker = temporalio_worker.Worker

    logger.info(
        'Starting Temporal visibility worker (address=%s namespace=%s task_queue=%s)',
        temporal_address,
        temporal_namespace,
        task_queue,
    )

    client = await Client.connect(temporal_address, namespace=temporal_namespace)

    worker = Worker(
        client,
        task_queue=task_queue,
        workflows=[EpisodeIngestionVisibilityWorkflow],
        activities=[],
        workflow_runner=UnsandboxedWorkflowRunner(),
    )

    stop_event = asyncio.Event()

    def _stop(*_args):
        logger.info('Shutdown signal received; stopping Temporal worker...')
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
