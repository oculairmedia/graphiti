"""Type stubs for graphiti_core.graphiti module."""

from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime
from graphiti_core.nodes import EntityNode, EpisodicNode, EpisodeType
from graphiti_core.edges import EntityEdge, EpisodicEdge

class AddEpisodeResults:
    """Results from adding an episode."""
    episode: EpisodicNode
    nodes: List[EntityNode]
    edges: List[EntityEdge]
    
    def model_dump(self, mode: str = 'json') -> Dict[str, Any]: ...

class Graphiti:
    """Main Graphiti class."""
    
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