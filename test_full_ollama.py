#!/usr/bin/env python3
"""
Test Graphiti with full Ollama setup - both LLM and embeddings.
Based on the provided example but adapted for Ollama.
"""

import asyncio
import os
import logging
import time
from datetime import datetime
from contextlib import contextmanager
import hashlib
import uuid

from graphiti_core import Graphiti
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
from graphiti_core.nodes import EpisodeType
from graphiti_core.embedder import EmbedderClient

# Timer context manager for performance tracking
@contextmanager
def timer(name):
    start = time.time()
    yield
    elapsed = time.time() - start
    print(f"{name} took {elapsed:.2f} seconds")

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logging.getLogger("neo4j").setLevel(logging.INFO)
logging.getLogger("httpcore").setLevel(logging.INFO)
logging.getLogger("httpx").setLevel(logging.INFO)
logging.getLogger("graphiti_core.search.search").setLevel(logging.INFO)


class OllamaEmbedder(EmbedderClient):
    """Custom embedder that uses Ollama for embeddings."""
    
    def __init__(self, base_url: str, model: str = "mxbai-embed-large"):
        self.base_url = base_url
        self.model = model
        # Import here to avoid issues if not installed
        from openai import AsyncOpenAI
        self.client = AsyncOpenAI(
            base_url=base_url,
            api_key="ollama"  # Ollama doesn't need a real API key
        )
        print(f"✓ Initialized OllamaEmbedder with model: {model}")
    
    async def create(self, input_data: list[str]) -> list[list[float]]:
        """Create embeddings using Ollama."""
        try:
            # Ollama's OpenAI-compatible endpoint for embeddings
            response = await self.client.embeddings.create(
                model=self.model,
                input=input_data
            )
            
            # Extract embeddings from response
            embeddings = [item.embedding for item in response.data]
            return embeddings
            
        except Exception as e:
            print(f"❌ Error creating embeddings: {e}")
            raise


# Test episode content
test_episode = {
    "content": """A Visual Guide to Quantization Demystifying the Compression of Large Language Models. 
    Maarten Grootendorst Jul 22, 2024. As their name suggests, Large Language Models (LLMs) are often too large 
    to run on consumer hardware. These models may exceed billions of parameters and generally need GPUs with large 
    amounts of VRAM to speed up inference. As such, more and more research has been focused on making these models 
    smaller through improved training, adapters, etc. One major technique in this field is called quantization.""",
    "metadata": {
        "source": "graphiti_memory_system_description",
        "timestamp": "2025-01-23T10:00:00Z"
    }
}


async def make_concurrent_llm_request(client, messages, response_model=None):
    """Make a concurrent LLM request."""
    try:
        response = await client._generate_response(messages, response_model)
        return response
    except Exception as e:
        print(f"Error in concurrent LLM request: {e}")
        return None


