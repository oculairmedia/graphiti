#!/usr/bin/env python3
"""
Quick test to validate the new conservative Cerebras rate limiting.
"""

import asyncio
import os

os.environ['USE_CEREBRAS'] = 'true'
os.environ['CEREBRAS_API_KEY'] = 'csk-2dhe695kn8k6j2ck2n3jmx9hn2decfhjmf82xpk8v4yp5dr4'

async def test_conservative_limits():
    print("🧪 Testing Conservative Cerebras Rate Limits")
    print("=" * 50)
    
    from graphiti_core.client_factory import GraphitiClientFactory
    from graphiti_core.llm_client.config import ModelSize
    from graphiti_core.prompts.models import Message
    
    llm_client = GraphitiClientFactory.create_llm_client()
    print(f"✅ Client: {type(llm_client).__name__}")
    
    # Quick test message
    test_messages = [
        Message(role="system", content="You are concise."),
        Message(role="user", content="Say 'Conservative rate limiting test successful' and explain why rate limiting matters.")
    ]
    
    try:
        print("\n🕐 Testing with 8-second rate limiting...")
        start_time = asyncio.get_event_loop().time()
        
        response = await llm_client._generate_response(
            messages=test_messages,
            model_size=ModelSize.small,
            max_tokens=200
        )
        
        end_time = asyncio.get_event_loop().time()
        print(f"✅ Success in {end_time - start_time:.2f}s")
        print(f"📝 Response: {str(response)[:100]}...")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_conservative_limits())