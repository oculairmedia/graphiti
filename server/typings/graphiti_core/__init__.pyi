"""Type stubs for graphiti_core library."""

from typing import Any, Dict, List, Optional, Tuple, TypedDict
from datetime import datetime
from graphiti_core.nodes import EntityNode, EpisodicNode, EpisodeType
from graphiti_core.edges import EntityEdge, EpisodicEdge
from graphiti_core.llm_client import LLMClient, LLMConfig, OpenAIClient
from graphiti_core.embedder import EmbedderClient, OpenAIEmbedder, OpenAIEmbedderConfig
from graphiti_core.driver.base import BaseDriver
from graphiti_core.search import SearchMethod, SearchConfig

class AddEpisodeResults:
    """Results from adding an episode."""
    episode: EpisodicNode
    nodes: List[EntityNode]
    edges: List[EntityEdge]
    
    def model_dump(self, mode: str = 'json') -> Dict[str, Any]: ...

class GraphitiConfig(TypedDict, total=False):
    """Configuration for Graphiti instance."""
    llm_client: LLMClient
    embedder: EmbedderClient
    driver: BaseDriver
    database: str
    user: str
    password: str
    uri: str
    host: str
    port: int

class Graphiti:
    """Main Graphiti class for graph operations."""
    
    def __init__(
        self,
        driver: BaseDriver,
        llm_client: LLMClient,
        embedder: EmbedderClient,
        database: Optional[str] = None
    ) -> None: ...
    
    async def initialize(self) -> None: ...
    
    async def add_episode(
        self,
        name: str,
        episode_body: str,
        source_description: str,
        reference_time: datetime,
        source: EpisodeType = ...,
        group_id: Optional[str] = None,
        uuid: Optional[str] = None,
        update_communities: bool = False,
        entity_types: Optional[Dict[str, Any]] = None,
        excluded_entity_types: Optional[List[str]] = None,
        previous_episode_uuids: Optional[List[str]] = None,
        edge_types: Optional[Dict[str, Any]] = None,
        edge_type_map: Optional[Dict[Tuple[str, str], List[str]]] = None
    ) -> AddEpisodeResults: ...
    
    async def retrieve_episodes(
        self,
        query: str,
        center_node_uuid: Optional[str] = None,
        num_episodes: int = 10,
        num_edge_types: int = 10,
        max_distance: int = 2,
        group_ids: Optional[List[str]] = None
    ) -> List[EpisodicNode]: ...
    
    async def search(
        self,
        query: str,
        group_ids: Optional[List[str]] = None,
        method: Optional[SearchMethod] = None,
        config: Optional[SearchConfig] = None,
        num_results: int = 10
    ) -> List[EntityNode]: ...
    
    async def build_indices_and_constraints(self) -> None: ...
    
    async def close(self) -> None: ...
    
    driver: BaseDriver
    llm_client: LLMClient
    embedder: EmbedderClient

__all__ = [
    'Graphiti',
    'GraphitiConfig',
]