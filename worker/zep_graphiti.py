"""
ZepGraphiti - Extended Graphiti class with additional methods.
"""

import logging
from typing import Optional
from graphiti_core import Graphiti
from graphiti_core.nodes import EntityNode, EpisodicNode
from graphiti_core.edges import EntityEdge
from graphiti_core.errors import GroupsEdgesNotFoundError, EdgeNotFoundError, NodeNotFoundError

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
    
    async def delete_group(self, group_id: str) -> None:
        """
        Delete all data for a specific group.
        
        Args:
            group_id: The group ID to delete
        """
        try:
            edges = await EntityEdge.get_by_group_ids(self.driver, [group_id])
        except GroupsEdgesNotFoundError:
            logger.warning(f'No edges found for group {group_id}')
            edges = []

        nodes = await EntityNode.get_by_group_ids(self.driver, [group_id])
        episodes = await EpisodicNode.get_by_group_ids(self.driver, [group_id])

        for edge in edges:
            await EntityEdge.delete(self.driver, edge.uuid)

        for node in nodes:
            await EntityNode.delete(self.driver, node.uuid)

        for episode in episodes:
            await episode.delete(self.driver)
            
        logger.info(f"Deleted group {group_id}: {len(edges)} edges, {len(nodes)} nodes, {len(episodes)} episodes")

    async def delete_entity_edge(self, uuid: str) -> None:
        """
        Delete an entity edge by UUID.
        
        Args:
            uuid: The UUID of the edge to delete
            
        Raises:
            EdgeNotFoundError: If the edge doesn't exist
        """
        try:
            edge = await EntityEdge.get_by_uuid(self.driver, uuid)
            await EntityEdge.delete(self.driver, edge.uuid)
            logger.info(f"Deleted entity edge {uuid}")
        except EdgeNotFoundError as e:
            logger.error(f"Edge not found: {uuid}")
            raise

    async def delete_episodic_node(self, uuid: str) -> None:
        """
        Delete an episodic node by UUID.
        
        Args:
            uuid: The UUID of the episode to delete
            
        Raises:
            NodeNotFoundError: If the episode doesn't exist
        """
        try:
            episode = await EpisodicNode.get_by_uuid(self.driver, uuid)
            await episode.delete(self.driver)
            logger.info(f"Deleted episodic node {uuid}")
        except NodeNotFoundError as e:
            logger.error(f"Episode not found: {uuid}")
            raise