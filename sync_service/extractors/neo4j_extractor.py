"""
Neo4j data extraction module for sync service.

This module provides efficient extraction of graph data from Neo4j
with support for incremental updates and batch processing.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple
from dataclasses import dataclass

from neo4j import AsyncGraphDatabase, AsyncDriver
from neo4j.exceptions import Neo4jError

logger = logging.getLogger(__name__)


@dataclass
class SyncMetadata:
    """Metadata tracking sync progress."""
    last_sync_timestamp: Optional[datetime] = None
    total_nodes: int = 0
    total_edges: int = 0
    sync_started_at: Optional[datetime] = None
    sync_completed_at: Optional[datetime] = None


@dataclass  
class ExtractionStats:
    """Statistics for extraction operation."""
    entity_nodes: int = 0
    episodic_nodes: int = 0
    community_nodes: int = 0
    entity_edges: int = 0
    episodic_edges: int = 0
    extraction_time_seconds: float = 0.0


class Neo4jExtractor:
    """
    Extracts graph data from Neo4j for synchronization to FalkorDB.
    
    Features:
    - Incremental extraction based on timestamps
    - Batch processing for memory efficiency  
    - Connection pooling and error handling
    - Support for all Graphiti node and edge types
    """
    
    def __init__(
        self,
        uri: str,
        user: str,
        password: str,
        database: str = "neo4j",
        pool_size: int = 10,
        batch_size: int = 1000,
    ):
        """
        Initialize Neo4j extractor.
        
        Args:
            uri: Neo4j connection URI
            user: Database username
            password: Database password  
            database: Database name
            pool_size: Connection pool size
            batch_size: Batch size for queries
        """
        self.uri = uri
        self.user = user
        self.password = password
        self.database = database
        self.batch_size = batch_size
        self.driver: Optional[AsyncDriver] = None
        
    async def connect(self) -> None:
        """Establish connection to Neo4j."""
        try:
            self.driver = AsyncGraphDatabase.driver(
                self.uri,
                auth=(self.user, self.password),
            )
            # Test connectivity
            await self.driver.verify_connectivity()
            logger.info(f"Connected to Neo4j at {self.uri}")
        except Neo4jError as e:
            logger.error(f"Failed to connect to Neo4j: {e}")
            raise
            
    async def disconnect(self) -> None:
        """Close Neo4j connection."""
        if self.driver:
            await self.driver.close()
            logger.info("Disconnected from Neo4j")
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit.""" 
        await self.disconnect()
        
    async def get_sync_metadata(self) -> SyncMetadata:
        """
        Get current sync metadata from Neo4j.
        
        Returns:
            SyncMetadata with current database state
        """
        if not self.driver:
            raise RuntimeError("Not connected to Neo4j")
            
        async with self.driver.session(database=self.database) as session:
            # Count all nodes and edges
            node_count_query = """
            MATCH (n) 
            RETURN count(n) as total_nodes
            """
            edge_count_query = """
            MATCH ()-[r]->() 
            RETURN count(r) as total_edges
            """
            
            node_result = await session.run(node_count_query)
            edge_result = await session.run(edge_count_query)
            
            node_record = await node_result.single()
            edge_record = await edge_result.single()
            
            total_nodes = node_record["total_nodes"] if node_record else 0
            total_edges = edge_record["total_edges"] if edge_record else 0
            
            return SyncMetadata(
                total_nodes=total_nodes,
                total_edges=total_edges
            )
    
    async def extract_entity_nodes(
        self, 
        since_timestamp: Optional[datetime] = None,
        limit: Optional[int] = None
    ) -> AsyncIterator[List[Dict[str, Any]]]:
        """
        Extract Entity nodes from Neo4j in batches.
        
        Args:
            since_timestamp: Only extract nodes created/modified after this time
            limit: Maximum number of nodes to extract
            
        Yields:
            Batches of entity node data as dictionaries
        """
        if not self.driver:
            raise RuntimeError("Not connected to Neo4j")
            
        base_query = """
        MATCH (n:Entity)
        """
        
        where_clauses = []
        params = {}
        
        if since_timestamp:
            where_clauses.append("n.created_at > $since_timestamp")
            params["since_timestamp"] = since_timestamp
            
        if where_clauses:
            base_query += " WHERE " + " AND ".join(where_clauses)
            
        base_query += """
        RETURN 
            n.uuid as uuid,
            n.name as name,
            n.group_id as group_id, 
            n.created_at as created_at,
            n.summary as summary,
            labels(n) as labels,
            properties(n) as attributes
        ORDER BY n.created_at ASC
        """
        
        if limit:
            base_query += f" LIMIT {limit}"
            
        async with self.driver.session(database=self.database) as session:
            result = await session.run(base_query, params)
            
            batch = []
            async for record in result:
                # Flatten all properties into a single dictionary
                node_data = dict(record["attributes"]) if record["attributes"] else {}
                
                # Override with specific fields to ensure consistency
                node_data.update({
                    "uuid": record["uuid"],
                    "name": record["name"], 
                    "group_id": record["group_id"],
                    "created_at": record["created_at"],
                    "summary": record["summary"],
                    "labels": record["labels"]
                })
                batch.append(node_data)
                
                if len(batch) >= self.batch_size:
                    yield batch
                    batch = []
                    
            if batch:
                yield batch
                
    async def extract_episodic_nodes(
        self,
        since_timestamp: Optional[datetime] = None,
        limit: Optional[int] = None
    ) -> AsyncIterator[List[Dict[str, Any]]]:
        """
        Extract Episodic nodes from Neo4j in batches.
        
        Args:
            since_timestamp: Only extract nodes created/modified after this time
            limit: Maximum number of nodes to extract
            
        Yields:
            Batches of episodic node data as dictionaries
        """
        if not self.driver:
            raise RuntimeError("Not connected to Neo4j")
            
        base_query = """
        MATCH (n:Episodic)
        """
        
        where_clauses = []
        params = {}
        
        if since_timestamp:
            where_clauses.append("n.created_at > $since_timestamp")
            params["since_timestamp"] = since_timestamp
            
        if where_clauses:
            base_query += " WHERE " + " AND ".join(where_clauses)
            
        base_query += """
        RETURN 
            n.uuid as uuid,
            n.name as name,
            n.group_id as group_id,
            n.created_at as created_at, 
            n.content as content,
            n.source as source,
            n.source_description as source_description,
            labels(n) as labels,
            properties(n) as attributes
        ORDER BY n.created_at ASC
        """
        
        if limit:
            base_query += f" LIMIT {limit}"
            
        async with self.driver.session(database=self.database) as session:
            result = await session.run(base_query, params)
            
            batch = []
            async for record in result:
                # Flatten all properties into a single dictionary
                node_data = dict(record["attributes"]) if record["attributes"] else {}
                
                # Override with specific fields to ensure consistency
                node_data.update({
                    "uuid": record["uuid"],
                    "name": record["name"],
                    "group_id": record["group_id"], 
                    "created_at": record["created_at"],
                    "content": record["content"],
                    "source": record["source"],
                    "source_description": record["source_description"],
                    "labels": record["labels"]
                })
                batch.append(node_data)
                
                if len(batch) >= self.batch_size:
                    yield batch
                    batch = []
                    
            if batch:
                yield batch
                
    async def extract_community_nodes(
        self,
        since_timestamp: Optional[datetime] = None,
        limit: Optional[int] = None
    ) -> AsyncIterator[List[Dict[str, Any]]]:
        """
        Extract Community nodes from Neo4j in batches.
        
        Args:
            since_timestamp: Only extract nodes created/modified after this time
            limit: Maximum number of nodes to extract
            
        Yields:
            Batches of community node data as dictionaries
        """
        if not self.driver:
            raise RuntimeError("Not connected to Neo4j")
            
        base_query = """
        MATCH (n:Community)
        """
        
        where_clauses = []
        params = {}
        
        if since_timestamp:
            where_clauses.append("n.created_at > $since_timestamp")
            params["since_timestamp"] = since_timestamp
            
        if where_clauses:
            base_query += " WHERE " + " AND ".join(where_clauses)
            
        base_query += """
        RETURN 
            n.uuid as uuid,
            n.name as name,
            n.group_id as group_id,
            n.created_at as created_at,
            n.summary as summary,
            labels(n) as labels,
            properties(n) as attributes
        ORDER BY n.created_at ASC
        """
        
        if limit:
            base_query += f" LIMIT {limit}"
            
        async with self.driver.session(database=self.database) as session:
            result = await session.run(base_query, params)
            
            batch = []
            async for record in result:
                # Flatten all properties into a single dictionary
                node_data = dict(record["attributes"]) if record["attributes"] else {}
                
                # Override with specific fields to ensure consistency
                node_data.update({
                    "uuid": record["uuid"],
                    "name": record["name"],
                    "group_id": record["group_id"],
                    "created_at": record["created_at"],
                    "summary": record["summary"], 
                    "labels": record["labels"]
                })
                batch.append(node_data)
                
                if len(batch) >= self.batch_size:
                    yield batch
                    batch = []
                    
            if batch:
                yield batch
                
    async def extract_entity_edges(
        self,
        since_timestamp: Optional[datetime] = None,
        limit: Optional[int] = None
    ) -> AsyncIterator[List[Dict[str, Any]]]:
        """
        Extract Entity edges (RELATES_TO) from Neo4j in batches.
        
        Args:
            since_timestamp: Only extract edges created/modified after this time
            limit: Maximum number of edges to extract
            
        Yields:
            Batches of entity edge data as dictionaries
        """
        if not self.driver:
            raise RuntimeError("Not connected to Neo4j")
            
        base_query = """
        MATCH (source)-[r:RELATES_TO]->(target)
        """
        
        where_clauses = []
        params = {}
        
        if since_timestamp:
            where_clauses.append("r.created_at > $since_timestamp")
            params["since_timestamp"] = since_timestamp
            
        if where_clauses:
            base_query += " WHERE " + " AND ".join(where_clauses)
            
        base_query += """
        RETURN 
            r.uuid as uuid,
            source.uuid as source_node_uuid,
            target.uuid as target_node_uuid,
            r.created_at as created_at,
            r.name as name,
            r.group_id as group_id,
            r.fact as fact,
            r.episodes as episodes,
            r.expired_at as expired_at,
            r.valid_at as valid_at,
            r.invalid_at as invalid_at,
            properties(r) as attributes
        ORDER BY r.created_at ASC
        """
        
        if limit:
            base_query += f" LIMIT {limit}"
            
        async with self.driver.session(database=self.database) as session:
            result = await session.run(base_query, params)
            
            batch = []
            async for record in result:
                # Flatten all properties into a single dictionary
                edge_data = dict(record["attributes"]) if record["attributes"] else {}
                
                # Override with specific fields to ensure consistency
                edge_data.update({
                    "uuid": record["uuid"],
                    "source_node_uuid": record["source_node_uuid"],
                    "target_node_uuid": record["target_node_uuid"],
                    "created_at": record["created_at"],
                    "name": record["name"],
                    "group_id": record["group_id"],
                    "fact": record["fact"],
                    "episodes": record["episodes"],
                    "expired_at": record["expired_at"],
                    "valid_at": record["valid_at"],
                    "invalid_at": record["invalid_at"]
                })
                batch.append(edge_data)
                
                if len(batch) >= self.batch_size:
                    yield batch
                    batch = []
                    
            if batch:
                yield batch
                
    async def extract_episodic_edges(
        self,
        since_timestamp: Optional[datetime] = None,
        limit: Optional[int] = None
    ) -> AsyncIterator[List[Dict[str, Any]]]:
        """
        Extract Episodic edges (MENTIONS) from Neo4j in batches.
        
        Args:
            since_timestamp: Only extract edges created/modified after this time
            limit: Maximum number of edges to extract
            
        Yields:
            Batches of episodic edge data as dictionaries
        """
        if not self.driver:
            raise RuntimeError("Not connected to Neo4j")
            
        base_query = """
        MATCH (episode:Episodic)-[r:MENTIONS]->(entity:Entity)
        """
        
        where_clauses = []
        params = {}
        
        if since_timestamp:
            where_clauses.append("r.created_at > $since_timestamp")
            params["since_timestamp"] = since_timestamp
            
        if where_clauses:
            base_query += " WHERE " + " AND ".join(where_clauses)
            
        base_query += """
        RETURN 
            r.uuid as uuid,
            episode.uuid as source_node_uuid,
            entity.uuid as target_node_uuid,
            r.created_at as created_at,
            r.group_id as group_id,
            properties(r) as attributes
        ORDER BY r.created_at ASC
        """
        
        if limit:
            base_query += f" LIMIT {limit}"
            
        async with self.driver.session(database=self.database) as session:
            result = await session.run(base_query, params)
            
            batch = []
            async for record in result:
                # Flatten all properties into a single dictionary
                edge_data = dict(record["attributes"]) if record["attributes"] else {}
                
                # Override with specific fields to ensure consistency
                edge_data.update({
                    "uuid": record["uuid"],
                    "source_node_uuid": record["source_node_uuid"],
                    "target_node_uuid": record["target_node_uuid"],
                    "created_at": record["created_at"],
                    "group_id": record["group_id"]
                })
                batch.append(edge_data)
                
                if len(batch) >= self.batch_size:
                    yield batch
                    batch = []
                    
            if batch:
                yield batch
                
    async def extract_all_data(
        self,
        since_timestamp: Optional[datetime] = None
    ) -> Tuple[AsyncIterator, ExtractionStats]:
        """
        Extract all graph data from Neo4j.
        
        Args:
            since_timestamp: Only extract data modified after this time
            
        Returns:
            Tuple of (async iterator of data batches, extraction statistics)
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
                
            # Calculate extraction time
            end_time = asyncio.get_event_loop().time()
            stats.extraction_time_seconds = end_time - start_time
            
        return data_generator(), stats