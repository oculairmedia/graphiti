from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

import importlib

workflow = importlib.import_module('temporalio.workflow')
common = importlib.import_module('temporalio.common')

with workflow.unsafe.imports_passed_through():
    from graphiti_core.utils.temporal_visibility.activities import (
        ExtractNodesOutput,
        ResolveNodesOutput,
        ExtractEdgesOutput,
        PersistOutput,
        IngestionResult,
    )
    from graphiti_core.utils.temporal_visibility.config import TemporalStageQueueConfig


@dataclass
class IngestEpisodeInput:
    episode_uuid: str
    group_id: str
    name: str
    episode_body: str
    source: str
    source_description: str
    reference_time: str
    entity_types: dict[str, Any] | None = None
    excluded_entity_types: list[str] | None = None
    edge_types: dict[str, Any] | None = None
    edge_type_map: dict[str, list[str]] | None = None
    previous_episode_uuids: list[str] | None = None
    store_raw_content: bool = True


@workflow.defn(name='IngestEpisodeWorkflow')
class IngestEpisodeWorkflow:
    @workflow.run
    async def run(self, input: IngestEpisodeInput) -> IngestionResult:
        start_ns = workflow.time_ns()
        stages: dict[str, dict[str, Any]] = {}
        stage_queues = TemporalStageQueueConfig.from_env()

        extract_nodes_output: dict = await workflow.execute_activity(
            'extract_nodes',
            args=[
                input.episode_uuid,
                input.group_id,
                input.episode_body,
                input.name,
                input.source,
                input.source_description,
                input.reference_time,
                input.entity_types,
                input.excluded_entity_types,
                input.previous_episode_uuids,
            ],
            start_to_close_timeout=timedelta(minutes=10),
            task_queue=stage_queues.extract_queue,
            retry_policy=common.RetryPolicy(
                initial_interval=timedelta(seconds=2),
                backoff_coefficient=2.0,
                maximum_attempts=3,
            ),
        )
        stages['extract_nodes'] = {
            'duration_ms': extract_nodes_output['duration_ms'],
            'node_count': len(extract_nodes_output['extracted_node_dicts']),
        }

        resolve_nodes_output: dict = await workflow.execute_activity(
            'resolve_nodes',
            args=[
                input.episode_uuid,
                input.group_id,
                extract_nodes_output['extracted_node_dicts'],
                input.episode_body,
                input.name,
                input.source,
                input.source_description,
                input.reference_time,
                input.entity_types,
                input.previous_episode_uuids,
            ],
            start_to_close_timeout=timedelta(minutes=10),
            task_queue=stage_queues.resolve_queue,
            retry_policy=common.RetryPolicy(
                initial_interval=timedelta(seconds=2),
                backoff_coefficient=2.0,
                maximum_attempts=3,
            ),
        )
        stages['resolve_nodes'] = {
            'duration_ms': resolve_nodes_output['duration_ms'],
            'node_count': len(resolve_nodes_output['resolved_node_uuids']),
            'duplicate_count': len(resolve_nodes_output['duplicate_node_uuids']),
        }

        extract_edges_output: dict = await workflow.execute_activity(
            'extract_edges',
            args=[
                input.episode_uuid,
                input.group_id,
                extract_nodes_output['extracted_node_dicts'],
                input.episode_body,
                input.name,
                input.source,
                input.source_description,
                input.reference_time,
                input.edge_types,
                input.edge_type_map,
                input.previous_episode_uuids,
            ],
            start_to_close_timeout=timedelta(minutes=10),
            task_queue=stage_queues.edge_queue,
            retry_policy=common.RetryPolicy(
                initial_interval=timedelta(seconds=2),
                backoff_coefficient=2.0,
                maximum_attempts=3,
            ),
        )
        stages['extract_edges'] = {
            'duration_ms': extract_edges_output['duration_ms'],
            'edge_count': len(extract_edges_output['extracted_edge_dicts']),
        }

        persist_output: dict = await workflow.execute_activity(
            'resolve_edges_and_persist',
            args=[
                input.episode_uuid,
                input.group_id,
                extract_nodes_output['extracted_node_dicts'],
                extract_edges_output['extracted_edge_dicts'],
                resolve_nodes_output['uuid_map'],
                resolve_nodes_output['duplicate_node_uuids'],
                input.episode_body,
                input.name,
                input.source,
                input.source_description,
                input.reference_time,
                input.edge_types,
                input.edge_type_map,
                input.previous_episode_uuids,
                input.store_raw_content,
            ],
            start_to_close_timeout=timedelta(minutes=15),
            task_queue=stage_queues.persist_queue,
            retry_policy=common.RetryPolicy(
                initial_interval=timedelta(seconds=2),
                backoff_coefficient=2.0,
                maximum_attempts=3,
            ),
        )
        stages['persist'] = {
            'duration_ms': persist_output['duration_ms'],
            'node_count': persist_output['node_count'],
            'entity_edge_count': persist_output['entity_edge_count'],
            'episodic_edge_count': persist_output['episodic_edge_count'],
            'merge_operation_count': persist_output['merge_operation_count'],
        }

        total_duration_ms = (workflow.time_ns() - start_ns) // 1_000_000

        return IngestionResult(
            episode_uuid=input.episode_uuid,
            group_id=input.group_id,
            node_count=persist_output['node_count'],
            entity_edge_count=persist_output['entity_edge_count'],
            total_duration_ms=total_duration_ms,
            stages=stages,
        )
