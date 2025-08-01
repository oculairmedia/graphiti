#!/usr/bin/env python3
"""
Test Universal-NER model for entity extraction.
Universal-NER uses a specific prompt format where you specify the entity type at the end.
"""

import asyncio
import json
import os
import time
from datetime import datetime
from typing import Any, Dict, List

import httpx

# Test cases
TEST_CASES = [
    {
        'name': 'Simple conversation',
        'text': 'Bob Smith met with Alice Johnson at Microsoft headquarters in Seattle last Tuesday to discuss the new AI project.',
        'expected_entities': {
            'Person': ['Bob Smith', 'Alice Johnson'],
            'Organization': ['Microsoft'],
            'Location': ['Seattle'],
            'Time': ['last Tuesday'],
        },
    },
    {
        'name': 'Technical discussion',
        'text': 'Dr. Chen from Stanford University published a paper on quantum computing with IBM Research in Nature journal, achieving 99.9% fidelity.',
        'expected_entities': {
            'Person': ['Dr. Chen'],
            'Organization': ['Stanford University', 'IBM Research', 'Nature'],
            'Metric': ['99.9% fidelity'],
        },
    },
    {
        'name': 'Business context',
        'text': 'CEO Sarah Williams announced that TechCorp acquired DataSystems for $2.5 billion, expanding their presence in New York and London markets.',
        'expected_entities': {
            'Person': ['Sarah Williams'],
            'Title': ['CEO'],
            'Organization': ['TechCorp', 'DataSystems'],
            'Money': ['$2.5 billion'],
            'Location': ['New York', 'London'],
        },
    },
]

# Entity types to extract
ENTITY_TYPES = ['Person', 'Organization', 'Location', 'Time', 'Money', 'Title']


async def extract_with_universal_ner(base_url: str, text: str, entity_type: str):
    """Extract specific entity type using Universal-NER format"""

    # Universal-NER format: "Text. Entity_Type"
    prompt = f'{text} {entity_type}'

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f'{base_url}/api/generate',
            json={
                'model': 'zeffmuks/universal-ner',
                'prompt': prompt,
                'stream': False,
                'options': {'temperature': 0.0},
            },
        )

        result = response.json()
        raw_output = result.get('response', '')

        # Parse the output - Universal-NER returns entities in brackets
        # Example: ["Bob Smith", "Alice Johnson"]
        try:
            # Clean up the output
            raw_output = raw_output.strip()
            if raw_output.startswith('[') and raw_output.endswith(']'):
                entities = json.loads(raw_output)
                return entities
            else:
                # Try to extract entities from other formats
                import re

                # Match patterns like ["entity1", "entity2"]
                match = re.search(r'\[.*?\]', raw_output)
                if match:
                    return json.loads(match.group())
                return []
        except:
            return []


async def test_universal_ner(base_url: str):
    """Test Universal-NER on all test cases"""

    print('Testing zeffmuks/universal-ner for entity extraction...')
    print('=' * 80)

    all_results = []

    for test_case in TEST_CASES:
        print(f'\nTest: {test_case["name"]}')
        print(f'Text: {test_case["text"][:100]}...')

        start_time = time.time()
        extracted_all = {}

        # Extract each entity type separately (Universal-NER requirement)
        for entity_type in ENTITY_TYPES:
            type_start = time.time()
            entities = await extract_with_universal_ner(base_url, test_case['text'], entity_type)
            type_time = time.time() - type_start

            if entities:
                extracted_all[entity_type] = entities
                print(f'  {entity_type}: {entities} ({type_time:.3f}s)')

        total_time = time.time() - start_time

        # Calculate metrics
        metrics = calculate_metrics(extracted_all, test_case['expected_entities'])

        # Print results
        print(f'\nMetrics:')
        print(f'  Precision: {metrics["precision"]:.2%}')
        print(f'  Recall: {metrics["recall"]:.2%}')
        print(f'  F1 Score: {metrics["f1_score"]:.2%}')
        print(f'  Total extraction time: {total_time:.3f}s')

        all_results.append(
            {
                'test': test_case['name'],
                'extracted': extracted_all,
                'expected': test_case['expected_entities'],
                'metrics': metrics,
                'time': total_time,
            }
        )

    # Summary
    print(f'\n{"=" * 80}')
    print('SUMMARY - Universal-NER')
    print(f'{"=" * 80}')

    avg_precision = sum(r['metrics']['precision'] for r in all_results) / len(all_results)
    avg_recall = sum(r['metrics']['recall'] for r in all_results) / len(all_results)
    avg_f1 = sum(r['metrics']['f1_score'] for r in all_results) / len(all_results)
    avg_time = sum(r['time'] for r in all_results) / len(all_results)

    print(f'Average Precision: {avg_precision:.2%}')
    print(f'Average Recall: {avg_recall:.2%}')
    print(f'Average F1 Score: {avg_f1:.2%}')
    print(f'Average Time per document: {avg_time:.3f}s')

    return all_results


