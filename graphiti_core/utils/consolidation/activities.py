from __future__ import annotations

import logging
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from time import time
from typing import Any

from temporalio import activity

from graphiti_core.driver.falkordb_driver import FalkorDriver

logger = logging.getLogger(__name__)

JUNK_NAMES = [
    'medium',
    'high',
    'low',
    'priority',
    'status',
    'component',
    'backlog',
    'todo',
    'testing',
    'milestone',
    'documentation',
    'project',
    'deployment',
    'server',
    'http',
    'none',
    'null',
    'true',
    'false',
    'yes',
    'no',
    'n/a',
    'unknown',
    'other',
]


@dataclass
class GraphMetrics:
    total_nodes: int
    entity_nodes: int
    episodic_nodes: int
    community_nodes: int
    total_edges: int
    mentions_edges: int
    relates_to_edges: int
    orphaned_entities: int
    low_connectivity_entities: int
    invalidated_edges: int
    duplicate_name_groups: int
    duplicate_uuid_count: int
    timestamp: str


@dataclass
class PruneResult:
    deleted_count: int
    category: str
    details: dict[str, Any]
    duration_ms: int


@dataclass
class MergeResult:
    merged_count: int
    edges_transferred: int
    conflicts_resolved: int
    nodes_deleted: int
    failed_merges: int
    category: str
    details: dict[str, Any]
    duration_ms: int


@dataclass
class EnrichResult:
    processed_count: int
    updated_count: int
    category: str  # 'entity_summaries', 'entity_embeddings', 'centrality'
    details: dict[str, Any]
    duration_ms: int


@dataclass
class HealthCheckResult:
    constraint_status: list[dict[str, str]]
    failed_constraints: int
    duplicate_uuids_found: int
    all_healthy: bool
    details: dict[str, Any]
    duration_ms: int



@dataclass
class ConsolidationResult:
    run_id: str
    started_at: str
    completed_at: str
    pre_metrics: dict[str, Any]
    post_metrics: dict[str, Any]
    prune_results: list[dict[str, Any]]
    merge_results: list[dict[str, Any]]
    enrich_results: list[dict[str, Any]]
    total_duration_ms: int
    health_check: dict[str, Any] | None = None


