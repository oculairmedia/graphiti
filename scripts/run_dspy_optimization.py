#!/usr/bin/env python3
"""
Scheduled MIPROv2 Optimization Script for DSPy Pipeline.

This script runs as a scheduled job (cron, systemd timer, etc.) to:
1. Read production logs from ResponseLogger
2. Export high-quality examples to training data format
3. Run MIPROv2 optimization if sufficient examples exist
4. Save optimized modules for hot-reload

Usage:
    # Run full optimization
    python scripts/run_dspy_optimization.py

    # Dry run (analyze logs without optimization)
    python scripts/run_dspy_optimization.py --dry-run

    # Optimize specific stage only
    python scripts/run_dspy_optimization.py --stage extraction

    # Set minimum example threshold
    python scripts/run_dspy_optimization.py --min-examples 100

Environment Variables:
    DSPY_LOG_DIR: Directory containing log files (default: dspy_logs)
    DSPY_TRAINING_DIR: Directory for training data (default: training_data)
    DSPY_OPTIMIZED_DIR: Directory for optimized modules (default: optimized_modules)
    OPENAI_API_KEY: Required for MIPROv2 optimization
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from graphiti_core.dspy.response_logger import ResponseLogger, ResponseLoggerConfig
from graphiti_core.dspy.optimization import (
    DSPyOptimizer,
    entity_extraction_metric,
    edge_extraction_metric,
    node_resolution_metric,
    summary_metric,
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)


# =============================================================================
# Configuration
# =============================================================================

STAGES = ['extraction', 'resolution', 'edges', 'summary']

STAGE_METRICS = {
    'extraction': entity_extraction_metric,
    'edge_extraction': edge_extraction_metric,
    'resolution': node_resolution_metric,
    'summary': summary_metric,
}


def get_config():
    """Get configuration from environment."""
    return {
        'log_dir': os.environ.get('DSPY_LOG_DIR', 'dspy_logs'),
        'training_dir': os.environ.get('DSPY_TRAINING_DIR', 'training_data'),
        'optimized_dir': os.environ.get('DSPY_OPTIMIZED_DIR', 'optimized_modules'),
        'min_quality': float(os.environ.get('DSPY_LOG_MIN_QUALITY', '0.6')),
        'min_examples': int(os.environ.get('DSPY_MIN_EXAMPLES', '50')),
        'num_candidates': int(os.environ.get('MIPRO_NUM_CANDIDATES', '10')),
        'num_threads': int(os.environ.get('MIPRO_NUM_THREADS', '4')),
    }


# =============================================================================
# Log Analysis
# =============================================================================

def analyze_logs(log_dir: str, min_quality: float) -> dict:
    """
    Analyze logs and return statistics.

    Returns:
        Dict with counts and quality distributions per stage.
    """
    config = ResponseLoggerConfig(log_dir=log_dir, min_quality_score=min_quality)
    response_logger = ResponseLogger(config)

    stats = {}

    for stage in STAGES:
        entries = response_logger.read_logs(stage, min_quality=0.0)  # Get all entries

        if not entries:
            stats[stage] = {
                'total': 0,
                'above_threshold': 0,
                'quality_distribution': {},
                'recent_24h': 0,
            }
            continue

        # Count by quality threshold
        above_threshold = sum(1 for e in entries if e.quality_score >= min_quality)

        # Quality distribution
        quality_buckets = {'0.0-0.3': 0, '0.3-0.5': 0, '0.5-0.7': 0, '0.7-0.9': 0, '0.9-1.0': 0}
        for e in entries:
            q = e.quality_score
            if q < 0.3:
                quality_buckets['0.0-0.3'] += 1
            elif q < 0.5:
                quality_buckets['0.3-0.5'] += 1
            elif q < 0.7:
                quality_buckets['0.5-0.7'] += 1
            elif q < 0.9:
                quality_buckets['0.7-0.9'] += 1
            else:
                quality_buckets['0.9-1.0'] += 1

        # Recent entries (last 24h)
        cutoff = datetime.now(timezone.utc).timestamp() - 86400
        recent = sum(
            1 for e in entries
            if datetime.fromisoformat(e.timestamp.replace('Z', '+00:00')).timestamp() > cutoff
        )

        stats[stage] = {
            'total': len(entries),
            'above_threshold': above_threshold,
            'quality_distribution': quality_buckets,
            'recent_24h': recent,
        }

    return stats


def print_analysis(stats: dict, min_quality: float):
    """Print log analysis in a readable format."""
    print('\n' + '=' * 60)
    print('DSPy Response Log Analysis')
    print('=' * 60)
    print(f'Minimum quality threshold: {min_quality}')
    print()

    for stage, data in stats.items():
        print(f'\n{stage.upper()}:')
        print(f'  Total entries: {data["total"]}')
        print(f'  Above threshold: {data["above_threshold"]}')
        print(f'  Recent (24h): {data["recent_24h"]}')

        if data['total'] > 0:
            print('  Quality distribution:')
            for bucket, count in data['quality_distribution'].items():
                pct = (count / data['total']) * 100
                bar = '#' * int(pct / 5)
                print(f'    {bucket}: {count:5d} ({pct:5.1f}%) {bar}')


# =============================================================================
# Training Data Export
# =============================================================================

def export_training_data(
    log_dir: str,
    training_dir: str,
    min_quality: float,
    stages: list[str] | None = None,
) -> dict[str, int]:
    """
    Export logs to training data format.

    Returns:
        Dict mapping stage names to example counts.
    """
    config = ResponseLoggerConfig(log_dir=log_dir, min_quality_score=min_quality)
    response_logger = ResponseLogger(config)

    training_path = Path(training_dir)
    training_path.mkdir(parents=True, exist_ok=True)

    stages = stages or STAGES
    exported = {}

    for stage in stages:
        output_path = training_path / f'{stage}.json'
        count = response_logger.export_to_training_data(
            stage=stage,
            output_path=output_path,
            min_quality=min_quality,
        )
        exported[stage] = count
        logger.info(f'Exported {count} {stage} examples to {output_path}')

    return exported


# =============================================================================
# MIPROv2 Optimization
# =============================================================================

def run_optimization(
    training_dir: str,
    optimized_dir: str,
    min_examples: int,
    num_candidates: int,
    num_threads: int,
    stages: list[str] | None = None,
) -> dict:
    """
    Run MIPROv2 optimization on training data.

    Returns:
        Dict with optimization results per stage.
    """
    optimizer = DSPyOptimizer(
        training_data_dir=training_dir,
        output_dir=optimized_dir,
        num_candidates=num_candidates,
        num_threads=num_threads,
    )

    stages = stages or ['extraction', 'edge_extraction', 'resolution']  # summary usually doesn't need optimization
    results = {}

    for stage in stages:
        logger.info(f'Checking training data for {stage}...')

        dataset = optimizer.load_training_data(stage)
        if not dataset:
            results[stage] = {'status': 'skipped', 'reason': 'no data'}
            continue

        if len(dataset.examples) < min_examples:
            results[stage] = {
                'status': 'skipped',
                'reason': f'insufficient examples ({len(dataset.examples)} < {min_examples})',
            }
            continue

        logger.info(f'Running MIPROv2 optimization for {stage} with {len(dataset.examples)} examples...')

        try:
            if stage == 'extraction':
                optimized = optimizer.optimize_entity_extraction(min_examples=min_examples)
            elif stage == 'edge_extraction':
                optimized = optimizer.optimize_edge_extraction(min_examples=min_examples)
            elif stage == 'resolution':
                optimized = optimizer.optimize_node_resolution(min_examples=min_examples)
            else:
                results[stage] = {'status': 'skipped', 'reason': 'unsupported stage'}
                continue

            if optimized:
                results[stage] = {
                    'status': 'success',
                    'examples_used': len(dataset.examples),
                    'output_path': str(Path(optimized_dir) / f'{stage}_optimized.json'),
                }
            else:
                results[stage] = {'status': 'failed', 'reason': 'optimization returned None'}

        except Exception as e:
            logger.error(f'Optimization failed for {stage}: {e}')
            results[stage] = {'status': 'error', 'error': str(e)}

    return results


# =============================================================================
# Hot-Reload Marker
# =============================================================================

def write_reload_marker(optimized_dir: str, results: dict):
    """
    Write a marker file indicating new optimized modules are ready.

    The pipeline can watch for this file to trigger hot-reload.
    """
    marker_path = Path(optimized_dir) / 'reload_ready.json'

    data = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'stages': {
            stage: result
            for stage, result in results.items()
            if result.get('status') == 'success'
        },
    }

    if data['stages']:
        with open(marker_path, 'w') as f:
            json.dump(data, f, indent=2)
        logger.info(f'Wrote reload marker to {marker_path}')
    else:
        logger.info('No successful optimizations - skipping reload marker')


# =============================================================================
# Main Entry Point
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Scheduled MIPROv2 optimization for DSPy pipeline',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Analyze logs without running optimization',
    )
    parser.add_argument(
        '--analyze-only',
        action='store_true',
        help='Only print log analysis (alias for --dry-run)',
    )
    parser.add_argument(
        '--stage',
        choices=['extraction', 'edge_extraction', 'resolution', 'summary', 'all'],
        default='all',
        help='Stage to optimize (default: all)',
    )
    parser.add_argument(
        '--min-examples',
        type=int,
        help='Minimum examples required for optimization',
    )
    parser.add_argument(
        '--min-quality',
        type=float,
        help='Minimum quality score for training examples',
    )
    parser.add_argument(
        '--export-only',
        action='store_true',
        help='Export training data without running optimization',
    )
    parser.add_argument(
        '--verbose',
        '-v',
        action='store_true',
        help='Enable verbose logging',
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    config = get_config()

    # Override from args
    if args.min_examples:
        config['min_examples'] = args.min_examples
    if args.min_quality:
        config['min_quality'] = args.min_quality

    # Determine stages to process
    if args.stage == 'all':
        stages = None  # Will use defaults
    else:
        stages = [args.stage]

    # Step 1: Analyze logs
    logger.info('Analyzing logs...')
    stats = analyze_logs(config['log_dir'], config['min_quality'])
    print_analysis(stats, config['min_quality'])

    if args.dry_run or args.analyze_only:
        print('\n[DRY RUN] Exiting without optimization.')
        return

    # Step 2: Export training data
    logger.info('\nExporting training data...')
    exported = export_training_data(
        log_dir=config['log_dir'],
        training_dir=config['training_dir'],
        min_quality=config['min_quality'],
        stages=stages,
    )

    print('\nExported training data:')
    for stage, count in exported.items():
        print(f'  {stage}: {count} examples')

    if args.export_only:
        print('\n[EXPORT ONLY] Exiting without optimization.')
        return

    # Step 3: Run optimization
    logger.info('\nRunning MIPROv2 optimization...')
    results = run_optimization(
        training_dir=config['training_dir'],
        optimized_dir=config['optimized_dir'],
        min_examples=config['min_examples'],
        num_candidates=config['num_candidates'],
        num_threads=config['num_threads'],
        stages=stages,
    )

    print('\nOptimization results:')
    for stage, result in results.items():
        status = result.get('status', 'unknown')
        if status == 'success':
            print(f'  {stage}: SUCCESS ({result.get("examples_used", 0)} examples)')
        elif status == 'skipped':
            print(f'  {stage}: SKIPPED - {result.get("reason", "unknown")}')
        else:
            print(f'  {stage}: {status.upper()} - {result.get("error", result.get("reason", "unknown"))}')

    # Step 4: Write reload marker
    write_reload_marker(config['optimized_dir'], results)

    print('\n' + '=' * 60)
    print('Optimization complete.')
    print('=' * 60)


if __name__ == '__main__':
    main()
