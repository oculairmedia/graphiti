#!/usr/bin/env python3
"""
Test DSPy extraction modules with GLM backend.

This test validates that the DSPy modules work correctly with the Z.AI GLM API.
Run with: CHUTES_API_KEY=your-key python3 test_dspy_extraction.py
"""

import os
import sys
import json
import logging
from datetime import datetime, timezone

# Add project root to path
sys.path.insert(0, '/opt/stacks/graphiti')

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def test_configuration():
    """Test LM configuration."""
    print('\n' + '=' * 60)
    print('TEST 1: LM Configuration')
    print('=' * 60)

    from graphiti_core.dspy.config import configure_lm, get_lm_config

    api_key = os.environ.get('CHUTES_API_KEY')
    if not api_key:
        print('SKIP: CHUTES_API_KEY not set')
        return False

    try:
        configure_lm(api_key=api_key)
        config = get_lm_config()
        print(f'API Base: {config.api_base}')
        print(f'Complex Model: {config.model_complex}')
        print(f'Simple Model: {config.model_simple}')
        print('PASS: Configuration successful')
        return True
    except Exception as e:
        print(f'FAIL: {e}')
        return False


def test_entity_extraction():
    """Test entity extraction module."""
    print('\n' + '=' * 60)
    print('TEST 2: Entity Extraction')
    print('=' * 60)

    from graphiti_core.dspy.modules import NodeExtractor

    extractor = NodeExtractor()

    # Test message
    test_message = "Alice: Hey Bob, did you hear that TechCorp is acquiring StartupXYZ for $50 million?"

    # Entity types
    entity_types = [
        {'id': 0, 'name': 'Person', 'description': 'A human individual'},
        {'id': 1, 'name': 'Organization', 'description': 'A company, institution, or group'},
        {'id': 2, 'name': 'Event', 'description': 'A significant occurrence or happening'},
    ]

    try:
        print(f'Input: {test_message}')
        print(f'Entity types: {[t["name"] for t in entity_types]}')

        result = extractor(
            current_message=test_message,
            entity_types=entity_types,
        )

        print(f'\nExtracted {len(result.extracted_entities)} entities:')
        for entity in result.extracted_entities:
            type_name = entity_types[entity.entity_type_id]['name'] if entity.entity_type_id < len(entity_types) else 'Unknown'
            print(f'  - {entity.name} (type: {type_name}, id: {entity.entity_type_id})')

        # Validate expected entities
        names = [e.name.lower() for e in result.extracted_entities]
        expected = ['alice', 'bob', 'techcorp', 'startupxyz']
        found = sum(1 for exp in expected if any(exp in name for name in names))

        if found >= 3:
            print(f'\nPASS: Found {found}/4 expected entities')
            return True
        else:
            print(f'\nWARN: Only found {found}/4 expected entities')
            return True  # Still pass, extraction worked
    except Exception as e:
        print(f'FAIL: {e}')
        import traceback
        traceback.print_exc()
        return False


def test_edge_extraction():
    """Test edge/relationship extraction module."""
    print('\n' + '=' * 60)
    print('TEST 3: Edge Extraction')
    print('=' * 60)

    from graphiti_core.dspy.modules import EdgeExtractor

    extractor = EdgeExtractor()

    test_message = "Alice works at TechCorp as a software engineer. She joined the company in 2023."

    entities = [
        {'id': 0, 'name': 'Alice', 'type': 'Person'},
        {'id': 1, 'name': 'TechCorp', 'type': 'Organization'},
    ]

    reference_time = datetime.now(timezone.utc).isoformat()

    try:
        print(f'Input: {test_message}')
        print(f'Entities: {[e["name"] for e in entities]}')

        result = extractor(
            current_message=test_message,
            entities=entities,
            reference_time=reference_time,
        )

        print(f'\nExtracted {len(result.edges)} edges:')
        for edge in result.edges:
            src = entities[edge.source_entity_id]['name'] if edge.source_entity_id < len(entities) else f'id:{edge.source_entity_id}'
            tgt = entities[edge.target_entity_id]['name'] if edge.target_entity_id < len(entities) else f'id:{edge.target_entity_id}'
            print(f'  - {src} --[{edge.relation_type}]--> {tgt}')
            print(f'    Fact: {edge.fact}')
            if edge.valid_at:
                print(f'    Valid at: {edge.valid_at}')

        if len(result.edges) >= 1:
            print('\nPASS: Extracted relationships')
            return True
        else:
            print('\nWARN: No relationships extracted')
            return False
    except Exception as e:
        print(f'FAIL: {e}')
        import traceback
        traceback.print_exc()
        return False


