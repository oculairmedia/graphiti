#!/usr/bin/env python3
"""Debug Chutes AI response structure."""

import asyncio
from graphiti_core.llm_client.openai_client import OpenAIClient
from graphiti_core.llm_client.config import LLMConfig


async def debug_response():
    """Debug what the Chutes API returns."""
    
    print("🔍 Debugging Chutes AI response structure...")
    
    config = LLMConfig(
        api_key='cpk_f62b08fa4c2b4ae0b195b944fd47d6fc.bb20b5a1d58c50c9bc051e74b2a39d7c.roXSCXsJnWAk8mcZ26umGcrPjkCaqXlh',
        base_url='https://llm.chutes.ai/v1',
        model='zai-org/GLM-4.5-FP8',
        temperature=0.1,
        max_tokens=100
    )
    client = OpenAIClient(config=config)
    
    messages = [
        {'role': 'system', 'content': 'You are a helpful assistant.'},
        {'role': 'user', 'content': 'Say hello in JSON format with a "message" field.'}
    ]
    
    try:
        response = await client.generate_response(messages=messages)
        
        print(f"Response type: {type(response)}")
        print(f"Response repr: {repr(response)}")
        
        if isinstance(response, dict):
            print("Response keys:", list(response.keys()))
            for key, value in response.items():
                print(f"  {key}: {type(value)} = {repr(value)[:100]}...")
        else:
            print("Response attributes:", dir(response))
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(debug_response())