class ConsolidationActivities:
    def __init__(self, graphiti_factory):
        self._graphiti_factory = graphiti_factory
        self._graphiti = None
        self._prompts_driver: FalkorDriver | None = None

    async def _get_graphiti(self):
        if self._graphiti is None:
            self._graphiti = await self._graphiti_factory()
        return self._graphiti

    async def _get_prompts_driver(self) -> FalkorDriver:
        if self._prompts_driver is None:
            falkordb_host = os.getenv('FALKORDB_HOST', 'falkordb')
            falkordb_port = int(os.getenv('FALKORDB_PORT', '6379'))
            self._prompts_driver = FalkorDriver(
                host=falkordb_host,
                port=falkordb_port,
                database='graphiti_prompts',
            )
        return self._prompts_driver

    @activity.defn
    async def collect_metrics(self, group_id: str | None = None) -> GraphMetrics:
        _ = group_id
        graphiti = await self._get_graphiti()
        driver = graphiti.driver

        node_records, _, _ = await driver.execute_query(
            'MATCH (n) RETURN labels(n)[0] as type, count(n) as cnt'
        )
        node_counts: dict[str, int] = {
            str(record.get('type') or ''): int(record.get('cnt') or 0) for record in node_records
        }

        edge_records, _, _ = await driver.execute_query(
            'MATCH ()-[r]->() RETURN type(r) as rel_type, count(r) as cnt'
        )
        edge_counts: dict[str, int] = {
            str(record.get('rel_type') or ''): int(record.get('cnt') or 0)
            for record in edge_records
        }

        orphan_records, _, _ = await driver.execute_query(
            'MATCH (n:Entity) WHERE NOT (n)-[]-() RETURN count(n) as cnt'
        )
        low_conn_records, _, _ = await driver.execute_query(
            'MATCH (n:Entity) OPTIONAL MATCH (n)-[r]-() WITH n, count(r) as rels WHERE rels <= 1 RETURN count(n) as cnt'
        )
        invalidated_records, _, _ = await driver.execute_query(
            'MATCH ()-[r]->() WHERE r.invalid_at IS NOT NULL RETURN count(r) as cnt'
        )
        duplicate_records, _, _ = await driver.execute_query(
            'MATCH (n:Entity) WITH n.name as name, count(*) as cnt WHERE cnt > 1 RETURN count(name) as cnt'
        )
        duplicate_uuid_records, _, _ = await driver.execute_query(
            'MATCH (n) WITH n.uuid AS uuid, count(n) AS cnt WHERE cnt > 1 RETURN count(uuid) as cnt'
        )

        return GraphMetrics(
            total_nodes=sum(node_counts.values()),
            entity_nodes=node_counts.get('Entity', 0),
            episodic_nodes=node_counts.get('Episodic', 0),
            community_nodes=node_counts.get('Community', 0),
            total_edges=sum(edge_counts.values()),
            mentions_edges=edge_counts.get('MENTIONS', 0),
            relates_to_edges=edge_counts.get('RELATES_TO', 0),
            orphaned_entities=int((orphan_records[0] if orphan_records else {}).get('cnt') or 0),
            low_connectivity_entities=int(
                (low_conn_records[0] if low_conn_records else {}).get('cnt') or 0
            ),
            invalidated_edges=int(
                (invalidated_records[0] if invalidated_records else {}).get('cnt') or 0
            ),
            duplicate_name_groups=int(
                (duplicate_records[0] if duplicate_records else {}).get('cnt') or 0
            ),
            duplicate_uuid_count=int(
                (duplicate_uuid_records[0] if duplicate_uuid_records else {}).get('cnt') or 0
            ),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
    @activity.defn
    async def prune_orphaned_nodes(self, batch_size: int = 100) -> PruneResult:
        start = time()
        graphiti = await self._get_graphiti()
        driver = graphiti.driver

        total_deleted = 0
        while True:
            records, _, _ = await driver.execute_query(
                'MATCH (n:Entity) WHERE NOT (n)-[]-() WITH n LIMIT $batch_size DETACH DELETE n RETURN count(n) as deleted',
                batch_size=batch_size,
            )
            deleted = int((records[0] if records else {}).get('deleted') or 0)
            total_deleted += deleted
            if deleted == 0:
                break

        duration_ms = int((time() - start) * 1000)
        return PruneResult(
            deleted_count=total_deleted,
            category='orphaned_nodes',
            details={'batch_size': batch_size},
            duration_ms=duration_ms,
        )

    @activity.defn
    async def prune_junk_entities(self, batch_size: int = 100) -> PruneResult:
        start = time()
        graphiti = await self._get_graphiti()
        driver = graphiti.driver

        total_deleted = 0
        while True:
            records, _, _ = await driver.execute_query(
                'MATCH (n:Entity) WHERE toLower(n.name) IN $junk_names WITH n LIMIT $batch_size OPTIONAL MATCH (n)-[r]-() WITH n, count(r) as edge_count WHERE edge_count <= 2 DETACH DELETE n RETURN count(n) as deleted',
                junk_names=JUNK_NAMES,
                batch_size=batch_size,
            )
            deleted = int((records[0] if records else {}).get('deleted') or 0)
            total_deleted += deleted
            if deleted == 0:
                break

        duration_ms = int((time() - start) * 1000)
        return PruneResult(
            deleted_count=total_deleted,
            category='junk_entities',
            details={'batch_size': batch_size, 'junk_name_count': len(JUNK_NAMES)},
            duration_ms=duration_ms,
        )

    @activity.defn
    async def prune_old_episodic_nodes(
        self, retention_days: int = 90, batch_size: int = 500
    ) -> PruneResult:
        start = time()
        graphiti = await self._get_graphiti()
        driver = graphiti.driver

        cutoff_iso = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()
        total_deleted = 0
        while True:
            records, _, _ = await driver.execute_query(
                'MATCH (e:Episodic) WHERE e.created_at < $cutoff_iso WITH e LIMIT $batch_size OPTIONAL MATCH (e)-[r:MENTIONS]-() DELETE r WITH e DELETE e RETURN count(e) as deleted',
                cutoff_iso=cutoff_iso,
                batch_size=batch_size,
            )
            deleted = int((records[0] if records else {}).get('deleted') or 0)
            total_deleted += deleted
            if deleted == 0:
                break

        duration_ms = int((time() - start) * 1000)
        return PruneResult(
            deleted_count=total_deleted,
            category='old_episodics',
            details={
                'batch_size': batch_size,
                'retention_days': retention_days,
                'cutoff_iso': cutoff_iso,
            },
            duration_ms=duration_ms,
        )

    @activity.defn
    async def prune_invalidated_edges(self, batch_size: int = 200) -> PruneResult:
        start = time()
        graphiti = await self._get_graphiti()
        driver = graphiti.driver

        total_deleted = 0
        while True:
            records, _, _ = await driver.execute_query(
                'MATCH ()-[r:RELATES_TO]->() WHERE r.invalid_at IS NOT NULL WITH r LIMIT $batch_size DELETE r RETURN count(r) as deleted',
                batch_size=batch_size,
            )
            deleted = int((records[0] if records else {}).get('deleted') or 0)
            total_deleted += deleted
            if deleted == 0:
                break

        duration_ms = int((time() - start) * 1000)
        return PruneResult(
            deleted_count=total_deleted,
            category='invalidated_edges',
            details={'batch_size': batch_size},
            duration_ms=duration_ms,
        )

    @activity.defn
    async def merge_duplicate_of_edges(self, batch_size: int = 50) -> MergeResult:
        """Resolve existing IS_DUPLICATE_OF edges by merging duplicate into canonical."""
        start = time()
        graphiti = await self._get_graphiti()
        driver = graphiti.driver

        from graphiti_core.utils.maintenance.node_operations import merge_node_into

        # Find all IS_DUPLICATE_OF edges: source=duplicate, target=canonical
        records, _, _ = await driver.execute_query(
            'MATCH (dup)-[r:IS_DUPLICATE_OF]->(canon) RETURN dup.uuid as dup_uuid, canon.uuid as canon_uuid, dup.name as dup_name, canon.name as canon_name'
        )

        total_merged = 0
        total_edges_transferred = 0
        total_conflicts = 0
        total_deleted = 0
        total_failed = 0

        for record in records:
            dup_uuid = record['dup_uuid']
            canon_uuid = record['canon_uuid']
            dup_name = record.get('dup_name', '')
            canon_name = record.get('canon_name', '')

            try:
                stats = await merge_node_into(
                    driver,
                    canonical_uuid=canon_uuid,
                    duplicate_uuid=dup_uuid,
                    maintain_audit_trail=False,
                    recalculate_centrality=False,
                    delete_duplicate=True,
                    allow_cross_graph_merge=True,
                )
                total_merged += 1
                total_edges_transferred += stats.get('edges_transferred', 0)
                total_conflicts += stats.get('conflicts_resolved', 0)
                total_deleted += stats.get('nodes_deleted', 0) if 'nodes_deleted' in stats else 1
                logger.info(
                    'Merged IS_DUPLICATE_OF: %s (%s) -> %s (%s), edges=%d',
                    dup_uuid,
                    dup_name,
                    canon_uuid,
                    canon_name,
                    stats.get('edges_transferred', 0),
                )
            except Exception as e:
                total_failed += 1
                logger.error('Failed to merge %s into %s: %s', dup_uuid, canon_uuid, e)

        duration_ms = int((time() - start) * 1000)
        return MergeResult(
            merged_count=total_merged,
            edges_transferred=total_edges_transferred,
            conflicts_resolved=total_conflicts,
            nodes_deleted=total_deleted,
            failed_merges=total_failed,
            category='duplicate_of_edges',
            details={'is_duplicate_of_count': len(records)},
            duration_ms=duration_ms,
        )

    @activity.defn
    async def merge_same_name_entities(self, batch_size: int = 50) -> MergeResult:
        """
        Merge entities with identical names (case-insensitive).

        For each group of same-name entities, select the canonical node (most edges,
        then longest summary, then earliest created_at) and merge the rest into it.
        """
        start = time()
        graphiti = await self._get_graphiti()
        driver = graphiti.driver

        from graphiti_core.utils.maintenance.node_operations import merge_node_into

        total_merged = 0
        total_edges_transferred = 0
        total_conflicts = 0
        total_deleted = 0
        total_failed = 0
        groups_processed = 0

        # Find duplicate-name groups in batches via SKIP/LIMIT
        offset = 0
        while True:
            group_records, _, _ = await driver.execute_query(
                'MATCH (n:Entity) '
                'WITH toLower(n.name) AS lname, collect(n.uuid) AS uuids '
                'WHERE size(uuids) > 1 '
                'RETURN lname, uuids '
                'ORDER BY size(uuids) DESC '
                'SKIP $offset LIMIT $batch_size',
                offset=offset,
                batch_size=batch_size,
            )

            if not group_records:
                break

            for group in group_records:
                lname = group.get('lname', '')
                uuids = group.get('uuids', [])

                if len(uuids) < 2:
                    continue

                # Select canonical: most edges, then longest summary, then earliest created_at
                node_records, _, _ = await driver.execute_query(
                    'UNWIND $uuids AS uid '
                    'MATCH (n:Entity {uuid: uid}) '
                    'OPTIONAL MATCH (n)-[r]-() '
                    'WITH n, count(r) AS edge_count '
                    'RETURN n.uuid AS uuid, edge_count, '
                    'CASE WHEN n.summary IS NOT NULL THEN size(n.summary) ELSE 0 END AS summary_len, '
                    'n.created_at AS created_at '
                    'ORDER BY edge_count DESC, summary_len DESC, created_at ASC',
                    uuids=uuids,
                )

                if len(node_records) < 2:
                    continue

                canonical_uuid = node_records[0]['uuid']
                duplicate_uuids = [r['uuid'] for r in node_records[1:]]

                for dup_uuid in duplicate_uuids:
                    try:
                        stats = await merge_node_into(
                            driver,
                            canonical_uuid=canonical_uuid,
                            duplicate_uuid=dup_uuid,
                            maintain_audit_trail=False,
                            recalculate_centrality=False,
                            delete_duplicate=True,
                            allow_cross_graph_merge=True,
                        )
                        total_merged += 1
                        total_edges_transferred += stats.get('edges_transferred', 0)
                        total_conflicts += stats.get('conflicts_resolved', 0)
                        total_deleted += (
                            stats.get('nodes_deleted', 0) if 'nodes_deleted' in stats else 1
                        )
                    except Exception as e:
                        total_failed += 1
                        logger.error(
                            'Failed to merge %s into %s (name=%s): %s',
                            dup_uuid,
                            canonical_uuid,
                            lname,
                            e,
                        )

                groups_processed += 1

            offset += batch_size

        duration_ms = int((time() - start) * 1000)
        return MergeResult(
            merged_count=total_merged,
            edges_transferred=total_edges_transferred,
            conflicts_resolved=total_conflicts,
            nodes_deleted=total_deleted,
            failed_merges=total_failed,
            category='same_name_entities',
            details={'groups_processed': groups_processed, 'batch_size': batch_size},
            duration_ms=duration_ms,
        )

    @activity.defn
    async def regenerate_entity_summaries(self, batch_size: int = 50) -> EnrichResult:
        """Regenerate summaries for entities with missing or empty summaries.

        For each entity, gathers connected RELATES_TO edge facts and uses LLM
        to generate a contextual summary.
        """
        start = time()
        graphiti = await self._get_graphiti()
        driver = graphiti.driver
        llm_client = graphiti.llm_client

        total_processed = 0
        total_updated = 0

        while True:
            records, _, _ = await driver.execute_query(
                'MATCH (n:Entity) '
                "WHERE n.summary IS NULL OR n.summary = '' "
                'WITH n LIMIT $batch_size '
                'OPTIONAL MATCH (n)-[r:RELATES_TO]-() '
                'WITH n, collect(DISTINCT r.fact) AS facts '
                'RETURN n.uuid AS uuid, n.name AS name, n.labels AS labels, facts',
                batch_size=batch_size,
            )

            if not records:
                break

            # Prepare all summary generation tasks
            from graphiti_core.llm_client.config import ModelSize
            import asyncio

            sem = asyncio.Semaphore(5)  # Limit concurrent LLM calls

            async def _generate_summary(record: dict) -> dict:
                uuid = record['uuid']
                name = record['name']
                labels = record.get('labels', [])
                facts = [f for f in (record.get('facts') or []) if f]

                if not facts:
                    return {'uuid': uuid, 'summary': name}

                facts_text = '; '.join(facts[:20])
                prompt = (
                    f'Generate a concise summary (under 200 words) for the entity "{name}" '
                    f'(type: {", ".join(labels) if labels else "unknown"}) based on these known facts:\n\n'
                    f'{facts_text}\n\n'
                    f'Focus on the most important information. Be factual and concise.'
                )

                async with sem:
                    try:
                        response = await llm_client.generate_response(
                            prompt, model_size=ModelSize.small
                        )
                        summary = str(response) if response else name
                        if len(summary) > 2000:
                            summary = summary[:2000]
                    except Exception as e:
                        logger.warning('LLM summary generation failed for %s: %s', name, e)
                        summary = name

                return {'uuid': uuid, 'summary': summary}

            # Parallel LLM calls for all records in batch
            results = await asyncio.gather(
                *[_generate_summary(r) for r in records]
            )
            total_processed += len(records)

            # Batch SET via UNWIND — summaries are plain strings, no vecf32 constraint
            updates = [{'uuid': r['uuid'], 'summary': r['summary']} for r in results]
            if updates:
                await driver.execute_query(
                    'UNWIND $updates AS update '
                    'MATCH (n:Entity {uuid: update.uuid}) '
                    'SET n.summary = update.summary',
                    updates=updates,
                )
                total_updated += len(updates)
                logger.info(
                    'Regenerated %d summaries in parallel + batch UNWIND',
                    len(updates),
                )

        duration_ms = int((time() - start) * 1000)
        return EnrichResult(
            processed_count=total_processed,
            updated_count=total_updated,
            category='entity_summaries',
            details={'batch_size': batch_size},
            duration_ms=duration_ms,
        )

    @activity.defn
    async def backfill_entity_embeddings(self, batch_size: int = 100) -> EnrichResult:
        """Backfill name_embedding for entities that are missing them."""
        start = time()
        graphiti = await self._get_graphiti()
        driver = graphiti.driver
        embedder = graphiti.embedder

        total_processed = 0
        total_updated = 0

        while True:
            records, _, _ = await driver.execute_query(
                'MATCH (n:Entity) WHERE n.name_embedding IS NULL '
                'RETURN n.uuid AS uuid, n.name AS name '
                'LIMIT $batch_size',
                batch_size=batch_size,
            )

            if not records:
                break

            names = [r['name'] for r in records]
            uuids = [r['uuid'] for r in records]
            total_processed += len(records)

            try:
                embeddings = await embedder.create_batch(names)

                # Parallelize SET queries — vecf32 requires inline floats,
                # can't batch via UNWIND params. Use asyncio.gather instead
                # of sequential await to reduce wall time by ~10x.
                import asyncio

                sem = asyncio.Semaphore(10)

                async def _store_embedding(uid: str, emb: list) -> None:
                    async with sem:
                        emb_str = ','.join(str(v) for v in emb)
                        await driver.execute_query(
                            f'MATCH (n:Entity {{uuid: $uuid}}) '
                            f'SET n.name_embedding = vecf32([{emb_str}])',
                            uuid=uid,
                        )

                await asyncio.gather(
                    *[_store_embedding(uid, emb) for uid, emb in zip(uuids, embeddings)]
                )
                total_updated += len(uuids)

                logger.info(
                    'Backfilled %d embeddings in parallel (batch_size=%d)',
                    len(uuids), batch_size,
                )
            except Exception as e:
                logger.error('Embedding backfill batch failed: %s', e)

        duration_ms = int((time() - start) * 1000)
        return EnrichResult(
            processed_count=total_processed,
            updated_count=total_updated,
            category='entity_embeddings',
            details={'batch_size': batch_size},
            duration_ms=duration_ms,
        )

    @activity.defn
    async def recalculate_centrality(self) -> EnrichResult:
        """Recalculate all centrality metrics (PageRank, degree, betweenness, importance)."""
        start = time()
        graphiti = await self._get_graphiti()
        driver = graphiti.driver

        from graphiti_core.utils.maintenance.centrality_operations import calculate_all_centralities

        scores = await calculate_all_centralities(
            driver=driver,
            group_id=None,
            store_results=True,
        )

        duration_ms = int((time() - start) * 1000)
        return EnrichResult(
            processed_count=len(scores),
            updated_count=len(scores),
            category='centrality',
            details={'metrics': ['pagerank', 'degree', 'betweenness', 'importance']},
            duration_ms=duration_ms,
        )

    @activity.defn
    async def rebuild_vector_indexes(self, embedding_dim: int = 2560) -> EnrichResult:
        """Verify and rebuild HNSW vector indexes if missing.

        After bulk deletes/merges, FalkorDB HNSW indexes can become invalid
        or disappear entirely. This activity ensures they always exist.
        CREATE VECTOR INDEX is idempotent — it's a no-op if the index already exists.
        """
        start = time()
        graphiti = await self._get_graphiti()
        driver = graphiti.driver

        from graphiti_core.graph_queries import get_vector_indices

        vector_queries = get_vector_indices(embedding_dim)
        rebuilt_count = 0

        for query in vector_queries:
            try:
                await driver.execute_query(query)
                rebuilt_count += 1
                logger.info('Vector index ensured: %s', query[:80])
            except Exception as e:
                # 'Index already exists' is expected and fine
                err_msg = str(e).lower()
                if 'already exists' in err_msg or 'duplicate' in err_msg:
                    logger.debug('Vector index already exists (ok): %s', query[:80])
                    rebuilt_count += 1
                else:
                    logger.error('Failed to create vector index: %s — %s', query[:80], e)

        duration_ms = int((time() - start) * 1000)
        return EnrichResult(
            processed_count=len(vector_queries),
            updated_count=rebuilt_count,
            category='vector_indexes',
            details={'embedding_dim': embedding_dim, 'indexes_ensured': rebuilt_count},
            duration_ms=duration_ms,
        )

    @activity.defn
    async def check_constraint_health(self) -> HealthCheckResult:
        """Check FalkorDB constraint status and detect duplicate UUID nodes."""
        start = time()
        graphiti = await self._get_graphiti()
        driver = graphiti.driver

        # Query all constraints
        constraint_records, _, _ = await driver.execute_query(
            'CALL db.constraints() YIELD type, label, properties, entitytype, status '
            'RETURN type, label, properties, entitytype, status'
        )
        constraint_status: list[dict[str, str]] = []
        failed_count = 0
        for record in constraint_records:
            status = str(record.get('status') or '')
            entry = {
                'type': str(record.get('type') or ''),
                'label': str(record.get('label') or ''),
                'properties': str(record.get('properties') or ''),
                'entitytype': str(record.get('entitytype') or ''),
                'status': status,
            }
            constraint_status.append(entry)
            if status != 'OPERATIONAL':
                failed_count += 1

        # Check for duplicate UUID nodes
        dup_records, _, _ = await driver.execute_query(
            'MATCH (n) WITH n.uuid AS uuid, count(n) AS cnt '
            'WHERE cnt > 1 RETURN uuid, cnt ORDER BY cnt DESC LIMIT 20'
        )
        duplicate_uuids_found = len(dup_records)
        dup_details: list[dict[str, Any]] = []
        for record in dup_records:
            dup_details.append({
                'uuid': str(record.get('uuid') or ''),
                'count': int(record.get('cnt') or 0),
            })

        all_healthy = failed_count == 0 and duplicate_uuids_found == 0
        duration_ms = int((time() - start) * 1000)

        if not all_healthy:
            logger.warning(
                'Health check FAILED: %d failed constraints, %d duplicate UUIDs',
                failed_count,
                duplicate_uuids_found,
            )
        else:
            logger.info(
                'Health check passed: %d constraints all OPERATIONAL, 0 duplicate UUIDs',
                len(constraint_status),
            )

        return HealthCheckResult(
            constraint_status=constraint_status,
            failed_constraints=failed_count,
            duplicate_uuids_found=duplicate_uuids_found,
            all_healthy=all_healthy,
            details={
                'total_constraints': len(constraint_status),
                'duplicate_uuid_details': dup_details,
            },
            duration_ms=duration_ms,
        )


    @activity.defn
    async def store_consolidation_report(
        self, result: ConsolidationResult | dict[str, Any]
    ) -> None:
        prompts_driver = await self._get_prompts_driver()
        result_data = asdict(result) if isinstance(result, ConsolidationResult) else result

        pre_metrics = result_data.get('pre_metrics', {})
        post_metrics = result_data.get('post_metrics', {})
        prune_results = result_data.get('prune_results', [])
        merge_results = result_data.get('merge_results', [])

        total_pruned = 0
        for prune_result in prune_results:
            if isinstance(prune_result, dict):
                total_pruned += int(prune_result.get('deleted_count', 0) or 0)

        total_merged = 0
        total_edges_transferred = 0
        for merge_result in merge_results:
            if isinstance(merge_result, dict):
                total_merged += int(merge_result.get('merged_count', 0) or 0)
                total_edges_transferred += int(merge_result.get('edges_transferred', 0) or 0)

        enrich_results = result_data.get('enrich_results', [])
        total_enriched = 0
        for enrich_result in enrich_results:
            if isinstance(enrich_result, dict):
                total_enriched += int(enrich_result.get('updated_count', 0) or 0)

        health_check = result_data.get('health_check') or {}
        failed_constraints = int(health_check.get('failed_constraints', 0) or 0)
        duplicate_uuids_found = int(health_check.get('duplicate_uuids_found', 0) or 0)
        health_all_healthy = bool(health_check.get('all_healthy', True))

        # Aggregate per-phase durations from individual activity results
        prune_duration_ms = sum(
            int(r.get('duration_ms', 0) or 0)
            for r in prune_results if isinstance(r, dict)
        )
        merge_duration_ms = sum(
            int(r.get('duration_ms', 0) or 0)
            for r in merge_results if isinstance(r, dict)
        )
        enrich_duration_ms = sum(
            int(r.get('duration_ms', 0) or 0)
            for r in enrich_results if isinstance(r, dict)
        )
        health_duration_ms = int(health_check.get('duration_ms', 0) or 0)

        await prompts_driver.execute_query(
            'CREATE (r:ConsolidationReport { '
            'run_id: $run_id, started_at: $started_at, completed_at: $completed_at, '
            'pre_entity_nodes: $pre_entity_nodes, post_entity_nodes: $post_entity_nodes, '
            'pre_total_edges: $pre_total_edges, post_total_edges: $post_total_edges, '
            'total_pruned: $total_pruned, total_merged: $total_merged, total_enriched: $total_enriched, '
            'total_edges_transferred: $total_edges_transferred, '
            'failed_constraints: $failed_constraints, duplicate_uuids_found: $duplicate_uuids_found, '
            'health_all_healthy: $health_all_healthy, '
            'prune_duration_ms: $prune_duration_ms, '
            'merge_duration_ms: $merge_duration_ms, '
            'enrich_duration_ms: $enrich_duration_ms, '
            'health_duration_ms: $health_duration_ms, '
            'total_duration_ms: $total_duration_ms })',
            run_id=str(result_data.get('run_id', '')),
            started_at=str(result_data.get('started_at', '')),
            completed_at=str(result_data.get('completed_at', '')),
            pre_entity_nodes=int(pre_metrics.get('entity_nodes', 0) or 0),
            post_entity_nodes=int(post_metrics.get('entity_nodes', 0) or 0),
            pre_total_edges=int(pre_metrics.get('total_edges', 0) or 0),
            post_total_edges=int(post_metrics.get('total_edges', 0) or 0),
            total_pruned=total_pruned,
            total_merged=total_merged,
            total_enriched=total_enriched,
            total_edges_transferred=total_edges_transferred,
            failed_constraints=failed_constraints,
            duplicate_uuids_found=duplicate_uuids_found,
            health_all_healthy=health_all_healthy,
            prune_duration_ms=prune_duration_ms,
            merge_duration_ms=merge_duration_ms,
            enrich_duration_ms=enrich_duration_ms,
            health_duration_ms=health_duration_ms,
            total_duration_ms=int(result_data.get('total_duration_ms', 0) or 0),
        )
