#!/usr/bin/env python3
"""
Schedule or manually trigger the Graph Consolidation Workflow.

Usage:
    # Trigger a one-off consolidation run
    python scripts/schedule_consolidation.py --once

    # Create a Temporal schedule for nightly consolidation (3 AM UTC)
    python scripts/schedule_consolidation.py --schedule

    # Create schedule with custom cron expression
    python scripts/schedule_consolidation.py --schedule --cron "0 5 * * *"

    # Delete the existing schedule
    python scripts/schedule_consolidation.py --delete-schedule

    # Custom retention (days) and batch size
    python scripts/schedule_consolidation.py --once --retention-days 60 --batch-size 200
"""

import argparse
import asyncio
import logging
import os
import uuid

logging.basicConfig(
    level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

SCHEDULE_ID = 'graphiti-consolidation-nightly'
WORKFLOW_ID_PREFIX = 'consolidation-'
DEFAULT_CRON = '0 3 * * *'  # 3 AM UTC daily


async def trigger_once(
    client,
    task_queue: str,
    retention_days: int = 90,
    batch_size: int = 100,
) -> str:
    """Trigger a single consolidation run and return the workflow ID."""
    from graphiti_core.utils.consolidation.workflow import (
        ConsolidationInput,
        GraphConsolidationWorkflow,
    )

    run_id = str(uuid.uuid4())[:8]
    workflow_id = f'{WORKFLOW_ID_PREFIX}{run_id}'

    handle = await client.start_workflow(
        GraphConsolidationWorkflow.run,
        ConsolidationInput(
            retention_days=retention_days,
            batch_size=batch_size,
            run_id=run_id,
        ),
        id=workflow_id,
        task_queue=task_queue,
    )

    logger.info('Started consolidation workflow: %s', workflow_id)
    logger.info('Waiting for completion...')

    result = await handle.result()
    logger.info('Consolidation complete: %s', result)
    return workflow_id


async def create_schedule(
    client,
    task_queue: str,
    cron: str = DEFAULT_CRON,
    retention_days: int = 90,
    batch_size: int = 100,
) -> None:
    """Create a Temporal schedule for periodic consolidation."""
    from temporalio.client import (
        Schedule,
        ScheduleActionStartWorkflow,
        ScheduleSpec,
        ScheduleIntervalSpec,
    )
    from graphiti_core.utils.consolidation.workflow import (
        ConsolidationInput,
        GraphConsolidationWorkflow,
    )

    schedule_input = ConsolidationInput(
        retention_days=retention_days,
        batch_size=batch_size,
    )

    action = ScheduleActionStartWorkflow(
        GraphConsolidationWorkflow.run,
        schedule_input,
        id=f'{WORKFLOW_ID_PREFIX}scheduled',
        task_queue=task_queue,
    )

    spec = ScheduleSpec(cron_expressions=[cron])

    await client.create_schedule(
        SCHEDULE_ID,
        Schedule(action=action, spec=spec),
    )
    logger.info('Created schedule "%s" with cron "%s"', SCHEDULE_ID, cron)


async def delete_schedule(client) -> None:
    """Delete the consolidation schedule."""
    handle = client.get_schedule_handle(SCHEDULE_ID)
    await handle.delete()
    logger.info('Deleted schedule "%s"', SCHEDULE_ID)


async def main() -> None:
    parser = argparse.ArgumentParser(description='Graph Consolidation Scheduler')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--once', action='store_true', help='Trigger a single consolidation run')
    group.add_argument('--schedule', action='store_true', help='Create a nightly schedule')
    group.add_argument(
        '--delete-schedule', action='store_true', help='Delete the existing schedule'
    )
    parser.add_argument(
        '--cron',
        default=DEFAULT_CRON,
        help=f'Cron expression for schedule (default: {DEFAULT_CRON})',
    )
    parser.add_argument('--retention-days', type=int, default=90, help='Episodic retention (days)')
    parser.add_argument('--batch-size', type=int, default=100, help='Batch size for pruning')
    args = parser.parse_args()

    temporal_address = os.getenv('TEMPORAL_VISIBILITY_ADDRESS', '192.168.50.90:7233')
    temporal_namespace = os.getenv('TEMPORAL_VISIBILITY_NAMESPACE', 'graphiti')
    task_queue = os.getenv('TEMPORAL_CONSOLIDATION_TASK_QUEUE', 'graphiti-consolidation')

    from temporalio.client import Client

    client = await Client.connect(temporal_address, namespace=temporal_namespace)

    if args.once:
        await trigger_once(client, task_queue, args.retention_days, args.batch_size)
    elif args.schedule:
        await create_schedule(client, task_queue, args.cron, args.retention_days, args.batch_size)
    elif args.delete_schedule:
        await delete_schedule(client)


if __name__ == '__main__':
    asyncio.run(main())
