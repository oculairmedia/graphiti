"""
Pipeline Comparison Utilities.

Tools for running both DSPy and original Graphiti pipelines in parallel
and comparing their results.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from difflib import SequenceMatcher

from .pipeline import DSPyIngestionPipeline, PipelineResult

logger = logging.getLogger(__name__)


@dataclass
class ComparisonMetrics:
    """Metrics comparing DSPy vs original pipeline results."""
    # Entity metrics
    dspy_entity_count: int = 0
    original_entity_count: int = 0
    entity_overlap_count: int = 0
    entity_match_rate: float = 0.0

    # Edge metrics
    dspy_edge_count: int = 0
    original_edge_count: int = 0
    edge_overlap_count: int = 0
    edge_match_rate: float = 0.0

    # Summary metrics
    summary_similarity: float = 0.0

    # Timing
    dspy_time_ms: float = 0.0
    original_time_ms: float = 0.0
    speedup_ratio: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            'entities': {
                'dspy_count': self.dspy_entity_count,
                'original_count': self.original_entity_count,
                'overlap_count': self.entity_overlap_count,
                'match_rate': round(self.entity_match_rate, 3),
            },
            'edges': {
                'dspy_count': self.dspy_edge_count,
                'original_count': self.original_edge_count,
                'overlap_count': self.edge_overlap_count,
                'match_rate': round(self.edge_match_rate, 3),
            },
            'summaries': {
                'similarity': round(self.summary_similarity, 3),
            },
            'timing': {
                'dspy_ms': round(self.dspy_time_ms, 2),
                'original_ms': round(self.original_time_ms, 2),
                'speedup': round(self.speedup_ratio, 2),
            },
        }


@dataclass
class ComparisonResult:
    """Full comparison result for an episode."""
    episode_id: str
    episode_content: str

    dspy_result: dict[str, Any] = field(default_factory=dict)
    original_result: dict[str, Any] = field(default_factory=dict)
    metrics: ComparisonMetrics = field(default_factory=ComparisonMetrics)

    # Differences
    entities_only_in_dspy: list[str] = field(default_factory=list)
    entities_only_in_original: list[str] = field(default_factory=list)
    edges_only_in_dspy: list[dict] = field(default_factory=list)
    edges_only_in_original: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            'episode_id': self.episode_id,
            'episode_content': self.episode_content[:200] + '...' if len(self.episode_content) > 200 else self.episode_content,
            'metrics': self.metrics.to_dict(),
            'differences': {
                'entities_only_in_dspy': self.entities_only_in_dspy,
                'entities_only_in_original': self.entities_only_in_original,
                'edges_only_in_dspy': self.edges_only_in_dspy,
                'edges_only_in_original': self.edges_only_in_original,
            },
        }


def normalize_entity_name(name: str) -> str:
    """Normalize entity name for comparison."""
    return name.lower().strip()


def normalize_edge(edge: dict) -> tuple:
    """Normalize edge for comparison."""
    return (
        normalize_entity_name(edge.get('source', '')),
        edge.get('relation_type', '').upper(),
        normalize_entity_name(edge.get('target', '')),
    )


def string_similarity(a: str, b: str) -> float:
    """Calculate string similarity using SequenceMatcher."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def find_matching_entity(name: str, entity_list: list[str], threshold: float = 0.8) -> str | None:
    """Find matching entity name in list using fuzzy matching."""
    name_norm = normalize_entity_name(name)
    for entity in entity_list:
        entity_norm = normalize_entity_name(entity)
        if name_norm == entity_norm:
            return entity
        if string_similarity(name_norm, entity_norm) >= threshold:
            return entity
    return None


def compare_entities(
    dspy_entities: list[dict[str, Any]],
    original_entities: list[dict[str, Any]],
) -> tuple[int, list[str], list[str]]:
    """
    Compare entity lists and return overlap count and differences.

    Returns:
        (overlap_count, only_in_dspy, only_in_original)
    """
    dspy_names = [e.get('name', '') for e in dspy_entities]
    original_names = [e.get('name', '') for e in original_entities]

    overlap = 0
    only_in_dspy = []
    matched_original = set()

    for name in dspy_names:
        match = find_matching_entity(name, original_names)
        if match:
            overlap += 1
            matched_original.add(normalize_entity_name(match))
        else:
            only_in_dspy.append(name)

    only_in_original = [
        name for name in original_names
        if normalize_entity_name(name) not in matched_original
    ]

    return overlap, only_in_dspy, only_in_original


