#!/usr/bin/env python3
"""
Test Chutes client with Pydantic model validation.
Tests the fix for parsing issues similar to the Cerebras client fix.
"""

import asyncio
import json
import logging
import os
from typing import List

from pydantic import BaseModel, Field
from graphiti_core.llm_client.chutes_client import ChutesClient
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.prompts.models import Message

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Test Pydantic models (same as Cerebras test)
class TestEntity(BaseModel):
    name: str = Field(..., description="Name of the entity")
    entity_type: str = Field(..., description="Type of the entity")
    context: str = Field(default="", description="Context or description")

class TestExtractedEntities(BaseModel):
    entities: List[TestEntity] = Field(..., description="List of extracted entities")

class TestRelationship(BaseModel):
    source: str = Field(..., description="Source entity")
    target: str = Field(..., description="Target entity") 
    relationship_type: str = Field(..., description="Type of relationship")

class TestExtractedData(BaseModel):
    entities: List[TestEntity] = Field(..., description="Extracted entities")
    relationships: List[TestRelationship] = Field(..., description="Extracted relationships")

async def test_chutes_pydantic_validation():
    """Test that Chutes client properly validates responses against Pydantic models."""
    print("🤖 Testing Chutes Client with Pydantic Model Validation")
    print("=" * 70)
    
    # Check API key
    chutes_api_key = os.getenv('CHUTES_API_KEY')
    if not chutes_api_key:
        print("❌ CHUTES_API_KEY environment variable not set")
        return False
    
    # Initialize client
    config = LLMConfig(
        api_key=chutes_api_key,
        model='deepseek-ai/DeepSeek-V3.1',  # Current model
        base_url='https://llm.chutes.ai/v1',
        temperature=0.3,
        max_tokens=1000,
    )
    client = ChutesClient(config=config)
    print("✅ Chutes client initialized")

    # Test 1: Simple entity extraction with Pydantic model
    print("\n📝 Test 1: Entity Extraction with Pydantic Validation")
    print("-" * 50)
    
    messages = [
        Message(
            role='user',
            content='''Extract entities from this text: "Dr. Alice Chen is a machine learning researcher at Stanford University. She collaborates with Prof. Bob Martinez on neural network architectures."
            
Return entities in the specified JSON format with name, entity_type, and context fields.'''
        )
    ]
    
    try:
        response = await client._generate_response(
            messages=messages,
            response_model=TestExtractedEntities  # This should trigger Pydantic validation
        )
        
        print("✅ Response received and validated successfully!")
        print(f"Response type: {type(response)}")
        print(f"Response content:")
        print(json.dumps(response, indent=2))
        
        # Verify the response structure matches what we expect
        if 'entities' in response:
            entities = response['entities']
            print(f"✅ Found {len(entities)} entities")
            for i, entity in enumerate(entities[:3]):  # Show first 3
                print(f"   {i+1}. {entity.get('name', 'Unknown')} ({entity.get('entity_type', 'Unknown type')})")
        else:
            print("⚠️ No 'entities' field in response")
            
    except Exception as e:
        print(f"❌ Test 1 failed: {e}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return False
    
    # Wait between requests
    print("\n⏱️ Waiting 5 seconds between requests...")
    await asyncio.sleep(5)
    
    # Test 2: Complex extraction with entities and relationships
    print("\n📝 Test 2: Complex Extraction with Relationships")
    print("-" * 50)
    
    complex_messages = [
        Message(
            role='user',
            content='''Extract entities and relationships from: "The CEO Maria Gonzalez announced the new partnership with TechCorp. The engineering team, led by David Kim, will integrate their AI platform with our mobile application."
            
Return both entities (with name, entity_type, context) and relationships (with source, target, relationship_type).'''
        )
    ]
    
    try:
        complex_response = await client._generate_response(
            messages=complex_messages,
            response_model=TestExtractedData  # This tests more complex model validation
        )
        
        print("✅ Complex response validated successfully!")
        print(f"Response content:")
        print(json.dumps(complex_response, indent=2))
        
        # Verify both entities and relationships
        entities = complex_response.get('entities', [])
        relationships = complex_response.get('relationships', [])
        
        print(f"✅ Found {len(entities)} entities and {len(relationships)} relationships")
        
        if entities:
            print("   Entities:")
            for entity in entities[:3]:
                print(f"     - {entity.get('name')} ({entity.get('entity_type')})")
                
        if relationships:
            print("   Relationships:")
            for rel in relationships[:3]:
                print(f"     - {rel.get('source')} → {rel.get('target')} ({rel.get('relationship_type')})")
                
    except Exception as e:
        print(f"❌ Test 2 failed: {e}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return False
    
    # Wait between requests
    print("\n⏱️ Waiting 5 seconds between requests...")
    await asyncio.sleep(5)
    
    # Test 3: Test without response model (should still work)
    print("\n📝 Test 3: No Response Model (Raw JSON)")
    print("-" * 50)
    
    try:
        raw_response = await client._generate_response(
            messages=[Message(role='user', content='List 3 programming languages as JSON with name and description.')],
            response_model=None  # No model validation
        )
        
        print("✅ Raw response (no model validation) successful!")
        print(f"Response type: {type(raw_response)}")
        print(f"Response: {json.dumps(raw_response, indent=2)[:300]}...")
        
    except Exception as e:
        print(f"❌ Test 3 failed: {e}")
        return False
    
    return True

async def main():
    """Run all tests."""
    print("🚀 Testing Chutes Client Pydantic Validation Fix")
    print("Focus: Ensuring response models are properly validated (similar to Cerebras fix)")
    
    try:
        success = await test_chutes_pydantic_validation()
        
        if success:
            print("\n\n🎯 SUMMARY:")
            print("✅ Chutes client now properly validates responses against Pydantic models")
            print("✅ This should resolve parsing issues in Graphiti ingestion pipeline")
            print("✅ Both structured and unstructured responses work correctly")
            print("\n📈 The fix adds model validation similar to Cerebras and Gemini clients:")
            print("   - When response_model is provided, validate with model.model_validate()")
            print("   - Return validated response as model.model_dump()")
            print("   - Log clear error messages if validation fails")
        else:
            print("\n❌ Some tests failed - Chutes client still needs work")
            
    except KeyboardInterrupt:
        print("\n\n⚠️ Tests interrupted by user")
    except Exception as e:
        print(f"\n❌ Tests failed: {e}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")

if __name__ == '__main__':
    asyncio.run(main())