#!/usr/bin/env python3
"""
Debug script to see what's happening with Cerebras/Qwen integration.
Adapted from test_ollama_debug.py for Cerebras testing.
"""

import asyncio
import os
from datetime import datetime

# Show environment
print('🧠 Cerebras Environment Check:')
print(f'   CEREBRAS_API_KEY: {"Set" if os.getenv("CEREBRAS_API_KEY") else "Not set"}')
print(f'   OPENAI_API_KEY: {"Set" if os.getenv("OPENAI_API_KEY") else "Not set"}')
print(f'   FALKORDB_HOST: {os.getenv("FALKORDB_HOST", "localhost")}')
print(f'   FALKORDB_PORT: {os.getenv("FALKORDB_PORT", "6389")}')

# Import and show what happens
print('\n📦 Importing Cerebras Components...')
try:
    from graphiti_core import Graphiti
    from graphiti_core.llm_client.cerebras_client import CerebrasClient, DEFAULT_CEREBRAS_MODEL
    from graphiti_core.llm_client.config import LLMConfig
    from graphiti_core.embedder import EmbedderClient
    from graphiti_core.prompts.models import Message
    print('   ✅ Core imports successful')
    print(f'   Default Qwen model: {DEFAULT_CEREBRAS_MODEL}')
except Exception as e:
    print(f'   ❌ Import failed: {e}')
    import traceback
    traceback.print_exc()
    exit(1)

# Basic embedder for testing
class OllamaEmbedder(EmbedderClient):
    """Debug embedder that uses Ollama."""

    def __init__(self, base_url: str = 'http://192.168.50.80:11434/v1', model: str = 'mxbai-embed-large'):
        self.base_url = base_url
        self.model = model
        print(f'   🔧 Initializing embedder: {model} at {base_url}')
        try:
            from openai import AsyncOpenAI
            self.client = AsyncOpenAI(base_url=base_url, api_key='ollama')
            print('   ✅ Embedder client created')
        except Exception as e:
            print(f'   ⚠️ Embedder creation warning: {e}')
            self.client = None

    async def create(self, input_data: list[str]) -> list[list[float]]:
        """Create embeddings with debug output."""
        print(f'   📊 Creating embeddings for {len(input_data)} texts')
        
        if not self.client:
            print('   ⚠️ No embedder client, returning dummy embeddings')
            return [[0.1] * 1536 for _ in input_data]
        
        try:
            response = await self.client.embeddings.create(model=self.model, input=input_data)
            embeddings = [item.embedding for item in response.data]
            print(f'   ✅ Generated {len(embeddings)} embeddings, dim: {len(embeddings[0])}')
            return embeddings
        except Exception as e:
            print(f'   ❌ Embedding error: {e}')
            # Return dummy embeddings for debugging
            return [[0.1] * 1536 for _ in input_data]


