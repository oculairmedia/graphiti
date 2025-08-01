#!/usr/bin/env python3
"""
Test script for node deduplication LLM task.
This tests the specific task of identifying duplicate entities between extracted and existing nodes.
"""

import asyncio
import json
import os
from datetime import datetime
from typing import Any, Dict, List

import httpx
from pydantic import BaseModel, Field


# The expected response model
class NodeResolutions(BaseModel):
    entity_resolutions: List[Dict[str, Any]] = Field(
        description='List of resolutions for each extracted entity'
    )


# Test cases for node deduplication
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
        'name': 'Edge case - similar but different types',
        'extracted_nodes': [
            {'id': 0, 'name': 'Washington', 'entity_type': 'Person'},
            {'id': 1, 'name': 'Washington', 'entity_type': 'Location'},
        ],
        'existing_nodes': [
            {'idx': 0, 'name': 'Washington', 'entity_types': ['Location']},
            {'idx': 1, 'name': 'George Washington', 'entity_types': ['Person']},
        ],
        'expected_mappings': {
            0: 1,  # Washington (Person) -> George Washington
            1: 0,  # Washington (Location) -> Washington (Location)
        },
    },
]

# The prompt template (simplified version of what Graphiti uses)
DEDUP_PROMPT = """You are a helpful assistant that identifies duplicate entities.

Given:
1. A list of newly extracted entities
2. A list of existing entities from the database

Your task is to identify which extracted entities are duplicates of existing ones.

Consider entities as duplicates if they refer to the same real-world entity, even with:
- Name variations (Bob vs Robert)
- Abbreviations (NYC vs New York City)
- Different formats (Microsoft Corp vs Microsoft Corporation)

Return a JSON object with an "entity_resolutions" array. For each extracted entity, specify:
- "id": the index of the extracted entity
- "duplicate_idx": the index of the existing entity it matches (-1 if no match)
- "name": the preferred name to use (optional)

Extracted entities:
{extracted_nodes}

Existing entities:
{existing_nodes}

Return only valid JSON matching this structure:
{{
  "entity_resolutions": [
    {{"id": 0, "duplicate_idx": -1 or valid_index, "name": "optional_preferred_name"}},
    ...
  ]
}}
"""


