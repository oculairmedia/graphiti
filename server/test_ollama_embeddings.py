#!/usr/bin/env python3

import asyncio
import os

from openai import AsyncOpenAI


async def test_ollama_embeddings():
    print('Testing Ollama embeddings...')

    client = AsyncOpenAI(base_url='http://100.81.139.20:11434/v1', api_key='ollama')

    try:
        print('Making embeddings request...')
        response = await client.embeddings.create(
            model='mxbai-embed-large:latest', input='Hello, this is a test for embeddings'
        )

        print(f'✅ Embeddings response: {len(response.data)} embeddings')
        print(f'   First embedding dimensions: {len(response.data[0].embedding)}')
        print('✅ Ollama embeddings integration is working!')

    except Exception as e:
        print(f'❌ Error: {e}')
        import traceback

        traceback.print_exc()


if __name__ == '__main__':
    asyncio.run(test_ollama_embeddings())
