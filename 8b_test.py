#!/usr/bin/env python3
"""
Simple test to check if qwen3:8b can extract entities
"""

import asyncio
import json
from datetime import datetime

from openai import AsyncOpenAI


async def test_entity_extraction():
    # Test content
    test_content = """The user is working on implementing a graph visualization feature with React and Cosmograph. 
    They've asked to add zoom controls with buttons for zoom in, zoom out, and fit view. 
    The implementation involves GraphCanvas component and useImperativeHandle hook."""

    # Create client
    client = AsyncOpenAI(base_url='http://100.81.139.20:11434/v1', api_key='ollama')

    # Simple prompt
    prompt = f"""Extract entities from this text:

{test_content}

Return ONLY a JSON array with entity names, no other text. Example format:
["React", "GraphCanvas", "zoom controls"]"""

    print(f'Testing qwen3:8b at {datetime.now()}')
    print(f'Content length: {len(test_content)} characters')
    print('Sending request...')

    start_time = datetime.now()

    try:
        response = await client.chat.completions.create(
            model='qwen3:8b',
            messages=[
                {
                    'role': 'system',
                    'content': 'You are a JSON entity extractor. You output only valid JSON arrays.',
                },
                {'role': 'user', 'content': prompt},
            ],
            temperature=0.0,
            max_tokens=500,
        )

        elapsed = (datetime.now() - start_time).total_seconds()

        result = response.choices[0].message.content
        print(f'\nResponse received in {elapsed:.2f} seconds:')
        print(result)

        # Try to parse as JSON
        try:
            entities = json.loads(result)
            print(f'\nExtracted {len(entities)} entities:')
            for i, entity in enumerate(entities, 1):
                print(f'  {i}. {entity}')
        except:
            print('\nCould not parse response as JSON')

    except Exception as e:
        print(f'\nError: {e}')
        print(f'Elapsed time: {(datetime.now() - start_time).total_seconds():.2f} seconds')


if __name__ == '__main__':
    asyncio.run(test_entity_extraction())
