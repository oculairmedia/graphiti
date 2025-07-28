#!/usr/bin/env python3
"""
Test script to compare entity extraction across different Qwen models
Using mock data - no database operations
"""

import asyncio
import logging
import json
from datetime import datetime
from typing import List, Dict
import os
from uuid import uuid4

from graphiti_core.nodes import EpisodicNode, EntityNode, EpisodeType
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
from graphiti_core.client_factory import GraphitiClientFactory
from graphiti_core.prompts import prompt_library
from graphiti_core.prompts.extract_nodes import ExtractedEntities, ExtractedEntity
from openai import AsyncOpenAI
from graphiti_core.utils.datetime_utils import utc_now

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def extract_with_model(episode: EpisodicNode, model_name: str) -> Dict[str, any]:
    """Extract entities from an episode using a specific model - no DB operations"""
    logger.info(f"\nTesting with model: {model_name}")
    start_time = datetime.now()
    
    # Create LLM client with specific model
    llm_config = LLMConfig(
        model=model_name,
        temperature=0.0
    )
    
    ollama_client = AsyncOpenAI(
        base_url=os.getenv('OLLAMA_BASE_URL', 'http://100.81.139.20:11434/v1'),
        api_key="ollama"
    )
    
    llm_client = OpenAIGenericClient(
        config=llm_config,
        cache=False,
        client=ollama_client
    )
    
    # Extract entities using direct LLM call
    try:
        # Prepare context for entity extraction
        context = {
            'episode_content': episode.content,
            'episode_timestamp': episode.valid_at.isoformat(),
            'previous_episodes': [],
            'custom_prompt': '',
            'entity_types': [
                {
                    'entity_type_id': 0,
                    'entity_type_name': 'Entity',
                    'entity_type_description': 'Default entity classification.'
                }
            ],
            'source_description': episode.source_description,
        }
        
        # Call LLM directly for entity extraction
        llm_response = await llm_client.generate_response(
            prompt_library.extract_nodes.extract_message(context),
            response_model=ExtractedEntities
        )
        
        extracted_entities = llm_response.get('extracted_entities', [])
        
        extraction_time = (datetime.now() - start_time).total_seconds()
        
        # Convert to simple format
        entities = []
        for entity_data in extracted_entities:
            entities.append({
                "name": entity_data.get('name', ''),
                "labels": ['Entity'],
                "uuid": str(uuid4())
            })
        
        result = {
            "model": model_name,
            "success": True,
            "extraction_time_seconds": extraction_time,
            "entities_count": len(entities),
            "entities": entities
        }
        
        logger.info(f"Model {model_name}: Extracted {len(entities)} entities in {extraction_time:.2f} seconds")
        
    except Exception as e:
        logger.error(f"Error with model {model_name}: {e}")
        result = {
            "model": model_name,
            "success": False,
            "error": str(e),
            "extraction_time_seconds": (datetime.now() - start_time).total_seconds()
        }
    
    return result


