#!/usr/bin/env python3
"""
Retrieval Strategy Evaluation Test Harness

Tests different reranking strategies and search configurations
to find optimal settings for retrieval quality.
"""

import asyncio
import httpx
import json
import time
from dataclasses import dataclass, field
from typing import Optional
from collections import defaultdict

# Configuration
API_URL = 'http://localhost:8003'
RUST_URL = 'http://localhost:3004'

# Test queries with expected keywords/concepts that should appear in good results
TEST_CASES = [
    {
        'name': 'Person Query - Emmanuel',
        'query': 'What does Emmanuel work on?',
        'expected_keywords': ['emmanuel', 'opencode', 'graphiti', 'project', 'work'],
        'query_type': 'person',
    },
    {
        'name': 'Project Query - Graphiti',
        'query': 'Tell me about the Graphiti knowledge graph project',
        'expected_keywords': ['graphiti', 'knowledge', 'graph', 'neo4j', 'falkordb', 'memory'],
        'query_type': 'project',
    },
    {
        'name': 'Technical Query - Sync Service',
        'query': 'How does the Rust sync service work?',
        'expected_keywords': ['rust', 'sync', 'neo4j', 'falkordb', 'service'],
        'query_type': 'technical',
    },
    {
        'name': 'Concept Query - Memory',
        'query': 'How are memories stored and retrieved?',
        'expected_keywords': ['memory', 'store', 'retrieve', 'episode', 'node', 'edge'],
        'query_type': 'concept',
    },
    {
        'name': 'Relationship Query',
        'query': "What are Emmanuel's preferences and interests?",
        'expected_keywords': ['emmanuel', 'prefer', 'interest', 'like'],
        'query_type': 'relationship',
    },
    {
        'name': 'Recent Activity Query',
        'query': 'What was recently discussed about the frontend?',
        'expected_keywords': ['frontend', 'react', 'visualizer', 'graph', 'ui'],
        'query_type': 'recent',
    },
]

# Strategies to test
STRATEGIES = [
    {
        'name': 'baseline_rrf',
        'description': 'Baseline: RRF with fulltext+similarity',
        'config': {
            'reranker': 'rrf',
            'search_methods': ['fulltext', 'similarity'],
            'bfs_max_depth': 2,
            'sim_min_score': 0.3,
            'mmr_lambda': 0.5,
        },
    },
    {
        'name': 'cross_encoder',
        'description': 'Cross-encoder reranking (vLLM)',
        'config': {
            'reranker': 'cross_encoder',
            'search_methods': ['fulltext', 'similarity'],
            'bfs_max_depth': 2,
            'sim_min_score': 0.3,
            'mmr_lambda': 0.5,
        },
    },
    {
        'name': 'cross_encoder_low_threshold',
        'description': 'Cross-encoder with lower similarity threshold',
        'config': {
            'reranker': 'cross_encoder',
            'search_methods': ['fulltext', 'similarity'],
            'bfs_max_depth': 2,
            'sim_min_score': 0.2,
            'mmr_lambda': 0.5,
        },
    },
    {
        'name': 'mmr_diverse',
        'description': 'MMR for diversity (lambda=0.3)',
        'config': {
            'reranker': 'mmr',
            'search_methods': ['fulltext', 'similarity'],
            'bfs_max_depth': 2,
            'sim_min_score': 0.3,
            'mmr_lambda': 0.3,
        },
    },
    {
        'name': 'mmr_relevant',
        'description': 'MMR favoring relevance (lambda=0.7)',
        'config': {
            'reranker': 'mmr',
            'search_methods': ['fulltext', 'similarity'],
            'bfs_max_depth': 2,
            'sim_min_score': 0.3,
            'mmr_lambda': 0.7,
        },
    },
    {
        'name': 'centrality_boosted',
        'description': 'Centrality-boosted (factor=2.0)',
        'config': {
            'reranker': 'centrality_boosted',
            'search_methods': ['fulltext', 'similarity'],
            'bfs_max_depth': 2,
            'sim_min_score': 0.3,
            'mmr_lambda': 0.5,
            'centrality_boost_factor': 2.0,
        },
    },
    {
        'name': 'centrality_high_boost',
        'description': 'Centrality-boosted (factor=3.0)',
        'config': {
            'reranker': 'centrality_boosted',
            'search_methods': ['fulltext', 'similarity'],
            'bfs_max_depth': 2,
            'sim_min_score': 0.3,
            'mmr_lambda': 0.5,
            'centrality_boost_factor': 3.0,
        },
    },
    {
        'name': 'similarity_only',
        'description': 'Pure semantic search (no fulltext)',
        'config': {
            'reranker': 'rrf',
            'search_methods': ['similarity'],
            'bfs_max_depth': 2,
            'sim_min_score': 0.4,
            'mmr_lambda': 0.5,
        },
    },
    {
        'name': 'fulltext_only',
        'description': 'Pure fulltext search (no semantic)',
        'config': {
            'reranker': 'rrf',
            'search_methods': ['fulltext'],
            'bfs_max_depth': 2,
            'sim_min_score': 0.3,
            'mmr_lambda': 0.5,
        },
    },
    {
        'name': 'with_bfs',
        'description': 'Include BFS graph traversal',
        'config': {
            'reranker': 'rrf',
            'search_methods': ['fulltext', 'similarity', 'bfs'],
            'bfs_max_depth': 3,
            'sim_min_score': 0.3,
            'mmr_lambda': 0.5,
        },
    },
    {
        'name': 'cross_encoder_with_bfs',
        'description': 'Cross-encoder + BFS traversal',
        'config': {
            'reranker': 'cross_encoder',
            'search_methods': ['fulltext', 'similarity', 'bfs'],
            'bfs_max_depth': 3,
            'sim_min_score': 0.25,
            'mmr_lambda': 0.5,
        },
    },
]


