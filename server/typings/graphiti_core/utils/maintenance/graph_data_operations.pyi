"""Type stubs for graphiti_core.utils.maintenance.graph_data_operations module."""

from typing import List, Optional
from graphiti_core.driver.base import BaseDriver

async def clear_data(
    driver: BaseDriver,
    group_ids: Optional[List[str]] = None
) -> int: ...

async def clear_nodes(
    driver: BaseDriver,
    group_ids: Optional[List[str]] = None
) -> int: ...

async def clear_edges(
    driver: BaseDriver,
    group_ids: Optional[List[str]] = None
) -> int: ...

__all__ = [
    'clear_data',
    'clear_nodes',
    'clear_edges',
]