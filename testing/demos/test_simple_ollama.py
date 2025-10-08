#!/usr/bin/env python3
"""
Simple test to verify Ollama is working with Graphiti.
This test adds a single piece of information and retrieves it.
"""

import asyncio
from datetime import datetime

from graphiti_core.nodes import EpisodeType
from use_ollama import EpisodicNode, Graphiti


async def simple_test():
    """Run a simple ingestion and retrieval test."""

    # Connect to FalkorDB
    graphiti = Graphiti(uri='bolt://localhost:6389', user='', password='')

    print('🦙 Testing Ollama with Graphiti - Simple Test')
    print('=' * 50)

    # Create a simple episode
    test_content = """
    Alice is a senior software engineer working on the Graphiti project.
    She specializes in graph databases and distributed systems.
    Today she implemented a new feature for temporal graph queries.
    """

    episode = EpisodicNode(
        name="Alice's Work Update",
        content=test_content,
        created_at=datetime.now(),
        valid_at=datetime.now(),
        source='text',  # Use EpisodeType enum value
        source_description='Team Update - Daily standup',
        group_id='default',  # Required field
    )

    print('📝 Adding episode to graph...')
    try:
        await graphiti.add_episode(
            name=episode.name,
            episode_body=episode.content,
            source_description=episode.source_description,
            reference_time=episode.valid_at,
            source=EpisodeType.text,
            group_id=episode.group_id,
        )
        print('✅ Episode added successfully!')
    except Exception as e:
        print(f'❌ Error adding episode: {e}')
        import traceback

        traceback.print_exc()
        return

    # Search for it
    print("\n🔍 Searching for 'Alice software engineer'...")
    try:
        results = await graphiti.search(query='Alice software engineer', num_results=5)

        if results:
            print(f'✅ Found {len(results)} results:')
            for i, result in enumerate(results, 1):
                print(f'\n   Result {i}:')
                print(f'   - Name: {result.node.name}')
                print(f'   - Type: {type(result.node).__name__}')
                print(f'   - Score: {result.score:.3f}')

                # Show summary if available
                if hasattr(result.node, 'summary') and result.node.summary:
                    print(f'   - Summary: {result.node.summary[:100]}...')
        else:
            print('❌ No results found')

    except Exception as e:
        print(f'❌ Search error: {e}')

    print('\n✨ Test complete!')


if __name__ == '__main__':
    asyncio.run(simple_test())