async def test_llm_deduplication(base_url: str, model: str, api_key: str = None):
    """Test LLM's ability to perform node deduplication"""

    headers = {'Content-Type': 'application/json'}
    if api_key:
        headers['Authorization'] = f'Bearer {api_key}'

    results = []

    async with httpx.AsyncClient(timeout=30.0) as client:
        for test_case in TEST_CASES:
            print(f'\n{"=" * 60}')
            print(f'Test: {test_case["name"]}')
            print(f'{"=" * 60}')

            # Format the prompt
            prompt = DEDUP_PROMPT.format(
                extracted_nodes=json.dumps(test_case['extracted_nodes'], indent=2),
                existing_nodes=json.dumps(test_case['existing_nodes'], indent=2),
            )

            # Call the LLM
            request_body = {
                'model': model,
                'messages': [{'role': 'user', 'content': prompt}],
                'temperature': 0.0,
                'response_format': {'type': 'json_object'} if 'gpt' in model else None,
            }

            # Remove None values
            request_body = {k: v for k, v in request_body.items() if v is not None}

            try:
                response = await client.post(
                    f'{base_url}/chat/completions', headers=headers, json=request_body
                )
                response.raise_for_status()

                result = response.json()
                content = result['choices'][0]['message']['content']

                # Parse the response
                try:
                    # Handle markdown code blocks
                    if content.startswith('```'):
                        # Extract JSON from markdown
                        lines = content.split('\n')
                        json_lines = []
                        in_json = False
                        for line in lines:
                            if line.strip() == '```json':
                                in_json = True
                            elif line.strip() == '```' and in_json:
                                break
                            elif in_json and line.strip() != '```json':
                                json_lines.append(line)
                        content = '\n'.join(json_lines)

                    parsed_response = json.loads(content)
                    resolutions = parsed_response.get('entity_resolutions', [])

                    # Check correctness
                    correct = 0
                    total = len(test_case['extracted_nodes'])
                    errors = []

                    for expected_id, expected_dup in test_case['expected_mappings'].items():
                        found = False
                        for res in resolutions:
                            if res.get('id') == expected_id:
                                found = True
                                actual_dup = res.get('duplicate_idx', -1)

                                # Check if the index is within bounds
                                if actual_dup >= len(test_case['existing_nodes']):
                                    errors.append(
                                        f'Entity {expected_id}: OUT OF BOUNDS! duplicate_idx={actual_dup} but only {len(test_case["existing_nodes"])} existing nodes'
                                    )
                                elif actual_dup < -1:
                                    errors.append(
                                        f'Entity {expected_id}: INVALID INDEX! duplicate_idx={actual_dup} (should be >= -1)'
                                    )
                                elif actual_dup == expected_dup:
                                    correct += 1
                                else:
                                    errors.append(
                                        f'Entity {expected_id}: expected duplicate_idx={expected_dup}, got {actual_dup}'
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

                    print(f'\nLLM Response:')
                    for res in resolutions:
                        print(
                            f'  Entity {res.get("id")} -> {res.get("duplicate_idx")} {res.get("name", "")}'
                        )

                    print(f'\nScore: {correct}/{total} correct')
                    if errors:
                        print('Errors:')
                        for error in errors:
                            print(f'  - {error}')

                    results.append(
                        {
                            'test': test_case['name'],
                            'score': f'{correct}/{total}',
                            'percentage': (correct / total) * 100,
                            'has_bounds_errors': any(
                                'OUT OF BOUNDS' in e or 'INVALID INDEX' in e for e in errors
                            ),
                            'errors': errors,
                        }
                    )

                except json.JSONDecodeError as e:
                    print(f'Failed to parse JSON response: {e}')
                    print(f'Raw response: {content}')
                    results.append(
                        {
                            'test': test_case['name'],
                            'score': '0/0',
                            'percentage': 0,
                            'has_bounds_errors': False,
                            'errors': ['Failed to parse JSON response'],
                        }
                    )

            except Exception as e:
                print(f'Error calling LLM: {e}')
                results.append(
                    {
                        'test': test_case['name'],
                        'score': '0/0',
                        'percentage': 0,
                        'has_bounds_errors': False,
                        'errors': [str(e)],
                    }
                )

    # Summary
    print(f'\n{"=" * 60}')
    print('SUMMARY')
    print(f'{"=" * 60}')
    total_score = sum(r['percentage'] for r in results) / len(results)
    bounds_errors = sum(1 for r in results if r['has_bounds_errors'])

    print(f'Overall accuracy: {total_score:.1f}%')
    print(f'Tests with bounds errors: {bounds_errors}/{len(results)}')
    print('\nPer-test results:')
    for r in results:
        bounds_indicator = ' ⚠️ BOUNDS ERROR' if r['has_bounds_errors'] else ''
        print(f'  - {r["test"]}: {r["score"]} ({r["percentage"]:.0f}%){bounds_indicator}')

    return results


async def main():
    # Get configuration from environment or use defaults
    base_url = os.getenv('OLLAMA_BASE_URL', 'http://100.81.139.20:11434/v1')
    model = os.getenv('TEST_MODEL', 'qwen3-30b-a3b:iq4_nl')
    api_key = os.getenv('OPENAI_API_KEY')

    print(f'Testing model: {model}')
    print(f'Base URL: {base_url}')

    results = await test_llm_deduplication(base_url, model, api_key)

    # Save results
    with open(
        f'dedup_test_results_{model.replace(":", "_")}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json',
        'w',
    ) as f:
        json.dump(results, f, indent=2)


if __name__ == '__main__':
    asyncio.run(main())
