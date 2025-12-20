#!/usr/bin/env python3
"""
Graph-Aware Retrieval Strategies Test

Tests three graph-aware retrieval approaches:
- Option A: Entity-Centric + Personalized PageRank
- Option B: Two-Stage Community + Local (simulated with clusters)
- Option C: Hybrid Graph + Vector expansion

Compares against baseline vector search.
"""

import time
from dataclasses import dataclass, field
from typing import Optional
import requests
import redis
import numpy as np
from collections import defaultdict

# Configuration
FALKORDB_HOST = 'localhost'
FALKORDB_PORT = 6379
GRAPH_NAME = 'graphiti_migration'
API_URL = 'http://localhost:8003'

# Redis connection for direct graph queries
redis_client = redis.Redis(host=FALKORDB_HOST, port=FALKORDB_PORT, decode_responses=True)


@dataclass
class RetrievalResult:
    """Single retrieval result."""

    uuid: str
    fact: str
    score: float
    source_entity: Optional[str] = None
    target_entity: Optional[str] = None
    method: str = ''


@dataclass
class StrategyResult:
    """Results from a retrieval strategy."""

    strategy: str
    query: str
    results: list[RetrievalResult]
    latency_ms: float
    entities_found: list[str] = field(default_factory=list)


def graph_query(cypher: str) -> list:
    """Execute a Cypher query against FalkorDB."""
    try:
        result = redis_client.execute_command('GRAPH.QUERY', GRAPH_NAME, cypher)
        if result and len(result) > 0:
            if len(result) >= 2 and isinstance(result[1], list):
                return result[1]
        return []
    except Exception as e:
        print(f'Graph query error: {e}')
        return []


def baseline_search(query: str, limit: int = 10) -> StrategyResult:
    """Baseline: Standard API search with cross-encoder."""
    start = time.perf_counter()

    response = requests.post(
        f'{API_URL}/search',
        json={
            'query': query,
            'max_facts': limit,
            'config': {'reranker': 'cross_encoder', 'search_methods': ['fulltext', 'similarity']},
        },
        timeout=60,
    )

    latency = (time.perf_counter() - start) * 1000

    results = []
    if response.status_code == 200:
        data = response.json()
        for fact in data.get('facts', []):
            results.append(
                RetrievalResult(
                    uuid=fact.get('uuid', ''),
                    fact=fact.get('fact', ''),
                    score=fact.get('score') or 0.0,
                    method='baseline',
                )
            )

    return StrategyResult(strategy='baseline', query=query, results=results, latency_ms=latency)


