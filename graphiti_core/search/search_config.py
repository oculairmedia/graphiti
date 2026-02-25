"""
Copyright 2024, Zep Software, Inc.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import os
from enum import Enum

from pydantic import BaseModel, Field

from graphiti_core.edges import EntityEdge
from graphiti_core.nodes import CommunityNode, EntityNode, EpisodicNode
from graphiti_core.search.search_utils import (
    DEFAULT_MIN_SCORE,
    DEFAULT_MMR_LAMBDA,
    MAX_SEARCH_DEPTH,
)

# Configurable via DEDUP_SEARCH_LIMIT env var (default: 10)
# Lower this to reduce token usage for rate-limited providers like Z.AI
DEFAULT_SEARCH_LIMIT = int(os.getenv('DEDUP_SEARCH_LIMIT', '10'))


class EdgeSearchMethod(Enum):
    cosine_similarity = 'cosine_similarity'
    bm25 = 'bm25'
    bfs = 'breadth_first_search'
    hipporag = 'hipporag'


class NodeSearchMethod(Enum):
    cosine_similarity = 'cosine_similarity'
    bm25 = 'bm25'
    bfs = 'breadth_first_search'
    hipporag = 'hipporag'
    community_boost = 'community_boost'


class EpisodeSearchMethod(Enum):
    bm25 = 'bm25'


class CommunitySearchMethod(Enum):
    cosine_similarity = 'cosine_similarity'
    bm25 = 'bm25'


class EdgeReranker(Enum):
    rrf = 'reciprocal_rank_fusion'
    node_distance = 'node_distance'
    episode_mentions = 'episode_mentions'
    mmr = 'mmr'
    cross_encoder = 'cross_encoder'
    centrality = 'centrality'


class NodeReranker(Enum):
    rrf = 'reciprocal_rank_fusion'
    node_distance = 'node_distance'
    episode_mentions = 'episode_mentions'
    mmr = 'mmr'
    cross_encoder = 'cross_encoder'
    centrality = 'centrality'


class EpisodeReranker(Enum):
    rrf = 'reciprocal_rank_fusion'
    cross_encoder = 'cross_encoder'


class CommunityReranker(Enum):
    rrf = 'reciprocal_rank_fusion'
    mmr = 'mmr'
    cross_encoder = 'cross_encoder'


class EdgeSearchConfig(BaseModel):
    search_methods: list[EdgeSearchMethod]
    reranker: EdgeReranker = Field(default=EdgeReranker.rrf)
    sim_min_score: float = Field(default=DEFAULT_MIN_SCORE)
    mmr_lambda: float = Field(default=DEFAULT_MMR_LAMBDA)
    centrality_boost_factor: float = Field(default=0.3)
    bfs_max_depth: int = Field(default=MAX_SEARCH_DEPTH)
    distance_max_hops: int = Field(default=MAX_SEARCH_DEPTH)
    hipporag_max_hops: int = Field(default=2)
    hipporag_decay: float = Field(default=0.85)
    hipporag_seed_count: int = Field(default=10)


class NodeSearchConfig(BaseModel):
    search_methods: list[NodeSearchMethod]
    reranker: NodeReranker = Field(default=NodeReranker.rrf)
    sim_min_score: float = Field(default=DEFAULT_MIN_SCORE)
    mmr_lambda: float = Field(default=DEFAULT_MMR_LAMBDA)
    centrality_boost_factor: float = Field(default=0.3)
    bfs_max_depth: int = Field(default=MAX_SEARCH_DEPTH)
    hipporag_max_hops: int = Field(default=2)
    hipporag_decay: float = Field(default=0.85)
    hipporag_seed_count: int = Field(default=10)
    community_boost_limit: int = Field(default=5)
    distance_max_hops: int = Field(default=MAX_SEARCH_DEPTH)


class EpisodeSearchConfig(BaseModel):
    search_methods: list[EpisodeSearchMethod]
    reranker: EpisodeReranker = Field(default=EpisodeReranker.rrf)
    sim_min_score: float = Field(default=DEFAULT_MIN_SCORE)
    mmr_lambda: float = Field(default=DEFAULT_MMR_LAMBDA)
    bfs_max_depth: int = Field(default=MAX_SEARCH_DEPTH)


class CommunitySearchConfig(BaseModel):
    search_methods: list[CommunitySearchMethod]
    reranker: CommunityReranker = Field(default=CommunityReranker.rrf)
    sim_min_score: float = Field(default=DEFAULT_MIN_SCORE)
    mmr_lambda: float = Field(default=DEFAULT_MMR_LAMBDA)
    bfs_max_depth: int = Field(default=MAX_SEARCH_DEPTH)


class SearchConfig(BaseModel):
    edge_config: EdgeSearchConfig | None = Field(default=None)
    node_config: NodeSearchConfig | None = Field(default=None)
    episode_config: EpisodeSearchConfig | None = Field(default=None)
    community_config: CommunitySearchConfig | None = Field(default=None)
    limit: int = Field(default=DEFAULT_SEARCH_LIMIT)
    reranker_min_score: float = Field(default=0)


class SearchResults(BaseModel):
    edges: list[EntityEdge]
    nodes: list[EntityNode]
    episodes: list[EpisodicNode]
    communities: list[CommunityNode]
