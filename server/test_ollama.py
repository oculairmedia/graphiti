#!/usr/bin/env python3

import asyncio
import os

from openai import AsyncOpenAI


async def test_ollama():
    print('Testing Ollama connection...')

    client = AsyncOpenAI(base_url='http://100.81.139.20:11434/v1', api_key='ollama')

    try:
        print('Making chat completion request...')
        response = await client.chat.completions.create(
            model='qwen3:32b',
            messages=[
                {'role': 'user', 'content': "Hello, can you respond with just 'Ollama is working!'"}
            ],
            max_tokens=50,
        )

        print(f'Response: {response.choices[0].message.content}')
        print('✅ Ollama integration is working!')

    except Exception as e:
        print(f'❌ Error: {e}')
        import traceback

        traceback.print_exc()


if __name__ == '__main__':
    asyncio.run(test_ollama())
