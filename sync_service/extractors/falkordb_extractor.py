"""
FalkorDB data extraction module for reverse sync service.

This module provides extraction of graph data from FalkorDB for synchronization
to Neo4j, supporting batch processing and incremental sync capabilities.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, AsyncIterator
from dataclasses import dataclass

from falkordb.asyncio import FalkorDB
from falkordb import Graph as FalkorGraph

logger = logging.getLogger(__name__)


@dataclass
class SyncMetadata:
    """Metadata for sync operations."""
    last_sync_timestamp: Optional[datetime] = None
    total_entity_nodes: int = 0
    total_episodic_nodes: int = 0
    total_community_nodes: int = 0
    total_entity_edges: int = 0
    total_episodic_edges: int = 0


@dataclass
class ExtractionStats:
    """Statistics for extraction operations."""
    entity_nodes: int = 0
    episodic_nodes: int = 0
    community_nodes: int = 0
    entity_edges: int = 0
    episodic_edges: int = 0
    extraction_time_seconds: float = 0.0


class FalkorDBExtractor:
    """
    Extracts graph data from FalkorDB for reverse synchronization.
    
    Features:
    - Batch processing for memory efficiency
    - Incremental extraction support
    - Comprehensive data type coverage
    - Connection pooling and error handling
    """
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        username: Optional[str] = None,
        password: Optional[str] = None,
        database: str = "graphiti_migration",
        batch_size: int = 1000,
    ):
        """
        Initialize FalkorDB extractor.
        
        Args:
            host: FalkorDB host
            port: FalkorDB port
            username: Database username (optional)
            password: Database password (optional)
            database: Graph database name
            batch_size: Batch size for processing
        """
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.database = database
        self.batch_size = batch_size
        self.client: Optional[FalkorDB] = None
        self.graph: Optional[FalkorGraph] = None
        
    async def connect(self) -> None:
        """Establish connection to FalkorDB."""
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
        
    def _convert_node_result(self, node_data: Dict[str, Any]) -> Dict[str, Any]:
        """Convert FalkorDB node result to standard format."""
        # FalkorDB stores datetime as ISO strings, convert back to datetime objects
        if 'created_at' in node_data and isinstance(node_data['created_at'], str):
            try:
                node_data['created_at'] = datetime.fromisoformat(node_data['created_at'].replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                pass  # Keep as string if conversion fails
                
        if 'updated_at' in node_data and isinstance(node_data['updated_at'], str):
            try:
                node_data['updated_at'] = datetime.fromisoformat(node_data['updated_at'].replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                pass
                
        return node_data
        
    def _convert_edge_result(self, edge_data: Dict[str, Any]) -> Dict[str, Any]:
        """Convert FalkorDB edge result to standard format."""
        # Similar datetime conversion for edges
        if 'created_at' in edge_data and isinstance(edge_data['created_at'], str):
            try:
                edge_data['created_at'] = datetime.fromisoformat(edge_data['created_at'].replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                pass
                
        return edge_data
        
    async def get_sync_metadata(self) -> SyncMetadata:
        """Get metadata about the FalkorDB database."""
        if not self.graph:
            raise RuntimeError("Not connected to FalkorDB")
            
        metadata = SyncMetadata()
        
        try:
            # Count entity nodes
            result = await self.graph.query("MATCH (n:Entity) RETURN count(n) as count")
            metadata.total_entity_nodes = result.result_set[0][0] if result.result_set else 0
            
            # Count episodic nodes
            result = await self.graph.query("MATCH (n:Episodic) RETURN count(n) as count")
            metadata.total_episodic_nodes = result.result_set[0][0] if result.result_set else 0
            
            # Count community nodes
            result = await self.graph.query("MATCH (n:Community) RETURN count(n) as count")
            metadata.total_community_nodes = result.result_set[0][0] if result.result_set else 0
            
            # Count entity edges
            result = await self.graph.query("MATCH ()-[r:RELATES_TO]->() RETURN count(r) as count")
            metadata.total_entity_edges = result.result_set[0][0] if result.result_set else 0
            
            # Count episodic edges
            result = await self.graph.query("MATCH ()-[r:MENTIONS]->() RETURN count(r) as count")
            metadata.total_episodic_edges = result.result_set[0][0] if result.result_set else 0
            
            logger.info(f"FalkorDB metadata: {metadata.total_entity_nodes} entities, "
                       f"{metadata.total_episodic_nodes} episodes, "
                       f"{metadata.total_entity_edges} entity edges, "
                       f"{metadata.total_episodic_edges} episodic edges")
                       
        except Exception as e:
            logger.error(f"Failed to get sync metadata: {e}")
            
        return metadata
        
    async def extract_entity_nodes(
        self, 
        since_timestamp: Optional[datetime] = None,
        limit: Optional[int] = None
    ) -> AsyncIterator[List[Dict[str, Any]]]:
        """Extract entity nodes in batches."""
        if not self.graph:
            raise RuntimeError("Not connected to FalkorDB")
            
        # Build query with optional timestamp filter
        where_clause = ""
        if since_timestamp:
            iso_timestamp = since_timestamp.isoformat()
            # Include nodes with NULL timestamps to ensure complete extraction
            where_clause = f"WHERE n.updated_at > '{iso_timestamp}' OR n.created_at > '{iso_timestamp}' OR n.updated_at IS NULL OR n.created_at IS NULL"
            
        query = f"""
        MATCH (n:Entity) 
        {where_clause}
        RETURN n.uuid as uuid, properties(n) as props
        ORDER BY n.created_at
        """
        
        if limit:
            query += f" LIMIT {limit}"
            
        try:
            result = await self.graph.query(query)
            if not result.result_set:
                return
                
            batch = []
            for row in result.result_set:
                uuid_val = row[0]
                props = row[1] if row[1] else {}
                
                # Ensure uuid is in properties
                props['uuid'] = uuid_val
                props['labels'] = ['Entity']
                
                batch.append(self._convert_node_result(props))
                
                if len(batch) >= self.batch_size:
                    yield batch
                    batch = []
                    
            # Yield remaining items
            if batch:
                yield batch
                
        except Exception as e:
            logger.error(f"Failed to extract entity nodes: {e}")
            raise
            
    async def extract_episodic_nodes(
        self, 
        since_timestamp: Optional[datetime] = None,
        limit: Optional[int] = None
    ) -> AsyncIterator[List[Dict[str, Any]]]:
        """Extract episodic nodes in batches."""
        if not self.graph:
            raise RuntimeError("Not connected to FalkorDB")
            
        where_clause = ""
        if since_timestamp:
            iso_timestamp = since_timestamp.isoformat()
            # Include nodes with NULL timestamps to ensure complete extraction
            where_clause = f"WHERE n.updated_at > '{iso_timestamp}' OR n.created_at > '{iso_timestamp}' OR n.updated_at IS NULL OR n.created_at IS NULL"
            
        query = f"""
        MATCH (n:Episodic) 
        {where_clause}
        RETURN n.uuid as uuid, properties(n) as props
        ORDER BY n.created_at
        """
        
        if limit:
            query += f" LIMIT {limit}"
            
        try:
            result = await self.graph.query(query)
            if not result.result_set:
                return
                
            batch = []
            for row in result.result_set:
                uuid_val = row[0]
                props = row[1] if row[1] else {}
                
                props['uuid'] = uuid_val
                props['labels'] = ['Episodic']
                
                batch.append(self._convert_node_result(props))
                
                if len(batch) >= self.batch_size:
                    yield batch
                    batch = []
                    
            if batch:
                yield batch
                
        except Exception as e:
            logger.error(f"Failed to extract episodic nodes: {e}")
            raise
            
    async def extract_community_nodes(
        self, 
        since_timestamp: Optional[datetime] = None,
        limit: Optional[int] = None
    ) -> AsyncIterator[List[Dict[str, Any]]]:
        """Extract community nodes in batches."""
        if not self.graph:
            raise RuntimeError("Not connected to FalkorDB")
            
        where_clause = ""
        if since_timestamp:
            iso_timestamp = since_timestamp.isoformat()
            # Include nodes with NULL timestamps to ensure complete extraction
            where_clause = f"WHERE n.updated_at > '{iso_timestamp}' OR n.created_at > '{iso_timestamp}' OR n.updated_at IS NULL OR n.created_at IS NULL"
            
        query = f"""
        MATCH (n:Community) 
        {where_clause}
        RETURN n.uuid as uuid, properties(n) as props
        ORDER BY n.created_at
        """
        
        if limit:
            query += f" LIMIT {limit}"
            
        try:
            result = await self.graph.query(query)
            if not result.result_set:
                return
                
            batch = []
            for row in result.result_set:
                uuid_val = row[0]
                props = row[1] if row[1] else {}
                
                props['uuid'] = uuid_val
                props['labels'] = ['Community']
                
                batch.append(self._convert_node_result(props))
                
                if len(batch) >= self.batch_size:
                    yield batch
                    batch = []
                    
            if batch:
                yield batch
                
        except Exception as e:
            logger.error(f"Failed to extract community nodes: {e}")
            raise
            
    async def extract_entity_edges(
        self, 
        since_timestamp: Optional[datetime] = None,
        limit: Optional[int] = None
    ) -> AsyncIterator[List[Dict[str, Any]]]:
        """Extract entity edges (RELATES_TO) in batches."""
        if not self.graph:
            raise RuntimeError("Not connected to FalkorDB")
            
        where_clause = ""
        if since_timestamp:
            iso_timestamp = since_timestamp.isoformat()
            # Include edges with NULL timestamps to ensure complete extraction
            where_clause = f"WHERE r.updated_at > '{iso_timestamp}' OR r.created_at > '{iso_timestamp}' OR r.updated_at IS NULL OR r.created_at IS NULL"
            
        query = f"""
        MATCH (source)-[r:RELATES_TO]->(target) 
        {where_clause}
        RETURN r.uuid as uuid, source.uuid as source_uuid, target.uuid as target_uuid, properties(r) as props
        ORDER BY r.created_at
        """
        
        if limit:
            query += f" LIMIT {limit}"
            
        try:
            result = await self.graph.query(query)
            if not result.result_set:
                return
                
            batch = []
            for row in result.result_set:
                uuid_val = row[0]
                source_uuid = row[1]
                target_uuid = row[2]
                props = row[3] if row[3] else {}
                
                edge_data = {
                    'uuid': uuid_val,
                    'source_node_uuid': source_uuid,
                    'target_node_uuid': target_uuid,
                    'relationship_type': 'RELATES_TO',
                    **props
                }
                
                batch.append(self._convert_edge_result(edge_data))
                
                if len(batch) >= self.batch_size:
                    yield batch
                    batch = []
                    
            if batch:
                yield batch
                
        except Exception as e:
            logger.error(f"Failed to extract entity edges: {e}")
            raise
            
    async def extract_episodic_edges(
        self, 
        since_timestamp: Optional[datetime] = None,
        limit: Optional[int] = None
    ) -> AsyncIterator[List[Dict[str, Any]]]:
        """Extract episodic edges (MENTIONS) in batches."""
        if not self.graph:
            raise RuntimeError("Not connected to FalkorDB")
            
        where_clause = ""
        if since_timestamp:
            iso_timestamp = since_timestamp.isoformat()
            # Include edges with NULL timestamps to ensure complete extraction
            where_clause = f"WHERE r.updated_at > '{iso_timestamp}' OR r.created_at > '{iso_timestamp}' OR r.updated_at IS NULL OR r.created_at IS NULL"
            
        query = f"""
        MATCH (episode:Episodic)-[r:MENTIONS]->(entity:Entity) 
        {where_clause}
        RETURN r.uuid as uuid, episode.uuid as source_uuid, entity.uuid as target_uuid, properties(r) as props
        ORDER BY r.created_at
        """
        
        if limit:
            query += f" LIMIT {limit}"
            
        try:
            result = await self.graph.query(query)
            if not result.result_set:
                return
                
            batch = []
            for row in result.result_set:
                uuid_val = row[0]
                source_uuid = row[1]
                target_uuid = row[2]
                props = row[3] if row[3] else {}
                
                edge_data = {
                    'uuid': uuid_val,
                    'source_node_uuid': source_uuid,
                    'target_node_uuid': target_uuid,
                    'relationship_type': 'MENTIONS',
                    **props
                }
                
                batch.append(self._convert_edge_result(edge_data))
                
                if len(batch) >= self.batch_size:
                    yield batch
                    batch = []
                    
            if batch:
                yield batch
                
        except Exception as e:
            logger.error(f"Failed to extract episodic edges: {e}")
            raise
            
    async def extract_all_data(
        self, 
        since_timestamp: Optional[datetime] = None
    ) -> Tuple[AsyncIterator[Tuple[str, List[Dict[str, Any]]]], ExtractionStats]:
        """
        Extract all data from FalkorDB.
        
        Returns:
            AsyncIterator yielding (data_type, batch) tuples and extraction statistics
        """
        stats = ExtractionStats()
        start_time = asyncio.get_event_loop().time()
        
        async def data_generator():
            # Extract entity nodes
            async for batch in self.extract_entity_nodes(since_timestamp):
                stats.entity_nodes += len(batch)
                yield ("entity_nodes", batch)
                
            # Extract episodic nodes
            async for batch in self.extract_episodic_nodes(since_timestamp):
                stats.episodic_nodes += len(batch)
                yield ("episodic_nodes", batch)
                
            # Extract community nodes
            async for batch in self.extract_community_nodes(since_timestamp):
                stats.community_nodes += len(batch)
                yield ("community_nodes", batch)
                
            # Extract entity edges
            async for batch in self.extract_entity_edges(since_timestamp):
                stats.entity_edges += len(batch)
                yield ("entity_edges", batch)
                
            # Extract episodic edges
            async for batch in self.extract_episodic_edges(since_timestamp):
                stats.episodic_edges += len(batch)
                yield ("episodic_edges", batch)
                
            # Calculate final stats
            end_time = asyncio.get_event_loop().time()
            stats.extraction_time_seconds = end_time - start_time
            
            logger.info(f"FalkorDB extraction completed: {stats.entity_nodes} entities, "
                       f"{stats.episodic_nodes} episodes, {stats.community_nodes} communities, "
                       f"{stats.entity_edges} entity edges, {stats.episodic_edges} episodic edges "
                       f"in {stats.extraction_time_seconds:.2f}s")
            
        return data_generator(), stats