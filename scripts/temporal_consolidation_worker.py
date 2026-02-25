#!/usr/bin/env python3

import asyncio
import importlib
import logging
import os
import signal
from typing import Any

from graphiti_core.utils.consolidation.config import ConsolidationConfig


def _configure_prometheus_runtime(port: int) -> Any:
    logger = logging.getLogger(__name__)

    metrics_enabled = os.getenv('TEMPORAL_METRICS_ENABLED', 'true').lower() == 'true'
    if not metrics_enabled:
        logger.info('Temporal Prometheus metrics DISABLED')
        return None

    try:
        temporalio_runtime = importlib.import_module('temporalio.runtime')
        PrometheusConfig = temporalio_runtime.PrometheusConfig
        TelemetryConfig = temporalio_runtime.TelemetryConfig
        Runtime = temporalio_runtime.Runtime

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
    from graphiti_core.client_factory import GraphitiClientFactory
    from graphiti_core.driver.falkordb_driver import FalkorDriver
    from graphiti_core.graphiti import Graphiti

    logger = logging.getLogger(__name__)

    falkordb_host = os.getenv('FALKORDB_HOST', 'falkordb')
    falkordb_port = int(os.getenv('FALKORDB_PORT', '6379'))
    falkordb_database = os.getenv('FALKORDB_DATABASE', 'graphiti_migration')
    use_dspy = os.getenv('USE_DSPY', 'false').lower() == 'true'

    driver = FalkorDriver(
        host=falkordb_host,
        port=falkordb_port,
        database=falkordb_database,
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
    config = ConsolidationConfig.from_env()

    metrics_port = int(os.getenv('TEMPORAL_METRICS_PORT', '9196'))
    runtime = _configure_prometheus_runtime(metrics_port)

    max_concurrent_workflow_tasks = int(os.getenv('TEMPORAL_MAX_CONCURRENT_WORKFLOW_TASKS', '10'))
    max_concurrent_local_activities = int(
        os.getenv('TEMPORAL_MAX_CONCURRENT_LOCAL_ACTIVITIES', '5')
    )

    try:
        temporalio_client = importlib.import_module('temporalio.client')
        temporalio_worker = importlib.import_module('temporalio.worker')
    except ModuleNotFoundError as e:
        raise RuntimeError(
            'temporalio is not installed. Install with: pip install temporalio'
        ) from e

    from graphiti_core.utils.consolidation.activities import ConsolidationActivities
    from graphiti_core.utils.consolidation.workflow import GraphConsolidationWorkflow

    Client = temporalio_client.Client
    Worker = temporalio_worker.Worker

    connect_kwargs = {'namespace': temporal_namespace}
    if runtime:
        connect_kwargs['runtime'] = runtime

    client = await Client.connect(temporal_address, **connect_kwargs)

    activities_instance = ConsolidationActivities(_create_graphiti)
    activities = [
        activities_instance.collect_metrics,
        activities_instance.prune_orphaned_nodes,
        activities_instance.prune_junk_entities,
        activities_instance.prune_old_episodic_nodes,
        activities_instance.prune_invalidated_edges,
        activities_instance.merge_duplicate_of_edges,
        activities_instance.merge_same_name_entities,
        activities_instance.store_consolidation_report,
    ]

    logger.info(
        'Starting Temporal consolidation worker (address=%s namespace=%s task_queue=%s)',
        temporal_address,
        temporal_namespace,
        config.task_queue,
    )
    logger.info(
        'Concurrency limits: max_workflow_tasks=%d, max_activities=%d, max_local_activities=%d',
        max_concurrent_workflow_tasks,
        config.max_concurrent_activities,
        max_concurrent_local_activities,
    )

    UnsandboxedWorkflowRunner = temporalio_worker.UnsandboxedWorkflowRunner

    worker = Worker(
        client,
        task_queue=config.task_queue,
        workflows=[GraphConsolidationWorkflow],
        activities=activities,
        max_concurrent_workflow_tasks=max_concurrent_workflow_tasks,
        max_concurrent_activities=config.max_concurrent_activities,
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
