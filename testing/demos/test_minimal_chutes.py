#!/usr/bin/env python3
"""
Minimal test to debug Chutes AI integration issues.
Based on test_minimal_cerebras.py but adapted for Chutes AI.
"""

import asyncio
import os
import sys
from datetime import datetime

print('🚀 Step 1: Environment Check')
print(f'   CHUTES_API_KEY: {"Set" if os.getenv("CHUTES_API_KEY") else "Not set"}')

print('\n🚀 Step 2: Import Core Components')
try:
    from graphiti_core import Graphiti
    from graphiti_core.llm_client.chutes_client import ChutesClient, DEFAULT_MODEL, DEFAULT_BASE_URL
    from graphiti_core.llm_client.config import LLMConfig
    from graphiti_core.embedder import EmbedderClient
    print('   ✅ Core imports successful')
except Exception as e:
    print(f'   ❌ Core import failed: {e}')
    sys.exit(1)

print('\n🚀 Step 3: Test Chutes API Key')
try:
    if not os.getenv('CHUTES_API_KEY'):
        print('   ⚠️ CHUTES_API_KEY not set - some tests will fail')
    else:
        print('   ✅ CHUTES_API_KEY is available')
        
        # Test basic client creation
        config = LLMConfig(
            api_key=os.getenv('CHUTES_API_KEY'),
            base_url=DEFAULT_BASE_URL,
            model=DEFAULT_MODEL,
            temperature=0.1,
            max_tokens=100,
        )
        chutes_client = ChutesClient(config=config)
        print(f'   ✅ Chutes client created with model: {DEFAULT_MODEL}')
        
except Exception as e:
    print(f'   ❌ Chutes client error: {e}')


class OllamaEmbedder(EmbedderClient):
    """Minimal embedder for testing."""

    def __init__(self, base_url: str = 'http://192.168.50.80:11434/v1', model: str = 'mxbai-embed-large'):
        self.base_url = base_url
        self.model = model
        try:
            from openai import AsyncOpenAI
            self.client = AsyncOpenAI(base_url=base_url, api_key='ollama')
            print(f'   ✅ Embedder initialized with {model}')
        except Exception as e:
            print(f'   ⚠️ Embedder warning: {e}')
            self.client = None

    async def create(self, input_data: list[str]) -> list[list[float]]:
        """Create embeddings."""
        if not self.client:
            # Return dummy embeddings for testing
            return [[0.1] * 1536 for _ in input_data]
        
        try:
            response = await self.client.embeddings.create(model=self.model, input=input_data)
            return [item.embedding for item in response.data]
        except Exception as e:
            print(f'   ⚠️ Embedding error: {e}')
            # Return dummy embeddings
            return [[0.1] * 1536 for _ in input_data]


