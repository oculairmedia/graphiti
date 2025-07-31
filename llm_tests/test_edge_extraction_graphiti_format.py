#!/usr/bin/env python3
"""
Test edge extraction using actual Graphiti prompt format
"""

import json
import asyncio
import httpx
import time
from datetime import datetime
from typing import List, Dict, Any

# Test cases with Graphiti format
TEST_CASES = [
    {
        "name": "CEO relationship",
        "episode_content": "John Smith is the CEO of Microsoft and married to Jane Doe.",
        "nodes": [
            {"id": 0, "name": "John Smith", "entity_types": ["Person"]},
            {"id": 1, "name": "Microsoft", "entity_types": ["Organization"]},
            {"id": 2, "name": "Jane Doe", "entity_types": ["Person"]}
        ],
        "expected_edges": [
            {"source_id": 0, "relation": "IS_CEO_OF", "target_id": 1},
            {"source_id": 0, "relation": "MARRIED_TO", "target_id": 2}
        ]
    },
    {
        "name": "Acquisition with date",
        "episode_content": "Apple acquired Beats Electronics for $3 billion in May 2014.",
        "nodes": [
            {"id": 0, "name": "Apple", "entity_types": ["Organization"]},
            {"id": 1, "name": "Beats Electronics", "entity_types": ["Organization"]}
        ],
        "expected_edges": [
            {"source_id": 0, "relation": "ACQUIRED", "target_id": 1}
        ]
    },
    {
        "name": "Complex relationships",
        "episode_content": "Dr. Sarah Chen graduated from MIT in 2010 and now works at Google Research in Tokyo.",
        "nodes": [
            {"id": 0, "name": "Dr. Sarah Chen", "entity_types": ["Person"]},
            {"id": 1, "name": "MIT", "entity_types": ["Organization", "University"]},
            {"id": 2, "name": "Google Research", "entity_types": ["Organization"]},
            {"id": 3, "name": "Tokyo", "entity_types": ["Location"]}
        ],
        "expected_edges": [
            {"source_id": 0, "relation": "GRADUATED_FROM", "target_id": 1},
            {"source_id": 0, "relation": "WORKS_AT", "target_id": 2},
            {"source_id": 2, "relation": "LOCATED_IN", "target_id": 3}
        ]
    }
]

def build_graphiti_prompt(test_case: Dict[str, Any]) -> str:
    """Build prompt using Graphiti's actual format"""
    
    system_prompt = ('You are an expert fact extractor that extracts fact triples from text. '
                    '1. Extracted fact triples should also be extracted with relevant date information.'
                    '2. Treat the CURRENT TIME as the time the CURRENT MESSAGE was sent. All temporal information should be extracted relative to this time.')
    
    # Mock edge types for common relationships
    edge_types = [
        {
            "fact_type_name": "WORKS_AT",
            "fact_type_signature": ("Person", "Organization"),
            "fact_type_description": "Person works at an organization"
        },
        {
            "fact_type_name": "IS_CEO_OF", 
            "fact_type_signature": ("Person", "Organization"),
            "fact_type_description": "Person is CEO of an organization"
        },
        {
            "fact_type_name": "MARRIED_TO",
            "fact_type_signature": ("Person", "Person"),
            "fact_type_description": "Person is married to another person"
        },
        {
            "fact_type_name": "ACQUIRED",
            "fact_type_signature": ("Organization", "Organization"),
            "fact_type_description": "Organization acquired another organization"
        }
    ]
    
    reference_time = datetime.utcnow().isoformat() + "Z"
    
    user_prompt = f"""
<PREVIOUS_MESSAGES>
[]
</PREVIOUS_MESSAGES>

<CURRENT_MESSAGE>
{test_case['episode_content']}
</CURRENT_MESSAGE>

<ENTITIES>
{json.dumps(test_case['nodes'], indent=2)}
</ENTITIES>

<REFERENCE_TIME>
{reference_time}  # ISO 8601 (UTC); used to resolve relative time mentions
</REFERENCE_TIME>

<FACT TYPES>
{json.dumps(edge_types, indent=2)}
</FACT TYPES>

# TASK
Extract all factual relationships between the given ENTITIES based on the CURRENT MESSAGE.
Only extract facts that:
- involve two DISTINCT ENTITIES from the ENTITIES list,
- are clearly stated or unambiguously implied in the CURRENT MESSAGE,
    and can be represented as edges in a knowledge graph.
- The FACT TYPES provide a list of the most important types of facts, make sure to extract facts of these types
- The FACT TYPES are not an exhaustive list, extract all facts from the message even if they do not fit into one
    of the FACT TYPES
- The FACT TYPES each contain their fact_type_signature which represents the source and target entity types.

You may use information from the PREVIOUS MESSAGES only to disambiguate references or support continuity.

# EXTRACTION RULES

1. Only emit facts where both the subject and object match IDs in ENTITIES.
2. Each fact must involve two **distinct** entities.
3. Use a SCREAMING_SNAKE_CASE string as the `relation_type` (e.g., FOUNDED, WORKS_AT).
4. Do not emit duplicate or semantically redundant facts.
5. The `fact_text` should quote or closely paraphrase the original source sentence(s).
6. Use `REFERENCE_TIME` to resolve vague or relative temporal expressions (e.g., "last week").
7. Do **not** hallucinate or infer temporal bounds from unrelated events.

# DATETIME RULES

- Use ISO 8601 with "Z" suffix (UTC) (e.g., 2025-04-30T00:00:00Z).
- If the fact is ongoing (present tense), set `valid_at` to REFERENCE_TIME.
- If a change/termination is expressed, set `invalid_at` to the relevant timestamp.
- Leave both fields `null` if no explicit or resolvable time is stated.
- If only a date is mentioned (no time), assume 00:00:00.
- If only a year is mentioned, use January 1st at 00:00:00.

Return a JSON object with an "edges" array. Each edge should have:
- relation_type: FACT_PREDICATE_IN_SCREAMING_SNAKE_CASE
- source_entity_id: The id of the source entity
- target_entity_id: The id of the target entity  
- fact: Brief description of the fact
- valid_at: When the fact became true (ISO 8601 or null)
- invalid_at: When the fact stopped being true (ISO 8601 or null)
"""
    
    return system_prompt, user_prompt

