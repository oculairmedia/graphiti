"""
Prompt compression utilities (DEPRECATED - now using reranker-based context gating).

This module is kept for backwards compatibility but returns no-op compressors.
The actual context management is now handled by:
- graphiti_core.utils.prompt_utils.rerank_and_budget_episodes() for semantic selection
- graphiti_core.utils.prompt_utils.enforce_max_prompt_tokens() for token clipping
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from graphiti_core.nodes import EntityNode

logger = logging.getLogger(__name__)


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
    No-op compressor for backwards compatibility.

    DEPRECATED: Use rerank_and_budget_episodes() and enforce_max_prompt_tokens() instead.
    """

    def __init__(self) -> None:
        logger.info(
            'GraphitiPromptCompressor is deprecated. '
            'Using reranker-based context gating instead.'
        )

    def compress_existing_entities(
        self, existing_nodes: list[EntityNode], target_tokens: int = 3000
    ) -> tuple[str, CompressionStats]:
        """
        No-op compression for existing entities - returns JSON formatted text.

        Returns:
            (nodes_text, stats)
        """
        import json

        # Format nodes as JSON text (no compression)
        nodes_text = json.dumps(
            [
                {'name': node.name, 'summary': node.summary, 'labels': node.labels}
                for node in existing_nodes
            ],
            ensure_ascii=False,
        )

        stats = CompressionStats(
            original_tokens=len(nodes_text) // 4,
            compressed_tokens=len(nodes_text) // 4,
            compression_ratio=1.0,
            compression_time_ms=0.0,
            entities_count=len(existing_nodes),
            target_tokens=target_tokens,
            error=None,
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
