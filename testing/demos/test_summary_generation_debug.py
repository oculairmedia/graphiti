#!/usr/bin/env python3
"""
Test script to debug and validate summary generation with different LLM clients.
This script tests the extract_attributes_from_node functionality in isolation.
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict

# Add the project root to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from pydantic import BaseModel, Field
import pydantic
from uuid import uuid4

# Import Graphiti components
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
from graphiti_core.llm_client.chutes_client import ChutesClient
from graphiti_core.nodes import EntityNode
from graphiti_core.prompts.extract_nodes import extract_attributes
from graphiti_core.prompts.models import Message

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class TestEntity(BaseModel):
    """Test entity type with a summary field"""
    summary: str = Field(description="Summary containing important information about the entity. Under 250 words.")

def create_test_node() -> EntityNode:
    """Create a test node for summary generation"""
    return EntityNode(
        uuid=str(uuid4()),
        group_id="test_group",
        name="Claude Tool Usage",
        labels=["Tool", "Software"],
        summary="",  # Empty summary to test generation
        attributes={"type": "AI_Tool", "context": "Code assistance"}
    )

def create_test_episode_content() -> str:
    """Create test episode content that should generate a summary"""
    return """
    Claude is being used as a code assistance tool to help with various programming tasks.
    The user is working on debugging summary generation issues in a knowledge graph system.
    Claude is analyzing LLM client implementations and testing different configurations
    to improve the reliability of entity summary generation.
    """

async def test_summary_generation_direct(client_type: str) -> Dict[str, Any]:
    """Test summary generation directly with the LLM clients"""
    logger.info(f"\n=== Testing {client_type} Summary Generation ===")
    
    # Configure client
    if client_type == "ollama":
        os.environ['USE_OLLAMA'] = 'true'
        config = LLMConfig(
            model="gemma3:12b",
            base_url="http://100.81.139.20:11434/v1",
            api_key="ollama"
        )
        client = OpenAIGenericClient(config=config)
    elif client_type == "chutes":
        config = LLMConfig(
            model="zai-org/GLM-4.5-FP8",
            base_url="https://llm.chutes.ai/v1",
            api_key=os.getenv('CHUTES_API_KEY')
        )
        if not config.api_key:
            logger.error("CHUTES_API_KEY not found in environment")
            return {"error": "Missing CHUTES_API_KEY"}
        client = ChutesClient(config=config)
    else:
        return {"error": f"Unknown client type: {client_type}"}
    
    # Create test node and context
    test_node = create_test_node()
    episode_content = create_test_episode_content()
    
    # Create the dynamic response model (similar to extract_attributes_from_node)
    node_context = {
        'name': test_node.name,
        'summary': test_node.summary,
        'entity_types': test_node.labels,
        'attributes': test_node.attributes,
    }
    
    attributes_definitions = {
        'summary': (
            str,
            Field(description='Summary containing the important information about the entity. Under 250 words'),
        )
    }
    
    unique_model_name = f'EntityAttributes_{uuid4().hex}'
    entity_attributes_model = pydantic.create_model(unique_model_name, **attributes_definitions)
    
    # Create the prompt context
    summary_context = {
        'node': node_context,
        'episode_content': episode_content,
        'previous_episodes': []
    }
    
    logger.info(f"Node context: {node_context}")
    logger.info(f"Episode content length: {len(episode_content)}")
    logger.info(f"Response model schema: {entity_attributes_model.model_json_schema()}")
    
    try:
        # Generate the response
        logger.info("Calling LLM for summary generation...")
        messages = extract_attributes(summary_context)
        
        logger.debug(f"System message: {messages[0].content[:200]}...")
        logger.debug(f"User message length: {len(messages[1].content)}")
        
        response = await client.generate_response(
            messages,
            response_model=entity_attributes_model
        )
        
        logger.info(f"LLM Response type: {type(response)}")
        logger.info(f"LLM Response: {response}")
        
        # Analyze the response
        result = {
            "client": client_type,
            "success": True,
            "response_type": str(type(response)),
            "response": response,
            "has_summary": 'summary' in response if isinstance(response, dict) else False,
            "summary_content": response.get('summary', '') if isinstance(response, dict) else '',
            "summary_length": len(response.get('summary', '')) if isinstance(response, dict) else 0
        }
        
        if result["has_summary"] and result["summary_length"] > 0:
            logger.info(f"✅ SUCCESS: {client_type} generated summary ({result['summary_length']} chars)")
            logger.info(f"Summary: {result['summary_content'][:100]}...")
        else:
            logger.error(f"❌ FAILURE: {client_type} did not generate summary")
            
        return result
        
    except Exception as e:
        logger.error(f"❌ ERROR: {client_type} failed with exception: {e}")
        return {
            "client": client_type,
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__
        }

async def test_response_format_behavior(client_type: str) -> Dict[str, Any]:
    """Test how clients handle response_format parameter"""
    logger.info(f"\n=== Testing {client_type} Response Format Behavior ===")
    
    if client_type == "ollama":
        config = LLMConfig(
            model="gemma3:12b",
            base_url="http://100.81.139.20:11434/v1",
            api_key="ollama"
        )
        client = OpenAIGenericClient(config=config)
    elif client_type == "chutes":
        config = LLMConfig(
            model="zai-org/GLM-4.5-FP8",
            base_url="https://llm.chutes.ai/v1",
            api_key=os.getenv('CHUTES_API_KEY')
        )
        if not config.api_key:
            return {"error": "Missing CHUTES_API_KEY"}
        client = ChutesClient(config=config)
    else:
        return {"error": f"Unknown client type: {client_type}"}
    
    # Simple test to see if the client follows JSON format
    messages = [
        Message(role='system', content='You are a helpful assistant that responds in JSON format.'),
        Message(role='user', content='Generate a JSON object with a "summary" field describing a test entity named "TestEntity". Keep it under 100 words.')
    ]
    
    try:
        response = await client.generate_response(messages, response_model=None)
        
        result = {
            "client": client_type,
            "success": True,
            "response_type": str(type(response)),
            "response": response,
            "is_dict": isinstance(response, dict),
            "has_summary": 'summary' in response if isinstance(response, dict) else False
        }
        
        logger.info(f"Response format test result: {result}")
        return result
        
    except Exception as e:
        logger.error(f"Response format test failed: {e}")
        return {
            "client": client_type,
            "success": False,
            "error": str(e)
        }

async def main():
    """Main test function"""
    print("🔍 Summary Generation Debug Test")
    print("=" * 50)
    
    results = []
    
    # Test clients
    client_types = []
    
    # Check if Ollama is available
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get("http://100.81.139.20:11434/api/tags", timeout=5) as resp:
                if resp.status == 200:
                    client_types.append("ollama")
                    logger.info("✅ Ollama service detected")
                else:
                    logger.warning("❌ Ollama service not responding")
    except Exception as e:
        logger.warning(f"❌ Ollama not available: {e}")
    
    # Check if Chutes API key is available
    if os.getenv('CHUTES_API_KEY'):
        client_types.append("chutes")
        logger.info("✅ Chutes API key found")
    else:
        logger.warning("❌ CHUTES_API_KEY not found in environment")
    
    if not client_types:
        logger.error("❌ No LLM clients available for testing")
        return
    
    # Run tests
    for client_type in client_types:
        # Test basic response format behavior
        format_result = await test_response_format_behavior(client_type)
        results.append(format_result)
        
        # Test full summary generation
        summary_result = await test_summary_generation_direct(client_type)
        results.append(summary_result)
        
        print(f"\n{'-' * 30}")
    
    # Summary
    print("\n🔍 TEST RESULTS SUMMARY")
    print("=" * 50)
    
    for result in results:
        client = result.get('client', 'unknown')
        success = result.get('success', False)
        has_summary = result.get('has_summary', False)
        
        if success and has_summary:
            status = "✅ PASS"
            summary_len = result.get('summary_length', 0)
            print(f"{client}: {status} - Generated {summary_len} char summary")
        elif success:
            status = "⚠️ PARTIAL"
            print(f"{client}: {status} - JSON response but no summary")
        else:
            status = "❌ FAIL"
            error = result.get('error', 'Unknown error')
            print(f"{client}: {status} - {error}")
    
    print("\n" + "=" * 50)

if __name__ == "__main__":
    asyncio.run(main())