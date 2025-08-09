"""Type stubs for graphiti_core.edges module."""

from typing import Any, Dict, List, Optional, TypedDict
from datetime import datetime
from pydantic import BaseModel

class EdgeAttributes(TypedDict, total=False):
    """Attributes that can be stored on edges."""
    weight: float
    confidence: float
    metadata: Dict[str, Any]

class BaseEdge(BaseModel):
    """Base class for all edge types."""
    uuid: str
    group_id: str
    source_uuid: str
    target_uuid: str
    created_at: datetime
    name: str
    summary: Optional[str]
    
    def __init__(self, **data: Any) -> None: ...
    
    class Config:
        arbitrary_types_allowed = True

class EntityEdge(BaseEdge):
    """Entity edge representation."""
    fact: Optional[str]
    episodes: List[str]
    attributes: EdgeAttributes
    source_node_uuid: str  # Alias for source_uuid
    target_node_uuid: str  # Alias for target_uuid
    valid_at: Optional[datetime]
    invalid_at: Optional[datetime]
    expired_at: Optional[datetime]
    
    def __init__(self, **data: Any) -> None: ...
    
    def to_dict(self) -> Dict[str, Any]: ...
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'EntityEdge': ...
    
    @classmethod
    async def get_by_uuid(cls, driver: Any, uuid: str) -> 'EntityEdge': ...
    
    @classmethod
    async def get_by_group_ids(cls, driver: Any, group_ids: List[str]) -> List['EntityEdge']: ...
    
    @classmethod
    async def get_by_node_uuid(cls, driver: Any, node_uuid: str) -> List['EntityEdge']: ...
    
    @classmethod
    async def get_by_uuids(cls, driver: Any, uuids: List[str]) -> List['EntityEdge']: ...
    
    @classmethod
    async def delete(cls, driver: Any, uuid: str) -> None: ...
    
    async def generate_embedding(self, embedder: Any) -> None: ...

class EpisodicEdge(BaseEdge):
    """Episodic edge representation."""
    episode_id: str
    reference_time: datetime
    attributes: EdgeAttributes
    
    def to_dict(self) -> Dict[str, Any]: ...
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'EpisodicEdge': ...

class CommunityEdge(BaseEdge):
    """Community edge representation."""
    community_id: str
    relationship_type: str
    attributes: EdgeAttributes
    
    def to_dict(self) -> Dict[str, Any]: ...
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CommunityEdge': ...

__all__ = [
    'BaseEdge',
    'EntityEdge',
    'EpisodicEdge', 
    'CommunityEdge',
    'EdgeAttributes',
]