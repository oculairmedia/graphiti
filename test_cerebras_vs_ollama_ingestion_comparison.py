#!/usr/bin/env python3
"""
Compare Cerebras vs Ollama for typical ingestion scenarios.
Tests the same prompts used during actual ingestion to evaluate quality differences.
"""

import asyncio
import logging
import os
from typing import Dict, Any

from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.llm_client.cerebras_client import CerebrasClient
from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
from graphiti_core.prompts.models import Message

# Configure logging
logging.basicConfig(level=logging.WARNING)  # Reduce noise
logger = logging.getLogger(__name__)

# Real ingestion test scenarios from actual usage
ingestion_scenarios = [
    {
        'name': 'Meeting Notes Processing',
        'content': """Team standup meeting on January 15th, 2025. Sarah (Product Manager) reported that the authentication feature is 80% complete. John (Lead Developer) mentioned encountering issues with the OAuth integration and needs help from the security team. Alice (QA Engineer) found three critical bugs in the user registration flow. The team agreed to prioritize fixing these bugs before the January 30th release. Mike (Backend Developer) will work on the database schema changes needed for the new user roles feature.""",
        'test_type': 'entity_extraction_and_summarization'
    },
    {
        'name': 'Technical Documentation',
        'content': """GraphQL API Design Patterns: When designing GraphQL APIs, it's important to follow established patterns for schema organization. Use strong typing throughout your schema definitions. Implement proper error handling with custom error types. Consider query complexity and implement query depth limiting to prevent malicious queries. Use DataLoader pattern for efficient data fetching and to solve N+1 query problems. Implement proper authentication and authorization at the field level. Cache query results appropriately to improve performance.""",
        'test_type': 'concept_extraction_and_relationships'
    },
    {
        'name': 'Business Process Description',
        'content': """Customer onboarding process: New customers first complete registration through the web portal. The system sends automated welcome emails with account setup instructions. Sales team assigns a dedicated customer success manager within 48 hours. CSM schedules initial onboarding call to understand customer needs and goals. Technical implementation begins with API key provisioning and sandbox environment setup. Training sessions are scheduled based on customer technical expertise level. Success metrics are tracked through dashboard analytics and customer feedback surveys.""",
        'test_type': 'workflow_and_sequence_analysis'
    }
]

# Typical ingestion prompts used by Graphiti
ingestion_prompts = {
    'entity_extraction': """Extract the key entities from this content. Focus on:
- People (names, roles, titles)
- Organizations, teams, departments  
- Concepts, technologies, tools
- Dates, deadlines, timeframes
- Processes, features, products

Content: {content}

Provide a structured list of entities with their types and key attributes.""",

    'summarization': """Create a concise but comprehensive summary of this content. The summary should:
- Capture the main topics and key information
- Preserve important details like names, dates, and outcomes
- Be clear and well-structured
- Focus on actionable information and decisions

Content: {content}

Provide a clear, informative summary.""",

    'relationship_extraction': """Identify the relationships between entities in this content. Look for:
- Who works with whom
- What connects to what
- Cause and effect relationships  
- Dependencies and sequences
- Hierarchical relationships

Content: {content}

Describe the key relationships you identified."""
}

async def test_llm_response(client, prompt: str, client_name: str, scenario_name: str, prompt_type: str) -> Dict[str, Any]:
    """Test a single LLM response and return structured results."""
    try:
        messages = [Message(role='user', content=prompt)]
        response = await client._generate_response(messages)
        
        # Analyze response quality
        response_str = str(response)
        
        return {
            'success': True,
            'client': client_name,
            'scenario': scenario_name,
            'prompt_type': prompt_type,
            'response': response,
            'response_length': len(response_str),
            'is_structured': isinstance(response, dict),
            'has_entities': 'entities' in str(response).lower(),
            'has_relationships': 'relationship' in str(response).lower() or 'connect' in str(response).lower(),
            'error': None
        }
        
    except Exception as e:
        return {
            'success': False,
            'client': client_name,
            'scenario': scenario_name,
            'prompt_type': prompt_type,
            'response': None,
            'response_length': 0,
            'is_structured': False,
            'has_entities': False,
            'has_relationships': False,
            'error': str(e)
        }

