#!/usr/bin/env python3
"""
Test if Cerebras/Qwen can handle structured outputs that Graphiti needs.
Adapted from test_ollama_structured.py for Cerebras testing.
"""

import asyncio
import json

from graphiti_core.llm_client.cerebras_client import CerebrasClient, DEFAULT_CEREBRAS_MODEL
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.prompts.models import Message


async def test_structured_output():
    """Test if Qwen can handle the kind of structured outputs Graphiti expects."""

    # Create Cerebras client
    config = LLMConfig(
        model=DEFAULT_CEREBRAS_MODEL,
        temperature=0.1,  # Low temperature for consistency
        max_tokens=500,
    )
    
    client = CerebrasClient(config=config)

    # A simplified version of what Graphiti might ask
    test_messages = [
        Message(
            role='system', 
            content='You are a JSON extractor. Always return valid JSON.'
        ),
        Message(
            role='user',
            content='''Extract entities from this text and return as JSON:
    
Text: "Alice is a software engineer. She works with Bob on the Graphiti project."

Return a JSON object with:
{
    "entities": [
        {"name": "...", "type": "person/organization/concept", "context": "..."}
    ],
    "relationships": [
        {"from": "...", "to": "...", "type": "..."}
    ]
}'''
        )
    ]

    print('🧠 Testing structured output with Qwen (Cerebras)...')
    print(f'📝 Model: {DEFAULT_CEREBRAS_MODEL}')

    try:
        response = await client._generate_response(
            messages=test_messages,
            max_tokens=500,
        )

        print('\n📤 Raw response:')
        print(json.dumps(response, indent=2))

        # Qwen should return structured JSON directly
        if isinstance(response, dict):
            print('\n✅ Valid structured response! Parsed structure:')
            print(json.dumps(response, indent=2))
            
            # Validate expected fields
            if 'entities' in response and 'relationships' in response:
                print('\n✅ Response has expected structure (entities & relationships)')
                print(f'   - Found {len(response.get("entities", []))} entities')
                print(f'   - Found {len(response.get("relationships", []))} relationships')
            else:
                print('\n⚠️ Response missing expected fields')
        else:
            print('\n❌ Response is not a dictionary structure')

    except Exception as e:
        print(f'\n❌ Error: {e}')
        import traceback
        traceback.print_exc()


async def test_complex_prompt():
    """Test a more complex prompt similar to what Graphiti uses."""

    config = LLMConfig(
        model=DEFAULT_CEREBRAS_MODEL,
        temperature=0.1,
        max_tokens=1000,
    )
    
    client = CerebrasClient(config=config)

    # This is more like what Graphiti actually sends
    complex_message = Message(
        role='user',
        content='''You are an AI assistant helping to build a knowledge graph. Extract entities and relationships from the given text.

IMPORTANT: Return ONLY a JSON object with no additional text or markdown formatting.

Text: "Sarah, the project manager, scheduled a meeting with John, the lead developer, to discuss the new graph visualization features for the Graphiti project."

Required JSON format:
{
    "entities": [
        {
            "name": "entity name",
            "type": "one of: person, organization, location, concept, event",
            "attributes": {"role": "if applicable", "description": "brief description"}
        }
    ],
    "relationships": [
        {
            "source": "entity name",
            "target": "entity name", 
            "type": "relationship type",
            "attributes": {}
        }
    ]
}'''
    )

    print('\n\n🧠 Testing complex structured prompt with Qwen...')

    try:
        print('⏱️ Sending request to Cerebras...')
        
        # Use asyncio.wait_for for timeout handling
        response = await asyncio.wait_for(
            client._generate_response(
                messages=[complex_message],
                max_tokens=1000,
            ),
            timeout=30.0
        )

        print('\n📤 Response received!')
        print(f'Response type: {type(response)}')
        
        if isinstance(response, dict):
            print('\n✅ Structured JSON response!')
            print(json.dumps(response, indent=2))
            
            # Validate structure quality
            entities = response.get('entities', [])
            relationships = response.get('relationships', [])
            
            print(f'\n📊 Quality Check:')
            print(f'   - Entities extracted: {len(entities)}')
            print(f'   - Relationships extracted: {len(relationships)}')
            
            # Check if entities have expected fields
            if entities and all('name' in e and 'type' in e for e in entities):
                print('   ✅ Entities have required fields')
            else:
                print('   ⚠️ Some entities missing required fields')
                
            # Check if relationships reference valid entities
            entity_names = [e.get('name') for e in entities]
            valid_relationships = []
            for rel in relationships:
                if rel.get('source') in entity_names and rel.get('target') in entity_names:
                    valid_relationships.append(rel)
                    
            print(f'   - Valid relationships: {len(valid_relationships)}/{len(relationships)}')
            
        else:
            print('\n⚠️ Response is not structured JSON')
            print(f'Raw response: {response}')

    except asyncio.TimeoutError:
        print('\n⏱️ Request timed out after 30 seconds')
    except Exception as e:
        print(f'\n❌ Error: {e}')
        import traceback
        traceback.print_exc()


