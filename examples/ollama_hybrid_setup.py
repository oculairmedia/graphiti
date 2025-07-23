"""
Hybrid setup: Ollama for LLM, OpenAI for embeddings.

This is the simplest migration path - just replace the LLM while keeping
the proven OpenAI embeddings.
"""

import asyncio
import os
from datetime import datetime
from openai import AsyncOpenAI

from graphiti_core import Graphiti
from graphiti_core.llm_client import OpenAIGenericClient, LLMConfig


# Configuration
OLLAMA_URL = "http://100.81.139.20:11434/v1"
OLLAMA_MODEL = "mistral:latest"


async def create_hybrid_graphiti(neo4j_uri: str, neo4j_user: str, neo4j_password: str):
    """Create Graphiti with Ollama LLM and OpenAI embeddings."""
    
    # Create Ollama client for LLM
    llm_client = AsyncOpenAI(
        base_url=OLLAMA_URL,
        api_key="ollama"  # Ollama doesn't need a real key
    )
    
    # Configure LLM
    llm_config = LLMConfig(
        model=OLLAMA_MODEL,
        small_model=OLLAMA_MODEL,  # Use same model for both
        temperature=0.7,
        max_tokens=2000
    )
    
    # Create Graphiti instance
    # Note: We're NOT specifying an embedder, so it will use the default OpenAI embedder
    graphiti = Graphiti(
        neo4j_uri=neo4j_uri,
        neo4j_user=neo4j_user,
        neo4j_password=neo4j_password,
        llm_client=OpenAIGenericClient(config=llm_config, client=llm_client)
        # embedder=None  # Will use default OpenAI embedder
    )
    
    await graphiti.initialize()
    
    return graphiti


async def main():
    """Example using Ollama for LLM with OpenAI embeddings."""
    
    # Make sure OpenAI API key is set for embeddings
    if not os.getenv("OPENAI_API_KEY"):
        print("⚠️  Warning: OPENAI_API_KEY not set. Required for embeddings.")
        print("Please set: export OPENAI_API_KEY='your-key'")
        return
    
    # Neo4j credentials
    neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = os.getenv("NEO4J_USER", "neo4j")
    neo4j_password = os.getenv("NEO4J_PASSWORD", "password")
    
    print("=== Hybrid Graphiti Setup ===")
    print(f"LLM: Ollama ({OLLAMA_URL}) with {OLLAMA_MODEL}")
    print(f"Embeddings: OpenAI (text-embedding-ada-002)")
    print(f"Database: Neo4j at {neo4j_uri}")
    
    try:
        # Create Graphiti instance
        graphiti = await create_hybrid_graphiti(
            neo4j_uri,
            neo4j_user,
            neo4j_password
        )
        
        print("\n✓ Graphiti initialized with hybrid setup")
        
        # Test with a real example
        print("\n=== Testing Knowledge Graph Operations ===")
        
        # Add an episode about AI/ML
        content = """
        Machine learning is a subset of artificial intelligence that enables systems to learn from data.
        Deep learning, which uses neural networks with multiple layers, has revolutionized computer vision 
        and natural language processing. Companies like OpenAI and Anthropic are pushing the boundaries 
        of large language models, while researchers at MIT and Stanford continue to advance the theoretical 
        foundations of machine learning.
        """
        
        print("Adding episode to graph...")
        result = await graphiti.add_episode(
            name="AI/ML Overview",
            episode_body=content,
            source_description="Technical documentation",
            timestamp=datetime.now().isoformat()
        )
        
        print(f"\n✓ Episode processed successfully!")
        print(f"  - Extracted {len(result.nodes)} entities")
        print(f"  - Created {len(result.edges)} relationships")
        
        # Show some extracted entities
        if result.nodes:
            print("\nSample entities extracted:")
            for node in result.nodes[:5]:
                print(f"  - {node.name} ({node.type})")
        
        # Show some relationships
        if result.edges:
            print("\nSample relationships found:")
            for edge in result.edges[:5]:
                print(f"  - {edge.fact}")
        
        # Test search functionality
        print("\n=== Testing Search ===")
        search_query = "machine learning artificial intelligence"
        print(f"Searching for: '{search_query}'")
        
        search_results = await graphiti.search_edges(search_query, limit=5)
        
        if search_results:
            print(f"\nFound {len(search_results)} relevant relationships:")
            for i, edge in enumerate(search_results, 1):
                print(f"  {i}. {edge.fact}")
                print(f"     Relevance: {edge.rank:.3f}")
        
        # Test node search
        print("\n=== Testing Node Search ===")
        node_results = await graphiti.search_nodes("deep learning", limit=3)
        
        if node_results:
            print(f"Found {len(node_results)} relevant nodes:")
            for node in node_results:
                print(f"  - {node.name} ({node.type})")
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await graphiti.close()
        print("\n✓ Graphiti connection closed")


if __name__ == "__main__":
    asyncio.run(main())