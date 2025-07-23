"""
Example showing how to use Ollama with Graphiti in Docker environment.
This approach requires NO changes to existing Graphiti code or Docker setup.
"""

import os
import asyncio
from datetime import datetime

# First, set up Ollama configuration
os.environ['USE_OLLAMA'] = 'true'
os.environ['OLLAMA_BASE_URL'] = 'http://100.81.139.20:11434/v1'
os.environ['OLLAMA_MODEL'] = 'mistral:latest'

# Now import - this will automatically use Ollama
from use_ollama import Graphiti


async def main():
    """Example that works with existing Docker setup."""
    
    # Your existing Neo4j configuration (from docker-compose)
    neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = os.getenv("NEO4J_USER", "neo4j")
    neo4j_password = os.getenv("NEO4J_PASSWORD", "password")
    
    print("=== Graphiti with Ollama (Docker-friendly) ===")
    print(f"LLM: Ollama/Mistral at {os.getenv('OLLAMA_BASE_URL')}")
    print(f"Embeddings: OpenAI (existing configuration)")
    print(f"Neo4j: {neo4j_uri}")
    
    # Create Graphiti instance - works exactly like before!
    graphiti = Graphiti(
        uri=neo4j_uri,
        user=neo4j_user,
        password=neo4j_password
    )
    
    try:
        await graphiti.initialize()
        print("\n✓ Graphiti initialized with Ollama")
        
        # Your existing code works without changes
        result = await graphiti.add_episode(
            name="Test Episode",
            episode_body="Graphiti now uses Ollama for LLM processing while keeping OpenAI embeddings.",
            source_description="Configuration test",
            timestamp=datetime.now().isoformat()
        )
        
        print(f"\n✓ Episode added successfully")
        print(f"  Entities: {len(result.nodes)}")
        print(f"  Relationships: {len(result.edges)}")
        
    finally:
        await graphiti.close()


if __name__ == "__main__":
    # Ensure OpenAI key is still available for embeddings
    if not os.getenv("OPENAI_API_KEY"):
        print("⚠️  Please set OPENAI_API_KEY for embeddings")
        print("   export OPENAI_API_KEY='your-key'")
    else:
        asyncio.run(main())