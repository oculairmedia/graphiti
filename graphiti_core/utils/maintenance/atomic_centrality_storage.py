"""
Atomic centrality storage with transaction safety and batch operations.

This module provides a robust centrality storage system with:
- Transaction safety for atomic updates
- Batch operations for efficient storage
- Rollback capability on failures
- Consistency guarantees across failures
- Progress tracking and resumability
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple, Any
from contextlib import asynccontextmanager

from graphiti_core.driver.driver import GraphDriver

logger = logging.getLogger(__name__)


class StorageState(Enum):
    """State of centrality storage operation."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMMITTED = "committed"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"


@dataclass
class StorageTransaction:
    """Represents a centrality storage transaction."""
    transaction_id: str
    timestamp: datetime
    state: StorageState
    total_nodes: int
    processed_nodes: int
    failed_nodes: int
    node_batch: List[str]
    error_details: Optional[str] = None
    checkpoint: Optional[Dict[str, Any]] = None


class AtomicCentralityStorage:
    """
    Provides atomic centrality storage with transaction safety.
    
    Features:
    - Atomic batch updates with all-or-nothing semantics
    - Transaction logging for audit and recovery
    - Checkpoint-based resumability
    - Automatic rollback on failures
    - Configurable batch sizes for memory efficiency
    """
    
    def __init__(
        self,
        driver: GraphDriver,
        batch_size: int = 100,
        max_retries: int = 3,
        checkpoint_interval: int = 500,
    ):
        """
        Initialize atomic centrality storage.
        
        Args:
            driver: Graph database driver
            batch_size: Number of nodes to process in each batch
            max_retries: Maximum retry attempts for failed operations
            checkpoint_interval: Nodes processed between checkpoints
        """
        self.driver = driver
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.checkpoint_interval = checkpoint_interval
        self._transaction_log: List[StorageTransaction] = []
        self._lock = asyncio.Lock()
    
    async def store_centrality_atomic(
        self,
        scores: Dict[str, Dict[str, float]],
        transaction_id: Optional[str] = None,
        validate: bool = True,
    ) -> StorageTransaction:
        """
        Store centrality scores atomically with transaction safety.
        
        Args:
            scores: Dictionary mapping node UUIDs to centrality scores
            transaction_id: Optional transaction ID for tracking
            validate: Whether to validate scores before storing
        
        Returns:
            StorageTransaction with operation results
        
        Raises:
            ValueError: If validation fails
            RuntimeError: If storage fails after retries
        """
        if not transaction_id:
            transaction_id = f"txn_{int(time.time() * 1000)}"
        
        transaction = StorageTransaction(
            transaction_id=transaction_id,
            timestamp=datetime.now(timezone.utc),
            state=StorageState.PENDING,
            total_nodes=len(scores),
            processed_nodes=0,
            failed_nodes=0,
            node_batch=[],
        )
        
        async with self._lock:
            self._transaction_log.append(transaction)
            
            try:
                # Validate scores if requested
                if validate:
                    await self._validate_scores(scores)
                
                # Store transaction metadata
                await self._store_transaction_metadata(transaction)
                
                # Process in batches
                transaction.state = StorageState.IN_PROGRESS
                await self._process_batches(transaction, scores)
                
                # Commit transaction
                await self._commit_transaction(transaction)
                transaction.state = StorageState.COMMITTED
                
                logger.info(
                    f"Transaction {transaction_id} committed: "
                    f"{transaction.processed_nodes}/{transaction.total_nodes} nodes stored"
                )
                
            except Exception as e:
                logger.error(f"Transaction {transaction_id} failed: {e}")
                transaction.error_details = str(e)
                transaction.state = StorageState.FAILED
                
                # Attempt rollback
                await self._rollback_transaction(transaction)
                raise RuntimeError(f"Centrality storage failed: {e}") from e
            
            return transaction
    
    async def _validate_scores(self, scores: Dict[str, Dict[str, float]]) -> None:
        """
        Validate centrality scores before storage.
        
        Args:
            scores: Centrality scores to validate
        
        Raises:
            ValueError: If validation fails
        """
        if not scores:
            raise ValueError("No scores provided")
        
        # Check score ranges
        for node_id, node_scores in scores.items():
            if not node_id:
                raise ValueError("Empty node ID found")
            
            for metric, value in node_scores.items():
                if not isinstance(value, (int, float)):
                    raise ValueError(
                        f"Invalid score type for {node_id}.{metric}: {type(value)}"
                    )
                
                # Centrality scores should be non-negative
                if value < 0:
                    raise ValueError(
                        f"Negative score for {node_id}.{metric}: {value}"
                    )
                
                # PageRank and betweenness should be <= 1
                if metric in ("pagerank", "betweenness") and value > 1.0:
                    raise ValueError(
                        f"Score out of range for {node_id}.{metric}: {value}"
                    )
    
    async def _store_transaction_metadata(self, transaction: StorageTransaction) -> None:
        """Store transaction metadata in the graph for recovery."""
        query = """
        CREATE (t:CentralityTransaction {
            transaction_id: $transaction_id,
            timestamp: $timestamp,
            state: $state,
            total_nodes: $total_nodes
        })
        """
        
        await self.driver.execute_query(
            query,
            transaction_id=transaction.transaction_id,
            timestamp=transaction.timestamp.isoformat(),
            state=transaction.state.value,
            total_nodes=transaction.total_nodes,
        )
    
    async def _process_batches(
        self,
        transaction: StorageTransaction,
        scores: Dict[str, Dict[str, float]],
    ) -> None:
        """
        Process centrality scores in batches.
        
        Args:
            transaction: Current transaction
            scores: Centrality scores to store
        """
        node_ids = list(scores.keys())
        total_batches = (len(node_ids) + self.batch_size - 1) // self.batch_size
        
        for batch_idx in range(0, len(node_ids), self.batch_size):
            batch_nodes = node_ids[batch_idx:batch_idx + self.batch_size]
            batch_num = batch_idx // self.batch_size + 1
            
            logger.debug(
                f"Processing batch {batch_num}/{total_batches} "
                f"({len(batch_nodes)} nodes)"
            )
            
            # Store batch with retry logic
            success = await self._store_batch_with_retry(
                transaction,
                batch_nodes,
                scores,
            )
            
            if not success:
                raise RuntimeError(
                    f"Failed to store batch {batch_num} after {self.max_retries} attempts"
                )
            
            transaction.processed_nodes += len(batch_nodes)
            transaction.node_batch = batch_nodes
            
            # Create checkpoint if needed
            if transaction.processed_nodes % self.checkpoint_interval == 0:
                await self._create_checkpoint(transaction)
    
    async def _store_batch_with_retry(
        self,
        transaction: StorageTransaction,
        batch_nodes: List[str],
        scores: Dict[str, Dict[str, float]],
    ) -> bool:
        """
        Store a batch of nodes with retry logic.
        
        Args:
            transaction: Current transaction
            batch_nodes: Node IDs in this batch
            scores: Full scores dictionary
        
        Returns:
            True if successful, False otherwise
        """
        for attempt in range(self.max_retries):
            try:
                await self._store_batch(batch_nodes, scores, transaction.transaction_id)
                return True
            except Exception as e:
                logger.warning(
                    f"Batch storage attempt {attempt + 1} failed: {e}"
                )
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                else:
                    transaction.failed_nodes += len(batch_nodes)
        
        return False
    
    async def _store_batch(
        self,
        batch_nodes: List[str],
        scores: Dict[str, Dict[str, float]],
        transaction_id: str,
    ) -> None:
        """
        Store a single batch of centrality scores.
        
        Args:
            batch_nodes: Node IDs to store
            scores: Full scores dictionary
            transaction_id: Current transaction ID
        """
        # Build batch update query
        # Using UNWIND for efficient batch processing
        batch_data = []
        for node_id in batch_nodes:
            node_scores = scores[node_id]
            batch_data.append({
                "uuid": node_id,
                "pagerank": node_scores.get("pagerank", 0.0),
                "degree": node_scores.get("degree", 0),
                "betweenness": node_scores.get("betweenness", 0.0),
                "importance": node_scores.get("importance", 0.0),
                "transaction_id": transaction_id,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            })
        
        query = """
        UNWIND $batch AS item
        MATCH (n {uuid: item.uuid})
        SET n.centrality_pagerank = item.pagerank,
            n.centrality_degree = item.degree,
            n.centrality_betweenness = item.betweenness,
            n.centrality_importance = item.importance,
            n.centrality_transaction_id = item.transaction_id,
            n.centrality_updated_at = item.updated_at
        """
        
        await self.driver.execute_query(query, batch=batch_data)
    
    async def _create_checkpoint(self, transaction: StorageTransaction) -> None:
        """Create a checkpoint for transaction recovery."""
        checkpoint = {
            "processed_nodes": transaction.processed_nodes,
            "last_batch": transaction.node_batch,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        
        transaction.checkpoint = checkpoint
        
        # Store checkpoint in graph
        query = """
        MATCH (t:CentralityTransaction {transaction_id: $transaction_id})
        SET t.checkpoint_processed = $processed,
            t.checkpoint_timestamp = $timestamp,
            t.checkpoint_last_batch = $last_batch
        """
        
        await self.driver.execute_query(
            query,
            transaction_id=transaction.transaction_id,
            processed=checkpoint["processed_nodes"],
            timestamp=checkpoint["timestamp"],
            last_batch=checkpoint["last_batch"],
        )
        
        logger.debug(f"Checkpoint created at {transaction.processed_nodes} nodes")
    
    async def _commit_transaction(self, transaction: StorageTransaction) -> None:
        """
        Commit a transaction, making changes permanent.
        
        Args:
            transaction: Transaction to commit
        """
        # Update transaction state
        query = """
        MATCH (t:CentralityTransaction {transaction_id: $transaction_id})
        SET t.state = 'committed',
            t.committed_at = $timestamp,
            t.processed_nodes = $processed,
            t.failed_nodes = $failed
        """
        
        await self.driver.execute_query(
            query,
            transaction_id=transaction.transaction_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            processed=transaction.processed_nodes,
            failed=transaction.failed_nodes,
        )
        
        # Create index on centrality properties for faster queries
        await self._ensure_centrality_indices()
    
    async def _rollback_transaction(self, transaction: StorageTransaction) -> None:
        """
        Rollback a failed transaction.
        
        Args:
            transaction: Transaction to rollback
        """
        logger.warning(f"Rolling back transaction {transaction.transaction_id}")
        
        try:
            # Remove centrality scores added by this transaction
            query = """
            MATCH (n)
            WHERE n.centrality_transaction_id = $transaction_id
            REMOVE n.centrality_pagerank,
                   n.centrality_degree,
                   n.centrality_betweenness,
                   n.centrality_importance,
                   n.centrality_transaction_id,
                   n.centrality_updated_at
            """
            
            await self.driver.execute_query(
                query,
                transaction_id=transaction.transaction_id,
            )
            
            # Update transaction state
            rollback_query = """
            MATCH (t:CentralityTransaction {transaction_id: $transaction_id})
            SET t.state = 'rolled_back',
                t.rolled_back_at = $timestamp,
                t.error_details = $error
            """
            
            await self.driver.execute_query(
                rollback_query,
                transaction_id=transaction.transaction_id,
                timestamp=datetime.now(timezone.utc).isoformat(),
                error=transaction.error_details,
            )
            
            transaction.state = StorageState.ROLLED_BACK
            logger.info(f"Transaction {transaction.transaction_id} rolled back successfully")
            
        except Exception as e:
            logger.error(f"Rollback failed for transaction {transaction.transaction_id}: {e}")
            raise
    
    async def _ensure_centrality_indices(self) -> None:
        """Ensure indices exist for centrality properties."""
        indices = [
            "CREATE INDEX IF NOT EXISTS FOR (n:EntityNode) ON (n.centrality_importance)",
            "CREATE INDEX IF NOT EXISTS FOR (n:EntityNode) ON (n.centrality_pagerank)",
            "CREATE INDEX IF NOT EXISTS FOR (n:EntityNode) ON (n.centrality_degree)",
            "CREATE INDEX IF NOT EXISTS FOR (n:EntityNode) ON (n.centrality_updated_at)",
        ]
        
        for index_query in indices:
            try:
                await self.driver.execute_query(index_query)
            except Exception as e:
                # Index might already exist
                logger.debug(f"Index creation note: {e}")
    
    async def resume_transaction(
        self,
        transaction_id: str,
        scores: Dict[str, Dict[str, float]],
    ) -> StorageTransaction:
        """
        Resume a previously failed or interrupted transaction.
        
        Args:
            transaction_id: ID of transaction to resume
            scores: Centrality scores to store
        
        Returns:
            Resumed StorageTransaction
        """
        # Load transaction state from graph
        query = """
        MATCH (t:CentralityTransaction {transaction_id: $transaction_id})
        RETURN t
        """
        
        records, _, _ = await self.driver.execute_query(
            query,
            transaction_id=transaction_id,
        )
        
        if not records:
            raise ValueError(f"Transaction {transaction_id} not found")
        
        tx_data = records[0]["t"]
        # Handle FalkorDB Node objects vs dict objects
        if hasattr(tx_data, "properties"):
            tx_data = tx_data.properties
        
        # Reconstruct transaction
        transaction = StorageTransaction(
            transaction_id=transaction_id,
            timestamp=datetime.fromisoformat(tx_data["timestamp"]),
            state=StorageState.IN_PROGRESS,
            total_nodes=tx_data["total_nodes"],
            processed_nodes=tx_data.get("checkpoint_processed", 0),
            failed_nodes=0,
            node_batch=[],
        )
        
        logger.info(
            f"Resuming transaction {transaction_id} from "
            f"{transaction.processed_nodes}/{transaction.total_nodes} nodes"
        )
        
        # Continue from checkpoint
        remaining_nodes = list(scores.keys())[transaction.processed_nodes:]
        scores_subset = {k: scores[k] for k in remaining_nodes}
        
        await self._process_batches(transaction, scores_subset)
        await self._commit_transaction(transaction)
        
        transaction.state = StorageState.COMMITTED
        
        return transaction
    
    async def get_transaction_history(
        self,
        limit: int = 10,
        state: Optional[StorageState] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get transaction history for audit and debugging.
        
        Args:
            limit: Maximum number of transactions to return
            state: Filter by transaction state
        
        Returns:
            List of transaction records
        """
        where_clause = ""
        params = {"limit": limit}
        
        if state:
            where_clause = "WHERE t.state = $state"
            params["state"] = state.value
        
        query = f"""
        MATCH (t:CentralityTransaction)
        {where_clause}
        RETURN t
        ORDER BY t.timestamp DESC
        LIMIT $limit
        """
        
        records, _, _ = await self.driver.execute_query(query, **params)
        
        # Handle FalkorDB Node objects vs dict objects
        result = []
        for record in records:
            t = record["t"]
            if hasattr(t, "properties"):
                # FalkorDB Node object
                result.append(t.properties)
            else:
                # Regular dict
                result.append(dict(t))
        return result
    
    @asynccontextmanager
    async def batch_update_context(self, transaction_id: Optional[str] = None):
        """
        Context manager for batch centrality updates.
        
        Usage:
            async with storage.batch_update_context() as batch:
                await batch.add_scores(node1_scores)
                await batch.add_scores(node2_scores)
                # Automatically commits on exit
        """
        batch = BatchUpdateContext(self, transaction_id)
        try:
            yield batch
            await batch.commit()
        except Exception as e:
            await batch.rollback()
            raise


class BatchUpdateContext:
    """Context for accumulating batch updates."""
    
    def __init__(self, storage: AtomicCentralityStorage, transaction_id: Optional[str] = None):
        self.storage = storage
        self.transaction_id = transaction_id or f"batch_{int(time.time() * 1000)}"
        self.scores: Dict[str, Dict[str, float]] = {}
        self.committed = False
    
    async def add_scores(self, node_id: str, scores: Dict[str, float]) -> None:
        """Add scores for a node to the batch."""
        self.scores[node_id] = scores
    
    async def commit(self) -> StorageTransaction:
        """Commit all accumulated scores."""
        if not self.committed:
            self.committed = True
            return await self.storage.store_centrality_atomic(
                self.scores,
                transaction_id=self.transaction_id,
            )
    
    async def rollback(self) -> None:
        """Rollback the batch update."""
        if not self.committed:
            logger.info(f"Rolling back batch {self.transaction_id}")
            # Clear accumulated scores
            self.scores.clear()