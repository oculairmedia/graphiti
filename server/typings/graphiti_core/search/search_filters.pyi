"""Type stubs for graphiti_core.search.search_filters module."""

from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel

class SearchFilters(BaseModel):
    """Filters for search operations."""
    group_ids: Optional[List[str]] = None
    labels: Optional[List[str]] = None
    created_after: Optional[datetime] = None
    created_before: Optional[datetime] = None
    node_types: Optional[List[str]] = None
    min_importance: Optional[float] = None
    max_importance: Optional[float] = None
    
    def to_cypher_conditions(self) -> str: ...

__all__ = ['SearchFilters']