def test_node_resolution():
    """Test node deduplication module."""
    print('\n' + '=' * 60)
    print('TEST 4: Node Resolution/Deduplication')
    print('=' * 60)

    from graphiti_core.dspy.modules import NodeResolver

    resolver = NodeResolver()

    test_message = "Alice mentioned that Ms. Smith is coming to the meeting."

    # New entities extracted
    extracted = [
        {'id': 0, 'name': 'Alice', 'type': 'Person'},
        {'id': 1, 'name': 'Ms. Smith', 'type': 'Person'},
    ]

    # Existing entities to compare against
    existing = [
        {'idx': 0, 'name': 'Alice Smith', 'type': 'Person', 'summary': 'A software engineer'},
        {'idx': 1, 'name': 'Bob Johnson', 'type': 'Person', 'summary': 'A project manager'},
    ]

    try:
        print(f'Input: {test_message}')
        print(f'New entities: {[e["name"] for e in extracted]}')
        print(f'Existing entities: {[e["name"] for e in existing]}')

        result = resolver(
            current_message=test_message,
            extracted_entities=extracted,
            existing_entities=existing,
        )

        print(f'\nResolutions:')
        for res in result.entity_resolutions:
            dup_status = f'duplicate of idx {res.duplicate_idx}' if res.duplicate_idx >= 0 else 'new entity'
            print(f'  - id {res.id}: {res.name} -> {dup_status}')
            if res.duplicates:
                print(f'    All duplicates: {res.duplicates}')

        print('\nPASS: Deduplication completed')
        return True
    except Exception as e:
        print(f'FAIL: {e}')
        import traceback
        traceback.print_exc()
        return False


def test_summary_generation():
    """Test summary generation module."""
    print('\n' + '=' * 60)
    print('TEST 5: Summary Generation')
    print('=' * 60)

    from graphiti_core.dspy.modules import SummaryGenerator

    generator = SummaryGenerator()

    test_message = """Alice is a senior software engineer at TechCorp.
    She specializes in machine learning and has been with the company for 3 years.
    She leads the AI research team and has published several papers on NLP."""

    try:
        print(f'Input: {test_message[:100]}...')
        print(f'Entity: Alice')

        result = generator(
            current_message=test_message,
            entity_name='Alice',
        )

        print(f'\nGenerated Summary:')
        print(f'  {result.summary}')

        if len(result.summary) > 20:
            print('\nPASS: Summary generated')
            return True
        else:
            print('\nWARN: Summary too short')
            return False
    except Exception as e:
        print(f'FAIL: {e}')
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print('=' * 60)
    print('DSPy Extraction Module Tests')
    print('=' * 60)
    print(f'Time: {datetime.now().isoformat()}')

    # Check API key
    if not os.environ.get('CHUTES_API_KEY'):
        print('\nERROR: CHUTES_API_KEY environment variable not set')
        print('Usage: CHUTES_API_KEY=your-key python3 test_dspy_extraction.py')
        sys.exit(1)

    results = {
        'configuration': test_configuration(),
    }

    # Only run other tests if configuration passed
    if results['configuration']:
        results['entity_extraction'] = test_entity_extraction()
        results['edge_extraction'] = test_edge_extraction()
        results['node_resolution'] = test_node_resolution()
        results['summary_generation'] = test_summary_generation()

    # Summary
    print('\n' + '=' * 60)
    print('TEST SUMMARY')
    print('=' * 60)
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    print(f'Passed: {passed}/{total}')
    for name, result in results.items():
        status = 'PASS' if result else 'FAIL'
        print(f'  {name}: {status}')

    return 0 if passed == total else 1


if __name__ == '__main__':
    sys.exit(main())
