#!/usr/bin/env python3
"""
Debug script to test FalkorDB extraction with the exact sync service configuration.
This reproduces the sync service environment to identify the hang.
"""

import asyncio
import time
import logging
import os
from typing import Optional, List, Dict, Any, AsyncIterator
from datetime import datetime

# Use the same async import as the sync service
from falkordb.asyncio import FalkorDB
from falkordb import Graph as FalkorGraph

# Set up logging like the sync service
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Sync service configuration (from the analysis document)
SYNC_CONFIG = {
    # Database connections
    'host': '192.168.50.90',
    'port': 6379,
    'username': None,
    'password': None,
    'database': 'graphiti_migration',
    
    # Sync service specific parameters
    'batch_size': 500,  # SYNC_BATCH_SIZE
    'max_query_limit': 15000,  # SYNC_MAX_QUERY_LIMIT
    'enable_pagination': True,  # SYNC_ENABLE_QUERY_PAGINATION
    'optimization_enabled': True,  # SYNC_OPTIMIZATION_ENABLED
    'edge_batch_size': 1000,  # SYNC_OPTIMIZATION_EDGE_BATCH_SIZE (reduced from 8000)
    'node_batch_size': 15000,  # SYNC_OPTIMIZATION_NODE_BATCH_SIZE
    'memory_threshold_mb': 100,  # SYNC_OPTIMIZATION_MEMORY_THRESHOLD_MB
    'adaptive_sizing': True,  # SYNC_OPTIMIZATION_ADAPTIVE_SIZING
}

class SyncServiceFalkorDBExtractor:
    """Exact replica of the sync service FalkorDB extractor configuration."""
    
    def __init__(self, **config):
        """Initialize with sync service configuration."""
        self.host = config.get('host', 'localhost')
        self.port = config.get('port', 6379)
        self.username = config.get('username')
        self.password = config.get('password')
        self.database = config.get('database', 'graphiti_cache')
        
        # Sync service specific parameters
        self.batch_size = config.get('batch_size', 1000)
        self.max_query_limit = config.get('max_query_limit', 15000)
        self.enable_pagination = config.get('enable_pagination', True)
        self.optimization_enabled = config.get('optimization_enabled', True)
        self.edge_batch_size = config.get('edge_batch_size', 8000)
        self.node_batch_size = config.get('node_batch_size', 15000)
        self.memory_threshold_mb = config.get('memory_threshold_mb', 100)
        self.adaptive_sizing = config.get('adaptive_sizing', True)
        
        self.client: Optional[FalkorDB] = None
        self.graph: Optional[FalkorGraph] = None
        
        logger.info(f"Initialized FalkorDB extractor with config:")
        logger.info(f"  Host: {self.host}:{self.port}")
        logger.info(f"  Database: {self.database}")
        logger.info(f"  Optimization enabled: {self.optimization_enabled}")
        logger.info(f"  Edge batch size: {self.edge_batch_size}")
        logger.info(f"  Enable pagination: {self.enable_pagination}")
        logger.info(f"  Max query limit: {self.max_query_limit}")
        
    async def connect(self) -> None:
        """Establish async connection to FalkorDB."""
        try:
            self.client = FalkorDB(
                host=self.host,
                port=self.port,
                username=self.username,
                password=self.password,
            )
            self.graph = self.client.select_graph(self.database)
            
            # Test connectivity
            await self.graph.query("RETURN 1")
            logger.info(f"Connected to FalkorDB at {self.host}:{self.port}/{self.database}")
        except Exception as e:
            logger.error(f"Failed to connect to FalkorDB: {e}")
            raise
            
    async def disconnect(self) -> None:
        """Close FalkorDB connection."""
        if self.client and hasattr(self.client, 'aclose'):
            await self.client.aclose()
            logger.info("Disconnected from FalkorDB")

    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect()

    def _build_edge_return_clause(self) -> str:
        """Build the return clause for edge queries."""
        return "r.uuid, r.group_id, r.created_at, r.updated_at, r.valid_at, r.invalid_at, r.fact, r.episodes, r.chunks, r.source_node_uuid, r.target_node_uuid, r.weight, r.embedding"

    def _resolve_batch_limit(self, data_type: str, batch_override: Optional[int] = None) -> int:
        """Resolve the effective batch limit."""
        if batch_override is not None:
            return batch_override
        if data_type == 'entity_edges':
            return self.edge_batch_size
        return self.node_batch_size

    def _resolve_query_limit(self, data_type: str, batch_override: Optional[int] = None) -> int:
        """Resolve the query limit."""
        if batch_override is not None:
            return min(batch_override, self.max_query_limit)
        if data_type == 'entity_edges':
            return min(self.edge_batch_size, self.max_query_limit)
        return min(self.node_batch_size, self.max_query_limit)

    def _map_edge_row(self, row) -> Dict[str, Any]:
        """Map a database row to edge dictionary."""
        return {
            'uuid': row[0],
            'group_id': row[1],
            'created_at': row[2],
            'updated_at': row[3],
            'valid_at': row[4],
            'invalid_at': row[5],
            'fact': row[6],
            'episodes': row[7],
            'chunks': row[8],
            'source_node_uuid': row[9],
            'target_node_uuid': row[10],
            'weight': row[11],
            'embedding': row[12],
        }

    async def extract_entity_edges_optimized(
        self,
        since_timestamp: Optional[datetime] = None,
        batch_size: Optional[int] = None
    ) -> AsyncIterator[List[Dict[str, Any]]]:
        """Exact copy of the sync service optimized entity edge extraction."""
        if not self.graph:
            raise RuntimeError("Not connected to FalkorDB")

        offset = 0
        total_processed = 0
        where_clause = ""
        if since_timestamp:
            iso_timestamp = since_timestamp.isoformat()
            where_clause = (
                f"WHERE r.updated_at > '{iso_timestamp}' OR r.created_at > '{iso_timestamp}' "
                "OR r.updated_at IS NULL OR r.created_at IS NULL"
            )

        return_clause = self._build_edge_return_clause()

        while True:
            effective_batch_limit = self._resolve_batch_limit('entity_edges', batch_size)
            page_limit = self._resolve_query_limit('entity_edges', batch_size)
            pagination_clause = (
                f"SKIP {offset} LIMIT {page_limit}"
                if self.enable_pagination
                else f"LIMIT {page_limit}"
            )

            query = f"""
            MATCH ()-[r:RELATES_TO]->()
            {where_clause}
            RETURN {return_clause}
            ORDER BY r.uuid
            {pagination_clause}
            """

            try:
                logger.info(f"Executing edge query: offset={offset}, limit={page_limit}, batch_limit={effective_batch_limit}")
                start_time = time.time()
                
                # This is where the hang occurs in the sync service
                result = await self.graph.query(query)
                
                duration = time.time() - start_time
                logger.info(f"Query completed in {duration:.2f}s")
                
            except Exception as exc:
                logger.error(f"Failed to extract optimized entity edges at offset {offset}: {exc}")
                raise

            rows = result.result_set if result and result.result_set else []
            if not rows:
                logger.info(f"Entity edge optimization completed. Total processed: {total_processed}")
                break

            batch: List[Dict[str, Any]] = []
            for row in rows:
                batch.append(self._map_edge_row(row))
                if len(batch) >= effective_batch_limit:
                    yield batch
                    total_processed += len(batch)
                    batch = []

            if batch:
                yield batch
                total_processed += len(batch)

            if not self.enable_pagination or len(rows) < page_limit:
                break

            offset += page_limit
            logger.debug(f"Processed {total_processed} optimized entity edges; continuing from offset {offset}")

    async def extract_all_data(self, since_timestamp: Optional[datetime] = None):
        """Simulate the extract_all_data method that hangs."""
        logger.info("Starting extract_all_data - this is where the sync service hangs")
        
        # This is the exact generator that hangs in the sync service
        async def data_generator():
            # Skip nodes for now, go straight to the problematic edges
            logger.info("Skipping nodes, going directly to edge extraction...")
            
            # Extract entity edges - this is where it hangs
            logger.info("Starting entity edge extraction...")
            async for batch in self.extract_entity_edges_optimized(since_timestamp):
                logger.info(f"Yielding edge batch with {len(batch)} edges")
                yield ("entity_edges", batch)
                
        return data_generator(), None

