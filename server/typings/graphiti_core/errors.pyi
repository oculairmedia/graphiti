"""Type stubs for graphiti_core.errors module."""

from typing import Optional

class GraphitiError(Exception):
    """Base exception for Graphiti errors."""
    message: str
    
    def __init__(self, message: str) -> None: ...

class NodeNotFoundError(GraphitiError):
    """Exception raised when a node is not found."""
    uuid: str
    
    def __init__(self, uuid: str, message: Optional[str] = None) -> None: ...

class EdgeNotFoundError(GraphitiError):
    """Exception raised when an edge is not found."""
    uuid: str
    
    def __init__(self, uuid: str, message: Optional[str] = None) -> None: ...

class GroupsEdgesNotFoundError(GraphitiError):
    """Exception raised when edges for a group are not found."""
    group_id: str
    
    def __init__(self, group_id: str, message: Optional[str] = None) -> None: ...

class InvalidQueryError(GraphitiError):
    """Exception raised for invalid queries."""
    query: str
    
    def __init__(self, query: str, message: Optional[str] = None) -> None: ...

class DatabaseConnectionError(GraphitiError):
    """Exception raised for database connection issues."""
    
    def __init__(self, message: str) -> None: ...

__all__ = [
    'GraphitiError',
    'NodeNotFoundError',
    'EdgeNotFoundError',
    'GroupsEdgesNotFoundError',
    'InvalidQueryError',
    'DatabaseConnectionError',
]