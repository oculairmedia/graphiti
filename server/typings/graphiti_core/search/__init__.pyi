"""Type stubs for graphiti_core.search module."""

from typing import Dict, List, Optional, Any
from enum import Enum
from pydantic import BaseModel

class SearchMethod(str, Enum):
    """Search method enumeration."""
    bm25 = "bm25"
    semantic = "semantic"
    hybrid = "hybrid"
    mmr = "mmr"

class SearchConfig(BaseModel):
    """Configuration for search operations."""
    bm25_weight: float = 0.5
    semantic_weight: float = 0.5
    mmr_lambda: float = 0.5
    rerank: bool = False
    rerank_threshold: float = 0.5

class SearchFilters(BaseModel):
    """Filters for search operations."""
    group_ids: Optional[List[str]] = None
    labels: Optional[List[str]] = None
    created_after: Optional[str] = None
    created_before: Optional[str] = None
    
class SearchResult(BaseModel):
    """Search result wrapper."""
    uuid: str
    score: float
    node: Dict[str, Any]

__all__ = [
    'SearchMethod',
    'SearchConfig',
    'SearchFilters',
    'SearchResult',
]