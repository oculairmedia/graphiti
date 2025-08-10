"""
Tests for atomic centrality storage with transaction safety.
"""

import asyncio
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch, call
from typing import Dict, Any

from graphiti_core.utils.maintenance.atomic_centrality_storage import (
    AtomicCentralityStorage,
    StorageState,
    StorageTransaction,
    BatchUpdateContext,
)
from graphiti_core.driver.driver import GraphDriver


@pytest.fixture
def mock_driver():
    """Create a mock graph driver."""
    driver = AsyncMock(spec=GraphDriver)
    driver.execute_query = AsyncMock()
    return driver


@pytest.fixture
def storage(mock_driver):
    """Create an atomic centrality storage instance."""
    return AtomicCentralityStorage(
        driver=mock_driver,
        batch_size=2,  # Small batch size for testing
        max_retries=2,
        checkpoint_interval=5,
    )


@pytest.fixture
def sample_scores():
    """Sample centrality scores for testing."""
    return {
        "node1": {
            "pagerank": 0.15,
            "degree": 5,
            "betweenness": 0.03,
            "importance": 2.5,
        },
        "node2": {
            "pagerank": 0.25,
            "degree": 10,
            "betweenness": 0.08,
            "importance": 4.2,
        },
        "node3": {
            "pagerank": 0.10,
            "degree": 3,
            "betweenness": 0.01,
            "importance": 1.8,
        },
    }


