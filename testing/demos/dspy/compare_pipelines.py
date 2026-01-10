#!/usr/bin/env python3
"""
Side-by-side Pipeline Comparison: Legacy vs DSPy

Runs both pipelines SEQUENTIALLY (not concurrent) to avoid overwhelming the API.
Saves intermediate results so you can resume if interrupted.

Usage:
    # Run full comparison
    CHUTES_API_KEY=your-key python3 compare_pipelines.py

    # Run only legacy (saves results for later DSPy comparison)
    CHUTES_API_KEY=your-key python3 compare_pipelines.py --legacy-only

    # Run only DSPy (uses saved legacy results)
    CHUTES_API_KEY=your-key python3 compare_pipelines.py --dspy-only

    # Compare saved results without running pipelines
    python3 compare_pipelines.py --compare-only
"""

import os
import sys
import json
import argparse
import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, '/opt/stacks/graphiti')

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Test episodes for comparison
TEST_EPISODES = [
    {
        'id': 'ep_001',
        'content': 'Sarah started a new project called DataFlow using Python and PostgreSQL.',
    },
    {
        'id': 'ep_002',
        'content': 'Mike joined the DataFlow team. Sarah promoted him to lead developer.',
    },
    {
        'id': 'ep_003',
        'content': 'Dr. Chen from the AI division will help with machine learning components for DataFlow.',
    },
]

RESULTS_DIR = Path('comparison_results')


def save_results(results: dict, filename: str):
    """Save results to JSON file."""
    RESULTS_DIR.mkdir(exist_ok=True)
    path = RESULTS_DIR / filename
    with open(path, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f'Saved: {path}')


def load_results(filename: str) -> dict | None:
    """Load results from JSON file."""
    path = RESULTS_DIR / filename
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


async def run_legacy_pipeline(episodes: list[dict]) -> dict:
    """Run the legacy Graphiti pipeline."""
    print('\n' + '=' * 60)
    print('RUNNING LEGACY GRAPHITI PIPELINE')
    print('=' * 60)

    from graphiti_core.graphiti import Graphiti
    from graphiti_core.driver.falkordb_driver import FalkorDriver
    from graphiti_core.llm_client.openai_client import OpenAIClient
    from graphiti_core.llm_client.config import LLMConfig
    from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig

    # Configure for FalkorDB
    driver = FalkorDriver(
        host='localhost',
        port=6379,
        database='comparison_legacy',
    )

    # Use environment config for LLM
    llm_config = LLMConfig(
        api_key=os.environ.get('CHUTES_API_KEY'),
        base_url=os.environ.get('CHUTES_BASE_URL', 'https://api.z.ai/api/paas/v4'),
        model=os.environ.get('CHUTES_MODEL', 'glm-4-plus'),
    )
    llm_client = OpenAIClient(config=llm_config)

    # Embedder config
    embedder_config = OpenAIEmbedderConfig(
        api_key='ollama',
        base_url=os.environ.get('OLLAMA_EMBEDDING_BASE_URL', 'http://100.81.139.20:11450/v1'),
        embedding_model=os.environ.get('OLLAMA_EMBEDDING_MODEL', 'qwen3-embedding'),
    )
    embedder = OpenAIEmbedder(config=embedder_config)

    graphiti = Graphiti(
        graph_driver=driver,
        llm_client=llm_client,
        embedder=embedder,
    )

    results = {
        'pipeline': 'legacy',
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'episodes': [],
    }

    try:
        # Initialize graph
        await graphiti.build_indices_and_constraints()

        for episode in episodes:
            print(f'\n--- Episode: {episode["id"]} ---')
            print(f'Content: {episode["content"]}')

            start_time = datetime.now(timezone.utc)

            try:
                # Run legacy pipeline
                episode_result = await graphiti.add_episode(
                    name=episode['id'],
                    episode_body=episode['content'],
                    source_description='comparison_test',
                    reference_time=datetime.now(timezone.utc),
                )

                elapsed_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000

                # Extract results
                nodes = []
                edges = []

                # Build node UUID to name mapping
                node_map = {}
                if hasattr(episode_result, 'nodes'):
                    for n in episode_result.nodes:
                        node_map[n.uuid] = n.name
                        labels = n.labels if hasattr(n, 'labels') and n.labels else ['Entity']
                        nodes.append({'name': n.name, 'type': labels[0]})

                if hasattr(episode_result, 'edges'):
                    for e in episode_result.edges:
                        src_name = node_map.get(e.source_node_uuid, e.source_node_uuid)
                        tgt_name = node_map.get(e.target_node_uuid, e.target_node_uuid)
                        edges.append({'source': src_name, 'relation': e.name, 'target': tgt_name})

                results['episodes'].append({
                    'id': episode['id'],
                    'content': episode['content'],
                    'entities': nodes,
                    'edges': edges,
                    'time_ms': elapsed_ms,
                    'success': True,
                })

                print(f'  Entities: {[n["name"] for n in nodes]}')
                print(f'  Edges: {len(edges)}')
                print(f'  Time: {elapsed_ms:.0f}ms')

            except Exception as e:
                elapsed_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
                results['episodes'].append({
                    'id': episode['id'],
                    'content': episode['content'],
                    'entities': [],
                    'edges': [],
                    'time_ms': elapsed_ms,
                    'success': False,
                    'error': str(e),
                })
                print(f'  Error: {e}')

    finally:
        await driver.close()

    return results


