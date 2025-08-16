#!/usr/bin/env python3
"""
Batch generate embeddings for all existing nodes in the database.
This script will find all nodes without embeddings and generate them.
"""

import asyncio
import sys
from typing import List
from graphiti_core import Graphiti
from graphiti_core.driver import FalkorDriver
from graphiti_core.embedder import OpenAIEmbedder, OpenAIEmbedderConfig
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.nodes import EntityNode
from openai import AsyncOpenAI
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def get_nodes_without_embeddings(driver: FalkorDriver, batch_size: int = 100) -> List[dict]:
    """Get all nodes that don't have embeddings"""
    query = """
    MATCH (n:Entity)
    WHERE NOT EXISTS(n.name_embedding)
    RETURN n.uuid AS uuid, n.name AS name, n.group_id AS group_id,
           n.summary AS summary, n.created_at AS created_at,
           labels(n) AS labels, n AS attributes
    LIMIT $batch_size
    """
    
    records, _, _ = await driver.execute_query(query, batch_size=batch_size)
    return records


async def update_node_embeddings(driver: FalkorDriver, nodes: List[EntityNode]):
    """Update nodes with their embeddings in the database"""
    for node in nodes:
        if node.name_embedding:
            query = """
            MATCH (n:Entity {uuid: $uuid})
            SET n.name_embedding = $embedding
            RETURN n.uuid
            """
            await driver.execute_query(
                query,
                uuid=node.uuid,
                embedding=node.name_embedding
            )
            logger.info(f"Updated embeddings for node {node.uuid}: {node.name}")


async def main():
    logger.info("Starting batch embedding generation...")
    
    # Initialize embedder with Ollama backend
    ollama_client = AsyncOpenAI(
        base_url='http://192.168.50.80:11434/v1',
        api_key='ollama'
    )
    config = OpenAIEmbedderConfig(
        embedding_model='mxbai-embed-large:latest'
    )
    embedder = OpenAIEmbedder(config=config, client=ollama_client)
    
    # Initialize driver
    driver = FalkorDriver(
        host='localhost',
        port=6389,
        database='graphiti_migration'
    )
    
    try:
        # Count total nodes without embeddings
        count_query = """
        MATCH (n:Entity)
        WHERE NOT EXISTS(n.name_embedding)
        RETURN COUNT(n) as count
        """
        count_result, _, _ = await driver.execute_query(count_query)
        total_nodes = count_result[0]['count'] if count_result else 0
        
        logger.info(f"Found {total_nodes} nodes without embeddings")
        
        if total_nodes == 0:
            logger.info("All nodes already have embeddings!")
            return
        
        # Process in batches
        batch_size = 50
        processed = 0
        
        while processed < total_nodes:
            # Get batch of nodes without embeddings
            records = await get_nodes_without_embeddings(driver, batch_size)
            
            if not records:
                break
            
            # Convert to EntityNode objects
            nodes = []
            for record in records:
                from datetime import datetime
                node = EntityNode(
                    uuid=record['uuid'],
                    name=record['name'],
                    group_id=record.get('group_id') or 'default',
                    summary=record.get('summary', ''),
                    created_at=record.get('created_at') or datetime.now(),
                    labels=record.get('labels', []),
                )
                nodes.append(node)
            
            logger.info(f"Processing batch of {len(nodes)} nodes...")
            
            # Generate embeddings for batch
            if nodes:
                # Use the batch embedding function
                from graphiti_core.nodes import create_entity_node_embeddings
                await create_entity_node_embeddings(embedder, nodes)
                
                # Update nodes in database
                await update_node_embeddings(driver, nodes)
                
                processed += len(nodes)
                logger.info(f"Progress: {processed}/{total_nodes} nodes processed")
        
        logger.info(f"Successfully generated embeddings for {processed} nodes")
        
        # Verify the update
        verify_query = """
        MATCH (n:Entity)
        WHERE EXISTS(n.name_embedding)
        RETURN COUNT(n) as count
        """
        verify_result, _, _ = await driver.execute_query(verify_query)
        nodes_with_embeddings = verify_result[0]['count'] if verify_result else 0
        
        logger.info(f"Verification: {nodes_with_embeddings} nodes now have embeddings")
        
    except Exception as e:
        logger.error(f"Error generating embeddings: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())