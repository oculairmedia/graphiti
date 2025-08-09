"""
Python client for the Rust search service.

This client provides a high-performance alternative to the Python search implementation
by delegating search operations to the Rust service.
"""

import asyncio
import json
from typing import Any, Dict, List, Optional
from uuid import UUID

import aiohttp
from pydantic import BaseModel, Field

from graphiti_core.nodes import EntityNode
from graphiti_core.edges import EntityEdge, EpisodicEdge
from graphiti_core.search.search_config import SearchConfig
from graphiti_core.search.search_results import SearchResults


class RustSearchClient:
    """Client for interacting with the Rust search service."""

    def __init__(
        self,
        base_url: str = "http://localhost:3004",
        timeout: int = 30,
    ):
        """
        Initialize the Rust search client.

        Args:
            base_url: Base URL of the Rust search service
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self._session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        """Async context manager entry."""
        self._session = aiohttp.ClientSession(timeout=self.timeout)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self._session:
            await self._session.close()

    @property
    def session(self) -> aiohttp.ClientSession:
        """Get or create the aiohttp session."""
        if self._session is None:
            self._session = aiohttp.ClientSession(timeout=self.timeout)
        return self._session

    async def health_check(self) -> Dict[str, Any]:
        """
        Check the health of the Rust search service.

        Returns:
            Health status information
        """
        async with self.session.get(f"{self.base_url}/health") as response:
            response.raise_for_status()
            return await response.json()

    async def search(
        self,
        query: str,
        config: SearchConfig,
        filters: Optional[Dict[str, Any]] = None,
        center_node_uuid: Optional[UUID] = None,
        bfs_origin_node_uuids: Optional[List[UUID]] = None,
        query_vector: Optional[List[float]] = None,
    ) -> SearchResults:
        """
        Execute a search request against the Rust service.

        Args:
            query: Search query string
            config: Search configuration
            filters: Optional search filters
            center_node_uuid: Optional center node for distance-based reranking
            bfs_origin_node_uuids: Optional origin nodes for BFS
            query_vector: Optional pre-computed query embedding

        Returns:
            SearchResults containing edges, nodes, episodes, and communities
        """
        # Build request payload
        payload = {
            "query": query,
            "config": self._serialize_config(config),
            "filters": filters or {},
        }

        if center_node_uuid:
            payload["center_node_uuid"] = str(center_node_uuid)

        if bfs_origin_node_uuids:
            payload["bfs_origin_node_uuids"] = [
                str(uuid) for uuid in bfs_origin_node_uuids
            ]

        if query_vector:
            payload["query_vector"] = query_vector

        # Make request
        async with self.session.post(
            f"{self.base_url}/search",
            json=payload,
        ) as response:
            response.raise_for_status()
            data = await response.json()

        # Convert response to SearchResults
        return self._parse_search_results(data)

    async def search_edges(
        self,
        query: str,
        config: Dict[str, Any],
        filters: Optional[Dict[str, Any]] = None,
        query_vector: Optional[List[float]] = None,
    ) -> List[EntityEdge]:
        """
        Search for edges using the specialized edge endpoint.

        Args:
            query: Search query string
            config: Edge search configuration
            filters: Optional search filters
            query_vector: Optional pre-computed query embedding

        Returns:
            List of matching edges
        """
        payload = {
            "query": query,
            "config": config,
            "filters": filters,
            "query_vector": query_vector,
        }

        async with self.session.post(
            f"{self.base_url}/search/edges",
            json=payload,
        ) as response:
            response.raise_for_status()
            data = await response.json()

        return [self._parse_edge(edge) for edge in data["edges"]]

    async def search_nodes(
        self,
        query: str,
        config: Dict[str, Any],
        filters: Optional[Dict[str, Any]] = None,
        query_vector: Optional[List[float]] = None,
    ) -> List[EntityNode]:
        """
        Search for nodes using the specialized node endpoint.

        Args:
            query: Search query string
            config: Node search configuration
            filters: Optional search filters
            query_vector: Optional pre-computed query embedding

        Returns:
            List of matching nodes
        """
        payload = {
            "query": query,
            "config": config,
            "filters": filters,
            "query_vector": query_vector,
        }

        async with self.session.post(
            f"{self.base_url}/search/nodes",
            json=payload,
        ) as response:
            response.raise_for_status()
            data = await response.json()

        return [self._parse_node(node) for node in data["nodes"]]

    def _serialize_config(self, config: SearchConfig) -> Dict[str, Any]:
        """Convert SearchConfig to JSON-serializable dict."""
        return {
            "edge_config": (
                {
                    "search_methods": [m.value for m in config.edge_config.search_methods],
                    "reranker": config.edge_config.reranker.value,
                    "bfs_max_depth": config.edge_config.bfs_max_depth,
                    "sim_min_score": config.edge_config.sim_min_score,
                    "mmr_lambda": config.edge_config.mmr_lambda,
                }
                if config.edge_config
                else None
            ),
            "node_config": (
                {
                    "search_methods": [m.value for m in config.node_config.search_methods],
                    "reranker": config.node_config.reranker.value,
                    "bfs_max_depth": config.node_config.bfs_max_depth,
                    "sim_min_score": config.node_config.sim_min_score,
                    "mmr_lambda": config.node_config.mmr_lambda,
                }
                if config.node_config
                else None
            ),
            "episode_config": (
                {"reranker": config.episode_config.reranker.value}
                if config.episode_config
                else None
            ),
            "community_config": (
                {
                    "reranker": config.community_config.reranker.value,
                    "sim_min_score": config.community_config.sim_min_score,
                    "mmr_lambda": config.community_config.mmr_lambda,
                }
                if config.community_config
                else None
            ),
            "limit": config.limit,
            "reranker_min_score": config.reranker_config.reranker_min_score,
        }

    def _parse_search_results(self, data: Dict[str, Any]) -> SearchResults:
        """Parse JSON response into SearchResults."""
        edges = [self._parse_edge(e) for e in data.get("edges", [])]
        nodes = [self._parse_node(n) for n in data.get("nodes", [])]
        episodes = [self._parse_episode(e) for e in data.get("episodes", [])]
        communities = data.get("communities", [])  # TODO: Parse communities

        return SearchResults(
            edges=edges,
            nodes=nodes,
            episodes=episodes,
            communities=communities,
        )

    def _parse_edge(self, data: Dict[str, Any]) -> EntityEdge:
        """Parse edge data from JSON."""
        return EntityEdge(
            uuid=data["uuid"],
            source_node_uuid=data["source_node_uuid"],
            target_node_uuid=data["target_node_uuid"],
            fact=data["fact"],
            created_at=data["created_at"],
            episodes=data.get("episodes", []),
            group_id=data.get("group_id"),
        )

    def _parse_node(self, data: Dict[str, Any]) -> EntityNode:
        """Parse node data from JSON."""
        return EntityNode(
            uuid=data["uuid"],
            name=data["name"],
            label=data["node_type"],
            summary=data.get("summary"),
            created_at=data["created_at"],
            group_id=data.get("group_id"),
        )

    def _parse_episode(self, data: Dict[str, Any]) -> EpisodicEdge:
        """Parse episode data from JSON."""
        return EpisodicEdge(
            uuid=data["uuid"],
            source_node_uuid=data.get("source_node_uuid"),
            target_node_uuid=data.get("target_node_uuid"),
            content=data["content"],
            created_at=data["created_at"],
            group_id=data.get("group_id"),
        )


# Convenience function for one-off searches
async def rust_search(
    query: str,
    config: SearchConfig,
    base_url: str = "http://localhost:3004",
    **kwargs,
) -> SearchResults:
    """
    Execute a search using the Rust service.

    This is a convenience function for one-off searches without
    managing the client lifecycle.

    Args:
        query: Search query string
        config: Search configuration
        base_url: Base URL of the Rust search service
        **kwargs: Additional search parameters

    Returns:
        SearchResults
    """
    async with RustSearchClient(base_url) as client:
        return await client.search(query, config, **kwargs)