def option_a_entity_ppr(query: str, limit: int = 10) -> StrategyResult:
    """
    Option A: Entity-Centric + Personalized PageRank

    1. Find entities matching the query (by name similarity)
    2. Use pre-computed PageRank to find important connected entities
    3. Collect edges between high-scoring entities
    """
    start = time.perf_counter()
    results = []
    entities_found = []

    # Step 1: Find seed entities by name matching
    query_words = [w for w in query.split() if len(w) > 3]

    seed_entities = []
    for word in query_words[:5]:
        word_escaped = word.replace("'", "\\'")
        cypher = f"""
        MATCH (e:Entity)
        WHERE toLower(e.name) CONTAINS toLower('{word_escaped}')
        RETURN e.uuid as uuid, e.name as name, e.pagerank_centrality as pr
        ORDER BY e.pagerank_centrality DESC
        LIMIT 3
        """
        rows = graph_query(cypher)
        for row in rows:
            if row and len(row) >= 3:
                seed_entities.append(
                    {'uuid': row[0], 'name': row[1], 'pagerank': float(row[2]) if row[2] else 0.0}
                )
                entities_found.append(row[1])

    # Deduplicate
    seen = set()
    seed_entities = [e for e in seed_entities if e['uuid'] not in seen and not seen.add(e['uuid'])]

    if not seed_entities:
        # Fallback: get top entities by pagerank
        cypher = """
        MATCH (e:Entity)
        WHERE e.pagerank_centrality IS NOT NULL
        RETURN e.uuid as uuid, e.name as name, e.pagerank_centrality as pr
        ORDER BY e.pagerank_centrality DESC
        LIMIT 5
        """
        rows = graph_query(cypher)
        for row in rows:
            if row and len(row) >= 3:
                seed_entities.append(
                    {'uuid': row[0], 'name': row[1], 'pagerank': float(row[2]) if row[2] else 0.0}
                )

    # Step 2: Get edges connected to seed entities
    seed_uuids = [e['uuid'] for e in seed_entities[:5]]

    if seed_uuids:
        uuid_list = "', '".join(seed_uuids)
        cypher = f"""
        MATCH (src:Entity)-[r:RELATES_TO]->(tgt:Entity)
        WHERE src.uuid IN ['{uuid_list}'] OR tgt.uuid IN ['{uuid_list}']
        RETURN r.uuid as uuid, r.fact as fact, 
               src.name as src_name, tgt.name as tgt_name,
               COALESCE(src.pagerank_centrality, 0) as src_pr,
               COALESCE(tgt.pagerank_centrality, 0) as tgt_pr
        ORDER BY (COALESCE(src.pagerank_centrality, 0) + COALESCE(tgt.pagerank_centrality, 0)) DESC
        LIMIT {limit * 2}
        """
        rows = graph_query(cypher)

        for row in rows:
            if row and len(row) >= 6 and row[1]:
                src_pr = float(row[4]) if row[4] else 0.0
                tgt_pr = float(row[5]) if row[5] else 0.0
                combined_score = (src_pr + tgt_pr) / 2

                results.append(
                    RetrievalResult(
                        uuid=row[0] or '',
                        fact=row[1] or '',
                        score=combined_score,
                        source_entity=row[2],
                        target_entity=row[3],
                        method='entity_ppr',
                    )
                )

    results.sort(key=lambda x: x.score, reverse=True)
    results = results[:limit]

    latency = (time.perf_counter() - start) * 1000

    return StrategyResult(
        strategy='option_a_entity_ppr',
        query=query,
        results=results,
        latency_ms=latency,
        entities_found=list(set(entities_found))[:10],
    )


