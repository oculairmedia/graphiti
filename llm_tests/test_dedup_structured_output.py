#!/usr/bin/env python3
"""
Test node deduplication using Ollama's structured output format.
This ensures the model returns valid JSON with correct structure and indices.
"""

import asyncio
import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
from pydantic import BaseModel, Field


# Define the structured output schema using Pydantic
class EntityResolution(BaseModel):
    id: int = Field(description='Index of the extracted entity (must be 0 or greater)')
    duplicate_idx: int = Field(description='Index of matching existing entity, or -1 if no match')
    name: Optional[str] = Field(default=None, description='Preferred name to use (optional)')


class NodeResolutions(BaseModel):
    entity_resolutions: List[EntityResolution] = Field(
        description='List of resolutions for each extracted entity'
    )


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
        'name': 'Edge case - out of bounds test',
        'extracted_nodes': [
            {'id': 0, 'name': 'Entity Zero', 'entity_type': 'Test'},
            {'id': 1, 'name': 'Entity One', 'entity_type': 'Test'},
            {'id': 2, 'name': 'Entity Two', 'entity_type': 'Test'},
        ],
        'existing_nodes': [{'idx': 0, 'name': 'Existing Zero', 'entity_types': ['Test']}],
        'expected_mappings': {
            0: 0,  # Entity Zero -> Existing Zero
            1: -1,  # Entity One is new
            2: -1,  # Entity Two is new
        },
    },
]

# Simplified prompt for structured output
STRUCTURED_PROMPT = """You are a deduplication assistant. Identify which extracted entities match existing ones.

Consider entities duplicates if they refer to the same real-world entity (e.g., "Bob" and "Robert", "NYC" and "New York City").

Important constraints:
- The 'id' field must be between 0 and {max_extracted_id} (inclusive)
- The 'duplicate_idx' field must be between -1 and {max_existing_idx} (inclusive)
- Use -1 for duplicate_idx when there's no match

Extracted entities (new):
{extracted_nodes}

Existing entities (database):
{existing_nodes}

Return structured output identifying duplicates."""


async def test_ollama_structured(base_url: str, model: str):
    """Test Ollama with structured output format"""

    results = []

    async with httpx.AsyncClient(timeout=30.0) as client:
        for test_case in TEST_CASES:
            print(f'\n{"=" * 60}')
            print(f'Test: {test_case["name"]}')
            print(f'{"=" * 60}')

            # Calculate bounds for validation
            max_extracted_id = len(test_case['extracted_nodes']) - 1
            max_existing_idx = len(test_case['existing_nodes']) - 1

            # Format the prompt
            prompt = STRUCTURED_PROMPT.format(
                max_extracted_id=max_extracted_id,
                max_existing_idx=max_existing_idx,
                extracted_nodes=json.dumps(test_case['extracted_nodes'], indent=2),
                existing_nodes=json.dumps(test_case['existing_nodes'], indent=2),
            )

            # Use Ollama's structured output format
            request_body = {
                'model': model,
                'messages': [{'role': 'user', 'content': prompt}],
                'temperature': 0.0,
                'stream': False,
                'format': NodeResolutions.model_json_schema(),  # Pass Pydantic schema
            }

            try:
                print(f'Testing with model: {model}')
                response = await client.post(f'{base_url}/api/chat', json=request_body)
                response.raise_for_status()

                result = response.json()
                content = result['message']['content']

                # Parse using Pydantic
                try:
                    resolutions = NodeResolutions.model_validate_json(content)

                    # Check correctness
                    correct = 0
                    total = len(test_case['extracted_nodes'])
                    errors = []
                    bounds_errors = []

                    # First check for bounds errors
                    for res in resolutions.entity_resolutions:
                        if res.id < 0 or res.id > max_extracted_id:
                            bounds_errors.append(
                                f'Invalid id={res.id} (must be 0-{max_extracted_id})'
                            )
                        if res.duplicate_idx < -1 or res.duplicate_idx > max_existing_idx:
                            bounds_errors.append(
                                f'Invalid duplicate_idx={res.duplicate_idx} (must be -1 to {max_existing_idx})'
                            )

                    # Then check correctness
                    for expected_id, expected_dup in test_case['expected_mappings'].items():
                        found = False
                        for res in resolutions.entity_resolutions:
                            if res.id == expected_id:
                                found = True
                                if res.duplicate_idx == expected_dup:
                                    correct += 1
                                else:
                                    errors.append(
                                        f'Entity {expected_id}: expected duplicate_idx={expected_dup}, got {res.duplicate_idx}'
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

                    print(f'\nLLM Response (structured):')
                    for res in resolutions.entity_resolutions:
                        name_str = f" -> '{res.name}'" if res.name else ''
                        print(f'  Entity {res.id} -> {res.duplicate_idx}{name_str}')

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
                        }
                    )

                except Exception as e:
                    print(f'Pydantic validation error: {e}')
                    print(f'Raw response: {content}')
                    results.append(
                        {
                            'test': test_case['name'],
                            'score': '0/0',
                            'percentage': 0,
                            'has_bounds_errors': False,
                            'bounds_errors': [],
                            'errors': [f'Validation error: {str(e)}'],
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
                    }
                )

    # Summary
    print(f'\n{"=" * 60}')
    print('SUMMARY - Structured Output Test')
    print(f'{"=" * 60}')
    total_score = sum(r['percentage'] for r in results) / len(results) if results else 0
    bounds_errors = sum(1 for r in results if r['has_bounds_errors'])

    print(f'Model: {model}')
    print(f'Overall accuracy: {total_score:.1f}%')
    print(f'Tests with bounds errors: {bounds_errors}/{len(results)}')
    print('\nPer-test results:')
    for r in results:
        bounds_indicator = ' ⚠️ BOUNDS ERROR' if r['has_bounds_errors'] else ''
        print(f'  - {r["test"]}: {r["score"]} ({r["percentage"]:.0f}%){bounds_indicator}')

    return results


async def main():
    # Get configuration
    base_url = os.getenv('OLLAMA_BASE_URL', 'http://100.81.139.20:11434/v1')
    # Remove /v1 for Ollama native endpoint
    if base_url.endswith('/v1'):
        base_url = base_url[:-3]

    model = os.getenv('TEST_MODEL', 'qwen3-30b-a3b:iq4_nl')

    print(f'Testing structured output with model: {model}')
    print(f'Base URL: {base_url}')

    results = await test_ollama_structured(base_url, model)

    # Save results
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'structured_dedup_results_{model.replace(":", "_")}_{timestamp}.json'
    with open(filename, 'w') as f:
        json.dump(
            {
                'model': model,
                'test_type': 'structured_output',
                'timestamp': timestamp,
                'results': results,
            },
            f,
            indent=2,
        )
    print(f'\nResults saved to: {filename}')


if __name__ == '__main__':
    asyncio.run(main())
