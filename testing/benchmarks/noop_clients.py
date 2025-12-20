"""Minimal no-op Graphiti clients for benchmark harnesses.

These are intentionally tiny implementations that satisfy Graphiti's runtime
interfaces without requiring a running database or embedding service.

They should only be used for isolated tests/benchmarks that do not persist data.
"""

from __future__ import annotations

from collections.abc import Coroutine, Iterable
from typing import Any

from graphiti_core.driver.driver import GraphDriver, GraphDriverSession
from graphiti_core.embedder.client import EmbedderClient, get_embedding_dimension


class NoopDriverSession(GraphDriverSession):
    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def run(self, query: str, **kwargs: Any) -> Any:
        return []

    async def close(self):
        return None

    async def execute_write(self, func, *args, **kwargs):
        return await func(*args, **kwargs)


class NoopDriver(GraphDriver):
    provider: str = 'noop'

    async def execute_query(self, cypher_query_: str, **kwargs: Any):
        return ([], None, None)

    def session(self, database: str | None = None) -> GraphDriverSession:
        return NoopDriverSession()

    async def close(self):
        return None

    def delete_all_indexes(self, database_: str | None = None) -> Coroutine:
        async def _noop():
            return ([], None, None)

        return _noop()


class DeterministicNoopEmbedder(EmbedderClient):
    """Return deterministic vectors to satisfy embedding calls."""

    def __init__(self, embedding_dim: int | None = None):
        self.embedding_dim = embedding_dim or get_embedding_dimension()

    async def create(
        self, input_data: str | list[str] | Iterable[int] | Iterable[Iterable[int]]
    ) -> list[float]:
        return [0.0] * self.embedding_dim

    async def create_batch(self, input_data_list: list[str]) -> list[list[float]]:
        return [[0.0] * self.embedding_dim for _ in input_data_list]
