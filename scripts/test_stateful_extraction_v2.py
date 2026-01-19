#!/usr/bin/env python3
"""
Test Stateful Entity Extraction using our custom Letta wrapper.

Compares extraction quality between:
1. Stateless extraction (no memory context)
2. Stateful extraction (with Letta archival memory)

Uses Chutes/Z.AI (OpenAI-compatible API) for LLM inference.
"""

import json
import os
import sys
from dataclasses import dataclass

sys.path.insert(0, '/opt/stacks/graphiti')

from openai import OpenAI
from graphiti_core.utils.stateful_learning import StatefulLearningClient

# Set environment
os.environ['LETTA_BASE_URL'] = 'http://192.168.50.90:8289'
os.environ['LETTA_API_KEY'] = 'lettaSecurePass123'

AGENT_ID = 'agent-fe8a9291-b49a-4fc1-94c3-1a23b86b6108'  # GraphitiExplorer

# Chutes/Z.AI configuration (OpenAI-compatible)
CHUTES_API_KEY = os.getenv('CHUTES_API_KEY', 'c9e26b23c6194059892ff22e99ec0ad6.pSk7TwXDsLSQNtvT')
CHUTES_BASE_URL = os.getenv('CHUTES_BASE_URL', 'https://api.z.ai/api/coding/paas/v4')
CHUTES_MODEL = os.getenv('CHUTES_MODEL', 'glm-4.5')

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

{context}

Message: {content}