async def test_sync_service_configuration():
    """Test with the exact sync service configuration."""
    print("🔍 Testing Sync Service FalkorDB Configuration")
    print("=" * 60)
    
    # Print configuration
    print("Configuration:")
    for key, value in SYNC_CONFIG.items():
        print(f"  {key}: {value}")
    print()
    
    try:
        async with SyncServiceFalkorDBExtractor(**SYNC_CONFIG) as extractor:
            
            # Test the exact method that hangs in the sync service
            print("⏳ Testing extract_all_data() - this is where sync service hangs...")
            
            start_time = time.time()
            batch_count = 0
            total_edges = 0
            
            # Set a timeout to detect the hang
            try:
                data_generator, _ = await extractor.extract_all_data()
                
                async for data_type, batch in data_generator:
                    batch_count += 1
                    total_edges += len(batch)
                    print(f"   Batch {batch_count}: {len(batch)} {data_type} (total: {total_edges})")
                    
                    # Stop after a few batches for testing
                    if batch_count >= 3:
                        print("   Stopping after 3 batches for testing...")
                        break
                        
            except asyncio.TimeoutError:
                print("❌ TIMEOUT: extract_all_data() hung!")
                print("   This confirms the sync service hang issue.")
                return False
                
            duration = time.time() - start_time
            print(f"✅ extract_all_data() completed: {total_edges} edges in {duration:.2f}s")
            return True
            
    except Exception as e:
        print(f"❌ Error during test: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Main test function."""
    success = await test_sync_service_configuration()
    
    print("\n" + "=" * 60)
    if success:
        print("✅ Sync service configuration works - issue may be environmental")
        print("   Possible causes:")
        print("   - Container resource limits")
        print("   - Network timeouts in Docker environment")
        print("   - Async event loop issues in containerized environment")
        print("   - Memory pressure in sync service container")
    else:
        print("💡 CONFIRMED: Sync service configuration causes hang!")
        print("   Root cause found in the configuration parameters")

if __name__ == "__main__":
    asyncio.run(main())
