"""Type stubs for graphiti_core.utils.maintenance module."""

from typing import List, Optional, Dict, Any
from graphiti_core.driver.base import BaseDriver

async def clear_data(
    driver: BaseDriver,
    group_ids: Optional[List[str]] = None
) -> int: ...

async def calculate_graph_statistics(
    driver: BaseDriver,
    group_id: Optional[str] = None
) -> Dict[str, Any]: ...

async def remove_duplicate_nodes(
    driver: BaseDriver,
    group_id: Optional[str] = None
) -> int: ...

async def remove_orphaned_edges(
    driver: BaseDriver,
    group_id: Optional[str] = None
) -> int: ...

__all__ = [
    'clear_data',
    'calculate_graph_statistics',
    'remove_duplicate_nodes',
    'remove_orphaned_edges',
]