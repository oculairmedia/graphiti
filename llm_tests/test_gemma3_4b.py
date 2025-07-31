#!/usr/bin/env python3
"""
Quick test of gemma3:4b for edge extraction
"""

import json
import asyncio
import httpx
import time

async def test_gemma3_4b():
    model = "gemma3:4b"
    base_url = "http://100.81.139.20:11434"
    
    test_texts = [
        "John Smith is the CEO of Microsoft and married to Jane Doe.",
        "Apple acquired Beats Electronics for $3 billion. Tim Cook announced the deal."
    ]
    
    print(f"Testing {model} for edge extraction")
    print("=" * 60)
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        for i, text in enumerate(test_texts):
            print(f"\nTest {i+1}: {text}")
            
            prompt = f"""Extract ALL relationships from this text as a JSON array.

Text: "{text}"

Format each relationship as: {{"source": "entity1", "relation": "RELATION_TYPE", "target": "entity2"}}

Return ONLY the JSON array, no other text. Example:
[{{"source": "John", "relation": "WORKS_AT", "target": "Google"}}]"""

            print("Extracting...", end="", flush=True)
            start = time.time()
            
            response = await client.post(
                f"{base_url}/api/chat",
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                    "options": {
                        "temperature": 1.0,
                        "top_k": 64,
                        "top_p": 0.95
                    }
                }
            )
            
            elapsed = time.time() - start
            content = response.json()['message']['content']
            
            print(f" Done! ({elapsed:.1f}s)")
            print(f"Raw output: {content[:200]}...")
            
            # Try to parse
            try:
                # Direct parse
                edges = json.loads(content)
                if isinstance(edges, list):
                    print(f"Extracted {len(edges)} edges:")
                    for edge in edges:
                        print(f"  - {edge}")
                else:
                    print(f"Got object instead of array: {edges}")
            except json.JSONDecodeError:
                # Try to find JSON in text
                import re
                match = re.search(r'\[.*?\]', content, re.DOTALL)
                if match:
                    try:
                        edges = json.loads(match.group())
                        print(f"Extracted {len(edges)} edges from text:")
                        for edge in edges:
                            print(f"  - {edge}")
                    except:
                        print("Could not parse JSON from text")
                else:
                    print("No JSON array found in output")

if __name__ == "__main__":
    asyncio.run(test_gemma3_4b())