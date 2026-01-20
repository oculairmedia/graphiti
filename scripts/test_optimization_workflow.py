#!/usr/bin/env python3
"""
Integration tests for the DSPy MIPROv2 Optimization Workflow.

Tests the workflow components without actually running MIPROv2
(which would require significant compute resources).
"""

import asyncio
import json
import logging
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_training_data_loading():
    """Test loading and splitting training data."""
    from graphiti_core.dspy.optimization_workflow import load_and_split_training_data

    with tempfile.TemporaryDirectory() as tmpdir:
        test_data = {
            'task_name': 'entity_extraction',
            'created_at': '2026-01-20T00:00:00Z',
            'example_count': 100,
            'examples': [
                {
                    'inputs': {'current_message': f'Message {i}', 'entity_types': '[]'},
                    'expected_output': {'extracted_entities': {'extracted_entities': []}},
                    'metadata': {},
                }
                for i in range(100)
            ],
        }

        path = Path(tmpdir) / 'entity_extraction.json'
        with open(path, 'w') as f:
            json.dump(test_data, f)

        result = load_and_split_training_data(
            training_data_dir=tmpdir,
            task='entity_extraction',
            min_examples=50,
            train_split=0.8,
        )

        assert result is not None
        assert result.task == 'entity_extraction'
        assert result.total_examples == 100
        assert len(result.train_examples) == 80
        assert len(result.val_examples) == 20

    logger.info('PASS: test_training_data_loading')


def test_training_data_insufficient():
    """Test that insufficient data returns None."""
    from graphiti_core.dspy.optimization_workflow import load_and_split_training_data

    with tempfile.TemporaryDirectory() as tmpdir:
        test_data = {
            'task_name': 'entity_extraction',
            'created_at': '2026-01-20T00:00:00Z',
            'example_count': 10,
            'examples': [
                {
                    'inputs': {'current_message': f'Message {i}', 'entity_types': '[]'},
                    'expected_output': {'extracted_entities': {}},
                    'metadata': {},
                }
                for i in range(10)
            ],
        }

        path = Path(tmpdir) / 'entity_extraction.json'
        with open(path, 'w') as f:
            json.dump(test_data, f)

        result = load_and_split_training_data(
            training_data_dir=tmpdir,
            task='entity_extraction',
            min_examples=50,
            train_split=0.8,
        )

        assert result is None

    logger.info('PASS: test_training_data_insufficient')


def test_training_data_missing():
    """Test that missing file returns None."""
    from graphiti_core.dspy.optimization_workflow import load_and_split_training_data

    with tempfile.TemporaryDirectory() as tmpdir:
        result = load_and_split_training_data(
            training_data_dir=tmpdir,
            task='nonexistent_task',
            min_examples=50,
            train_split=0.8,
        )

        assert result is None

    logger.info('PASS: test_training_data_missing')


def test_optimization_config():
    """Test OptimizationConfig dataclass."""
    from graphiti_core.dspy.optimization_workflow import OptimizationConfig

    config = OptimizationConfig()
    assert config.training_data_dir == '/data/training_data'
    assert config.min_examples_per_task == 50
    assert config.train_split == 0.8
    assert config.num_candidates == 7
    assert len(config.tasks) == 4

    custom_config = OptimizationConfig(
        training_data_dir='/custom/path',
        min_examples_per_task=100,
        num_candidates=5,
    )
    assert custom_config.training_data_dir == '/custom/path'
    assert custom_config.min_examples_per_task == 100
    assert custom_config.num_candidates == 5

    logger.info('PASS: test_optimization_config')


async def test_store_candidate():
    """Test storing a candidate in PromptRegistry."""
    from graphiti_core.dspy.optimization_workflow import store_candidate
    from graphiti_core.prompts.registry import PromptTask, get_prompt_registry

    registry = get_prompt_registry()

    live_prompt = await registry.get_live_prompt(PromptTask.ENTITY_EXTRACTION)
    if live_prompt is None:
        logger.warning('No live prompt found, skipping store_candidate test')
        logger.info('SKIP: test_store_candidate (no live prompt)')
        return

    candidate_id, version = await store_candidate(
        task='entity_extraction',
        docstring='Test optimized instructions',
        demos=[{'inputs': {'test': 'data'}, 'outputs': {'result': 'value'}}],
        val_score=0.85,
        training_examples=100,
    )

    assert candidate_id is not None
    assert isinstance(version, int)
    assert version > live_prompt.version

    logger.info(f'PASS: test_store_candidate (created v{version})')


def test_workflow_dataclasses():
    """Test workflow input/output dataclasses."""
    from graphiti_core.dspy.optimization_workflow import (
        OptimizationTaskResult,
        OptimizationWorkflowResult,
        TrainingDataSplit,
    )

    split = TrainingDataSplit(
        task='entity_extraction',
        train_examples=[{'input': 1}],
        val_examples=[{'input': 2}],
        total_examples=2,
    )
    assert split.task == 'entity_extraction'
    assert split.total_examples == 2

    result = OptimizationTaskResult(
        task='entity_extraction',
        success=True,
        val_score=0.9,
        docstring='test',
        demos=[],
        duration_ms=1000,
    )
    assert result.success
    assert result.val_score == 0.9

    workflow_result = OptimizationWorkflowResult(
        success=True,
        tasks_optimized=4,
        tasks_failed=0,
        results=[result],
        total_duration_ms=5000,
    )
    assert workflow_result.tasks_optimized == 4

    logger.info('PASS: test_workflow_dataclasses')


async def test_trigger_callback_creation():
    """Test creating the Temporal workflow trigger callback."""
    from graphiti_core.dspy.trigger import create_temporal_optimization_callback

    os.environ['TEMPORAL_VISIBILITY_ADDRESS'] = 'localhost:7233'
    os.environ['TEMPORAL_VISIBILITY_NAMESPACE'] = 'test'
    os.environ['TEMPORAL_OPTIMIZATION_TASK_QUEUE'] = 'test-queue'

    callback = await create_temporal_optimization_callback()

    assert callback is not None
    assert asyncio.iscoroutinefunction(callback)

    logger.info('PASS: test_trigger_callback_creation')


async def test_activities_class():
    """Test OptimizationActivities class instantiation."""
    from graphiti_core.dspy.optimization_workflow import OptimizationActivities

    activities = OptimizationActivities()

    assert hasattr(activities, 'load_training_data')
    assert hasattr(activities, 'optimize_task')
    assert hasattr(activities, 'store_optimized_candidate')

    logger.info('PASS: test_activities_class')


async def run_async_tests():
    """Run async tests."""
    await test_store_candidate()
    await test_trigger_callback_creation()
    await test_activities_class()


def main():
    logger.info('Starting optimization workflow tests...')
    logger.info('=' * 60)

    test_training_data_loading()
    logger.info('-' * 60)

    test_training_data_insufficient()
    logger.info('-' * 60)

    test_training_data_missing()
    logger.info('-' * 60)

    test_optimization_config()
    logger.info('-' * 60)

    test_workflow_dataclasses()
    logger.info('-' * 60)

    asyncio.run(run_async_tests())

    logger.info('=' * 60)
    logger.info('All tests passed!')


if __name__ == '__main__':
    main()