def option_b_community_local(query: str, limit: int = 10) -> StrategyResult:
    """
    Option B: Community-Aware Search (using CDLP communities)

    1. Find entities matching query terms (excluding giant community 4)
    2. Get their small/medium communities
    3. Retrieve all facts within those focused communities
    4. Also get cross-community (bridge) facts for context
    """
    start = time.perf_counter()
    results = []
    community_names = []

    # Step 1: Find entities matching query, prefer smaller communities
    query_words = [w for w in query.split() if len(w) > 3]

    matched_communities = {}  # cid -> list of entity names
    for word in query_words[:5]:
        word_escaped = word.replace("'", "\\'")
        cypher = f"""
        MATCH (e:Entity)
        WHERE toLower(e.name) CONTAINS toLower('{word_escaped}')
        AND e.community_id IS NOT NULL
        AND e.community_id <> 4
        RETURN e.community_id as cid, e.name as name, 
               e.pagerank_centrality as pr
        ORDER BY e.pagerank_centrality DESC
        LIMIT 5
        """
        rows = graph_query(cypher)
        for row in rows:
            if row and len(row) >= 2:
                cid = int(row[0])
                if cid not in matched_communities:
                    matched_communities[cid] = []
                matched_communities[cid].append(row[1])
                community_names.append(row[1])

    # Step 2: Get facts from matched communities
    if matched_communities:
        cid_list = ', '.join(str(c) for c in list(matched_communities.keys())[:5])

        cypher = f"""
        MATCH (src:Entity)-[r:RELATES_TO]->(tgt:Entity)
        WHERE src.community_id IN [{cid_list}] 
        AND tgt.community_id IN [{cid_list}]
        RETURN r.uuid as uuid, r.fact as fact,
               src.name as src_name, tgt.name as tgt_name,
               src.community_id as cid,
               COALESCE(src.pagerank_centrality, 0) + COALESCE(tgt.pagerank_centrality, 0) as combined_pr
        ORDER BY combined_pr DESC
        LIMIT {limit}
        """
        rows = graph_query(cypher)

        for row in rows:
            if row and len(row) >= 6 and row[1]:
                results.append(
                    RetrievalResult(
                        uuid=row[0] or '',
                        fact=row[1] or '',
                        score=float(row[5]) if row[5] else 0.5,
                        source_entity=row[2],
                        target_entity=row[3],
                        method=f'community_{row[4]}',
                    )
                )

    # Step 3: Add cross-community facts (bridges) for matched entities
    if community_names and len(results) < limit:
        entity_names = "', '".join([n.replace("'", "\\'") for n in community_names[:5]])
        cypher = f"""
        MATCH (src:Entity)-[r:RELATES_TO]->(tgt:Entity)
        WHERE (src.name IN ['{entity_names}'] OR tgt.name IN ['{entity_names}'])
        AND src.community_id <> tgt.community_id
        RETURN r.uuid as uuid, r.fact as fact,
               src.name as src_name, tgt.name as tgt_name,
               src.betweenness_centrality as bc
        ORDER BY src.betweenness_centrality DESC
        LIMIT {limit - len(results)}
        """
        rows = graph_query(cypher)

        for row in rows:
            if row and len(row) >= 5 and row[1]:
                results.append(
                    RetrievalResult(
                        uuid=row[0] or '',
                        fact=row[1] or '',
                        score=float(row[4]) if row[4] else 0.3,
                        source_entity=row[2],
                        target_entity=row[3],
                        method='cross_community',
                    )
                )

    # Fallback: if no matches, get high-betweenness bridge facts
    if not results:
        cypher = f"""
        MATCH (src:Entity)-[r:RELATES_TO]->(tgt:Entity)
        WHERE src.community_id <> tgt.community_id
        AND src.betweenness_centrality IS NOT NULL
        RETURN r.uuid as uuid, r.fact as fact,
               src.name as src_name, tgt.name as tgt_name,
               src.betweenness_centrality as bc
        ORDER BY src.betweenness_centrality DESC
        LIMIT {limit}
        """
        rows = graph_query(cypher)

        for row in rows:
            if row and len(row) >= 5 and row[1]:
                results.append(
                    RetrievalResult(
                        uuid=row[0] or '',
                        fact=row[1] or '',
                        score=float(row[4]) if row[4] else 0.5,
                        source_entity=row[2],
                        target_entity=row[3],
                        method='community_fallback',
                    )
                )

    latency = (time.perf_counter() - start) * 1000

    return StrategyResult(
        strategy='option_b_community_local',
        query=query,
        results=results[:limit],
        latency_ms=latency,
        entities_found=community_names[:5],
    )


def option_c_hybrid_graph_vector(query: str, limit: int = 10) -> StrategyResult:
    """
    Option C: Hybrid Graph + Vector expansion

    1. Do initial vector search for candidate edges
    2. Get source/target entities from candidates
    3. Expand to 1-hop graph neighborhood
    4. Combine results
    """
    start = time.perf_counter()

    # Step 1: Initial vector search
    response = requests.post(
        f'{API_URL}/search',
        json={
            'query': query,
            'max_facts': limit,
            'config': {'reranker': 'rrf', 'search_methods': ['similarity']},
        },
        timeout=60,
    )

    initial_results = []
    entity_uuids = set()

    if response.status_code == 200:
        data = response.json()
        for fact in data.get('facts', []):
            initial_results.append(
                RetrievalResult(
                    uuid=fact.get('uuid', ''),
                    fact=fact.get('fact', ''),
                    score=1.0,
                    method='vector_initial',
                )
            )

    # Step 2: Get entities from initial results
    if initial_results:
        fact_uuids = [r.uuid for r in initial_results if r.uuid][:10]
        if fact_uuids:
            uuid_list = "', '".join(fact_uuids)
            cypher = f"""
            MATCH (src:Entity)-[r:RELATES_TO]->(tgt:Entity)
            WHERE r.uuid IN ['{uuid_list}']
            RETURN DISTINCT src.uuid, tgt.uuid, src.name, tgt.name
            """
            rows = graph_query(cypher)

            for row in rows:
                if row:
                    if row[0]:
                        entity_uuids.add(row[0])
                    if row[1]:
                        entity_uuids.add(row[1])

    # Step 3: Expand to 1-hop neighborhood
    expanded_results = list(initial_results)

    if entity_uuids:
        initial_uuids = [r.uuid for r in initial_results if r.uuid]
        uuid_list = "', '".join(list(entity_uuids)[:10])
        exclude_list = "', '".join(initial_uuids) if initial_uuids else ''

        cypher = f"""
        MATCH (src:Entity)-[r:RELATES_TO]->(tgt:Entity)
        WHERE (src.uuid IN ['{uuid_list}'] OR tgt.uuid IN ['{uuid_list}'])
        {('AND r.uuid NOT IN ["' + exclude_list + '"]') if exclude_list else ''}
        RETURN r.uuid as uuid, r.fact as fact,
               src.name as src_name, tgt.name as tgt_name,
               COALESCE(src.pagerank_centrality, 0) as pr
        ORDER BY src.pagerank_centrality DESC
        LIMIT {limit}
        """
        rows = graph_query(cypher)

        for row in rows:
            if row and len(row) >= 5 and row[1]:
                expanded_results.append(
                    RetrievalResult(
                        uuid=row[0] or '',
                        fact=row[1] or '',
                        score=0.8,
                        source_entity=row[2],
                        target_entity=row[3],
                        method='graph_expanded',
                    )
                )

    # Deduplicate
    seen = set()
    final_results = []
    for r in expanded_results:
        if r.uuid and r.uuid not in seen:
            seen.add(r.uuid)
            final_results.append(r)

    latency = (time.perf_counter() - start) * 1000

    return StrategyResult(
        strategy='option_c_hybrid_graph_vector',
        query=query,
        results=final_results[:limit],
        latency_ms=latency,
        entities_found=list(entity_uuids)[:10],
    )


