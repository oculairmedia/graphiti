#!/usr/bin/env python3
"""
Test node deduplication using Ollama's JSON mode (format: "json").
This is different from structured output and may work with more models.
"""

import asyncio
import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx

# Test cases (same as before)
TEST_CASES = [
    {
        'name': 'Basic name variations',
        'extracted_nodes': [
            {'id': 0, 'name': 'Bob Smith', 'entity_type': 'Person'},
            {'id': 1, 'name': 'Microsoft Corporation', 'entity_type': 'Organization'},
            {'id': 2, 'name': 'New York City', 'entity_type': 'Location'},
        ],
        'existing_nodes': [
            {'idx': 0, 'name': 'Bob S.', 'entity_types': ['Person']},
            {'idx': 1, 'name': 'Microsoft Corp', 'entity_types': ['Organization']},
            {'idx': 2, 'name': 'NYC', 'entity_types': ['Location']},
            {'idx': 3, 'name': 'Alice Johnson', 'entity_types': ['Person']},
        ],
        'expected_mappings': {
            0: 0,  # Bob Smith -> Bob S.
            1: 1,  # Microsoft Corporation -> Microsoft Corp
            2: 2,  # New York City -> NYC
        },
    },
    {
        'name': 'Overlapping duplicates',
        'extracted_nodes': [
            {'id': 0, 'name': 'Robert Smith', 'entity_type': 'Person'},
            {'id': 1, 'name': 'Bob Smith', 'entity_type': 'Person'},
            {'id': 2, 'name': 'R. Smith', 'entity_type': 'Person'},
        ],
        'existing_nodes': [
            {'idx': 0, 'name': 'Bob S.', 'entity_types': ['Person']},
            {'idx': 1, 'name': 'Alice Johnson', 'entity_types': ['Person']},
        ],
        'expected_mappings': {
            0: 0,  # Robert Smith -> Bob S.
            1: 0,  # Bob Smith -> Bob S.
            2: 0,  # R. Smith -> Bob S.
        },
    },
    {
        'name': 'No duplicates',
        'extracted_nodes': [
            {'id': 0, 'name': 'Charlie Brown', 'entity_type': 'Person'},
            {'id': 1, 'name': 'Tesla Inc', 'entity_type': 'Organization'},
        ],
        'existing_nodes': [
            {'idx': 0, 'name': 'Bob Smith', 'entity_types': ['Person']},
            {'idx': 1, 'name': 'Microsoft', 'entity_types': ['Organization']},
        ],
        'expected_mappings': {
            0: -1,  # Charlie Brown is new
            1: -1,  # Tesla Inc is new
        },
    },
    {
        'name': 'Edge case - bounds validation',
        'extracted_nodes': [
            {'id': 0, 'name': 'Test Entity', 'entity_type': 'Test'},
            {'id': 1, 'name': 'Another Test', 'entity_type': 'Test'},
        ],
        'existing_nodes': [{'idx': 0, 'name': 'Existing Test', 'entity_types': ['Test']}],
        'expected_mappings': {
            0: 0,  # Test Entity -> Existing Test
            1: -1,  # Another Test is new
        },
    },
]

# JSON mode prompt - explicitly tells model to respond in JSON
JSON_MODE_PROMPT = """You are a deduplication assistant. Identify which extracted entities match existing ones.

Rules:
1. Entities are duplicates if they refer to the same real-world entity
2. Consider name variations (Bob/Robert), abbreviations (NYC/New York City)
3. Entity types should match (Person != Location)

IMPORTANT: You must respond with valid JSON only. No markdown, no explanation.

The response must follow this exact structure:
{
  "entity_resolutions": [
    {"id": 0, "duplicate_idx": -1, "name": "optional_name"},
    {"id": 1, "duplicate_idx": 0, "name": "optional_name"}
  ]
}

Constraints:
- id: must be between 0 and %d (number of extracted entities - 1)
- duplicate_idx: must be between -1 and %d (number of existing entities - 1)
- Use -1 for duplicate_idx when there's no match

Extracted entities:
%s

Existing entities:
%s

Respond with JSON:"""


