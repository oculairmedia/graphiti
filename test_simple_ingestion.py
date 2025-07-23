#!/usr/bin/env python3
"""
Test simple ingestion without LLM to verify FalkorDB integration works.
"""

import asyncio
from datetime import datetime
from graphiti_core import Graphiti
from graphiti_core.driver.falkordb_driver import FalkorDriver
from graphiti_core.nodes import EpisodeType, EpisodicNode
from graphiti_core.embedder import EmbedderClient

class DummyEmbedder(EmbedderClient):
    """Dummy embedder that returns fixed embeddings."""
    
    async def create(self, input_data: list[str]) -> list[list[float]]:
        """Return dummy embeddings."""
        # Return 384-dimensional embeddings (typical size)
        return [[0.1] * 384 for _ in input_data]


from graphiti_core.llm_client.client import LLMClient
from typing import Any

class DummyLLMClient(LLMClient):
    """Dummy LLM client that returns empty extractions."""
    
    def __init__(self):
        # Initialize without config
        pass
    
    async def _generate_response(self, messages, **kwargs):
        """Internal method to generate response."""
        return {"choices": [{"message": {"content": "{}"}}]}
    
    async def generate_response(self, messages, model=None, response_model=None, **kwargs) -> Any:
        """Return empty extraction results."""
        # The code expects dict responses, not Pydantic models
        # Return appropriate dict based on the response model name
        if response_model:
            model_name = response_model.__name__ if hasattr(response_model, '__name__') else str(response_model)
            
            if 'ExtractedEntities' in model_name:
                return {'extracted_entities': []}
            elif 'MissedEntities' in model_name:
                return {'missed_entities': []}
            elif 'ExtractedEdges' in model_name:
                return {'edges': []}
            elif 'MissingFacts' in model_name:
                return {'missing_facts': []}
            elif 'NodeResolutions' in model_name:
                return {'entity_resolutions': []}
        
        # Fallback
        return {'extracted_entities': []}


async def test_simple_ingestion():
    print("🚀 Testing Simple Ingestion Without LLM")
    print("=" * 60)
    
    # Create FalkorDB driver
    falkor_driver = FalkorDriver(
        host="localhost",
        port=6389,
        database="simple_ingestion_test"
    )
    
    # Create Graphiti with dummy components
    graphiti = Graphiti(
        graph_driver=falkor_driver,
        embedder=DummyEmbedder(),
        llm_client=DummyLLMClient()
    )
    
    try:
        # Build indices
        print("\n1️⃣ Building indices...")
        await graphiti.build_indices_and_constraints()
        print("✅ Indices built successfully")
        
        # Add a simple episode
        print("\n2️⃣ Adding episode...")
        episode_name = "Test Episode"
        episode_content = "This is a test episode to verify FalkorDB integration works."
        
        result = await graphiti.add_episode(
            name=episode_name,
            episode_body=episode_content,
            source_description="Test",
            reference_time=datetime.now(),
            source=EpisodeType.text
        )
        print("✅ Episode added successfully")
        
        # Verify episode was stored
        print("\n3️⃣ Verifying episode storage...")
        episodes = await falkor_driver.execute_query(
            "MATCH (e:Episodic) RETURN e.name as name, e.content as content, e.uuid as uuid"
        )
        
        if episodes and episodes[0]:
            print(f"✅ Found {len(episodes[0])} episodes:")
            for ep in episodes[0]:
                print(f"   - Name: {ep['name']}")
                print(f"   - UUID: {ep['uuid']}")
                print(f"   - Content: {ep['content'][:50]}...")
        else:
            print("❌ No episodes found")
            
        # Test search (should work even without entities)
        print("\n4️⃣ Testing search...")
        try:
            results = await graphiti.search("test episode")
            print(f"✅ Search completed, found {len(results)} results")
        except Exception as e:
            print(f"❌ Search failed: {e}")
            
        # Test direct episode retrieval
        print("\n5️⃣ Testing episode retrieval...")
        if episodes and episodes[0] and episodes[0][0]['uuid']:
            episode_uuid = episodes[0][0]['uuid']
            episode = await EpisodicNode.get_by_uuid(falkor_driver, episode_uuid)
            if episode:
                print(f"✅ Retrieved episode: {episode.name}")
                print(f"   Valid at: {episode.valid_at}")
                print(f"   Source: {episode.source}")
            else:
                print("❌ Could not retrieve episode by UUID")
                
        print("\n✨ Simple ingestion test complete!")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        await graphiti.close()
        await falkor_driver.close()


if __name__ == "__main__":
    asyncio.run(test_simple_ingestion())