def compare_edges(
    dspy_edges: list[dict[str, Any]],
    original_edges: list[dict[str, Any]],
) -> tuple[int, list[dict], list[dict]]:
    """
    Compare edge lists and return overlap count and differences.

    Returns:
        (overlap_count, only_in_dspy, only_in_original)
    """
    dspy_normalized = {normalize_edge(e): e for e in dspy_edges}
    original_normalized = {normalize_edge(e): e for e in original_edges}

    overlap = len(set(dspy_normalized.keys()) & set(original_normalized.keys()))

    only_in_dspy = [
        dspy_normalized[k] for k in dspy_normalized
        if k not in original_normalized
    ]

    only_in_original = [
        original_normalized[k] for k in original_normalized
        if k not in dspy_normalized
    ]

    return overlap, only_in_dspy, only_in_original


def compare_summaries(
    dspy_summaries: dict[str, str],
    original_summaries: dict[str, str],
) -> float:
    """
    Compare summaries and return average similarity.

    Returns:
        Average similarity score (0.0 - 1.0)
    """
    if not dspy_summaries or not original_summaries:
        return 0.0

    similarities = []
    for name, dspy_summary in dspy_summaries.items():
        # Find matching original summary
        for orig_name, orig_summary in original_summaries.items():
            if string_similarity(name, orig_name) >= 0.8:
                sim = string_similarity(dspy_summary, orig_summary)
                similarities.append(sim)
                break

    return sum(similarities) / len(similarities) if similarities else 0.0