@dataclass
class SearchResult:
    """Individual search result."""

    uuid: str
    fact: str
    score: Optional[float] = None
    name: str = ''


@dataclass
class TestResult:
    """Result of a single test case with a strategy."""

    query_name: str
    strategy_name: str
    latency_ms: float
    num_results: int
    keyword_hits: int
    keyword_total: int
    keyword_score: float  # hits / total
    top_facts: list[str] = field(default_factory=list)
    error: Optional[str] = None


async def search_facts(
    client: httpx.AsyncClient, query: str, config: dict, max_facts: int = 10
) -> tuple[list[SearchResult], float]:
    """Execute a search query and return results with latency."""
    payload = {'query': query, 'max_facts': max_facts, 'config': config}

    start = time.perf_counter()
    try:
        response = await client.post(f'{API_URL}/search', json=payload, timeout=60.0)
        latency = (time.perf_counter() - start) * 1000

        if response.status_code != 200:
            return [], latency

        data = response.json()
        results = []
        for fact in data.get('facts', []):
            results.append(
                SearchResult(
                    uuid=fact.get('uuid', ''),
                    fact=fact.get('fact', ''),
                    score=fact.get('score'),
                    name=fact.get('name', ''),
                )
            )
        return results, latency
    except Exception as e:
        latency = (time.perf_counter() - start) * 1000
        print(f'  Error: {e}')
        return [], latency


def calculate_keyword_score(
    results: list[SearchResult], expected_keywords: list[str]
) -> tuple[int, int]:
    """Calculate how many expected keywords appear in results."""
    # Combine all result text
    combined_text = ' '.join([r.fact.lower() for r in results])

    hits = 0
    for keyword in expected_keywords:
        if keyword.lower() in combined_text:
            hits += 1

    return hits, len(expected_keywords)


