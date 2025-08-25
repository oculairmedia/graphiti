"""
Neo4j data loading module for reverse sync service.

This module provides efficient loading of graph data into Neo4j from FalkorDB
with support for upsert operations and batch processing.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

from neo4j import AsyncGraphDatabase, AsyncDriver, AsyncSession
from neo4j.exceptions import Neo4jError

logger = logging.getLogger(__name__)


@dataclass
class LoadingStats:
    """Statistics for loading operation."""
    entity_nodes_loaded: int = 0
    episodic_nodes_loaded: int = 0 
    community_nodes_loaded: int = 0
    entity_edges_loaded: int = 0
    episodic_edges_loaded: int = 0
    loading_time_seconds: float = 0.0
    errors: int = 0


class Neo4jLoader:
    """
    Loads graph data into Neo4j from FalkorDB extraction.
    
    Features:
    - Upsert operations (create or update existing data)
    - Batch processing for performance
    - Index creation and maintenance
    - Data validation and error handling
    - Transaction management for data consistency
    """
    
    def __init__(
        self,
        uri: str = "bolt://localhost:7687",
        user: str = "neo4j",
        password: str = "password",
        database: str = "neo4j",
        batch_size: int = 1000,
    ):
        """
        Initialize Neo4j loader.
        
        Args:
            uri: Neo4j connection URI
            user: Database username
            password: Database password
            database: Target database name
            batch_size: Batch size for operations
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
                auth=(self.user, self.password)
            )
            
            # Test connectivity by running a simple query
            async with self.driver.session(database=self.database) as session:
                await session.run("RETURN 1")
                
            logger.info(f"Connected to Neo4j at {self.uri}/{self.database}")
        except Exception as e:
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
        
    def _prepare_node_properties(self, node: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare node properties for Neo4j insertion."""
        # Remove system fields that shouldn't be stored as properties
        props = {k: v for k, v in node.items() if k not in ['uuid', 'labels']}
        
        # Ensure datetime objects are properly handled
        for key, value in props.items():
            if isinstance(value, str) and key in ['created_at', 'updated_at']:
                try:
                    # Try to parse ISO datetime strings back to datetime objects
                    props[key] = datetime.fromisoformat(value.replace('Z', '+00:00'))
                except (ValueError, AttributeError):
                    # Keep as string if parsing fails
                    pass
                    
        return props
        
    def _prepare_edge_properties(self, edge: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare edge properties for Neo4j insertion."""
        # Remove system fields
        props = {k: v for k, v in edge.items() 
                if k not in ['uuid', 'source_node_uuid', 'target_node_uuid', 'relationship_type']}
        
        # Handle datetime conversion
        for key, value in props.items():
            if isinstance(value, str) and key in ['created_at', 'updated_at']:
                try:
                    props[key] = datetime.fromisoformat(value.replace('Z', '+00:00'))
                except (ValueError, AttributeError):
                    pass
                    
        return props
        
    async def create_indices(self) -> None:
        """Create indices for optimal query performance."""
        if not self.driver:
            raise RuntimeError("Not connected to Neo4j")
            
        index_queries = [
            # Entity node indices
            "CREATE INDEX entity_uuid IF NOT EXISTS FOR (n:Entity) ON (n.uuid)",
            "CREATE INDEX entity_name IF NOT EXISTS FOR (n:Entity) ON (n.name)",
            "CREATE INDEX entity_group_id IF NOT EXISTS FOR (n:Entity) ON (n.group_id)",
            "CREATE INDEX entity_created_at IF NOT EXISTS FOR (n:Entity) ON (n.created_at)",
            
            # Episodic node indices  
            "CREATE INDEX episodic_uuid IF NOT EXISTS FOR (n:Episodic) ON (n.uuid)",
            "CREATE INDEX episodic_name IF NOT EXISTS FOR (n:Episodic) ON (n.name)",
            "CREATE INDEX episodic_group_id IF NOT EXISTS FOR (n:Episodic) ON (n.group_id)",
            "CREATE INDEX episodic_created_at IF NOT EXISTS FOR (n:Episodic) ON (n.created_at)",
            
            # Community node indices
            "CREATE INDEX community_uuid IF NOT EXISTS FOR (n:Community) ON (n.uuid)",
            "CREATE INDEX community_name IF NOT EXISTS FOR (n:Community) ON (n.name)",
            "CREATE INDEX community_group_id IF NOT EXISTS FOR (n:Community) ON (n.group_id)",
            "CREATE INDEX community_created_at IF NOT EXISTS FOR (n:Community) ON (n.created_at)",
        ]
        
        async with self.driver.session(database=self.database) as session:
            for query in index_queries:
                try:
                    await session.run(query)
                    logger.debug(f"Created index: {query}")
                except Neo4jError as e:
                    if "already exists" in str(e).lower() or "equivalent" in str(e).lower():
                        logger.debug(f"Index already exists: {query}")
                    else:
                        logger.warning(f"Failed to create index {query}: {e}")
                        
    async def clear_all_data(self) -> None:
        """Clear all data from Neo4j database."""
        if not self.driver:
            raise RuntimeError("Not connected to Neo4j")
            
        try:
            async with self.driver.session(database=self.database) as session:
                # Delete all nodes and relationships
                await session.run("MATCH (n) DETACH DELETE n")
                logger.info("Cleared all data from Neo4j database")
        except Exception as e:
            logger.error(f"Failed to clear Neo4j data: {e}")
            raise
            
    async def load_entity_nodes(self, nodes: List[Dict[str, Any]]) -> int:
        """
        Load entity nodes into Neo4j using upsert.
        
        Args:
            nodes: List of entity node data dictionaries
            
        Returns:
            Number of nodes successfully loaded
        """
        if not self.driver or not nodes:
            return 0
            
        loaded_count = 0
        
        async with self.driver.session(database=self.database) as session:
            for node in nodes:
                try:
                    props = self._prepare_node_properties(node)
                    uuid_val = node["uuid"]
                    
                    # Upsert query - merge on UUID
                    query = """
                    MERGE (n:Entity {uuid: $uuid})
                    SET n += $props
                    RETURN n.uuid as uuid
                    """
                    
                    result = await session.run(query, uuid=uuid_val, props=props)
                    if await result.single():
                        loaded_count += 1
                        
                except Exception as e:
                    logger.error(f"Failed to load entity node {node.get('uuid', 'unknown')}: {e}")
                    
        logger.debug(f"Loaded {loaded_count}/{len(nodes)} entity nodes")
        return loaded_count
        
    async def load_episodic_nodes(self, nodes: List[Dict[str, Any]]) -> int:
        """
        Load episodic nodes into Neo4j using upsert.
        
        Args:
            nodes: List of episodic node data dictionaries
            
        Returns:
            Number of nodes successfully loaded
        """
        if not self.driver or not nodes:
            return 0
            
        loaded_count = 0
        
        async with self.driver.session(database=self.database) as session:
            for node in nodes:
                try:
                    props = self._prepare_node_properties(node)
                    uuid_val = node["uuid"]
                    
                    query = """
                    MERGE (n:Episodic {uuid: $uuid})
                    SET n += $props
                    RETURN n.uuid as uuid
                    """
                    
                    result = await session.run(query, uuid=uuid_val, props=props)
                    if await result.single():
                        loaded_count += 1
                        
                except Exception as e:
                    logger.error(f"Failed to load episodic node {node.get('uuid', 'unknown')}: {e}")
                    
        logger.debug(f"Loaded {loaded_count}/{len(nodes)} episodic nodes")
        return loaded_count
        
    async def load_community_nodes(self, nodes: List[Dict[str, Any]]) -> int:
        """
        Load community nodes into Neo4j using upsert.
        
        Args:
            nodes: List of community node data dictionaries
            
        Returns:
            Number of nodes successfully loaded
        """
        if not self.driver or not nodes:
            return 0
            
        loaded_count = 0
        
        async with self.driver.session(database=self.database) as session:
            for node in nodes:
                try:
                    props = self._prepare_node_properties(node)
                    uuid_val = node["uuid"]
                    
                    query = """
                    MERGE (n:Community {uuid: $uuid})
                    SET n += $props
                    RETURN n.uuid as uuid
                    """
                    
                    result = await session.run(query, uuid=uuid_val, props=props)
                    if await result.single():
                        loaded_count += 1
                        
                except Exception as e:
                    logger.error(f"Failed to load community node {node.get('uuid', 'unknown')}: {e}")
                    
        logger.debug(f"Loaded {loaded_count}/{len(nodes)} community nodes")
        return loaded_count
        
    async def load_entity_edges(self, edges: List[Dict[str, Any]]) -> int:
        """
        Load entity edges (RELATES_TO) into Neo4j using upsert.
        
        Args:
            edges: List of entity edge data dictionaries
            
        Returns:
            Number of edges successfully loaded
        """
        if not self.driver or not edges:
            return 0
            
        loaded_count = 0
        
        async with self.driver.session(database=self.database) as session:
            for edge in edges:
                try:
                    props = self._prepare_edge_properties(edge)
                    uuid_val = edge["uuid"]
                    source_uuid = edge["source_node_uuid"]
                    target_uuid = edge["target_node_uuid"]
                    
                    # Upsert query - ensure nodes exist and create/update relationship
                    query = """
                    MATCH (source {uuid: $source_uuid})
                    MATCH (target {uuid: $target_uuid})
                    MERGE (source)-[r:RELATES_TO {uuid: $uuid}]->(target)
                    SET r += $props
                    RETURN r.uuid as uuid
                    """
                    
                    result = await session.run(
                        query,
                        source_uuid=source_uuid,
                        target_uuid=target_uuid,
                        uuid=uuid_val,
                        props=props
                    )
                    
                    if await result.single():
                        loaded_count += 1
                    else:
                        logger.warning(f"Could not create edge {uuid_val} - source or target nodes may not exist")
                        
                except Exception as e:
                    logger.error(f"Failed to load entity edge {edge.get('uuid', 'unknown')}: {e}")
                    
        logger.debug(f"Loaded {loaded_count}/{len(edges)} entity edges")
        return loaded_count
        
    async def load_episodic_edges(self, edges: List[Dict[str, Any]]) -> int:
        """
        Load episodic edges (MENTIONS) into Neo4j using upsert.
        
        Args:
            edges: List of episodic edge data dictionaries
            
        Returns:
            Number of edges successfully loaded
        """
        if not self.driver or not edges:
            return 0
            
        loaded_count = 0
        
        async with self.driver.session(database=self.database) as session:
            for edge in edges:
                try:
                    props = self._prepare_edge_properties(edge)
                    uuid_val = edge["uuid"]
                    source_uuid = edge["source_node_uuid"]
                    target_uuid = edge["target_node_uuid"]
                    
                    query = """
                    MATCH (episode:Episodic {uuid: $source_uuid})
                    MATCH (entity:Entity {uuid: $target_uuid})
                    MERGE (episode)-[r:MENTIONS {uuid: $uuid}]->(entity)
                    SET r += $props
                    RETURN r.uuid as uuid
                    """
                    
                    result = await session.run(
                        query,
                        source_uuid=source_uuid,
                        target_uuid=target_uuid,
                        uuid=uuid_val,
                        props=props
                    )
                    
                    if await result.single():
                        loaded_count += 1
                    else:
                        logger.warning(f"Could not create edge {uuid_val} - episode or entity nodes may not exist")
                        
                except Exception as e:
                    logger.error(f"Failed to load episodic edge {edge.get('uuid', 'unknown')}: {e}")
                    
        logger.debug(f"Loaded {loaded_count}/{len(edges)} episodic edges")
        return loaded_count
        
    async def load_batch(self, data_type: str, batch: List[Dict[str, Any]]) -> int:
        """
        Load a batch of data based on type.
        
        Args:
            data_type: Type of data ("entity_nodes", "episodic_nodes", etc.)
            batch: List of data dictionaries
            
        Returns:
            Number of items successfully loaded
        """
        if data_type == "entity_nodes":
            return await self.load_entity_nodes(batch)
        elif data_type == "episodic_nodes":
            return await self.load_episodic_nodes(batch)
        elif data_type == "community_nodes":
            return await self.load_community_nodes(batch)
        elif data_type == "entity_edges":
            return await self.load_entity_edges(batch)
        elif data_type == "episodic_edges":
            return await self.load_episodic_edges(batch)
        else:
            logger.error(f"Unknown data type: {data_type}")
            return 0
            
    async def get_database_statistics(self) -> Dict[str, int]:
        """
        Get statistics about data in Neo4j database.
        
        Returns:
            Dictionary with counts of different data types
        """
        if not self.driver:
            raise RuntimeError("Not connected to Neo4j")
            
        stats = {}
        
        async with self.driver.session(database=self.database) as session:
            try:
                # Count nodes by type
                result = await session.run("MATCH (n:Entity) RETURN count(n) as count")
                record = await result.single()
                stats["entity_nodes"] = record["count"] if record else 0
                
                result = await session.run("MATCH (n:Episodic) RETURN count(n) as count")
                record = await result.single()
                stats["episodic_nodes"] = record["count"] if record else 0
                
                result = await session.run("MATCH (n:Community) RETURN count(n) as count")
                record = await result.single()
                stats["community_nodes"] = record["count"] if record else 0
                
                # Count edges by type  
                result = await session.run("MATCH ()-[r:RELATES_TO]->() RETURN count(r) as count")
                record = await result.single()
                stats["entity_edges"] = record["count"] if record else 0
                
                result = await session.run("MATCH ()-[r:MENTIONS]->() RETURN count(r) as count")
                record = await result.single()
                stats["episodic_edges"] = record["count"] if record else 0
                
            except Exception as e:
                logger.error(f"Failed to get database statistics: {e}")
                
        return stats