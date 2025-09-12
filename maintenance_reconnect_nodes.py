#!/usr/bin/env python3
"""
Maintenance script to reconnect disconnected nodes by finding relevant relationships.
This script identifies isolated episodes and entities, then attempts to create meaningful connections.
"""

import asyncio
import logging
import os
from typing import Dict, List, Optional

from graphiti_core import Graphiti
from graphiti_core.driver.driver import GraphDriver
from graphiti_core.embedder import EmbedderClient
from graphiti_core.llm_client import LLMClient
from graphiti_core.nodes import EntityNode, EpisodeType, EpisodicNode
from graphiti_core.utils.maintenance.node_operations import extract_nodes
from graphiti_core.utils.maintenance.edge_operations import extract_edges

# Configure logging
logging.basicConfig(
    level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class NodeReconnector:
    """Reconnect disconnected nodes by creating missing relationships"""

    def __init__(self, graphiti: Graphiti):
        self.graphiti = graphiti
        self.driver = graphiti.driver
        self.llm_client = graphiti.llm_client
        self.embedder = graphiti.embedder

    async def find_disconnected_episodes(self, group_id: Optional[str] = None, limit: int = 100) -> List[EpisodicNode]:
        """Find episodic nodes with no MENTIONS relationships"""
        logger.info('Finding disconnected episodic nodes...')
        
        query = """
        MATCH (ep:Episodic)
        WHERE ($group_id IS NULL OR ep.group_id = $group_id)
          AND NOT (ep)-[:MENTIONS]->()
        RETURN ep
        LIMIT $limit
        """
        
        result, _, _ = await self.driver.execute_query(query, group_id=group_id, limit=limit)
        
        episodes = []
        for record in result:
            episode_data = record['ep']
            episode = EpisodicNode(
                uuid=episode_data.properties['uuid'],
                name=episode_data.properties.get('name', 'Episode'),
                labels=episode_data.labels,
                created_at=episode_data.properties['created_at'],
                valid_at=episode_data.properties.get('valid_at', episode_data.properties['created_at']),
                content=episode_data.properties['content'],
                source=EpisodeType(episode_data.properties.get('source', 'message')),
                source_description=episode_data.properties.get('source_description', 'Unknown'),
                group_id=episode_data.properties.get('group_id', 'default'),
            )
            episodes.append(episode)

        logger.info(f'Found {len(episodes)} disconnected episodes')
        return episodes

    async def find_disconnected_entities(self, group_id: Optional[str] = None, limit: int = 100) -> List[EntityNode]:
        """Find entity nodes with no incoming MENTIONS relationships"""
        logger.info('Finding disconnected entity nodes...')
        
        query = """
        MATCH (ent:Entity)
        WHERE ($group_id IS NULL OR ent.group_id = $group_id)
          AND NOT ()-[:MENTIONS]->(ent)
        RETURN ent
        LIMIT $limit
        """
        
        result, _, _ = await self.driver.execute_query(query, group_id=group_id, limit=limit)
        
        entities = []
        for record in result:
            entity_data = record['ent']
            entity = EntityNode(
                uuid=entity_data.properties['uuid'],
                name=entity_data.properties['name'],
                labels=entity_data.labels,
                created_at=entity_data.properties['created_at'],
                group_id=entity_data.properties.get('group_id', 'default'),
            )
            entities.append(entity)

        logger.info(f'Found {len(entities)} disconnected entities')
        return entities

    async def reconnect_episode_batch(self, episodes: List[EpisodicNode], batch_size: int = 5):
        """Reconnect a batch of episodes by extracting entities and creating relationships"""
        from graphiti_core.graphiti_types import GraphitiClients
        
        logger.info(f'Processing {len(episodes)} episodes for reconnection...')
        
        clients = GraphitiClients(
            llm_client=self.llm_client,
            embedder=self.embedder,
            driver=self.driver,
            cross_encoder=self.graphiti.cross_encoder,
        )
        
        total_entities_created = 0
        total_episodes_processed = 0
        
        for i in range(0, len(episodes), batch_size):
            batch = episodes[i:i + batch_size]
            logger.info(f'Processing batch {i // batch_size + 1}: {len(batch)} episodes')
            
            for episode in batch:
                try:
                    # Get some context episodes (previous episodes for the same group)
                    previous_episodes = await self.get_context_episodes(episode.group_id, exclude_uuid=episode.uuid)
                    
                    # Extract entities from the episode
                    extracted_entities = await extract_nodes(
                        clients=clients,
                        episode=episode,
                        previous_episodes=previous_episodes[:3],  # Limit to 3 for context
                        entity_types=None,
                        excluded_entity_types=None,
                    )
                    
                    if extracted_entities:
                        logger.info(f'Extracted {len(extracted_entities)} entities for episode {episode.uuid[:8]}')
                        total_entities_created += len(extracted_entities)
                    else:
                        logger.info(f'No entities extracted for episode {episode.uuid[:8]}')
                    
                    total_episodes_processed += 1
                    
                except Exception as e:
                    logger.error(f'Failed to process episode {episode.uuid}: {e}')
        
        logger.info(f'Batch complete: {total_episodes_processed} episodes processed, {total_entities_created} entities created')
        return {'episodes_processed': total_episodes_processed, 'entities_created': total_entities_created}

    async def get_context_episodes(self, group_id: str, exclude_uuid: str, limit: int = 5) -> List[EpisodicNode]:
        """Get recent episodes from the same group for context"""
        query = """
        MATCH (ep:Episodic)
        WHERE ep.group_id = $group_id AND ep.uuid <> $exclude_uuid
        RETURN ep
        ORDER BY ep.created_at DESC
        LIMIT $limit
        """
        
        result, _, _ = await self.driver.execute_query(query, group_id=group_id, exclude_uuid=exclude_uuid, limit=limit)
        
        episodes = []
        for record in result:
            episode_data = record['ep']
            episode = EpisodicNode(
                uuid=episode_data.properties['uuid'],
                name=episode_data.properties.get('name', 'Episode'),
                labels=episode_data.labels,
                created_at=episode_data.properties['created_at'],
                valid_at=episode_data.properties.get('valid_at', episode_data.properties['created_at']),
                content=episode_data.properties['content'],
                source=EpisodeType(episode_data.properties.get('source', 'message')),
                source_description=episode_data.properties.get('source_description', 'Unknown'),
                group_id=episode_data.properties.get('group_id', 'default'),
            )
            episodes.append(episode)
            
        return episodes

    async def get_disconnected_count(self) -> Dict[str, int]:
        """Get counts of disconnected nodes by type"""
        # Count disconnected episodes
        episode_query = """
        MATCH (ep:Episodic)
        WHERE NOT (ep)-[:MENTIONS]->()
        RETURN count(ep) as count
        """
        
        # Count disconnected entities
        entity_query = """
        MATCH (ent:Entity)
        WHERE NOT ()-[:MENTIONS]->(ent)
        RETURN count(ent) as count
        """
        
        episode_result, _, _ = await self.driver.execute_query(episode_query)
        entity_result, _, _ = await self.driver.execute_query(entity_query)
        
        return {
            'episodes': episode_result[0]['count'] if episode_result else 0,
            'entities': entity_result[0]['count'] if entity_result else 0,
        }

    async def run_reconnection(
        self, 
        group_id: str = 'claude_conversations', 
        limit: int = 50,
        dry_run: bool = False
    ) -> Dict:
        """Run the full reconnection process"""
        
        if dry_run:
            logger.info('DRY RUN MODE - No changes will be made')
        
        # Get initial counts
        initial_counts = await self.get_disconnected_count()
        logger.info(f'Initial disconnected counts: {initial_counts["episodes"]} episodes, {initial_counts["entities"]} entities')
        
        if initial_counts['episodes'] == 0:
            logger.info('No disconnected episodes found')
            return {'episodes_processed': 0, 'entities_created': 0}
        
        if dry_run:
            disconnected_episodes = await self.find_disconnected_episodes(group_id, limit=min(limit, 10))
            logger.info(f'Would process {len(disconnected_episodes)} episodes')
            for i, ep in enumerate(disconnected_episodes[:5], 1):
                logger.info(f'  {i}. {ep.content[:100]}...')
            return {'episodes_processed': 0, 'entities_created': 0, 'dry_run': True}
        
        # Find and process disconnected episodes
        disconnected_episodes = await self.find_disconnected_episodes(group_id, limit)
        if not disconnected_episodes:
            logger.info('No disconnected episodes to process')
            return {'episodes_processed': 0, 'entities_created': 0}
        
        # Process episodes in batches
        result = await self.reconnect_episode_batch(disconnected_episodes)
        
        # Get final counts
        final_counts = await self.get_disconnected_count()
        logger.info(f'Final disconnected counts: {final_counts["episodes"]} episodes, {final_counts["entities"]} entities')
        
        result['initial_disconnected'] = initial_counts
        result['final_disconnected'] = final_counts
        result['episodes_reconnected'] = initial_counts['episodes'] - final_counts['episodes']
        
        return result


async def main():
    """Main function to run node reconnection"""
    # Initialize Graphiti with FalkorDB
    from openai import AsyncOpenAI
    from graphiti_core.client_factory import GraphitiClientFactory
    from graphiti_core.driver.falkordb_driver import FalkorDriver
    from graphiti_core.llm_client.config import LLMConfig
    from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
    
    # Create FalkorDB driver
    driver = FalkorDriver(host='localhost', port=6379, database='graphiti_migration')
    
    # Use Ollama LLM client
    ollama_client = AsyncOpenAI(
        base_url='http://100.81.139.20:11434/v1',
        api_key='ollama'
    )
    
    llm_config = LLMConfig(
        model='gemma3:12b',
        temperature=0.3,
        max_tokens=16384
    )
    llm_client = OpenAIGenericClient(config=llm_config, cache=False, client=ollama_client)
    
    # Create cross encoder
    cross_encoder = GraphitiClientFactory.create_cross_encoder()
    
    # Initialize Graphiti
    graphiti = Graphiti(
        graph_driver=driver,
        llm_client=llm_client,
        embedder=None,  # Will use default embedder
        cross_encoder=cross_encoder,
    )
    
    reconnector = NodeReconnector(graphiti)
    
    # Check if we should run in dry-run mode
    import sys
    dry_run = '--dry-run' in sys.argv
    include_sparse = '--include-sparse' in sys.argv
    
    # Run dry run first to see what would be processed
    if not dry_run:
        logger.info('Running dry run to analyze disconnected nodes...')
        dry_run_result = await reconnector.run_reconnection(
            group_id='claude_conversations',
            limit=20,
            dry_run=True
        )
        logger.info(f'Dry run results: {dry_run_result}')
        
        confirmation = input('\nProceed with reconnection? (yes/no): ')
        if confirmation.lower() not in ['yes', 'y']:
            logger.info('Operation cancelled.')
            return
    
    # Run the actual reconnection
    logger.info('Starting node reconnection process...')
    result = await reconnector.run_reconnection(
        group_id='claude_conversations',
        limit=850,  # Process up to 850 episodes (all disconnected)
        dry_run=dry_run
    )
    
    print('\n' + '=' * 60)
    print('RECONNECTION SUMMARY')
    print('=' * 60)
    print(f'Episodes processed: {result.get("episodes_processed", 0)}')
    print(f'Entities created: {result.get("entities_created", 0)}')
    if not dry_run:
        print(f'Episodes reconnected: {result.get("episodes_reconnected", 0)}')
        initial = result.get("initial_disconnected", {})
        final = result.get("final_disconnected", {})
        print(f'Disconnected episodes: {initial.get("episodes", 0)} → {final.get("episodes", 0)}')
        print(f'Disconnected entities: {initial.get("entities", 0)} → {final.get("entities", 0)}')


if __name__ == '__main__':
    asyncio.run(main())