async def run_test_case(client: httpx.AsyncClient, test_case: dict, strategy: dict) -> TestResult:
    """Run a single test case with a specific strategy."""
    results, latency = await search_facts(
        client, test_case['query'], strategy['config'], max_facts=10
    )

    if not results:
        return TestResult(
            query_name=test_case['name'],
            strategy_name=strategy['name'],
            latency_ms=latency,
            num_results=0,
            keyword_hits=0,
            keyword_total=len(test_case['expected_keywords']),
            keyword_score=0.0,
            error='No results returned',
        )

    hits, total = calculate_keyword_score(results, test_case['expected_keywords'])

    return TestResult(
        query_name=test_case['name'],
        strategy_name=strategy['name'],
        latency_ms=latency,
        num_results=len(results),
        keyword_hits=hits,
        keyword_total=total,
        keyword_score=hits / total if total > 0 else 0.0,
        top_facts=[r.fact[:100] for r in results[:3]],
    )


async def run_all_tests():
    """Run all test cases across all strategies."""
    print('=' * 80)
    print('RETRIEVAL STRATEGY EVALUATION')
    print('=' * 80)
    print(f'\nTest Cases: {len(TEST_CASES)}')
    print(f'Strategies: {len(STRATEGIES)}')
    print(f'Total Tests: {len(TEST_CASES) * len(STRATEGIES)}')
    print()

    all_results: list[TestResult] = []

    async with httpx.AsyncClient() as client:
        # Verify API is up
        try:
            health = await client.get(f'{API_URL}/healthcheck', timeout=5.0)
            print(f'API Health: {health.status_code}')
        except Exception as e:
            print(f'API not available: {e}')
            return

        for strategy in STRATEGIES:
            print(f'\n{"─" * 60}')
            print(f'Strategy: {strategy["name"]}')
            print(f'Description: {strategy["description"]}')
            print(f'{"─" * 60}')

            for test_case in TEST_CASES:
                print(f'  Testing: {test_case["name"]}...', end=' ', flush=True)
                result = await run_test_case(client, test_case, strategy)
                all_results.append(result)

                if result.error:
                    print(f'ERROR - {result.error}')
                else:
                    print(
                        f'OK - {result.keyword_hits}/{result.keyword_total} keywords, {result.latency_ms:.0f}ms'
                    )

    return all_results