async def test_cerebras_components():
    """Test Cerebras components step by step."""
    
    print('\n🧠 Testing Cerebras/Qwen LLM Client...')
    
    # Test 1: Basic client creation
    try:
        config = LLMConfig(
            model=DEFAULT_CEREBRAS_MODEL,
            temperature=0.3,
            max_tokens=500,
        )
        
        cerebras_client = CerebrasClient(config=config)
        print('   ✅ Cerebras client created')
        print(f'   Model: {config.model}')
        print(f'   Temperature: {config.temperature}')
        print(f'   Max tokens: {config.max_tokens}')
        
        # Check if API key is available for testing
        if not os.getenv('CEREBRAS_API_KEY'):
            print('   ⚠️ No CEREBRAS_API_KEY - skipping LLM calls')
            cerebras_client = None
        else:
            print('   ✅ API key available for testing')
        
    except Exception as e:
        print(f'   ❌ Cerebras client creation failed: {e}')
        cerebras_client = None

    # Test 2: Embedder creation
    print('\n📊 Testing Embedder...')
    try:
        embedder = OllamaEmbedder()
        print('   ✅ Embedder initialized')
    except Exception as e:
        print(f'   ❌ Embedder creation failed: {e}')
        embedder = None

    # Test 3: Graphiti initialization  
    print('\n🔗 Testing Graphiti Initialization...')
    try:
        falkor_uri = f'bolt://{os.getenv("FALKORDB_HOST", "localhost")}:{os.getenv("FALKORDB_PORT", "6389")}'
        print(f'   Connecting to: {falkor_uri}')
        
        graphiti = Graphiti(
            uri=falkor_uri,
            user='',
            password='',
            llm_client=cerebras_client,
            embedder=embedder
        )
        
        print('   ✅ Graphiti initialized')
        print(f'   LLM Client: {type(graphiti.llm_client).__name__ if graphiti.llm_client else "None"}')
        print(f'   Embedder: {type(graphiti.embedder).__name__ if graphiti.embedder else "None"}')
        
    except Exception as e:
        print(f'   ❌ Graphiti initialization failed: {e}')
        import traceback
        traceback.print_exc()
        return

    # Test 4: Database connection
    print('\n💾 Testing Database Connection...')
    try:
        await graphiti.build_indices_and_constraints()
        print('   ✅ Database connection successful')
        
        # Test query
        result = await graphiti.driver.execute_query('RETURN "Connection test" as test')
        if result and result[0].get('test') == 'Connection test':
            print('   ✅ Database query test passed')
        else:
            print('   ⚠️ Database query returned unexpected result')
            
    except Exception as e:
        print(f'   ❌ Database connection error: {e}')

    # Test 5: LLM functionality (if available)
    if cerebras_client and os.getenv('CEREBRAS_API_KEY'):
        print('\n🤖 Testing Qwen LLM Functionality...')
        try:
            test_message = Message(
                role='user',
                content='Respond with exactly: "Qwen debug test successful"'
            )
            
            print('   📡 Sending test message to Qwen...')
            response = await asyncio.wait_for(
                cerebras_client._generate_response([test_message], max_tokens=100),
                timeout=20.0
            )
            
            if response:
                print('   ✅ Qwen response received')
                response_str = str(response)
                preview = response_str[:150] + '...' if len(response_str) > 150 else response_str
                print(f'   Response: {preview}')
                
                # Test structured output (Qwen's strength)
                print('\n   🔬 Testing structured output...')
                struct_message = Message(
                    role='user',
                    content='Extract entities from "Dr. John works at MIT" and return JSON with entities array'
                )
                
                struct_response = await asyncio.wait_for(
                    cerebras_client._generate_response([struct_message], max_tokens=200),
                    timeout=20.0
                )
                
                if struct_response:
                    print('   ✅ Structured output response received')
                    if isinstance(struct_response, dict):
                        print('   ✅ Response is structured (dict)')
                    else:
                        print(f'   ⚠️ Response type: {type(struct_response)}')
                else:
                    print('   ❌ No structured response received')
                    
            else:
                print('   ❌ Empty response from Qwen')
                
        except asyncio.TimeoutError:
            print('   ⏱️ Qwen LLM test timed out')
        except Exception as e:
            print(f'   ❌ LLM test error: {e}')
    else:
        print('\n⚠️ Skipping LLM tests - no API key or client failed')

    # Test 6: Embedding functionality
    print('\n📊 Testing Embedding Functionality...')
    try:
        test_texts = ['Test embedding 1', 'Test embedding 2']
        embeddings = await asyncio.wait_for(
            graphiti.embedder.create(test_texts),
            timeout=15.0
        )
        
        if embeddings and len(embeddings) == 2:
            print(f'   ✅ Embeddings generated: {len(embeddings)} vectors')
            print(f'   Vector dimensions: {len(embeddings[0])}')
        else:
            print('   ⚠️ Embedding test returned unexpected format')
            
    except Exception as e:
        print(f'   ❌ Embedding test error: {e}')

    # Test 7: Simple end-to-end test (if LLM available)
    if cerebras_client and os.getenv('CEREBRAS_API_KEY'):
        print('\n🔄 Testing End-to-End Pipeline...')
        try:
            print('   📝 Processing simple episode with Qwen...')
            
            result = await asyncio.wait_for(
                graphiti.add_episode(
                    name='Debug Test Episode',
                    episode_body='Dr. Sarah Chen is a researcher at Stanford University working on neural networks.',
                    source_description='Debug Test',
                    reference_time=datetime.now(),
                ),
                timeout=90.0  # Longer timeout for full pipeline
            )
            
            if result:
                print('   ✅ Episode processing completed')
                if hasattr(result, 'nodes') and result.nodes:
                    print(f'   Entities: {len(result.nodes)}')
                    for node in result.nodes[:3]:  # Show first 3
                        labels = ', '.join(node.labels) if hasattr(node, 'labels') and node.labels else 'N/A'
                        print(f'     • {node.name} ({labels})')
                        
                if hasattr(result, 'edges') and result.edges:
                    print(f'   Relationships: {len(result.edges)}')
                    for edge in result.edges[:2]:  # Show first 2
                        fact = edge.fact[:80] + '...' if len(edge.fact) > 80 else edge.fact
                        print(f'     • "{fact}"')
            else:
                print('   ⚠️ Episode processing returned no result')
                
        except asyncio.TimeoutError:
            print('   ⏱️ End-to-end test timed out')
        except Exception as e:
            print(f'   ❌ End-to-end test error: {e}')
            import traceback
            traceback.print_exc()
    else:
        print('\n⚠️ Skipping end-to-end test - no API key available')

    # Cleanup
    try:
        await graphiti.close()
        print('\n🧹 Cleanup completed')
    except Exception as e:
        print(f'\n⚠️ Cleanup warning: {e}')


async def main():
    """Run debug tests."""
    print('🧠 Cerebras/Qwen Debug Session')
    print('=' * 50)
    
    try:
        await test_cerebras_components()
        print('\n🎯 Debug Summary:')
        print('  Check each test section above for specific results')
        print('  Key areas: Client creation, Database, LLM calls, Embeddings, End-to-end')
        
    except Exception as e:
        print(f'\n❌ Debug session failed: {e}')
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    asyncio.run(main())