"""Type stubs for graphiti_core.nodes module."""

from typing import Any, Dict, List, Optional, TypedDict
from datetime import datetime
from enum import Enum
from pydantic import BaseModel

class NodeAttributes(TypedDict, total=False):
    """Attributes that can be stored on nodes."""
    importance: float
    tags: List[str]
    metadata: Dict[str, Any]

class EpisodeType(str, Enum):
    """Types of episodes."""
    message = "message"
    event = "event"
    action = "action"
    observation = "observation"
    
class BaseNode(BaseModel):
    """Base class for all node types."""
    uuid: str
    group_id: str
    created_at: datetime
    name: str
    summary: Optional[str]
    
    class Config:
        arbitrary_types_allowed = True

class EntityNode(BaseNode):
    """Entity node representation."""
    labels: List[str]
    attributes: NodeAttributes
    
    def to_dict(self) -> Dict[str, Any]: ...
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'EntityNode': ...

class EpisodicNode(BaseNode):
    """Episodic node representation."""
    episode_type: EpisodeType
    episode_id: str
    source_description: str
    reference_time: datetime
    content: str
    attributes: NodeAttributes
    
    def to_dict(self) -> Dict[str, Any]: ...
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'EpisodicNode': ...

class CommunityNode(BaseNode):
    """Community node representation."""
    community_id: str
    member_ids: List[str]
    attributes: NodeAttributes
    
    def to_dict(self) -> Dict[str, Any]: ...
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CommunityNode': ...

__all__ = [
    'BaseNode',
    'EntityNode', 
    'EpisodicNode',
    'CommunityNode',
    'EpisodeType',
    'NodeAttributes',
]