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

async def calculate_all_centralities(driver: BaseDriver, group_id: Optional[str] = None) -> Dict[str, float]: ...
async def calculate_betweenness_centrality(driver: BaseDriver, group_id: Optional[str] = None) -> Dict[str, float]: ...
async def calculate_degree_centrality(driver: BaseDriver, group_id: Optional[str] = None) -> Dict[str, float]: ...
async def calculate_pagerank(driver: BaseDriver, group_id: Optional[str] = None) -> Dict[str, float]: ...
async def store_centrality_scores(driver: BaseDriver, scores: Dict[str, float], metric_name: str) -> None: ...

__all__ = [
    'clear_data',
    'calculate_graph_statistics',
    'remove_duplicate_nodes',
    'remove_orphaned_edges',
    'calculate_all_centralities',
    'calculate_betweenness_centrality',
    'calculate_degree_centrality',
    'calculate_pagerank',
    'store_centrality_scores',
]