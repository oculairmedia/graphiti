#!/usr/bin/env python3

import asyncio
import logging
import os
import signal
import sys

sys.path.insert(0, '/scripts')


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
    task_queue = os.getenv('TEMPORAL_MONITORING_TASK_QUEUE', 'graphiti-monitoring')
    metrics_port = int(os.getenv('TEMPORAL_METRICS_PORT', '9195'))
    metrics_enabled = os.getenv('TEMPORAL_METRICS_ENABLED', 'true').lower() == 'true'

    import importlib

    try:
        temporalio_client = importlib.import_module('temporalio.client')
        temporalio_worker = importlib.import_module('temporalio.worker')
    except ModuleNotFoundError as e:
        raise RuntimeError(
            'temporalio is not installed. Install with: pip install temporalio'
        ) from e

    from temporal_monitoring.workflow import GraphHealthMonitorWorkflow
    from temporal_monitoring.activities import MonitoringActivities

    Client = temporalio_client.Client
    Worker = temporalio_worker.Worker

    runtime = None
    if metrics_enabled:
        try:
            from temporalio.runtime import PrometheusConfig, TelemetryConfig, Runtime

            prometheus_config = PrometheusConfig(bind_address=f'0.0.0.0:{metrics_port}')
            telemetry_config = TelemetryConfig(metrics=prometheus_config)
            runtime = Runtime(telemetry=telemetry_config)
            logger.info('Temporal Prometheus metrics enabled on port %d', metrics_port)
        except Exception as e:
            logger.warning('Failed to configure Prometheus metrics: %s', e)

    connect_kwargs = {'namespace': temporal_namespace}
    if runtime:
        connect_kwargs['runtime'] = runtime

    client = await Client.connect(temporal_address, **connect_kwargs)

    activities_instance = MonitoringActivities()

    logger.info(
        'Starting Temporal monitoring worker (address=%s namespace=%s task_queue=%s)',
        temporal_address,
        temporal_namespace,
        task_queue,
    )

    from temporalio.worker import UnsandboxedWorkflowRunner

    worker = Worker(
        client,
        task_queue=task_queue,
        workflows=[GraphHealthMonitorWorkflow],
        activities=[activities_instance.check_graph_health],
        max_concurrent_workflow_tasks=5,
        max_concurrent_activities=3,
        workflow_runner=UnsandboxedWorkflowRunner(),
    )

    stop_event = asyncio.Event()

    def _stop(*_args):
        logger.info('Shutdown signal received; stopping monitoring worker...')
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
