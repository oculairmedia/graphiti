#!/usr/bin/env python3
"""
Test script to verify DSPy training data collection is working.

Usage:
    # Test locally (collection disabled by default)
    python scripts/test_training_collection.py

    # Test with collection enabled
    DSPY_COLLECT_TRAINING_DATA=true python scripts/test_training_collection.py

    # Check collection in running worker
    docker exec graphiti-graphiti-worker-1 python -c "
        from graphiti_core.dspy.modules import get_training_stats, is_training_collection_enabled
        print(f'Collection enabled: {is_training_collection_enabled()}')
        print(f'Stats: {get_training_stats()}')
    "
"""

import os
import sys
import json
import tempfile

sys.path.insert(0, '/opt/stacks/graphiti')


def test_collection_disabled():
    """Test that collection is disabled by default."""
    from graphiti_core.dspy import modules

    modules._training_collection_enabled = None
    modules._training_collector = None

    from graphiti_core.dspy.modules import (
        is_training_collection_enabled,
        get_training_stats,
        save_training_data,
    )

    assert not is_training_collection_enabled(), 'Collection should be disabled by default'
    assert get_training_stats() is None, 'Stats should be None when disabled'
    assert save_training_data() is None, 'Save should return None when disabled'
    print('✓ Collection correctly disabled by default')


def test_collection_enabled():
    """Test that collection works when enabled."""
    os.environ['DSPY_COLLECT_TRAINING_DATA'] = 'true'

    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ['DSPY_TRAINING_DATA_DIR'] = tmpdir

        from graphiti_core.dspy import modules

        modules._training_collection_enabled = None
        modules._training_collector = None

        from graphiti_core.dspy.modules import (
            is_training_collection_enabled,
            get_training_stats,
            save_training_data,
            _get_training_collector,
        )

        assert is_training_collection_enabled(), 'Collection should be enabled'

        collector = _get_training_collector()
        assert collector is not None, 'Collector should be initialized'

        stats = get_training_stats()
        assert stats is not None, 'Stats should not be None'
        assert stats['entity_extraction'] == 0, 'Should start with 0 examples'

        save_result = save_training_data()
        assert save_result is not None, 'Save should return stats'

        files = os.listdir(tmpdir)
        assert 'entity_extraction.json' in files, 'Should create entity_extraction.json'
        assert 'edge_extraction.json' in files, 'Should create edge_extraction.json'

        with open(os.path.join(tmpdir, 'entity_extraction.json')) as f:
            data = json.load(f)
            assert data['task_name'] == 'entity_extraction'
            assert 'examples' in data

        print('✓ Collection correctly enabled and working')
        print(f'  Files created: {files}')


def test_mock_extraction():
    """Test recording a mock extraction."""
    os.environ['DSPY_COLLECT_TRAINING_DATA'] = 'true'

    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ['DSPY_TRAINING_DATA_DIR'] = tmpdir

        from graphiti_core.dspy import modules

        modules._training_collection_enabled = None
        modules._training_collector = None
        modules._training_example_count = 0

        from graphiti_core.dspy.modules import (
            _get_training_collector,
            get_training_stats,
            save_training_data,
        )
        from graphiti_core.dspy.signatures import ExtractedEntities
        from graphiti_core.prompts.extract_nodes import ExtractedEntity

        collector = _get_training_collector()

        mock_result = ExtractedEntities(
            extracted_entities=[
                ExtractedEntity(name='Alice', entity_type_id=0),
                ExtractedEntity(name='Bob', entity_type_id=0),
            ]
        )

        collector.record_entity_extraction(
            current_message='Alice met Bob at the coffee shop.',
            entity_types=[{'name': 'Person', 'description': 'A human'}],
            result=mock_result,
            previous_messages=None,
        )

        stats = get_training_stats()
        assert stats['entity_extraction'] == 1, f'Should have 1 example, got {stats}'

        save_training_data()

        with open(os.path.join(tmpdir, 'entity_extraction.json')) as f:
            data = json.load(f)
            assert data['example_count'] == 1
            assert len(data['examples']) == 1
            example = data['examples'][0]
            assert 'Alice met Bob' in example['inputs']['current_message']

        print('✓ Mock extraction recorded correctly')
        print(f'  Example: {json.dumps(data["examples"][0]["inputs"], indent=2)[:200]}...')


def check_worker_status():
    """Check if the worker would collect data with current config."""
    print('\n--- Worker Configuration Check ---')

    env_value = os.environ.get('DSPY_COLLECT_TRAINING_DATA', 'false')
    print(f'DSPY_COLLECT_TRAINING_DATA={env_value}')

    if env_value.lower() == 'true':
        print('✓ Collection is ENABLED')
        data_dir = os.environ.get('DSPY_TRAINING_DATA_DIR', '/data/training_data')
        print(f'  Data directory: {data_dir}')
        if os.path.exists(data_dir):
            files = os.listdir(data_dir)
            print(f'  Existing files: {files}')
        else:
            print(f'  Directory does not exist yet (will be created)')
    else:
        print('○ Collection is DISABLED')
        print('  To enable: set DSPY_COLLECT_TRAINING_DATA=true in .env')


if __name__ == '__main__':
    print('=== DSPy Training Data Collection Tests ===\n')

    test_collection_disabled()

    os.environ.pop('DSPY_COLLECT_TRAINING_DATA', None)

    test_collection_enabled()

    os.environ.pop('DSPY_COLLECT_TRAINING_DATA', None)

    test_collection_enabled()
    test_mock_extraction()

    os.environ.pop('DSPY_COLLECT_TRAINING_DATA', None)

    check_worker_status()

    print('\n=== All Tests Passed ===')
