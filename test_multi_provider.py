#!/usr/bin/env python3
"""Test multi-provider evolution with OpenAI + Gemini proxies only (no Z.AI)."""
import os
import sys
sys.path.insert(0, '/opt/stacks/graphiti')

from dotenv import load_dotenv
load_dotenv()

from graphiti_core.dspy.openevolve.runner import (
    ProviderConfig,
    MultiProviderManager,
    EvolutionConfig,
    OpenEvolveRunner,
)

# Create providers WITHOUT Z.AI (to avoid rate limit conflicts with Graphiti)
providers = [
    ProviderConfig(
        name='openai-proxy',
        api_base='http://192.168.50.90:8082/v1',
        api_key='dummy',
        weight=1.0,
        models=[
            {'name': 'gpt5', 'weight': 1.0},
            {'name': 'gpt51', 'weight': 0.8},
            {'name': 'codexmini', 'weight': 0.6},
        ],
    ),
    ProviderConfig(
        name='gemini-proxy',
        api_base='http://192.168.50.90:8083/v1',
        api_key=os.environ.get('GOOGLE_API_KEY', ''),
        weight=1.0,
        models=[
            {'name': 'gemini-2.5-flash', 'weight': 1.0},
            {'name': 'gemini-2.5-pro', 'weight': 0.7},
        ],
    ),
]

print("=== Multi-Provider Test (No Z.AI) ===")
print(f"Providers: {[p.name for p in providers]}")

manager = MultiProviderManager(providers, mode='sequential')

print("\n=== Sequential Round-Robin Test ===")
for i in range(6):
    config = manager.sample_model_config()
    print(f"{i+1}. {config['name']} @ {config['api_base'][:35]}...")

print("\n=== Provider Stats ===")
for p in manager.get_stats()['providers']:
    print(f"  {p['name']}: {p['calls']} calls")

# Test actual API calls
print("\n=== Testing Actual API Calls ===")
import httpx

for provider in providers:
    model = provider.models[0]
    model_name = model['name'] if isinstance(model, dict) else model
    print(f"\nTesting {provider.name} with {model_name}...")

    try:
        # Use streaming for OpenAI proxy compatibility
        with httpx.stream(
            "POST",
            f"{provider.api_base}/chat/completions",
            headers={
                "Authorization": f"Bearer {provider.api_key}",
                "Content-Type": "application/json",
                "Accept-Encoding": "identity",  # Disable compression
            },
            json={
                "model": model_name,
                "messages": [{"role": "user", "content": "Say 'test ok' in exactly 2 words"}],
                "max_tokens": 20,
                "stream": True,
            },
            timeout=30.0,
        ) as response:
            if response.status_code == 200:
                # Collect streamed content
                content = ""
                for line in response.iter_lines():
                    if line.startswith("data: ") and line != "data: [DONE]":
                        try:
                            import json
                            chunk = json.loads(line[6:])
                            delta = chunk.get('choices', [{}])[0].get('delta', {})
                            content += delta.get('content', '')
                        except:
                            pass
                print(f"  ✓ Success: {content[:50]}")
            else:
                print(f"  ✗ Error {response.status_code}: {response.text[:100]}")
    except Exception as e:
        print(f"  ✗ Exception: {e}")

print("\n=== All providers tested! ===")
