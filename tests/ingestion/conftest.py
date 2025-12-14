"""
Shared fixtures for ingestion tests.
This module provides common mock objects and test fixtures used across
multiple test files in the ingestion test suite.
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from types import SimpleNamespace

from graphiti_core.ingestion.worker import IngestionWorker
from graphiti_core.ingestion.queue_client import (
    IngestionTask,
    TaskType,
    TaskPriority,
)
from graphiti_core.utils.datetime_utils import utc_now


class MockQueueClient:
    """Mock queue client for testing.

    Provides async mock methods for all queue operations:
    - push: Add tasks to queue
    - poll: Retrieve tasks from queue
    - delete: Remove tasks from queue
    - update: Update task visibility timeout
    - close: Close the client connection
    """

    def __init__(self):
        self.push = AsyncMock(return_value=['msg-1'])
        self.poll = AsyncMock(return_value=[])
        self.delete = AsyncMock(return_value=True)
        self.update = AsyncMock(return_value=True)
        self.close = AsyncMock()


class MockGraphiti:
    """Mock Graphiti client for testing.

    Provides mock implementations of Graphiti methods commonly used in workers:
    - driver: Mock driver with provider info
    - llm_client: Mock LLM client
    - add_episode_resilient: Process episode content
    - add_triplet: Add relationship triplets
    - save_entity_node: Save entity nodes
    """

    def __init__(self):
        self.driver = SimpleNamespace(provider='neo4j')
        self.llm_client = MagicMock()
        self.add_episode_resilient = AsyncMock()
        self.add_triplet = AsyncMock()
        self.save_entity_node = AsyncMock()


@pytest.fixture
def mock_queue():
    """Create a mock queue client."""
    return MockQueueClient()


@pytest.fixture
def mock_graphiti():
    """Create a mock Graphiti client."""
    return MockGraphiti()


@pytest.fixture
def worker(mock_queue, mock_graphiti):
    """Create a worker with mocked dependencies.

    Sets up:
    - Worker with test worker_id
    - Mocked centrality client
    - Mocked rate limiter (always allows)
    """
    w = IngestionWorker(
        worker_id='test-worker',
        queue_client=mock_queue,
        graphiti=mock_graphiti,
        batch_size=1,
    )
    # Mock centrality client
    w.centrality_client.update_nodes_centrality = AsyncMock(return_value=0)
    w.centrality_client.close = AsyncMock()
    # Mock rate limiter to always allow
    w.rate_limiter.acquire = AsyncMock(return_value=True)
    return w


@pytest.fixture
def sample_task():
    """Create a sample ingestion task for testing.

    Returns an EPISODE type task with:
    - Valid UUID, content, name
    - Test group_id
    - Normal priority
    - Zero retry count with 3 max retries
    """
    return IngestionTask(
        id='task-123',
        type=TaskType.EPISODE,
        payload={
            'uuid': 'episode-123',
            'content': 'Test content',
            'name': 'Test Episode',
            'timestamp': utc_now().isoformat(),
        },
        group_id='test-group',
        priority=TaskPriority.NORMAL,
        retry_count=0,
        max_retries=3,
        created_at=utc_now(),
        metadata={},
    )


def create_task(task_type: TaskType, payload: dict, group_id: str = 'test-group') -> IngestionTask:
    """Helper to create test tasks with specific type and payload.

    Args:
        task_type: The TaskType enum value
        payload: Task payload dictionary
        group_id: Optional group ID (defaults to 'test-group')

    Returns:
        An IngestionTask configured for testing
    """
    return IngestionTask(
        id=f'task-{task_type.value}',
        type=task_type,
        payload=payload,
        group_id=group_id,
        priority=TaskPriority.NORMAL,
        retry_count=0,
        max_retries=3,
        created_at=utc_now(),
        metadata={},
    )


def create_episode_task(content: str = 'Test content', name: str = 'Test Episode') -> IngestionTask:
    """Create a standard episode ingestion task.

    Args:
        content: Episode content text
        name: Episode name

    Returns:
        An EPISODE type IngestionTask
    """
    return create_task(
        TaskType.EPISODE,
        {
            'content': content,
            'name': name,
            'timestamp': utc_now().isoformat(),
        },
    )


def create_entity_task(name: str = 'Test Entity', summary: str = 'Test summary') -> IngestionTask:
    """Create a standard entity ingestion task.

    Args:
        name: Entity name
        summary: Entity summary

    Returns:
        An ENTITY type IngestionTask
    """
    return create_task(
        TaskType.ENTITY,
        {
            'name': name,
            'summary': summary,
        },
    )


def create_batch_task(operations: list) -> IngestionTask:
    """Create a batch task with multiple operations.

    Args:
        operations: List of operation dictionaries

    Returns:
        A BATCH type IngestionTask
    """
    return create_task(TaskType.BATCH, {'operations': operations})


# Re-export for convenience
__all__ = [
    'MockQueueClient',
    'MockGraphiti',
    'mock_queue',
    'mock_graphiti',
    'worker',
    'sample_task',
    'create_task',
    'create_episode_task',
    'create_entity_task',
    'create_batch_task',
]
