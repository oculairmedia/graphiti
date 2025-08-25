"""
Sync orchestration engine for Neo4j-FalkorDB synchronization.

This module coordinates the extraction from Neo4j and loading into FalkorDB,
managing the sync process with error handling and progress tracking.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

from extractors.neo4j_extractor import Neo4jExtractor, ExtractionStats, SyncMetadata
from extractors.falkordb_extractor import FalkorDBExtractor
from loaders.falkordb_loader import FalkorDBLoader, LoadingStats
from loaders.neo4j_loader import Neo4jLoader

logger = logging.getLogger(__name__)


class SyncMode(Enum):
    """Sync operation modes."""
    INCREMENTAL = "incremental"
    FULL = "full" 
    DIFFERENTIAL = "differential"
    REVERSE_FULL = "reverse_full"                # FalkorDB → Neo4j full sync
    REVERSE_INCREMENTAL = "reverse_incremental"  # FalkorDB → Neo4j incremental sync


class SyncStatus(Enum):
    """Sync operation status."""
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class SyncOperationStats:
    """Comprehensive statistics for sync operation."""
    mode: SyncMode
    status: SyncStatus = SyncStatus.IDLE
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: float = 0.0
    
    # Extraction stats
    extraction_stats: Optional[ExtractionStats] = None
    
    # Loading stats  
    loading_stats: Optional[LoadingStats] = None
    
    # Overall progress
    total_items_processed: int = 0
    total_items_failed: int = 0
    success_rate: float = 0.0
    
    # Error tracking
    errors: List[str] = field(default_factory=list)
    
    def calculate_metrics(self):
        """Calculate derived metrics."""
        if self.started_at and self.completed_at:
            self.duration_seconds = (self.completed_at - self.started_at).total_seconds()
            
        if self.extraction_stats and self.loading_stats:
            # Total items from extraction
            total_extracted = (
                self.extraction_stats.entity_nodes +
                self.extraction_stats.episodic_nodes + 
                self.extraction_stats.community_nodes +
                self.extraction_stats.entity_edges +
                self.extraction_stats.episodic_edges
            )
            
            # Total items loaded
            total_loaded = (
                self.loading_stats.entity_nodes_loaded +
                self.loading_stats.episodic_nodes_loaded +
                self.loading_stats.community_nodes_loaded +
                self.loading_stats.entity_edges_loaded +
                self.loading_stats.episodic_edges_loaded
            )
            
            self.total_items_processed = total_extracted
            self.total_items_failed = total_extracted - total_loaded + self.loading_stats.errors
            
            if total_extracted > 0:
                self.success_rate = total_loaded / total_extracted
            else:
                self.success_rate = 1.0


class SyncOrchestrator:
    """
    Orchestrates synchronization between Neo4j and FalkorDB.
    
    Features:
    - Multiple sync modes (incremental, full, differential)
    - Progress tracking and statistics
    - Error handling and recovery
    - Configurable sync intervals
    - Health monitoring
    """
    
    def __init__(
        self,
        neo4j_config: Dict[str, Any],
        falkordb_config: Dict[str, Any],
        batch_size: int = 1000,
        sync_interval_seconds: int = 300,
        max_retries: int = 3,
        retry_delay_seconds: int = 30,
        sync_direction: str = "forward",
        enable_reverse_incremental: bool = False,
        auto_recovery: bool = True,
    ):
        """
        Initialize sync orchestrator.
        
        Args:
            neo4j_config: Neo4j connection configuration
            falkordb_config: FalkorDB connection configuration  
            batch_size: Batch size for processing
            sync_interval_seconds: Interval between automatic syncs
            max_retries: Maximum retry attempts for failed operations
            retry_delay_seconds: Delay between retry attempts
            sync_direction: Sync direction ("forward" for Neo4j→FalkorDB, "reverse" for FalkorDB→Neo4j)
            enable_reverse_incremental: Enable reverse incremental sync
            auto_recovery: Enable automatic disaster recovery
        """
        self.neo4j_config = neo4j_config
        self.falkordb_config = falkordb_config
        self.batch_size = batch_size
        self.sync_interval_seconds = sync_interval_seconds
        self.max_retries = max_retries
        self.retry_delay_seconds = retry_delay_seconds
        self.sync_direction = sync_direction
        self.enable_reverse_incremental = enable_reverse_incremental
        self.auto_recovery = auto_recovery
        
        # State tracking
        self.last_sync_timestamp: Optional[datetime] = None
        self.current_operation: Optional[SyncOperationStats] = None
        self.sync_history: List[SyncOperationStats] = []
        self.is_running = False
        self._stop_requested = False
        
        # Change detection for continuous sync
        self.last_source_counts: Dict[str, int] = {}
        self.last_target_counts: Dict[str, int] = {}
        
        # Background task
        self._sync_task: Optional[asyncio.Task] = None
        
    async def start_continuous_sync(self) -> None:
        """Start continuous sync process."""
        if self.is_running:
            logger.warning("Sync orchestrator is already running")
            return
            
        self.is_running = True
        self._stop_requested = False
        
        logger.info(f"Starting continuous sync with {self.sync_interval_seconds}s interval")
        
        # Start background sync task
        self._sync_task = asyncio.create_task(self._continuous_sync_loop())
        
    async def stop_continuous_sync(self) -> None:
        """Stop continuous sync process."""
        if not self.is_running:
            return
            
        logger.info("Stopping continuous sync")
        self._stop_requested = True
        self.is_running = False
        
        # Cancel background task
        if self._sync_task:
            self._sync_task.cancel()
            try:
                await self._sync_task
            except asyncio.CancelledError:
                pass
            self._sync_task = None
            
    async def _continuous_sync_loop(self) -> None:
        """Background task for continuous sync operations."""
        while not self._stop_requested:
            try:
                # Check for data changes before deciding sync method
                changes_detected, current_source_counts, current_target_counts = await self._detect_data_changes()
                
                # Perform sync based on configured direction
                if self.sync_direction == "reverse" and self.enable_reverse_incremental:
                    if changes_detected:
                        logger.info("Data changes detected - performing full reverse sync (FalkorDB → Neo4j)")
                        # Use sync_reverse_incremental with no timestamp to get all data
                        stats = await self.sync_reverse_incremental(since_timestamp=None)
                        
                        # Update stored counts only after successful sync
                        if stats.status == SyncStatus.COMPLETED:
                            self.last_source_counts = current_source_counts
                            self.last_target_counts = current_target_counts
                            logger.info(f"Sync completed successfully - updated stored counts")
                            
                            # Verify sync success by checking final alignment
                            _, final_source_counts, final_target_counts = await self._detect_data_changes()
                            final_source_total = sum(final_source_counts.values())
                            final_target_total = sum(final_target_counts.values())
                            
                            if final_source_total == final_target_total:
                                logger.info(f"✅ Databases fully aligned: {final_source_total} items each")
                            else:
                                logger.warning(f"⚠️  Databases still misaligned: source={final_source_total}, target={final_target_total}")
                        else:
                            logger.error(f"Sync failed with status: {stats.status}")
                    else:
                        logger.debug("No data changes detected - skipping sync")
                elif self.sync_direction == "forward":
                    if changes_detected:
                        logger.info("Data changes detected - performing incremental sync (Neo4j → FalkorDB)")
                        stats = await self.sync_incremental()
                        
                        # Update stored counts only after successful sync
                        if stats.status == SyncStatus.COMPLETED:
                            self.last_source_counts = current_source_counts
                            self.last_target_counts = current_target_counts
                            logger.info(f"Forward sync completed successfully - updated stored counts")
                    else:
                        logger.debug("No data changes detected - skipping sync")
                else:
                    logger.warning(f"No sync performed - direction: {self.sync_direction}, reverse_incremental: {self.enable_reverse_incremental}")
                
                # Wait for next sync interval
                await asyncio.sleep(self.sync_interval_seconds)
                
            except asyncio.CancelledError:
                logger.info("Continuous sync cancelled")
                break
            except Exception as e:
                logger.error(f"Error in continuous sync loop: {e}")
                # Wait before retrying
                await asyncio.sleep(self.retry_delay_seconds)
    
    async def _detect_data_changes(self) -> Tuple[bool, Dict[str, int], Dict[str, int]]:
        """
        Detect if data has changed since last sync by comparing node/edge counts.
        Similar to how the Rust visualizer detects changes.
        
        Returns:
            Tuple of (changes_detected, current_source_counts, current_target_counts)
        """
        try:
            if self.sync_direction == "reverse":
                # Check FalkorDB (source) and Neo4j (target) counts
                source_extractor = FalkorDBExtractor(
                    host=self.falkordb_config['host'],
                    port=self.falkordb_config['port'],
                    username=self.falkordb_config.get('username'),
                    password=self.falkordb_config.get('password'),
                    database=self.falkordb_config['database']
                )
                
                async with source_extractor:
                    source_metadata = await source_extractor.get_sync_metadata()
                    current_source_counts = {
                        'entity_nodes': source_metadata.total_entity_nodes,
                        'episodic_nodes': source_metadata.total_episodic_nodes,
                        'community_nodes': source_metadata.total_community_nodes,
                        'entity_edges': source_metadata.total_entity_edges,
                        'episodic_edges': source_metadata.total_episodic_edges,
                    }
                
                neo4j_loader_config = {k: v for k, v in self.neo4j_config.items() if k != 'pool_size'}
                target_loader = Neo4jLoader(**neo4j_loader_config)
                
                async with target_loader:
                    current_target_counts = await target_loader.get_database_statistics()
                
            else:
                # Forward sync: Neo4j (source) → FalkorDB (target)
                source_extractor = Neo4jExtractor(**self.neo4j_config)
                
                async with source_extractor:
                    source_metadata = await source_extractor.get_sync_metadata()
                    current_source_counts = {
                        'entity_nodes': source_metadata.total_entity_nodes,
                        'episodic_nodes': source_metadata.total_episodic_nodes,
                        'community_nodes': source_metadata.total_community_nodes,
                        'entity_edges': source_metadata.total_entity_edges,
                        'episodic_edges': source_metadata.total_episodic_edges,
                    }
                
                target_loader = FalkorDBLoader(**self.falkordb_config)
                async with target_loader:
                    target_metadata = await target_loader.get_sync_metadata()
                    current_target_counts = {
                        'entity_nodes': target_metadata.total_entity_nodes,
                        'episodic_nodes': target_metadata.total_episodic_nodes,
                        'community_nodes': target_metadata.total_community_nodes,
                        'entity_edges': target_metadata.total_entity_edges,
                        'episodic_edges': target_metadata.total_episodic_edges,
                    }
            
            # Check if sync is needed by comparing source vs target directly
            source_total = sum(current_source_counts.values())
            target_total = sum(current_target_counts.values())
            
            # Also check individual metrics for more granular detection
            counts_match = all(
                current_source_counts.get(key, 0) == current_target_counts.get(key, 0)
                for key in set(current_source_counts.keys()) | set(current_target_counts.keys())
            )
            
            changes_detected = not counts_match or source_total != target_total
            
            if changes_detected:
                logger.info(f"Sync needed - databases not aligned:")
                logger.info(f"  Source (FalkorDB): {current_source_counts} (total: {source_total})")
                logger.info(f"  Target (Neo4j): {current_target_counts} (total: {target_total})")
            else:
                logger.debug(f"Databases aligned - no sync needed")
            
            return changes_detected, current_source_counts, current_target_counts
            
        except Exception as e:
            logger.error(f"Failed to detect data changes: {e}")
            # On error, assume changes to be safe and return empty counts
            return True, {}, {}
    
    async def check_disaster_recovery_needed(self) -> bool:
        """
        Check if disaster recovery is needed (FalkorDB is empty but Neo4j has data).
        
        Returns:
            True if disaster recovery is needed
        """
        try:
            # Check FalkorDB node count
            falkor_extractor = FalkorDBExtractor(
                host=self.falkordb_config['host'],
                port=self.falkordb_config['port'],
                username=self.falkordb_config.get('username'),
                password=self.falkordb_config.get('password'),
                database=self.falkordb_config['database']
            )
            
            falkor_metadata = await falkor_extractor.get_sync_metadata()
            falkor_node_count = falkor_metadata.total_entity_nodes + falkor_metadata.total_episodic_nodes + falkor_metadata.total_community_nodes
            
            # Check Neo4j node count
            neo4j_extractor = Neo4jExtractor(
                uri=self.neo4j_config['uri'],
                user=self.neo4j_config['user'], 
                password=self.neo4j_config['password'],
                database=self.neo4j_config['database'],
                pool_size=self.neo4j_config.get('pool_size', 10)
            )
            
            neo4j_metadata = await neo4j_extractor.get_sync_metadata()
            neo4j_node_count = neo4j_metadata.total_entity_nodes + neo4j_metadata.total_episodic_nodes + neo4j_metadata.total_community_nodes
            
            # Disaster recovery needed if FalkorDB is empty but Neo4j has data
            needs_recovery = falkor_node_count < 10 and neo4j_node_count > 100
            
            if needs_recovery:
                logger.warning(f"Disaster recovery needed: FalkorDB has {falkor_node_count} nodes, Neo4j has {neo4j_node_count} nodes")
            else:
                logger.info(f"No disaster recovery needed: FalkorDB has {falkor_node_count} nodes, Neo4j has {neo4j_node_count} nodes")
            
            return needs_recovery
            
        except Exception as e:
            logger.error(f"Failed to check disaster recovery status: {e}")
            return False
                
    async def sync_full(self, clear_cache: bool = True) -> SyncOperationStats:
        """
        Perform full synchronization from Neo4j to FalkorDB.
        
        Args:
            clear_cache: Whether to clear FalkorDB cache before sync
            
        Returns:
            Statistics for the sync operation
        """
        operation_stats = SyncOperationStats(
            mode=SyncMode.FULL,
            started_at=datetime.utcnow()
        )
        
        self.current_operation = operation_stats
        operation_stats.status = SyncStatus.RUNNING
        
        try:
            logger.info("Starting full synchronization")
            
            # Initialize connections
            async with Neo4jExtractor(**self.neo4j_config, batch_size=self.batch_size) as extractor:
                async with FalkorDBLoader(**self.falkordb_config, batch_size=self.batch_size) as loader:
                    
                    # Clear cache if requested
                    if clear_cache:
                        logger.info("Clearing FalkorDB cache")
                        await loader.clear_all_data()
                        
                    # Create indices
                    logger.info("Creating FalkorDB indices")
                    await loader.create_indices()
                    
                    # Extract all data from Neo4j
                    logger.info("Extracting data from Neo4j")
                    data_generator, extraction_stats = await extractor.extract_all_data()
                    
                    # Initialize loading stats
                    loading_stats = LoadingStats()
                    start_time = asyncio.get_event_loop().time()
                    
                    # Process data in batches
                    async for data_type, batch in data_generator:
                        try:
                            loaded_count = await loader.load_batch(data_type, batch)
                            
                            # Update loading stats
                            if data_type == "entity_nodes":
                                loading_stats.entity_nodes_loaded += loaded_count
                            elif data_type == "episodic_nodes":
                                loading_stats.episodic_nodes_loaded += loaded_count
                            elif data_type == "community_nodes":
                                loading_stats.community_nodes_loaded += loaded_count
                            elif data_type == "entity_edges":
                                loading_stats.entity_edges_loaded += loaded_count
                            elif data_type == "episodic_edges":
                                loading_stats.episodic_edges_loaded += loaded_count
                                
                            if loaded_count < len(batch):
                                loading_stats.errors += len(batch) - loaded_count
                                
                            logger.debug(f"Processed {data_type}: {loaded_count}/{len(batch)} loaded")
                            
                        except Exception as e:
                            error_msg = f"Failed to load {data_type} batch: {e}"
                            logger.error(error_msg)
                            operation_stats.errors.append(error_msg)
                            loading_stats.errors += len(batch)
                            
                    # Calculate loading time
                    end_time = asyncio.get_event_loop().time()
                    loading_stats.loading_time_seconds = end_time - start_time
                    
                    # Store stats
                    operation_stats.extraction_stats = extraction_stats
                    operation_stats.loading_stats = loading_stats
                    
            # Update sync timestamp
            self.last_sync_timestamp = datetime.utcnow()
            operation_stats.completed_at = self.last_sync_timestamp
            operation_stats.status = SyncStatus.COMPLETED
            
            logger.info(f"Full sync completed in {operation_stats.duration_seconds:.2f}s")
            
        except Exception as e:
            error_msg = f"Full sync failed: {e}"
            logger.error(error_msg)
            operation_stats.errors.append(error_msg)
            operation_stats.status = SyncStatus.FAILED
            operation_stats.completed_at = datetime.utcnow()
            
        finally:
            # Calculate final metrics
            operation_stats.calculate_metrics()
            
            # Add to history
            self.sync_history.append(operation_stats)
            self.current_operation = None
            
        return operation_stats
        
    async def sync_incremental(self) -> SyncOperationStats:
        """
        Perform incremental synchronization from Neo4j to FalkorDB.
        
        Returns:
            Statistics for the sync operation
        """
        operation_stats = SyncOperationStats(
            mode=SyncMode.INCREMENTAL,
            started_at=datetime.utcnow()
        )
        
        self.current_operation = operation_stats
        operation_stats.status = SyncStatus.RUNNING
        
        try:
            # Determine since timestamp
            since_timestamp = self.last_sync_timestamp
            if since_timestamp is None:
                logger.info("No previous sync timestamp, performing full sync")
                return await self.sync_full(clear_cache=False)
                
            logger.info(f"Starting incremental sync since {since_timestamp}")
            
            # Initialize connections
            async with Neo4jExtractor(**self.neo4j_config, batch_size=self.batch_size) as extractor:
                async with FalkorDBLoader(**self.falkordb_config, batch_size=self.batch_size) as loader:
                    
                    # Extract incremental data from Neo4j
                    data_generator, extraction_stats = await extractor.extract_all_data(since_timestamp)
                    
                    # Initialize loading stats
                    loading_stats = LoadingStats()
                    start_time = asyncio.get_event_loop().time()
                    
                    # Process data in batches
                    async for data_type, batch in data_generator:
                        try:
                            loaded_count = await loader.load_batch(data_type, batch)
                            
                            # Update loading stats
                            if data_type == "entity_nodes":
                                loading_stats.entity_nodes_loaded += loaded_count
                            elif data_type == "episodic_nodes":
                                loading_stats.episodic_nodes_loaded += loaded_count
                            elif data_type == "community_nodes":
                                loading_stats.community_nodes_loaded += loaded_count
                            elif data_type == "entity_edges":
                                loading_stats.entity_edges_loaded += loaded_count
                            elif data_type == "episodic_edges":
                                loading_stats.episodic_edges_loaded += loaded_count
                                
                            if loaded_count < len(batch):
                                loading_stats.errors += len(batch) - loaded_count
                                
                            logger.debug(f"Processed {data_type}: {loaded_count}/{len(batch)} loaded")
                            
                        except Exception as e:
                            error_msg = f"Failed to load {data_type} batch: {e}"
                            logger.error(error_msg)
                            operation_stats.errors.append(error_msg)
                            loading_stats.errors += len(batch)
                            
                    # Calculate loading time
                    end_time = asyncio.get_event_loop().time()
                    loading_stats.loading_time_seconds = end_time - start_time
                    
                    # Store stats
                    operation_stats.extraction_stats = extraction_stats
                    operation_stats.loading_stats = loading_stats
                    
            # Update sync timestamp
            self.last_sync_timestamp = datetime.utcnow()
            operation_stats.completed_at = self.last_sync_timestamp
            operation_stats.status = SyncStatus.COMPLETED
            
            total_items = (
                operation_stats.extraction_stats.entity_nodes +
                operation_stats.extraction_stats.episodic_nodes + 
                operation_stats.extraction_stats.community_nodes +
                operation_stats.extraction_stats.entity_edges +
                operation_stats.extraction_stats.episodic_edges
            )
            
            logger.info(f"Incremental sync completed: {total_items} items in {operation_stats.duration_seconds:.2f}s")
            
        except Exception as e:
            error_msg = f"Incremental sync failed: {e}"
            logger.error(error_msg)
            operation_stats.errors.append(error_msg)
            operation_stats.status = SyncStatus.FAILED
            operation_stats.completed_at = datetime.utcnow()
            
        finally:
            # Calculate final metrics
            operation_stats.calculate_metrics()
            
            # Add to history
            self.sync_history.append(operation_stats)
            self.current_operation = None
            
        return operation_stats
        
    async def sync_differential(self) -> SyncOperationStats:
        """
        Perform differential synchronization by comparing data counts.
        
        Returns:
            Statistics for the sync operation
        """
        operation_stats = SyncOperationStats(
            mode=SyncMode.DIFFERENTIAL,
            started_at=datetime.utcnow()
        )
        
        self.current_operation = operation_stats
        operation_stats.status = SyncStatus.RUNNING
        
        try:
            logger.info("Starting differential synchronization")
            
            # Initialize connections
            async with Neo4jExtractor(**self.neo4j_config, batch_size=self.batch_size) as extractor:
                async with FalkorDBLoader(**self.falkordb_config, batch_size=self.batch_size) as loader:
                    
                    # Get metadata from both databases
                    neo4j_metadata = await extractor.get_sync_metadata()
                    falkor_stats = await loader.get_cache_statistics()
                    
                    # Compare counts
                    neo4j_total = neo4j_metadata.total_nodes + neo4j_metadata.total_edges
                    falkor_total = sum(falkor_stats.values())
                    
                    logger.info(f"Neo4j: {neo4j_total} items, FalkorDB: {falkor_total} items")
                    
                    if neo4j_total != falkor_total:
                        logger.info("Count mismatch detected, performing full sync")
                        return await self.sync_full(clear_cache=True)
                    else:
                        logger.info("Counts match, no sync needed")
                        operation_stats.status = SyncStatus.COMPLETED
                        operation_stats.completed_at = datetime.utcnow()
                        
        except Exception as e:
            error_msg = f"Differential sync failed: {e}"
            logger.error(error_msg)
            operation_stats.errors.append(error_msg)
            operation_stats.status = SyncStatus.FAILED
            operation_stats.completed_at = datetime.utcnow()
            
        finally:
            # Calculate final metrics
            operation_stats.calculate_metrics()
            
            # Add to history
            self.sync_history.append(operation_stats)
            self.current_operation = None
            
        return operation_stats
        
    async def get_health_status(self) -> Dict[str, Any]:
        """
        Get health status of the sync orchestrator.
        
        Returns:
            Dictionary with health information
        """
        status = {
            "is_running": self.is_running,
            "last_sync_timestamp": self.last_sync_timestamp,
            "current_operation": None,
            "recent_operations": []
        }
        
        if self.current_operation:
            status["current_operation"] = {
                "mode": self.current_operation.mode.value,
                "status": self.current_operation.status.value,
                "started_at": self.current_operation.started_at,
                "duration_seconds": (datetime.utcnow() - self.current_operation.started_at).total_seconds() if self.current_operation.started_at else 0
            }
            
        # Include recent operations (last 10)
        for operation in self.sync_history[-10:]:
            status["recent_operations"].append({
                "mode": operation.mode.value,
                "status": operation.status.value,
                "started_at": operation.started_at,
                "completed_at": operation.completed_at,
                "duration_seconds": operation.duration_seconds,
                "total_items_processed": operation.total_items_processed,
                "success_rate": operation.success_rate,
                "error_count": len(operation.errors)
            })
            
        return status
        
    async def get_sync_statistics(self) -> Dict[str, Any]:
        """
        Get comprehensive sync statistics.
        
        Returns:
            Dictionary with sync statistics
        """
        if not self.sync_history:
            return {"total_operations": 0}
            
        # Calculate aggregate statistics
        total_operations = len(self.sync_history)
        successful_operations = sum(1 for op in self.sync_history if op.status == SyncStatus.COMPLETED)
        failed_operations = sum(1 for op in self.sync_history if op.status == SyncStatus.FAILED)
        
        # Calculate average duration
        completed_ops = [op for op in self.sync_history if op.status == SyncStatus.COMPLETED]
        avg_duration = sum(op.duration_seconds for op in completed_ops) / len(completed_ops) if completed_ops else 0
        
        # Calculate total items processed
        total_items = sum(op.total_items_processed for op in self.sync_history)
        
        return {
            "total_operations": total_operations,
            "successful_operations": successful_operations,
            "failed_operations": failed_operations,
            "success_rate": successful_operations / total_operations if total_operations > 0 else 0,
            "average_duration_seconds": avg_duration,
            "total_items_processed": total_items,
            "last_sync_timestamp": self.last_sync_timestamp,
        }
        
    async def _validate_sync_safety(
        self, 
        source_stats: Dict[str, int], 
        target_stats: Dict[str, int],
        safety_threshold: float = 0.5
    ) -> Tuple[bool, str]:
        """
        Validate sync safety to prevent catastrophic data loss.
        
        Args:
            source_stats: Statistics from source database
            target_stats: Statistics from target database
            safety_threshold: Maximum allowed reduction ratio (default 0.5 = 50%)
            
        Returns:
            Tuple of (is_safe, reason)
        """
        # Calculate total node counts
        source_total = sum(v for k, v in source_stats.items() if k.endswith('_nodes'))
        target_total = sum(v for k, v in target_stats.items() if k.endswith('_nodes'))
        
        # If target is empty, allow any sync
        if target_total == 0:
            return True, "Target database is empty - sync allowed"
            
        # If source is empty, this would delete everything - block unless explicitly allowed
        if source_total == 0:
            return False, f"Source database is empty but target has {target_total} nodes - would delete all data"
            
        # Calculate reduction percentage
        reduction_ratio = (target_total - source_total) / target_total
        
        if reduction_ratio > safety_threshold:
            return False, (f"Safety check failed: Sync would reduce node count by "
                          f"{reduction_ratio*100:.1f}% ({target_total} → {source_total}), "
                          f"exceeding {safety_threshold*100:.1f}% threshold")
        
        if reduction_ratio > 0.1:  # Warn for reductions over 10%
            logger.warning(f"Significant data reduction detected: {reduction_ratio*100:.1f}% "
                          f"({target_total} → {source_total})")
                          
        return True, f"Sync safety validated: {reduction_ratio*100:.1f}% change ({target_total} → {source_total})"
        
    async def sync_reverse_full(
        self, 
        clear_target: bool = False,
        force_override_safety: bool = False,
        safety_threshold: float = 0.5
    ) -> SyncOperationStats:
        """
        Perform full reverse sync from FalkorDB to Neo4j with safety checks.
        
        Args:
            clear_target: Whether to clear Neo4j before sync
            force_override_safety: Override safety checks (use with caution)
            safety_threshold: Safety threshold for data reduction (default 50%)
            
        Returns:
            Statistics for the sync operation
        """
        operation_stats = SyncOperationStats(
            mode=SyncMode.REVERSE_FULL,
            started_at=datetime.utcnow()
        )
        
        self.current_operation = operation_stats
        operation_stats.status = SyncStatus.RUNNING
        
        try:
            logger.info("Starting reverse full synchronization (FalkorDB → Neo4j)")
            
            # Initialize connections  
            # Filter out pool_size for Neo4jLoader (doesn't support it)
            neo4j_loader_config = {k: v for k, v in self.neo4j_config.items() if k != 'pool_size'}
            async with FalkorDBExtractor(**self.falkordb_config, batch_size=self.batch_size) as extractor:
                async with Neo4jLoader(**neo4j_loader_config, batch_size=self.batch_size) as loader:
                    
                    # Get statistics for safety check
                    if not force_override_safety:
                        logger.info("Performing safety validation")
                        source_metadata = await extractor.get_sync_metadata()
                        target_stats = await loader.get_database_statistics()
                        
                        source_stats = {
                            "entity_nodes": source_metadata.total_entity_nodes,
                            "episodic_nodes": source_metadata.total_episodic_nodes,
                            "community_nodes": source_metadata.total_community_nodes,
                            "entity_edges": source_metadata.total_entity_edges,
                            "episodic_edges": source_metadata.total_episodic_edges,
                        }
                        
                        is_safe, reason = await self._validate_sync_safety(source_stats, target_stats, safety_threshold)
                        
                        if not is_safe:
                            operation_stats.status = SyncStatus.FAILED
                            operation_stats.errors.append(f"Safety check failed: {reason}")
                            logger.error(f"Reverse sync blocked: {reason}")
                            raise RuntimeError(f"Reverse sync safety check failed: {reason}")
                        else:
                            logger.info(f"Safety check passed: {reason}")
                    
                    # Clear target if requested
                    if clear_target:
                        logger.info("Clearing Neo4j database")
                        await loader.clear_all_data()
                        
                    # Create indices
                    logger.info("Creating Neo4j indices")
                    await loader.create_indices()
                    
                    # Extract all data from FalkorDB
                    logger.info("Extracting data from FalkorDB")
                    data_generator, extraction_stats = await extractor.extract_all_data()
                    
                    # Initialize loading stats
                    loading_stats = LoadingStats()
                    start_time = asyncio.get_event_loop().time()
                    
                    # Process data in batches
                    async for data_type, batch in data_generator:
                        try:
                            loaded_count = await loader.load_batch(data_type, batch)
                            
                            # Update loading stats
                            if data_type == "entity_nodes":
                                loading_stats.entity_nodes_loaded += loaded_count
                            elif data_type == "episodic_nodes":
                                loading_stats.episodic_nodes_loaded += loaded_count
                            elif data_type == "community_nodes":
                                loading_stats.community_nodes_loaded += loaded_count
                            elif data_type == "entity_edges":
                                loading_stats.entity_edges_loaded += loaded_count
                            elif data_type == "episodic_edges":
                                loading_stats.episodic_edges_loaded += loaded_count
                                
                            logger.debug(f"Loaded batch of {loaded_count} {data_type}")
                            
                        except Exception as e:
                            loading_stats.errors += 1
                            logger.error(f"Failed to load batch of {data_type}: {e}")
                            
                    # Calculate final loading time
                    end_time = asyncio.get_event_loop().time()
                    loading_stats.loading_time_seconds = end_time - start_time
                    
                    # Update operation statistics
                    operation_stats.extraction_stats = extraction_stats
                    operation_stats.loading_stats = loading_stats
                    operation_stats.status = SyncStatus.COMPLETED
                    operation_stats.completed_at = datetime.utcnow()
                    operation_stats.calculate_metrics()
                    
                    logger.info(f"Reverse full sync completed: {operation_stats.total_items_processed} items "
                               f"in {operation_stats.duration_seconds:.2f}s "
                               f"({operation_stats.success_rate:.1%} success rate)")
                    
        except Exception as e:
            operation_stats.status = SyncStatus.FAILED
            operation_stats.completed_at = datetime.utcnow()
            operation_stats.errors.append(f"Reverse full sync failed: {str(e)}")
            logger.error(f"Reverse full sync failed: {e}")
            
        finally:
            # Update sync timestamp and history
            if operation_stats.status == SyncStatus.COMPLETED:
                self.last_sync_timestamp = operation_stats.completed_at
                
            self.sync_history.append(operation_stats)
            self.current_operation = None
            
        return operation_stats
        
    async def sync_reverse_incremental(
        self, 
        since_timestamp: Optional[datetime] = None,
        safety_threshold: float = 0.5
    ) -> SyncOperationStats:
        """
        Perform incremental reverse sync from FalkorDB to Neo4j.
        
        Args:
            since_timestamp: Only sync data modified after this timestamp
            safety_threshold: Safety threshold for data reduction
            
        Returns:
            Statistics for the sync operation
        """
        operation_stats = SyncOperationStats(
            mode=SyncMode.REVERSE_INCREMENTAL,
            started_at=datetime.utcnow()
        )
        
        self.current_operation = operation_stats
        operation_stats.status = SyncStatus.RUNNING
        
        # Use last sync timestamp if none provided
        if since_timestamp is None:
            since_timestamp = self.last_sync_timestamp
            
        try:
            logger.info(f"Starting reverse incremental sync (FalkorDB → Neo4j) since {since_timestamp}")
            logger.info(f"FalkorDB config: {self.falkordb_config}")
            logger.info(f"Neo4j config: {self.neo4j_config}")
            
            # Filter out pool_size for Neo4jLoader (doesn't support it)
            neo4j_loader_config = {k: v for k, v in self.neo4j_config.items() if k != 'pool_size'}
            async with FalkorDBExtractor(**self.falkordb_config, batch_size=self.batch_size) as extractor:
                logger.info(f"Connected to FalkorDB with database: {extractor.database}")
                async with Neo4jLoader(**neo4j_loader_config, batch_size=self.batch_size) as loader:
                    logger.info(f"Connected to Neo4j")
                    
                    # Get current counts for comparison
                    extractor_stats = await extractor.get_sync_metadata()
                    logger.info(f"FalkorDB stats: {extractor_stats}")
                    
                    loader_stats = await loader.get_database_statistics()
                    logger.info(f"Neo4j stats: {loader_stats}")
                    
                    
                    # Extract incremental data from FalkorDB
                    data_generator, extraction_stats = await extractor.extract_all_data(since_timestamp)
                    
                    # Initialize loading stats
                    loading_stats = LoadingStats()
                    start_time = asyncio.get_event_loop().time()
                    
                    # Process data in batches
                    async for data_type, batch in data_generator:
                        try:
                            loaded_count = await loader.load_batch(data_type, batch)
                            
                            # Update loading stats
                            if data_type == "entity_nodes":
                                loading_stats.entity_nodes_loaded += loaded_count
                            elif data_type == "episodic_nodes":
                                loading_stats.episodic_nodes_loaded += loaded_count
                            elif data_type == "community_nodes":
                                loading_stats.community_nodes_loaded += loaded_count
                            elif data_type == "entity_edges":
                                loading_stats.entity_edges_loaded += loaded_count
                            elif data_type == "episodic_edges":
                                loading_stats.episodic_edges_loaded += loaded_count
                                
                            logger.debug(f"Loaded batch of {loaded_count} {data_type}")
                            
                        except Exception as e:
                            loading_stats.errors += 1
                            logger.error(f"Failed to load batch of {data_type}: {e}")
                            
                    # Calculate final loading time
                    end_time = asyncio.get_event_loop().time()
                    loading_stats.loading_time_seconds = end_time - start_time
                    
                    # Update operation statistics
                    operation_stats.extraction_stats = extraction_stats
                    operation_stats.loading_stats = loading_stats
                    operation_stats.status = SyncStatus.COMPLETED
                    operation_stats.completed_at = datetime.utcnow()
                    operation_stats.calculate_metrics()
                    
                    logger.info(f"Reverse incremental sync completed: {operation_stats.total_items_processed} items "
                               f"in {operation_stats.duration_seconds:.2f}s "
                               f"({operation_stats.success_rate:.1%} success rate)")
                    
        except Exception as e:
            operation_stats.status = SyncStatus.FAILED
            operation_stats.completed_at = datetime.utcnow()
            operation_stats.errors.append(f"Reverse incremental sync failed: {str(e)}")
            logger.error(f"Reverse incremental sync failed: {e}")
            
        finally:
            # Update sync timestamp and history
            if operation_stats.status == SyncStatus.COMPLETED:
                self.last_sync_timestamp = operation_stats.completed_at
                
            self.sync_history.append(operation_stats)
            self.current_operation = None
            
        return operation_stats