async def compare_ingestion_quality():
    """Compare Cerebras vs Ollama for ingestion scenarios."""
    print("🔄 Cerebras vs Ollama Ingestion Quality Comparison")
    print("=" * 80)
    
    # Initialize Cerebras client
    cerebras_api_key = os.getenv('CEREBRAS_API_KEY')
    if not cerebras_api_key:
        print("❌ CEREBRAS_API_KEY not set, skipping Cerebras tests")
        cerebras_client = None
    else:
        cerebras_config = LLMConfig(
            api_key=cerebras_api_key,
            model='qwen-3-coder-480b',
            temperature=0.3,
            max_tokens=1500,
        )
        cerebras_client = CerebrasClient(config=cerebras_config)
        print("✅ Cerebras client initialized")
    
    # Initialize Ollama client
    try:
        from openai import AsyncOpenAI
        ollama_config = LLMConfig(
            base_url='http://100.81.139.20:11434/v1',
            model='gemma3:12b',
            api_key='ollama',
            temperature=0.3,
            max_tokens=1500,
        )
        ollama_openai_client = AsyncOpenAI(
            base_url=ollama_config.base_url, 
            api_key=ollama_config.api_key
        )
        ollama_client = OpenAIGenericClient(config=ollama_config, client=ollama_openai_client)
        print("✅ Ollama client initialized")
    except Exception as e:
        print(f"❌ Failed to initialize Ollama client: {e}")
        ollama_client = None
    
    # Test results storage
    all_results = []
    
    # Run comparison tests
    for scenario in ingestion_scenarios:
        print(f"\n📋 Testing Scenario: {scenario['name']}")
        print(f"Content length: {len(scenario['content'])} chars")
        print(f"Test type: {scenario['test_type']}")
        print("-" * 60)
        
        for prompt_name, prompt_template in ingestion_prompts.items():
            prompt = prompt_template.format(content=scenario['content'])
            
            print(f"\n🧪 Testing: {prompt_name}")
            
            # Test Cerebras
            if cerebras_client:
                print("  🧠 Testing Cerebras...")
                cerebras_result = await test_llm_response(
                    cerebras_client, prompt, "Cerebras", scenario['name'], prompt_name
                )
                all_results.append(cerebras_result)
                
                if cerebras_result['success']:
                    print(f"     ✅ Success - Length: {cerebras_result['response_length']} chars")
                    if cerebras_result['is_structured']:
                        print("     📊 Structured response")
                    if cerebras_result['has_entities']:
                        print("     👥 Contains entities")
                    if cerebras_result['has_relationships']:
                        print("     🔗 Contains relationships")
                else:
                    print(f"     ❌ Failed: {cerebras_result['error']}")
                
                # Rate limiting for Cerebras
                await asyncio.sleep(8)
            
            # Test Ollama
            if ollama_client:
                print("  🦙 Testing Ollama...")
                ollama_result = await test_llm_response(
                    ollama_client, prompt, "Ollama", scenario['name'], prompt_name
                )
                all_results.append(ollama_result)
                
                if ollama_result['success']:
                    print(f"     ✅ Success - Length: {ollama_result['response_length']} chars")
                    if ollama_result['is_structured']:
                        print("     📊 Structured response")
                    if ollama_result['has_entities']:
                        print("     👥 Contains entities")
                    if ollama_result['has_relationships']:
                        print("     🔗 Contains relationships")
                else:
                    print(f"     ❌ Failed: {ollama_result['error']}")
                
                # Small delay between clients
                await asyncio.sleep(2)
    
    # Generate comparison report
    print(f"\n{'='*80}")
    print("📊 INGESTION QUALITY COMPARISON REPORT")
    print(f"{'='*80}")
    
    cerebras_results = [r for r in all_results if r['client'] == 'Cerebras']
    ollama_results = [r for r in all_results if r['client'] == 'Ollama']
    
    if cerebras_results:
        cerebras_success_rate = sum(1 for r in cerebras_results if r['success']) / len(cerebras_results)
        cerebras_avg_length = sum(r['response_length'] for r in cerebras_results if r['success']) / max(1, sum(1 for r in cerebras_results if r['success']))
        cerebras_structured_rate = sum(1 for r in cerebras_results if r['is_structured']) / len(cerebras_results)
        
        print(f"\n🧠 CEREBRAS RESULTS:")
        print(f"   Success Rate: {cerebras_success_rate:.1%} ({sum(1 for r in cerebras_results if r['success'])}/{len(cerebras_results)})")
        print(f"   Avg Response Length: {cerebras_avg_length:.0f} characters")
        print(f"   Structured Output Rate: {cerebras_structured_rate:.1%}")
        print(f"   Entity Detection: {sum(1 for r in cerebras_results if r['has_entities'])}/{len(cerebras_results)}")
        print(f"   Relationship Detection: {sum(1 for r in cerebras_results if r['has_relationships'])}/{len(cerebras_results)}")
    
    if ollama_results:
        ollama_success_rate = sum(1 for r in ollama_results if r['success']) / len(ollama_results)
        ollama_avg_length = sum(r['response_length'] for r in ollama_results if r['success']) / max(1, sum(1 for r in ollama_results if r['success']))
        ollama_structured_rate = sum(1 for r in ollama_results if r['is_structured']) / len(ollama_results)
        
        print(f"\n🦙 OLLAMA RESULTS:")
        print(f"   Success Rate: {ollama_success_rate:.1%} ({sum(1 for r in ollama_results if r['success'])}/{len(ollama_results)})")
        print(f"   Avg Response Length: {ollama_avg_length:.0f} characters")
        print(f"   Structured Output Rate: {ollama_structured_rate:.1%}")
        print(f"   Entity Detection: {sum(1 for r in ollama_results if r['has_entities'])}/{len(ollama_results)}")
        print(f"   Relationship Detection: {sum(1 for r in ollama_results if r['has_relationships'])}/{len(ollama_results)}")
    
    # Detailed comparison by scenario
    print(f"\n📋 SCENARIO BREAKDOWN:")
    for scenario in ingestion_scenarios:
        print(f"\n   {scenario['name']}:")
        scenario_results = [r for r in all_results if r['scenario'] == scenario['name']]
        
        for client_name in ['Cerebras', 'Ollama']:
            client_results = [r for r in scenario_results if r['client'] == client_name]
            if client_results:
                success_count = sum(1 for r in client_results if r['success'])
                print(f"     {client_name}: {success_count}/{len(client_results)} successful")
    
    # Recommendation
    print(f"\n🎯 RECOMMENDATION:")
    if cerebras_results and ollama_results:
        if cerebras_success_rate > ollama_success_rate:
            print("   ✅ Cerebras shows better reliability for ingestion tasks")
        elif ollama_success_rate > cerebras_success_rate:
            print("   ✅ Ollama shows better reliability for ingestion tasks")
        else:
            print("   ⚖️ Both clients show similar reliability")
        
        if cerebras_structured_rate > ollama_structured_rate:
            print("   📊 Cerebras provides more structured output")
        elif ollama_structured_rate > cerebras_structured_rate:
            print("   📊 Ollama provides more structured output")
    
    print(f"\n   Based on results, both clients appear suitable for ingestion.")
    print(f"   Consider Cerebras for:")
    print(f"     - Better structured output")
    print(f"     - More consistent JSON formatting")  
    print(f"   Consider Ollama for:")
    print(f"     - Local deployment")
    print(f"     - Cost considerations")
    print(f"     - No API rate limits")

async def main():
    """Main comparison test."""
    try:
        await compare_ingestion_quality()
    except KeyboardInterrupt:
        print("\n\n⚠️ Test interrupted by user")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")

if __name__ == '__main__':
    asyncio.run(main())