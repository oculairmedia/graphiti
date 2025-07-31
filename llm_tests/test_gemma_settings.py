#!/usr/bin/env python3
"""
Test gemma3 with different temperature settings
"""

import json
import asyncio
import httpx
import time

TEST_CASES = [
    {
        "text": "John Smith is the CEO of Microsoft and married to Jane Doe.",
        "edges": [
            ("John Smith", "CEO_OF", "Microsoft"),
            ("John Smith", "MARRIED_TO", "Jane Doe")
        ]
    },
    {
        "text": "Apple acquired Beats Electronics for $3 billion. Tim Cook announced the deal.",
        "edges": [
            ("Apple", "ACQUIRED", "Beats Electronics"),
            ("Tim Cook", "ANNOUNCED", "deal")
        ]
    }
]

async def test_with_settings(temperature, top_k, top_p):
    """Test gemma3 with specific settings"""
    model = "gemma3:12b"
    base_url = "http://100.81.139.20:11434"
    
    print(f"\nTesting with temperature={temperature}, top_k={top_k}, top_p={top_p}")
    print("-" * 60)
    
    total_correct = 0
    total_expected = 0
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        for i, test in enumerate(TEST_CASES):
            print(f"Test {i+1}: {test['text'][:50]}...", end="", flush=True)
            
            prompt = f"""Extract ALL relationships from this text as a JSON array.

Text: "{test['text']}"

Format each relationship as: {{"source": "entity1", "relation": "RELATION_TYPE", "target": "entity2"}}

Return ONLY the JSON array, no other text. Example:
[{{"source": "John", "relation": "WORKS_AT", "target": "Google"}}]"""

            start = time.time()
            
            response = await client.post(
                f"{base_url}/api/chat",
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                    "options": {
                        "temperature": temperature,
                        "top_k": top_k,
                        "top_p": top_p
                    }
                }
            )
            
            elapsed = time.time() - start
            content = response.json()['message']['content']
            
            # Extract JSON
            edges = []
            try:
                # Try direct parse
                data = json.loads(content)
                if isinstance(data, list):
                    edges = data
                elif isinstance(data, dict):
                    for key in ['edges', 'relationships', 'data']:
                        if key in data and isinstance(data[key], list):
                            edges = data[key]
                            break
            except:
                # Try to find array in text
                import re
                match = re.search(r'\[.*?\]', content, re.DOTALL)
                if match:
                    try:
                        edges = json.loads(match.group())
                    except:
                        pass
            
            # Score
            found = set()
            for edge in edges:
                if isinstance(edge, dict) and all(k in edge for k in ['source', 'relation', 'target']):
                    found.add((
                        edge['source'].lower(),
                        edge['relation'].upper().replace(' ', '_'),
                        edge['target'].lower()
                    ))
            
            expected = set((s.lower(), r, t.lower()) for s, r, t in test['edges'])
            correct = len(found & expected)
            total_correct += correct
            total_expected += len(expected)
            
            print(f" Time: {elapsed:.1f}s, Found: {len(edges)}, Correct: {correct}/{len(expected)}")
            
            if i == 0 and edges:  # Show first example
                print(f"  Example output: {json.dumps(edges[0])}")
    
    accuracy = total_correct / total_expected if total_expected > 0 else 0
    print(f"\nOverall accuracy: {accuracy:.1%} ({total_correct}/{total_expected})")
    return accuracy

async def main():
    print("Testing gemma3:12b with different temperature settings")
    print("=" * 60)
    
    # Test with original settings (temperature=0)
    accuracy1 = await test_with_settings(0.0, 40, 0.9)
    
    # Test with new settings
    accuracy2 = await test_with_settings(1.0, 64, 0.95)
    
    # Test intermediate settings
    accuracy3 = await test_with_settings(0.5, 50, 0.92)
    
    print("\n" + "=" * 60)
    print("SUMMARY:")
    print(f"Temperature=0.0, top_k=40, top_p=0.9:   {accuracy1:.1%}")
    print(f"Temperature=1.0, top_k=64, top_p=0.95:  {accuracy2:.1%}")
    print(f"Temperature=0.5, top_k=50, top_p=0.92:  {accuracy3:.1%}")

if __name__ == "__main__":
    asyncio.run(main())