#!/usr/bin/env python3
"""
Test if Ollama/Mistral can handle structured outputs that Graphiti needs.
"""

import asyncio
import json

from openai import AsyncOpenAI


async def test_structured_output():
    """Test if Mistral can handle the kind of structured outputs Graphiti expects."""

    client = AsyncOpenAI(base_url='http://100.81.139.20:11434/v1', api_key='ollama')

    # A simplified version of what Graphiti might ask
    test_prompt = """
    Extract entities from this text and return as JSON:
    
    Text: "Alice is a software engineer. She works with Bob on the Graphiti project."
    
    Return a JSON object with:
    {
        "entities": [
            {"name": "...", "type": "person/organization/concept", "context": "..."}
        ],
        "relationships": [
            {"from": "...", "to": "...", "type": "..."}
        ]
    }
    """

    print('🔍 Testing structured output with Mistral...')
    print('📝 Prompt:', test_prompt[:100] + '...')

    try:
        response = await client.chat.completions.create(
            model='mistral:latest',
            messages=[
                {
                    'role': 'system',
                    'content': 'You are a JSON extractor. Always return valid JSON.',
                },
                {'role': 'user', 'content': test_prompt},
            ],
            temperature=0.1,  # Low temperature for consistency
            max_tokens=500,
        )

        result = response.choices[0].message.content
        print('\n📤 Raw response:')
        print(result)

        # Try to parse as JSON
        try:
            parsed = json.loads(result)
            print('\n✅ Valid JSON! Parsed structure:')
            print(json.dumps(parsed, indent=2))
        except json.JSONDecodeError as e:
            print(f'\n❌ Invalid JSON: {e}')

    except Exception as e:
        print(f'\n❌ Error: {e}')
        import traceback

        traceback.print_exc()


async def test_complex_prompt():
    """Test a more complex prompt similar to what Graphiti uses."""

    client = AsyncOpenAI(base_url='http://100.81.139.20:11434/v1', api_key='ollama')

    # This is more like what Graphiti actually sends
    complex_prompt = """
    You are an AI assistant helping to build a knowledge graph. Extract entities and relationships from the given text.

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
    }
    """

    print('\n\n🔍 Testing complex structured prompt...')

    try:
        print('⏱️ Sending request (this might take a while)...')
        response = await client.chat.completions.create(
            model='mistral:latest',
            messages=[{'role': 'user', 'content': complex_prompt}],
            temperature=0.1,
            max_tokens=1000,
            timeout=30.0,  # 30 second timeout
        )

        result = response.choices[0].message.content
        print('\n📤 Response received!')
        print('Length:', len(result), 'characters')
        print('\nFirst 200 chars:')
        print(result[:200] + '...' if len(result) > 200 else result)

        # Check if it's JSON-like
        if result.strip().startswith('{'):
            try:
                parsed = json.loads(result)
                print('\n✅ Looks like valid JSON!')
            except:
                print('\n⚠️ Starts with { but not valid JSON')
        else:
            print("\n⚠️ Response doesn't start with {")

    except asyncio.TimeoutError:
        print('\n⏱️ Request timed out after 30 seconds')
    except Exception as e:
        print(f'\n❌ Error: {e}')


async def main():
    await test_structured_output()
    await test_complex_prompt()


if __name__ == '__main__':
    asyncio.run(main())
