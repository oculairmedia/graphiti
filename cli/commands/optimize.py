#!/usr/bin/env python3
"""
CLI commands for MIPROv2 DSPy prompt optimization.

Provides command-line interface for running prompt optimization,
analyzing training data, and managing optimized prompts.
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import click

logger = logging.getLogger(__name__)


@click.group()
def optimize():
    """MIPROv2 DSPy prompt optimization commands"""
    pass


@optimize.command()
@click.option('--task', '-t', multiple=True, help='Tasks to optimize (can specify multiple)')
@click.option('--min-examples', type=int, default=50, help='Minimum examples required per task')
@click.option(
    '--num-candidates', type=int, default=7, help='Number of prompt candidates to generate'
)
@click.option('--num-threads', type=int, default=4, help='Number of threads for optimization')
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose logging')
def run(
    task: tuple[str, ...],
    min_examples: int,
    num_candidates: int,
    num_threads: int,
    verbose: bool,
):
    """Run MIPROv2 optimization on collected training data."""
    if verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    async def _run():
        from graphiti_core.dspy.training_storage import get_training_stats, get_training_examples

        click.echo('=' * 60)
        click.echo('MIPROv2 DSPy Prompt Optimization')
        click.echo('=' * 60)

        stats = await get_training_stats()
        click.echo(f'\nTraining data available:')
        for task_name, count in stats.items():
            status = '✓' if count >= min_examples else '✗'
            click.echo(f'  {status} {task_name}: {count} examples')

        tasks_to_optimize = (
            list(task)
            if task
            else [
                'entity_extraction',
                'edge_extraction',
                'node_resolution',
                'summary_generation',
            ]
        )

        eligible_tasks = [t for t in tasks_to_optimize if stats.get(t, 0) >= min_examples]

        if not eligible_tasks:
            click.echo(f'\n✗ No tasks have sufficient training data (min: {min_examples})')
            click.echo('  Run more ingestions to collect training examples.')
            return

        click.echo(f'\nOptimizing {len(eligible_tasks)} task(s): {", ".join(eligible_tasks)}')
        click.echo(f'  Candidates: {num_candidates}')
        click.echo(f'  Threads: {num_threads}')

        try:
            from graphiti_core.dspy.optimization import DSPyOptimizer

            optimizer = DSPyOptimizer(
                num_candidates=num_candidates,
                num_threads=num_threads,
            )

            results = {}
            for task_name in eligible_tasks:
                click.echo(f'\n[{task_name}] Starting optimization...')

                examples = await get_training_examples(task_name)
                click.echo(f'  Loaded {len(examples)} examples')

                try:
                    if task_name == 'entity_extraction':
                        result = optimizer.optimize_entity_extraction(min_examples=min_examples)
                    elif task_name == 'edge_extraction':
                        result = optimizer.optimize_edge_extraction(min_examples=min_examples)
                    elif task_name == 'node_resolution':
                        result = optimizer.optimize_node_resolution(min_examples=min_examples)
                    else:
                        click.echo(f'  Skipping unsupported task: {task_name}')
                        continue

                    if result:
                        results[task_name] = {'status': 'success'}
                        click.echo(f'  ✓ Optimization complete')
                    else:
                        results[task_name] = {'status': 'failed', 'reason': 'returned None'}
                        click.echo(f'  ✗ Optimization returned None')

                except Exception as e:
                    results[task_name] = {'status': 'error', 'error': str(e)}
                    click.echo(f'  ✗ Error: {e}')
                    if verbose:
                        import traceback

                        traceback.print_exc()

            click.echo('\n' + '=' * 60)
            click.echo('Results:')
            for task_name, result in results.items():
                status = result.get('status', 'unknown')
                if status == 'success':
                    click.echo(f'  ✓ {task_name}: SUCCESS')
                else:
                    click.echo(
                        f'  ✗ {task_name}: {status} - {result.get("error", result.get("reason", ""))}'
                    )

        except ImportError as e:
            click.echo(f'✗ Import error: {e}')
            click.echo('  Make sure graphiti_core is installed with DSPy support')

    asyncio.run(_run())


@optimize.command()
@click.option('--verbose', '-v', is_flag=True, help='Show detailed statistics')
def stats(verbose: bool):
    """Show training data statistics."""
    if verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.WARNING)

    async def _stats():
        from graphiti_core.dspy.training_storage import get_training_stats

        click.echo('Training Data Statistics')
        click.echo('=' * 40)

        stats = await get_training_stats()

        if not stats:
            click.echo('No training data found.')
            return

        total = sum(stats.values())
        click.echo(f'Total examples: {total}\n')

        for task, count in sorted(stats.items()):
            bar_len = min(count // 5, 40)
            bar = '█' * bar_len
            click.echo(f'{task:25s} {count:5d} {bar}')

    asyncio.run(_stats())


@optimize.command()
@click.option('--task', '-t', required=True, help='Task to sample from')
@click.option('--count', '-n', type=int, default=5, help='Number of examples to show')
def sample(task: str, count: int):
    """Show sample training examples for a task."""

    async def _sample():
        from graphiti_core.dspy.training_storage import sample_training_examples

        examples = await sample_training_examples(task, count)

        if not examples:
            click.echo(f'No training examples found for task: {task}')
            return

        click.echo(f"Sample {len(examples)} examples from '{task}':")
        click.echo('=' * 60)

        for i, ex in enumerate(examples, 1):
            click.echo(f'\n--- Example {i} ---')
            click.echo(f'Inputs: {ex.inputs}')
            click.echo(f'Output: {ex.output}')

    asyncio.run(_sample())


@optimize.command()
@click.option('--use-temporal', is_flag=True, help='Trigger via Temporal workflow')
@click.option('--force', is_flag=True, help='Force trigger even if threshold not met')
def trigger(use_temporal: bool, force: bool):
    """Manually trigger optimization (resets counter)."""

    async def _trigger():
        from graphiti_core.dspy.trigger import get_optimization_trigger

        trigger = get_optimization_trigger()
        status = await trigger.get_status()

        click.echo(f'Current count: {status["count"]}/{status["threshold"]}')
        click.echo(f'Last optimization: {status.get("last_optimization", "never")}')

        if not force and status['count'] < status['threshold']:
            click.echo(f'\n⚠ Threshold not met. Use --force to trigger anyway.')
            return

        click.echo('\nTriggering optimization...')

        if use_temporal:
            from graphiti_core.dspy.trigger import create_temporal_optimization_callback

            callback = await create_temporal_optimization_callback()
            await callback()
            click.echo('✓ Temporal workflow started')
        else:
            await trigger.trigger_optimization()
            click.echo('✓ Optimization triggered')

    asyncio.run(_trigger())


@optimize.command()
def status():
    """Show optimization trigger status."""

    async def _status():
        from graphiti_core.dspy.trigger import get_optimization_trigger

        trigger = get_optimization_trigger()
        status = await trigger.get_status()

        click.echo('Optimization Trigger Status')
        click.echo('=' * 40)
        click.echo(f'Count:          {status["count"]}')
        click.echo(f'Threshold:      {status["threshold"]}')
        click.echo(
            f'Progress:       {status["count"]}/{status["threshold"]} ({status["count"] / status["threshold"] * 100:.0f}%)'
        )
        click.echo(f'Last reset:     {status.get("last_reset", "unknown")}')
        click.echo(f'Last optimize:  {status.get("last_optimization", "never")}')

    asyncio.run(_status())


if __name__ == '__main__':
    optimize()