def run_dspy_pipeline(episodes: list[dict]) -> dict:
    """Run the DSPy pipeline."""
    print('\n' + '=' * 60)
    print('RUNNING DSPY PIPELINE')
    print('=' * 60)

    from graphiti_core.dspy import DSPyIngestionPipeline, configure_lm

    configure_lm()
    pipeline = DSPyIngestionPipeline(group_id="test", generate_summaries=False)

    results = {
        'pipeline': 'dspy',
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'episodes': [],
    }

    for episode in episodes:
        print(f'\n--- Episode: {episode["id"]} ---')
        print(f'Content: {episode["content"]}')

        try:
            result = pipeline.ingest_episode(
                content=episode['content'],
                episode_id=episode['id'],
            )

            entities = [{'name': e['name'], 'type': e.get('type', 'Entity'), 'is_new': e.get('is_new', True)}
                        for e in result.resolved_entities]

            edges = [{'source': e['source'], 'relation': e['relation_type'], 'target': e['target']}
                     for e in result.extracted_edges]

            results['episodes'].append({
                'id': episode['id'],
                'content': episode['content'],
                'entities': entities,
                'edges': edges,
                'time_ms': result.total_time_ms,
                'timing_breakdown': {
                    'extraction_ms': result.extraction_time_ms,
                    'resolution_ms': result.resolution_time_ms,
                    'edge_ms': result.edge_time_ms,
                },
                'success': result.success,
            })

            new_entities = [e['name'] for e in entities if e.get('is_new')]
            reused_entities = [e['name'] for e in entities if not e.get('is_new')]

            print(f'  New: {new_entities}')
            print(f'  Reused: {reused_entities}')
            print(f'  Edges: {len(edges)}')
            print(f'  Time: {result.total_time_ms:.0f}ms')

        except Exception as e:
            results['episodes'].append({
                'id': episode['id'],
                'content': episode['content'],
                'entities': [],
                'edges': [],
                'time_ms': 0,
                'success': False,
                'error': str(e),
            })
            print(f'  Error: {e}')

    return results


