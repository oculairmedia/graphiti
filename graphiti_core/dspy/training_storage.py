"""
FalkorDB-backed storage for DSPy training data.

Replaces the JSON file-based TrainingDataCollector to avoid race conditions
when multiple workers write simultaneously.
"""

import json
import logging
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

TRAINING_TASKS = ['entity_extraction', 'edge_extraction', 'node_resolution', 'summary_generation']
PROMPT_DATABASE = 'graphiti_prompts'


@dataclass
class StoredTrainingExample:
    """A training example retrieved from FalkorDB."""

    id: str
    task: str
    inputs: dict[str, Any]
    output: dict[str, Any]
    metadata: dict[str, Any]
    created_at: datetime

    def to_dspy_example(self):
        """Convert to DSPy Example format for MIPROv2."""
        import dspy

        example_dict = {**self.inputs, **self.output}
        return dspy.Example(**example_dict).with_inputs(*self.inputs.keys())


class TrainingDataStorage:
    """
    FalkorDB-backed storage for training examples.

    Uses atomic CREATE operations to avoid race conditions between workers.
    """

    def __init__(self):
        self._client = None
        self._graph = None

    async def _ensure_connected(self):
        """Lazily connect to FalkorDB."""
        if self._graph is not None:
            return

        try:
            from falkordb.asyncio import FalkorDB

            host = os.getenv('FALKORDB_HOST', 'localhost')
            port = int(os.getenv('FALKORDB_PORT', '6379'))

            self._client = FalkorDB(host=host, port=port)
            self._graph = self._client.select_graph(PROMPT_DATABASE)
            logger.debug(f'Connected to FalkorDB training storage at {host}:{port}')
        except Exception as e:
            logger.error(f'Failed to connect to FalkorDB for training storage: {e}')
            raise

    async def record_example(
        self,
        task: str,
        inputs: dict[str, Any],
        output: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """
        Record a training example atomically.

        Args:
            task: Task name (entity_extraction, edge_extraction, etc.)
            inputs: Input parameters dict
            output: Expected output dict
            metadata: Optional metadata (worker_id, episode_uuid, etc.)

        Returns:
            UUID of the created example
        """
        await self._ensure_connected()

        example_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        query = """
        CREATE (t:TrainingExample {
            id: $id,
            task: $task,
            inputs: $inputs,
            output: $output,
            metadata: $metadata,
            created_at: $created_at
        })
        RETURN t.id
        """

        try:
            await self._graph.query(
                query,
                {
                    'id': example_id,
                    'task': task,
                    'inputs': json.dumps(inputs),
                    'output': json.dumps(output),
                    'metadata': json.dumps(metadata or {}),
                    'created_at': now,
                },
            )
            logger.debug(f'Recorded training example {example_id[:8]}... for {task}')
            return example_id
        except Exception as e:
            logger.error(f'Failed to record training example: {e}')
            raise

    async def get_examples(
        self,
        task: str,
        limit: int = 1000,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[StoredTrainingExample]:
        """
        Retrieve training examples for a task.

        Args:
            task: Task name to filter by
            limit: Maximum examples to return
            since: Optional start date filter
            until: Optional end date filter

        Returns:
            List of StoredTrainingExample objects
        """
        await self._ensure_connected()

        if since or until:
            query = """
            MATCH (t:TrainingExample {task: $task})
            WHERE ($since IS NULL OR t.created_at >= $since)
              AND ($until IS NULL OR t.created_at <= $until)
            RETURN t.id, t.inputs, t.output, t.metadata, t.created_at
            ORDER BY t.created_at DESC
            LIMIT $limit
            """
            params = {
                'task': task,
                'limit': limit,
                'since': since.isoformat() if since else None,
                'until': until.isoformat() if until else None,
            }
        else:
            query = """
            MATCH (t:TrainingExample {task: $task})
            RETURN t.id, t.inputs, t.output, t.metadata, t.created_at
            ORDER BY t.created_at DESC
            LIMIT $limit
            """
            params = {'task': task, 'limit': limit}

        try:
            result = await self._graph.query(query, params)

            examples = []
            for row in result.result_set:
                try:
                    created_at = row[4]
                    if isinstance(created_at, str):
                        created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    elif not isinstance(created_at, datetime):
                        created_at = datetime.now(timezone.utc)

                    examples.append(
                        StoredTrainingExample(
                            id=row[0],
                            task=task,
                            inputs=json.loads(row[1]) if isinstance(row[1], str) else row[1],
                            output=json.loads(row[2]) if isinstance(row[2], str) else row[2],
                            metadata=json.loads(row[3]) if isinstance(row[3], str) else row[3],
                            created_at=created_at,
                        )
                    )
                except Exception as e:
                    logger.warning(f'Failed to parse training example: {e}')
                    continue

            return examples
        except Exception as e:
            logger.error(f'Failed to get training examples: {e}')
            return []

    async def get_stats(self) -> dict[str, int]:
        """Get count of training examples per task."""
        await self._ensure_connected()

        query = """
        MATCH (t:TrainingExample)
        RETURN t.task, count(t) as count
        """

        try:
            result = await self._graph.query(query)
            stats = {task: 0 for task in TRAINING_TASKS}
            for row in result.result_set:
                if row[0] in stats:
                    stats[row[0]] = row[1]
            return stats
        except Exception as e:
            logger.error(f'Failed to get training stats: {e}')
            return {task: 0 for task in TRAINING_TASKS}

    async def get_total_count(self) -> int:
        """Get total count of all training examples."""
        await self._ensure_connected()

        query = 'MATCH (t:TrainingExample) RETURN count(t)'

        try:
            result = await self._graph.query(query)
            return result.result_set[0][0] if result.result_set else 0
        except Exception as e:
            logger.error(f'Failed to get total count: {e}')
            return 0


_storage_instance: TrainingDataStorage | None = None


def get_training_storage() -> TrainingDataStorage:
    """Get singleton TrainingDataStorage instance."""
    global _storage_instance
    if _storage_instance is None:
        _storage_instance = TrainingDataStorage()
    return _storage_instance


async def record_training_example(
    task: str,
    inputs: dict[str, Any],
    output: dict[str, Any],
    metadata: dict[str, Any] | None = None,
) -> str | None:
    """
    Convenience function to record a training example.

    Returns the example ID or None if collection is disabled.
    """
    if os.getenv('DSPY_COLLECT_TRAINING_DATA', 'false').lower() != 'true':
        return None

    try:
        storage = get_training_storage()
        return await storage.record_example(task, inputs, output, metadata)
    except Exception as e:
        logger.warning(f'Failed to record training example: {e}')
        return None


async def get_training_stats() -> dict[str, int]:
    """Get training data statistics."""
    try:
        storage = get_training_storage()
        return await storage.get_stats()
    except Exception as e:
        logger.warning(f'Failed to get training stats: {e}')
        return {task: 0 for task in TRAINING_TASKS}


async def get_training_examples(
    task: str,
    limit: int = 1000,
    since: datetime | None = None,
    until: datetime | None = None,
) -> list[StoredTrainingExample]:
    """Retrieve training examples for MIPROv2 optimization."""
    storage = get_training_storage()
    return await storage.get_examples(task, limit, since, until)


async def sample_training_examples(
    task: str,
    n: int,
    seed: int | None = None,
) -> list[StoredTrainingExample]:
    """
    Random sample of training examples for validation set.

    Used by MIPROv2 to create train/validation splits.
    """
    import random

    examples = await get_training_examples(task, limit=n * 10)

    if len(examples) <= n:
        return examples

    rng = random.Random(seed)
    return rng.sample(examples, n)


def split_train_val(
    examples: list[StoredTrainingExample],
    val_ratio: float = 0.2,
    seed: int | None = None,
) -> tuple[list[StoredTrainingExample], list[StoredTrainingExample]]:
    """Split examples into train and validation sets."""
    import random

    if not examples:
        return [], []

    rng = random.Random(seed)
    shuffled = examples.copy()
    rng.shuffle(shuffled)

    split_idx = int(len(shuffled) * (1 - val_ratio))
    return shuffled[:split_idx], shuffled[split_idx:]


def to_dspy_examples(examples: list[StoredTrainingExample]) -> list:
    """Convert StoredTrainingExamples to DSPy Examples for MIPROv2."""
    return [ex.to_dspy_example() for ex in examples]
