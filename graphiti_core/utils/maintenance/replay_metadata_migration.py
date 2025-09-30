"""Replay metadata migration helpers.

This module provides utilities for introducing the ReplayMetadata schema into the
graph store. It creates the supporting indexes, backfills ReplayMetadata nodes for
existing episodes, and initializes episodic enrichment counters so replay heuristics
have lightweight access patterns. A corresponding rollback helper removes the nodes
and clears the new properties if a deploy needs to be reverted.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List

from graphiti_core.driver.driver import GraphDriver

logger = logging.getLogger(__name__)


NEO4J_INDEX_QUERIES: List[str] = [
    'CREATE INDEX replay_metadata_episode_uuid IF NOT EXISTS FOR (rm:ReplayMetadata) ON (rm.episode_uuid)',
    'CREATE INDEX replay_metadata_group_id IF NOT EXISTS FOR (rm:ReplayMetadata) ON (rm.group_id)',
]

FALKOR_INDEX_QUERIES: List[str] = [
    'CREATE INDEX FOR (rm:ReplayMetadata) ON (rm.episode_uuid)',
    'CREATE INDEX FOR (rm:ReplayMetadata) ON (rm.group_id)',
]

NEO4J_DROP_INDEX_QUERIES: List[str] = [
    'DROP INDEX replay_metadata_episode_uuid IF EXISTS',
    'DROP INDEX replay_metadata_group_id IF EXISTS',
]

FALKOR_DROP_INDEX_QUERIES: List[str] = [
    # FalkorDB does not currently expose IF EXISTS semantics; attempting to drop an
    # index that is missing raises an error. We guard the call and log the outcome.
    'DROP INDEX FOR (rm:ReplayMetadata) ON (rm.episode_uuid)',
    'DROP INDEX FOR (rm:ReplayMetadata) ON (rm.group_id)',
]


@dataclass(slots=True)
class ReplayMetadataMigrationStats:
    """Structured response summarising migration side-effects."""

    created_metadata_nodes: int = 0
    hydrated_episode_counts: int = 0
    index_operations: int = 0

    def as_dict(self) -> Dict[str, int]:
        return {
            'created_metadata_nodes': self.created_metadata_nodes,
            'hydrated_episode_counts': self.hydrated_episode_counts,
            'index_operations': self.index_operations,
        }


def _extract_records(result: Any) -> List[Dict[str, Any]]:
    """Normalise the driver response into a list of dictionaries."""

    if result is None:
        return []

    if isinstance(result, tuple):
        records = result[0]
    else:
        records = getattr(result, 'records', result)

    if records is None:
        return []

    # For Neo4j, records are neo4j.Record objects; treat them like mappings.
    return [dict(record) for record in records]


async def ensure_replay_metadata_indices(driver: GraphDriver) -> int:
    """Create ReplayMetadata indexes appropriate for the current backend."""

    if driver.provider == 'falkordb':
        queries = FALKOR_INDEX_QUERIES
    else:
        queries = NEO4J_INDEX_QUERIES

    executed = 0
    for query in queries:
        try:
            await driver.execute_query(query)
            executed += 1
        except Exception as exc:  # pragma: no cover - defensive logging only
            logger.info('Skipping index query %s: %s', query, exc)
    return executed


async def _create_replay_metadata_nodes(driver: GraphDriver, batch_size: int) -> int:
    """Create ReplayMetadata nodes for episodic records that lack them."""

    total_created = 0
    query = """
    MATCH (e:Episodic)
    OPTIONAL MATCH (existing:ReplayMetadata {episode_uuid: e.uuid})
    WITH e, existing
    WHERE existing IS NULL
    WITH e LIMIT $batch_size
    MERGE (rm:ReplayMetadata {episode_uuid: e.uuid})
    ON CREATE SET
        rm.group_id = e.group_id,
        rm.replay_attempts = 0,
        rm.last_replayed_at = NULL,
        rm.replay_reason = NULL,
        rm.extraction_version = e.extraction_version,
        rm.confidence_score = e.confidence_score,
        rm.created_at = $now,
        rm.updated_at = $now
    RETURN count(rm) AS created
    """

    while True:
        now = datetime.now(timezone.utc)
        result = await driver.execute_query(query, batch_size=batch_size, now=now)
        records = _extract_records(result)
        created = records[0]['created'] if records else 0
        if created == 0:
            break
        total_created += int(created)

    return total_created


async def _hydrate_episode_counters(driver: GraphDriver, batch_size: int) -> int:
    """Populate new episodic enrichment counters for legacy records."""

    total_updated = 0
    query = """
    MATCH (e:Episodic)
    WHERE e.entity_count IS NULL OR e.edge_count IS NULL OR e.cross_group_connections IS NULL
    WITH e LIMIT $batch_size
    WITH e, size(coalesce(e.entity_edges, [])) AS derived_edge_count
    SET e.entity_count = coalesce(e.entity_count, derived_edge_count),
        e.edge_count = coalesce(e.edge_count, derived_edge_count),
        e.cross_group_connections = coalesce(e.cross_group_connections, 0)
    RETURN count(e) AS updated
    """

    while True:
        result = await driver.execute_query(query, batch_size=batch_size)
        records = _extract_records(result)
        updated = records[0]['updated'] if records else 0
        if updated == 0:
            break
        total_updated += int(updated)

    return total_updated


async def apply_replay_metadata_migration(
    driver: GraphDriver,
    *,
    batch_size: int = 500,
) -> ReplayMetadataMigrationStats:
    """Run the forward migration for ReplayMetadata support."""

    stats = ReplayMetadataMigrationStats()
    stats.index_operations = await ensure_replay_metadata_indices(driver)
    stats.created_metadata_nodes = await _create_replay_metadata_nodes(driver, batch_size)
    stats.hydrated_episode_counts = await _hydrate_episode_counters(driver, batch_size)

    logger.info(
        'Replay metadata migration completed: %s metadata nodes created, %s episodes hydrated',
        stats.created_metadata_nodes,
        stats.hydrated_episode_counts,
    )
    return stats


async def rollback_replay_metadata_migration(
    driver: GraphDriver,
    *,
    batch_size: int = 500,
) -> ReplayMetadataMigrationStats:
    """Rollback helper that removes ReplayMetadata nodes and clears episodic counters."""

    stats = ReplayMetadataMigrationStats()

    if driver.provider == 'falkordb':
        drop_queries = FALKOR_DROP_INDEX_QUERIES
    else:
        drop_queries = NEO4J_DROP_INDEX_QUERIES

    for query in drop_queries:
        try:
            await driver.execute_query(query)
            stats.index_operations += 1
        except Exception as exc:  # pragma: no cover - best-effort cleanup
            logger.info('Skipping index drop %s: %s', query, exc)

    delete_query = """
    MATCH (rm:ReplayMetadata)
    WITH rm LIMIT $batch_size
    DETACH DELETE rm
    RETURN count(rm) AS deleted
    """

    while True:
        result = await driver.execute_query(delete_query, batch_size=batch_size)
        records = _extract_records(result)
        deleted = records[0]['deleted'] if records else 0
        if deleted == 0:
            break
        stats.created_metadata_nodes += int(deleted)

    clear_query = """
    MATCH (e:Episodic)
    WHERE e.entity_count IS NOT NULL OR e.edge_count IS NOT NULL OR e.cross_group_connections IS NOT NULL
          OR e.extraction_version IS NOT NULL OR e.confidence_score IS NOT NULL
    WITH e LIMIT $batch_size
    REMOVE e.entity_count, e.edge_count, e.cross_group_connections, e.extraction_version, e.confidence_score
    RETURN count(e) AS cleared
    """

    while True:
        result = await driver.execute_query(clear_query, batch_size=batch_size)
        records = _extract_records(result)
        cleared = records[0]['cleared'] if records else 0
        if cleared == 0:
            break
        stats.hydrated_episode_counts += int(cleared)

    logger.info(
        'Replay metadata rollback completed: %s metadata nodes deleted, %s episodes cleared',
        stats.created_metadata_nodes,
        stats.hydrated_episode_counts,
    )
    return stats
