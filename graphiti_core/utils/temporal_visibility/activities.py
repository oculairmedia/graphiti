from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from temporalio import activity

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting between activities."""

    # Delay in seconds between activities (prevents API flooding)
    inter_activity_delay: float = 0.0
    # Delay after LLM-heavy activities (extract_nodes, extract_edges)
    post_llm_delay: float = 0.0
    # Maximum concurrent LLM calls within an activity (0 = no limit)
    max_concurrent_llm_calls: int = 0

    @classmethod
    def from_env(cls) -> 'RateLimitConfig':
        """Load rate limit config from environment variables."""
        return cls(
            inter_activity_delay=float(
                os.getenv('TEMPORAL_RATE_LIMIT_INTER_ACTIVITY_DELAY', '0.0')
            ),
            post_llm_delay=float(os.getenv('TEMPORAL_RATE_LIMIT_POST_LLM_DELAY', '0.0')),
            max_concurrent_llm_calls=int(os.getenv('TEMPORAL_RATE_LIMIT_MAX_CONCURRENT_LLM', '0')),
        )


@dataclass
class IngestionInput:
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
    update_communities: bool = False
    previous_episode_uuids: list[str] | None = None


@dataclass
class ExtractNodesOutput:
    episode_uuid: str
    extracted_node_dicts: list[dict[str, Any]]
    duration_ms: int


@dataclass
class ResolveNodesOutput:
    episode_uuid: str
    resolved_node_uuids: list[str]
    uuid_map: dict[str, str]
    duplicate_node_uuids: list[str]
    duration_ms: int


@dataclass
class ExtractEdgesOutput:
    episode_uuid: str
    extracted_edge_dicts: list[dict[str, Any]]
    duration_ms: int


@dataclass
class ResolveEdgesOutput:
    episode_uuid: str
    resolved_edge_uuids: list[str]
    invalidated_edge_uuids: list[str]
    hydrated_node_uuids: list[str]
    duration_ms: int


@dataclass
class PersistOutput:
    episode_uuid: str
    node_count: int
    entity_edge_count: int
    episodic_edge_count: int
    merge_operation_count: int
    duration_ms: int


@dataclass
class IngestionResult:
    episode_uuid: str
    group_id: str
    node_count: int
    entity_edge_count: int
    total_duration_ms: int
    stages: dict[str, dict[str, Any]] = field(default_factory=dict)


class IngestionActivities:
    def __init__(self, graphiti_factory, rate_limit_config: RateLimitConfig | None = None):
        self._graphiti_factory = graphiti_factory
        self._graphiti = None
        self._rate_limit = rate_limit_config or RateLimitConfig.from_env()
        logger.info(
            f'IngestionActivities rate limiting: inter_activity_delay={self._rate_limit.inter_activity_delay}s, '
            f'post_llm_delay={self._rate_limit.post_llm_delay}s'
        )

    async def _apply_rate_limit(self, is_llm_activity: bool = False) -> None:
        """Apply rate limiting delay after activity completion."""
        delay = (
            self._rate_limit.post_llm_delay
            if is_llm_activity
            else self._rate_limit.inter_activity_delay
        )
        if delay > 0:
            logger.debug(f'Rate limit: sleeping {delay}s')
            await asyncio.sleep(delay)

    async def _get_graphiti(self):
        if self._graphiti is None:
            self._graphiti = await self._graphiti_factory()
        return self._graphiti

    @activity.defn
    async def extract_nodes(
        self,
        episode_uuid: str,
        group_id: str,
        episode_content: str,
        episode_name: str,
        source: str,
        source_description: str,
        reference_time: str,
        entity_types: dict[str, Any] | None,
        excluded_entity_types: list[str] | None,
        previous_episode_uuids: list[str] | None,
    ) -> ExtractNodesOutput:
        from time import time
        from graphiti_core.nodes import EpisodicNode, EpisodeType
        from graphiti_core.utils.datetime_utils import utc_now, ensure_utc
        from graphiti_core.utils.maintenance.node_operations import extract_nodes
        from datetime import datetime as dt

        start = time()
        graphiti = await self._get_graphiti()

        ref_time = dt.fromisoformat(reference_time) if reference_time else utc_now()
        episode_source = EpisodeType(source) if isinstance(source, str) else source

        episode = EpisodicNode(
            uuid=episode_uuid,
            name=episode_name,
            group_id=group_id,
            labels=[],
            source=episode_source,
            content=episode_content,
            source_description=source_description,
            created_at=utc_now(),
            valid_at=ensure_utc(ref_time),
        )

        if previous_episode_uuids:
            previous_episodes = await EpisodicNode.get_by_uuids(
                graphiti.driver, previous_episode_uuids
            )
        else:
            from graphiti_core.utils.maintenance.graph_data_operations import EPISODE_WINDOW_LEN

            previous_episodes = await graphiti.retrieve_episodes(
                ref_time,
                last_n=EPISODE_WINDOW_LEN,
                group_ids=[group_id],
                source=episode_source,
            )

        if graphiti.use_dspy:
            extracted_nodes = await graphiti._extract_nodes_dspy(
                episode, previous_episodes, entity_types
            )
            extracted_node_dicts = [
                {'name': n.name, 'labels': n.labels, 'uuid': n.uuid, 'group_id': n.group_id}
                for n in extracted_nodes
            ]
        else:
            extracted_node_dicts = await extract_nodes(
                graphiti.clients, episode, previous_episodes, entity_types, excluded_entity_types
            )

        duration_ms = int((time() - start) * 1000)
        logger.info(
            f'Activity extract_nodes completed: {len(extracted_node_dicts)} nodes in {duration_ms}ms'
        )

        # Apply rate limiting after LLM-heavy activity
        await self._apply_rate_limit(is_llm_activity=True)

        return ExtractNodesOutput(
            episode_uuid=episode_uuid,
            extracted_node_dicts=extracted_node_dicts,
            duration_ms=duration_ms,
        )

    @activity.defn
    async def resolve_nodes(
        self,
        episode_uuid: str,
        group_id: str,
        extracted_node_dicts: list[dict[str, Any]],
        episode_content: str,
        episode_name: str,
        source: str,
        source_description: str,
        reference_time: str,
        entity_types: dict[str, Any] | None,
        previous_episode_uuids: list[str] | None,
    ) -> ResolveNodesOutput:
        from time import time
        from graphiti_core.nodes import EpisodicNode, EntityNode, EpisodeType
        from graphiti_core.utils.datetime_utils import utc_now, ensure_utc
        from datetime import datetime as dt

        start = time()
        graphiti = await self._get_graphiti()

        ref_time = dt.fromisoformat(reference_time) if reference_time else utc_now()
        episode_source = EpisodeType(source) if isinstance(source, str) else source

        episode = EpisodicNode(
            uuid=episode_uuid,
            name=episode_name,
            group_id=group_id,
            labels=[],
            source=episode_source,
            content=episode_content,
            source_description=source_description,
            created_at=utc_now(),
            valid_at=ensure_utc(ref_time),
        )

        if previous_episode_uuids:
            previous_episodes = await EpisodicNode.get_by_uuids(
                graphiti.driver, previous_episode_uuids
            )
        else:
            from graphiti_core.utils.maintenance.graph_data_operations import EPISODE_WINDOW_LEN

            previous_episodes = await graphiti.retrieve_episodes(
                ref_time,
                last_n=EPISODE_WINDOW_LEN,
                group_ids=[group_id],
                source=episode_source,
            )

        now = utc_now()
        extracted_nodes = [
            EntityNode(
                uuid=d.get('uuid', ''),
                name=d['name'],
                group_id=d.get('group_id', group_id),
                labels=d.get('labels', ['Entity']),
                created_at=now,
                summary=d.get('summary', ''),
            )
            for d in extracted_node_dicts
        ]

        if graphiti.use_dspy:
            nodes, uuid_map, dspy_duplicates = await graphiti._resolve_nodes_dspy(
                extracted_nodes, episode, previous_episodes
            )
            duplicate_uuids = [n.uuid for n in dspy_duplicates]
        else:
            from graphiti_core.utils.maintenance.node_operations import resolve_extracted_nodes

            nodes, uuid_map, legacy_duplicates = await resolve_extracted_nodes(
                graphiti.clients,
                extracted_nodes,
                episode,
                previous_episodes,
                entity_types,
                existing_nodes_override=None,
                enable_cross_graph_deduplication=graphiti.enable_cross_graph_deduplication,
            )
            duplicate_uuids = [dup[0].uuid for dup in legacy_duplicates]

        duration_ms = int((time() - start) * 1000)
        logger.info(f'Activity resolve_nodes completed: {len(nodes)} nodes in {duration_ms}ms')

        await self._apply_rate_limit(is_llm_activity=True)

        return ResolveNodesOutput(
            episode_uuid=episode_uuid,
            resolved_node_uuids=[n.uuid for n in nodes],
            uuid_map=uuid_map,
            duplicate_node_uuids=duplicate_uuids,
            duration_ms=duration_ms,
        )

    @activity.defn
    async def extract_edges(
        self,
        episode_uuid: str,
        group_id: str,
        extracted_node_dicts: list[dict[str, Any]],
        episode_content: str,
        episode_name: str,
        source: str,
        source_description: str,
        reference_time: str,
        edge_types: dict[str, Any] | None,
        edge_type_map: dict[str, list[str]] | None,
        previous_episode_uuids: list[str] | None,
    ) -> ExtractEdgesOutput:
        from time import time
        from graphiti_core.nodes import EpisodicNode, EpisodeType
        from graphiti_core.utils.datetime_utils import utc_now, ensure_utc
        from graphiti_core.utils.maintenance.edge_operations import extract_edges
        from datetime import datetime as dt

        start = time()
        graphiti = await self._get_graphiti()

        ref_time = dt.fromisoformat(reference_time) if reference_time else utc_now()
        episode_source = EpisodeType(source) if isinstance(source, str) else source

        episode = EpisodicNode(
            uuid=episode_uuid,
            name=episode_name,
            group_id=group_id,
            labels=[],
            source=episode_source,
            content=episode_content,
            source_description=source_description,
            created_at=utc_now(),
            valid_at=ensure_utc(ref_time),
        )

        if previous_episode_uuids:
            previous_episodes = await EpisodicNode.get_by_uuids(
                graphiti.driver, previous_episode_uuids
            )
        else:
            from graphiti_core.utils.maintenance.graph_data_operations import EPISODE_WINDOW_LEN

            previous_episodes = await graphiti.retrieve_episodes(
                ref_time,
                last_n=EPISODE_WINDOW_LEN,
                group_ids=[group_id],
                source=episode_source,
            )

        edge_type_map_default = (
            {('Entity', 'Entity'): list(edge_types.keys())}
            if edge_types is not None
            else {('Entity', 'Entity'): []}
        )

        if graphiti.use_dspy:
            from graphiti_core.nodes import EntityNode

            entity_nodes = [
                EntityNode(
                    uuid=d.get('uuid', ''),
                    name=d['name'],
                    group_id=group_id,
                    labels=d.get('labels', ['Entity']),
                    created_at=utc_now(),
                    summary='',
                )
                for d in extracted_node_dicts
            ]
            extracted_edges = await graphiti._extract_edges_dspy(
                episode, entity_nodes, previous_episodes, edge_types
            )
            extracted_edge_dicts = [
                {
                    'source_node_uuid': e.source_node_uuid,
                    'target_node_uuid': e.target_node_uuid,
                    'name': e.name,
                    'fact': e.fact,
                    'uuid': e.uuid,
                }
                for e in extracted_edges
            ]
        else:
            extracted_edge_dicts = await extract_edges(
                graphiti.clients,
                episode,
                extracted_node_dicts,
                previous_episodes,
                edge_type_map or edge_type_map_default,
                group_id,
                edge_types,
            )

        duration_ms = int((time() - start) * 1000)
        logger.info(
            f'Activity extract_edges completed: {len(extracted_edge_dicts)} edges in {duration_ms}ms'
        )

        # Apply rate limiting after LLM-heavy activity
        await self._apply_rate_limit(is_llm_activity=True)

        return ExtractEdgesOutput(
            episode_uuid=episode_uuid,
            extracted_edge_dicts=extracted_edge_dicts,
            duration_ms=duration_ms,
        )

    @activity.defn
    async def resolve_edges_and_persist(
        self,
        episode_uuid: str,
        group_id: str,
        extracted_node_dicts: list[dict[str, Any]],
        extracted_edge_dicts: list[dict[str, Any]],
        uuid_map: dict[str, str],
        duplicate_node_uuids: list[str],
        episode_content: str,
        episode_name: str,
        source: str,
        source_description: str,
        reference_time: str,
        edge_types: dict[str, Any] | None,
        edge_type_map: dict[str, list[str]] | None,
        previous_episode_uuids: list[str] | None,
        store_raw_content: bool,
    ) -> PersistOutput:
        from time import time
        import os
        from graphiti_core.nodes import EpisodicNode, EntityNode, EpisodeType
        from graphiti_core.edges import EntityEdge
        from graphiti_core.utils.datetime_utils import utc_now, ensure_utc
        from graphiti_core.utils.bulk_utils import resolve_edge_pointers, add_nodes_and_edges_bulk
        from graphiti_core.utils.maintenance.edge_operations import (
            resolve_extracted_edges,
            build_episodic_edges,
            build_duplicate_of_edges,
        )
        from graphiti_core.utils.maintenance.node_operations import extract_attributes_from_nodes
        from graphiti_core.helpers import semaphore_gather
        from datetime import datetime as dt

        start = time()
        graphiti = await self._get_graphiti()

        now = utc_now()
        ref_time = dt.fromisoformat(reference_time) if reference_time else now
        episode_source = EpisodeType(source) if isinstance(source, str) else source

        episode = EpisodicNode(
            uuid=episode_uuid,
            name=episode_name,
            group_id=group_id,
            labels=[],
            source=episode_source,
            content=episode_content if store_raw_content else '',
            source_description=source_description,
            created_at=now,
            valid_at=ensure_utc(ref_time),
        )

        if previous_episode_uuids:
            previous_episodes = await EpisodicNode.get_by_uuids(
                graphiti.driver, previous_episode_uuids
            )
        else:
            from graphiti_core.utils.maintenance.graph_data_operations import EPISODE_WINDOW_LEN

            previous_episodes = await graphiti.retrieve_episodes(
                ref_time,
                last_n=EPISODE_WINDOW_LEN,
                group_ids=[group_id],
                source=episode_source,
            )

        existing_uuids = [v for k, v in uuid_map.items() if k != v]
        existing_summaries: dict[str, str] = {}
        if existing_uuids:
            records, _, _ = await graphiti.driver.execute_query(
                """
                MATCH (n:Entity)
                WHERE n.uuid IN $uuids
                RETURN n.uuid AS uuid, n.summary AS summary
                """,
                uuids=existing_uuids,
            )
            existing_summaries = {r['uuid']: r['summary'] or '' for r in records}

        nodes = [
            EntityNode(
                uuid=d.get('uuid', ''),
                name=d['name'],
                group_id=group_id,
                labels=d.get('labels', ['Entity']),
                created_at=now,
                summary=existing_summaries.get(
                    uuid_map.get(d.get('uuid', ''), ''), d.get('summary', '')
                )
                or '',
            )
            for d in extracted_node_dicts
        ]

        node_duplicates_tuples: list[tuple] = []

        extracted_edges = [
            EntityEdge(
                uuid=d.get('uuid', ''),
                group_id=group_id,
                source_node_uuid=d['source_node_uuid'],
                target_node_uuid=d['target_node_uuid'],
                name=d['name'],
                fact=d.get('fact', ''),
                created_at=now,
            )
            for d in extracted_edge_dicts
        ]

        edges = resolve_edge_pointers(extracted_edges, uuid_map)

        edge_type_map_default = (
            {('Entity', 'Entity'): list(edge_types.keys())}
            if edge_types is not None
            else {('Entity', 'Entity'): []}
        )

        # Use DSPy for attribute extraction (summaries) if enabled
        # This matches the behavior in graphiti.py add_episode_resilient
        if graphiti.use_dspy:
            logger.info(f'Episode {episode.uuid}: Extracting attributes [DSPy]')
            (resolved_edges, invalidated_edges), hydrated_nodes = await semaphore_gather(
                resolve_extracted_edges(
                    graphiti.clients,
                    edges,
                    episode,
                    nodes,
                    edge_types or {},
                    edge_type_map or edge_type_map_default,
                ),
                graphiti._extract_attributes_dspy(nodes, episode, previous_episodes),
            )
        else:
            (resolved_edges, invalidated_edges), hydrated_nodes = await semaphore_gather(
                resolve_extracted_edges(
                    graphiti.clients,
                    edges,
                    episode,
                    nodes,
                    edge_types or {},
                    edge_type_map or edge_type_map_default,
                ),
                extract_attributes_from_nodes(
                    graphiti.clients, nodes, episode, previous_episodes, None
                ),
            )

        nodes_to_use = hydrated_nodes if hydrated_nodes else nodes

        duplicate_of_edges, merge_operations, duplicate_nodes_to_save = build_duplicate_of_edges(
            episode, now, node_duplicates_tuples
        )

        entity_edges = resolved_edges + invalidated_edges + duplicate_of_edges
        episodic_edges = build_episodic_edges(
            nodes_to_use, episode.uuid, now, episode_group_id=episode.group_id
        )
        episode.entity_edges = [edge.uuid for edge in entity_edges]

        all_nodes_to_save = nodes_to_use + duplicate_nodes_to_save

        await add_nodes_and_edges_bulk(
            graphiti.driver,
            [episode],
            episodic_edges,
            all_nodes_to_save,
            entity_edges,
            graphiti.embedder,
        )

        auto_merge_enabled = os.getenv('GRAPHITI_ENABLE_AUTO_MERGE', 'false').lower() == 'true'
        if merge_operations and auto_merge_enabled:
            from graphiti_core.utils.maintenance.edge_operations import execute_merge_operations

            await execute_merge_operations(
                graphiti.driver,
                merge_operations,
                allow_cross_graph_merge=graphiti.enable_cross_graph_deduplication,
            )

        duration_ms = int((time() - start) * 1000)
        logger.info(f'Activity resolve_edges_and_persist completed in {duration_ms}ms')

        return PersistOutput(
            episode_uuid=episode_uuid,
            node_count=len(all_nodes_to_save),
            entity_edge_count=len(entity_edges),
            episodic_edge_count=len(episodic_edges),
            merge_operation_count=len(merge_operations),
            duration_ms=duration_ms,
        )
