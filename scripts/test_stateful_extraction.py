#!/usr/bin/env python3
"""
Test Stateful Entity Extraction using Letta Learning SDK

Compares extraction quality between:
1. Stateless extraction (current Graphiti approach)
2. Stateful extraction (with Letta Learning SDK)
"""

import asyncio
import json
import os
import sys
from dataclasses import dataclass
from typing import Any

sys.path.insert(0, '/opt/stacks/graphiti')

from anthropic import Anthropic
from agentic_learning import learning, AgenticLearning

TEST_EPISODES = [
    {
        'id': 1,
        'content': "Emmanuel: I'm working on the Graphiti project today. It uses FalkorDB as the graph database.",
    },
    {
        'id': 2,
        'content': 'Emmanuel: The Graphiti system also has a Rust visualizer that connects to Falkor DB.',
    },
    {
        'id': 3,
        'content': 'User: Can you check if the graphiti-worker is processing episodes correctly?',
    },
    {
        'id': 4,
        'content': 'Emmanuel: Yes, the worker is connected to the FalkorDB instance on port 6379.',
    },
    {
        'id': 5,
        'content': 'System: Alert - high memory usage detected on the Graphiti stack. Emmanuel notified.',
    },
]

EXTRACTION_PROMPT = """Extract all named entities from the following message.
Return a JSON object with an "entities" array containing objects with "name" and "type" fields.

Entity types: Person, System, Project, Database, Component, Alert

Message: {content}

Respond with valid JSON only, no markdown code blocks."""


@dataclass
class ExtractionResult:
    episode_id: int
    entities: list[dict[str, str]]
    raw_response: str


def extract_json_from_response(text: str) -> dict:
    """Extract JSON from response, handling markdown code blocks"""
    text = text.strip()
    if text.startswith('```'):
        lines = text.split('\n')
        text = '\n'.join(lines[1:-1] if lines[-1].strip() == '```' else lines[1:])
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {'entities': []}


async def extract_stateless(client: Anthropic, episode: dict) -> ExtractionResult:
    """Extract entities without learning context"""
    response = client.messages.create(
        model='claude-3-5-haiku-latest',
        max_tokens=1024,
        system='You are an entity extraction assistant. Return valid JSON only, no markdown.',
        messages=[
            {'role': 'user', 'content': EXTRACTION_PROMPT.format(content=episode['content'])},
        ],
    )

    raw = ''
    if response.content:
        block = response.content[0]
        if hasattr(block, 'text'):
            raw = block.text

    data = extract_json_from_response(raw)
    entities = data.get('entities', [])

    return ExtractionResult(
        episode_id=episode['id'],
        entities=entities,
        raw_response=raw,
    )


async def extract_stateful(
    client: Anthropic, episode: dict, agent_name: str, learning_client: AgenticLearning
) -> ExtractionResult:
    """Extract entities with learning context (stateful approach)"""
    with learning(agent=agent_name, memory=['entities', 'patterns'], client=learning_client):
        response = client.messages.create(
            model='claude-3-5-haiku-latest',
            max_tokens=1024,
            system="You are an entity extraction assistant. Return valid JSON only. Be consistent with entity names you've used before.",
            messages=[
                {'role': 'user', 'content': EXTRACTION_PROMPT.format(content=episode['content'])},
            ],
        )

    raw = ''
    if response.content:
        block = response.content[0]
        if hasattr(block, 'text'):
            raw = block.text

    data = extract_json_from_response(raw)
    entities = data.get('entities', [])

    return ExtractionResult(
        episode_id=episode['id'],
        entities=entities,
        raw_response=raw,
    )


def analyze_consistency(results: list[ExtractionResult]) -> dict[str, Any]:
    """Analyze entity naming consistency across episodes"""
    all_entity_names = []
    entity_variations: dict[str, set[str]] = {}

    for result in results:
        for entity in result.entities:
            name = entity.get('name', '').lower().strip()
            all_entity_names.append(name)

            base_name = name.replace('-', ' ').replace('_', ' ')
            if base_name not in entity_variations:
                entity_variations[base_name] = set()
            entity_variations[base_name].add(entity.get('name', ''))

    unique_names = len(set(all_entity_names))
    total_mentions = len(all_entity_names)

    inconsistencies = {k: list(v) for k, v in entity_variations.items() if len(v) > 1}

    return {
        'unique_names': unique_names,
        'total_mentions': total_mentions,
        'consistency_ratio': unique_names / total_mentions if total_mentions > 0 else 0,
        'inconsistencies': inconsistencies,
    }


