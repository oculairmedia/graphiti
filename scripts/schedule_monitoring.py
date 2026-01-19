#!/usr/bin/env python3

import asyncio
import os
import sys
from datetime import timedelta

# Add scripts directory to path for standalone temporal_monitoring module
sys.path.insert(0, '/scripts')


async def main():
    temporal_address = os.getenv('TEMPORAL_VISIBILITY_ADDRESS', '192.168.50.90:7233')
    temporal_namespace = os.getenv('TEMPORAL_VISIBILITY_NAMESPACE', 'graphiti')
    interval_minutes = int(os.getenv('MONITORING_INTERVAL_MINUTES', '5'))

    from temporalio.client import (
        Client,
        ScheduleActionStartWorkflow,
        Schedule,
        ScheduleSpec,
        ScheduleIntervalSpec,
        ScheduleState,
    )

    # Import from standalone module (avoids graphiti_core -> dspy dependency chain)
    from temporal_monitoring.workflow import (
        GraphHealthMonitorWorkflow,
        MonitoringInput,
    )

    client = await Client.connect(temporal_address, namespace=temporal_namespace)

    schedule_id = 'graphiti-health-monitor'

    try:
        handle = client.get_schedule_handle(schedule_id)
        desc = await handle.describe()
        print(f"Schedule '{schedule_id}' already exists, updating...")
        await handle.update(
            lambda _: Schedule(
                action=ScheduleActionStartWorkflow(
                    GraphHealthMonitorWorkflow.run,
                    MonitoringInput(
                        check_interval_minutes=interval_minutes,
                        alert_on_isolated=True,
                        min_edge_ratio=3.0,
                    ),
                    id='graph-health-check',
                    task_queue='graphiti-monitoring',
                ),
                spec=ScheduleSpec(
                    intervals=[ScheduleIntervalSpec(every=timedelta(minutes=interval_minutes))]
                ),
                state=ScheduleState(note=f'Graph health check every {interval_minutes} minutes'),
            )
        )
        print(f'Schedule updated: runs every {interval_minutes} minutes')
    except Exception:
        await client.create_schedule(
            schedule_id,
            Schedule(
                action=ScheduleActionStartWorkflow(
                    GraphHealthMonitorWorkflow.run,
                    MonitoringInput(
                        check_interval_minutes=interval_minutes,
                        alert_on_isolated=True,
                        min_edge_ratio=3.0,
                    ),
                    id='graph-health-check',
                    task_queue='graphiti-monitoring',
                ),
                spec=ScheduleSpec(
                    intervals=[ScheduleIntervalSpec(every=timedelta(minutes=interval_minutes))]
                ),
                state=ScheduleState(note=f'Graph health check every {interval_minutes} minutes'),
            ),
        )
        print(f'Schedule created: {schedule_id} - runs every {interval_minutes} minutes')

    print(
        f'\nTo view in Temporal UI: http://192.168.50.90:8080/namespaces/graphiti/schedules/{schedule_id}'
    )


if __name__ == '__main__':
    asyncio.run(main())