Respond with valid JSON only, no markdown."""


@dataclass
class ExtractionResult:
    episode_id: int
    entities: list[dict]
    raw_response: str


def extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith('```'):
        lines = text.split('\n')
        text = '\n'.join(lines[1:-1] if lines[-1].strip() == '```' else lines[1:])
    try:
        return json.loads(text)
    except:
        return {'entities': []}


def extract_stateless(client: OpenAI, episode: dict) -> ExtractionResult:
    """Extract without memory context"""
    response = client.chat.completions.create(
        model=CHUTES_MODEL,
        max_tokens=1024,
        messages=[
            {
                'role': 'system',
                'content': 'You are an entity extraction assistant. Return valid JSON only.',
            },
            {
                'role': 'user',
                'content': EXTRACTION_PROMPT.format(context='', content=episode['content']),
            },
        ],
    )

    raw = response.choices[0].message.content if response.choices else ''
    raw = raw or ''
    data = extract_json(raw)

    return ExtractionResult(episode['id'], data.get('entities', []), raw)


def extract_stateful(
    client: OpenAI, episode: dict, learning: StatefulLearningClient, agent_id: str
) -> ExtractionResult:
    """Extract WITH memory context from previous extractions"""

    # Get hints from previous extractions
    hints = learning.get_extraction_hints(agent_id, episode['content'][:200])
    context = (
        f'\n<PREVIOUS_EXTRACTIONS>\n{hints}\n</PREVIOUS_EXTRACTIONS>\n\nUse consistent entity names with previous extractions.'
        if hints
        else ''
    )

    response = client.chat.completions.create(
        model=CHUTES_MODEL,
        max_tokens=1024,
        messages=[
            {
                'role': 'system',
                'content': 'You are an entity extraction assistant. Return valid JSON only. Be consistent with entity names from previous extractions.',
            },
            {
                'role': 'user',
                'content': EXTRACTION_PROMPT.format(context=context, content=episode['content']),
            },
        ],
    )

    raw = response.choices[0].message.content if response.choices else ''
    raw = raw or ''
    data = extract_json(raw)
    entities = data.get('entities', [])

    # Store this extraction for future reference
    learning.store_extraction_memory(agent_id, episode['content'], entities)

    return ExtractionResult(episode['id'], entities, raw)


def analyze(results: list[ExtractionResult]) -> dict:
    """Analyze entity naming consistency"""
    all_names = []
    variations = {}

    for r in results:
        for e in r.entities:
            name = e.get('name', '').lower().strip()
            all_names.append(name)
            base = name.replace('-', ' ').replace('_', ' ')
            if base not in variations:
                variations[base] = set()
            variations[base].add(e.get('name', ''))

    inconsistencies = {k: list(v) for k, v in variations.items() if len(v) > 1}

    return {
        'unique': len(set(all_names)),
        'total': len(all_names),
        'ratio': len(set(all_names)) / len(all_names) if all_names else 0,
        'inconsistencies': inconsistencies,
    }


def print_results(title: str, results: list[ExtractionResult], analysis: dict):
    print(f'\n{"=" * 60}')
    print(title)
    print('=' * 60)

    for r in results:
        print(f'\nEpisode {r.episode_id}:')
        for e in r.entities:
            print(f'  - {e.get("name", "?")} ({e.get("type", "?")})')

    print(f'\n--- Analysis ---')
    print(f'Unique names: {analysis["unique"]}, Total: {analysis["total"]}')
    print(f'Consistency: {analysis["ratio"]:.1%}')

    if analysis['inconsistencies']:
        print(f'Inconsistencies: {analysis["inconsistencies"]}')
    else:
        print('No inconsistencies!')


def main():
    print('Stateful vs Stateless Extraction Test (v2 - Chutes/Z.AI)')
    print('=' * 60)
    print(f'Using model: {CHUTES_MODEL}')
    print(f'Using endpoint: {CHUTES_BASE_URL}')

    if not CHUTES_API_KEY:
        print('ERROR: CHUTES_API_KEY not set')
        return

    # Initialize Chutes/Z.AI client (OpenAI-compatible)
    chutes_client = OpenAI(
        api_key=CHUTES_API_KEY,
        base_url=CHUTES_BASE_URL,
    )

    learning = StatefulLearningClient()

    # Verify agent exists
    agent = learning.get_agent_by_name('GraphitiExplorer')
    if not agent:
        print('ERROR: GraphitiExplorer agent not found')
        return
    print(f'Using Letta agent: {agent.name} ({agent.id})')

    # Run stateless extraction
    print('\n[1/2] STATELESS extraction...')
    stateless = []
    for ep in TEST_EPISODES:
        try:
            r = extract_stateless(chutes_client, ep)
            stateless.append(r)
            print(f'  Episode {ep["id"]}: {len(r.entities)} entities')
        except Exception as e:
            print(f'  Episode {ep["id"]}: ERROR - {e}')
            stateless.append(ExtractionResult(ep['id'], [], str(e)))

    stateless_analysis = analyze(stateless)
    print_results('STATELESS RESULTS', stateless, stateless_analysis)

    # Run stateful extraction
    print('\n[2/2] STATEFUL extraction...')
    stateful = []
    for ep in TEST_EPISODES:
        try:
            r = extract_stateful(chutes_client, ep, learning, agent.id)
            stateful.append(r)
            print(f'  Episode {ep["id"]}: {len(r.entities)} entities')
        except Exception as e:
            print(f'  Episode {ep["id"]}: ERROR - {e}')
            stateful.append(ExtractionResult(ep['id'], [], str(e)))

    stateful_analysis = analyze(stateful)
    print_results('STATEFUL RESULTS', stateful, stateful_analysis)

    # Compare
    print('\n' + '=' * 60)
    print('COMPARISON')
    print('=' * 60)
    print(
        f'Stateless: {stateless_analysis["ratio"]:.1%} consistency, {len(stateless_analysis["inconsistencies"])} inconsistencies'
    )
    print(
        f'Stateful:  {stateful_analysis["ratio"]:.1%} consistency, {len(stateful_analysis["inconsistencies"])} inconsistencies'
    )

    if stateful_analysis['ratio'] > stateless_analysis['ratio']:
        print('\n>>> STATEFUL showed BETTER consistency!')
    elif stateful_analysis['ratio'] < stateless_analysis['ratio']:
        print('\n>>> STATELESS showed better consistency')
    else:
        print('\n>>> Both approaches showed similar consistency')

    # Show specific inconsistencies found
    if stateless_analysis['inconsistencies'] or stateful_analysis['inconsistencies']:
        print('\n--- Detailed Inconsistencies ---')
        if stateless_analysis['inconsistencies']:
            print(f'Stateless variations: {stateless_analysis["inconsistencies"]}')
        if stateful_analysis['inconsistencies']:
            print(f'Stateful variations: {stateful_analysis["inconsistencies"]}')


if __name__ == '__main__':
    main()