def print_results(title: str, results: list[ExtractionResult], analysis: dict):
    """Pretty print extraction results"""
    print(f'\n{"=" * 60}')
    print(f'{title}')
    print(f'{"=" * 60}')

    for result in results:
        print(f'\nEpisode {result.episode_id}:')
        for entity in result.entities:
            print(f'  - {entity.get("name", "?")} ({entity.get("type", "?")})')

    print(f'\n--- Analysis ---')
    print(f'Unique entity names: {analysis["unique_names"]}')
    print(f'Total entity mentions: {analysis["total_mentions"]}')
    print(f'Consistency ratio: {analysis["consistency_ratio"]:.2%}')

    if analysis['inconsistencies']:
        print(f'\nInconsistencies found:')
        for base, variations in analysis['inconsistencies'].items():
            print(f"  '{base}': {variations}")
    else:
        print(f'\nNo inconsistencies found!')


async def main():
    print('Stateful vs Stateless Entity Extraction Test')
    print('=' * 60)

    anthropic_key = os.getenv('ANTHROPIC_API_KEY')
    letta_url = os.getenv('LETTA_BASE_URL', 'http://192.168.50.90:8289')
    letta_key = os.getenv('LETTA_API_KEY')

    if not anthropic_key:
        print('ERROR: ANTHROPIC_API_KEY not set')
        return

    print(f'Using Letta server: {letta_url}')

    anthropic_client = Anthropic(api_key=anthropic_key)

    try:
        learning_client = AgenticLearning(base_url=letta_url, api_key=letta_key)
        print('Connected to Letta server')
    except Exception as e:
        print(f'WARNING: Could not connect to Letta server: {e}')
        print('Running stateless-only test')
        learning_client = None

    print('\n[1/2] Running STATELESS extraction...')
    stateless_results = []
    for episode in TEST_EPISODES:
        result = await extract_stateless(anthropic_client, episode)
        stateless_results.append(result)
        print(f'  Episode {episode["id"]}: {len(result.entities)} entities')

    stateless_analysis = analyze_consistency(stateless_results)
    print_results('STATELESS EXTRACTION RESULTS', stateless_results, stateless_analysis)

    if learning_client:
        print('\n[2/2] Running STATEFUL extraction...')
        agent_name = (
            'GraphitiExplorer'  # Existing agent: agent-fe8a9291-b49a-4fc1-94c3-1a23b86b6108
        )

        stateful_results = []
        for episode in TEST_EPISODES:
            result = await extract_stateful(anthropic_client, episode, agent_name, learning_client)
            stateful_results.append(result)
            print(f'  Episode {episode["id"]}: {len(result.entities)} entities')

        stateful_analysis = analyze_consistency(stateful_results)
        print_results('STATEFUL EXTRACTION RESULTS', stateful_results, stateful_analysis)

        print('\n' + '=' * 60)
        print('COMPARISON')
        print('=' * 60)
        print(f'Stateless consistency: {stateless_analysis["consistency_ratio"]:.2%}')
        print(f'Stateful consistency:  {stateful_analysis["consistency_ratio"]:.2%}')
        print(f'Stateless inconsistencies: {len(stateless_analysis["inconsistencies"])}')
        print(f'Stateful inconsistencies:  {len(stateful_analysis["inconsistencies"])}')

        if stateful_analysis['consistency_ratio'] > stateless_analysis['consistency_ratio']:
            print('\n>>> STATEFUL extraction showed BETTER consistency!')
        elif stateful_analysis['consistency_ratio'] < stateless_analysis['consistency_ratio']:
            print('\n>>> STATELESS extraction showed better consistency (unexpected)')
        else:
            print('\n>>> Both approaches showed similar consistency')
    else:
        print('\n[2/2] Skipping STATEFUL extraction (Letta not available)')

    print('\nTest complete!')


if __name__ == '__main__':
    asyncio.run(main())
