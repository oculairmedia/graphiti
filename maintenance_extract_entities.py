#!/usr/bin/env python3
"""
Maintenance script to extract entities from episodic nodes that have no entities.
This fixes the issue where episodes were created without entity extraction.
"""

import asyncio
import logging
from datetime import datetime
from typing import List, Dict, Optional
import os

from graphiti_core import Graphiti
from graphiti_core.nodes import EpisodicNode, EntityNode, EpisodeType
from graphiti_core.driver.driver import GraphDriver
from graphiti_core.llm_client import LLMClient
from graphiti_core.utils.maintenance.node_operations import extract_nodes
from graphiti_core.embedder import EmbedderClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class EntityExtractor:
    """Extract entities from existing episodic nodes"""
    
    def __init__(self, graphiti: Graphiti):
        self.graphiti = graphiti
        self.driver = graphiti.driver
        self.llm_client = graphiti.llm_client
        self.embedder = graphiti.embedder
        
    async def find_episodes_without_entities(self, 
                                           group_id: Optional[str] = None,
                                           limit: int = 100) -> List[EpisodicNode]:
        """Find episodic nodes that have no associated entities"""
        logger.info("Finding episodic nodes without entities...")
        
        # Get all episodes with entities first
        query_with_entities = """
        MATCH (ep:Episodic)-[:MENTIONS]->(e:Entity)
        WHERE ($group_id IS NULL OR ep.group_id = $group_id)
        RETURN DISTINCT ep.uuid as uuid
        """
        
        records, _, _ = await self.driver.execute_query(
            query_with_entities,
            group_id=group_id
        )
        
        episodes_with_entities = {r['uuid'] for r in records}
        logger.info(f"Found {len(episodes_with_entities)} episodes with entities")
        
        # Get episodes without entities directly
        query_without_entities = """
        MATCH (ep:Episodic)
        WHERE ($group_id IS NULL OR ep.group_id = $group_id)
        AND NOT (ep)-[:MENTIONS]->(:Entity)
        RETURN ep
        ORDER BY ep.created_at DESC
        LIMIT $limit
        """
        
        records, _, _ = await self.driver.execute_query(
            query_without_entities,
            group_id=group_id,
            limit=limit
        )
        
        # Convert results directly since we're already filtering for episodes without entities
        episodes_without_entities = []
        for record in records:
            episode_data = record.get('ep')
            if episode_data:
                # episode_data is a Node object in FalkorDB
                uuid = episode_data.properties.get('uuid')
                # Convert to EpisodicNode
                episode = EpisodicNode(
                    uuid=uuid,
                    name=episode_data.properties.get('name'),
                    group_id=episode_data.properties.get('group_id'),
                    content=episode_data.properties.get('content'),
                    created_at=episode_data.properties.get('created_at'),
                    valid_at=episode_data.properties.get('valid_at', episode_data.properties.get('created_at')),
                    source=EpisodeType(episode_data.properties.get('source', 'message')),
                    source_description=episode_data.properties.get('source_description', 'Unknown')
                )
                episodes_without_entities.append(episode)
                
        logger.info(f"Found {len(episodes_without_entities)} episodes without entities")
        return episodes_without_entities
        
    async def extract_entities_from_episode(self, 
                                          episode: EpisodicNode,
                                          previous_episodes: List[EpisodicNode]) -> List[EntityNode]:
        """Extract entities from a single episode"""
        try:
            # Create context for entity extraction
            from graphiti_core.graphiti_types import GraphitiClients
            
            clients = GraphitiClients(
                llm_client=self.llm_client,
                embedder=self.embedder,
                driver=self.driver,
                cross_encoder=self.graphiti.cross_encoder  # Get from graphiti instance
            )
            
            # Extract entities
            extracted_nodes = await extract_nodes(
                clients=clients,
                episode=episode,
                previous_episodes=previous_episodes,
                entity_types=None,  # Use default entity types
                excluded_entity_types=None
            )
            
            return extracted_nodes
            
        except Exception as e:
            logger.error(f"Error extracting entities from episode {episode.uuid}: {e}")
            return []
            
    async def get_orphan_count(self) -> int:
        """Get count of episodes without entities"""
        query = """
        MATCH (ep:Episodic)
        WHERE NOT (ep)-[:MENTIONS]->(:Entity)
        RETURN count(ep) as count
        """
        records, _, _ = await self.driver.execute_query(query)
        return records[0]['count'] if records else 0
        
    async def process_episodes_batch(self, 
                                   episodes: List[EpisodicNode],
                                   batch_size: int = 5) -> Dict[str, any]:
        """Process a batch of episodes to extract entities"""
        results = {
            'processed': 0,
            'entities_created': 0,
            'failed': 0,
            'entities_by_episode': {}
        }
        
        for i in range(0, len(episodes), batch_size):
            batch = episodes[i:i + batch_size]
            logger.info(f"Processing batch {i//batch_size + 1} of {(len(episodes) + batch_size - 1)//batch_size}")
            
            for episode in batch:
                try:
                    # Get previous episodes for context (last 5)
                    previous_episodes = []
                    if i > 0:
                        # Simple approach - use previous episodes from our list
                        start_idx = max(0, episodes.index(episode) - 5)
                        previous_episodes = episodes[start_idx:episodes.index(episode)]
                    
                    # Extract entities
                    entities = await self.extract_entities_from_episode(episode, previous_episodes)
                    
                    if entities:
                        # Save entities and create MENTIONS edges
                        for entity in entities:
                            await entity.save(self.driver)
                            
                            # Create MENTIONS edge
                            mentions_query = """
                            MATCH (ep:Episodic {uuid: $episode_uuid})
                            MATCH (e:Entity {uuid: $entity_uuid})
                            MERGE (ep)-[:MENTIONS]->(e)
                            """
                            await self.driver.execute_query(
                                mentions_query,
                                episode_uuid=episode.uuid,
                                entity_uuid=entity.uuid
                            )
                        
                        results['entities_created'] += len(entities)
                        results['entities_by_episode'][episode.uuid] = [e.name for e in entities]
                        logger.info(f"Created {len(entities)} entities for episode: {episode.content[:100]}...")
                    
                    results['processed'] += 1
                    
                except Exception as e:
                    logger.error(f"Failed to process episode {episode.uuid}: {e}")
                    results['failed'] += 1
                    
        return results
        
    async def run_extraction(self,
                           group_id: Optional[str] = None,
                           limit: int = 100,
                           dry_run: bool = False) -> Dict[str, any]:
        """Run the entity extraction process"""
        start_time = datetime.now()
        
        # Find episodes without entities
        episodes = await self.find_episodes_without_entities(group_id, limit)
        
        if not episodes:
            logger.info("No episodes without entities found")
            return {
                "duration": str(datetime.now() - start_time),
                "episodes_found": 0,
                "entities_created": 0,
                "dry_run": dry_run
            }
            
        if dry_run:
            # Just analyze what would be processed
            logger.info(f"Dry run: Would process {len(episodes)} episodes")
            
            # Sample first few episodes
            sample_count = min(5, len(episodes))
            for i, episode in enumerate(episodes[:sample_count]):
                content_preview = episode.content[:200] + "..." if len(episode.content) > 200 else episode.content
                logger.info(f"\nEpisode {i+1}:")
                logger.info(f"  Created: {episode.created_at}")
                logger.info(f"  Content: {content_preview}")
                
            return {
                "duration": str(datetime.now() - start_time),
                "episodes_found": len(episodes),
                "entities_created": 0,
                "dry_run": dry_run,
                "sample_episodes": [ep.content[:200] for ep in episodes[:sample_count]]
            }
        
        # Process episodes
        logger.info(f"Processing {len(episodes)} episodes to extract entities...")
        results = await self.process_episodes_batch(episodes)
        
        duration = datetime.now() - start_time
        
        return {
            "duration": str(duration),
            "episodes_found": len(episodes),
            "episodes_processed": results['processed'],
            "entities_created": results['entities_created'],
            "failed": results['failed'],
            "dry_run": dry_run
        }