def evaluate_results(
    results: list[RetrievalResult], query: str, expected_keywords: list[str]
) -> dict:
    """Evaluate retrieval results."""
    combined_text = ' '.join([r.fact.lower() for r in results])

    hits = sum(1 for kw in expected_keywords if kw.lower() in combined_text)
    coverage = hits / len(expected_keywords) if expected_keywords else 0

    query_words = [w.lower() for w in query.split() if len(w) > 3]
    relevance_hits = sum(1 for w in query_words if w in combined_text)
    relevance = relevance_hits / len(query_words) if query_words else 0

    return {
        'keyword_coverage': coverage,
        'keyword_hits': hits,
        'keyword_total': len(expected_keywords),
        'relevance_score': relevance,
        'result_count': len(results),
    }


def option_e_path_based(query: str, limit: int = 10) -> StrategyResult:
    """
    Option E: Path-Based Retrieval (using Shortest Path algorithm)

    1. Extract entity mentions from query
    2. Find shortest paths between pairs of entities
    3. Collect facts along those paths
    4. Rank by path importance (shorter paths = more relevant)
    """
    start = time.perf_counter()
    results = []
    found_entities = []

    # Step 1: Find entities matching query terms
    query_words = [w for w in query.split() if len(w) > 3]
    matched_entities = []

    for word in query_words[:6]:
        word_escaped = word.replace("'", "\\'")
        cypher = f"""
        MATCH (e:Entity)
        WHERE toLower(e.name) CONTAINS toLower('{word_escaped}')
        RETURN e.uuid, e.name, e.pagerank_centrality
        ORDER BY e.pagerank_centrality DESC
        LIMIT 2
        """
        rows = graph_query(cypher)
        for row in rows:
            if row and len(row) >= 2:
                matched_entities.append({'uuid': row[0], 'name': row[1]})
                found_entities.append(row[1])

    # Deduplicate entities
    seen = set()
    matched_entities = [
        e for e in matched_entities if e['uuid'] not in seen and not seen.add(e['uuid'])
    ]

    # Step 2: Find shortest paths between entity pairs
    path_facts = []

    if len(matched_entities) >= 2:
        # Try paths between first few entity pairs
        for i in range(min(3, len(matched_entities))):
            for j in range(i + 1, min(4, len(matched_entities))):
                src_uuid = matched_entities[i]['uuid']
                tgt_uuid = matched_entities[j]['uuid']

                cypher = f"""
                MATCH (src:Entity {{uuid: '{src_uuid}'}}), (tgt:Entity {{uuid: '{tgt_uuid}'}})
                CALL algo.SPpaths({{
                  sourceNode: src,
                  targetNode: tgt,
                  relTypes: ['RELATES_TO'],
                  relDirection: 'both',
                  maxLen: 4,
                  pathCount: 2
                }})
                YIELD path, pathWeight
                WITH path, pathWeight
                UNWIND relationships(path) as r
                RETURN DISTINCT r.uuid as uuid, r.fact as fact, pathWeight,
                       startNode(r).name as src_name, endNode(r).name as tgt_name
                LIMIT 10
                """
                rows = graph_query(cypher)

                for row in rows:
                    if row and len(row) >= 5 and row[1]:
                        path_weight = int(row[2]) if row[2] else 1
                        # Shorter paths get higher scores
                        score = 1.0 / (path_weight + 1)
                        path_facts.append(
                            RetrievalResult(
                                uuid=row[0] or '',
                                fact=row[1] or '',
                                score=score,
                                source_entity=row[3],
                                target_entity=row[4],
                                method=f'path_len_{path_weight}',
                            )
                        )

    # Step 3: If no paths found, fallback to direct entity connections
    if not path_facts and matched_entities:
        entity_uuids = [e['uuid'] for e in matched_entities[:5]]
        uuid_list = "', '".join(entity_uuids)

        cypher = f"""
        MATCH (src:Entity)-[r:RELATES_TO]->(tgt:Entity)
        WHERE src.uuid IN ['{uuid_list}'] OR tgt.uuid IN ['{uuid_list}']
        RETURN r.uuid, r.fact, src.name, tgt.name, 
               COALESCE(src.pagerank_centrality, 0) as pr
        ORDER BY pr DESC
        LIMIT {limit}
        """
        rows = graph_query(cypher)

        for row in rows:
            if row and len(row) >= 5 and row[1]:
                path_facts.append(
                    RetrievalResult(
                        uuid=row[0] or '',
                        fact=row[1] or '',
                        score=float(row[4]) if row[4] else 0.5,
                        source_entity=row[2],
                        target_entity=row[3],
                        method='direct_connection',
                    )
                )

    # Deduplicate and sort
    seen = set()
    for r in path_facts:
        if r.uuid and r.uuid not in seen:
            seen.add(r.uuid)
            results.append(r)

    results.sort(key=lambda x: x.score, reverse=True)
    results = results[:limit]

    latency = (time.perf_counter() - start) * 1000

    return StrategyResult(
        strategy='option_e_path_based',
        query=query,
        results=results,
        latency_ms=latency,
        entities_found=found_entities[:10],
    )


