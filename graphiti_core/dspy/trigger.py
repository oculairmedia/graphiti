"""
Optimization Trigger for DSPy MIPROv2.

Tracks ingestion counts and triggers optimization when threshold is reached.
Counter is persisted in FalkorDB graphiti_prompts graph.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Callable, Awaitable

if TYPE_CHECKING:
    from falkordb.asyncio import FalkorDB

logger = logging.getLogger(__name__)

PROMPT_DATABASE = 'graphiti_prompts'
COUNTER_NODE_ID = 'ingestion_counter'


@dataclass
class TriggerConfig:
    threshold: int = 100
    min_training_examples: int = 50
    enabled: bool = True

    @classmethod
    def from_env(cls) -> TriggerConfig:
        return cls(
            threshold=int(os.getenv('DSPY_OPTIMIZATION_THRESHOLD', '100')),
            min_training_examples=int(os.getenv('DSPY_OPTIMIZATION_MIN_EXAMPLES', '50')),
            enabled=os.getenv('DSPY_OPTIMIZATION_ENABLED', 'true').lower() == 'true',
        )


class OptimizationTrigger:
    """
    Tracks ingestion count and triggers MIPROv2 optimization.

    The counter is persisted in FalkorDB's graphiti_prompts graph
    as an IngestionCounter node, surviving restarts.
    """

    def __init__(
        self,
        config: TriggerConfig | None = None,
        client: FalkorDB | None = None,
        host: str | None = None,
        port: int | None = None,
        on_trigger: Callable[[], Awaitable[None]] | None = None,
    ):
        self.config = config or TriggerConfig.from_env()
        self._client = client
        self._host = host or os.getenv('FALKORDB_HOST', 'localhost')
        self._port = port or int(os.getenv('FALKORDB_PORT', '6379'))
        self._on_trigger = on_trigger
        self._lock = asyncio.Lock()
        self._local_counter = 0

    async def _get_client(self) -> FalkorDB:
        if self._client is not None:
            return self._client

        from falkordb.asyncio import FalkorDB

        self._client = FalkorDB(host=self._host, port=self._port)
        return self._client

    async def _get_graph(self):
        client = await self._get_client()
        return client.select_graph(PROMPT_DATABASE)

    async def _ensure_counter_exists(self) -> None:
        graph = await self._get_graph()

        query = """
        MERGE (c:IngestionCounter {id: $id})
        ON CREATE SET c.count = 0, c.last_reset = $now, c.last_optimization = null
        """

        now = datetime.now(timezone.utc).isoformat()
        await graph.query(query, {'id': COUNTER_NODE_ID, 'now': now})

    async def get_count(self) -> int:
        await self._ensure_counter_exists()
        graph = await self._get_graph()

        query = """
        MATCH (c:IngestionCounter {id: $id})
        RETURN c.count as count
        """

        result = await graph.query(query, {'id': COUNTER_NODE_ID})
        if result.result_set:
            return result.result_set[0][0] or 0
        return 0

    async def increment(self) -> bool:
        """
        Increment the counter. Returns True if optimization should trigger.

        Thread-safe via asyncio lock.
        """
        if not self.config.enabled:
            return False

        async with self._lock:
            await self._ensure_counter_exists()
            graph = await self._get_graph()

            query = """
            MATCH (c:IngestionCounter {id: $id})
            SET c.count = c.count + 1
            RETURN c.count as count
            """

            result = await graph.query(query, {'id': COUNTER_NODE_ID})
            current_count = result.result_set[0][0] if result.result_set else 0

            self._local_counter = current_count

            if current_count >= self.config.threshold:
                if await self._has_enough_training_data():
                    logger.info(
                        f'Optimization trigger: count={current_count}, threshold={self.config.threshold}'
                    )
                    return True
                else:
                    logger.debug(f'Counter at {current_count} but insufficient training data')

            return False

    async def _has_enough_training_data(self) -> bool:
        try:
            from graphiti_core.dspy.modules import get_training_stats

            stats = get_training_stats()
            if stats is None:
                return False

            min_count = min(stats.values()) if stats else 0
            has_enough = min_count >= self.config.min_training_examples

            if not has_enough:
                logger.debug(
                    f'Training data stats: {stats}, need {self.config.min_training_examples} each'
                )

            return has_enough
        except Exception as e:
            logger.warning(f'Failed to check training data: {e}')
            return False

    async def reset_counter(self) -> None:
        async with self._lock:
            graph = await self._get_graph()
            now = datetime.now(timezone.utc).isoformat()

            query = """
            MATCH (c:IngestionCounter {id: $id})
            SET c.count = 0, c.last_reset = $now
            """

            await graph.query(query, {'id': COUNTER_NODE_ID, 'now': now})
            self._local_counter = 0
            logger.info('Optimization counter reset')

    async def mark_optimization_started(self) -> None:
        graph = await self._get_graph()
        now = datetime.now(timezone.utc).isoformat()

        query = """
        MATCH (c:IngestionCounter {id: $id})
        SET c.last_optimization = $now, c.count = 0
        """

        await graph.query(query, {'id': COUNTER_NODE_ID, 'now': now})
        self._local_counter = 0

    async def trigger_optimization(self) -> None:
        """
        Trigger the optimization callback and reset the counter.

        The callback should launch a background MIPROv2 job
        (e.g., Temporal workflow or async task).
        """
        await self.mark_optimization_started()

        if self._on_trigger:
            try:
                await self._on_trigger()
                logger.info('Optimization triggered successfully')
            except Exception as e:
                logger.error(f'Optimization trigger callback failed: {e}')
        else:
            logger.warning('No optimization callback configured')

    async def get_status(self) -> dict:
        await self._ensure_counter_exists()
        graph = await self._get_graph()

        query = """
        MATCH (c:IngestionCounter {id: $id})
        RETURN c.count as count, c.last_reset as last_reset, c.last_optimization as last_optimization
        """

        result = await graph.query(query, {'id': COUNTER_NODE_ID})
        if result.result_set:
            row = result.result_set[0]
            return {
                'count': row[0] or 0,
                'threshold': self.config.threshold,
                'last_reset': row[1],
                'last_optimization': row[2],
                'enabled': self.config.enabled,
                'min_training_examples': self.config.min_training_examples,
            }
        return {
            'count': 0,
            'threshold': self.config.threshold,
            'last_reset': None,
            'last_optimization': None,
            'enabled': self.config.enabled,
            'min_training_examples': self.config.min_training_examples,
        }


_default_trigger: OptimizationTrigger | None = None


def get_optimization_trigger() -> OptimizationTrigger:
    global _default_trigger
    if _default_trigger is None:
        _default_trigger = OptimizationTrigger()
    return _default_trigger


def configure_optimization_trigger(trigger: OptimizationTrigger) -> None:
    global _default_trigger
    _default_trigger = trigger
