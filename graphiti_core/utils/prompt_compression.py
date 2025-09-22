"""Prompt compression utilities for deduplication prompts."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple, Union, TYPE_CHECKING

try:  # pragma: no cover - optional dependency
    from llmlingua import PromptCompressor
except ImportError:  # pragma: no cover - graceful fallback when package missing
    PromptCompressor = None  # type: ignore

try:  # pragma: no cover - optional dependency
    import tiktoken
except ImportError:  # pragma: no cover
    tiktoken = None  # type: ignore

if TYPE_CHECKING:  # pragma: no cover - typing only
    from graphiti_core.nodes import EntityNode


logger = logging.getLogger(__name__)

_DEFAULT_MODEL_NAME = "microsoft/llmlingua-2-xlm-roberta-large-meetingbank"
_DEFAULT_TARGET_TOKENS = 3000
_DEFAULT_COMPRESSION_RATIO = 0.6
_DEFAULT_BATCH_TARGET_TOKENS = 4000
_DEFAULT_BATCH_RATIO = 0.5


@dataclass
class CompressionStats:
    """Simple container with compression statistics."""

    original_tokens: int
    compressed_tokens: int
    compression_ratio: float
    compression_time_ms: float
    entities_count: int
    target_tokens: int
    error: Optional[str] = None


class GraphitiPromptCompressor:
    """Compresses prompt context while preserving duplicate indexes."""

    def __init__(self) -> None:
        self._compressor: Optional[PromptCompressor] = None
        self._tokenizer = None
        self._initialize_tokenizer()
        self._initialize_compressor()

    def _initialize_compressor(self) -> None:
        if PromptCompressor is None:
            logger.warning("LLMLingua not available; prompt compression disabled")
            return
        try:
            self._compressor = PromptCompressor(
                model_name=_DEFAULT_MODEL_NAME,
                use_llmlingua2=True,
            )
            logger.info("Prompt compressor initialised with %s", _DEFAULT_MODEL_NAME)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("Failed to initialise prompt compressor: %s", exc)
            self._compressor = None

    def _initialize_tokenizer(self) -> None:
        if tiktoken is None:
            logger.warning("tiktoken not available; using approximate token counts")
            return
        try:
            self._tokenizer = tiktoken.get_encoding("cl100k_base")
        except Exception as exc:  # pragma: no cover
            logger.warning("Failed to initialise tokenizer: %s", exc)
            self._tokenizer = None

    # Public API -----------------------------------------------------------------
    def compress_existing_entities(
        self,
        entities: Sequence[Union["EntityNode", Mapping[str, Any]]],
        *,
        target_tokens: int = _DEFAULT_TARGET_TOKENS,
        compression_ratio: float = _DEFAULT_COMPRESSION_RATIO,
        force_tokens: Optional[Iterable[str]] = None,
    ) -> Tuple[str, CompressionStats]:
        """Compress the textual representation of existing entities.

        The returned text enumerates entities by index so the LLM can still refer to
        canonical indices when producing `duplicate_idx` values.
        """

        normalized = self._normalize_entities(entities)
        text_block = self._format_entities(normalized)
        original_tokens = self.count_tokens(text_block)

        if not normalized:
            empty_stats = CompressionStats(
                original_tokens=0,
                compressed_tokens=0,
                compression_ratio=1.0,
                compression_time_ms=0.0,
                entities_count=0,
                target_tokens=target_tokens,
            )
            return "", empty_stats

        if self._compressor is None or original_tokens <= target_tokens:
            stats = CompressionStats(
                original_tokens=original_tokens,
                compressed_tokens=original_tokens,
                compression_ratio=1.0,
                compression_time_ms=0.0,
                entities_count=len(normalized),
                target_tokens=target_tokens,
            )
            return text_block, stats

        compression_force_tokens = list(force_tokens or [])
        if not compression_force_tokens:
            compression_force_tokens = [
                "Candidate",  # keeps candidate label intact
                "idx=",
                "Name:",
                "Labels:",
                "UUID:",
                "Summary:",
                "Attributes:",
            ]

        try:
            import time

            start = time.perf_counter()
            compressed = self._compressor.compress_prompt(
                text_block,
                rate=compression_ratio,
                force_tokens=compression_force_tokens,
                drop_consecutive=True,
            )
            duration_ms = (time.perf_counter() - start) * 1000
            compressed_text = compressed.get("compressed_prompt", text_block)
            compressed_tokens = self.count_tokens(compressed_text)

            stats = CompressionStats(
                original_tokens=original_tokens,
                compressed_tokens=compressed_tokens,
                compression_ratio=(
                    compressed_tokens / original_tokens if original_tokens > 0 else 1.0
                ),
                compression_time_ms=duration_ms,
                entities_count=len(normalized),
                target_tokens=target_tokens,
            )
            return compressed_text, stats
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Prompt compression failed: %s", exc)
            stats = CompressionStats(
                original_tokens=original_tokens,
                compressed_tokens=original_tokens,
                compression_ratio=1.0,
                compression_time_ms=0.0,
                entities_count=len(normalized),
                target_tokens=target_tokens,
                error=str(exc),
            )
            return text_block, stats

    def compress_existing_entities_for_batch(
        self,
        entities: Sequence[Union["EntityNode", Mapping[str, Any]]],
    ) -> Tuple[str, CompressionStats]:
        """Convenience wrapper for batch deduplication."""

        return self.compress_existing_entities(
            entities,
            target_tokens=_DEFAULT_BATCH_TARGET_TOKENS,
            compression_ratio=_DEFAULT_BATCH_RATIO,
        )

    def count_tokens(self, text: str) -> int:
        if not text:
            return 0
        if self._tokenizer is None:
            # Fallback: rough approximation using whitespace split
            return len(text.split())
        return len(self._tokenizer.encode(text))

    # Internal helpers -----------------------------------------------------------
    def _normalize_entities(
        self,
        entities: Sequence[Union["EntityNode", Mapping[str, Any]]],
    ) -> List[MutableMapping[str, Any]]:
        normalized: List[MutableMapping[str, Any]] = []
        for idx, entity in enumerate(entities):
            if hasattr(entity, "model_dump"):
                # Pydantic model (EntityNode)
                data: MutableMapping[str, Any] = {
                    "name": getattr(entity, "name", ""),
                    "labels": list(getattr(entity, "labels", []) or []),
                    "uuid": getattr(entity, "uuid", ""),
                    "summary": getattr(entity, "summary", ""),
                    "attributes": dict(getattr(entity, "attributes", {}) or {}),
                }
            else:
                mapping = dict(entity)  # type: ignore[arg-type]
                data = {
                    "name": mapping.get("name", ""),
                    "labels": list(mapping.get("labels", []) or []),
                    "uuid": mapping.get("uuid", ""),
                    "summary": mapping.get("summary", ""),
                    "attributes": dict(mapping.get("attributes", {}) or {}),
                }
            data["idx"] = idx
            normalized.append(data)
        return normalized

    def _format_entities(self, entities: Sequence[Mapping[str, Any]]) -> str:
        formatted: List[str] = []
        for entry in entities:
            idx = entry.get("idx", "?")
            name = entry.get("name", "")
            labels = ", ".join(entry.get("labels", []) or [])
            uuid = entry.get("uuid", "")
            summary = (entry.get("summary") or "").strip()
            attributes = self._format_attributes(entry.get("attributes") or {})

            lines = [
                f"Candidate idx={idx}",
                f"Name: {name}",
            ]
            if labels:
                lines.append(f"Labels: {labels}")
            if uuid:
                lines.append(f"UUID: {uuid}")
            if summary:
                lines.append(f"Summary: {summary}")
            if attributes:
                lines.append(f"Attributes: {attributes}")

            formatted.append("\n".join(lines))
        return "\n\n".join(formatted)

    def _format_attributes(self, attributes: Mapping[str, Any]) -> str:
        if not attributes:
            return ""
        formatted_items: List[str] = []
        for key, value in attributes.items():
            if value is None:
                continue
            value_str = str(value)
            if not value_str:
                continue
            if len(value_str) > 120:
                value_str = f"{value_str[:117]}..."
            formatted_items.append(f"{key}={value_str}")
            if len(formatted_items) >= 5:
                break
        return ", ".join(formatted_items)


_compressor_instance: Optional[GraphitiPromptCompressor] = None


def get_prompt_compressor() -> GraphitiPromptCompressor:
    global _compressor_instance
    if _compressor_instance is None:
        _compressor_instance = GraphitiPromptCompressor()
    return _compressor_instance