def option_d_enhanced_hybrid(query: str, limit: int = 10) -> StrategyResult:
    """
    Option D: Enhanced Hybrid (Best of All Worlds)

    Combines:
    1. Vector search for semantic matching (from baseline)
    2. Entity extraction + 1-hop expansion (from Option A/C)
    3. Cross-encoder reranking on combined results
    4. Centrality weighting for importance
    """
    start = time.perf_counter()
    all_candidates = []
    entity_uuids = set()

    # Stage 1: Vector search for initial candidates (over-fetch)
    response = requests.post(
        f'{API_URL}/search',
        json={
            'query': query,
            'max_facts': limit * 3,  # Over-fetch for reranking
            'config': {'reranker': 'rrf', 'search_methods': ['similarity', 'fulltext']},
        },
        timeout=60,
    )

    if response.status_code == 200:
        data = response.json()
        for i, fact in enumerate(data.get('facts', [])):
            all_candidates.append(
                RetrievalResult(
                    uuid=fact.get('uuid', ''),
                    fact=fact.get('fact', ''),
                    score=1.0 - (i * 0.02),  # Decay by rank
                    method='vector',
                )
            )

    # Stage 2: Get entities from vector results
    if all_candidates:
        fact_uuids = [r.uuid for r in all_candidates if r.uuid][:15]
        if fact_uuids:
            uuid_list = "', '".join(fact_uuids)
            cypher = f"""
            MATCH (src:Entity)-[r:RELATES_TO]->(tgt:Entity)
            WHERE r.uuid IN ['{uuid_list}']
            RETURN DISTINCT src.uuid, tgt.uuid, src.name, tgt.name,
                   src.pagerank_centrality as src_pr, tgt.pagerank_centrality as tgt_pr
            """
            rows = graph_query(cypher)

            for row in rows:
                if row:
                    if row[0]:
                        entity_uuids.add(row[0])
                    if row[1]:
                        entity_uuids.add(row[1])

    # Stage 3: Expand to 1-hop from discovered entities
    existing_uuids = set(r.uuid for r in all_candidates if r.uuid)

    if entity_uuids:
        uuid_list = "', '".join(list(entity_uuids)[:10])
        cypher = f"""
        MATCH (src:Entity)-[r:RELATES_TO]->(tgt:Entity)
        WHERE (src.uuid IN ['{uuid_list}'] OR tgt.uuid IN ['{uuid_list}'])
        RETURN r.uuid, r.fact, src.name, tgt.name,
               COALESCE(src.pagerank_centrality, 0) as src_pr,
               COALESCE(tgt.pagerank_centrality, 0) as tgt_pr
        ORDER BY (COALESCE(src.pagerank_centrality, 0) + COALESCE(tgt.pagerank_centrality, 0)) DESC
        LIMIT {limit * 2}
        """
        rows = graph_query(cypher)

        for row in rows:
            if row and len(row) >= 6 and row[1] and row[0] not in existing_uuids:
                combined_pr = (float(row[4]) if row[4] else 0) + (float(row[5]) if row[5] else 0)
                all_candidates.append(
                    RetrievalResult(
                        uuid=row[0] or '',
                        fact=row[1] or '',
                        score=0.7 + (combined_pr * 0.1),  # Base score + centrality boost
                        source_entity=row[2],
                        target_entity=row[3],
                        method='graph_expand',
                    )
                )

    # Stage 4: Deduplicate
    seen = set()
    unique_candidates = []
    for r in all_candidates:
        if r.uuid and r.uuid not in seen:
            seen.add(r.uuid)
            unique_candidates.append(r)

    # Stage 5: Cross-encoder rerank top candidates
    if unique_candidates:
        # Send to API for cross-encoder reranking
        top_facts = [r.fact for r in unique_candidates[: limit * 2]]

        response = requests.post(
            f'{API_URL}/search',
            json={
                'query': query,
                'max_facts': limit,
                'config': {'reranker': 'cross_encoder', 'search_methods': ['similarity']},
            },
            timeout=60,
        )

        if response.status_code == 200:
            data = response.json()
            # Use cross-encoder results but keep graph-expanded ones too
            ce_facts = {f.get('fact', ''): i for i, f in enumerate(data.get('facts', []))}

            # Re-score based on cross-encoder ranking
            for r in unique_candidates:
                if r.fact in ce_facts:
                    r.score = 1.0 - (ce_facts[r.fact] * 0.05)

    # Sort by final score and return top results
    unique_candidates.sort(key=lambda x: x.score, reverse=True)
    final_results = unique_candidates[:limit]

    latency = (time.perf_counter() - start) * 1000

    return StrategyResult(
        strategy='option_d_enhanced_hybrid',
        query=query,
        results=final_results,
        latency_ms=latency,
        entities_found=list(entity_uuids)[:10],
    )