def analyze_results(results: list[TestResult]):
    """Analyze and present results."""
    print('\n' + '=' * 80)
    print('RESULTS ANALYSIS')
    print('=' * 80)

    # Group by strategy
    by_strategy = defaultdict(list)
    for r in results:
        by_strategy[r.strategy_name].append(r)

    # Calculate aggregate metrics per strategy
    strategy_metrics = []
    for strategy_name, strategy_results in by_strategy.items():
        valid_results = [r for r in strategy_results if not r.error]
        if not valid_results:
            continue

        avg_keyword_score = sum(r.keyword_score for r in valid_results) / len(valid_results)
        avg_latency = sum(r.latency_ms for r in valid_results) / len(valid_results)
        avg_results = sum(r.num_results for r in valid_results) / len(valid_results)
        total_hits = sum(r.keyword_hits for r in valid_results)
        total_possible = sum(r.keyword_total for r in valid_results)

        strategy_metrics.append(
            {
                'name': strategy_name,
                'avg_keyword_score': avg_keyword_score,
                'total_keyword_score': total_hits / total_possible if total_possible > 0 else 0,
                'avg_latency_ms': avg_latency,
                'avg_results': avg_results,
                'total_hits': total_hits,
                'total_possible': total_possible,
            }
        )

    # Sort by keyword score (descending)
    strategy_metrics.sort(key=lambda x: x['total_keyword_score'], reverse=True)

    # Print ranking table
    print('\n### STRATEGY RANKING (by keyword coverage) ###\n')
    print(f'{"Rank":<5} {"Strategy":<30} {"Score":>8} {"Hits":>8} {"Latency":>10} {"Results":>8}')
    print('-' * 75)

    for i, m in enumerate(strategy_metrics, 1):
        print(
            f'{i:<5} {m["name"]:<30} {m["total_keyword_score"] * 100:>7.1f}% {m["total_hits"]:>4}/{m["total_possible"]:<3} {m["avg_latency_ms"]:>8.0f}ms {m["avg_results"]:>7.1f}'
        )

    # Print per-query breakdown for top 3 strategies
    print('\n\n### TOP 3 STRATEGIES - DETAILED BREAKDOWN ###')

    top_strategies = [m['name'] for m in strategy_metrics[:3]]

    for strategy_name in top_strategies:
        strategy_results = by_strategy[strategy_name]
        print(f'\n{"─" * 60}')
        print(f'Strategy: {strategy_name}')
        print(f'{"─" * 60}')

        for r in strategy_results:
            status = '✓' if r.keyword_score >= 0.5 else '✗'
            print(
                f'  {status} {r.query_name}: {r.keyword_hits}/{r.keyword_total} ({r.keyword_score * 100:.0f}%) - {r.latency_ms:.0f}ms'
            )
            if r.top_facts:
                print(f'      Top result: {r.top_facts[0][:80]}...')

    # Print latency comparison
    print('\n\n### LATENCY COMPARISON ###\n')
    latency_sorted = sorted(strategy_metrics, key=lambda x: x['avg_latency_ms'])

    print(f'{"Strategy":<30} {"Avg Latency":>12} {"Quality Score":>14}')
    print('-' * 58)
    for m in latency_sorted:
        print(
            f'{m["name"]:<30} {m["avg_latency_ms"]:>10.0f}ms {m["total_keyword_score"] * 100:>12.1f}%'
        )

    # Quality vs Latency tradeoff
    print('\n\n### QUALITY vs LATENCY TRADEOFF ###\n')
    print('(Higher quality score is better, lower latency is better)\n')

    # Find pareto-optimal strategies
    pareto_optimal = []
    for m in strategy_metrics:
        is_dominated = False
        for other in strategy_metrics:
            if other['name'] == m['name']:
                continue
            # Check if 'other' dominates 'm' (better in both metrics)
            if (
                other['total_keyword_score'] >= m['total_keyword_score']
                and other['avg_latency_ms'] <= m['avg_latency_ms']
                and (
                    other['total_keyword_score'] > m['total_keyword_score']
                    or other['avg_latency_ms'] < m['avg_latency_ms']
                )
            ):
                is_dominated = True
                break
        if not is_dominated:
            pareto_optimal.append(m['name'])

    print('Pareto-optimal strategies (best tradeoff):')
    for name in pareto_optimal:
        m = next(x for x in strategy_metrics if x['name'] == name)
        print(
            f'  • {name}: {m["total_keyword_score"] * 100:.1f}% quality, {m["avg_latency_ms"]:.0f}ms latency'
        )

    # Recommendations
    print('\n\n### RECOMMENDATIONS ###\n')

    best_quality = strategy_metrics[0]
    fastest = min(strategy_metrics, key=lambda x: x['avg_latency_ms'])

    print(f'Best Quality: {best_quality["name"]}')
    print(
        f'  → {best_quality["total_keyword_score"] * 100:.1f}% keyword coverage, {best_quality["avg_latency_ms"]:.0f}ms avg latency'
    )

    print(f'\nFastest: {fastest["name"]}')
    print(
        f'  → {fastest["avg_latency_ms"]:.0f}ms avg latency, {fastest["total_keyword_score"] * 100:.1f}% keyword coverage'
    )

    # Best balanced (if different from above)
    if pareto_optimal:
        balanced = next(
            (
                m
                for m in strategy_metrics
                if m['name'] in pareto_optimal
                and m['name'] != best_quality['name']
                and m['name'] != fastest['name']
            ),
            None,
        )
        if balanced:
            print(f'\nBest Balanced: {balanced["name"]}')
            print(
                f'  → {balanced["total_keyword_score"] * 100:.1f}% quality, {balanced["avg_latency_ms"]:.0f}ms latency'
            )

    return strategy_metrics


async def main():
    results = await run_all_tests()
    if results:
        analyze_results(results)


if __name__ == '__main__':
    asyncio.run(main())
