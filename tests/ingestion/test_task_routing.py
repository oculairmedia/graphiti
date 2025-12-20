"""
Tests for task type routing in IngestionWorker.
Covers routing logic for different TaskTypes and error handling.
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from types import SimpleNamespace

from graphiti_core.ingestion.worker import (
    IngestionWorker,
    PermanentError,
    RateLimitError,
)
from graphiti_core.ingestion.queue_client import (
    IngestionTask,
    TaskType,
    TaskPriority,
)
from graphiti_core.utils.datetime_utils import utc_now


class MockQueueClient:
    """Mock queue client for testing."""

    def __init__(self):
        self.push = AsyncMock(return_value=['msg-1'])
        self.poll = AsyncMock(return_value=[])
        self.delete = AsyncMock(return_value=True)
        self.update = AsyncMock(return_value=True)
        self.close = AsyncMock()


class MockGraphiti:
    """Mock Graphiti client for testing."""

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
    """Create a worker with mocked dependencies."""
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


def create_task(task_type: TaskType, payload: dict, group_id: str = 'test-group') -> IngestionTask:
    """Helper to create test tasks."""
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


class TestTaskRouting:
    """Tests for task type routing."""

    @pytest.mark.asyncio
    async def test_episode_task_routes_to_process_episode(self, worker, mock_graphiti):
        """TaskType.EPISODE should call _process_episode."""
        mock_graphiti.add_episode_resilient.return_value = SimpleNamespace(
            nodes=[], episode=SimpleNamespace(uuid='ep-1'), edges=[]
        )

        task = create_task(
            TaskType.EPISODE,
            {
                'uuid': 'ep-123',
                'content': 'Test content',
                'name': 'Test Episode',
                'timestamp': utc_now().isoformat(),
            },
        )

        await worker._process_task(task)

        mock_graphiti.add_episode_resilient.assert_called_once()

    @pytest.mark.asyncio
    async def test_deduplication_task_routes_to_process_deduplication(self, worker, mock_graphiti):
        """TaskType.DEDUPLICATION should call _process_deduplication."""
        # Mock EntityNode.get_by_group_ids at the module where it's imported from
        with patch(
            'graphiti_core.nodes.EntityNode.get_by_group_ids', new_callable=AsyncMock
        ) as mock_get_by_group_ids:
            mock_get_by_group_ids.return_value = []

            task = create_task(
                TaskType.DEDUPLICATION,
                {'type': 'nodes', 'group_ids': ['test-group']},
            )

            await worker._process_task(task)

            # Should have tried to get entities for deduplication
            mock_get_by_group_ids.assert_called()

    @pytest.mark.asyncio
    async def test_unknown_task_type_raises_permanent_error(self, worker):
        """Unknown task type should raise PermanentError."""
        task = IngestionTask(
            id='task-unknown',
            type='UNKNOWN_TYPE',  # Invalid type
            payload={},
            group_id='test-group',
            priority=TaskPriority.NORMAL,
            retry_count=0,
            max_retries=3,
            created_at=utc_now(),
            metadata={},
        )

        with pytest.raises(PermanentError) as exc_info:
            await worker._process_task(task)

        assert 'Unknown task type' in str(exc_info.value)


class TestRateLimitingInRouting:
    """Tests for rate limiting during task routing."""

    @pytest.mark.asyncio
    async def test_rate_limiter_called_before_processing(self, worker, mock_graphiti):
        """Rate limiter should be checked before processing."""
        worker.rate_limiter.acquire = AsyncMock(return_value=True)
        mock_graphiti.add_episode_resilient.return_value = SimpleNamespace(
            nodes=[], episode=SimpleNamespace(uuid='ep-1'), edges=[]
        )

        task = create_task(
            TaskType.EPISODE,
            {'content': 'Test', 'name': 'Test', 'timestamp': utc_now().isoformat()},
        )

        await worker._process_task(task)

        worker.rate_limiter.acquire.assert_called_once()

    @pytest.mark.asyncio
    async def test_rate_limit_error_propagates(self, worker):
        """RateLimitError from rate limiter should propagate."""
        worker.rate_limiter.acquire = AsyncMock(
            side_effect=RateLimitError('test-group', retry_after=60)
        )

        task = create_task(TaskType.EPISODE, {'content': 'Test', 'name': 'Test'})

        with pytest.raises(RateLimitError):
            await worker._process_task(task)


class TestGroupIdResolution:
    """Tests for group_id resolution in task routing."""

    @pytest.mark.asyncio
    async def test_uses_task_group_id(self, worker, mock_graphiti):
        """Should use task.group_id when available."""
        mock_graphiti.add_episode_resilient.return_value = SimpleNamespace(
            nodes=[], episode=SimpleNamespace(uuid='ep-1'), edges=[]
        )

        task = create_task(
            TaskType.EPISODE,
            {'content': 'Test', 'name': 'Test', 'timestamp': utc_now().isoformat()},
            group_id='explicit-group',
        )

        await worker._process_task(task)

        # Check that the correct group_id was used
        call_args = mock_graphiti.add_episode_resilient.call_args
        assert call_args[1]['group_id'] == 'explicit-group'

    @pytest.mark.asyncio
    async def test_uses_payload_group_id_fallback(self, worker, mock_graphiti):
        """Should fall back to payload.group_id when task.group_id is None."""
        mock_graphiti.add_episode_resilient.return_value = SimpleNamespace(
            nodes=[], episode=SimpleNamespace(uuid='ep-1'), edges=[]
        )

        task = IngestionTask(
            id='task-123',
            type=TaskType.EPISODE,
            payload={
                'content': 'Test',
                'name': 'Test',
                'group_id': 'payload-group',
                'timestamp': utc_now().isoformat(),
            },
            group_id=None,  # No task-level group_id
            priority=TaskPriority.NORMAL,
            retry_count=0,
            max_retries=3,
            created_at=utc_now(),
            metadata={},
        )

        await worker._process_task(task)

        call_args = mock_graphiti.add_episode_resilient.call_args
        assert call_args[1]['group_id'] == 'payload-group'


class TestPostSuccessJobsInRouting:
    """Tests for post-success job handling in routing."""

    @pytest.mark.asyncio
    async def test_post_success_jobs_run_after_success(self, worker, mock_graphiti):
        """Post-success jobs should run after successful processing."""
        mock_graphiti.add_episode_resilient.return_value = SimpleNamespace(
            nodes=[SimpleNamespace(uuid='node-1')],
            episode=SimpleNamespace(uuid='ep-1'),
            edges=[],
        )

        task = create_task(
            TaskType.EPISODE,
            {'content': 'Test', 'name': 'Test', 'timestamp': utc_now().isoformat()},
        )

        await worker._process_task(task)

        # Centrality update should have been scheduled and run
        worker.centrality_client.update_nodes_centrality.assert_called()

    @pytest.mark.asyncio
    async def test_post_success_jobs_cleared_on_failure(self, worker, mock_graphiti):
        """Post-success jobs should be cleared on failure."""
        mock_graphiti.add_episode_resilient.side_effect = Exception('Processing failed')

        task = create_task(
            TaskType.EPISODE,
            {'content': 'Test', 'name': 'Test', 'timestamp': utc_now().isoformat()},
        )

        with pytest.raises(Exception):
            await worker._process_task(task)

        # Jobs should have been cleared
        assert len(worker._post_success_jobs) == 0


class TestBatchProcessing:
    """Tests for batch task processing."""

    @pytest.mark.asyncio
    async def test_batch_processes_all_operations(self, worker, mock_graphiti):
        """Batch should process all operations."""
        mock_graphiti.add_episode_resilient.return_value = SimpleNamespace(
            nodes=[], episode=SimpleNamespace(uuid='ep-1'), edges=[]
        )

        task = create_task(
            TaskType.BATCH,
            {
                'operations': [
                    {
                        'id': 'op-1',
                        'type': TaskType.EPISODE.value,
                        'payload': {
                            'content': 'Content 1',
                            'name': 'Episode 1',
                            'timestamp': utc_now().isoformat(),
                        },
                    },
                    {
                        'id': 'op-2',
                        'type': TaskType.EPISODE.value,
                        'payload': {
                            'content': 'Content 2',
                            'name': 'Episode 2',
                            'timestamp': utc_now().isoformat(),
                        },
                    },
                ],
            },
        )

        await worker._process_task(task)

        # Should have processed both operations
        assert mock_graphiti.add_episode_resilient.call_count == 2

    @pytest.mark.asyncio
    async def test_batch_continues_on_partial_failure(self, worker, mock_graphiti):
        """Batch should continue processing after individual failures."""
        success_result = SimpleNamespace(nodes=[], episode=SimpleNamespace(uuid='ep-1'), edges=[])
        mock_graphiti.add_episode_resilient.side_effect = [
            Exception('First failed'),
            success_result,
        ]

        task = create_task(
            TaskType.BATCH,
            {
                'operations': [
                    {
                        'id': 'op-1',
                        'type': TaskType.EPISODE.value,
                        'payload': {
                            'content': 'Content 1',
                            'name': 'Episode 1',
                            'timestamp': utc_now().isoformat(),
                        },
                    },
                    {
                        'id': 'op-2',
                        'type': TaskType.EPISODE.value,
                        'payload': {
                            'content': 'Content 2',
                            'name': 'Episode 2',
                            'timestamp': utc_now().isoformat(),
                        },
                    },
                ],
            },
        )

        # Should not raise - continues after first failure
        await worker._process_task(task)

        assert mock_graphiti.add_episode_resilient.call_count == 2

    @pytest.mark.asyncio
    async def test_batch_raises_when_all_fail(self, worker, mock_graphiti):
        """Batch should raise when all operations fail."""
        mock_graphiti.add_episode_resilient.side_effect = Exception('All failed')

        task = create_task(
            TaskType.BATCH,
            {
                'operations': [
                    {
                        'id': 'op-1',
                        'type': TaskType.EPISODE.value,
                        'payload': {
                            'content': 'Content 1',
                            'name': 'Episode 1',
                            'timestamp': utc_now().isoformat(),
                        },
                    },
                ],
            },
        )

        with pytest.raises(Exception) as exc_info:
            await worker._process_task(task)

        assert 'All batch operations failed' in str(exc_info.value)
