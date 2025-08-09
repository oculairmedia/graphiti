"""Type stubs for graphiti_core.driver.neo4j_driver module."""

from typing import Any, Dict, List, Optional
from graphiti_core.driver.base import BaseDriver

class Neo4jDriver(BaseDriver):
    """Neo4j driver implementation."""
    
    def __init__(
        self,
        uri: str,
        username: str,
        password: str,
        database: Optional[str] = None
    ) -> None: ...
    
    async def create_node(
        self,
        node_type: str,
        properties: Dict[str, Any]
    ) -> str: ...
    
    async def create_edge(
        self,
        source_uuid: str,
        target_uuid: str,
        edge_type: str,
        properties: Dict[str, Any]
    ) -> str: ...
    
    async def get_node(
        self,
        uuid: str
    ) -> Optional[Dict[str, Any]]: ...
    
    async def get_edge(
        self,
        uuid: str
    ) -> Optional[Dict[str, Any]]: ...
    
    async def update_node(
        self,
        uuid: str,
        properties: Dict[str, Any]
    ) -> bool: ...
    
    async def update_edge(
        self,
        uuid: str,
        properties: Dict[str, Any]
    ) -> bool: ...
    
    async def delete_node(
        self,
        uuid: str
    ) -> bool: ...
    
    async def delete_edge(
        self,
        uuid: str
    ) -> bool: ...
    
    async def query(
        self,
        cypher: str,
        parameters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]: ...
    
    async def create_indices(self) -> None: ...
    
    async def create_constraints(self) -> None: ...
    
    async def close(self) -> None: ...

__all__ = ['Neo4jDriver']