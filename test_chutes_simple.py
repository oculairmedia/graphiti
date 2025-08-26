#!/usr/bin/env python3
"""
Simple Chutes AI Performance Test for Entity Extraction.

Quick test to evaluate Chutes AI model performance on entity extraction tasks.
"""

import asyncio
import json
import time
from datetime import datetime

from graphiti_core.llm_client.openai_client import OpenAIClient
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.prompts.models import Message


async def test_chutes_extraction():
    """Test Chutes AI on a simple entity extraction task."""
    
    print("🧠 Testing Chutes AI (zai-org/GLM-4.5-FP8) for Entity Extraction")
    print("=" * 60)
    
    # Setup Chutes client
    config = LLMConfig(
        api_key='cpk_f62b08fa4c2b4ae0b195b944fd47d6fc.bb20b5a1d58c50c9bc051e74b2a39d7c.roXSCXsJnWAk8mcZ26umGcrPjkCaqXlh',
        base_url='https://llm.chutes.ai/v1',
        model='zai-org/GLM-4.5-FP8',
        temperature=0.1,
        max_tokens=1024
    )
    client = OpenAIClient(config=config)
    
    # Test content
    test_content = """
    Emmanuel Umukoro had a conversation with Claude about implementing a graph visualization system
    using FalkorDB and Rust. They discussed integrating Cosmograph for WebGL rendering and 
    setting up the infrastructure on a remote server at IP 192.168.50.90. The project involves
    building a knowledge graph platform called Graphiti that processes episodic memories and 
    extracts entities and relationships for AI agents.
    """
    
    # Simple extraction prompt using Message objects
    messages = [
        Message(
            role='system',
            content='You are an AI that extracts entities from text. Return a JSON object with an "entities" array containing objects with "name" and "type" fields.'
        ),
        Message(
            role='user', 
            content=f'Extract all entities (people, organizations, technologies, locations) from this text:\n\n{test_content}\n\nReturn only valid JSON.'
        )
    ]
    
    results = []
    
    # Run 3 test calls
    for i in range(3):
        print(f"\n🔍 Test {i+1}/3...")
        
        start_time = time.time()
        try:
            response = await client.generate_response(messages=messages)
            end_time = time.time()
            
            response_time = (end_time - start_time) * 1000
            
            # Get response content
            if isinstance(response, dict):
                content = response.get('content', str(response))
            elif hasattr(response, 'content'):
                content = response.content
            else:
                content = str(response)
            
            print(f"⏱️  Response time: {response_time:.1f}ms")
            print(f"📄 Response (first 200 chars): {content[:200]}...")
            
            # Try to parse JSON
            try:
                import re
                json_match = re.search(r'\{.*\}', content, re.DOTALL)
                if json_match:
                    parsed = json.loads(json_match.group())
                    entities = parsed.get('entities', [])
                    print(f"✅ Found {len(entities)} entities")
                    
                    for entity in entities[:3]:  # Show first 3
                        print(f"   - {entity.get('name', 'Unknown')}: {entity.get('type', 'Unknown')}")
                    
                    results.append({
                        'test_num': i+1,
                        'response_time_ms': response_time,
                        'entities_found': len(entities),
                        'json_valid': True,
                        'success': True
                    })
                else:
                    print("❌ No valid JSON found")
                    results.append({
                        'test_num': i+1,
                        'response_time_ms': response_time,
                        'json_valid': False,
                        'success': False
                    })
                    
            except json.JSONDecodeError:
                print("❌ JSON parsing failed")
                results.append({
                    'test_num': i+1,
                    'response_time_ms': response_time,
                    'json_valid': False,
                    'success': False
                })
                
        except Exception as e:
            end_time = time.time()
            response_time = (end_time - start_time) * 1000
            print(f"❌ Error: {e}")
            results.append({
                'test_num': i+1,
                'response_time_ms': response_time,
                'error': str(e),
                'success': False
            })
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 CHUTES AI TEST RESULTS")
    print("=" * 60)
    
    successful_tests = [r for r in results if r['success']]
    if successful_tests:
        avg_response_time = sum(r['response_time_ms'] for r in successful_tests) / len(successful_tests)
        avg_entities = sum(r.get('entities_found', 0) for r in successful_tests) / len(successful_tests)
        json_success_rate = len([r for r in successful_tests if r.get('json_valid')]) / len(results) * 100
        
        print(f"✅ Successful tests: {len(successful_tests)}/3")
        print(f"⏱️  Average response time: {avg_response_time:.1f}ms")
        print(f"🎯 Average entities found: {avg_entities:.1f}")
        print(f"📋 JSON compliance rate: {json_success_rate:.1f}%")
    else:
        print("❌ All tests failed")
        for result in results:
            if 'error' in result:
                print(f"   Test {result['test_num']}: {result['error']}")
    
    # Save results
    with open('chutes_simple_test_results.json', 'w') as f:
        json.dump({
            'timestamp': datetime.now().isoformat(),
            'model': 'zai-org/GLM-4.5-FP8',
            'results': results
        }, f, indent=2)
    
    print(f"\n📁 Results saved to: chutes_simple_test_results.json")


if __name__ == "__main__":
    asyncio.run(test_chutes_extraction())