async def main():
    """Main function to run entity extraction"""
    # Initialize Graphiti with FalkorDB
    from graphiti_core.driver.falkordb_driver import FalkorDriver
    from graphiti_core.llm_client.config import LLMConfig
    from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
    from graphiti_core.client_factory import GraphitiClientFactory
    from openai import AsyncOpenAI
    
    # Create FalkorDB driver
    driver = FalkorDriver(
        host="localhost",
        port=6389,
        database="graphiti_migration"
    )
    
    # Use same LLM config as deduplication
    llm_config = LLMConfig(
        model="qwen3:30b",
        temperature=0.0
    )
    
    # Create Ollama client
    ollama_client = AsyncOpenAI(
        base_url=os.getenv('OLLAMA_BASE_URL', 'http://100.81.139.20:11434/v1'),
        api_key="ollama"
    )
    
    llm_client = OpenAIGenericClient(
        config=llm_config,
        cache=False,
        client=ollama_client
    )
    
    # Create cross encoder
    cross_encoder = GraphitiClientFactory.create_cross_encoder()
    
    # Initialize Graphiti
    graphiti = Graphiti(
        graph_driver=driver,
        llm_client=llm_client,
        embedder=None,  # Will use default embedder
        cross_encoder=cross_encoder
    )
    
    # Create extractor
    extractor = EntityExtractor(graphiti)
    
    # Run extraction
    logger.info("Running dry run to analyze episodes without entities...")
    dry_run_result = await extractor.run_extraction(
        group_id="claude_conversations",
        limit=20,  # Start with small batch
        dry_run=True
    )
    
    print(f"\nDry run results: {dry_run_result}")
    
    # Get actual total count of orphan episodes
    total_orphans = await extractor.get_orphan_count()
    
    # Process all episodes in batches
    if total_orphans > 0:
        print(f"\nFound {total_orphans} total episodes without entities (showing first 20 in dry run).")
        print("Processing ALL episodes in batches of 5...")
        
        total_processed = 0
        total_entities_created = 0
        batch_num = 0
        
        while True:
            batch_num += 1
            print(f"\n{'='*60}")
            print(f"BATCH {batch_num} - Processing episodes {total_processed+1} to {min(total_processed+5, total_orphans)}")
            print(f"{'='*60}")
            
            logger.info(f"Running batch {batch_num}...")
            result = await extractor.run_extraction(
                group_id="claude_conversations",
                limit=5,  # Process 5 episodes at a time
                dry_run=False
            )
            
            episodes_processed = result.get('episodes_processed', 0)
            entities_created = result.get('entities_created', 0)
            
            if episodes_processed == 0:
                print("\nNo more episodes to process!")
                break
                
            total_processed += episodes_processed
            total_entities_created += entities_created
            
            print(f"\nBatch {batch_num} complete:")
            print(f"  Episodes processed: {episodes_processed}")
            print(f"  Entities created: {entities_created}")
            print(f"  Total progress: {total_processed}/{total_orphans} episodes")
            
            # Check if we've processed all episodes
            remaining = await extractor.get_orphan_count()
            if remaining == 0:
                print("\nAll episodes have been processed!")
                break
                
            print(f"\nRemaining episodes without entities: {remaining}")
            print("Continuing to next batch...")
            
        print(f"\n{'='*60}")
        print("FINAL SUMMARY")
        print(f"{'='*60}")
        print(f"Total episodes processed: {total_processed}")
        print(f"Total entities created: {total_entities_created}")
        print(f"Average entities per episode: {total_entities_created/total_processed:.1f}" if total_processed > 0 else "N/A")


if __name__ == "__main__":
    asyncio.run(main())