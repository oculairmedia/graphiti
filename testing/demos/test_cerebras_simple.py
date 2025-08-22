#!/usr/bin/env python3
"""Simple test to verify Cerebras is working"""

import os
import asyncio
from graphiti_core.client_factory import GraphitiClientFactory

async def test_cerebras():
    # Set environment variables
    os.environ['USE_CEREBRAS'] = 'true'
    os.environ['USE_OLLAMA'] = 'false'
    os.environ['CEREBRAS_API_KEY'] = 'csk-v5pp234vww5hk53cjxkfern5nx262yv69xfn5fhvcrdt45jf'
    os.environ['CEREBRAS_MODEL'] = 'qwen-3-coder-480b'
    
    print("Creating Cerebras client via factory...")
    client = GraphitiClientFactory.create_llm_client()
    
    print(f"Client type: {type(client).__name__}")
    print(f"Client model: {client.config.model}")
    
    # Simple test message
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Say hello in 5 words or less."}
    ]
    
    print("\nSending test message to Cerebras...")
    try:
        response = await client.generate_response(messages)
        print(f"Response: {response}")
        print("✅ Cerebras is working!")
    except Exception as e:
        print(f"❌ Error: {e}")
        print(f"Error type: {type(e).__name__}")

if __name__ == "__main__":
    asyncio.run(test_cerebras())