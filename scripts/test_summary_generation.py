#!/usr/bin/env python3
"""
Test script to diagnose why summaries are not being generated.
Tests the extract_attributes prompt with the current LLM configuration.
"""

import asyncio
import json
import os
import sys
from pydantic import BaseModel, Field, create_model
from typing import Any
from uuid import uuid4

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
from graphiti_core.llm_client.config import LLMConfig, ModelSize
from graphiti_core.prompts import extract_nodes as prompt_library
from graphiti_core.prompts.models import Message


async def test_summary_generation():
    """Test the extract_attributes prompt with current LLM config."""

    # Load environment config
    base_url = os.getenv('OLLAMA_BASE_URL', 'http://192.168.50.90:8082/v1')
    model = os.getenv('OLLAMA_MODEL', 'haiku-4-5')
    api_key = os.getenv('OLLAMA_API_KEY', 'ollama')

    print(f'=== Summary Generation Diagnostic ===')
    print(f'LLM Base URL: {base_url}')
    print(f'LLM Model: {model}')
    print()

    # Create LLM client
    config = LLMConfig(
        api_key=api_key,
        base_url=base_url,
        model=model,
        temperature=0.7,
    )
    llm_client = OpenAIGenericClient(config)

    # Create test context (similar to real entity)
    node_context = {
        'name': 'retrieval_pipeline',
        'summary': '',  # Empty summary - needs to be filled
        'entity_types': ['Entity'],
        'attributes': {},
    }

    episode_content = """The retrieval pipeline in Graphiti has been optimized. 
    We tested 7 different retrieval strategies including baseline vector search, 
    tri-bucket allocation, entity-seeded propagation, fact-first, lexical rescue, 
    multi-rewrite with MMR, and adaptive intent-based routing. 
    RRF (Reciprocal Rank Fusion) was found to match cross-encoder accuracy at lower latency.
    The pipeline now achieves 90%+ accuracy at ~6s latency."""

    previous_episodes = [
        'Earlier work involved backfilling embeddings in FalkorDB to 100% coverage.',
        'Vector search was enabled after fixing embedding gaps in the database.',
    ]

    summary_context = {
        'node': node_context,
        'episode_content': episode_content,
        'previous_episodes': previous_episodes,
    }

    # Create the Pydantic model for response (same approach as node_operations.py)
    attributes_definitions: dict[str, Any] = {
        'summary': (
            str,
            Field(
                description='Summary containing the important information about the entity. Under 250 words',
            ),
        )
    }
    unique_model_name = f'EntityAttributes_{uuid4().hex}'
    entity_attributes_model = create_model(unique_model_name, **attributes_definitions)

    print('=== Test 1: Using extract_attributes prompt ===')
    print(f'Node name: {node_context["name"]}')
    print(f'Episode content length: {len(episode_content)} chars')
    print()

    # Get the prompt
    messages = prompt_library.extract_attributes(summary_context)
    print('=== Generated Prompt ===')
    for msg in messages:
        print(f'[{msg.role}]:')
        print(msg.content[:500] + '...' if len(msg.content) > 500 else msg.content)
        print()

    print('=== LLM Response (with response_model) ===')
    try:
        response = await llm_client.generate_response(
            messages,
            response_model=entity_attributes_model,
            model_size=ModelSize.small,
        )
        print(f'Response type: {type(response)}')
        print(f'Response: {json.dumps(response, indent=2)}')
        print()

        if 'summary' in response:
            print(f"SUCCESS: 'summary' key found!")
            print(f'Summary: {response["summary"]}')
        else:
            print(f"FAILURE: No 'summary' key in response!")
            print(f'Available keys: {list(response.keys())}')
    except Exception as e:
        print(f'ERROR: {type(e).__name__}: {e}')
        import traceback

        traceback.print_exc()

    print()
    print('=== Test 2: Without response_model (free-form JSON) ===')
    try:
        response2 = await llm_client.generate_response(
            messages,
            response_model=None,
            model_size=ModelSize.small,
        )
        print(f'Response type: {type(response2)}')
        print(f'Response: {json.dumps(response2, indent=2)}')

        if 'summary' in response2:
            print(f"SUCCESS: 'summary' key found!")
        else:
            print(f"FAILURE: No 'summary' key in response!")
            print(f'Available keys: {list(response2.keys())}')
    except Exception as e:
        print(f'ERROR: {type(e).__name__}: {e}')
        import traceback

        traceback.print_exc()

    print()
    print('=== Test 3: Simplified prompt (explicit JSON output request) ===')
    simplified_messages = [
        Message(
            role='system',
            content='You are a JSON extraction assistant. Respond ONLY with a valid JSON object containing a "summary" key.',
        ),
        Message(
            role='user',
            content=f"""Generate a summary for this entity based on the provided context.

ENTITY NAME: {node_context['name']}

CONTEXT:
{episode_content}

Return a JSON object with this EXACT format:
{{"summary": "<your generated summary here, under 250 words>"}}

IMPORTANT: The response must contain ONLY the JSON object, no other text.""",
        ),
    ]

    try:
        response3 = await llm_client.generate_response(
            simplified_messages,
            response_model=None,
            model_size=ModelSize.small,
        )
        print(f'Response: {json.dumps(response3, indent=2)}')

        if 'summary' in response3:
            print(f"SUCCESS: 'summary' key found with simplified prompt!")
            print(f'Summary: {response3["summary"]}')
        else:
            print(f"FAILURE: No 'summary' key in response!")
    except Exception as e:
        print(f'ERROR: {type(e).__name__}: {e}')
        import traceback

        traceback.print_exc()


if __name__ == '__main__':
    asyncio.run(test_summary_generation())
