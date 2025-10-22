#!/usr/bin/env python3
"""
Minimal test to debug Ollama integration issues.
"""

import asyncio
import os
import sys
from datetime import datetime

print('🔍 Step 1: Environment Check')
print(f'   OPENAI_API_KEY: {"Set" if os.getenv("OPENAI_API_KEY") else "Not set"}')
print(f'   USE_OLLAMA: {os.getenv("USE_OLLAMA")}')

print('\n🔍 Step 2: Load .env.ollama')
from dotenv import load_dotenv

load_dotenv('.env.ollama', override=True)
print(f'   OPENAI_API_KEY after loading: {"Set" if os.getenv("OPENAI_API_KEY") else "Not set"}')
print(f'   USE_OLLAMA after loading: {os.getenv("USE_OLLAMA")}')

print('\n🔍 Step 3: Import Graphiti')
try:
    from use_ollama import Graphiti

    print('   ✅ Import successful')
except Exception as e:
    print(f'   ❌ Import failed: {e}')
    sys.exit(1)

print('\n🔍 Step 4: Test OpenAI API key directly')
try:
    import openai

    client = openai.Client(api_key=os.getenv('OPENAI_API_KEY'))
    # Just create the client, don't make a call
    print('   ✅ OpenAI client created')
except Exception as e:
    print(f'   ❌ OpenAI client error: {e}')


async def minimal_test():
    print('\n🔍 Step 5: Initialize Graphiti')
    try:
        # Don't even connect to DB, just create instance
        graphiti = Graphiti(uri='bolt://localhost:6389', user='', password='')
        print('   ✅ Graphiti instance created')

        # Check what we have
        print(f'   LLM Client: {type(graphiti.llm_client).__name__}')
        print(f'   Embedder: {type(graphiti.embedder).__name__}')

    except Exception as e:
        print(f'   ❌ Error: {e}')
        import traceback

        traceback.print_exc()

    print('\n🔍 Step 6: Test simple LLM call')
    try:
        # Just test if we can access the LLM
        if hasattr(graphiti, 'llm_client') and hasattr(graphiti.llm_client, 'config'):
            print(f'   Model configured: {graphiti.llm_client.config.model}')
            print('   ✅ LLM client is configured')
    except Exception as e:
        print(f'   ❌ LLM test error: {e}')


if __name__ == '__main__':
    asyncio.run(minimal_test())