async def minimal_chutes_test():
    """Minimal Chutes AI integration test."""
    
    print('\n🚀 Step 4: Initialize Minimal Graphiti with Chutes')
    try:
        # Create components
        config = LLMConfig(
            api_key=os.getenv('CHUTES_API_KEY'),
            base_url=DEFAULT_BASE_URL,
            model=DEFAULT_MODEL,
            temperature=0.2,
            max_tokens=200,
        )
        
        chutes_client = ChutesClient(config=config)
        ollama_embedder = OllamaEmbedder()
        
        # Create Graphiti instance (minimal connection)
        graphiti = Graphiti(
            uri='bolt://localhost:6389',
            user='',
            password='',
            llm_client=chutes_client,
            embedder=ollama_embedder
        )
        
        print('   ✅ Graphiti instance created with Chutes AI')
        print(f'   LLM Client: {type(graphiti.llm_client).__name__}')
        print(f'   Model: {graphiti.llm_client.config.model}')
        print(f'   Embedder: {type(graphiti.embedder).__name__}')

    except Exception as e:
        print(f'   ❌ Graphiti initialization error: {e}')
        import traceback
        traceback.print_exc()
        return

    print('\n🚀 Step 5: Test Chutes AI LLM Connection')
    try:
        if not os.getenv('CHUTES_API_KEY'):
            print('   ⚠️ Skipping LLM test - no API key')
        else:
            # Test basic message generation
            from graphiti_core.prompts.models import Message
            
            test_message = Message(
                role='user',
                content='Respond with exactly this JSON: {"test": "Chutes connection successful", "model": "GLM-4.5-FP8"}'
            )
            
            print('   📡 Testing Chutes AI connection...')
            response = await asyncio.wait_for(
                graphiti.llm_client._generate_response([test_message], max_tokens=100),
                timeout=60.0  # Chutes can be slower
            )
            
            if response:
                print('   ✅ Chutes AI LLM response received')
                if isinstance(response, dict):
                    print(f'   Response keys: {list(response.keys())}')
                    if 'test' in response:
                        print(f'   Test message: {response["test"]}')
                else:
                    response_str = str(response)
                    preview = response_str[:100] + '...' if len(response_str) > 100 else response_str
                    print(f'   Response preview: {preview}')
            else:
                print('   ⚠️ Empty response from Chutes AI')
                
    except asyncio.TimeoutError:
        print('   ⏱️ Chutes AI LLM connection timed out (Chutes can be slower)')
    except Exception as e:
        print(f'   ❌ LLM test error: {e}')

    print('\n🚀 Step 6: Test Embedder Connection')
    try:
        print('   📊 Testing embedding generation...')
        test_texts = ['Hello world', 'Test embedding']
        
        embeddings = await asyncio.wait_for(
            graphiti.embedder.create(test_texts),
            timeout=10.0
        )
        
        if embeddings and len(embeddings) == 2:
            print(f'   ✅ Embeddings generated: {len(embeddings)} vectors')
            print(f'   Vector dimensions: {len(embeddings[0])}')
        else:
            print('   ⚠️ Embedding test failed or returned wrong format')
            
    except Exception as e:
        print(f'   ❌ Embedder test error: {e}')

    print('\n🚀 Step 7: Test FalkorDB Connection')
    try:
        print('   🔌 Testing database connection...')
        
        # Simple connection test
        await graphiti.build_indices_and_constraints()
        print('   ✅ Database connection successful')
        
        # Test simple query
        result = await graphiti.driver.execute_query('RETURN "Database test" as test')
        if result and result[0].get('test') == 'Database test':
            print('   ✅ Database query test passed')
        else:
            print('   ⚠️ Database query test failed')
            
    except Exception as e:
        print(f'   ❌ Database connection error: {e}')

    print('\n🚀 Step 8: Test Chutes AI Extraction Capabilities')
    try:
        if not os.getenv('CHUTES_API_KEY'):
            print('   ⚠️ Skipping extraction test - no API key')
        else:
            print('   🔬 Testing Chutes AI entity extraction...')
            
            # Minimal extraction test - Chutes is good with technical content
            test_content = "Dr. Alice Smith works as a researcher at MIT on quantum computing projects using GLM models."
            
            result = await asyncio.wait_for(
                graphiti.add_episode(
                    name='Minimal Chutes Test Episode',
                    episode_body=test_content,
                    source_description='Test Source',
                    reference_time=datetime.now(),
                ),
                timeout=120.0  # Longer timeout for Chutes
            )
            
            if result:
                print('   ✅ Episode processing completed')
                if hasattr(result, 'nodes') and result.nodes:
                    print(f'   Extracted {len(result.nodes)} entities')
                    for node in result.nodes[:2]:  # Show first 2
                        labels = ', '.join(node.labels) if hasattr(node, 'labels') and node.labels else 'N/A'
                        print(f'     • {node.name} ({labels})')
                
                if hasattr(result, 'edges') and result.edges:
                    print(f'   Extracted {len(result.edges)} relationships')
            else:
                print('   ⚠️ Episode processing returned no result')
                
    except asyncio.TimeoutError:
        print('   ⏱️ Episode processing timed out (Chutes can be slower)')
    except Exception as e:
        print(f'   ❌ Extraction test error: {e}')

    # Cleanup
    try:
        await graphiti.close()
        print('\n✅ Cleanup completed')
    except Exception as e:
        print(f'\n⚠️ Cleanup warning: {e}')

    print('\n🎯 Minimal Chutes AI Test Summary:')
    print('  - Chutes client initialization: Check Step 3')
    print('  - LLM connectivity: Check Step 5') 
    print('  - Embeddings: Check Step 6')
    print('  - Database: Check Step 7')
    print('  - Chutes extraction: Check Step 8')
    print('  - Note: Chutes AI (GLM-4.5-FP8) can have slower response times')


async def main():
    """Run minimal test."""
    try:
        await minimal_chutes_test()
        print('\n🎉 Minimal test completed!')
    except Exception as e:
        print(f'\n❌ Test failed with error: {e}')
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    asyncio.run(main())