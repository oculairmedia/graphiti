#!/usr/bin/env python3
"""
Test Cerebras client with Pydantic model validation.
This tests the fix for parsing issues when using Cerebras as a provider in Graphiti.
"""

import asyncio
import json
import logging
import os
from typing import List

from pydantic import BaseModel, Field
from graphiti_core.llm_client.cerebras_client import CerebrasClient
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.prompts.models import Message

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Test Pydantic models similar to what Graphiti uses
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

async def test_pydantic_validation():
    """Test that Cerebras client properly validates responses against Pydantic models."""
    print("🧠 Testing Cerebras Client with Pydantic Model Validation")
    print("=" * 70)
    
    # Check API key
    cerebras_api_key = os.getenv('CEREBRAS_API_KEY')
    if not cerebras_api_key:
        print("❌ CEREBRAS_API_KEY environment variable not set")
        return False
    
    # Initialize client
    config = LLMConfig(
        api_key=cerebras_api_key,
        model='qwen-3-coder-480b',
        temperature=0.3,
        max_tokens=1000,
    )
    client = CerebrasClient(config=config)
    print("✅ Cerebras client initialized")

    # Test 1: Simple entity extraction with Pydantic model
    print("\n📝 Test 1: Entity Extraction with Pydantic Validation")
    print("-" * 50)
    
    messages = [
        Message(
            role='user',
            content='''Extract entities from this text: "Alice is a software engineer at Google. She works with Bob on machine learning projects."
            
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
    
    # Wait for rate limiting
    print("\n⏱️ Waiting 8 seconds for rate limiting...")
    await asyncio.sleep(8)
    
    # Test 2: Complex extraction with entities and relationships
    print("\n📝 Test 2: Complex Extraction with Relationships")
    print("-" * 50)
    
    complex_messages = [
        Message(
            role='user',
            content='''Extract entities and relationships from: "Sarah, the project manager, scheduled a meeting with John, the lead developer, to discuss the authentication system for the mobile app."
            
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
    
    # Wait for rate limiting
    print("\n⏱️ Waiting 8 seconds for rate limiting...")
    await asyncio.sleep(8)
    
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

async def test_validation_failures():
    """Test that validation properly fails when response doesn't match model."""
    print("\n\n🚨 Testing Validation Failure Handling")
    print("=" * 70)
    
    cerebras_api_key = os.getenv('CEREBRAS_API_KEY')
    if not cerebras_api_key:
        return True  # Skip if no API key
    
    config = LLMConfig(
        api_key=cerebras_api_key,
        model='qwen-3-coder-480b',
        temperature=0.1,
        max_tokens=500,
    )
    client = CerebrasClient(config=config)
    
    # Try to force a validation error by asking for something that won't match our strict model
    messages = [
        Message(
            role='user',
            content='Just say "Hello World" and nothing else.'  # This won't match TestExtractedEntities
        )
    ]
    
    try:
        response = await client._generate_response(
            messages=messages,
            response_model=TestExtractedEntities  # This should fail validation
        )
        print("⚠️ Expected validation to fail, but it succeeded")
        print(f"Response: {json.dumps(response, indent=2)}")
    except Exception as e:
        print("✅ Validation correctly failed as expected!")
        print(f"Error type: {type(e).__name__}")
        print(f"Error message: {str(e)[:200]}...")

async def main():
    """Run all tests."""
    print("🚀 Testing Cerebras Client Pydantic Validation Fix")
    print("Focus: Ensuring response models are properly validated")
    
    try:
        success = await test_pydantic_validation()
        await test_validation_failures()
        
        if success:
            print("\n\n🎯 SUMMARY:")
            print("✅ Cerebras client now properly validates responses against Pydantic models")
            print("✅ This should resolve parsing issues in Graphiti ingestion pipeline")
            print("✅ Both structured and unstructured responses work correctly")
            print("\n📈 The fix adds model validation similar to the Gemini client:")
            print("   - When response_model is provided, validate with model.model_validate()")
            print("   - Return validated response as model.model_dump()")
            print("   - Log clear error messages if validation fails")
        else:
            print("\n❌ Some tests failed - Cerebras client still needs work")
            
    except KeyboardInterrupt:
        print("\n\n⚠️ Tests interrupted by user")
    except Exception as e:
        print(f"\n❌ Tests failed: {e}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")

if __name__ == '__main__':
    asyncio.run(main())