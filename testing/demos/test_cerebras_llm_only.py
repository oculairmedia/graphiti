#!/usr/bin/env python3
"""
Safe Cerebras LLM Client Test - Tests only the LLM integration without any database operations.
"""

import asyncio
import os
import logging
import json
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Set environment variables for Cerebras
os.environ['USE_CEREBRAS'] = 'true'
os.environ['CEREBRAS_API_KEY'] = 'csk-2dhe695kn8k6j2ck2n3jmx9hn2decfhjmf82xpk8v4yp5dr4'
os.environ['CEREBRAS_MODEL'] = 'qwen-3-coder-480b'
os.environ['CEREBRAS_SMALL_MODEL'] = 'qwen-3-coder-480b'

# Enable fallback for rate limit handling
os.environ['ENABLE_FALLBACK'] = 'true'
os.environ['USE_OLLAMA'] = 'true'
os.environ['OLLAMA_BASE_URL'] = 'http://100.81.139.20:11434/v1'
os.environ['OLLAMA_MODEL'] = 'gemma3:12b'


async def test_cerebras_llm_client():
    """Test Cerebras LLM client directly - NO DATABASE OPERATIONS."""
    try:
        print("=" * 80)
        print("SAFE CEREBRAS LLM CLIENT TEST (NO DATABASE)")
        print("=" * 80)
        
        # Import LLM clients
        from graphiti_core.client_factory import GraphitiClientFactory
        from graphiti_core.llm_client.config import ModelSize
        
        # Test LLM client creation using the factory
        print("\n🧠 Creating Cerebras LLM client via factory...")
        
        llm_client = GraphitiClientFactory.create_llm_client()
        print(f"✅ LLM Client created: {type(llm_client).__name__}")
        print(f"   Model: {llm_client.model}")
        print(f"   Small Model: {llm_client.small_model}")
        
        # Test a simple prompt
        print("\n📝 Testing simple text generation...")
        from graphiti_core.prompts.models import Message
        
        test_messages = [
            Message(role="system", content="You are a helpful AI assistant."),
            Message(role="user", content="Explain what a knowledge graph is in one sentence.")
        ]
        
        try:
            response = await llm_client._generate_response(
                messages=test_messages,
                model_size=ModelSize.small
            )
            
            print(f"✅ Cerebras response received:")
            response_text = response if isinstance(response, str) else str(response)
            print(f"   Response type: {type(response)}")
            print(f"   Length: {len(response_text)} characters")
            print(f"   Preview: {response_text[:100]}...")
            
        except Exception as e:
            print(f"⚠️  Cerebras request failed, testing fallback: {e}")
            # This should trigger Ollama fallback if enabled
            
        # Test structured output (entity extraction style)
        print("\n🔧 Testing structured JSON output...")
        
        structured_messages = [
            Message(role="system", content="You are an entity extraction system. Return only valid JSON."),
            Message(role="user", content="""Extract entities from this text and return as JSON:
"Alice works at TechCorp as a software engineer."

Return format:
{
  "entities": [
    {"name": "entity_name", "type": "entity_type", "description": "brief_description"}
  ]
}""")
        ]
        
        try:
            structured_response = await llm_client._generate_response(
                messages=structured_messages,
                model_size=ModelSize.medium
            )
            
            print(f"✅ Structured response received:")
            structured_text = structured_response if isinstance(structured_response, str) else str(structured_response)
            print(f"   Response type: {type(structured_response)}")
            print(f"   Length: {len(structured_text)} characters")
            
            # Try to parse as JSON if it's a dict already or try parsing string
            try:
                if isinstance(structured_response, dict):
                    parsed = structured_response
                else:
                    parsed = json.loads(structured_text)
                print(f"   ✅ Valid JSON with {len(parsed.get('entities', []))} entities")
                for entity in parsed.get('entities', [])[:3]:
                    print(f"      - {entity.get('name', 'N/A')} ({entity.get('type', 'N/A')})")
            except (json.JSONDecodeError, TypeError) as e:
                print(f"   ⚠️  Response not valid JSON: {e}")
                print(f"   Preview: {structured_text[:100]}...")
                
        except Exception as e:
            print(f"⚠️  Structured request failed: {e}")
        
        # Test rate limiting behavior
        print("\n⚡ Testing rate limiting behavior...")
        tasks = []
        for i in range(5):
            rate_test_messages = [
                Message(role="system", content="Be concise."),
                Message(role="user", content=f"Say 'Test {i}' and explain why testing is important.")
            ]
            task = asyncio.create_task(
                llm_client._generate_response(
                    messages=rate_test_messages,
                    model_size=ModelSize.small
                )
            )
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        success_count = 0
        error_count = 0
        
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                print(f"   Task {i}: ❌ {type(result).__name__}: {str(result)[:50]}...")
                error_count += 1
            else:
                result_text = result if isinstance(result, str) else str(result)
                print(f"   Task {i}: ✅ Success ({len(result_text)} chars)")
                success_count += 1
        
        print(f"\n📊 Rate limit test results:")
        print(f"   Successful: {success_count}/{len(tasks)}")
        print(f"   Failed: {error_count}/{len(tasks)}")
        
        if success_count > 0:
            print(f"   ✅ Cerebras LLM client is working!")
        elif error_count == len(tasks):
            print(f"   ⚠️  All requests failed - check API key and rate limits")
        else:
            print(f"   ⚠️  Mixed results - Cerebras may be rate limited")
            
        print("\n" + "=" * 80)
        print("CEREBRAS LLM CLIENT TEST COMPLETED SAFELY")
        print("(No database operations were performed)")
        print("=" * 80)
        
    except ImportError as e:
        print(f"Import error: {e}")
        print("Make sure you have installed the required dependencies")
    except Exception as e:
        print(f"Test failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # Install Cerebras SDK if not already installed
    try:
        import cerebras
    except ImportError:
        print("Installing Cerebras SDK...")
        import subprocess
        subprocess.run(["pip", "install", "cerebras-cloud-sdk"], check=True)
    
    # Run the async test
    asyncio.run(test_cerebras_llm_client())