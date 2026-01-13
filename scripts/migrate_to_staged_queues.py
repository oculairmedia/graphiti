#!/usr/bin/env python3
"""
Migrate in-flight ingestion workflows from the legacy single queue to staged queues.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from dataclasses import dataclass
from typing import Iterable

from graphiti_core.utils.temporal_visibility.config import TemporalStageQueueConfig

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MigrationConfig:
    address: str
    namespace: str
    legacy_task_queue: str
    workflow_task_queue: str
    workflow_timeout_hours: int

    @classmethod
    def from_env(cls) -> 'MigrationConfig':
        stage_queues = TemporalStageQueueConfig.from_env()
        return cls(
            address=os.getenv('TEMPORAL_VISIBILITY_ADDRESS', '192.168.50.90:7233'),
            namespace=os.getenv('TEMPORAL_VISIBILITY_NAMESPACE', 'graphiti'),
            legacy_task_queue=stage_queues.legacy_queue,
            workflow_task_queue=stage_queues.workflow_queue,
            workflow_timeout_hours=int(os.getenv('TEMPORAL_INGESTION_WORKFLOW_TIMEOUT_HOURS', '8')),
        )


async def _get_workflow_input(client, workflow_id: str) -> dict | None:
    try:
        handle = client.get_workflow_handle(workflow_id)
        async for event in handle.fetch_history_events():
            if event.event_type == 1:  # WorkflowExecutionStarted
                attrs = event.workflow_execution_started_event_attributes
                if attrs.input and attrs.input.payloads:
                    payload_data = attrs.input.payloads[0].data
                    return json.loads(payload_data)
        return None
    except Exception as exc:
        logger.error('Error getting input for %s: %s', workflow_id, exc)
        return None


async def _completed_activity_names(client, workflow_id: str) -> set[str]:
    completed = set()
    try:
        handle = client.get_workflow_handle(workflow_id)
        async for event in handle.fetch_history_events():
            if event.event_type == 17:  # ActivityTaskCompleted
                attrs = event.activity_task_completed_event_attributes
                if attrs and attrs.activity_type:
                    completed.add(attrs.activity_type.name)
    except Exception as exc:
        logger.error('Error fetching activity history for %s: %s', workflow_id, exc)
    return completed


async def _start_new_workflow(
    client, input_data: dict, task_queue: str, timeout_hours: int
) -> str | None:
    from datetime import timedelta
    from graphiti_core.utils.temporal_visibility.ingestion_workflow import (
        IngestEpisodeWorkflow,
        IngestEpisodeInput,
    )

    episode_uuid = input_data['episode_uuid']
    new_wf_id = f'migrated-{episode_uuid}'

    try:
        inp = IngestEpisodeInput(
            episode_uuid=episode_uuid,
            group_id=input_data['group_id'],
            name=input_data['name'],
            episode_body=input_data['episode_body'],
            source=input_data['source'],
            source_description=input_data['source_description'],
            reference_time=input_data['reference_time'],
            entity_types=input_data.get('entity_types'),
            excluded_entity_types=input_data.get('excluded_entity_types'),
            edge_types=input_data.get('edge_types'),
            edge_type_map=input_data.get('edge_type_map'),
            previous_episode_uuids=input_data.get('previous_episode_uuids'),
            store_raw_content=input_data.get('store_raw_content', True),
        )

        await client.start_workflow(
            IngestEpisodeWorkflow.run,
            args=[inp],
            id=new_wf_id,
            task_queue=task_queue,
            execution_timeout=timedelta(hours=timeout_hours),
        )
        logger.info('Started migrated workflow: %s', new_wf_id)
        return new_wf_id
    except Exception as exc:
        if 'already started' in str(exc).lower():
            logger.info('Workflow %s already exists, skipping', new_wf_id)
            return None
        logger.error('Error starting workflow for %s: %s', episode_uuid, exc)
        return None


async def _cancel_workflow(client, workflow_id: str) -> bool:
    try:
        handle = client.get_workflow_handle(workflow_id)
        await handle.cancel()
        return True
    except Exception as exc:
        logger.error('Failed to cancel %s: %s', workflow_id, exc)
        return False


def _should_skip(completed_activity_names: Iterable[str]) -> bool:
    skip_stages = {'resolve_nodes', 'extract_edges', 'resolve_edges_and_persist'}
    return any(stage in completed_activity_names for stage in skip_stages)


async def migrate_workflows(limit: int, dry_run: bool, force: bool) -> None:
    from temporalio.client import Client

    config = MigrationConfig.from_env()

    if limit == 0:
        limit = 10_000

    if limit > 100 and not force and not dry_run:
        raise RuntimeError('Refusing to migrate more than 100 workflows without --force')

    logger.info('Connecting to Temporal at %s', config.address)
    client = await Client.connect(config.address, namespace=config.namespace)

    query = f"TaskQueue = '{config.legacy_task_queue}' AND ExecutionStatus = 'Running'"
    workflow_ids: list[str] = []
    async for wf in client.list_workflows(query=query):
        workflow_ids.append(wf.id)
        if len(workflow_ids) >= limit:
            break

    logger.info('Found %d workflows on legacy queue', len(workflow_ids))

    migrated = 0
    skipped = 0
    errors = 0

    for index, wf_id in enumerate(workflow_ids, start=1):
        logger.info('Processing %d/%d: %s', index, len(workflow_ids), wf_id)

        completed = await _completed_activity_names(client, wf_id)
        if _should_skip(completed):
            logger.info('Skipping %s (already past extract_nodes)', wf_id)
            skipped += 1
            continue

        input_data = await _get_workflow_input(client, wf_id)
        if not input_data:
            logger.warning('Could not get input for %s', wf_id)
            errors += 1
            continue

        if dry_run:
            logger.info('Dry run: would cancel %s and start migrated workflow', wf_id)
            migrated += 1
            continue

        if not await _cancel_workflow(client, wf_id):
            errors += 1
            continue

        new_id = await _start_new_workflow(
            client,
            input_data,
            config.workflow_task_queue,
            config.workflow_timeout_hours,
        )
        if new_id:
            migrated += 1
        else:
            skipped += 1

        await asyncio.sleep(0.1)

    logger.info('Done. Migrated: %d, Skipped: %d, Errors: %d', migrated, skipped, errors)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Migrate ingestion workflows to staged queues')
    parser.add_argument(
        '--limit', type=int, default=100, help='Max workflows to migrate (0 = no limit)'
    )
    parser.add_argument(
        '--dry-run', action='store_true', help='Show actions without cancelling/restarting'
    )
    parser.add_argument(
        '--force', action='store_true', help='Allow migration of more than 100 workflows'
    )
    return parser.parse_args()


if __name__ == '__main__':
    args = parse_args()
    asyncio.run(migrate_workflows(args.limit, args.dry_run, args.force))
