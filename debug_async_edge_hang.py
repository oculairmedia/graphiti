#!/usr/bin/env python3
"""
Debug script to test the exact async FalkorDB edge extraction that's hanging.
This mimics the sync service's async implementation.
"""

import asyncio
import time
import logging
from typing import Optional, List, Dict, Any, AsyncIterator
from datetime import datetime

# Use the same async import as the sync service
from falkordb.asyncio import FalkorDB
from falkordb import Graph as FalkorGraph

# Connection settings
FALKORDB_HOST = "192.168.50.90"
FALKORDB_PORT = 6379
FALKORDB_DATABASE = "graphiti_migration"

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TestFalkorDBExtractor:
    """Test version of the FalkorDB extractor to reproduce the hang."""
    
    def __init__(self):
        self.host = FALKORDB_HOST
        self.port = FALKORDB_PORT
        self.database = FALKORDB_DATABASE
        self.client: Optional[FalkorDB] = None
        self.graph: Optional[FalkorGraph] = None
        self.optimization_enabled = True
        self.edge_batch_size = 1000
        self.enable_pagination = True
        
    async def connect(self) -> None:
        """Establish async connection to FalkorDB."""
        try:
            self.client = FalkorDB(
                host=self.host,
                port=self.port,
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

    def _build_edge_return_clause(self) -> str:
        """Build the return clause for edge queries."""
        return "r.uuid, r.group_id, r.created_at, r.updated_at, r.valid_at, r.invalid_at, r.fact, r.episodes, r.chunks, r.source_node_uuid, r.target_node_uuid, r.weight, r.embedding"

    def _resolve_batch_limit(self, data_type: str, batch_override: Optional[int] = None) -> int:
        """Resolve the effective batch limit."""
        return batch_override or self.edge_batch_size

    def _resolve_query_limit(self, data_type: str, batch_override: Optional[int] = None) -> int:
        """Resolve the query limit."""
        return batch_override or self.edge_batch_size

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
        """Exact copy of the optimized entity edge extraction that's hanging."""
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
                logger.info(f"Executing edge query at offset {offset}, limit {page_limit}")
                start_time = time.time()
                
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

    async def extract_entity_edges(
        self,
        since_timestamp: Optional[datetime] = None,
        limit: Optional[int] = None
    ) -> AsyncIterator[List[Dict[str, Any]]]:
        """Extract entity edges - exact copy of sync service method."""
        if not self.graph:
            raise RuntimeError("Not connected to FalkorDB")

        if self.optimization_enabled:
            remaining = limit
            batch_override = min(remaining, self.edge_batch_size) if remaining is not None else None

            async for batch in self.extract_entity_edges_optimized(
                since_timestamp=since_timestamp,
                batch_size=batch_override
            ):
                if remaining is not None:
                    if len(batch) >= remaining:
                        yield batch[:remaining]
                        return
                    yield batch
                    remaining -= len(batch)
                    if remaining <= 0:
                        return
                else:
                    yield batch
            return

async def test_async_edge_extraction():
    """Test the async edge extraction that's hanging in the sync service."""
    print("🔍 Testing Async FalkorDB Edge Extraction")
    print("=" * 50)
    
    extractor = TestFalkorDBExtractor()
    
    try:
        # Connect
        await extractor.connect()
        
        # Test the exact extraction method that hangs
        print("⏳ Starting edge extraction (this is where it hangs)...")
        
        total_edges = 0
        batch_count = 0
        start_time = time.time()
        
        # Set a timeout to detect the hang
        async def extract_with_timeout():
            edge_generator = extractor.extract_entity_edges()

            async for batch in edge_generator:
                batch_count_ref[0] += 1
                total_edges_ref[0] += len(batch)
                print(f"   Batch {batch_count_ref[0]}: {len(batch)} edges (total: {total_edges_ref[0]})")

                # Stop after a few batches to test
                if batch_count_ref[0] >= 3:
                    print("   Stopping after 3 batches for testing...")
                    break

        # Use references to track counts in nested function
        batch_count_ref = [0]
        total_edges_ref = [0]

        try:
            await asyncio.wait_for(extract_with_timeout(), timeout=60.0)
            batch_count = batch_count_ref[0]
            total_edges = total_edges_ref[0]

        except asyncio.TimeoutError:
            print("❌ TIMEOUT: Edge extraction hung after 60 seconds!")
            print("   This confirms the sync service hang issue.")
            return False
            
        duration = time.time() - start_time
        print(f"✅ Edge extraction completed: {total_edges} edges in {duration:.2f}s")
        return True
        
    except Exception as e:
        print(f"❌ Error during edge extraction: {e}")
        return False
        
    finally:
        await extractor.disconnect()

async def main():
    """Main test function."""
    success = await test_async_edge_extraction()
    
    print("\n" + "=" * 50)
    if success:
        print("✅ Async edge extraction works - issue may be elsewhere")
    else:
        print("💡 CONFIRMED: Async edge extraction hangs!")
        print("   Root cause found in the sync service async implementation")

if __name__ == "__main__":
    asyncio.run(main())
