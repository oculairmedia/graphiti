#!/usr/bin/env python3
"""
Results Analysis Tool - Analyzes captured and replayed prompts.

Usage:
    python analyze_results.py --captures prompts.jsonl --replays replay_results.jsonl
"""

import json
import sys
from pathlib import Path


def load_jsonl(file_path: Path):
    """Load JSONL file"""
    data = []
    with open(file_path) as f:
        for line in f:
            if line.strip():
                data.append(json.loads(line))
    return data


def analyze_captures(captures):
    """Analyze captured prompts"""
    by_type = {}

    for cap in captures:
        ptype = cap['prompt_type']
        if ptype not in by_type:
            by_type[ptype] = {'count': 0, 'tokens': [], 'latencies': []}

        by_type[ptype]['count'] += 1
        by_type[ptype]['tokens'].append(cap['token_count'])
        by_type[ptype]['latencies'].append(cap.get('latency_ms', 0))

    # Calculate statistics
    stats = {}
    for ptype, data in by_type.items():
        tokens = data['tokens']
        latencies = data['latencies']

        stats[ptype] = {
            'count': data['count'],
            'tokens': {
                'min': min(tokens),
                'max': max(tokens),
                'avg': sum(tokens) / len(tokens),
                'total': sum(tokens),
            },
            'latency': {
                'min': min(latencies),
                'max': max(latencies),
                'avg': sum(latencies) / len(latencies),
                'total': sum(latencies),
            },
        }

    return stats


def print_analysis_report(captures_stats):
    """Print formatted analysis report"""
    print('\n' + '=' * 70)
    print('PROMPT ANALYSIS REPORT')
    print('=' * 70)

    print('\n### CAPTURE ANALYSIS ###')
    total_tokens = sum(s['tokens']['total'] for s in captures_stats.values())
    total_calls = sum(s['count'] for s in captures_stats.values())

    print(f'\nTotal calls: {total_calls}')
    print(f'Total tokens: {total_tokens:,}')
    print(f'Average tokens per call: {total_tokens / total_calls:.0f}')

    print('\nBy prompt type:')
    print('-' * 70)

    for ptype, stats in sorted(
        captures_stats.items(), key=lambda x: x[1]['tokens']['total'], reverse=True
    ):
        print(f'\n{ptype}:')
        print(f'  Calls: {stats["count"]}')
        print(
            f'  Tokens: avg={stats["tokens"]["avg"]:.0f}, min={stats["tokens"]["min"]}, max={stats["tokens"]["max"]}'
        )
        print(
            f'  Total tokens: {stats["tokens"]["total"]:,} ({stats["tokens"]["total"] / total_tokens * 100:.1f}%)'
        )
        print(
            f'  Latency: avg={stats["latency"]["avg"]:.0f}ms, total={stats["latency"]["total"]:.0f}ms'
        )

    print('\n' + '=' * 70)


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Analyze prompt captures')
    parser.add_argument('--captures', type=Path, required=True, help='Captures file (.jsonl)')
    parser.add_argument(
        '--output-dir', type=Path, default=Path('./analysis_output'), help='Output directory'
    )

    args = parser.parse_args()

    # Load data
    print(f'Loading captures from {args.captures}...')
    captures = load_jsonl(args.captures)

    # Analyze
    captures_stats = analyze_captures(captures)

    # Print report
    print_analysis_report(captures_stats)

    # Save full report
    args.output_dir.mkdir(exist_ok=True, parents=True)
    report_file = args.output_dir / 'analysis_report.json'
    with open(report_file, 'w') as f:
        json.dump(captures_stats, f, indent=2)

    print(f'\nFull report saved to: {report_file}')


if __name__ == '__main__':
    main()
