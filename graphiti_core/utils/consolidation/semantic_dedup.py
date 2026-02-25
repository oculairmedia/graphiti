from __future__ import annotations

import logging
from dataclasses import dataclass
from time import time
from typing import Any

from temporalio import activity

logger = logging.getLogger(__name__)

DEFAULT_SIMILARITY_THRESHOLD = 0.92
DEFAULT_MAX_CANDIDATES = 10


@dataclass
class SemanticDedupResult:
    merged_count: int
    edges_transferred: int
    nodes_deleted: int
    failed_merges: int
    candidates_found: int
    details: dict[str, Any]
    duration_ms: int


class SemanticDedupActivities:
    def __init__(self, graphiti_factory):
        self._graphiti_factory = graphiti_factory
        self._graphiti = None

    async def _get_graphiti(self):
        if self._graphiti is None:
            self._graphiti = await self._graphiti_factory()
        return self._graphiti

    @activity.defn
    async def semantic_entity_dedup(
        self,
        similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
        max_candidates: int = DEFAULT_MAX_CANDIDATES,
        batch_size: int = 100,
    ) -> SemanticDedupResult:
        """Find and merge semantically similar entities via name_embedding cosine similarity.

        Algorithm:
        1. Iterate through all Entity nodes that have name_embedding, in batches
        2. For each entity, query similar entities using HNSW vector index
        3. Filter by similarity threshold (default 0.92)
        4. Skip already-processed entities (tracked via processed_uuids set)
        5. For each candidate group, select canonical (most edges -> longest summary -> earliest created_at)
        6. Merge duplicates into canonical via merge_node_into()

        Conservative defaults: high threshold (0.92), skip entities already merged in this run.
        """
        start = time()
        graphiti = await self._get_graphiti()
        driver = graphiti.driver

        from graphiti_core.utils.maintenance.node_operations import merge_node_into

        processed_uuids: set[str] = set()
        total_merged = 0
        total_edges_transferred = 0
        total_deleted = 0
        total_failed = 0
        total_candidates = 0

        offset = 0
        while True:
            records, _, _ = await driver.execute_query(
                'MATCH (n:Entity) '
                'WHERE n.name_embedding IS NOT NULL '
                'RETURN n.uuid AS uuid, n.name AS name, n.name_embedding AS embedding '
                'ORDER BY n.uuid '
                'SKIP $offset LIMIT $batch_size',
                offset=offset,
                batch_size=batch_size,
            )

            if not records:
                break

            for record in records:
                entity_uuid = record['uuid']
                entity_name = record['name']
                embedding = record['embedding']

                if entity_uuid in processed_uuids:
                    continue

                if not embedding or not isinstance(embedding, (list, tuple)):
                    continue

                embedding_str = ','.join(str(float(v)) for v in embedding)
                similar_records, _, _ = await driver.execute_query(
                    'MATCH (n:Entity) '
                    'WHERE n.name_embedding IS NOT NULL AND n.uuid <> $entity_uuid '
                    f'WITH n, (2 - vec.cosineDistance(n.name_embedding, vecf32([{embedding_str}]))) / 2 AS score '
                    'WHERE score > $threshold '
                    'OPTIONAL MATCH (n)-[r]-() '
                    'WITH n, score, count(r) AS edge_count '
                    'RETURN n.uuid AS uuid, n.name AS name, score, edge_count, '
                    'CASE WHEN n.summary IS NOT NULL THEN size(n.summary) ELSE 0 END AS summary_len, '
                    'n.created_at AS created_at '
                    'ORDER BY score DESC '
                    'LIMIT $max_candidates',
                    entity_uuid=entity_uuid,
                    threshold=similarity_threshold,
                    max_candidates=max_candidates,
                )

                candidates = [r for r in similar_records if r['uuid'] not in processed_uuids]

                if not candidates:
                    continue

                total_candidates += len(candidates)

                current_stats, _, _ = await driver.execute_query(
                    'MATCH (n:Entity {uuid: $uuid}) '
                    'OPTIONAL MATCH (n)-[r]-() '
                    'WITH n, count(r) AS edge_count '
                    'RETURN edge_count, '
                    'CASE WHEN n.summary IS NOT NULL THEN size(n.summary) ELSE 0 END AS summary_len, '
                    'n.created_at AS created_at',
                    uuid=entity_uuid,
                )

                if not current_stats:
                    continue

                all_candidates = [
                    {
                        'uuid': entity_uuid,
                        'name': entity_name,
                        'edge_count': current_stats[0].get('edge_count', 0) or 0,
                        'summary_len': current_stats[0].get('summary_len', 0) or 0,
                        'created_at': current_stats[0].get('created_at', ''),
                    }
                ]
                for c in candidates:
                    all_candidates.append(
                        {
                            'uuid': c['uuid'],
                            'name': c.get('name', ''),
                            'edge_count': c.get('edge_count', 0) or 0,
                            'summary_len': c.get('summary_len', 0) or 0,
                            'created_at': c.get('created_at', ''),
                        }
                    )

                all_candidates.sort(
                    key=lambda x: (
                        -(x.get('edge_count') or 0),
                        -(x.get('summary_len') or 0),
                        x.get('created_at') or '',
                    )
                )
                canonical_uuid = all_candidates[0]['uuid']
                duplicate_uuids = [c['uuid'] for c in all_candidates[1:]]

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
                        total_deleted += (
                            stats.get('nodes_deleted', 0) if 'nodes_deleted' in stats else 1
                        )
                        processed_uuids.add(dup_uuid)
                        logger.info(
                            'Semantic merge: %s -> %s (score above %.2f), edges=%d',
                            dup_uuid,
                            canonical_uuid,
                            similarity_threshold,
                            stats.get('edges_transferred', 0),
                        )
                    except Exception as e:
                        total_failed += 1
                        logger.error(
                            'Semantic merge failed: %s into %s: %s',
                            dup_uuid,
                            canonical_uuid,
                            e,
                        )

                processed_uuids.add(entity_uuid)

            offset += batch_size

        duration_ms = int((time() - start) * 1000)
        return SemanticDedupResult(
            merged_count=total_merged,
            edges_transferred=total_edges_transferred,
            nodes_deleted=total_deleted,
            failed_merges=total_failed,
            candidates_found=total_candidates,
            details={
                'similarity_threshold': similarity_threshold,
                'max_candidates': max_candidates,
                'batch_size': batch_size,
                'entities_scanned': offset,
            },
            duration_ms=duration_ms,
        )


SemanticDedupActivities.semantic_entity_dedup.__wrapped__ = (
    SemanticDedupActivities.semantic_entity_dedup
)