async def test_graphiti():
    print("\n🦙 Testing Graphiti with Full Ollama Setup")
    print("=" * 60)
    
    # LLM Configuration for Ollama
    llm_config = LLMConfig(
        base_url="http://100.81.139.20:11434/v1",  # Ollama base URL
        model="mistral:latest",  # Ollama model
        api_key="ollama",  # Dummy API key for Ollama
        temperature=0.2,
        max_tokens=1000
    )
    ollama_llm_client = OpenAIGenericClient(config=llm_config)
    
    # Embedder Configuration for Ollama
    ollama_embedder = OllamaEmbedder(
        base_url="http://100.81.139.20:11434/v1",
        model="mxbai-embed-large"  # Or "nomic-embed-text" if available
    )
    
    # FalkorDB connection
    print("\n📊 Connecting to FalkorDB...")
    graphiti = Graphiti(
        uri="bolt://localhost:6389",
        user="",
        password="",
        embedder=ollama_embedder,
        llm_client=ollama_llm_client
    )
    
    # Build indices and constraints
    print("🔨 Building indices and constraints...")
    await graphiti.build_indices_and_constraints()
    
    # Generate deterministic UUID for the episode
    episode_content = test_episode["content"]
    GRAPHITI_APP_NAMESPACE = uuid.UUID('9a14a468-3730-4c69-b391-57f979239d51')
    content_hash = hashlib.sha256(episode_content.encode('utf-8')).hexdigest()
    deterministic_episode_uuid = str(uuid.uuid5(GRAPHITI_APP_NAMESPACE, content_hash))
    
    print(f"\n📝 Processing episode with UUID: {deterministic_episode_uuid}")
    
    # Test concurrent LLM requests
    test_messages = [
        [{"role": "user", "content": "Summarize the key points about quantization in LLMs"}],
        [{"role": "user", "content": "What are the benefits of model quantization?"}],
        [{"role": "user", "content": "Explain different quantization techniques for LLMs"}],
        [{"role": "user", "content": "How does quantization affect model performance?"}]
    ]
    
    with timer("Total processing"):
        # Test concurrent LLM requests
        with timer("Concurrent LLM requests"):
            print("\n🔄 Making concurrent LLM requests...")
            concurrent_results = await asyncio.gather(
                *[make_concurrent_llm_request(
                    ollama_llm_client,
                    [{"role": msg[0]["role"], "content": msg[0]["content"]}]
                ) for msg in test_messages]
            )
            
            print("\n📤 Concurrent LLM request results:")
            for i, result in enumerate(concurrent_results):
                print(f"\nRequest {i+1}:")
                print(f"Query: {test_messages[i][0]['content']}")
                if result:
                    result_str = str(result)
                    print(f"Response: {result_str[:150]}..." if len(result_str) > 150 else f"Response: {result_str}")
                else:
                    print("Response: None")
        
        # Add episode to graph
        with timer("Episode addition"):
            print("\n➕ Adding episode to graph...")
            episode_result = await graphiti.add_episode(
                episode_body=episode_content,
                source_description=test_episode["metadata"]["source"],
                reference_time=datetime.fromisoformat(test_episode["metadata"]["timestamp"].replace("Z", "+00:00")),
                uuid=deterministic_episode_uuid,
                source=EpisodeType.text  # Explicitly set the source type
            )
        
        # Display results
        if episode_result:
            if hasattr(episode_result, 'episode') and episode_result.episode:
                print(f"\n✅ Episode Processed: {episode_result.episode.uuid}")
            else:
                print(f"\n✅ Episode Processed")
            
            print("\n🔹 Extracted Nodes (Entities):")
            if hasattr(episode_result, 'nodes') and episode_result.nodes:
                for node in episode_result.nodes:
                    labels = ', '.join(node.labels) if hasattr(node, 'labels') and node.labels else 'N/A'
                    print(f"  - Name: {node.name}, UUID: {node.uuid}, Type(s): {labels}")
            else:
                print("  No nodes extracted.")
            
            print("\n🔗 Created Edges (Relationships):")
            if hasattr(episode_result, 'edges') and episode_result.edges:
                for edge in episode_result.edges:
                    print(f"  - Name: {edge.name}, Fact: \"{edge.fact}\"")
                    print(f"    Source: {edge.source_node_uuid}, Target: {edge.target_node_uuid}")
            else:
                print("  No edges created.")
            
            print("\n📍 Created Episodic Edges (Mentions):")
            if hasattr(episode_result, 'episodic_edges') and episode_result.episodic_edges:
                for ep_edge in episode_result.episodic_edges:
                    print(f"  - Episode: {ep_edge.source_node_uuid} -> Entity: {ep_edge.target_node_uuid}")
            else:
                print("  No episodic edges created.")
            
            print("\n👥 Identified/Created Communities:")
            if hasattr(episode_result, 'communities') and episode_result.communities:
                for comm in episode_result.communities:
                    print(f"  - Name: {comm.name}, UUID: {comm.uuid}")
                    if hasattr(comm, 'description') and comm.description:
                        print(f"    Description: {comm.description}")
            else:
                print("  No communities identified/created.")
        else:
            print("\n❌ Episode processing did not return a result.")
        
        # Test search functionality
        with timer("Search operation"):
            print("\n🔍 Testing search functionality...")
            search_query = "quantization LLM compression"
            search_result = await graphiti.search(
                query=search_query,
                limit=5
            )
        
        print(f"\n📋 Search Results for: '{search_query}'")
        if search_result:
            for i, result in enumerate(search_result, 1):
                print(f"\n  Result {i}:")
                if hasattr(result, 'content'):
                    print(f"  Content: {result.content}")
                elif hasattr(result, 'node'):
                    node = result.node
                    if hasattr(node, 'name'):
                        print(f"  Name: {node.name}")
                    if hasattr(node, 'summary'):
                        print(f"  Summary: {node.summary}")
                else:
                    print(f"  {result}")
        else:
            print("  No search results found.")
    
    # Close the connection
    await graphiti.close()
    print("\n✨ Test complete!")


if __name__ == "__main__":
    print("🚀 Starting Full Ollama Test")
    asyncio.run(test_graphiti())