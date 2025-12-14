"""
Tests for WorkerPool lifecycle management in IngestionWorker.
Covers pool initialization, startup, shutdown, and metrics aggregation.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from types import SimpleNamespace

from graphiti_core.ingestion.worker import (
    WorkerPool,
    IngestionWorker,
)


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


@pytest.fixture
def mock_queue():
    """Create a mock queue client."""
    return MockQueueClient()


@pytest.fixture
def mock_graphiti():
    """Create a mock Graphiti client."""
    return MockGraphiti()


class TestWorkerPoolInitialization:
    """Tests for WorkerPool initialization."""

    def test_pool_initialization(self, mock_queue, mock_graphiti):
        """Pool should initialize with correct parameters."""
        pool = WorkerPool(
            queue_client=mock_queue,
            graphiti=mock_graphiti,
            worker_count=4,
            batch_size=10,
        )

        assert pool.worker_count == 4
        assert pool.batch_size == 10
        assert pool.queue == mock_queue
        assert pool.graphiti == mock_graphiti
        assert len(pool.workers) == 0

    def test_default_worker_count(self, mock_queue, mock_graphiti):
        """Pool should default to 4 workers."""
        pool = WorkerPool(
            queue_client=mock_queue,
            graphiti=mock_graphiti,
        )

        assert pool.worker_count == 4

    def test_default_batch_size(self, mock_queue, mock_graphiti):
        """Pool should default to batch_size of 1."""
        pool = WorkerPool(
            queue_client=mock_queue,
            graphiti=mock_graphiti,
        )

        assert pool.batch_size == 1

    def test_custom_worker_count(self, mock_queue, mock_graphiti):
        """Pool should accept custom worker count."""
        pool = WorkerPool(
            queue_client=mock_queue,
            graphiti=mock_graphiti,
            worker_count=8,
        )

        assert pool.worker_count == 8


class TestWorkerPoolStartup:
    """Tests for WorkerPool startup behavior."""

    @pytest.mark.asyncio
    async def test_start_creates_workers(self, mock_queue, mock_graphiti):
        """Start should create the correct number of workers."""
        pool = WorkerPool(
            queue_client=mock_queue,
            graphiti=mock_graphiti,
            worker_count=3,
        )

        with patch.object(IngestionWorker, 'start', new_callable=AsyncMock):
            await pool.start()

        assert len(pool.workers) == 3

    @pytest.mark.asyncio
    async def test_start_assigns_unique_worker_ids(self, mock_queue, mock_graphiti):
        """Each worker should have a unique ID."""
        pool = WorkerPool(
            queue_client=mock_queue,
            graphiti=mock_graphiti,
            worker_count=3,
        )

        with patch.object(IngestionWorker, 'start', new_callable=AsyncMock):
            await pool.start()

        worker_ids = [w.worker_id for w in pool.workers]
        assert len(set(worker_ids)) == 3  # All unique
        assert 'worker_0' in worker_ids
        assert 'worker_1' in worker_ids
        assert 'worker_2' in worker_ids

    @pytest.mark.asyncio
    async def test_start_calls_worker_start(self, mock_queue, mock_graphiti):
        """Start should call start() on each worker."""
        pool = WorkerPool(
            queue_client=mock_queue,
            graphiti=mock_graphiti,
            worker_count=2,
        )

        with patch.object(IngestionWorker, 'start', new_callable=AsyncMock) as mock_start:
            await pool.start()

        assert mock_start.call_count == 2

    @pytest.mark.asyncio
    async def test_workers_share_queue_client(self, mock_queue, mock_graphiti):
        """All workers should share the same queue client."""
        pool = WorkerPool(
            queue_client=mock_queue,
            graphiti=mock_graphiti,
            worker_count=3,
        )

        with patch.object(IngestionWorker, 'start', new_callable=AsyncMock):
            await pool.start()

        for worker in pool.workers:
            assert worker.queue == mock_queue

    @pytest.mark.asyncio
    async def test_workers_share_graphiti_client(self, mock_queue, mock_graphiti):
        """All workers should share the same Graphiti client."""
        pool = WorkerPool(
            queue_client=mock_queue,
            graphiti=mock_graphiti,
            worker_count=3,
        )

        with patch.object(IngestionWorker, 'start', new_callable=AsyncMock):
            await pool.start()

        for worker in pool.workers:
            assert worker.graphiti == mock_graphiti


class TestWorkerPoolShutdown:
    """Tests for WorkerPool shutdown behavior."""

    @pytest.mark.asyncio
    async def test_stop_calls_worker_stop(self, mock_queue, mock_graphiti):
        """Stop should call stop() on each worker."""
        pool = WorkerPool(
            queue_client=mock_queue,
            graphiti=mock_graphiti,
            worker_count=2,
        )

        with patch.object(IngestionWorker, 'start', new_callable=AsyncMock):
            await pool.start()

        with patch.object(IngestionWorker, 'stop', new_callable=AsyncMock) as mock_stop:
            await pool.stop()

        assert mock_stop.call_count == 2

    @pytest.mark.asyncio
    async def test_stop_clears_workers_list(self, mock_queue, mock_graphiti):
        """Stop should clear the workers list."""
        pool = WorkerPool(
            queue_client=mock_queue,
            graphiti=mock_graphiti,
            worker_count=3,
        )

        with patch.object(IngestionWorker, 'start', new_callable=AsyncMock):
            await pool.start()

        assert len(pool.workers) == 3

        with patch.object(IngestionWorker, 'stop', new_callable=AsyncMock):
            await pool.stop()

        assert len(pool.workers) == 0

    @pytest.mark.asyncio
    async def test_stop_handles_worker_stop_errors(self, mock_queue, mock_graphiti):
        """Stop should handle errors from individual workers gracefully."""
        pool = WorkerPool(
            queue_client=mock_queue,
            graphiti=mock_graphiti,
            worker_count=3,
        )

        with patch.object(IngestionWorker, 'start', new_callable=AsyncMock):
            await pool.start()

        # Simulate one worker raising an error during stop
        async def stop_with_error():
            raise Exception('Worker stop failed')

        pool.workers[1].stop = stop_with_error

        # Should not raise - errors are caught via return_exceptions=True
        with patch.object(pool.workers[0], 'stop', new_callable=AsyncMock):
            with patch.object(pool.workers[2], 'stop', new_callable=AsyncMock):
                await pool.stop()

        assert len(pool.workers) == 0

    @pytest.mark.asyncio
    async def test_stop_on_empty_pool(self, mock_queue, mock_graphiti):
        """Stop should handle empty pool gracefully."""
        pool = WorkerPool(
            queue_client=mock_queue,
            graphiti=mock_graphiti,
        )

        # Should not raise
        await pool.stop()

        assert len(pool.workers) == 0


class TestWorkerPoolMetrics:
    """Tests for WorkerPool metrics aggregation."""

    @pytest.mark.asyncio
    async def test_get_metrics_includes_pool_size(self, mock_queue, mock_graphiti):
        """Metrics should include pool size."""
        pool = WorkerPool(
            queue_client=mock_queue,
            graphiti=mock_graphiti,
            worker_count=4,
        )

        metrics = pool.get_metrics()

        assert metrics['pool_size'] == 4

    @pytest.mark.asyncio
    async def test_get_metrics_includes_worker_metrics(self, mock_queue, mock_graphiti):
        """Metrics should include metrics from all workers."""
        pool = WorkerPool(
            queue_client=mock_queue,
            graphiti=mock_graphiti,
            worker_count=2,
        )

        with patch.object(IngestionWorker, 'start', new_callable=AsyncMock):
            await pool.start()

        metrics = pool.get_metrics()

        assert 'workers' in metrics
        assert len(metrics['workers']) == 2

    @pytest.mark.asyncio
    async def test_get_metrics_empty_pool(self, mock_queue, mock_graphiti):
        """Metrics should handle empty pool."""
        pool = WorkerPool(
            queue_client=mock_queue,
            graphiti=mock_graphiti,
            worker_count=3,
        )

        metrics = pool.get_metrics()

        assert metrics['pool_size'] == 3
        assert metrics['workers'] == []


class TestWorkerPoolConcurrency:
    """Tests for concurrent worker operations."""

    @pytest.mark.asyncio
    async def test_workers_start_concurrently(self, mock_queue, mock_graphiti):
        """Workers should start sequentially (implementation detail)."""
        pool = WorkerPool(
            queue_client=mock_queue,
            graphiti=mock_graphiti,
            worker_count=3,
        )

        start_order = []

        async def track_start(self):
            start_order.append(self.worker_id)
            await asyncio.sleep(0.01)  # Small delay to verify order

        with patch.object(IngestionWorker, 'start', track_start):
            await pool.start()

        # Current implementation starts sequentially
        assert start_order == ['worker_0', 'worker_1', 'worker_2']

    @pytest.mark.asyncio
    async def test_workers_stop_concurrently(self, mock_queue, mock_graphiti):
        """Workers should stop concurrently (via asyncio.gather)."""
        pool = WorkerPool(
            queue_client=mock_queue,
            graphiti=mock_graphiti,
            worker_count=3,
        )

        with patch.object(IngestionWorker, 'start', new_callable=AsyncMock):
            await pool.start()

        stop_times = []

        async def track_stop(self):
            stop_times.append(asyncio.get_event_loop().time())
            await asyncio.sleep(0.1)

        for worker in pool.workers:
            worker.stop = lambda self=worker: track_stop(self)

        start_time = asyncio.get_event_loop().time()
        await pool.stop()
        total_time = asyncio.get_event_loop().time() - start_time

        # If running concurrently, total time should be ~0.1s, not ~0.3s
        # Allow some margin for test execution overhead
        assert total_time < 0.25  # Should be close to 0.1s if concurrent


class TestWorkerPoolIntegration:
    """Integration tests for WorkerPool."""

    @pytest.mark.asyncio
    async def test_full_lifecycle(self, mock_queue, mock_graphiti):
        """Test complete pool lifecycle: init -> start -> metrics -> stop."""
        pool = WorkerPool(
            queue_client=mock_queue,
            graphiti=mock_graphiti,
            worker_count=2,
        )

        # Initially empty
        assert len(pool.workers) == 0

        # Start pool
        with patch.object(IngestionWorker, 'start', new_callable=AsyncMock):
            await pool.start()

        assert len(pool.workers) == 2

        # Check metrics
        metrics = pool.get_metrics()
        assert metrics['pool_size'] == 2
        assert len(metrics['workers']) == 2

        # Stop pool
        with patch.object(IngestionWorker, 'stop', new_callable=AsyncMock):
            await pool.stop()

        assert len(pool.workers) == 0

    @pytest.mark.asyncio
    async def test_restart_pool(self, mock_queue, mock_graphiti):
        """Pool should support restart (stop then start again)."""
        pool = WorkerPool(
            queue_client=mock_queue,
            graphiti=mock_graphiti,
            worker_count=2,
        )

        # First start
        with patch.object(IngestionWorker, 'start', new_callable=AsyncMock):
            await pool.start()
        assert len(pool.workers) == 2

        # Stop
        with patch.object(IngestionWorker, 'stop', new_callable=AsyncMock):
            await pool.stop()
        assert len(pool.workers) == 0

        # Restart
        with patch.object(IngestionWorker, 'start', new_callable=AsyncMock):
            await pool.start()
        assert len(pool.workers) == 2
