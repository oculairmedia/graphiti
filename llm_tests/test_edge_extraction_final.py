#!/usr/bin/env python3
"""
Test edge extraction with proper format handling
"""

import json
import asyncio
import httpx
import time
import re
from typing import List, Dict, Any, Tuple

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
    },
    {
        "text": "Dr. Sarah Chen graduated from MIT in 2010 and now works at Google Research in Tokyo.",
        "edges": [
            ("Dr. Sarah Chen", "GRADUATED_FROM", "MIT"),
            ("Dr. Sarah Chen", "WORKS_AT", "Google Research"),
            ("Google Research", "LOCATED_IN", "Tokyo")
        ]
    },
    {
        "text": "The meeting between Biden and Xi Jinping will take place in San Francisco next week.",
        "edges": [
            ("meeting", "BETWEEN", "Biden"),
            ("meeting", "BETWEEN", "Xi Jinping"),
            ("meeting", "WILL_TAKE_PLACE_IN", "San Francisco")
        ]
    },
    {
        "text": "Tesla's factory in Berlin produces 5000 cars per week and employs over 12000 people.",
        "edges": [
            ("Tesla", "HAS_FACTORY_IN", "Berlin"),
            ("factory", "PRODUCES", "5000 cars per week"),
            ("factory", "EMPLOYS", "over 12000 people")
        ]
    },
    {
        "text": "Emma's brother David teaches physics at Harvard while their sister Lisa runs a startup.",
        "edges": [
            ("David", "BROTHER_OF", "Emma"),
            ("David", "TEACHES", "physics"),
            ("David", "TEACHES_AT", "Harvard"),
            ("Lisa", "SISTER_OF", "Emma"),
            ("Lisa", "RUNS", "startup")
        ]
    }
]

async def extract_edges(client: httpx.AsyncClient, model: str, text: str, json_mode: bool = False):
    """Extract edges using a model"""
    
    prompt = f"""Extract ALL relationships from this text as a JSON array.

Text: "{text}"

Format each relationship as: {{"source": "entity1", "relation": "RELATION_TYPE", "target": "entity2"}}

Return ONLY the JSON array, no other text. Example:
[{{"source": "John", "relation": "WORKS_AT", "target": "Google"}}]"""

    # Use custom settings for gemma3 models
    if model.startswith("gemma3"):
        options = {
            "temperature": 1.0,
            "top_k": 64,
            "top_p": 0.95
        }
    else:
        options = {"temperature": 0.0}
    
    request = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": options
    }
    
    if json_mode:
        request["format"] = "json"
    
    response = await client.post(
        "http://100.81.139.20:11434/api/chat",
        json=request
    )
    
    content = response.json()['message']['content']
    
    # Try to extract JSON from response
    edges = []
    
    # First try: direct JSON parse
    try:
        data = json.loads(content)
        if isinstance(data, list):
            edges = data
        elif isinstance(data, dict):
            # Sometimes models wrap in an object
            for key in ['edges', 'relationships', 'data', 'result', 'output']:
                if key in data and isinstance(data[key], list):
                    edges = data[key]
                    break
            if not edges and len(data) == 3 and all(k in data for k in ['source', 'relation', 'target']):
                # Single edge as object
                edges = [data]
    except:
        # Try to find JSON array in text
        array_match = re.search(r'\[.*?\]', content, re.DOTALL)
        if array_match:
            try:
                edges = json.loads(array_match.group())
            except:
                pass
    
    return edges, content

async def test_model(model: str):
    """Test a model's edge extraction capability"""
    print(f"\n{'='*60}")
    print(f"Testing: {model}")
    print(f"{'='*60}")
    
    results = []
    total_correct = 0
    total_expected = 0
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        for i, test in enumerate(TEST_CASES):
            print(f"\nTest {i+1}: {test['text'][:50]}...")
            
            # Try with and without JSON mode
            for json_mode in [False, True]:
                mode_str = "JSON mode" if json_mode else "Regular"
                print(f"  Trying {mode_str}...", end="", flush=True)
                try:
                    start = time.time()
                    edges, raw = await extract_edges(client, model, test['text'], json_mode)
                    elapsed = time.time() - start
                    
                    # Score the extraction
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
                    
                    print(f" Done! Time: {elapsed:4.1f}s, Found: {len(edges)}, Correct: {correct}/{len(expected)}")
                    
                    if edges and not json_mode:  # Use regular mode results for scoring
                        total_correct += correct
                        total_expected += len(expected)
                    
                    # Show first extraction for debugging
                    if edges and i == 0 and not json_mode:
                        print(f"  Example: {json.dumps(edges[0], indent=2)}")
                    
                except Exception as e:
                    print(f" ERROR: {str(e)[:50]}")
    
    # Summary
    accuracy = total_correct / total_expected if total_expected > 0 else 0
    print(f"\nOverall accuracy: {accuracy:.1%} ({total_correct}/{total_expected})")
    return accuracy

async def main():
    models = [
        "gemma3:1b",
        "gemma3:4b",
        "gemma3:12b",
        "exaone3.5:2.4b",
        "llama3.2:3b",
        "llama3.2:1b",
        "phi3:mini",
        "phi4:mini",
        "qwen2.5:3b",
        "granite3-dense:2b"
    ]
    
    # Check available
    print("Checking available models...", end="", flush=True)
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            response = await client.get("http://100.81.139.20:11434/api/tags")
            available = [m['name'] for m in response.json()['models']]
            models = [m for m in models if m in available]
            print(f" Found: {', '.join(models)}")
        except Exception as e:
            print(f" ERROR: {str(e)[:50]}")
            print("Continuing with all models...")
    
    results = {}
    for model in models:
        accuracy = await test_model(model)
        results[model] = accuracy
    
    # Final summary
    print(f"\n{'='*60}")
    print("EDGE EXTRACTION RESULTS")
    print(f"{'='*60}")
    for model, accuracy in sorted(results.items(), key=lambda x: x[1], reverse=True):
        print(f"{model:25} {accuracy:6.1%}")

if __name__ == "__main__":
    asyncio.run(main())