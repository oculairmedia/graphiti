#!/usr/bin/env python3
"""
Quick script to add test data to Neo4j before migration.
"""

import asyncio
import os
from datetime import datetime

from graphiti_core import Graphiti


async def add_test_data():
    """Add some test data to Neo4j."""
    print('Adding test data to Neo4j...')

    # Create Graphiti instance with Neo4j
    graphiti = Graphiti(uri='bolt://localhost:7687', user='neo4j', password='demodemo')

    await graphiti.build_indices_and_constraints()

    # Add test episodes
    episodes = [
        {
            'name': 'AI and Graph Databases',
            'content': 'Graph databases like Neo4j and FalkorDB are excellent for storing knowledge graphs used by AI systems. They allow for complex relationship modeling and efficient traversal.',
        },
        {
            'name': 'Knowledge Graph Applications',
            'content': 'Knowledge graphs power recommendation systems, fraud detection, and semantic search. Companies like Google and Facebook use massive knowledge graphs.',
        },
        {
            'name': 'Graph Algorithms',
            'content': 'Common graph algorithms include PageRank for importance scoring, community detection for clustering, and shortest path for navigation.',
        },
    ]

    for episode in episodes:
        print(f'\nAdding episode: {episode["name"]}')
        result = await graphiti.add_episode(
            name=episode['name'],
            episode_body=episode['content'],
            source_description='Test data for migration',
            reference_time=datetime.now(),
        )
        print(f'  Created {len(result.nodes)} nodes and {len(result.edges)} edges')

    # Get counts
    node_count = await graphiti.driver.execute_query('MATCH (n) RETURN count(n) as count')
    edge_count = await graphiti.driver.execute_query('MATCH ()-[r]->() RETURN count(r) as count')

    print(f'\nTotal nodes in Neo4j: {node_count[0]["count"] if node_count else 0}')
    print(f'Total edges in Neo4j: {edge_count[0]["count"] if edge_count else 0}')

    await graphiti.close()


if __name__ == '__main__':
    # Set OpenAI key if not already set
    if not os.getenv('OPENAI_API_KEY'):
        print('Please set OPENAI_API_KEY environment variable')
        exit(1)

    asyncio.run(add_test_data())