def compare_results(legacy: dict, dspy: dict):
    """Compare and display results from both pipelines."""
    print('\n' + '=' * 60)
    print('COMPARISON RESULTS')
    print('=' * 60)

    legacy_eps = {ep['id']: ep for ep in legacy['episodes']}
    dspy_eps = {ep['id']: ep for ep in dspy['episodes']}

    total_legacy_entities = 0
    total_dspy_entities = 0
    total_legacy_edges = 0
    total_dspy_edges = 0
    total_legacy_time = 0
    total_dspy_time = 0
    entity_overlap = 0

    for ep_id in legacy_eps:
        leg = legacy_eps[ep_id]
        dsp = dspy_eps.get(ep_id, {})

        print(f'\n--- {ep_id} ---')
        print(f'Content: {leg["content"][:60]}...')

        leg_names = set(e['name'].lower() for e in leg.get('entities', []))
        dsp_names = set(e['name'].lower() for e in dsp.get('entities', []))

        overlap = leg_names & dsp_names
        only_legacy = leg_names - dsp_names
        only_dspy = dsp_names - leg_names

        print(f'\nEntities:')
        print(f'  Legacy: {[e["name"] for e in leg.get("entities", [])]}')
        print(f'  DSPy:   {[e["name"] for e in dsp.get("entities", [])]}')
        print(f'  Overlap: {overlap}')
        if only_legacy:
            print(f'  Only Legacy: {only_legacy}')
        if only_dspy:
            print(f'  Only DSPy: {only_dspy}')

        print(f'\nEdges:')
        print(f'  Legacy: {len(leg.get("edges", []))}')
        for e in leg.get('edges', []):
            print(f'    {e["source"]} --[{e["relation"]}]--> {e["target"]}')
        print(f'  DSPy: {len(dsp.get("edges", []))}')
        for e in dsp.get('edges', []):
            print(f'    {e["source"]} --[{e["relation"]}]--> {e["target"]}')

        print(f'\nTiming:')
        print(f'  Legacy: {leg.get("time_ms", 0):.0f}ms')
        print(f'  DSPy:   {dsp.get("time_ms", 0):.0f}ms')

        total_legacy_entities += len(leg.get('entities', []))
        total_dspy_entities += len(dsp.get('entities', []))
        total_legacy_edges += len(leg.get('edges', []))
        total_dspy_edges += len(dsp.get('edges', []))
        total_legacy_time += leg.get('time_ms', 0)
        total_dspy_time += dsp.get('time_ms', 0)
        entity_overlap += len(overlap)

    print('\n' + '=' * 60)
    print('SUMMARY')
    print('=' * 60)
    print(f'\nTotal Entities:')
    print(f'  Legacy: {total_legacy_entities}')
    print(f'  DSPy:   {total_dspy_entities}')
    print(f'  Overlap: {entity_overlap}')

    print(f'\nTotal Edges:')
    print(f'  Legacy: {total_legacy_edges}')
    print(f'  DSPy:   {total_dspy_edges}')

    print(f'\nTotal Time:')
    print(f'  Legacy: {total_legacy_time:.0f}ms')
    print(f'  DSPy:   {total_dspy_time:.0f}ms')

    if total_legacy_time > 0:
        ratio = total_dspy_time / total_legacy_time
        print(f'  Ratio:  {ratio:.2f}x {"(DSPy slower)" if ratio > 1 else "(DSPy faster)"}')


async def main():
    parser = argparse.ArgumentParser(description='Compare Legacy vs DSPy pipelines')
    parser.add_argument('--legacy-only', action='store_true', help='Run only legacy pipeline')
    parser.add_argument('--dspy-only', action='store_true', help='Run only DSPy pipeline')
    parser.add_argument('--compare-only', action='store_true', help='Compare saved results only')
    args = parser.parse_args()

    if args.compare_only:
        legacy = load_results('legacy_results.json')
        dspy = load_results('dspy_results.json')
        if legacy and dspy:
            compare_results(legacy, dspy)
        else:
            print('Missing results files. Run pipelines first.')
        return

    # Check API key
    if not os.environ.get('CHUTES_API_KEY'):
        print('ERROR: CHUTES_API_KEY not set')
        sys.exit(1)

    legacy_results = None
    dspy_results = None

    if not args.dspy_only:
        # Run legacy pipeline
        legacy_results = await run_legacy_pipeline(TEST_EPISODES)
        save_results(legacy_results, 'legacy_results.json')
        print('\n✓ Legacy pipeline complete. Results saved.')

    if not args.legacy_only:
        # Run DSPy pipeline
        dspy_results = run_dspy_pipeline(TEST_EPISODES)
        save_results(dspy_results, 'dspy_results.json')
        print('\n✓ DSPy pipeline complete. Results saved.')

    # Compare if we have both
    if args.legacy_only or args.dspy_only:
        legacy_results = legacy_results or load_results('legacy_results.json')
        dspy_results = dspy_results or load_results('dspy_results.json')

    if legacy_results and dspy_results:
        compare_results(legacy_results, dspy_results)


if __name__ == '__main__':
    asyncio.run(main())
