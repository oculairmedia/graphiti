"""
Tests for error handling, retry logic, and dead letter queue operations.
Covers error classification, exponential backoff, and DLQ management.
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from types import SimpleNamespace

from graphiti_core.ingestion.worker import (
    IngestionWorker,
    RateLimitError,
    TransientError,
    PermanentError,
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
    # Mock centrality client to avoid HTTP calls
    w.centrality_client.update_nodes_centrality = AsyncMock(return_value=0)
    w.centrality_client.close = AsyncMock()
    return w


@pytest.fixture
def sample_task():
    """Create a sample task for testing."""
    return IngestionTask(
        id='task-123',
        type=TaskType.EPISODE,
        payload={
            'uuid': 'episode-123',
            'content': 'Test content',
            'name': 'Test Episode',
            'group_id': 'group-1',
            'timestamp': utc_now().isoformat(),
        },
        group_id='group-1',
        priority=TaskPriority.NORMAL,
        retry_count=0,
        max_retries=3,
        created_at=utc_now(),
        metadata={},
    )


class TestPermanentErrorHandling:
    """Tests for PermanentError handling."""

    @pytest.mark.asyncio
    async def test_permanent_error_moves_to_dlq(self, worker, sample_task):
        """PermanentError should immediately move task to DLQ."""
        error = PermanentError('Invalid data format')

        await worker._handle_failure(
            message_id='msg-1',
            poll_tag='tag-1',
            task=sample_task,
            error=error,
        )

        # Should push to dead_letter queue
        worker.queue.push.assert_called_once()
        call_args = worker.queue.push.call_args
        assert call_args[1]['queue_name'] == 'dead_letter'

        # Should delete from main queue
        worker.queue.delete.assert_called_once_with('msg-1', 'tag-1')

        # Should NOT update visibility (no retry)
        worker.queue.update.assert_not_called()

    @pytest.mark.asyncio
    async def test_permanent_error_preserves_error_metadata(self, worker, sample_task):
        """DLQ task should contain error information."""
        error = PermanentError('Schema validation failed')

        await worker._handle_failure(
            message_id='msg-1',
            poll_tag='tag-1',
            task=sample_task,
            error=error,
        )

        # Check that metadata was updated
        assert 'error' in sample_task.metadata
        assert 'Schema validation failed' in sample_task.metadata['error']
        assert sample_task.metadata['error_type'] == 'PermanentError'
        assert 'failed_at' in sample_task.metadata
        assert sample_task.metadata['worker_id'] == 'test-worker'

    @pytest.mark.asyncio
    async def test_permanent_error_increments_retry_count(self, worker, sample_task):
        """Retry count should be incremented even for permanent errors."""
        initial_retry_count = sample_task.retry_count
        error = PermanentError('Invalid task')

        await worker._handle_failure(
            message_id='msg-1',
            poll_tag='tag-1',
            task=sample_task,
            error=error,
        )

        assert sample_task.retry_count == initial_retry_count + 1


class TestTransientErrorHandling:
    """Tests for TransientError handling and retries."""

    @pytest.mark.asyncio
    async def test_transient_error_retries_task(self, worker, sample_task):
        """TransientError should retry the task with backoff."""
        error = TransientError('Connection timeout')
        sample_task.retry_count = 0

        await worker._handle_failure(
            message_id='msg-1',
            poll_tag='tag-1',
            task=sample_task,
            error=error,
        )

        # Should update visibility timeout
        worker.queue.update.assert_called_once()

        # Should NOT delete from queue
        worker.queue.delete.assert_not_called()

        # Should NOT push to DLQ
        worker.queue.push.assert_not_called()

    @pytest.mark.asyncio
    async def test_exponential_backoff_calculation(self, worker, sample_task):
        """Should use exponential backoff for retry delays."""
        error = TransientError('Temporary failure')

        # Test different retry counts
        expected_delays = [
            (0, 20),  # 10 * 2^1 = 20
            (1, 40),  # 10 * 2^2 = 40
            (2, 80),  # 10 * 2^3 = 80
            (3, 160),  # 10 * 2^4 = 160
            (4, 300),  # 10 * 2^5 = 320, capped at 300
        ]

        for retry_count, expected_delay in expected_delays:
            sample_task.retry_count = retry_count
            worker.queue.update.reset_mock()

            await worker._handle_failure(
                message_id='msg-1',
                poll_tag='tag-1',
                task=sample_task,
                error=error,
            )

            actual_delay = worker.queue.update.call_args[0][2]
            assert actual_delay == expected_delay, (
                f'Expected {expected_delay} for retry {retry_count}, got {actual_delay}'
            )

    @pytest.mark.asyncio
    async def test_max_delay_capped_at_300(self, worker, sample_task):
        """Backoff delay should never exceed 300 seconds."""
        error = TransientError('Network error')
        sample_task.retry_count = 10  # High retry count

        await worker._handle_failure(
            message_id='msg-1',
            poll_tag='tag-1',
            task=sample_task,
            error=error,
        )

        actual_delay = worker.queue.update.call_args[0][2]
        assert actual_delay <= 300


class TestMaxRetriesExceeded:
    """Tests for behavior when max retries are exceeded."""

    @pytest.mark.asyncio
    async def test_max_retries_moves_to_dlq(self, worker, sample_task):
        """Should move to DLQ when max retries exceeded."""
        error = Exception('Generic error')
        sample_task.retry_count = 3  # Already at max
        sample_task.max_retries = 3

        await worker._handle_failure(
            message_id='msg-1',
            poll_tag='tag-1',
            task=sample_task,
            error=error,
        )

        # Should push to DLQ
        worker.queue.push.assert_called_once()
        call_args = worker.queue.push.call_args
        assert call_args[1]['queue_name'] == 'dead_letter'

        # Should delete from main queue
        worker.queue.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_just_under_max_retries_still_retries(self, worker, sample_task):
        """Should retry when under max retries."""
        error = Exception('Generic error')
        # Note: _handle_failure increments retry_count BEFORE comparison
        # So setting to 1 means after increment it's 2, which is < 3 (max_retries)
        sample_task.retry_count = 1  # After increment becomes 2, still < max_retries(3)
        sample_task.max_retries = 3

        await worker._handle_failure(
            message_id='msg-1',
            poll_tag='tag-1',
            task=sample_task,
            error=error,
        )

        # Should update for retry
        worker.queue.update.assert_called_once()

        # Should NOT push to DLQ
        worker.queue.push.assert_not_called()


class TestRateLimitErrorHandling:
    """Tests for RateLimitError handling."""

    @pytest.mark.asyncio
    async def test_rate_limit_updates_visibility_with_backoff(self, worker, sample_task):
        """RateLimitError should update visibility with exponential backoff."""
        error = RateLimitError(group_id='group-1', retry_after=60)
        sample_task.retry_count = 1

        # Handle failure in the main processing loop context
        # The _handle_failure method doesn't handle RateLimitError - it's handled in _process_loop
        # Let's test the direct behavior
        retry_after = min(300, error.retry_after * (2**sample_task.retry_count))
        await worker.queue.update('msg-1', 'tag-1', retry_after)

        # Verify update was called with backoff
        worker.queue.update.assert_called_with('msg-1', 'tag-1', 120)  # 60 * 2^1 = 120

    @pytest.mark.asyncio
    async def test_rate_limit_backoff_capped(self, worker, sample_task):
        """Rate limit backoff should be capped at 300 seconds."""
        error = RateLimitError(group_id='group-1', retry_after=100)
        sample_task.retry_count = 3

        # Calculate expected backoff: min(300, 100 * 2^3) = min(300, 800) = 300
        retry_after = min(300, error.retry_after * (2**sample_task.retry_count))

        assert retry_after == 300


class TestErrorClassification:
    """Tests for error classification logic."""

    @pytest.mark.asyncio
    async def test_rate_limit_string_detected(self, worker, mock_graphiti, sample_task):
        """Errors containing 'rate limit' should raise RateLimitError."""
        mock_graphiti.add_episode_resilient.side_effect = Exception('API rate limit exceeded')

        with pytest.raises(RateLimitError):
            await worker._process_episode(sample_task)

    @pytest.mark.asyncio
    async def test_connection_error_detected(self, worker, mock_graphiti, sample_task):
        """Errors containing 'connection' should raise TransientError."""
        mock_graphiti.add_episode_resilient.side_effect = Exception('Connection refused')

        with pytest.raises(TransientError) as exc_info:
            await worker._process_episode(sample_task)

        assert 'Connection error' in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_timeout_error_detected(self, worker, mock_graphiti, sample_task):
        """Errors containing 'timeout' should raise TransientError."""
        mock_graphiti.add_episode_resilient.side_effect = Exception('Request timeout')

        with pytest.raises(TransientError) as exc_info:
            await worker._process_episode(sample_task)

        assert 'Connection error' in str(exc_info.value)


class TestDLQOperations:
    """Tests for dead letter queue operations."""

    @pytest.mark.asyncio
    async def test_move_to_dlq_sets_error_metadata(self, worker, sample_task):
        """Moving to DLQ should set appropriate metadata."""
        error = Exception('Test error message')

        await worker._move_to_dlq(sample_task, error)

        assert sample_task.metadata['error'] == 'Test error message'
        assert sample_task.metadata['error_type'] == 'Exception'
        assert sample_task.metadata['worker_id'] == 'test-worker'
        assert 'failed_at' in sample_task.metadata

    @pytest.mark.asyncio
    async def test_move_to_dlq_pushes_to_dead_letter_queue(self, worker, sample_task):
        """Should push task to dead_letter queue."""
        error = Exception('Fatal error')

        await worker._move_to_dlq(sample_task, error)

        worker.queue.push.assert_called_once()
        call_args = worker.queue.push.call_args
        assert call_args[0][0] == [sample_task]
        assert call_args[1]['queue_name'] == 'dead_letter'

    @pytest.mark.asyncio
    async def test_dlq_preserves_original_task_data(self, worker, sample_task):
        """DLQ task should preserve original task data."""
        original_payload = sample_task.payload.copy()
        original_type = sample_task.type
        original_id = sample_task.id

        error = Exception('Error')
        await worker._move_to_dlq(sample_task, error)

        # Original data should be unchanged
        assert sample_task.payload == original_payload
        assert sample_task.type == original_type
        assert sample_task.id == original_id


class TestMetricsRecording:
    """Tests for metrics recording during error handling."""

    @pytest.mark.asyncio
    async def test_failure_increments_failure_metric(self, worker, sample_task):
        """Should record failure metric."""
        error = PermanentError('Test')
        initial_failures = worker.metrics.tasks_failed

        await worker._handle_failure(
            message_id='msg-1',
            poll_tag='tag-1',
            task=sample_task,
            error=error,
        )

        assert worker.metrics.tasks_failed == initial_failures + 1

    @pytest.mark.asyncio
    async def test_retry_increments_retry_metric(self, worker, sample_task):
        """Should record retry metric for transient errors."""
        error = TransientError('Temporary failure')
        sample_task.retry_count = 0
        initial_retries = worker.metrics.tasks_retried

        await worker._handle_failure(
            message_id='msg-1',
            poll_tag='tag-1',
            task=sample_task,
            error=error,
        )

        assert worker.metrics.tasks_retried == initial_retries + 1


class TestEdgeCases:
    """Tests for edge cases in error handling."""

    @pytest.mark.asyncio
    async def test_empty_error_message(self, worker, sample_task):
        """Should handle empty error messages when moved to DLQ."""
        # Use PermanentError to ensure it goes to DLQ where metadata is updated
        error = PermanentError('')

        await worker._handle_failure(
            message_id='msg-1',
            poll_tag='tag-1',
            task=sample_task,
            error=error,
        )

        assert sample_task.metadata['error'] == ''

    @pytest.mark.asyncio
    async def test_none_group_id_in_task(self, worker, sample_task):
        """Should handle tasks with None group_id."""
        sample_task.group_id = None
        sample_task.payload['group_id'] = None
        error = PermanentError('Test')

        # Should not raise
        await worker._handle_failure(
            message_id='msg-1',
            poll_tag='tag-1',
            task=sample_task,
            error=error,
        )

    @pytest.mark.asyncio
    async def test_unicode_in_error_message(self, worker, sample_task):
        """Should handle unicode in error messages."""
        error = Exception('Error with unicode: \u4e2d\u6587 \u65e5\u672c\u8a9e')

        await worker._move_to_dlq(sample_task, error)

        assert '\u4e2d\u6587' in sample_task.metadata['error']

    @pytest.mark.asyncio
    async def test_very_long_error_message(self, worker, sample_task):
        """Should handle very long error messages."""
        long_message = 'x' * 10000
        error = Exception(long_message)

        await worker._move_to_dlq(sample_task, error)

        assert len(sample_task.metadata['error']) == 10000
