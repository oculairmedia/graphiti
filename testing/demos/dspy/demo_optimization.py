#!/usr/bin/env python3
"""
Demo: DSPy MIPROv2 Optimization

This script demonstrates how to:
1. Collect training data from pipeline runs
2. Save training data for later optimization
3. Run MIPROv2 optimization (requires 50+ examples)

Usage:
    # Collect training data
    CHUTES_API_KEY=your-key python3 demo_optimization.py --collect

    # Run optimization (after collecting 50+ examples)
    CHUTES_API_KEY=your-key python3 demo_optimization.py --optimize
"""

import os
import sys
import argparse
import logging
from datetime import datetime, timezone

sys.path.insert(0, '/opt/stacks/graphiti')

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Sample episodes for training data collection
SAMPLE_EPISODES = [
    # Tech industry
    "Satya Nadella announced that Microsoft is acquiring Activision Blizzard for $69 billion.",
    "Tim Cook revealed the new iPhone 15 at Apple's annual keynote event in Cupertino.",
    "Elon Musk tweeted that Tesla will accept Dogecoin for merchandise.",
    "Mark Zuckerberg changed Facebook's name to Meta and pivoted to the metaverse.",
    "Sundar Pichai announced Google's new Gemini AI model at Google I/O 2024.",

    # Workplace scenarios
    "Sarah joined TechCorp as a senior engineer. She reports to Director Mike Chen.",
    "The marketing team, led by Jennifer, launched the Q4 campaign for ProductX.",
    "CEO Robert approved the budget for Project Phoenix. CFO Lisa will oversee finances.",
    "Dr. Smith from the Research department published findings on quantum computing.",
    "The DevOps team migrated all services to AWS. Lead engineer Tom coordinated the effort.",

    # Events and relationships
    "The annual tech conference TechSummit 2024 will be held in San Francisco next month.",
    "StartupXYZ raised $50 million in Series B funding led by Sequoia Capital.",
    "The merger between CompanyA and CompanyB was approved by the board yesterday.",
    "Professor Johnson from MIT collaborated with Google on the new ML framework.",
    "The customer support team resolved 500 tickets this week. Manager Alice praised the team.",

    # Complex relationships
    "John worked at Google from 2015 to 2020, then joined Microsoft as a principal engineer.",
    "The partnership between Amazon and Anthropic focuses on AI safety research.",
    "Netflix acquired game studio Night School Studio to expand into gaming.",
    "Former Apple engineer Tony Fadell founded Nest, which was later acquired by Google.",
    "SpaceX launched Starship from Boca Chica. NASA administrator praised the achievement.",
]


def collect_training_data(num_episodes: int = 10):
    """Collect training data from pipeline runs."""
    from graphiti_core.dspy import (
        DSPyIngestionPipeline,
        TrainingDataCollector,
        configure_lm,
    )
    from graphiti_core.dspy.signatures import ExtractedEntities, ExtractedEdges

    configure_lm()

    pipeline = DSPyIngestionPipeline(generate_summaries=False)
    collector = TrainingDataCollector(save_dir='training_data')

    episodes = SAMPLE_EPISODES[:num_episodes]

    print(f'\nCollecting training data from {len(episodes)} episodes...\n')

    for i, content in enumerate(episodes):
        print(f'[{i+1}/{len(episodes)}] {content[:60]}...')

        try:
            result = pipeline.ingest_episode(content, f'train_ep_{i}')

            # Record entity extraction
            if result.extracted_entities:
                collector.record_entity_extraction(
                    current_message=content,
                    entity_types=pipeline.entity_types,
                    result=ExtractedEntities(
                        extracted_entities=[
                            {'name': e['name'], 'entity_type_id': e.get('type_id', 0)}
                            for e in result.extracted_entities
                        ]
                    ),
                )

            # Record edge extraction
            if result.extracted_edges:
                collector.record_edge_extraction(
                    current_message=content,
                    entities=[{'id': i, 'name': e['name'], 'type': e['type']}
                              for i, e in enumerate(result.resolved_entities)],
                    reference_time=result.timestamp,
                    result=ExtractedEdges(edges=[]),  # Simplified for demo
                )

            print(f'  Entities: {len(result.extracted_entities)}, Edges: {len(result.extracted_edges)}')

        except Exception as e:
            print(f'  Error: {e}')

    # Save collected data
    collector.save_all()

    stats = collector.get_stats()
    print(f'\n=== Training Data Stats ===')
    for task, count in stats.items():
        print(f'  {task}: {count} examples')

    print(f'\nData saved to: training_data/')
    print(f'Need 50+ examples per task before optimization.')


def run_optimization():
    """Run MIPROv2 optimization on collected data."""
    from graphiti_core.dspy import DSPyOptimizer, configure_lm

    configure_lm()

    optimizer = DSPyOptimizer(
        training_data_dir='training_data',
        output_dir='optimized_modules',
        num_candidates=5,  # Reduce for faster iteration
        num_threads=2,
    )

    print('\n=== Running MIPROv2 Optimization ===\n')

    # Check data availability
    from pathlib import Path
    data_dir = Path('training_data')

    for task in ['entity_extraction', 'edge_extraction', 'node_resolution']:
        path = data_dir / f'{task}.json'
        if path.exists():
            import json
            with open(path) as f:
                data = json.load(f)
            print(f'{task}: {data["example_count"]} examples')
        else:
            print(f'{task}: No data')

    print()

    # Optimize (will warn if insufficient data)
    results = optimizer.optimize_all(min_examples=50)

    print('\n=== Optimization Results ===')
    for task, result in results.items():
        status = 'Optimized' if result else 'Skipped (insufficient data)'
        print(f'  {task}: {status}')


def show_stats():
    """Show current training data statistics."""
    from pathlib import Path
    import json

    data_dir = Path('training_data')

    print('\n=== Training Data Statistics ===\n')

    if not data_dir.exists():
        print('No training data directory found.')
        print('Run with --collect to gather training data.')
        return

    for task in ['entity_extraction', 'edge_extraction', 'node_resolution', 'summary_generation']:
        path = data_dir / f'{task}.json'
        if path.exists():
            with open(path) as f:
                data = json.load(f)
            print(f'{task}:')
            print(f'  Examples: {data["example_count"]}')
            print(f'  Created: {data.get("created_at", "unknown")}')
            print(f'  Ready for optimization: {"Yes" if data["example_count"] >= 50 else "No (need 50+)"}')
        else:
            print(f'{task}: No data file')
        print()


def main():
    parser = argparse.ArgumentParser(description='DSPy MIPROv2 Optimization Demo')
    parser.add_argument('--collect', action='store_true', help='Collect training data')
    parser.add_argument('--optimize', action='store_true', help='Run optimization')
    parser.add_argument('--stats', action='store_true', help='Show training data stats')
    parser.add_argument('--episodes', type=int, default=10, help='Number of episodes to collect')

    args = parser.parse_args()

    if not any([args.collect, args.optimize, args.stats]):
        args.stats = True  # Default to showing stats

    # Check API key
    if (args.collect or args.optimize) and not os.environ.get('CHUTES_API_KEY'):
        print('ERROR: CHUTES_API_KEY environment variable not set')
        sys.exit(1)

    if args.stats:
        show_stats()

    if args.collect:
        collect_training_data(args.episodes)

    if args.optimize:
        run_optimization()


if __name__ == '__main__':
    main()