async def main():
    """Main function to run model comparison with mock data"""
    # Create a mock episode with rich content
    mock_content = """claude_code(system): User request: The user is working on implementing a graph visualization feature with React and Cosmograph. They've asked to add zoom controls with buttons for zoom in, zoom out, and fit view. The implementation involves:

1. GraphCanvas component at /opt/stacks/graphiti/frontend/src/components/GraphCanvas.tsx
2. Integration with Cosmograph library for WebGL-based graph rendering
3. Implementation of zoom controls using useImperativeHandle to expose methods
4. Bug fixes related to canvas initialization and double-click interactions

The code includes references to:
- React hooks: useRef, useImperativeHandle, useState, useEffect
- Cosmograph configuration with node colors, sizes, and physics settings
- Graph data structures with nodes and edges
- TypeScript interfaces for GraphCanvasRef
- Event handlers for user interactions

Claude has been helping debug issues with zoom functionality not working after page refresh, implementing proper canvas readiness detection, and ensuring the visualization works correctly with the graph data."""
    
    episode = EpisodicNode(
        uuid=str(uuid4()),
        name="Mock Episode for Testing",
        group_id="test_group",
        content=mock_content,
        created_at=utc_now(),
        valid_at=utc_now(),
        source=EpisodeType.message,
        source_description="Mock episode for model comparison"
    )
    
    logger.info(f"\nSelected episode for testing:")
    logger.info(f"UUID: {episode.uuid}")
    logger.info(f"Created: {episode.created_at}")
    logger.info(f"Content preview: {episode.content[:200]}...")
    logger.info(f"Content length: {len(episode.content)} characters")
    
    # Test with qwen3:8b only
    models = ["qwen3:8b"]
    results = []
    
    for model in models:
        result = await extract_with_model(episode, model)
        results.append(result)
    
    # Print comparison report
    print("\n" + "="*80)
    print("MODEL COMPARISON REPORT")
    print("="*80)
    print(f"\nEpisode tested: {episode.uuid}")
    print(f"Content length: {len(episode.content)} characters")
    print(f"Content preview: {episode.content[:100]}...")
    
    print("\n" + "-"*80)
    print("PERFORMANCE METRICS")
    print("-"*80)
    print(f"{'Model':<15} {'Time (sec)':<15} {'Entities Found':<20} {'Status'}")
    print("-"*80)
    
    for result in results:
        if result["success"]:
            print(f"{result['model']:<15} {result['extraction_time_seconds']:<15.2f} {result['entities_count']:<20} Success")
        else:
            print(f"{result['model']:<15} {result['extraction_time_seconds']:<15.2f} {'N/A':<20} Failed: {result['error'][:30]}...")
    
    print("\n" + "-"*80)
    print("ENTITY EXTRACTION COMPARISON")
    print("-"*80)
    
    # Compare entities found
    all_entities = set()
    model_entities = {}
    
    for result in results:
        if result["success"]:
            model_entities[result["model"]] = set(e["name"] for e in result["entities"])
            all_entities.update(model_entities[result["model"]])
    
    # Print entity comparison
    print(f"\nTotal unique entities found across all models: {len(all_entities)}")
    
    for entity in sorted(all_entities):
        found_by = [model for model, entities in model_entities.items() if entity in entities]
        print(f"\n'{entity}':")
        print(f"  Found by: {', '.join(found_by)}")
    
    # Save results to text file
    output_file = f"model_comparison_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(output_file, 'w') as f:
        f.write("="*80 + "\n")
        f.write("MODEL COMPARISON REPORT\n")
        f.write("="*80 + "\n\n")
        f.write(f"Episode tested: {episode.uuid}\n")
        f.write(f"Content length: {len(episode.content)} characters\n")
        f.write(f"Content preview:\n{episode.content[:300]}...\n\n")
        
        f.write("-"*80 + "\n")
        f.write("PERFORMANCE METRICS\n")
        f.write("-"*80 + "\n")
        f.write(f"{'Model':<15} {'Time (sec)':<15} {'Entities Found':<20} {'Status'}\n")
        f.write("-"*80 + "\n")
        
        for result in results:
            if result["success"]:
                f.write(f"{result['model']:<15} {result['extraction_time_seconds']:<15.2f} {result['entities_count']:<20} Success\n")
            else:
                f.write(f"{result['model']:<15} {result['extraction_time_seconds']:<15.2f} {'N/A':<20} Failed: {result['error'][:30]}...\n")
        
        f.write("\n" + "-"*80 + "\n")
        f.write("ENTITY EXTRACTION DETAILS\n")
        f.write("-"*80 + "\n\n")
        
        for result in results:
            if result["success"]:
                f.write(f"\n{result['model']} extracted {result['entities_count']} entities:\n")
                for i, entity in enumerate(result["entities"], 1):
                    f.write(f"  {i}. {entity['name']}\n")
            else:
                f.write(f"\n{result['model']} failed: {result['error']}\n")
        
        # Compare common and unique entities
        f.write("\n" + "-"*80 + "\n")
        f.write("ENTITY COMPARISON\n")
        f.write("-"*80 + "\n")
        
        f.write(f"\nTotal unique entities found across all models: {len(all_entities)}\n\n")
        
        # Show which models found which entities
        for entity in sorted(all_entities):
            found_by = [model for model, entities in model_entities.items() if entity in entities]
            f.write(f"'{entity}':\n")
            f.write(f"  Found by: {', '.join(found_by)}\n\n")
        
        # Add JSON results at the end
        f.write("\n" + "="*80 + "\n")
        f.write("RAW JSON RESULTS\n")
        f.write("="*80 + "\n")
        f.write(json.dumps({
            "episode": {
                "uuid": episode.uuid,
                "content_length": len(episode.content),
                "created_at": episode.created_at.isoformat()
            },
            "results": results
        }, indent=2))
    
    print(f"\n\nDetailed results saved to: {output_file}")


if __name__ == "__main__":
    asyncio.run(main())