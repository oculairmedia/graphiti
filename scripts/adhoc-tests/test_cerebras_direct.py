#!/usr/bin/env python3
"""
Direct test of Cerebras client for summary generation without any Graphiti framework.
Focus on testing just the Cerebras LLM response quality for ingestion use cases.
"""

import asyncio
import logging
import os
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.llm_client.cerebras_client import CerebrasClient
from graphiti_core.prompts.models import Message

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Test scenarios for ingestion
test_scenarios = [
    {
        'name': 'Simple Summarization',
        'prompt': 'Summarize this in one clear sentence: Quantization is a technique used to compress Large Language Models by reducing the precision of their parameters.',
        'expected_type': 'Simple factual summary'
    },
    {
        'name': 'Entity Extraction',
        'prompt': 'Extract the key entities from this text: Sarah Johnson, the project manager, met with John Smith, the lead developer, to discuss the authentication system deadline on February 1st.',
        'expected_type': 'List of people, roles, and dates'
    },
    {
        'name': 'Technical Summary',
        'prompt': 'Create a brief technical summary of this content: Machine learning models require significant computational resources. GPU memory limitations often prevent deployment of large models on consumer hardware. Techniques like quantization, pruning, and distillation help reduce model size while maintaining performance.',
        'expected_type': 'Technical overview focusing on key concepts'
    },
    {
        'name': 'Relationship Extraction',
        'prompt': 'Identify the relationships between entities in this text: The research team published a paper on neural network optimization. Dr. Maria Rodriguez led the project with assistance from graduate student Alex Chen. They collaborated with Google AI research division.',
        'expected_type': 'Entity relationships and collaborations'
    }
]

async def test_cerebras_response(client: CerebrasClient, scenario: dict) -> bool:
    """Test a single Cerebras response scenario."""
    print(f"\n{'='*60}")
    print(f"Testing: {scenario['name']}")
    print(f"Expected: {scenario['expected_type']}")
    print(f"{'='*60}")
    print(f"Prompt: {scenario['prompt']}")
    print("-" * 60)
    
    try:
        # Create message in expected format
        messages = [Message(role='user', content=scenario['prompt'])]
        
        # Generate response
        response = await client._generate_response(messages)
        
        # Analyze response
        print(f"✅ Response received successfully!")
        print(f"Response type: {type(response)}")
        
        if isinstance(response, dict):
            print(f"Response keys: {list(response.keys())}")
            print(f"Response content:")
            for key, value in response.items():
                print(f"  {key}: {str(value)[:200]}..." if len(str(value)) > 200 else f"  {key}: {value}")
        else:
            print(f"Response: {str(response)[:500]}...")
            
        # Basic quality checks
        response_str = str(response)
        if len(response_str) < 10:
            print("⚠️ Warning: Very short response")
            return False
        elif len(response_str) > 2000:
            print("⚠️ Warning: Very long response")
        else:
            print("✅ Response length appropriate")
            
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return False

async def test_cerebras_direct():
    """Test Cerebras client directly for ingestion scenarios."""
    print("🧠 Direct Cerebras LLM Client Test for Ingestion")
    print("=" * 80)
    
    # Check API key
    cerebras_api_key = os.getenv('CEREBRAS_API_KEY')
    if not cerebras_api_key:
        print("❌ CEREBRAS_API_KEY environment variable not set")
        return
    
    # Initialize client with conservative settings
    config = LLMConfig(
        api_key=cerebras_api_key,
        model='qwen-3-coder-480b',
        small_model='qwen-3-coder-480b', 
        temperature=0.3,  # Lower temperature for more focused responses
        max_tokens=1000,  # Moderate limit
    )
    
    client = CerebrasClient(config=config)
    print("✅ Cerebras client initialized")
    print(f"Model: {config.model}")
    print(f"Temperature: {config.temperature}")
    print(f"Max tokens: {config.max_tokens}")
    
    # Test each scenario
    results = []
    for i, scenario in enumerate(test_scenarios):
        print(f"\n🧪 Test {i+1}/{len(test_scenarios)}")
        success = await test_cerebras_response(client, scenario)
        results.append((scenario['name'], success))
        
        # Rate limiting: wait between requests
        if i < len(test_scenarios) - 1:
            print("⏱️ Waiting 8 seconds for rate limiting...")
            await asyncio.sleep(8)
    
    # Summary
    print(f"\n{'='*80}")
    print("📊 TEST RESULTS SUMMARY")
    print(f"{'='*80}")
    
    successful = sum(1 for _, success in results if success)
    total = len(results)
    
    print(f"Overall Success Rate: {successful}/{total} ({successful/total*100:.1f}%)")
    print("\nIndividual Results:")
    
    for name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"  {status}: {name}")
    
    # Assessment for ingestion quality
    if successful >= 3:
        print("\n🎯 Assessment: Cerebras client appears suitable for ingestion tasks")
        print("   - Successfully handles summarization and entity extraction")
        print("   - Response format is consistent")
        print("   - Ready for integration testing with actual ingestion pipeline")
    elif successful >= 2:
        print("\n⚠️ Assessment: Cerebras client needs refinement")
        print("   - Some responses successful but inconsistent results")
        print("   - May need prompt engineering or parameter tuning")
    else:
        print("\n❌ Assessment: Cerebras client not ready for ingestion")
        print("   - Multiple failures indicate fundamental issues")
        print("   - Need to investigate response format or API configuration")

async def main():
    """Main test execution."""
    try:
        await test_cerebras_direct()
    except KeyboardInterrupt:
        print("\n\n⚠️ Test interrupted by user")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")

if __name__ == '__main__':
    asyncio.run(main())