from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import timedelta
from typing import Any

import importlib

workflow = importlib.import_module('temporalio.workflow')
common = importlib.import_module('temporalio.common')

with workflow.unsafe.imports_passed_through():
    from graphiti_core.utils.consolidation.activities import (
        ConsolidationResult,
        EnrichResult,
        GraphMetrics,
        MergeResult,
        PruneResult,
    )
    from graphiti_core.utils.consolidation.config import ConsolidationConfig
    from graphiti_core.utils.consolidation.semantic_dedup import SemanticDedupResult

_CONSOLIDATION_CONFIG = ConsolidationConfig.from_env()


@dataclass
class ConsolidationInput:
    group_id: str | None = None
    retention_days: int = 90
    batch_size: int = 100
    merge_batch_size: int = 50
    run_id: str = ''


@workflow.defn(name='GraphConsolidationWorkflow')
class GraphConsolidationWorkflow:
    @workflow.run
    async def run(self, input: ConsolidationInput) -> ConsolidationResult:
        start_ns = workflow.time_ns()
        run_id = input.run_id if input.run_id else str(workflow.uuid4())
        started_at = workflow.now().isoformat()

        retry_policy = common.RetryPolicy(
            initial_interval=timedelta(seconds=5),
            backoff_coefficient=2.0,
            maximum_attempts=3,
        )

        pre_metrics_data: dict[str, Any] = await workflow.execute_activity(
            'collect_metrics',
            args=[input.group_id],
            start_to_close_timeout=timedelta(minutes=5),
            task_queue=_CONSOLIDATION_CONFIG.task_queue,
            retry_policy=retry_policy,
        )

        prune_results: list[dict[str, Any]] = []

        orphaned_result: dict[str, Any] = await workflow.execute_activity(
            'prune_orphaned_nodes',
            args=[input.batch_size],
            start_to_close_timeout=timedelta(minutes=30),
            task_queue=_CONSOLIDATION_CONFIG.task_queue,
            retry_policy=retry_policy,
        )
        prune_results.append(orphaned_result)

        junk_result: dict[str, Any] = await workflow.execute_activity(
            'prune_junk_entities',
            args=[input.batch_size],
            start_to_close_timeout=timedelta(minutes=30),
            task_queue=_CONSOLIDATION_CONFIG.task_queue,
            retry_policy=retry_policy,
        )
        prune_results.append(junk_result)

        old_episodic_result: dict[str, Any] = await workflow.execute_activity(
            'prune_old_episodic_nodes',
            args=[input.retention_days, input.batch_size],
            start_to_close_timeout=timedelta(minutes=30),
            task_queue=_CONSOLIDATION_CONFIG.task_queue,
            retry_policy=retry_policy,
        )
        prune_results.append(old_episodic_result)

        invalidated_result: dict[str, Any] = await workflow.execute_activity(
            'prune_invalidated_edges',
            args=[input.batch_size],
            start_to_close_timeout=timedelta(minutes=30),
            task_queue=_CONSOLIDATION_CONFIG.task_queue,
            retry_policy=retry_policy,
        )
        prune_results.append(invalidated_result)

        # === PHASE 2: MERGE ===

        merge_results: list[dict[str, Any]] = []

        dup_of_result: dict[str, Any] = await workflow.execute_activity(
            'merge_duplicate_of_edges',
            args=[input.merge_batch_size],
            start_to_close_timeout=timedelta(minutes=60),
            task_queue=_CONSOLIDATION_CONFIG.task_queue,
            retry_policy=retry_policy,
        )
        merge_results.append(dup_of_result)

        same_name_result: dict[str, Any] = await workflow.execute_activity(
            'merge_same_name_entities',
            args=[input.merge_batch_size],
            start_to_close_timeout=timedelta(hours=2),
            task_queue=_CONSOLIDATION_CONFIG.task_queue,
            retry_policy=retry_policy,
        )
        merge_results.append(same_name_result)

        # Post-merge prune: merging can create new orphans
        post_merge_orphan_result: dict[str, Any] = await workflow.execute_activity(
            'prune_orphaned_nodes',
            args=[input.batch_size],
            start_to_close_timeout=timedelta(minutes=30),
            task_queue=_CONSOLIDATION_CONFIG.task_queue,
            retry_policy=retry_policy,
        )
        prune_results.append(post_merge_orphan_result)

        enrich_results: list[dict[str, Any]] = []

        summary_result: dict[str, Any] = await workflow.execute_activity(
            'regenerate_entity_summaries',
            args=[input.batch_size],
            start_to_close_timeout=timedelta(hours=1),
            task_queue=_CONSOLIDATION_CONFIG.task_queue,
            retry_policy=retry_policy,
        )
        enrich_results.append(summary_result)

        embedding_result: dict[str, Any] = await workflow.execute_activity(
            'backfill_entity_embeddings',
            args=[input.batch_size],
            start_to_close_timeout=timedelta(minutes=30),
            task_queue=_CONSOLIDATION_CONFIG.task_queue,
            retry_policy=retry_policy,
        )
        enrich_results.append(embedding_result)

        semantic_dedup_result: dict[str, Any] = await workflow.execute_activity(
            'semantic_entity_dedup',
            args=[],
            start_to_close_timeout=timedelta(hours=2),
            task_queue=_CONSOLIDATION_CONFIG.task_queue,
            retry_policy=retry_policy,
        )
        enrich_results.append(semantic_dedup_result)

        # Post-semantic-dedup prune: semantic merges can create new orphans
        post_dedup_orphan_result: dict[str, Any] = await workflow.execute_activity(
            'prune_orphaned_nodes',
            args=[input.batch_size],
            start_to_close_timeout=timedelta(minutes=30),
            task_queue=_CONSOLIDATION_CONFIG.task_queue,
            retry_policy=retry_policy,
        )
        prune_results.append(post_dedup_orphan_result)

        centrality_result: dict[str, Any] = await workflow.execute_activity(
            'recalculate_centrality',
            args=[],
            start_to_close_timeout=timedelta(hours=1),
            task_queue=_CONSOLIDATION_CONFIG.task_queue,
            retry_policy=retry_policy,
        )
        enrich_results.append(centrality_result)

        # Ensure HNSW vector indexes are intact after all deletes/merges
        rebuild_indexes_result: dict[str, Any] = await workflow.execute_activity(
            'rebuild_vector_indexes',
            args=[],
            start_to_close_timeout=timedelta(minutes=30),
            task_queue=_CONSOLIDATION_CONFIG.task_queue,
            retry_policy=retry_policy,
        )
        enrich_results.append(rebuild_indexes_result)

        # === COLLECT POST-METRICS ===

        post_metrics_data: dict[str, Any] = await workflow.execute_activity(
            'collect_metrics',
            args=[input.group_id],
            start_to_close_timeout=timedelta(minutes=5),
            task_queue=_CONSOLIDATION_CONFIG.task_queue,
            retry_policy=retry_policy,
        )

        total_duration_ms = (workflow.time_ns() - start_ns) // 1_000_000
        result = ConsolidationResult(
            run_id=run_id,
            started_at=started_at,
            completed_at=workflow.now().isoformat(),
            pre_metrics=pre_metrics_data,
            post_metrics=post_metrics_data,
            prune_results=prune_results,
            merge_results=merge_results,
            enrich_results=enrich_results,
            total_duration_ms=total_duration_ms,
        )

        await workflow.execute_activity(
            'store_consolidation_report',
            args=[asdict(result)],
            start_to_close_timeout=timedelta(minutes=5),
            task_queue=_CONSOLIDATION_CONFIG.task_queue,
            retry_policy=retry_policy,
        )

        return result
