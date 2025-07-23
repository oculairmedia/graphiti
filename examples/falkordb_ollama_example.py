#!/usr/bin/env python3
"""
Example using FalkorDB backend with Ollama for LLM operations.

This demonstrates how to use Graphiti with FalkorDB as the graph database
and Ollama for local LLM inference.
"""

import asyncio
import os
from datetime import datetime
from openai import AsyncOpenAI

from graphiti_core import Graphiti
from graphiti_core.driver.falkordb_driver import FalkorDriver
from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
from graphiti_core.llm_client import LLMConfig


# Configuration
OLLAMA_URL = "http://100.81.139.20:11434/v1"
OLLAMA_MODEL = "mistral:latest"
FALKORDB_HOST = os.getenv("FALKORDB_HOST", "localhost")
FALKORDB_PORT = int(os.getenv("FALKORDB_PORT", "6389"))


async def create_graphiti_with_falkordb():
    """Create Graphiti instance with FalkorDB and Ollama."""
    
    # Create FalkorDB driver
    falkor_driver = FalkorDriver(
        host=FALKORDB_HOST,
        port=FALKORDB_PORT,
        database="graphiti_test"  # Use a test database
    )
    
    # Create Ollama client for LLM
    llm_client = AsyncOpenAI(
        base_url=OLLAMA_URL,
        api_key="ollama"
    )
    
    # Configure LLM
    llm_config = LLMConfig(
        model=OLLAMA_MODEL,
        small_model=OLLAMA_MODEL,
        temperature=0.7,
        max_tokens=2000
    )
    
    # Create Graphiti instance
    graphiti = Graphiti(
        graph_driver=falkor_driver,
        llm_client=OpenAIGenericClient(config=llm_config, client=llm_client)
        # Note: Still using OpenAI embeddings by default
    )
    
    await graphiti.initialize()
    
    return graphiti


async def test_falkordb_operations():
    """Test various operations with FalkorDB backend."""
    
    print("=== Testing Graphiti with FalkorDB Backend ===")
    print(f"Database: FalkorDB at {FALKORDB_HOST}:{FALKORDB_PORT}")
    print(f"LLM: Ollama ({OLLAMA_URL}) with {OLLAMA_MODEL}")
    print(f"Embeddings: OpenAI (default)")
    
    try:
        # Create Graphiti instance
        graphiti = await create_graphiti_with_falkordb()
        print("\n✓ Connected to FalkorDB")
        
        # Test 1: Add episodes
        print("\n--- Test 1: Adding Episodes ---")
        
        episodes = [
            {
                "content": "FalkorDB is a graph database built on Redis. It supports Cypher query language and provides high performance graph operations.",
                "name": "FalkorDB Introduction"
            },
            {
                "content": "Redis is an in-memory data structure store. FalkorDB extends Redis with graph database capabilities, making it extremely fast.",
                "name": "Redis and FalkorDB"
            },
            {
                "content": "Cypher is a declarative query language for graphs. Both Neo4j and FalkorDB support Cypher queries.",
                "name": "Query Languages"
            }
        ]
        
        for episode in episodes:
            result = await graphiti.add_episode(
                name=episode["name"],
                episode_body=episode["content"],
                source_description="FalkorDB documentation",
                timestamp=datetime.now().isoformat()
            )
            print(f"\n✓ Added episode: {episode['name']}")
            print(f"  - Entities: {len(result.nodes)}")
            print(f"  - Relationships: {len(result.edges)}")
            
            if result.nodes:
                print("  - Sample entities:", [n.name for n in result.nodes[:3]])
        
        # Test 2: Search operations
        print("\n--- Test 2: Search Operations ---")
        
        # Search for edges
        search_query = "FalkorDB Redis"
        print(f"\nSearching edges for: '{search_query}'")
        edges = await graphiti.search_edges(search_query, limit=5)
        
        if edges:
            print(f"Found {len(edges)} relevant edges:")
            for i, edge in enumerate(edges, 1):
                print(f"  {i}. {edge.fact} (score: {edge.rank:.3f})")
        
        # Search for nodes
        print(f"\nSearching nodes for: 'database'")
        nodes = await graphiti.search_nodes("database", limit=5)
        
        if nodes:
            print(f"Found {len(nodes)} relevant nodes:")
            for node in nodes:
                print(f"  - {node.name} ({node.type})")
        
        # Test 3: Direct FalkorDB queries
        print("\n--- Test 3: Direct FalkorDB Queries ---")
        
        # Count nodes
        node_count = await graphiti.driver.execute_query(
            "MATCH (n) RETURN count(n) as count"
        )
        print(f"\nTotal nodes in graph: {node_count[0]['count'] if node_count else 0}")
        
        # Count edges
        edge_count = await graphiti.driver.execute_query(
            "MATCH ()-[r]->() RETURN count(r) as count"
        )
        print(f"Total edges in graph: {edge_count[0]['count'] if edge_count else 0}")
        
        # Get node types
        node_types = await graphiti.driver.execute_query(
            "MATCH (n) RETURN DISTINCT labels(n) as types, count(n) as count"
        )
        if node_types:
            print("\nNode types in graph:")
            for nt in node_types:
                print(f"  - {nt['types']}: {nt['count']} nodes")
        
        # Test 4: Performance comparison
        print("\n--- Test 4: Query Performance ---")
        
        import time
        
        # Time a complex query
        start = time.time()
        complex_query = """
        MATCH (n:Entity)-[r]-(m:Entity)
        WHERE n.name CONTAINS 'DB' OR m.name CONTAINS 'DB'
        RETURN n.name, type(r), m.name
        LIMIT 10
        """
        results = await graphiti.driver.execute_query(complex_query)
        elapsed = time.time() - start
        
        print(f"\nComplex query executed in {elapsed:.3f} seconds")
        print(f"Returned {len(results)} results")
        
        # Test 5: Check FalkorDB-specific features
        print("\n--- Test 5: FalkorDB Features ---")
        
        # Get graph statistics
        stats_query = "CALL db.stats()"
        try:
            stats = await graphiti.driver.execute_query(stats_query)
            print("\nGraph statistics:")
            for stat in stats:
                print(f"  - {stat}")
        except:
            print("Note: Graph statistics might not be available in this version")
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await graphiti.close()
        print("\n✓ Closed FalkorDB connection")


async def compare_backends():
    """Quick comparison between Neo4j and FalkorDB."""
    
    print("\n=== Backend Comparison ===")
    print("\nFalkorDB advantages:")
    print("- Faster for read-heavy workloads (in-memory)")
    print("- Lower memory footprint")
    print("- Simpler deployment (Redis-based)")
    print("- Built-in Redis data structures")
    
    print("\nNeo4j advantages:")
    print("- More mature ecosystem")
    print("- Better tooling and visualization")
    print("- ACID compliance")
    print("- Larger community support")
    
    print("\nBoth support:")
    print("- Cypher query language")
    print("- Property graphs")
    print("- Indexing")
    print("- Graphiti's full feature set")


async def main():
    """Run the FalkorDB example."""
    
    # Check if OpenAI API key is set (still needed for embeddings)
    if not os.getenv("OPENAI_API_KEY"):
        print("⚠️  Warning: OPENAI_API_KEY not set. Required for embeddings.")
        print("Please set: export OPENAI_API_KEY='your-key'")
        return
    
    # Run tests
    await test_falkordb_operations()
    
    # Show comparison
    await compare_backends()


if __name__ == "__main__":
    asyncio.run(main())