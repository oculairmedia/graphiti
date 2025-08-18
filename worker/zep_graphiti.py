"""
ZepGraphiti - Extended Graphiti class with additional methods.
"""

import logging
from graphiti_core import Graphiti
from graphiti_core.nodes import EntityNode

logger = logging.getLogger(__name__)


class ZepGraphiti(Graphiti):
    """Extended Graphiti class with additional entity management methods"""
    
    async def save_entity_node(self, name: str, uuid: str, group_id: str, summary: str = '') -> EntityNode:
        """
        Save an entity node to the graph.
        
        Args:
            name: Name of the entity
            uuid: UUID of the entity
            group_id: Group ID for the entity
            summary: Summary of the entity
            
        Returns:
            The created EntityNode
        """
        new_node = EntityNode(
            name=name,
            uuid=uuid,
            group_id=group_id,
            summary=summary,
        )
        await new_node.generate_name_embedding(self.embedder)
        await new_node.save(self.driver)
        return new_node