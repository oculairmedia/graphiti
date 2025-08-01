#!/usr/bin/env python3
"""
Ultra simple test for qwen3:8b
"""

import asyncio
from datetime import datetime

from openai import AsyncOpenAI


async def test_simple():
    client = AsyncOpenAI(base_url='http://100.81.139.20:11434/v1', api_key='ollama')

    print(f'Testing qwen3:8b at {datetime.now()}')
    print('Sending simple request...')

    start_time = datetime.now()

    try:
        response = await client.chat.completions.create(
            model='qwen3:8b',
            messages=[
                {'role': 'user', 'content': 'List 3 colors as JSON: ["color1", "color2", "color3"]'}
            ],
            temperature=0.0,
            max_tokens=50,
        )

        elapsed = (datetime.now() - start_time).total_seconds()
        print(f'\nResponse in {elapsed:.2f} seconds:')
        print(response.choices[0].message.content)

    except Exception as e:
        print(f'\nError: {e}')
        print(f'Time elapsed: {(datetime.now() - start_time).total_seconds():.2f} seconds')


if __name__ == '__main__':
    asyncio.run(test_simple())
