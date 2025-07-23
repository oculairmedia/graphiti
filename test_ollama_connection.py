#!/usr/bin/env python3
"""
Quick test script to verify Ollama connection and model availability.
"""

import asyncio
import json
from openai import AsyncOpenAI


OLLAMA_URL = "http://100.81.139.20:11434/v1"
MODEL = "mistral:latest"


async def test_connection():
    """Test Ollama connection and capabilities."""
    client = AsyncOpenAI(base_url=OLLAMA_URL, api_key="ollama")
    
    print(f"Testing connection to Ollama at {OLLAMA_URL}")
    print(f"Using model: {MODEL}\n")
    
    # Test 1: Basic completion
    print("1. Testing basic completion...")
    try:
        response = await client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": "Complete this: The capital of France is"}],
            max_tokens=20
        )
        print(f"✓ Response: {response.choices[0].message.content}\n")
    except Exception as e:
        print(f"✗ Failed: {e}\n")
        return False
    
    # Test 2: JSON output
    print("2. Testing JSON structured output...")
    try:
        response = await client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": "You are a helpful assistant that outputs valid JSON."},
                {"role": "user", "content": 'Extract entities from: "Python was created by Guido van Rossum". Output as JSON with format: {"entities": [{"name": "...", "type": "..."}]}'}
            ],
            max_tokens=200,
            response_format={"type": "json_object"}
        )
        content = response.choices[0].message.content
        print(f"✓ Raw response: {content}")
        
        # Try to parse JSON
        parsed = json.loads(content)
        print(f"✓ Parsed successfully: {json.dumps(parsed, indent=2)}\n")
    except json.JSONDecodeError as e:
        print(f"✗ JSON parsing failed: {e}")
        print(f"  Raw content: {content}\n")
    except Exception as e:
        print(f"✗ Request failed: {e}\n")
    
    # Test 3: Check available models
    print("3. Checking available models...")
    try:
        # Ollama doesn't support the models endpoint via OpenAI API
        # but we can still check if our model works
        models_to_test = ["mistral:latest", "nomic-embed-text:latest"]
        for model_name in models_to_test:
            try:
                response = await client.chat.completions.create(
                    model=model_name,
                    messages=[{"role": "user", "content": "Hi"}],
                    max_tokens=10
                )
                print(f"✓ {model_name} is available")
            except Exception:
                print(f"✗ {model_name} is not available")
    except Exception as e:
        print(f"Note: Cannot list models via OpenAI API. Test specific models instead.\n")
    
    return True


if __name__ == "__main__":
    asyncio.run(test_connection())