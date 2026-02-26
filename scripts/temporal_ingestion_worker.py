#!/usr/bin/env python3

import asyncio
import logging
import os
import signal
from typing import Callable, Awaitable, Optional

from graphiti_core.utils.temporal_visibility.config import (
    TemporalStageQueueConfig,
    TemporalStageConcurrencyConfig,
)


def _configure_prometheus_runtime(port: int) -> Optional['Runtime']:
    """Configure Temporal runtime with Prometheus metrics exporter.

    Args:
        port: Port to expose Prometheus metrics on

    Returns:
        Configured Runtime with Prometheus telemetry, or None if disabled
    """
    logger = logging.getLogger(__name__)

    metrics_enabled = os.getenv('TEMPORAL_METRICS_ENABLED', 'true').lower() == 'true'
    if not metrics_enabled:
        logger.info('Temporal Prometheus metrics DISABLED')
        return None

    try:
        from temporalio.runtime import PrometheusConfig, TelemetryConfig, Runtime

        prometheus_config = PrometheusConfig(bind_address=f'0.0.0.0:{port}')
        telemetry_config = TelemetryConfig(metrics=prometheus_config)
        runtime = Runtime(telemetry=telemetry_config)

        logger.info('Temporal Prometheus metrics enabled on port %d', port)
        return runtime
    except Exception as e:
        logger.warning('Failed to configure Prometheus metrics: %s', e)
        return None


def _configure_logging() -> None:
    log_level_str = os.getenv('LOG_LEVEL', 'INFO').upper()
    log_level = getattr(logging, log_level_str, logging.INFO)
    logging.basicConfig(
        level=log_level, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )


async def _create_graphiti():
    from graphiti_core.graphiti import Graphiti
    from graphiti_core.driver.falkordb_driver import FalkorDriver
    from graphiti_core.client_factory import GraphitiClientFactory

    logger = logging.getLogger(__name__)

    falkordb_host = os.getenv('FALKORDB_HOST', 'falkordb')
    falkordb_port = int(os.getenv('FALKORDB_PORT', '6379'))
    falkordb_database = os.getenv('FALKORDB_DATABASE', 'graphiti_migration')
    falkordb_max_conn_str = os.getenv('FALKORDB_MAX_CONNECTIONS')
    falkordb_max_connections = int(falkordb_max_conn_str) if falkordb_max_conn_str else None
    use_dspy = os.getenv('USE_DSPY', 'false').lower() == 'true'

    driver = FalkorDriver(
        host=falkordb_host,
        port=falkordb_port,
        database=falkordb_database,
        max_connections=falkordb_max_connections,
    )

    if use_dspy:
        logger.info('DSPy pipeline ENABLED - using DSPy for LLM extraction')
        graphiti = Graphiti(graph_driver=driver, use_dspy=True)
    else:
        logger.info('Creating LLM and embedder clients using factory...')
        llm_client = GraphitiClientFactory.create_llm_client()
        embedder = GraphitiClientFactory.create_embedder()
        graphiti = Graphiti(
            graph_driver=driver,
            llm_client=llm_client,
            embedder=embedder,
            use_dspy=False,
        )

    return graphiti


