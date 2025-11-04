#!/usr/bin/env python3
"""
Prompt Replay Tool - Tests different prompt configurations using captured prompts.

Usage:
    python replay_prompts.py --input prompts_20250123.jsonl --config config.json
"""

import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from dataclasses import dataclass, asdict

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from graphiti_core.client_factory import GraphitiClientFactory

logging.basicConfig(
    level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class ReplayConfig:
    """Configuration for prompt replay experiments"""

    name: str
    description: str
    previous_episodes_limit: Optional[int] = None  # Trim previous episodes
    existing_nodes_limit: Optional[int] = None  # Trim dedupe candidates
    compression_enabled: bool = False  # Use prompt compression

    def to_dict(self):
        return asdict(self)


@dataclass
class ReplayResult:
    """Result from replaying a single prompt"""

    config_name: str
    prompt_type: str
    original_tokens: int
    modified_tokens: int
    latency_ms: float
    response: dict
    success: bool
    error: Optional[str] = None

    def to_dict(self):
        return asdict(self)


class PromptReplayHarness:
    """Harness for replaying captured prompts with modifications"""

    def __init__(self, llm_client):
        self.llm_client = llm_client

    def estimate_tokens(self, text: str) -> int:
        """Simple token estimation"""
        return len(text) // 4

    def apply_config(self, messages: list[dict], config: ReplayConfig) -> list[dict]:
        """Apply configuration to modify prompt"""
        modified = []

        for msg in messages:
            content = msg['content']

            # Apply previous episode limiting
            if config.previous_episodes_limit is not None:
                if '<PREVIOUS MESSAGES>' in content:
                    # Extract and trim previous episodes
                    parts = content.split('<PREVIOUS MESSAGES>')
                    if len(parts) > 1:
                        before = parts[0]
                        after_parts = parts[1].split('</PREVIOUS MESSAGES>')
                        if len(after_parts) > 1:
                            prev_episodes = after_parts[0]
                            rest = after_parts[1]

                            # Parse and trim
                            try:
                                episodes = json.loads(prev_episodes.strip())
                                if isinstance(episodes, list):
                                    episodes = episodes[-config.previous_episodes_limit :]
                                    prev_episodes = json.dumps(episodes, indent=2)
                            except:
                                pass

                            content = f'{before}<PREVIOUS MESSAGES>\n{prev_episodes}\n</PREVIOUS MESSAGES>{rest}'

            # Apply existing nodes limiting for dedupe prompts
            if config.existing_nodes_limit is not None:
                if '<EXISTING NODES>' in content or 'existing_nodes' in content.lower():
                    # Similar trimming logic for existing nodes
                    pass

            modified.append({'role': msg['role'], 'content': content})

        return modified

    async def replay_prompt(self, capture: dict, config: ReplayConfig) -> ReplayResult:
        """Replay a single captured prompt with configuration"""
        try:
            # Apply config modifications
            original_messages = capture['messages']
            modified_messages = self.apply_config(original_messages, config)

            # Calculate token counts
            original_tokens = capture['token_count']
            modified_text = json.dumps(modified_messages)
            modified_tokens = self.estimate_tokens(modified_text)

            # Convert to Message objects
            from graphiti_core.prompts.models import Message

            msg_objects = [Message(role=m['role'], content=m['content']) for m in modified_messages]

            # Replay with LLM
            start_time = datetime.now()
            response = await self.llm_client.generate_response(msg_objects)
            latency = (datetime.now() - start_time).total_seconds() * 1000

            return ReplayResult(
                config_name=config.name,
                prompt_type=capture['prompt_type'],
                original_tokens=original_tokens,
                modified_tokens=modified_tokens,
                latency_ms=latency,
                response=response if isinstance(response, dict) else {'raw': str(response)},
                success=True,
            )

        except Exception as e:
            logger.error(f'Replay error: {e}')
            return ReplayResult(
                config_name=config.name,
                prompt_type=capture['prompt_type'],
                original_tokens=capture['token_count'],
                modified_tokens=0,
                latency_ms=0,
                response={},
                success=False,
                error=str(e),
            )


async def run_replay_experiments(
    capture_file: Path, configs: list[ReplayConfig], output_dir: Path, max_samples: int = 10
):
    """Run replay experiments with different configurations"""

    output_dir.mkdir(exist_ok=True, parents=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    results_file = output_dir / f'replay_results_{timestamp}.jsonl'

    logger.info(f'Loading captures from {capture_file}')

    # Load captures
    captures = []
    with open(capture_file) as f:
        for line in f:
            if line.strip():
                captures.append(json.loads(line))

    logger.info(f'Loaded {len(captures)} captures')

    # Initialize LLM
    llm_client = GraphitiClientFactory.create_llm_client()
    if not llm_client:
        logger.error('Failed to create LLM client')
        return

    harness = PromptReplayHarness(llm_client)

    # Run experiments
    all_results = []

    for config in configs:
        logger.info(f'\n=== Testing config: {config.name} ===')
        logger.info(f'Description: {config.description}')

        for i, capture in enumerate(captures[:max_samples]):
            logger.info(
                f'Replaying {i + 1}/{min(max_samples, len(captures))}: {capture["prompt_type"]}'
            )

            result = await harness.replay_prompt(capture, config)
            all_results.append(result)

            # Write incrementally
            with open(results_file, 'a') as f:
                f.write(json.dumps(result.to_dict()) + '\n')

            if result.success:
                token_reduction = result.original_tokens - result.modified_tokens
                logger.info(
                    f'  Tokens: {result.original_tokens} → {result.modified_tokens} '
                    f'({token_reduction} saved, {result.latency_ms:.0f}ms)'
                )
            else:
                logger.error(f'  Failed: {result.error}')

    # Generate comparison report
    report = generate_comparison_report(all_results, configs)
    report_file = output_dir / f'comparison_report_{timestamp}.json'
    with open(report_file, 'w') as f:
        json.dump(report, f, indent=2)

    logger.info(f'\n=== Results saved to {results_file} ===')
    logger.info(f'Comparison report: {report_file}')
    print_comparison_report(report)


def generate_comparison_report(results: list[ReplayResult], configs: list[ReplayConfig]) -> dict:
    """Generate comparison report across configurations"""
    by_config = {}

    for result in results:
        config_name = result.config_name
        if config_name not in by_config:
            by_config[config_name] = {
                'total_original_tokens': 0,
                'total_modified_tokens': 0,
                'total_latency': 0,
                'success_count': 0,
                'failure_count': 0,
                'by_prompt_type': {},
            }

        stats = by_config[config_name]
        stats['total_original_tokens'] += result.original_tokens
        stats['total_modified_tokens'] += result.modified_tokens
        stats['total_latency'] += result.latency_ms

        if result.success:
            stats['success_count'] += 1
        else:
            stats['failure_count'] += 1

        # By prompt type
        ptype = result.prompt_type
        if ptype not in stats['by_prompt_type']:
            stats['by_prompt_type'][ptype] = {'count': 0, 'tokens_saved': 0}

        stats['by_prompt_type'][ptype]['count'] += 1
        stats['by_prompt_type'][ptype]['tokens_saved'] += (
            result.original_tokens - result.modified_tokens
        )

    return {'configs': [c.to_dict() for c in configs], 'by_config': by_config}


def print_comparison_report(report: dict):
    """Print formatted comparison report"""
    print('\n' + '=' * 60)
    print('REPLAY COMPARISON REPORT')
    print('=' * 60)

    for config_name, stats in report['by_config'].items():
        tokens_saved = stats['total_original_tokens'] - stats['total_modified_tokens']
        reduction_pct = (
            (tokens_saved / stats['total_original_tokens'] * 100)
            if stats['total_original_tokens'] > 0
            else 0
        )

        print(f'\n{config_name}:')
        print(
            f'  Success: {stats["success_count"]} / {stats["success_count"] + stats["failure_count"]}'
        )
        print(f'  Tokens saved: {tokens_saved:,} ({reduction_pct:.1f}% reduction)')
        print(f'  Total latency: {stats["total_latency"]:.0f}ms')

        if stats['by_prompt_type']:
            print(f'  By prompt type:')
            for ptype, pstats in stats['by_prompt_type'].items():
                print(
                    f'    {ptype}: {pstats["count"]} calls, {pstats["tokens_saved"]} tokens saved'
                )

    print('=' * 60)


async def main():
    import argparse

    parser = argparse.ArgumentParser(description='Replay captured prompts with modifications')
    parser.add_argument('--input', type=Path, required=True, help='Input capture file (.jsonl)')
    parser.add_argument(
        '--output-dir', type=Path, default=Path('./replay_results'), help='Output directory'
    )
    parser.add_argument(
        '--max-samples', type=int, default=10, help='Max prompts to replay per config'
    )

    args = parser.parse_args()

    # Define test configurations
    configs = [
        ReplayConfig(name='baseline', description='Original prompts unmodified'),
        ReplayConfig(
            name='trim_prev_episodes_5',
            description='Limit previous episodes to last 5',
            previous_episodes_limit=5,
        ),
        ReplayConfig(
            name='trim_prev_episodes_3',
            description='Limit previous episodes to last 3',
            previous_episodes_limit=3,
        ),
        ReplayConfig(
            name='trim_existing_nodes_20',
            description='Limit existing nodes to 20 for dedupe',
            existing_nodes_limit=20,
        ),
    ]

    await run_replay_experiments(args.input, configs, args.output_dir, args.max_samples)


if __name__ == '__main__':
    asyncio.run(main())