async def test_qwen_specific_features():
    """Test features specific to Qwen's capabilities."""
    
    config = LLMConfig(
        model=DEFAULT_CEREBRAS_MODEL,
        temperature=0.3,  # Slightly higher for creativity
        max_tokens=800,
    )
    
    client = CerebrasClient(config=config)
    
    print('\n\n🎯 Testing Qwen-specific features...')
    
    # Test multilingual capability
    multilingual_message = Message(
        role='user',
        content='''Extract entities from this multilingual text:

English: "The AI researcher Dr. Smith published a paper on neural networks."
Spanish: "El investigador de IA Dr. García colaboró con la universidad."
French: "Le chercheur Dr. Martin développe des algorithmes innovants."

Return JSON with entities preserving original language:
{
    "entities": [
        {"name": "...", "type": "...", "language": "...", "context": "..."}
    ]
}'''
    )
    
    try:
        response = await client._generate_response(
            messages=[multilingual_message],
            max_tokens=800,
        )
        
        print('\n🌐 Multilingual extraction test:')
        if isinstance(response, dict) and 'entities' in response:
            entities = response['entities']
            print(f'   ✅ Extracted {len(entities)} multilingual entities')
            
            # Check language preservation
            languages_found = set()
            for entity in entities:
                if 'language' in entity:
                    languages_found.add(entity['language'])
                    
            print(f'   - Languages detected: {languages_found}')
            print('   - Sample entities:')
            for i, entity in enumerate(entities[:3]):
                print(f'     {i+1}. {entity.get("name", "N/A")} ({entity.get("language", "unknown")})')
        else:
            print('   ⚠️ Multilingual test failed')
            
    except Exception as e:
        print(f'   ❌ Multilingual test error: {e}')


async def test_reasoning_chains():
    """Test Qwen's chain-of-thought reasoning for complex extractions."""
    
    config = LLMConfig(
        model=DEFAULT_CEREBRAS_MODEL,
        temperature=0.2,
        max_tokens=1000,
    )
    
    client = CerebrasClient(config=config)
    
    reasoning_message = Message(
        role='user',
        content='''Analyze this complex scenario and extract entities with reasoning:

Text: "After the board meeting, CEO Johnson announced that TechCorp would acquire StartupAI for $50M. The deal, negotiated by lawyer Williams, will close in Q3 2024. This acquisition will strengthen TechCorp's AI capabilities, as StartupAI's team of 15 engineers will join the existing R&D department led by Dr. Chen."

Use step-by-step reasoning to identify entities and their relationships. Return JSON with:
{
    "reasoning": "Brief explanation of extraction logic",
    "entities": [...],
    "relationships": [...]
}'''
    )
    
    print('\n\n🤔 Testing reasoning chains...')
    
    try:
        response = await client._generate_response(
            messages=[reasoning_message],
            max_tokens=1000,
        )
        
        if isinstance(response, dict):
            print('\n✅ Reasoning response received!')
            
            if 'reasoning' in response:
                print(f'\n🧠 Reasoning provided:')
                print(f'   {response["reasoning"][:200]}...')
                
            entities = response.get('entities', [])
            relationships = response.get('relationships', [])
            
            print(f'\n📊 Extraction results:')
            print(f'   - Entities: {len(entities)}')
            print(f'   - Relationships: {len(relationships)}')
            
            # Check for complex entity types
            entity_types = [e.get('type') for e in entities]
            complex_types = ['organization', 'financial_event', 'legal_document']
            found_complex = [t for t in entity_types if t in complex_types]
            print(f'   - Complex entity types found: {found_complex}')
            
        else:
            print('   ⚠️ Reasoning test failed - no structured response')
            
    except Exception as e:
        print(f'   ❌ Reasoning test error: {e}')


async def main():
    """Run all structured output tests."""
    print('🧠 Cerebras/Qwen Structured Output Testing Suite')
    print('=' * 60)
    
    await test_structured_output()
    await test_complex_prompt()
    await test_qwen_specific_features()
    await test_reasoning_chains()
    
    print('\n✅ All tests completed!')


if __name__ == '__main__':
    asyncio.run(main())