async def main() -> None:
    _configure_logging()
    logger = logging.getLogger(__name__)

    temporal_address = os.getenv('TEMPORAL_VISIBILITY_ADDRESS', '192.168.50.90:7233')
    temporal_namespace = os.getenv('TEMPORAL_VISIBILITY_NAMESPACE', 'graphiti')
    worker_mode = os.getenv('WORKER_MODE', 'all').lower()
    stage_queues = TemporalStageQueueConfig.from_env()
    stage_concurrency = TemporalStageConcurrencyConfig.from_env()

    # Prometheus metrics port - different port per worker mode to avoid conflicts
    # Using 919x range to avoid conflicts with Kafka (9092) and Prometheus (9090)
    metrics_port_map = {
        'workflow': 9190,
        'extract': 9191,
        'resolve': 9192,
        'edge': 9193,
        'persist': 9194,
        'legacy': 9195,
        'all': 9195,
    }
    metrics_port = int(
        os.getenv('TEMPORAL_METRICS_PORT', str(metrics_port_map.get(worker_mode, 9090)))
    )

    # Configure Prometheus runtime (must be done before Client.connect)
    runtime = _configure_prometheus_runtime(metrics_port)

    # Concurrency limits - prevents overwhelming LLM APIs
    max_concurrent_workflow_tasks = int(os.getenv('TEMPORAL_MAX_CONCURRENT_WORKFLOW_TASKS', '10'))
    max_concurrent_local_activities = int(
        os.getenv('TEMPORAL_MAX_CONCURRENT_LOCAL_ACTIVITIES', '5')
    )

    import importlib

    try:
        temporalio_client = importlib.import_module('temporalio.client')
        temporalio_worker = importlib.import_module('temporalio.worker')
    except ModuleNotFoundError as e:
        raise RuntimeError(
            'temporalio is not installed. Install with: pip install temporalio'
        ) from e

    from graphiti_core.utils.temporal_visibility.ingestion_workflow import IngestEpisodeWorkflow
    from graphiti_core.utils.temporal_visibility.activities import (
        IngestionActivities,
        RateLimitConfig,
    )

    Client = temporalio_client.Client
    Worker = temporalio_worker.Worker

    # Connect with custom runtime if metrics are enabled
    connect_kwargs = {'namespace': temporal_namespace}
    if runtime:
        connect_kwargs['runtime'] = runtime

    client = await Client.connect(temporal_address, **connect_kwargs)

    # Load rate limiting config from environment
    rate_limit_config = RateLimitConfig.from_env()
    activities_instance = IngestionActivities(_create_graphiti, rate_limit_config)

    if worker_mode == 'workflow':
        task_queue = stage_queues.workflow_queue
        workflows = [IngestEpisodeWorkflow]
        activities = []
        max_concurrent_activities = stage_concurrency.legacy_max_activities
    elif worker_mode == 'extract':
        task_queue = stage_queues.extract_queue
        workflows = []
        activities = [activities_instance.extract_nodes]
        max_concurrent_activities = stage_concurrency.extract_max_activities
    elif worker_mode == 'resolve':
        task_queue = stage_queues.resolve_queue
        workflows = []
        activities = [activities_instance.resolve_nodes]
        max_concurrent_activities = stage_concurrency.resolve_max_activities
    elif worker_mode == 'edge':
        task_queue = stage_queues.edge_queue
        workflows = []
        activities = [activities_instance.extract_edges]
        max_concurrent_activities = stage_concurrency.edge_max_activities
    elif worker_mode == 'persist':
        task_queue = stage_queues.persist_queue
        workflows = []
        activities = [activities_instance.resolve_edges_and_persist]
        max_concurrent_activities = stage_concurrency.persist_max_activities
    elif worker_mode in ('legacy', 'all'):
        task_queue = stage_queues.legacy_queue
        workflows = [IngestEpisodeWorkflow]
        activities = [
            activities_instance.extract_nodes,
            activities_instance.resolve_nodes,
            activities_instance.extract_edges,
            activities_instance.resolve_edges_and_persist,
        ]
        max_concurrent_activities = stage_concurrency.legacy_max_activities
    else:
        raise ValueError(f'Unknown WORKER_MODE: {worker_mode}')

    logger.info(
        'Starting Temporal ingestion worker (mode=%s address=%s namespace=%s task_queue=%s)',
        worker_mode,
        temporal_address,
        temporal_namespace,
        task_queue,
    )
    logger.info(
        'Concurrency limits: max_workflow_tasks=%d, max_activities=%d, max_local_activities=%d',
        max_concurrent_workflow_tasks,
        max_concurrent_activities,
        max_concurrent_local_activities,
    )
    logger.info('Staged queues enabled: %s', stage_queues.staged_enabled)

    # Disable workflow sandbox to avoid import issues with numpy/graphiti_core
    # The sandbox tries to validate all imports but fails with complex dependencies
    from temporalio.worker import UnsandboxedWorkflowRunner

    worker = Worker(
        client,
        task_queue=task_queue,
        workflows=workflows,
        activities=activities,
        max_concurrent_workflow_tasks=max_concurrent_workflow_tasks,
        max_concurrent_activities=max_concurrent_activities,
        max_concurrent_local_activities=max_concurrent_local_activities,
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