@pytest.mark.asyncio
class TestAtomicCentralityStorage:
    """Test suite for atomic centrality storage."""
    
    async def test_store_centrality_atomic_success(self, storage, mock_driver, sample_scores):
        """Test successful atomic storage of centrality scores."""
        # Execute the storage
        transaction = await storage.store_centrality_atomic(sample_scores)
        
        # Verify transaction state
        assert transaction.state == StorageState.COMMITTED
        assert transaction.total_nodes == 3
        assert transaction.processed_nodes == 3
        assert transaction.failed_nodes == 0
        
        # Verify driver was called with correct queries
        calls = mock_driver.execute_query.call_args_list
        
        # Should have: transaction metadata, 2 batches, commit
        assert len(calls) >= 4
        
        # Check transaction metadata creation
        metadata_call = calls[0]
        assert "CREATE (t:CentralityTransaction" in metadata_call[0][0]
        
        # Check batch updates
        batch_calls = [c for c in calls if "UNWIND" in c[0][0]]
        assert len(batch_calls) == 2  # 3 nodes with batch_size=2
    
    async def test_store_centrality_validation(self, storage, mock_driver):
        """Test validation of centrality scores."""
        # Test empty scores - should raise RuntimeError (wrapping ValueError)
        with pytest.raises(RuntimeError, match="Centrality storage failed"):
            await storage.store_centrality_atomic({})
        
        # Test invalid score type
        invalid_scores = {
            "node1": {"pagerank": "invalid"},
        }
        with pytest.raises(RuntimeError, match="Centrality storage failed"):
            await storage.store_centrality_atomic(invalid_scores)
        
        # Test negative score
        negative_scores = {
            "node1": {"pagerank": -0.5},
        }
        with pytest.raises(RuntimeError, match="Centrality storage failed"):
            await storage.store_centrality_atomic(negative_scores)
        
        # Test out of range PageRank
        out_of_range_scores = {
            "node1": {"pagerank": 1.5},
        }
        with pytest.raises(RuntimeError, match="Centrality storage failed"):
            await storage.store_centrality_atomic(out_of_range_scores)
    
    async def test_store_centrality_with_retry(self, storage, mock_driver, sample_scores):
        """Test retry logic on batch failures."""
        # Make first batch fail once, then succeed
        call_count = 0
        
        async def execute_with_retry(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if "UNWIND" in args[0] and call_count == 2:
                # Fail the first batch on first attempt
                raise Exception("Database error")
            return ([], None, None)
        
        mock_driver.execute_query.side_effect = execute_with_retry
        
        # Should succeed with retry
        transaction = await storage.store_centrality_atomic(sample_scores)
        
        assert transaction.state == StorageState.COMMITTED
        assert transaction.processed_nodes == 3
        
        # Verify retry happened (more calls than expected)
        assert call_count > 4  # Extra call due to retry
    
    async def test_store_centrality_rollback_on_failure(self, storage, mock_driver, sample_scores):
        """Test rollback on persistent failure."""
        # Make batch updates always fail
        async def execute_with_failure(*args, **kwargs):
            if "UNWIND" in args[0]:
                raise Exception("Persistent database error")
            return ([], None, None)
        
        mock_driver.execute_query.side_effect = execute_with_failure
        
        # Should raise and trigger rollback
        with pytest.raises(RuntimeError, match="Centrality storage failed"):
            await storage.store_centrality_atomic(sample_scores)
        
        # Verify rollback was attempted
        rollback_calls = [
            c for c in mock_driver.execute_query.call_args_list
            if "REMOVE n.centrality" in str(c)
        ]
        assert len(rollback_calls) > 0
    
    async def test_checkpoint_creation(self, storage, mock_driver):
        """Test checkpoint creation during batch processing."""
        # Create scores that will trigger checkpoint
        many_scores = {
            f"node{i}": {
                "pagerank": 0.1,
                "degree": i,
                "betweenness": 0.01,
                "importance": 1.0,
            }
            for i in range(10)
        }
        
        storage.checkpoint_interval = 5  # Checkpoint every 5 nodes
        
        transaction = await storage.store_centrality_atomic(many_scores)
        
        assert transaction.state == StorageState.COMMITTED
        assert transaction.processed_nodes == 10
        
        # Check for checkpoint calls
        checkpoint_calls = [
            c for c in mock_driver.execute_query.call_args_list
            if "checkpoint_processed" in str(c)
        ]
        assert len(checkpoint_calls) >= 1  # At least one checkpoint
    
    async def test_resume_transaction(self, storage, mock_driver, sample_scores):
        """Test resuming a failed transaction from checkpoint."""
        # Mock loading transaction from database
        mock_driver.execute_query.return_value = (
            [{
                "t": {
                    "transaction_id": "test_txn",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "total_nodes": 3,
                    "checkpoint_processed": 1,  # Already processed 1 node
                    "state": "in_progress",
                }
            }],
            None,
            None,
        )
        
        # Resume transaction
        transaction = await storage.resume_transaction("test_txn", sample_scores)
        
        assert transaction.state == StorageState.COMMITTED
        assert transaction.processed_nodes == 3  # Total processed (1 before + 2 new)
        assert transaction.total_nodes == 3
    
    async def test_transaction_history(self, storage, mock_driver):
        """Test retrieving transaction history."""
        # Mock transaction records
        mock_driver.execute_query.return_value = (
            [
                {"t": {"transaction_id": "txn1", "state": "committed"}},
                {"t": {"transaction_id": "txn2", "state": "rolled_back"}},
            ],
            None,
            None,
        )
        
        history = await storage.get_transaction_history(limit=10)
        
        assert len(history) == 2
        assert history[0]["transaction_id"] == "txn1"
        assert history[0]["state"] == "committed"
        assert history[1]["state"] == "rolled_back"
    
    async def test_batch_update_context(self, storage, mock_driver):
        """Test batch update context manager."""
        async with storage.batch_update_context() as batch:
            await batch.add_scores("node1", {"pagerank": 0.15, "degree": 5})
            await batch.add_scores("node2", {"pagerank": 0.25, "degree": 10})
            # Should auto-commit on exit
        
        # Verify commit was called
        assert mock_driver.execute_query.called
        
        # Check that scores were accumulated
        assert len(batch.scores) == 2
        assert batch.committed
    
    async def test_batch_update_context_rollback(self, storage, mock_driver):
        """Test batch update context rollback on error."""
        try:
            async with storage.batch_update_context() as batch:
                await batch.add_scores("node1", {"pagerank": 0.15})
                # Simulate error
                raise ValueError("Test error")
        except ValueError:
            pass
        
        # Verify rollback was called
        assert not batch.committed
        assert len(batch.scores) == 0  # Scores cleared on rollback
    
    async def test_ensure_indices(self, storage, mock_driver):
        """Test index creation for centrality properties."""
        await storage._ensure_centrality_indices()
        
        # Check index creation queries
        index_calls = [
            c for c in mock_driver.execute_query.call_args_list
            if "CREATE INDEX" in c[0][0]
        ]
        
        # Should create indices for importance, pagerank, degree, updated_at
        assert len(index_calls) >= 4
        
        # Verify index types
        index_queries = [c[0][0] for c in index_calls]
        assert any("centrality_importance" in q for q in index_queries)
        assert any("centrality_pagerank" in q for q in index_queries)
        assert any("centrality_degree" in q for q in index_queries)
        assert any("centrality_updated_at" in q for q in index_queries)
    
    async def test_concurrent_transactions(self, storage, mock_driver):
        """Test handling of concurrent transactions."""
        scores1 = {"node1": {"pagerank": 0.1, "degree": 5}}
        scores2 = {"node2": {"pagerank": 0.2, "degree": 10}}
        
        # Run two transactions concurrently
        results = await asyncio.gather(
            storage.store_centrality_atomic(scores1, "txn1"),
            storage.store_centrality_atomic(scores2, "txn2"),
            return_exceptions=True,
        )
        
        # Both should succeed (lock ensures serialization)
        assert all(isinstance(r, StorageTransaction) for r in results)
        assert all(r.state == StorageState.COMMITTED for r in results)
    
    async def test_batch_size_configuration(self, mock_driver, sample_scores):
        """Test different batch size configurations."""
        # Test with batch_size=1 (each node in separate batch)
        storage_small = AtomicCentralityStorage(mock_driver, batch_size=1)
        transaction = await storage_small.store_centrality_atomic(sample_scores)
        
        assert transaction.state == StorageState.COMMITTED
        
        # Should have 3 batch calls for 3 nodes
        batch_calls = [
            c for c in mock_driver.execute_query.call_args_list
            if "UNWIND" in c[0][0]
        ]
        assert len(batch_calls) == 3
        
        # Reset mock
        mock_driver.reset_mock()
        
        # Test with batch_size=10 (all nodes in one batch)
        storage_large = AtomicCentralityStorage(mock_driver, batch_size=10)
        transaction = await storage_large.store_centrality_atomic(sample_scores)
        
        assert transaction.state == StorageState.COMMITTED
        
        # Should have 1 batch call for 3 nodes
        batch_calls = [
            c for c in mock_driver.execute_query.call_args_list
            if "UNWIND" in c[0][0]
        ]
        assert len(batch_calls) == 1


@pytest.mark.asyncio
class TestBatchUpdateContext:
    """Test suite for batch update context."""
    
    async def test_batch_accumulation(self, storage, mock_driver):
        """Test accumulating scores in batch context."""
        batch = BatchUpdateContext(storage, "test_batch")
        
        await batch.add_scores("node1", {"pagerank": 0.1})
        await batch.add_scores("node2", {"pagerank": 0.2})
        await batch.add_scores("node3", {"pagerank": 0.3})
        
        assert len(batch.scores) == 3
        assert batch.scores["node1"]["pagerank"] == 0.1
        assert batch.scores["node2"]["pagerank"] == 0.2
        assert not batch.committed
    
    async def test_batch_commit(self, storage, mock_driver):
        """Test committing batch updates."""
        batch = BatchUpdateContext(storage, "test_batch")
        
        await batch.add_scores("node1", {"pagerank": 0.1, "degree": 5})
        transaction = await batch.commit()
        
        assert batch.committed
        assert transaction.state == StorageState.COMMITTED
        assert transaction.processed_nodes == 1
        
        # Verify can't commit twice
        result = await batch.commit()
        assert result is None  # Already committed
    
    async def test_batch_rollback(self, storage, mock_driver):
        """Test rolling back batch updates."""
        batch = BatchUpdateContext(storage, "test_batch")
        
        await batch.add_scores("node1", {"pagerank": 0.1})
        await batch.add_scores("node2", {"pagerank": 0.2})
        
        await batch.rollback()
        
        assert len(batch.scores) == 0
        assert not batch.committed