TEST_CASES = [
    {
        'name': 'Sync Service Query',
        'query': 'How does the sync service handle data transfer between FalkorDB and Neo4j?',
        'expected_keywords': ['sync', 'falkordb', 'neo4j', 'transfer', 'data', 'migration'],
    },
    {
        'name': 'Entity Relationship Query',
        'query': 'What is Emmanuel working on with Graphiti?',
        'expected_keywords': ['emmanuel', 'graphiti', 'working', 'opencode', 'project'],
    },
    {
        'name': 'Architecture Query',
        'query': 'What are the main components of the knowledge graph system?',
        'expected_keywords': ['graph', 'entity', 'edge', 'node', 'knowledge', 'component'],
    },
    {
        'name': 'Technical Implementation Query',
        'query': 'How does the reranker improve search results?',
        'expected_keywords': ['rerank', 'search', 'score', 'result', 'cross-encoder', 'relevance'],
    },
    {
        'name': 'Integration Query',
        'query': 'How do Letta agents interact with the knowledge graph?',
        'expected_keywords': ['letta', 'agent', 'graph', 'memory', 'tool', 'mcp'],
    },
]


def main():
    print('=' * 80)
    print('GRAPH-AWARE RETRIEVAL STRATEGIES TEST')
    print('=' * 80)

    strategies = [
        ('Baseline (Cross-Encoder)', baseline_search),
        ('Option A: Entity-Centric + PPR', option_a_entity_ppr),
        ('Option B: Community + Local', option_b_community_local),
        ('Option C: Hybrid Graph + Vector', option_c_hybrid_graph_vector),
        ('Option D: Enhanced Hybrid', option_d_enhanced_hybrid),
        ('Option E: Path-Based', option_e_path_based),
    ]

    all_results = defaultdict(list)

    for test_case in TEST_CASES:
        print(f'\n{"─" * 60}')
        print(f'TEST: {test_case["name"]}')
        print(f'Query: {test_case["query"][:60]}...')
        print(f'{"─" * 60}')

        for strategy_name, strategy_fn in strategies:
            try:
                result = strategy_fn(test_case['query'])
                eval_metrics = evaluate_results(
                    result.results, test_case['query'], test_case['expected_keywords']
                )

                all_results[strategy_name].append(
                    {
                        'test': test_case['name'],
                        'metrics': eval_metrics,
                        'latency': result.latency_ms,
                        'entities': result.entities_found,
                    }
                )

                print(f'\n  {strategy_name}:')
                print(
                    f'    Keywords: {eval_metrics["keyword_hits"]}/{eval_metrics["keyword_total"]} ({eval_metrics["keyword_coverage"] * 100:.1f}%)'
                )
                print(f'    Relevance: {eval_metrics["relevance_score"] * 100:.1f}%')
                print(f'    Latency: {result.latency_ms:.0f}ms')
                if result.results:
                    print(f'    Top: {result.results[0].fact[:65]}...')
                if result.entities_found:
                    print(f'    Entities: {result.entities_found[:3]}')

            except Exception as e:
                print(f'\n  {strategy_name}: ERROR - {e}')
                import traceback

                traceback.print_exc()

    # Summary
    print('\n' + '=' * 80)
    print('SUMMARY')
    print('=' * 80)

    print(f'\n{"Strategy":<40} {"Keywords":<12} {"Relevance":<12} {"Latency":<10}')
    print('-' * 74)

    strategy_summaries = []
    for strategy_name, results in all_results.items():
        if results:
            avg_coverage = np.mean([r['metrics']['keyword_coverage'] for r in results])
            avg_relevance = np.mean([r['metrics']['relevance_score'] for r in results])
            avg_latency = np.mean([r['latency'] for r in results])

            strategy_summaries.append(
                {
                    'name': strategy_name,
                    'coverage': avg_coverage,
                    'relevance': avg_relevance,
                    'latency': avg_latency,
                }
            )

            print(
                f'{strategy_name:<40} {avg_coverage * 100:>9.1f}% {avg_relevance * 100:>9.1f}% {avg_latency:>8.0f}ms'
            )

    print('\n' + '─' * 74)
    print('RANKINGS:')

    by_coverage = sorted(strategy_summaries, key=lambda x: x['coverage'], reverse=True)
    coverage_strs = [
        f'{s["name"].split(":")[0].strip()} ({s["coverage"] * 100:.0f}%)' for s in by_coverage
    ]
    print(f'\nBy Keyword Coverage: {" > ".join(coverage_strs)}')

    by_relevance = sorted(strategy_summaries, key=lambda x: x['relevance'], reverse=True)
    relevance_strs = [
        f'{s["name"].split(":")[0].strip()} ({s["relevance"] * 100:.0f}%)' for s in by_relevance
    ]
    print(f'By Relevance:        {" > ".join(relevance_strs)}')

    by_latency = sorted(strategy_summaries, key=lambda x: x['latency'])
    latency_strs = [f'{s["name"].split(":")[0].strip()} ({s["latency"]:.0f}ms)' for s in by_latency]
    print(f'By Speed:            {" > ".join(latency_strs)}')


if __name__ == '__main__':
    main()