class PipelineComparator:
    """
    Compare DSPy pipeline results against original Graphiti pipeline.

    This class can compare results from:
    1. Pre-computed original results (from JSON/dict)
    2. Live comparison with Graphiti instance (if available)
    """

    def __init__(
        self,
        dspy_pipeline: DSPyIngestionPipeline | None = None,
        entity_types: list[dict[str, Any]] | None = None,
    ):
        """
        Initialize comparator.

        Args:
            dspy_pipeline: Optional pre-configured DSPy pipeline.
            entity_types: Entity types for creating new pipeline.
        """
        self.dspy_pipeline = dspy_pipeline or DSPyIngestionPipeline(
            entity_types=entity_types
        )
        self.results: list[ComparisonResult] = []

    def compare_episode(
        self,
        content: str,
        original_result: dict[str, Any],
        episode_id: str | None = None,
    ) -> ComparisonResult:
        """
        Compare DSPy extraction against pre-computed original result.

        Args:
            content: Episode content.
            original_result: Dict with 'entities', 'edges', 'summaries' from original pipeline.
            episode_id: Optional episode identifier.

        Returns:
            ComparisonResult with metrics and differences.
        """
        episode_id = episode_id or f'ep_{len(self.results)}'

        # Run DSPy pipeline
        dspy_result = self.dspy_pipeline.ingest_episode(content, episode_id)

        # Build comparison result
        comparison = ComparisonResult(
            episode_id=episode_id,
            episode_content=content,
            dspy_result=dspy_result.to_dict(),
            original_result=original_result,
        )

        # Compare entities
        dspy_entities = dspy_result.resolved_entities
        original_entities = original_result.get('entities', [])

        entity_overlap, only_dspy, only_orig = compare_entities(
            dspy_entities, original_entities
        )

        comparison.entities_only_in_dspy = only_dspy
        comparison.entities_only_in_original = only_orig
        comparison.metrics.dspy_entity_count = len(dspy_entities)
        comparison.metrics.original_entity_count = len(original_entities)
        comparison.metrics.entity_overlap_count = entity_overlap

        max_entities = max(len(dspy_entities), len(original_entities))
        comparison.metrics.entity_match_rate = entity_overlap / max_entities if max_entities > 0 else 1.0

        # Compare edges
        dspy_edges = dspy_result.extracted_edges
        original_edges = original_result.get('edges', [])

        edge_overlap, edge_only_dspy, edge_only_orig = compare_edges(
            dspy_edges, original_edges
        )

        comparison.edges_only_in_dspy = edge_only_dspy
        comparison.edges_only_in_original = edge_only_orig
        comparison.metrics.dspy_edge_count = len(dspy_edges)
        comparison.metrics.original_edge_count = len(original_edges)
        comparison.metrics.edge_overlap_count = edge_overlap

        max_edges = max(len(dspy_edges), len(original_edges))
        comparison.metrics.edge_match_rate = edge_overlap / max_edges if max_edges > 0 else 1.0

        # Compare summaries
        comparison.metrics.summary_similarity = compare_summaries(
            dspy_result.summaries,
            original_result.get('summaries', {}),
        )

        # Timing
        comparison.metrics.dspy_time_ms = dspy_result.total_time_ms
        comparison.metrics.original_time_ms = original_result.get('time_ms', 0)
        if comparison.metrics.original_time_ms > 0:
            comparison.metrics.speedup_ratio = comparison.metrics.original_time_ms / comparison.metrics.dspy_time_ms

        self.results.append(comparison)
        return comparison

    def compare_episodes(
        self,
        episodes: list[dict[str, Any]],
    ) -> list[ComparisonResult]:
        """
        Compare multiple episodes.

        Args:
            episodes: List of dicts with 'content' and 'original_result'.

        Returns:
            List of ComparisonResult objects.
        """
        results = []
        for i, episode in enumerate(episodes):
            result = self.compare_episode(
                content=episode['content'],
                original_result=episode.get('original_result', {}),
                episode_id=episode.get('id', f'ep_{i}'),
            )
            results.append(result)
        return results

    def get_aggregate_metrics(self) -> dict[str, Any]:
        """Get aggregate metrics across all comparisons."""
        if not self.results:
            return {}

        total = len(self.results)
        return {
            'total_episodes': total,
            'avg_entity_match_rate': sum(r.metrics.entity_match_rate for r in self.results) / total,
            'avg_edge_match_rate': sum(r.metrics.edge_match_rate for r in self.results) / total,
            'avg_summary_similarity': sum(r.metrics.summary_similarity for r in self.results) / total,
            'total_dspy_entities': sum(r.metrics.dspy_entity_count for r in self.results),
            'total_original_entities': sum(r.metrics.original_entity_count for r in self.results),
            'total_dspy_edges': sum(r.metrics.dspy_edge_count for r in self.results),
            'total_original_edges': sum(r.metrics.original_edge_count for r in self.results),
            'avg_dspy_time_ms': sum(r.metrics.dspy_time_ms for r in self.results) / total,
            'avg_original_time_ms': sum(r.metrics.original_time_ms for r in self.results) / total,
        }

    def generate_report(self) -> str:
        """Generate a text report of comparison results."""
        if not self.results:
            return 'No comparison results available.'

        lines = [
            '=' * 60,
            'DSPy vs Original Pipeline Comparison Report',
            '=' * 60,
            '',
        ]

        # Aggregate metrics
        agg = self.get_aggregate_metrics()
        lines.extend([
            'AGGREGATE METRICS',
            '-' * 40,
            f"Total Episodes: {agg['total_episodes']}",
            f"Avg Entity Match Rate: {agg['avg_entity_match_rate']:.1%}",
            f"Avg Edge Match Rate: {agg['avg_edge_match_rate']:.1%}",
            f"Avg Summary Similarity: {agg['avg_summary_similarity']:.1%}",
            '',
            f"Total DSPy Entities: {agg['total_dspy_entities']}",
            f"Total Original Entities: {agg['total_original_entities']}",
            f"Total DSPy Edges: {agg['total_dspy_edges']}",
            f"Total Original Edges: {agg['total_original_edges']}",
            '',
            f"Avg DSPy Time: {agg['avg_dspy_time_ms']:.0f}ms",
            f"Avg Original Time: {agg['avg_original_time_ms']:.0f}ms",
            '',
        ])

        # Per-episode details
        lines.extend([
            'PER-EPISODE DETAILS',
            '-' * 40,
        ])

        for result in self.results:
            lines.extend([
                f"\nEpisode: {result.episode_id}",
                f"  Entities: DSPy={result.metrics.dspy_entity_count}, Orig={result.metrics.original_entity_count}, Match={result.metrics.entity_match_rate:.1%}",
                f"  Edges: DSPy={result.metrics.dspy_edge_count}, Orig={result.metrics.original_edge_count}, Match={result.metrics.edge_match_rate:.1%}",
            ])

            if result.entities_only_in_dspy:
                lines.append(f"  Only in DSPy: {result.entities_only_in_dspy}")
            if result.entities_only_in_original:
                lines.append(f"  Only in Original: {result.entities_only_in_original}")

        lines.append('')
        lines.append('=' * 60)
        return '\n'.join(lines)