async def test_json_mode(base_url: str, model: str):
    """Test Ollama with JSON mode (format: 'json')"""

    # For Ollama native API, use /api/generate
    if base_url.endswith('/v1'):
        base_url = base_url[:-3]  # Remove /v1

    results = []

    async with httpx.AsyncClient(timeout=30.0) as client:
        for test_case in TEST_CASES:
            print(f'\n{"=" * 60}')
            print(f'Test: {test_case["name"]}')
            print(f'{"=" * 60}')

            # Calculate bounds
            max_extracted_id = len(test_case['extracted_nodes']) - 1
            max_existing_idx = len(test_case['existing_nodes']) - 1

            # Format the prompt
            prompt = JSON_MODE_PROMPT % (
                max_extracted_id,
                max_existing_idx,
                json.dumps(test_case['extracted_nodes'], indent=2),
                json.dumps(test_case['existing_nodes'], indent=2),
            )

            # Use Ollama's generate endpoint with JSON mode
            request_body = {
                'model': model,
                'prompt': prompt,
                'format': 'json',  # This enables JSON mode
                'stream': False,
                'options': {
                    'temperature': 0.0,
                    'seed': 42,  # For reproducibility
                },
            }

            try:
                print(f'Testing with model: {model} (JSON mode)')
                response = await client.post(f'{base_url}/api/generate', json=request_body)
                response.raise_for_status()

                result = response.json()
                content = result.get('response', '')

                # Parse the JSON response
                try:
                    parsed_response = json.loads(content)
                    resolutions = parsed_response.get('entity_resolutions', [])

                    # Validate and check correctness
                    correct = 0
                    total = len(test_case['extracted_nodes'])
                    errors = []
                    bounds_errors = []

                    # Check bounds
                    for res in resolutions:
                        res_id = res.get('id', -999)
                        dup_idx = res.get('duplicate_idx', -999)

                        if res_id < 0 or res_id > max_extracted_id:
                            bounds_errors.append(
                                f'Invalid id={res_id} (must be 0-{max_extracted_id})'
                            )
                        if dup_idx < -1 or dup_idx > max_existing_idx:
                            bounds_errors.append(
                                f'Invalid duplicate_idx={dup_idx} (must be -1 to {max_existing_idx})'
                            )

                    # Check correctness
                    for expected_id, expected_dup in test_case['expected_mappings'].items():
                        found = False
                        for res in resolutions:
                            if res.get('id') == expected_id:
                                found = True
                                if res.get('duplicate_idx') == expected_dup:
                                    correct += 1
                                else:
                                    errors.append(
                                        f'Entity {expected_id}: expected duplicate_idx={expected_dup}, got {res.get("duplicate_idx")}'
                                    )
                                break

                        if not found:
                            errors.append(f'Entity {expected_id}: NOT FOUND in response')

                    # Print results
                    print(f'\nExtracted nodes:')
                    for node in test_case['extracted_nodes']:
                        print(f'  {node["id"]}: {node["name"]} ({node["entity_type"]})')

                    print(f'\nExisting nodes:')
                    for node in test_case['existing_nodes']:
                        print(
                            f'  {node["idx"]}: {node["name"]} ({", ".join(node["entity_types"])})'
                        )

                    print(f'\nLLM Response (JSON mode):')
                    for res in resolutions:
                        name_str = f" -> '{res.get('name')}'" if res.get('name') else ''
                        print(f'  Entity {res.get("id")} -> {res.get("duplicate_idx")}{name_str}')

                    if bounds_errors:
                        print(f'\n⚠️  BOUNDS ERRORS:')
                        for err in bounds_errors:
                            print(f'  - {err}')

                    print(f'\nScore: {correct}/{total} correct')
                    if errors:
                        print('Errors:')
                        for error in errors:
                            print(f'  - {error}')

                    results.append(
                        {
                            'test': test_case['name'],
                            'score': f'{correct}/{total}',
                            'percentage': (correct / total) * 100 if total > 0 else 0,
                            'has_bounds_errors': len(bounds_errors) > 0,
                            'bounds_errors': bounds_errors,
                            'errors': errors,
                            'mode': 'json',
                        }
                    )

                except json.JSONDecodeError as e:
                    print(f'Failed to parse JSON: {e}')
                    print(f'Raw response: {content[:500]}...')
                    results.append(
                        {
                            'test': test_case['name'],
                            'score': '0/0',
                            'percentage': 0,
                            'has_bounds_errors': False,
                            'bounds_errors': [],
                            'errors': [f'JSON parse error: {str(e)}'],
                            'mode': 'json',
                        }
                    )

            except Exception as e:
                print(f'Error calling Ollama: {e}')
                results.append(
                    {
                        'test': test_case['name'],
                        'score': '0/0',
                        'percentage': 0,
                        'has_bounds_errors': False,
                        'bounds_errors': [],
                        'errors': [str(e)],
                        'mode': 'json',
                    }
                )

    # Summary
    print(f'\n{"=" * 60}')
    print('SUMMARY - JSON Mode Test')
    print(f'{"=" * 60}')
    total_score = sum(r['percentage'] for r in results) / len(results) if results else 0
    bounds_errors = sum(1 for r in results if r['has_bounds_errors'])

    print(f'Model: {model}')
    print(f"Mode: JSON (format: 'json')")
    print(f'Overall accuracy: {total_score:.1f}%')
    print(f'Tests with bounds errors: {bounds_errors}/{len(results)}')
    print('\nPer-test results:')
    for r in results:
        bounds_indicator = ' ⚠️ BOUNDS ERROR' if r['has_bounds_errors'] else ''
        print(f'  - {r["test"]}: {r["score"]} ({r["percentage"]:.0f}%){bounds_indicator}')

    return results


async def compare_modes(base_url: str, model: str):
    """Compare JSON mode vs structured output for a model"""
    print(f'\n{"=" * 80}')
    print(f'COMPARING MODES FOR MODEL: {model}')
    print(f'{"=" * 80}')

    # Test JSON mode
    json_results = await test_json_mode(base_url, model)

    # Calculate averages
    json_avg = sum(r['percentage'] for r in json_results) / len(json_results) if json_results else 0
    json_bounds = sum(1 for r in json_results if r['has_bounds_errors'])

    print(f'\n{"=" * 80}')
    print('MODE COMPARISON SUMMARY')
    print(f'{"=" * 80}')
    print(f'Model: {model}')
    print(f"\nJSON Mode (format: 'json'):")
    print(f'  - Average accuracy: {json_avg:.1f}%')
    print(f'  - Bounds errors: {json_bounds}/{len(json_results)} tests')

    return {
        'model': model,
        'json_mode': {'accuracy': json_avg, 'bounds_errors': json_bounds, 'results': json_results},
    }


async def main():
    # Get configuration
    base_url = os.getenv('OLLAMA_BASE_URL', 'http://100.81.139.20:11434/v1')
    model = os.getenv('TEST_MODEL', 'qwen3-30b-a3b:iq4_nl')

    # Run comparison
    comparison = await compare_modes(base_url, model)

    # Save results
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'json_mode_results_{model.replace(":", "_")}_{timestamp}.json'
    with open(f'/opt/stacks/graphiti/llm_tests/{filename}', 'w') as f:
        json.dump(comparison, f, indent=2)
    print(f'\nResults saved to: {filename}')


if __name__ == '__main__':
    asyncio.run(main())
