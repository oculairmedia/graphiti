"""
Prompt compression utilities for managing token budgets.

This module provides token-efficient compression for entity nodes,
especially important for rate-limited providers like Z.AI.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from graphiti_core.nodes import EntityNode

logger = logging.getLogger(__name__)

# Configuration for aggressive compression (useful for slow/rate-limited providers like Z.AI)
COMPRESS_NODE_SUMMARIES = os.getenv('COMPRESS_NODE_SUMMARIES', 'true').lower() == 'true'
MAX_SUMMARY_CHARS = int(os.getenv('MAX_SUMMARY_CHARS', '100'))  # Truncate summaries to this length
EXCLUDE_NODE_LABELS = os.getenv('EXCLUDE_NODE_LABELS', 'false').lower() == 'true'


@dataclass
class CompressionStats:
    """Simple container with compression statistics (deprecated)."""

    original_tokens: int
    compressed_tokens: int
    compression_ratio: float
    compression_time_ms: float
    entities_count: int
    target_tokens: int
    error: Optional[str] = None


class GraphitiPromptCompressor:
    """
    Token-efficient compressor for entity nodes in prompts.

    Configurable via environment variables:
    - COMPRESS_NODE_SUMMARIES: Whether to truncate summaries (default: true)
    - MAX_SUMMARY_CHARS: Max chars per summary (default: 100)
    - EXCLUDE_NODE_LABELS: Whether to exclude labels from output (default: false)
    """

    def __init__(self) -> None:
        logger.debug(
            f'GraphitiPromptCompressor initialized: '
            f'compress_summaries={COMPRESS_NODE_SUMMARIES}, '
            f'max_summary={MAX_SUMMARY_CHARS}, '
            f'exclude_labels={EXCLUDE_NODE_LABELS}'
        )

    def compress_existing_entities(
        self, existing_nodes: list[EntityNode], target_tokens: int = 3000
    ) -> tuple[str, CompressionStats]:
        """
        Compress existing entities for prompt inclusion.

        Applies token-efficient compression:
        - Truncates summaries to MAX_SUMMARY_CHARS
        - Optionally excludes labels
        - Uses compact JSON formatting

        Returns:
            (nodes_text, stats)
        """
        import json
        import time

        start_time = time.time()

        # Build compressed node representations
        compressed_nodes = []
        for i, node in enumerate(existing_nodes):
            node_data: dict[str, str | list[str]] = {
                'idx': str(i),  # Use idx for dedup reference
                'name': node.name,
            }

            # Compress or truncate summary
            if node.summary:
                if COMPRESS_NODE_SUMMARIES and len(node.summary) > MAX_SUMMARY_CHARS:
                    node_data['summary'] = node.summary[:MAX_SUMMARY_CHARS] + '...'
                else:
                    node_data['summary'] = node.summary

            # Optionally include labels
            if not EXCLUDE_NODE_LABELS and node.labels:
                node_data['labels'] = node.labels

            compressed_nodes.append(node_data)

        # Format with candidate idx prefix for dedup prompt clarity
        formatted_nodes = []
        for node_data in compressed_nodes:
            formatted_nodes.append(f"Candidate idx={node_data['idx']}: {json.dumps(node_data, ensure_ascii=False)}")

        nodes_text = '\n'.join(formatted_nodes)

        # Calculate compression stats
        original_text = json.dumps(
            [{'name': n.name, 'summary': n.summary, 'labels': n.labels} for n in existing_nodes],
            ensure_ascii=False,
        )
        original_tokens = len(original_text) // 4
        compressed_tokens = len(nodes_text) // 4
        compression_ratio = compressed_tokens / original_tokens if original_tokens > 0 else 1.0
        compression_time_ms = (time.time() - start_time) * 1000

        stats = CompressionStats(
            original_tokens=original_tokens,
            compressed_tokens=compressed_tokens,
            compression_ratio=compression_ratio,
            compression_time_ms=compression_time_ms,
            entities_count=len(existing_nodes),
            target_tokens=target_tokens,
            error=None,
        )

        if compression_ratio < 0.9:
            logger.info(
                f'Node compression: {original_tokens} → {compressed_tokens} tokens '
                f'({compression_ratio:.1%} of original, {len(existing_nodes)} nodes)'
            )

        return nodes_text, stats

    def compress_deduplication_context(
        self,
        chunk_nodes: list[EntityNode],
        existing_nodes_text: str,
        target_tokens: int = 3000,
    ) -> tuple[list[int], str, CompressionStats]:
        """
        No-op compression - returns original content.

        Returns:
            (preserved_indexes, compressed_text, stats)
        """
        # Return all node indexes as preserved (no compression)
        preserved_indexes = list(range(len(chunk_nodes)))

        stats = CompressionStats(
            original_tokens=len(existing_nodes_text) // 4,
            compressed_tokens=len(existing_nodes_text) // 4,
            compression_ratio=1.0,
            compression_time_ms=0.0,
            entities_count=len(chunk_nodes),
            target_tokens=target_tokens,
            error=None,
        )

        return preserved_indexes, existing_nodes_text, stats


def get_prompt_compressor() -> GraphitiPromptCompressor:
    """
    Returns a no-op compressor instance.

    DEPRECATED: Use rerank_and_budget_episodes() and enforce_max_prompt_tokens() instead.
    """
    return GraphitiPromptCompressor()
