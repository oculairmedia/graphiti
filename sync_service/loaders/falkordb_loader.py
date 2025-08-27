"""
FalkorDB data loading module for sync service.

This module provides efficient loading of graph data into FalkorDB
with support for upsert operations and batch processing.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Set
from dataclasses import dataclass

from falkordb.asyncio import FalkorDB
from falkordb import Graph as FalkorGraph

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


class FalkorDBLoader:
    """
    Loads graph data into FalkorDB cache from Neo4j extraction.
    
    Features:
    - Upsert operations (create or update existing data)
    - Batch processing for performance
    - Index creation and maintenance
    - Data validation and error handling
    """
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        username: Optional[str] = None,
        password: Optional[str] = None,
        database: str = "graphiti_cache",
        batch_size: int = 1000,
    ):
        """
        Initialize FalkorDB loader.
        
        Args:
            host: FalkorDB host
            port: FalkorDB port
            username: Database username (optional)
            password: Database password (optional)
            database: Graph database name
            batch_size: Batch size for operations
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
            
            # Test connectivity by running a simple query
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
        
    def _convert_datetimes_to_strings(self, obj: Any) -> Any:
        """Convert datetime objects to FalkorDB-compatible strings."""
        # Check for Neo4j DateTime FIRST, before checking collections
        if hasattr(obj, 'to_native'):
            # Handle Neo4j DateTime objects - they have a to_native() method
            try:
                native_dt = obj.to_native()
                return native_dt.strftime('%Y-%m-%dT%H:%M:%S')
            except:
                # Fall back to string representation and clean it
                return str(obj).split('.')[0].replace('+00:00', '').replace('Z', '')
        elif isinstance(obj, datetime):
            # FalkorDB prefers simpler datetime format without microseconds and timezone
            return obj.strftime('%Y-%m-%dT%H:%M:%S')
        elif isinstance(obj, dict):
            return {k: self._convert_datetimes_to_strings(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._convert_datetimes_to_strings(item) for item in obj]
        elif isinstance(obj, tuple):
            return tuple(self._convert_datetimes_to_strings(item) for item in obj)
        elif isinstance(obj, str):
            # Handle string datetimes that might be malformed
            if 'T' in obj and (':' in obj or '+' in obj or '-' in obj[-6:]):
                try:
                    # Try to parse and reformat
                    dt = datetime.fromisoformat(obj.replace('Z', '+00:00'))
                    return dt.strftime('%Y-%m-%dT%H:%M:%S')
                except (ValueError, TypeError):
                    # If parsing fails, sanitize the string to remove problematic characters
                    return obj.replace('+00:00', '').replace('Z', '').split('.')[0]
            return obj
        else:
            return obj
    
    def _safe_value_for_query(self, value: Any) -> str:
        """Convert a value to a safely escaped string for direct query insertion."""
        if value is None:
            return 'NULL'
        elif isinstance(value, bool):
            return 'true' if value else 'false'
        elif isinstance(value, (int, float)):
            return str(value)
        elif isinstance(value, str):
            # Escape quotes and backslashes for string literals
            escaped = value.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r')
            return f'"{escaped}"'
        else:
            # Convert to string and escape
            escaped = str(value).replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r')
            return f'"{escaped}"'
            
    async def create_indices(self) -> None:
        """Create indices for optimal query performance."""
        if not self.graph:
            raise RuntimeError("Not connected to FalkorDB")
            
        index_queries = [
            # Entity node indices
            "CREATE INDEX FOR (n:Entity) ON (n.uuid)",
            "CREATE INDEX FOR (n:Entity) ON (n.name)",
            "CREATE INDEX FOR (n:Entity) ON (n.group_id)",
            "CREATE INDEX FOR (n:Entity) ON (n.created_at)",
            
            # Episodic node indices  
            "CREATE INDEX FOR (n:Episodic) ON (n.uuid)",
            "CREATE INDEX FOR (n:Episodic) ON (n.name)",
            "CREATE INDEX FOR (n:Episodic) ON (n.group_id)",
            "CREATE INDEX FOR (n:Episodic) ON (n.created_at)",
            
            # Community node indices
            "CREATE INDEX FOR (n:Community) ON (n.uuid)",
            "CREATE INDEX FOR (n:Community) ON (n.name)",
            "CREATE INDEX FOR (n:Community) ON (n.group_id)",
            "CREATE INDEX FOR (n:Community) ON (n.created_at)",
            
            # Edge indices
            "CREATE INDEX FOR ()-[r:RELATES_TO]->() ON (r.uuid)",
            "CREATE INDEX FOR ()-[r:RELATES_TO]->() ON (r.group_id)",
            "CREATE INDEX FOR ()-[r:RELATES_TO]->() ON (r.created_at)",
            "CREATE INDEX FOR ()-[r:MENTIONS]->() ON (r.uuid)",
            "CREATE INDEX FOR ()-[r:MENTIONS]->() ON (r.group_id)",
            "CREATE INDEX FOR ()-[r:MENTIONS]->() ON (r.created_at)",
        ]
        
        for query in index_queries:
            try:
                await self.graph.query(query)
                logger.debug(f"Created index: {query}")
            except Exception as e:
                if "already indexed" in str(e).lower():
                    logger.debug(f"Index already exists: {query}")
                else:
                    logger.warning(f"Failed to create index {query}: {e}")
                    
    async def clear_all_data(self) -> None:
        """Clear all data from FalkorDB cache."""
        if not self.graph:
            raise RuntimeError("Not connected to FalkorDB")
            
        try:
            await self.graph.query("MATCH (n) DETACH DELETE n")
            logger.info("Cleared all data from FalkorDB cache")
        except Exception as e:
            logger.error(f"Failed to clear FalkorDB data: {e}")
            raise
            
    async def load_entity_nodes(self, nodes: List[Dict[str, Any]]) -> int:
        """
        Load entity nodes into FalkorDB using upsert.
        
        Args:
            nodes: List of entity node data dictionaries
            
        Returns:
            Number of nodes successfully loaded
        """
        if not self.graph or not nodes:
            return 0
            
        loaded_count = 0
        
        for node in nodes:
            try:
                # Convert datetimes to strings
                node = self._convert_datetimes_to_strings(node)
                
                # Build properties string for direct query insertion (no parameters)
                props = []
                uuid_val = self._safe_value_for_query(node["uuid"])
                
                for key, value in node.items():
                    if key not in ["uuid", "labels"]:
                        safe_value = self._safe_value_for_query(value)
                        props.append(f"{key}: {safe_value}")
                        
                props_str = "{uuid: " + uuid_val + ", " + ", ".join(props) + "}"
                
                # Upsert query - merge on UUID (no parameters to avoid parsing issues)
                query = f"""
                MERGE (n:Entity {{uuid: {uuid_val}}})
                SET n = {props_str}
                RETURN n.uuid as uuid
                """
                
                await self.graph.query(query)
                loaded_count += 1
                
            except Exception as e:
                logger.error(f"Failed to load entity node {node.get('uuid', 'unknown')}: {e}")
                logger.debug(f"Failing node data: {node}")
                logger.debug(f"Generated query: {query}")
                
        logger.debug(f"Loaded {loaded_count}/{len(nodes)} entity nodes")
        return loaded_count
        
    async def load_episodic_nodes(self, nodes: List[Dict[str, Any]]) -> int:
        """
        Load episodic nodes into FalkorDB using upsert.
        
        Args:
            nodes: List of episodic node data dictionaries
            
        Returns:
            Number of nodes successfully loaded
        """
        if not self.graph or not nodes:
            return 0
            
        loaded_count = 0
        
        for node in nodes:
            try:
                # Convert datetimes to strings
                node = self._convert_datetimes_to_strings(node)
                
                # Build properties string for direct query insertion (no parameters)
                props = []
                uuid_val = self._safe_value_for_query(node["uuid"])
                
                for key, value in node.items():
                    if key not in ["uuid", "labels"]:
                        safe_value = self._safe_value_for_query(value)
                        props.append(f"{key}: {safe_value}")
                        
                props_str = "{uuid: " + uuid_val + ", " + ", ".join(props) + "}"
                
                # Upsert query - merge on UUID (no parameters to avoid parsing issues)
                query = f"""
                MERGE (n:Episodic {{uuid: {uuid_val}}})
                SET n = {props_str}
                RETURN n.uuid as uuid
                """
                
                await self.graph.query(query)
                loaded_count += 1
                
            except Exception as e:
                logger.error(f"Failed to load episodic node {node.get('uuid', 'unknown')}: {e}")
                logger.debug(f"Failing node data: {node}")
                logger.debug(f"Generated query: {query}")
                
        logger.debug(f"Loaded {loaded_count}/{len(nodes)} episodic nodes")
        return loaded_count
        
    async def load_community_nodes(self, nodes: List[Dict[str, Any]]) -> int:
        """
        Load community nodes into FalkorDB using upsert.
        
        Args:
            nodes: List of community node data dictionaries
            
        Returns:
            Number of nodes successfully loaded
        """
        if not self.graph or not nodes:
            return 0
            
        loaded_count = 0
        
        for node in nodes:
            try:
                # Convert datetimes to strings
                node = self._convert_datetimes_to_strings(node)
                
                # Build properties string for direct query insertion (no parameters)
                props = []
                uuid_val = self._safe_value_for_query(node["uuid"])
                
                for key, value in node.items():
                    if key not in ["uuid", "labels"]:
                        safe_value = self._safe_value_for_query(value)
                        props.append(f"{key}: {safe_value}")
                        
                props_str = "{uuid: " + uuid_val + ", " + ", ".join(props) + "}"
                
                # Upsert query - merge on UUID (no parameters to avoid parsing issues)
                query = f"""
                MERGE (n:Community {{uuid: {uuid_val}}})
                SET n = {props_str}
                RETURN n.uuid as uuid
                """
                
                await self.graph.query(query)
                loaded_count += 1
                
            except Exception as e:
                logger.error(f"Failed to load community node {node.get('uuid', 'unknown')}: {e}")
                logger.debug(f"Failing node data: {node}")
                logger.debug(f"Generated query: {query}")
                
        logger.debug(f"Loaded {loaded_count}/{len(nodes)} community nodes")
        return loaded_count
        
    async def load_entity_edges(self, edges: List[Dict[str, Any]]) -> int:
        """
        Load entity edges (RELATES_TO) into FalkorDB using upsert.
        
        Args:
            edges: List of entity edge data dictionaries
            
        Returns:
            Number of edges successfully loaded
        """
        if not self.graph or not edges:
            return 0
            
        loaded_count = 0
        
        for edge in edges:
            try:
                # Convert datetimes to strings
                edge = self._convert_datetimes_to_strings(edge)
                
                # Build properties string for direct query insertion
                props = []
                uuid_val = self._safe_value_for_query(edge["uuid"])
                source_uuid_val = self._safe_value_for_query(edge["source_node_uuid"])
                target_uuid_val = self._safe_value_for_query(edge["target_node_uuid"])
                
                for key, value in edge.items():
                    if key not in ["uuid", "source_node_uuid", "target_node_uuid"]:
                        safe_value = self._safe_value_for_query(value)
                        props.append(f"{key}: {safe_value}")
                        
                props_str = "{uuid: " + uuid_val + ", " + ", ".join(props) + "}"
                
                # Upsert query - merge on UUID and ensure nodes exist (no parameters)
                query = f"""
                MATCH (source {{uuid: {source_uuid_val}}})
                MATCH (target {{uuid: {target_uuid_val}}})
                MERGE (source)-[r:RELATES_TO {{uuid: {uuid_val}}}]->(target)
                SET r = {props_str}
                RETURN r.uuid as uuid
                """
                
                result = await self.graph.query(query)
                if result.result_set:
                    loaded_count += 1
                else:
                    logger.warning(f"Could not create edge {edge['uuid']} - nodes may not exist")
                    
            except Exception as e:
                # Log more details about the failing edge for debugging
                logger.error(f"Failed to load entity edge {edge.get('uuid', 'unknown')}: {e}")
                logger.debug(f"Failing edge data: {edge}")
                logger.debug(f"Generated query: {query}")
                
        logger.debug(f"Loaded {loaded_count}/{len(edges)} entity edges")
        return loaded_count
        
    async def load_episodic_edges(self, edges: List[Dict[str, Any]]) -> int:
        """
        Load episodic edges (MENTIONS) into FalkorDB using upsert.
        
        Args:
            edges: List of episodic edge data dictionaries
            
        Returns:
            Number of edges successfully loaded
        """
        if not self.graph or not edges:
            return 0
            
        loaded_count = 0
        
        for edge in edges:
            try:
                # Convert datetimes to strings
                edge = self._convert_datetimes_to_strings(edge)
                
                # Build properties string for direct query insertion
                props = []
                uuid_val = self._safe_value_for_query(edge["uuid"])
                source_uuid_val = self._safe_value_for_query(edge["source_node_uuid"])
                target_uuid_val = self._safe_value_for_query(edge["target_node_uuid"])
                
                for key, value in edge.items():
                    if key not in ["uuid", "source_node_uuid", "target_node_uuid"]:
                        safe_value = self._safe_value_for_query(value)
                        props.append(f"{key}: {safe_value}")
                        
                props_str = "{uuid: " + uuid_val + ", " + ", ".join(props) + "}"
                
                # Upsert query - merge on UUID and ensure nodes exist (no parameters)
                query = f"""
                MATCH (episode:Episodic {{uuid: {source_uuid_val}}})
                MATCH (entity:Entity {{uuid: {target_uuid_val}}})
                MERGE (episode)-[r:MENTIONS {{uuid: {uuid_val}}}]->(entity)
                SET r = {props_str}
                RETURN r.uuid as uuid
                """
                
                result = await self.graph.query(query)
                if result.result_set:
                    loaded_count += 1
                else:
                    logger.warning(f"Could not create edge {edge['uuid']} - nodes may not exist")
                    
            except Exception as e:
                # Log more details about the failing edge for debugging
                logger.error(f"Failed to load episodic edge {edge.get('uuid', 'unknown')}: {e}")
                logger.debug(f"Failing edge data: {edge}")
                logger.debug(f"Generated query: {query}")
                
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
            
    async def get_cache_statistics(self) -> Dict[str, int]:
        """
        Get statistics about cached data in FalkorDB.
        
        Returns:
            Dictionary with counts of different data types
        """
        if not self.graph:
            raise RuntimeError("Not connected to FalkorDB")
            
        stats = {}
        
        try:
            # Count nodes by type
            entity_result = await self.graph.query("MATCH (n:Entity) RETURN count(n) as count")
            stats["entity_nodes"] = entity_result.result_set[0][0] if entity_result.result_set else 0
            
            episodic_result = await self.graph.query("MATCH (n:Episodic) RETURN count(n) as count")
            stats["episodic_nodes"] = episodic_result.result_set[0][0] if episodic_result.result_set else 0
            
            community_result = await self.graph.query("MATCH (n:Community) RETURN count(n) as count")
            stats["community_nodes"] = community_result.result_set[0][0] if community_result.result_set else 0
            
            # Count edges by type  
            entity_edge_result = await self.graph.query("MATCH ()-[r:RELATES_TO]->() RETURN count(r) as count")
            stats["entity_edges"] = entity_edge_result.result_set[0][0] if entity_edge_result.result_set else 0
            
            episodic_edge_result = await self.graph.query("MATCH ()-[r:MENTIONS]->() RETURN count(r) as count")
            stats["episodic_edges"] = episodic_edge_result.result_set[0][0] if episodic_edge_result.result_set else 0
            
        except Exception as e:
            logger.error(f"Failed to get cache statistics: {e}")
            
        return stats