def calculate_metrics(extracted: Dict[str, List[str]], expected: Dict[str, List[str]]):
    """Calculate precision, recall, and F1 score"""

    # Flatten and normalize all entities
    extracted_all = set()
    expected_all = set()

    for category, entities in extracted.items():
        extracted_all.update(e.lower().strip() for e in entities)

    for category, entities in expected.items():
        expected_all.update(e.lower().strip() for e in entities)

    # Calculate metrics
    true_positives = len(extracted_all & expected_all)
    false_positives = len(extracted_all - expected_all)
    false_negatives = len(expected_all - extracted_all)

    precision = (
        true_positives / (true_positives + false_positives)
        if (true_positives + false_positives) > 0
        else 0
    )
    recall = (
        true_positives / (true_positives + false_negatives)
        if (true_positives + false_negatives) > 0
        else 0
    )
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0

    return {
        'precision': precision,
        'recall': recall,
        'f1_score': f1,
        'true_positives': true_positives,
        'false_positives': false_positives,
        'false_negatives': false_negatives,
    }


async def compare_with_qwen():
    """Quick comparison with current model"""
    base_url = os.getenv('OLLAMA_BASE_URL', 'http://100.81.139.20:11434')
    if base_url.endswith('/v1'):
        base_url = base_url[:-3]

    # Test one example with both models
    test_text = 'Bob Smith met with Alice Johnson at Microsoft headquarters in Seattle.'

    print('\n' + '=' * 80)
    print('QUICK COMPARISON')
    print('=' * 80)

    # Universal-NER
    print('\nUniversal-NER:')
    start = time.time()
    people = await extract_with_universal_ner(base_url, test_text, 'Person')
    orgs = await extract_with_universal_ner(base_url, test_text, 'Organization')
    locs = await extract_with_universal_ner(base_url, test_text, 'Location')
    universal_time = time.time() - start
    print(f'  People: {people}')
    print(f'  Organizations: {orgs}')
    print(f'  Locations: {locs}')
    print(f'  Time: {universal_time:.3f}s')

    # Current model (qwen3)
    print('\nCurrent model (qwen3-30b):')
    start = time.time()
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f'{base_url}/api/chat',
            json={
                'model': 'qwen3-30b-a3b:iq4_nl',
                'messages': [
                    {
                        'role': 'user',
                        'content': f'Extract all entities from: {test_text}\nReturn JSON with Person, Organization, Location arrays.',
                    }
                ],
                'stream': False,
                'format': 'json',
            },
        )
        qwen_time = time.time() - start
        result = json.loads(response.json()['message']['content'])
        print(f'  All entities: {result}')
        print(f'  Time: {qwen_time:.3f}s')

    print(
        f'\nSpeed improvement: {qwen_time / universal_time:.1f}x faster'
        if universal_time > 0
        else 'N/A'
    )


async def main():
    base_url = os.getenv('OLLAMA_BASE_URL', 'http://100.81.139.20:11434')
    if base_url.endswith('/v1'):
        base_url = base_url[:-3]

    # Full test
    results = await test_universal_ner(base_url)

    # Quick comparison
    await compare_with_qwen()

    # Save results
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    with open(f'universal_ner_results_{timestamp}.json', 'w') as f:
        json.dump(results, f, indent=2)


if __name__ == '__main__':
    asyncio.run(main())
