from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from enum import Enum

from pydantic import BaseModel, Field

from graph_service.dto.common import Message


class SearchMethod(str, Enum):
    """Search method options."""

    fulltext = 'fulltext'
    similarity = 'similarity'
    bfs = 'bfs'
    hipporag = 'hipporag'  # Spreading activation through graph


class NodeReranker(str, Enum):
    """Node reranking strategies."""

    rrf = 'rrf'
    mmr = 'mmr'
    cross_encoder = 'cross_encoder'
    episode_mentions = 'episode_mentions'
    node_distance = 'node_distance'
    centrality_boosted = 'centrality_boosted'


class EdgeReranker(str, Enum):
    """Edge reranking strategies."""

    rrf = 'rrf'
    mmr = 'mmr'
    cross_encoder = 'cross_encoder'
    node_distance = 'node_distance'
    episode_mentions = 'episode_mentions'


class SearchConfig(BaseModel):
    """Advanced search configuration matching Rust service capabilities."""

    reranker: Optional[NodeReranker] = Field(
        default=NodeReranker.rrf, description='Reranking strategy'
    )
    search_methods: Optional[List[SearchMethod]] = Field(
        default=[SearchMethod.similarity],
        description='Search methods to use (similarity performs best for quality)',
    )
    centrality_boost_factor: Optional[float] = Field(
        default=1.0, description='Boost factor for centrality-based reranking'
    )
    mmr_lambda: Optional[float] = Field(
        default=0.5, description='Lambda parameter for MMR diversity (0=diversity, 1=relevance)'
    )
    similarity_threshold: Optional[float] = Field(
        default=0.3, description='Minimum similarity score for semantic matches'
    )
    bfs_max_depth: Optional[int] = Field(
        default=2, description='Maximum depth for breadth-first search traversal'
    )
    hipporag_max_hops: Optional[int] = Field(
        default=2, description='Maximum hops for HippoRAG spreading activation'
    )
    hipporag_decay: Optional[float] = Field(
        default=0.85, description='Score decay factor per hop in HippoRAG'
    )
    hipporag_seed_count: Optional[int] = Field(
        default=10, description='Number of HNSW seed nodes for HippoRAG'
    )
    bfs_beam_width: Optional[int] = Field(default=50, description='Top candidates per hop for BFS')
    bfs_per_hop_limit: Optional[int] = Field(
        default=100, description='Max neighbors per node expansion for BFS'
    )
    bfs_max_expansions: Optional[int] = Field(
        default=500, description='Total node expansions before stop for BFS'
    )
    bfs_max_visited: Optional[int] = Field(
        default=1000, description='Hard cap on visited set for BFS'
    )
    bfs_hub_degree_threshold: Optional[int] = Field(
        default=200, description='Nodes above this degree get limited expansion for BFS'
    )
    bfs_min_score_cutoff: Optional[float] = Field(
        default=0.1, description='Stop expanding below this score for BFS'
    )


class SearchQuery(BaseModel):
    group_ids: list[str] | None = Field(
        None, description='The group ids for the memories to search'
    )
    query: str
    max_facts: int = Field(default=10, description='The maximum number of facts to retrieve')
    config: Optional[SearchConfig] = Field(
        default=None, description='Advanced search configuration'
    )


class FactResult(BaseModel):
    uuid: str
    name: str
    fact: str
    valid_at: datetime | None
    invalid_at: datetime | None
    created_at: datetime
    expired_at: datetime | None

    class Config:
        json_encoders = {datetime: lambda v: v.astimezone(timezone.utc).isoformat()}


class SearchResults(BaseModel):
    facts: list[FactResult]


class GetMemoryRequest(BaseModel):
    group_id: str = Field(..., description='The group id of the memory to get')
    max_facts: int = Field(default=10, description='The maximum number of facts to retrieve')
    center_node_uuid: str | None = Field(
        ..., description='The uuid of the node to center the retrieval on'
    )
    messages: list[Message] = Field(
        ..., description='The messages to build the retrieval query from '
    )


class GetMemoryResponse(BaseModel):
    facts: list[FactResult] = Field(..., description='The facts that were retrieved from the graph')


class NodeSearchQuery(BaseModel):
    group_ids: list[str] | None = Field(None, description='The group ids for the nodes to search')
    query: str
    max_nodes: int = Field(default=10, description='The maximum number of nodes to retrieve')
    center_node_uuid: str | None = Field(
        None, description='Optional UUID of a node to center the search around'
    )
    entity: str = Field(default='', description='Optional entity type to filter results')
    config: Optional[SearchConfig] = Field(
        default=None, description='Advanced search configuration'
    )


class NodeResult(BaseModel):
    uuid: str
    name: str
    summary: str
    labels: list[str]
    group_id: str
    created_at: datetime
    attributes: Dict[str, Any]

    class Config:
        json_encoders = {datetime: lambda v: v.astimezone(timezone.utc).isoformat()}


class NodeSearchResults(BaseModel):
    nodes: list[NodeResult]


class EdgesByNodeResponse(BaseModel):
    edges: list[FactResult]
    source_edges: list[FactResult] = Field(..., description='Edges where this node is the source')
    target_edges: list[FactResult] = Field(..., description='Edges where this node is the target')