async def test_model_graphiti_format(model: str):
    """Test a model using Graphiti's actual prompt format"""
    
    print(f"\nTesting {model} with Graphiti format")
    print("=" * 60)
    
    base_url = "http://100.81.139.20:11434"
    total_correct = 0
    total_expected = 0
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        for test_case in TEST_CASES:
            print(f"\n{test_case['name']}: {test_case['episode_content'][:50]}...")
            
            system_prompt, user_prompt = build_graphiti_prompt(test_case)
            
            print("  Extracting...", end="", flush=True)
            start = time.time()
            
            response = await client.post(
                f"{base_url}/api/chat",
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "stream": False,
                    "options": {"temperature": 0.0}
                }
            )
            
            elapsed = time.time() - start
            content = response.json()['message']['content']
            
            # Parse response
            edges = []
            try:
                # Try to parse JSON
                if "```json" in content:
                    json_start = content.find("```json") + 7
                    json_end = content.find("```", json_start)
                    content = content[json_start:json_end].strip()
                
                data = json.loads(content)
                if isinstance(data, dict) and "edges" in data:
                    edges = data["edges"]
                elif isinstance(data, list):
                    edges = data
                    
            except Exception as e:
                print(f" ERROR parsing: {str(e)[:50]}")
                continue
            
            # Score results
            correct = 0
            for edge in edges:
                if all(k in edge for k in ['source_entity_id', 'target_entity_id', 'relation_type']):
                    for expected in test_case['expected_edges']:
                        if (edge['source_entity_id'] == expected['source_id'] and 
                            edge['target_entity_id'] == expected['target_id']):
                            correct += 1
                            break
            
            total_correct += correct
            total_expected += len(test_case['expected_edges'])
            
            print(f" Done! Time: {elapsed:.1f}s, Found: {len(edges)}, Correct: {correct}/{len(test_case['expected_edges'])}")
            
            # Show first edge as example
            if edges:
                print(f"  Example: {json.dumps(edges[0], indent=2)}")
    
    accuracy = total_correct / total_expected if total_expected > 0 else 0
    print(f"\nOverall accuracy: {accuracy:.1%} ({total_correct}/{total_expected})")
    return accuracy

async def main():
    models = ["gemma3:4b", "gemma3:12b", "exaone3.5:2.4b"]
    
    results = {}
    for model in models:
        accuracy = await test_model_graphiti_format(model)
        results[model] = accuracy
    
    print("\n" + "=" * 60)
    print("GRAPHITI FORMAT RESULTS")
    print("=" * 60)
    for model, acc in sorted(results.items(), key=lambda x: x[1], reverse=True):
        print(f"{model:20} {acc:6.1%}")

if __name__ == "__main__":
    asyncio.run(main())