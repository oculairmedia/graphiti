#!/usr/bin/env python3
"""
Prompt Capture Tool - Logs LLM prompts during ingestion via monkey patching.

Usage:
    python capture_prompts.py --samples 10 --output-dir ./prompt_captures
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from dataclasses import dataclass, asdict

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

logging.basicConfig(
    level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class PromptCapture:
    """Captured prompt with metadata"""

    timestamp: str
    prompt_type: str
    messages: list[dict]
    token_count: int
    episode_name: str
    group_id: str
    latency_ms: float

    def to_dict(self):
        return asdict(self)


class PromptCaptureMonkeyPatch:
    """Monkey patch LLM client methods to capture prompts"""

    def __init__(self, output_file: Path):
        self.output_file = output_file
        self.captures = []
        self.original_methods = {}

    def estimate_tokens(self, text: str) -> int:
        """Simple token estimation: ~4 chars per token"""
        return len(text) // 4

    def patch_client(self, client):
        """Patch LLM client generate_response method"""
        original_method = client.generate_response
        self.original_methods[id(client)] = original_method

        async def patched_generate_response(messages, response_model=None, **kwargs):
            start_time = datetime.now()

            # Determine prompt type from caller
            import traceback

            stack = traceback.extract_stack()
            prompt_type = 'unknown'
            for frame in reversed(stack):
                fname = frame.filename
                if 'extract_nodes' in fname:
                    prompt_type = 'extract_nodes'
                    break
                elif 'extract_edges' in fname:
                    prompt_type = 'extract_edges'
                    break
                elif 'dedupe_nodes' in fname:
                    prompt_type = 'dedupe_nodes'
                    break
                elif 'dedupe_edges' in fname:
                    prompt_type = 'dedupe_edges'
                    break
                elif 'extract_attributes' in fname:
                    prompt_type = 'extract_attributes'
                    break

            # Estimate tokens
            prompt_text = json.dumps(
                [
                    {'role': getattr(m, 'role', 'unknown'), 'content': getattr(m, 'content', '')}
                    for m in messages
                ]
            )
            token_count = self.estimate_tokens(prompt_text)

            # Call original method
            try:
                response = await original_method(messages, response_model, **kwargs)
                latency = (datetime.now() - start_time).total_seconds() * 1000

                # Log capture
                logger.info(f'[CAPTURE] {prompt_type}: {token_count} tokens, {latency:.0f}ms')

                # Save to file
                capture = {
                    'timestamp': datetime.utcnow().isoformat(),
                    'prompt_type': prompt_type,
                    'messages': [
                        {
                            'role': getattr(m, 'role', 'unknown'),
                            'content': getattr(m, 'content', ''),
                        }
                        for m in messages
                    ],
                    'token_count': token_count,
                    'latency_ms': latency,
                }

                with open(self.output_file, 'a') as f:
                    f.write(json.dumps(capture) + '\n')

                return response

            except Exception as e:
                logger.error(f'Error in patched method: {e}')
                raise

        client.generate_response = patched_generate_response
        return client


async def capture_from_live_ingestion(
    samples: int = 10, output_dir: Path = Path('./prompt_captures')
):
    """Capture prompts from replaying existing episodes"""
    output_dir.mkdir(exist_ok=True, parents=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_file = output_dir / f'prompts_{timestamp}.jsonl'

    logger.info(f'Capturing up to {samples} episodes to {output_file}')

    from graphiti_core import Graphiti
    from graphiti_core.client_factory import GraphitiClientFactory
    from graphiti_core.driver.falkordb_driver import FalkorDriver
    from graphiti_core.nodes import EpisodicNode

    # Initialize clients
    base_llm = GraphitiClientFactory.create_llm_client()
    base_embedder = GraphitiClientFactory.create_embedder()

    if not base_llm or not base_embedder:
        logger.error('Failed to create clients')
        return

    # Apply monkey patch
    patcher = PromptCaptureMonkeyPatch(output_file)
    patcher.patch_client(base_llm)

    # Initialize Graphiti
    driver = FalkorDriver(
        host=os.getenv('FALKORDB_HOST', 'localhost'),
        port=int(os.getenv('FALKORDB_PORT', '6379')),
        database=os.getenv('FALKORDB_DATABASE', 'graphiti_migration'),
    )

    graphiti = Graphiti(graph_driver=driver, llm_client=base_llm, embedder=base_embedder)

    try:
        # Get recent episodes to replay - query directly to avoid validation issues
        group_id = os.getenv('DEFAULT_GROUP_ID', 'default')

        query = """
        MATCH (e:Episodic) 
        WHERE e.group_id IN $group_ids
        RETURN e.uuid, e.name, e.content, e.source_description, e.valid_at, 
               e.source, e.group_id, e.entity_edges
        ORDER BY e.created_at DESC
        LIMIT $limit
        """

        result = await driver.execute_query(query, group_ids=[group_id], limit=min(samples, 100))
        records = result[0] if result else []

        # Parse episodes manually to handle empty fields
        from graphiti_core.nodes import EpisodeType

        episodes = []
        for record in records:
            try:
                # Parse valid_at from string
                valid_at_raw = record.get('e.valid_at')
                if isinstance(valid_at_raw, str):
                    valid_at = datetime.fromisoformat(valid_at_raw.replace('Z', '+00:00'))
                else:
                    valid_at = valid_at_raw

                episode_data = {
                    'uuid': record.get('e.uuid'),
                    'name': record.get('e.name'),
                    'content': record.get('e.content'),
                    'source_description': record.get('e.source_description') or 'No description',
                    'valid_at': valid_at,
                    'source': EpisodeType(record.get('e.source'))
                    if record.get('e.source')
                    else EpisodeType.message,
                    'group_id': record.get('e.group_id'),
                    'entity_edges': record.get('e.entity_edges') or [],
                }

                episodes.append(type('Episode', (), episode_data))
            except Exception as e:
                logger.warning(f'Skipping malformed episode: {e}')
                continue

        logger.info(f'Found {len(episodes)} episodes, replaying {min(samples, len(episodes))}')

        if not episodes:
            logger.error('No episodes found in database')
            return

        for i, episode in enumerate(episodes[:samples]):
            try:
                logger.info(f'\n=== Episode {i + 1}/{samples}: {episode.name} ===')

                # Replay episode
                result = await graphiti.add_episode(
                    name=episode.name,
                    episode_body=episode.content,
                    source_description=episode.source_description or '',
                    reference_time=episode.valid_at,
                    source=episode.source,
                    group_id=episode.group_id,
                )

                logger.info(f'Result: {len(result.nodes)} nodes, {len(result.edges)} edges')

            except Exception as e:
                logger.error(f'Error processing episode {i}: {e}', exc_info=True)
                continue

        logger.info(f'\n=== Capture Complete ===')
        logger.info(f'Prompts saved to: {output_file}')

        # Generate summary
        summary = generate_summary(output_file)
        summary_file = output_dir / f'summary_{timestamp}.json'
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2)

        logger.info(f'Summary saved to: {summary_file}')
        print_summary(summary)

    finally:
        await driver.close()


def generate_summary(capture_file: Path) -> dict:
    """Generate statistics from captured prompts"""
    captures = []
    with open(capture_file) as f:
        for line in f:
            if line.strip():
                captures.append(json.loads(line))

    if not captures:
        return {'error': 'No captures found'}

    by_type = {}
    for cap in captures:
        ptype = cap['prompt_type']
        if ptype not in by_type:
            by_type[ptype] = {
                'count': 0,
                'total_tokens': 0,
                'total_latency': 0,
                'min_tokens': float('inf'),
                'max_tokens': 0,
            }

        stats = by_type[ptype]
        stats['count'] += 1
        stats['total_tokens'] += cap['token_count']
        stats['total_latency'] += cap.get('latency_ms', 0)
        stats['min_tokens'] = min(stats['min_tokens'], cap['token_count'])
        stats['max_tokens'] = max(stats['max_tokens'], cap['token_count'])

    for stats in by_type.values():
        stats['avg_tokens'] = stats['total_tokens'] / stats['count']
        stats['avg_latency'] = stats['total_latency'] / stats['count']

    return {
        'total_captures': len(captures),
        'by_type': by_type,
        'total_tokens': sum(c['token_count'] for c in captures),
        'total_latency': sum(c.get('latency_ms', 0) for c in captures),
    }


def print_summary(summary: dict):
    """Print formatted summary"""
    print('\n' + '=' * 60)
    print('PROMPT CAPTURE SUMMARY')
    print('=' * 60)
    print(f'Total captures: {summary["total_captures"]}')
    print(f'Total tokens: {summary["total_tokens"]:,}')
    print(f'Total latency: {summary["total_latency"]:.0f}ms')
    print('\nBy prompt type:')
    print('-' * 60)

    for ptype, stats in summary['by_type'].items():
        print(f'\n{ptype}:')
        print(f'  Count: {stats["count"]}')
        print(f'  Avg tokens: {stats["avg_tokens"]:.0f}')
        print(f'  Token range: {stats["min_tokens"]}-{stats["max_tokens"]}')
        print(f'  Avg latency: {stats["avg_latency"]:.0f}ms')

    print('=' * 60)


async def main():
    import argparse

    parser = argparse.ArgumentParser(description='Capture LLM prompts during ingestion')
    parser.add_argument(
        '--samples', type=int, default=10, help='Number of episodes to sample (default: 10)'
    )
    parser.add_argument(
        '--output-dir',
        type=Path,
        default=Path('./prompt_captures'),
        help='Output directory for captures',
    )

    args = parser.parse_args()

    await capture_from_live_ingestion(args.samples, args.output_dir)


if __name__ == '__main__':
    asyncio.run(main())
