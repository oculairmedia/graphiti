#!/usr/bin/env python3
"""
Test optimization trigger functionality.

Tests:
1. Counter persistence in FalkorDB
2. Threshold triggering
3. Training data check
4. Reset behavior
"""

import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_counter_persistence():
    """Test that counter persists in FalkorDB."""
    from graphiti_core.dspy.trigger import OptimizationTrigger, TriggerConfig

    config = TriggerConfig(threshold=10, min_training_examples=0, enabled=True)
    trigger = OptimizationTrigger(config=config)

    await trigger.reset_counter()

    initial_count = await trigger.get_count()
    assert initial_count == 0, f'Expected 0, got {initial_count}'

    await trigger.increment()
    await trigger.increment()
    await trigger.increment()

    count = await trigger.get_count()
    assert count == 3, f'Expected 3, got {count}'

    trigger2 = OptimizationTrigger(config=config)
    count2 = await trigger2.get_count()
    assert count2 == 3, f'New instance should see persisted count 3, got {count2}'

    logger.info('PASS: test_counter_persistence')


async def test_threshold_triggering():
    """Test that trigger fires at threshold."""
    from graphiti_core.dspy.trigger import OptimizationTrigger, TriggerConfig

    config = TriggerConfig(threshold=5, min_training_examples=0, enabled=True)
    trigger = OptimizationTrigger(config=config)

    await trigger.reset_counter()

    triggered_at = None
    for i in range(10):
        should_trigger = await trigger.increment()
        if should_trigger:
            triggered_at = i + 1
            break

    assert triggered_at == 5, f'Expected trigger at 5, triggered at {triggered_at}'

    logger.info('PASS: test_threshold_triggering')


async def test_trigger_callback():
    """Test that callback is invoked on trigger."""
    from graphiti_core.dspy.trigger import OptimizationTrigger, TriggerConfig

    callback_called = False

    async def on_trigger():
        nonlocal callback_called
        callback_called = True

    config = TriggerConfig(threshold=3, min_training_examples=0, enabled=True)
    trigger = OptimizationTrigger(config=config, on_trigger=on_trigger)

    await trigger.reset_counter()

    for _ in range(3):
        should_trigger = await trigger.increment()
        if should_trigger:
            await trigger.trigger_optimization()

    assert callback_called, 'Callback should have been called'

    count_after = await trigger.get_count()
    assert count_after == 0, f'Counter should reset after trigger, got {count_after}'

    logger.info('PASS: test_trigger_callback')


async def test_disabled_trigger():
    """Test that disabled trigger doesn't fire."""
    from graphiti_core.dspy.trigger import OptimizationTrigger, TriggerConfig

    config = TriggerConfig(threshold=2, min_training_examples=0, enabled=False)
    trigger = OptimizationTrigger(config=config)

    await trigger.reset_counter()

    for _ in range(5):
        should_trigger = await trigger.increment()
        assert not should_trigger, 'Disabled trigger should never fire'

    logger.info('PASS: test_disabled_trigger')


async def test_status_endpoint():
    """Test the status method."""
    from graphiti_core.dspy.trigger import OptimizationTrigger, TriggerConfig

    config = TriggerConfig(threshold=100, min_training_examples=50, enabled=True)
    trigger = OptimizationTrigger(config=config)

    await trigger.reset_counter()
    await trigger.increment()
    await trigger.increment()

    status = await trigger.get_status()

    assert status['count'] == 2
    assert status['threshold'] == 100
    assert status['enabled'] == True
    assert status['min_training_examples'] == 50
    assert status['last_reset'] is not None

    logger.info(f'Status: {status}')
    logger.info('PASS: test_status_endpoint')


async def test_env_config():
    """Test configuration from environment variables."""
    os.environ['DSPY_OPTIMIZATION_THRESHOLD'] = '200'
    os.environ['DSPY_OPTIMIZATION_MIN_EXAMPLES'] = '75'
    os.environ['DSPY_OPTIMIZATION_ENABLED'] = 'true'

    from graphiti_core.dspy.trigger import TriggerConfig

    config = TriggerConfig.from_env()

    assert config.threshold == 200
    assert config.min_training_examples == 75
    assert config.enabled == True

    os.environ.pop('DSPY_OPTIMIZATION_THRESHOLD', None)
    os.environ.pop('DSPY_OPTIMIZATION_MIN_EXAMPLES', None)
    os.environ.pop('DSPY_OPTIMIZATION_ENABLED', None)

    logger.info('PASS: test_env_config')


async def main():
    logger.info('Starting optimization trigger tests...')
    logger.info('=' * 60)

    await test_counter_persistence()
    logger.info('-' * 60)

    await test_threshold_triggering()
    logger.info('-' * 60)

    await test_trigger_callback()
    logger.info('-' * 60)

    await test_disabled_trigger()
    logger.info('-' * 60)

    await test_status_endpoint()
    logger.info('-' * 60)

    await test_env_config()
    logger.info('=' * 60)

    logger.info('All tests passed!')


if __name__ == '__main__':
    asyncio.run(main())
