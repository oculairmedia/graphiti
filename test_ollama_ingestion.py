#!/usr/bin/env python3
"""
Test script to verify Ollama-based ingestion pipeline for Graphiti.
This will test ingesting data into FalkorDB using the local Mistral model.
"""

import asyncio
import os
from datetime import datetime
from use_ollama import Graphiti, EpisodicNode

# FalkorDB connection details
FALKORDB_HOST = os.getenv('FALKORDB_HOST', 'localhost')
FALKORDB_PORT = os.getenv('FALKORDB_PORT', '6389')
FALKORDB_URI = f'bolt://{FALKORDB_HOST}:{FALKORDB_PORT}'


async def test_ollama_ingestion():
    """Test the ingestion pipeline with Ollama."""
    print("🧪 Testing Graphiti ingestion with Ollama...")
    print(f"📡 Connecting to FalkorDB at {FALKORDB_URI}")
    
    # Initialize Graphiti (will automatically use Ollama due to .env.ollama)
    graphiti = Graphiti(uri=FALKORDB_URI, user="", password="")
    
    # Test data - a series of related events
    test_episodes = [
        {
            "name": "Project Planning Meeting",
            "content": """
            The team gathered to discuss the new graph visualization project. 
            Sarah, the project manager, outlined the timeline and milestones. 
            John, the lead developer, proposed using WebGL for performance.
            Emma, the UX designer, suggested a dark theme with cyan accents.
            The team agreed to use FalkorDB as the backend and Rust for the server.
            """,
            "timestamp": datetime(2024, 7, 20, 10, 0, 0),
            "source": "Meeting Notes"
        },
        {
            "name": "Technical Architecture Decision",
            "content": """
            John and the development team decided on the technical stack.
            They chose Cosmograph for WebGL rendering due to its performance with large graphs.
            The Rust server would use Actix-web for high concurrency.
            Sarah approved the architecture and allocated resources.
            Migration from Neo4j to FalkorDB was planned for better performance.
            """,
            "timestamp": datetime(2024, 7, 21, 14, 30, 0),
            "source": "Technical Documentation"
        },
        {
            "name": "UI Design Review",
            "content": """
            Emma presented the UI mockups to the team.
            The design featured a collapsible left sidebar for controls.
            Sarah loved the glass-morphism effects and dark theme.
            John suggested adding real-time search with autocomplete.
            The team approved the design with minor adjustments.
            """,
            "timestamp": datetime(2024, 7, 22, 11, 0, 0),
            "source": "Design Review"
        }
    ]
    
    print("\n📝 Ingesting test episodes...")
    
    for i, episode_data in enumerate(test_episodes, 1):
        print(f"\n[{i}/{len(test_episodes)}] Processing: {episode_data['name']}")
        
        try:
            # Create episodic node
            episode = EpisodicNode(
                name=episode_data["name"],
                content=episode_data["content"],
                created_at=episode_data["timestamp"],
                valid_at=episode_data["timestamp"],
                source="text",  # Use EpisodeType enum value
                source_description=episode_data["source"],
                group_id="project_planning"  # Group related episodes
            )
            
            # Add to graph
            await graphiti.add_episode(
                episode=episode,
                reference_time=episode_data["timestamp"]
            )
            
            print(f"   ✅ Successfully ingested: {episode_data['name']}")
            
        except Exception as e:
            print(f"   ❌ Error ingesting episode: {e}")
            return False
    
    print("\n🔍 Verifying ingestion by searching...")
    
    # Test searches
    test_queries = [
        "Sarah project manager",
        "WebGL performance",
        "FalkorDB backend",
        "Emma UX designer"
    ]
    
    for query in test_queries:
        print(f"\n🔎 Searching for: '{query}'")
        try:
            results = await graphiti.search(
                query=query,
                num_results=3
            )
            
            if results:
                print(f"   ✅ Found {len(results)} results")
                for j, result in enumerate(results[:2], 1):
                    print(f"   {j}. {result.node.name} (Score: {result.score:.3f})")
            else:
                print(f"   ⚠️  No results found")
                
        except Exception as e:
            print(f"   ❌ Search error: {e}")
    
    # Get graph statistics
    print("\n📊 Graph Statistics:")
    try:
        # Query FalkorDB directly for stats
        from falkordb import FalkorDB
        
        db = FalkorDB(host=FALKORDB_HOST, port=int(FALKORDB_PORT))
        graph = db.select_graph("graphiti_migration")
        
        # Count nodes by type
        node_stats = graph.query("""
            MATCH (n)
            RETURN labels(n)[0] as type, count(n) as count
            ORDER BY count DESC
        """)
        
        print("   Node counts by type:")
        for row in node_stats.result_set:
            print(f"     - {row[0]}: {row[1]}")
        
        # Count relationships
        edge_stats = graph.query("""
            MATCH ()-[r]->()
            RETURN type(r) as type, count(r) as count
            ORDER BY count DESC
        """)
        
        print("   Relationship counts by type:")
        for row in edge_stats.result_set:
            print(f"     - {row[0]}: {row[1]}")
            
    except Exception as e:
        print(f"   ❌ Error getting stats: {e}")
    
    print("\n✅ Ollama ingestion test completed!")
    return True


async def check_ollama_connection():
    """Check if Ollama is accessible."""
    import aiohttp
    
    ollama_url = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434/v1')
    print(f"\n🔌 Checking Ollama connection at {ollama_url}")
    
    try:
        async with aiohttp.ClientSession() as session:
            # Try to get models list
            async with session.get(f"{ollama_url}/models") as response:
                if response.status == 200:
                    data = await response.json()
                    print("   ✅ Ollama is accessible")
                    if 'data' in data:
                        print("   Available models:")
                        for model in data['data']:
                            print(f"     - {model.get('id', 'unknown')}")
                    return True
                else:
                    print(f"   ❌ Ollama returned status {response.status}")
                    return False
    except Exception as e:
        print(f"   ❌ Cannot connect to Ollama: {e}")
        return False


async def main():
    """Main test function."""
    print("🦙 Graphiti + Ollama Integration Test")
    print("=" * 50)
    
    # Check environment
    use_ollama = os.getenv('USE_OLLAMA', '').lower() == 'true'
    if not use_ollama:
        print("⚠️  USE_OLLAMA is not set to true in .env.ollama")
        print("   The test will use OpenAI instead of Ollama")
        response = input("   Continue anyway? (y/n): ")
        if response.lower() != 'y':
            return
    
    # Check Ollama connection
    if not await check_ollama_connection():
        print("\n❌ Cannot connect to Ollama. Please ensure:")
        print("   1. Ollama is running")
        print("   2. OLLAMA_BASE_URL is correct in .env.ollama")
        print("   3. The mistral model is available")
        return
    
    # Run ingestion test
    await test_ollama_ingestion()


if __name__ == "__main__":
    asyncio.run(main())