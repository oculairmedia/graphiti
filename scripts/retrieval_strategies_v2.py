#!/usr/bin/env python3
"""
Retrieval Strategies V2 - Refined Graph-Aware Retrieval

Implements the refined strategies from brainstorming:
1. Tri-bucket retrieval (Facts + Entities + Episodes)
2. Entity-seeded with score propagation
3. Fact-first for relationship queries
4. MMR diversity enforcement
5. Lexical rescue for exact matches
6. Query intent classification

Key insight: No embeddings for Episodic.content or most Entity.name,
so we use external vector search + graph expansion.
"""

import re
import time
import json
import hashlib
from dataclasses import dataclass, field
from typing import Optional, Literal
from enum import Enum
from collections import defaultdict

import requests
import redis
import numpy as np

# Configuration
FALKORDB_HOST = 'localhost'
FALKORDB_PORT = 6379
GRAPH_NAME = 'graphiti_migration'
API_URL = 'http://localhost:8003'
RERANKER_URL = 'http://100.81.139.20:11435'

# Redis connection
redis_client = redis.Redis(host=FALKORDB_HOST, port=FALKORDB_PORT, decode_responses=True)


class QueryIntent(Enum):
    """Detected query intent affects retrieval strategy."""

    FACTUAL = 'factual'  # "What is X?" - entity summaries + facts
    RELATIONSHIP = 'relationship'  # "How does X relate to Y?" - paths + facts
    TEMPORAL = 'temporal'  # "When did X happen?" - episodes + timestamps
    PROCEDURAL = 'procedural'  # "How to do X?" - episodes + facts
    EXPLORATORY = 'exploratory'  # "Tell me about X" - mix of all


class ResultType(Enum):
    """Type of retrieval result for quota enforcement."""

    FACT = 'fact'  # RELATES_TO.fact
    ENTITY = 'entity'  # Entity.name + summary
    EPISODE = 'episode'  # Episodic.content


@dataclass
class RetrievalItem:
    """A single retrieval item (can be fact, entity, or episode)."""

    uuid: str
    text: str
    score: float
    result_type: ResultType
    source_entity: Optional[str] = None
    target_entity: Optional[str] = None
    method: str = ''
    metadata: dict = field(default_factory=dict)

    def __hash__(self):
        return hash(self.uuid)

    def __eq__(self, other):
        return self.uuid == other.uuid


@dataclass
class StrategyResult:
    """Results from a retrieval strategy."""

    strategy: str
    query: str
    intent: QueryIntent
    results: list[RetrievalItem]
    latency_ms: float
    breakdown: dict = field(default_factory=dict)


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


# =============================================================================
# Query Understanding
# =============================================================================


def classify_intent(query: str) -> QueryIntent:
    """
    Classify query intent to determine retrieval strategy weights.

    Rules:
    - "how/why/what connects/relationship" -> RELATIONSHIP
    - "when/timeline/history" -> TEMPORAL
    - "how to/steps/procedure" -> PROCEDURAL
    - "what is/define/explain" -> FACTUAL
    - default -> EXPLORATORY
    """
    q = query.lower()

    # Relationship patterns
    if any(
        p in q
        for p in [
            'how does',
            'why does',
            'relationship',
            'connect',
            'relate',
            'between',
            'interact',
            'depend',
        ]
    ):
        return QueryIntent.RELATIONSHIP

    # Temporal patterns
    if any(
        p in q for p in ['when', 'timeline', 'history', 'before', 'after', 'sequence', 'order of']
    ):
        return QueryIntent.TEMPORAL

    # Procedural patterns
    if any(
        p in q
        for p in [
            'how to',
            'steps',
            'procedure',
            'process',
            'implement',
            'configure',
            'set up',
            'fix',
        ]
    ):
        return QueryIntent.PROCEDURAL

    # Factual patterns
    if any(
        p in q for p in ['what is', 'define', 'explain', 'describe', 'meaning of', 'purpose of']
    ):
        return QueryIntent.FACTUAL

    return QueryIntent.EXPLORATORY


def extract_entities_from_query(query: str) -> list[dict]:
    """
    Extract potential entity mentions from query.
    Returns list of {name, confidence} dicts.

    Uses:
    - Capitalized words
    - Technical terms (camelCase, snake_case, kebab-case)
    - Quoted strings
    - Known patterns (file paths, UUIDs)
    """
    entities = []

    # Quoted strings (high confidence)
    quoted = re.findall(r'"([^"]+)"|\'([^\']+)\'', query)
    for match in quoted:
        name = match[0] or match[1]
        entities.append({'name': name, 'confidence': 0.95})

    # File paths
    paths = re.findall(r'[/\w-]+\.[a-z]{2,4}|/opt/[^\s]+', query)
    for path in paths:
        entities.append({'name': path, 'confidence': 0.9})

    # Technical terms (camelCase, PascalCase)
    camel = re.findall(r'\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b', query)
    for term in camel:
        entities.append({'name': term, 'confidence': 0.8})

    # snake_case and kebab-case
    snake = re.findall(r'\b[a-z]+(?:[-_][a-z]+)+\b', query)
    for term in snake:
        entities.append({'name': term, 'confidence': 0.75})

    # Capitalized words (medium confidence, filter common words)
    common_words = {
        'how',
        'what',
        'when',
        'where',
        'why',
        'the',
        'is',
        'are',
        'does',
        'do',
        'can',
        'could',
        'would',
        'should',
        'with',
    }
    caps = re.findall(r'\b[A-Z][a-z]{2,}\b', query)
    for word in caps:
        if word.lower() not in common_words:
            entities.append({'name': word, 'confidence': 0.6})

    # Deduplicate, keeping highest confidence
    seen = {}
    for e in entities:
        name_lower = e['name'].lower()
        if name_lower not in seen or seen[name_lower]['confidence'] < e['confidence']:
            seen[name_lower] = e

    return sorted(seen.values(), key=lambda x: x['confidence'], reverse=True)


def generate_query_rewrites(query: str, intent: QueryIntent) -> list[str]:
    """
    Generate query rewrites for multi-query retrieval.
    Returns original + 2-3 variants.
    """
    rewrites = [query]

    # Extract key terms
    words = [w for w in query.split() if len(w) > 3]

    # Keyword list version
    keywords = ' '.join(words[:6])
    if keywords != query:
        rewrites.append(keywords)

    # Intent-specific rewrites
    if intent == QueryIntent.RELATIONSHIP:
        # Add "connection" framing
        entities = extract_entities_from_query(query)
        if len(entities) >= 2:
            rewrites.append(f'{entities[0]["name"]} {entities[1]["name"]} connection relationship')

    elif intent == QueryIntent.PROCEDURAL:
        # Add action words
        rewrites.append(f'steps to {" ".join(words[:4])}')

    return rewrites[:4]  # Max 4 rewrites


# =============================================================================
# Core Retrieval Functions
# =============================================================================


def vector_search(query: str, limit: int = 20, use_reranker: bool = False) -> list[RetrievalItem]:
    """
    Initial vector search via Python API.
    Returns RELATES_TO facts.
    """
    config = {
        'reranker': 'cross_encoder' if use_reranker else 'rrf',
        'search_methods': ['similarity'],
    }

    try:
        response = requests.post(
            f'{API_URL}/search',
            json={'query': query, 'max_facts': limit, 'config': config},
            timeout=60,
        )

        results = []
        if response.status_code == 200:
            data = response.json()
            for i, fact in enumerate(data.get('facts', [])):
                results.append(
                    RetrievalItem(
                        uuid=fact.get('uuid', ''),
                        text=fact.get('fact', ''),
                        score=1.0 - (i * 0.02),  # Rank-based score
                        result_type=ResultType.FACT,
                        method='vector_search',
                    )
                )
        return results
    except Exception as e:
        print(f'Vector search error: {e}')
        return []


def resolve_entities(names: list[str], limit_per_name: int = 3) -> list[dict]:
    """
    Resolve entity names to UUIDs via FalkorDB.
    Returns list of {uuid, name, pagerank, community_id}.
    """
    entities = []
    seen = set()

    for name in names[:10]:
        name_escaped = name.replace("'", "\\'").replace('\\', '\\\\')
        cypher = f"""
        MATCH (e:Entity)
        WHERE toLower(e.name) CONTAINS toLower('{name_escaped}')
        RETURN e.uuid, e.name, e.pagerank_centrality, e.community_id, e.summary
        ORDER BY e.pagerank_centrality DESC
        LIMIT {limit_per_name}
        """
        rows = graph_query(cypher)

        for row in rows:
            if row and len(row) >= 4 and row[0] not in seen:
                seen.add(row[0])
                entities.append(
                    {
                        'uuid': row[0],
                        'name': row[1],
                        'pagerank': float(row[2]) if row[2] else 0.0,
                        'community_id': row[3],
                        'summary': row[4] if len(row) > 4 else '',
                    }
                )

    return entities


def get_facts_for_entities(entity_uuids: list[str], limit: int = 30) -> list[RetrievalItem]:
    """
    Get RELATES_TO facts connected to given entities.
    """
    if not entity_uuids:
        return []

    uuid_list = "', '".join(entity_uuids[:15])
    cypher = f"""
    MATCH (src:Entity)-[r:RELATES_TO]->(tgt:Entity)
    WHERE src.uuid IN ['{uuid_list}'] OR tgt.uuid IN ['{uuid_list}']
    RETURN r.uuid, r.fact, src.name, tgt.name,
           COALESCE(src.pagerank_centrality, 0) as src_pr,
           COALESCE(tgt.pagerank_centrality, 0) as tgt_pr
    ORDER BY (src_pr + tgt_pr) DESC
    LIMIT {limit}
    """
    rows = graph_query(cypher)

    results = []
    for row in rows:
        if row and len(row) >= 6 and row[1]:
            combined_pr = (float(row[4]) if row[4] else 0) + (float(row[5]) if row[5] else 0)
            results.append(
                RetrievalItem(
                    uuid=row[0],
                    text=row[1],
                    score=0.5 + (combined_pr * 0.5),  # Normalize to 0.5-1.0
                    result_type=ResultType.FACT,
                    source_entity=row[2],
                    target_entity=row[3],
                    method='entity_facts',
                )
            )

    return results


def get_episodes_for_entities(entity_uuids: list[str], limit: int = 20) -> list[RetrievalItem]:
    """
    Get Episodic nodes that MENTION the given entities.
    """
    if not entity_uuids:
        return []

    uuid_list = "', '".join(entity_uuids[:10])
    cypher = f"""
    MATCH (ep:Episodic)-[:MENTIONS]->(e:Entity)
    WHERE e.uuid IN ['{uuid_list}']
    WITH ep, count(e) as mention_count, collect(e.name) as mentioned_entities
    ORDER BY mention_count DESC, ep.created_at DESC
    LIMIT {limit}
    RETURN ep.uuid, substring(ep.content, 0, 500), ep.source, 
           ep.valid_at, mention_count, mentioned_entities
    """
    rows = graph_query(cypher)

    results = []
    for row in rows:
        if row and len(row) >= 5 and row[1]:
            mention_count = int(row[4]) if row[4] else 1
            results.append(
                RetrievalItem(
                    uuid=row[0],
                    text=row[1],
                    score=0.4 + (min(mention_count, 5) * 0.1),  # 0.4-0.9 based on mentions
                    result_type=ResultType.EPISODE,
                    method='entity_episodes',
                    metadata={
                        'source': row[2],
                        'valid_at': str(row[3]) if row[3] else None,
                        'mention_count': mention_count,
                        'mentioned_entities': row[5] if len(row) > 5 else [],
                    },
                )
            )

    return results


def lexical_search_facts(keywords: list[str], limit: int = 15) -> list[RetrievalItem]:
    """
    Lexical search on RELATES_TO.fact for exact keyword matches.
    Good for: file paths, error codes, UUIDs, technical terms.
    """
    if not keywords:
        return []

    results = []
    seen = set()

    for kw in keywords[:5]:
        kw_escaped = kw.replace("'", "\\'").replace('\\', '\\\\')
        cypher = f"""
        MATCH (src:Entity)-[r:RELATES_TO]->(tgt:Entity)
        WHERE toLower(r.fact) CONTAINS toLower('{kw_escaped}')
        RETURN r.uuid, r.fact, src.name, tgt.name
        LIMIT {limit // len(keywords[:5]) + 1}
        """
        rows = graph_query(cypher)

        for row in rows:
            if row and len(row) >= 4 and row[0] not in seen and row[1]:
                seen.add(row[0])
                results.append(
                    RetrievalItem(
                        uuid=row[0],
                        text=row[1],
                        score=0.8,  # High score for exact matches
                        result_type=ResultType.FACT,
                        source_entity=row[2],
                        target_entity=row[3],
                        method='lexical_search',
                    )
                )

    return results[:limit]


def lexical_search_episodes(keywords: list[str], limit: int = 10) -> list[RetrievalItem]:
    """
    Lexical search on Episodic.content for exact keyword matches.
    """
    if not keywords:
        return []

    results = []
    seen = set()

    for kw in keywords[:3]:
        kw_escaped = kw.replace("'", "\\'").replace('\\', '\\\\')
        cypher = f"""
        MATCH (ep:Episodic)
        WHERE toLower(ep.content) CONTAINS toLower('{kw_escaped}')
        RETURN ep.uuid, substring(ep.content, 0, 500), ep.source, ep.valid_at
        ORDER BY ep.created_at DESC
        LIMIT {limit // len(keywords[:3]) + 1}
        """
        rows = graph_query(cypher)

        for row in rows:
            if row and len(row) >= 3 and row[0] not in seen and row[1]:
                seen.add(row[0])
                results.append(
                    RetrievalItem(
                        uuid=row[0],
                        text=row[1],
                        score=0.7,
                        result_type=ResultType.EPISODE,
                        method='lexical_episode',
                        metadata={'source': row[2], 'valid_at': str(row[3]) if row[3] else None},
                    )
                )

    return results[:limit]


# =============================================================================
# MMR Diversity
# =============================================================================


def simple_text_similarity(text1: str, text2: str) -> float:
    """
    Simple Jaccard similarity on word sets.
    """
    words1 = set(text1.lower().split())
    words2 = set(text2.lower().split())

    if not words1 or not words2:
        return 0.0

    intersection = len(words1 & words2)
    union = len(words1 | words2)

    return intersection / union if union > 0 else 0.0


def mmr_rerank(
    results: list[RetrievalItem], lambda_param: float = 0.7, limit: int = 20
) -> list[RetrievalItem]:
    """
    Maximal Marginal Relevance reranking for diversity.

    MMR = lambda * relevance - (1 - lambda) * max_similarity_to_selected

    Args:
        results: Items to rerank (must have .score for relevance)
        lambda_param: Balance between relevance (1.0) and diversity (0.0)
        limit: Number of results to return
    """
    if len(results) <= limit:
        return results

    selected = []
    candidates = list(results)

    while len(selected) < limit and candidates:
        best_idx = -1
        best_mmr = float('-inf')

        for i, candidate in enumerate(candidates):
            # Relevance component
            relevance = candidate.score

            # Diversity component: max similarity to any selected item
            max_sim = 0.0
            for s in selected:
                sim = simple_text_similarity(candidate.text, s.text)
                max_sim = max(max_sim, sim)

            # MMR score
            mmr = lambda_param * relevance - (1 - lambda_param) * max_sim

            if mmr > best_mmr:
                best_mmr = mmr
                best_idx = i

        if best_idx >= 0:
            selected.append(candidates.pop(best_idx))
        else:
            break

    return selected


# =============================================================================
# Score Propagation
# =============================================================================


def propagate_scores(
    seed_items: list[RetrievalItem], hop_decay: float = 0.6, max_hops: int = 1
) -> list[RetrievalItem]:
    """
    Propagate scores from seed items to neighbors via graph edges.

    Seed items (from vector search) have high scores.
    Neighbors get decayed scores based on:
    - Distance (hop count)
    - Seed score
    - Edge weight (centrality of endpoints)
    """
    if not seed_items:
        return []

    # Get entity UUIDs from seed facts
    seed_fact_uuids = [item.uuid for item in seed_items if item.result_type == ResultType.FACT]

    if not seed_fact_uuids:
        return []

    uuid_list = "', '".join(seed_fact_uuids[:20])

    # Get entities involved in seed facts
    cypher = f"""
    MATCH (src:Entity)-[r:RELATES_TO]->(tgt:Entity)
    WHERE r.uuid IN ['{uuid_list}']
    RETURN DISTINCT src.uuid, src.pagerank_centrality,
                    tgt.uuid, tgt.pagerank_centrality
    """
    rows = graph_query(cypher)

    # Build score map for seed entities
    entity_scores = {}
    for row in rows:
        if row and len(row) >= 4:
            src_uuid, src_pr, tgt_uuid, tgt_pr = row
            if src_uuid:
                entity_scores[src_uuid] = max(
                    entity_scores.get(src_uuid, 0), float(src_pr) if src_pr else 0.1
                )
            if tgt_uuid:
                entity_scores[tgt_uuid] = max(
                    entity_scores.get(tgt_uuid, 0), float(tgt_pr) if tgt_pr else 0.1
                )

    if not entity_scores:
        return []

    # Get 1-hop neighbors
    entity_uuids = list(entity_scores.keys())[:15]
    uuid_list = "', '".join(entity_uuids)
    seed_fact_set = set(seed_fact_uuids)

    cypher = f"""
    MATCH (src:Entity)-[r:RELATES_TO]->(tgt:Entity)
    WHERE (src.uuid IN ['{uuid_list}'] OR tgt.uuid IN ['{uuid_list}'])
    RETURN r.uuid, r.fact, src.uuid, src.name, tgt.uuid, tgt.name,
           COALESCE(src.pagerank_centrality, 0),
           COALESCE(tgt.pagerank_centrality, 0)
    LIMIT 50
    """
    rows = graph_query(cypher)

    propagated = []
    for row in rows:
        if row and len(row) >= 8 and row[1]:
            r_uuid = row[0]
            if r_uuid in seed_fact_set:
                continue  # Skip seeds

            fact = row[1]
            src_uuid, src_name = row[2], row[3]
            tgt_uuid, tgt_name = row[4], row[5]
            src_pr = float(row[6]) if row[6] else 0.0
            tgt_pr = float(row[7]) if row[7] else 0.0

            # Calculate propagated score
            seed_contribution = 0.0
            if src_uuid in entity_scores:
                seed_contribution = max(seed_contribution, entity_scores[src_uuid])
            if tgt_uuid in entity_scores:
                seed_contribution = max(seed_contribution, entity_scores[tgt_uuid])

            # Score = decay * seed_contribution * edge_importance
            edge_importance = (src_pr + tgt_pr) / 2 + 0.1
            score = hop_decay * seed_contribution * edge_importance

            propagated.append(
                RetrievalItem(
                    uuid=r_uuid,
                    text=fact,
                    score=min(score, 0.95),  # Cap at 0.95
                    result_type=ResultType.FACT,
                    source_entity=src_name,
                    target_entity=tgt_name,
                    method='score_propagation',
                )
            )

    return propagated


# =============================================================================
# Reranking
# =============================================================================


def rerank_with_cross_encoder(
    query: str, items: list[RetrievalItem], limit: int = 20
) -> list[RetrievalItem]:
    """
    Rerank items using cross-encoder via vLLM.
    """
    if not items:
        return []

    documents = [item.text for item in items[:50]]  # Limit to 50 for speed

    try:
        response = requests.post(
            f'{RERANKER_URL}/v1/rerank',
            json={'model': 'qwen3-reranker-4b', 'query': query, 'documents': documents},
            timeout=30,
        )

        if response.status_code == 200:
            data = response.json()
            results = data.get('results', [])

            # Map scores back to items (invert because vLLM gives inverted scores)
            for result in results:
                idx = result.get('index', 0)
                score = result.get('relevance_score', 0.5)
                if idx < len(items):
                    items[idx].score = 1.0 - score  # Invert

            # Sort by score
            items.sort(key=lambda x: x.score, reverse=True)

        return items[:limit]

    except Exception as e:
        print(f'Reranker error: {e}')
        return items[:limit]


# =============================================================================
# Main Retrieval Strategies
# =============================================================================


def strategy_baseline(query: str, limit: int = 15) -> StrategyResult:
    """
    Baseline: Vector search + cross-encoder reranking.
    """
    start = time.perf_counter()
    intent = classify_intent(query)

    results = vector_search(query, limit=limit * 2, use_reranker=True)
    results = results[:limit]

    latency = (time.perf_counter() - start) * 1000

    return StrategyResult(
        strategy='baseline',
        query=query,
        intent=intent,
        results=results,
        latency_ms=latency,
        breakdown={'vector': len(results)},
    )


def strategy_tri_bucket(
    query: str,
    limit: int = 15,
    fact_quota: float = 0.4,
    entity_quota: float = 0.2,
    episode_quota: float = 0.4,
) -> StrategyResult:
    """
    Strategy 1: Tri-Bucket Retrieval

    Explicitly retrieves from 3 buckets with quotas:
    - RELATES_TO.fact (default 40%)
    - Entity summaries (default 20%)
    - Episodic.content (default 40%)

    Uses entity resolution + graph expansion.
    """
    start = time.perf_counter()
    intent = classify_intent(query)

    # Adjust quotas based on intent
    if intent == QueryIntent.RELATIONSHIP:
        fact_quota, entity_quota, episode_quota = 0.5, 0.3, 0.2
    elif intent == QueryIntent.TEMPORAL:
        fact_quota, entity_quota, episode_quota = 0.2, 0.2, 0.6
    elif intent == QueryIntent.FACTUAL:
        fact_quota, entity_quota, episode_quota = 0.4, 0.4, 0.2

    # Calculate bucket limits
    fact_limit = max(3, int(limit * fact_quota))
    entity_limit = max(2, int(limit * entity_quota))
    episode_limit = max(3, int(limit * episode_quota))

    # Step 1: Vector search for initial facts
    vector_facts = vector_search(query, limit=fact_limit * 2)

    # Step 2: Extract entities from query
    query_entities = extract_entities_from_query(query)
    entity_names = [e['name'] for e in query_entities]

    # Step 3: Resolve entities via graph
    resolved_entities = resolve_entities(entity_names)
    entity_uuids = [e['uuid'] for e in resolved_entities]

    # Also get entities from vector facts
    fact_uuids = [f.uuid for f in vector_facts if f.uuid]
    if fact_uuids:
        uuid_list = "', '".join(fact_uuids[:10])
        cypher = f"""
        MATCH (src:Entity)-[r:RELATES_TO]->(tgt:Entity)
        WHERE r.uuid IN ['{uuid_list}']
        RETURN DISTINCT src.uuid, tgt.uuid
        """
        rows = graph_query(cypher)
        for row in rows:
            if row:
                if row[0] and row[0] not in entity_uuids:
                    entity_uuids.append(row[0])
                if row[1] and row[1] not in entity_uuids:
                    entity_uuids.append(row[1])

    # Step 4: Get graph facts for entities
    graph_facts = get_facts_for_entities(entity_uuids, limit=fact_limit)

    # Step 5: Get episodes that mention entities
    episodes = get_episodes_for_entities(entity_uuids, limit=episode_limit)

    # Step 6: Create entity items from resolved entities
    entity_items = []
    for e in resolved_entities[:entity_limit]:
        if e.get('summary'):
            entity_items.append(
                RetrievalItem(
                    uuid=e['uuid'],
                    text=f'{e["name"]}: {e["summary"]}',
                    score=0.6 + (e.get('pagerank', 0) * 0.3),
                    result_type=ResultType.ENTITY,
                    method='entity_resolution',
                    metadata={'pagerank': e.get('pagerank'), 'community': e.get('community_id')},
                )
            )

    # Combine facts (deduplicate)
    all_facts = []
    seen_uuids = set()
    for f in vector_facts + graph_facts:
        if f.uuid not in seen_uuids:
            seen_uuids.add(f.uuid)
            all_facts.append(f)

    # Apply quotas
    final_facts = all_facts[:fact_limit]
    final_entities = entity_items[:entity_limit]
    final_episodes = episodes[:episode_limit]

    # Combine all
    all_results = final_facts + final_entities + final_episodes
    all_results.sort(key=lambda x: x.score, reverse=True)

    latency = (time.perf_counter() - start) * 1000

    return StrategyResult(
        strategy='tri_bucket',
        query=query,
        intent=intent,
        results=all_results[:limit],
        latency_ms=latency,
        breakdown={
            'facts': len(final_facts),
            'entities': len(final_entities),
            'episodes': len(final_episodes),
        },
    )


def strategy_entity_seeded_propagation(query: str, limit: int = 15) -> StrategyResult:
    """
    Strategy 2: Entity-Seeded with Score Propagation

    1. Vector search for seeds
    2. Extract entities from seeds
    3. Propagate scores to neighbors
    4. Combine with MMR
    """
    start = time.perf_counter()
    intent = classify_intent(query)

    # Step 1: Vector search for seeds
    seeds = vector_search(query, limit=20)

    # Step 2: Propagate scores to neighbors
    propagated = propagate_scores(seeds, hop_decay=0.6)

    # Step 3: Combine seeds + propagated
    all_items = seeds + propagated

    # Step 4: MMR for diversity
    diverse_results = mmr_rerank(all_items, lambda_param=0.7, limit=limit)

    latency = (time.perf_counter() - start) * 1000

    return StrategyResult(
        strategy='entity_seeded_propagation',
        query=query,
        intent=intent,
        results=diverse_results,
        latency_ms=latency,
        breakdown={'seeds': len(seeds), 'propagated': len(propagated)},
    )


def strategy_fact_first_relationship(query: str, limit: int = 15) -> StrategyResult:
    """
    Strategy 3: Fact-First for Relationship Queries

    Optimized for "how does X relate to Y?" type queries.
    1. Extract entity mentions
    2. Find all facts between/around those entities
    3. Get supporting episodes
    4. Rerank with cross-encoder
    """
    start = time.perf_counter()
    intent = classify_intent(query)

    # Step 1: Extract entities
    query_entities = extract_entities_from_query(query)
    entity_names = [e['name'] for e in query_entities]

    # Step 2: Resolve entities
    resolved = resolve_entities(entity_names, limit_per_name=5)
    entity_uuids = [e['uuid'] for e in resolved]

    # Step 3: Get all facts for these entities (more aggressive)
    facts = get_facts_for_entities(entity_uuids, limit=limit * 3)

    # Step 4: Also do vector search for semantic coverage
    vector_facts = vector_search(query, limit=limit)

    # Combine and dedupe
    seen = set()
    all_facts = []
    for f in facts + vector_facts:
        if f.uuid not in seen:
            seen.add(f.uuid)
            all_facts.append(f)

    # Step 5: Rerank with cross-encoder
    reranked = rerank_with_cross_encoder(query, all_facts, limit=limit)

    # Step 6: Get supporting episodes for top entities
    if entity_uuids:
        episodes = get_episodes_for_entities(entity_uuids[:5], limit=3)
        # Add episodes at lower scores
        for ep in episodes:
            ep.score = min(ep.score, reranked[-1].score * 0.9 if reranked else 0.5)
        reranked.extend(episodes)

    latency = (time.perf_counter() - start) * 1000

    return StrategyResult(
        strategy='fact_first_relationship',
        query=query,
        intent=intent,
        results=reranked[:limit],
        latency_ms=latency,
        breakdown={'facts': len(facts), 'vector_facts': len(vector_facts)},
    )


def strategy_lexical_rescue(query: str, limit: int = 15) -> StrategyResult:
    """
    Strategy 4: Lexical Rescue Path

    For queries with exact terms (file paths, UUIDs, error codes).
    Combines lexical + vector search.
    """
    start = time.perf_counter()
    intent = classify_intent(query)

    # Extract potential exact terms
    exact_terms = []

    # File paths
    exact_terms.extend(re.findall(r'/[^\s]+', query))

    # UUIDs
    exact_terms.extend(
        re.findall(r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}', query.lower())
    )

    # Technical terms (docker, config names, etc.)
    exact_terms.extend(re.findall(r'\b[a-z]+-[a-z]+(?:-[a-z]+)*\b', query.lower()))

    # Quoted strings
    exact_terms.extend(re.findall(r'"([^"]+)"', query))

    # Dedupe
    exact_terms = list(set(exact_terms))

    # Step 1: Lexical search
    lexical_facts = lexical_search_facts(exact_terms, limit=limit)
    lexical_episodes = lexical_search_episodes(exact_terms, limit=5)

    # Step 2: Vector search for semantic coverage
    vector_facts = vector_search(query, limit=limit)

    # Combine with lexical results boosted
    all_items = []
    seen = set()

    # Add lexical first (higher priority)
    for item in lexical_facts + lexical_episodes:
        if item.uuid not in seen:
            seen.add(item.uuid)
            item.score += 0.1  # Boost lexical matches
            all_items.append(item)

    # Add vector results
    for item in vector_facts:
        if item.uuid not in seen:
            seen.add(item.uuid)
            all_items.append(item)

    # Sort by score
    all_items.sort(key=lambda x: x.score, reverse=True)

    latency = (time.perf_counter() - start) * 1000

    return StrategyResult(
        strategy='lexical_rescue',
        query=query,
        intent=intent,
        results=all_items[:limit],
        latency_ms=latency,
        breakdown={
            'lexical_facts': len(lexical_facts),
            'lexical_episodes': len(lexical_episodes),
            'vector': len(vector_facts),
            'exact_terms': exact_terms[:5],
        },
    )


def strategy_multi_rewrite(query: str, limit: int = 15) -> StrategyResult:
    """
    Strategy 5: Multi-Query Rewrite

    1. Generate query rewrites
    2. Search for each rewrite
    3. Merge with MMR
    """
    start = time.perf_counter()
    intent = classify_intent(query)

    # Generate rewrites
    rewrites = generate_query_rewrites(query, intent)

    # Search for each rewrite
    all_results = []
    for rewrite in rewrites:
        results = vector_search(rewrite, limit=limit)
        for r in results:
            r.metadata['rewrite'] = rewrite
        all_results.extend(results)

    # Dedupe
    seen = set()
    unique = []
    for r in all_results:
        if r.uuid not in seen:
            seen.add(r.uuid)
            unique.append(r)

    # MMR for diversity
    diverse = mmr_rerank(unique, lambda_param=0.65, limit=limit)

    latency = (time.perf_counter() - start) * 1000

    return StrategyResult(
        strategy='multi_rewrite',
        query=query,
        intent=intent,
        results=diverse,
        latency_ms=latency,
        breakdown={'rewrites': rewrites, 'total_candidates': len(unique)},
    )


def strategy_adaptive(query: str, limit: int = 15) -> StrategyResult:
    """
    Strategy 6: Adaptive (Intent-Based Strategy Selection)

    Chooses the best strategy based on query intent:
    - RELATIONSHIP -> fact_first_relationship
    - TEMPORAL -> tri_bucket (episode-heavy)
    - PROCEDURAL -> lexical_rescue + episodes
    - FACTUAL -> entity_seeded_propagation
    - EXPLORATORY -> multi_rewrite
    """
    intent = classify_intent(query)

    if intent == QueryIntent.RELATIONSHIP:
        return strategy_fact_first_relationship(query, limit)
    elif intent == QueryIntent.TEMPORAL:
        return strategy_tri_bucket(query, limit)
    elif intent == QueryIntent.PROCEDURAL:
        result = strategy_lexical_rescue(query, limit)
        result.strategy = 'adaptive_procedural'
        return result
    elif intent == QueryIntent.FACTUAL:
        return strategy_entity_seeded_propagation(query, limit)
    else:
        return strategy_multi_rewrite(query, limit)


# =============================================================================
# Evaluation
# =============================================================================


def evaluate_results(
    results: list[RetrievalItem], query: str, expected_keywords: list[str]
) -> dict:
    """Evaluate retrieval results."""
    if not results:
        return {
            'keyword_coverage': 0.0,
            'keyword_hits': 0,
            'keyword_total': len(expected_keywords),
            'relevance_score': 0.0,
            'result_count': 0,
            'type_distribution': {},
        }

    combined_text = ' '.join([r.text.lower() for r in results])

    # Keyword coverage
    hits = sum(1 for kw in expected_keywords if kw.lower() in combined_text)
    coverage = hits / len(expected_keywords) if expected_keywords else 0

    # Query word relevance
    query_words = [w.lower() for w in query.split() if len(w) > 3]
    relevance_hits = sum(1 for w in query_words if w in combined_text)
    relevance = relevance_hits / len(query_words) if query_words else 0

    # Type distribution
    type_dist = defaultdict(int)
    for r in results:
        type_dist[r.result_type.value] += 1

    return {
        'keyword_coverage': coverage,
        'keyword_hits': hits,
        'keyword_total': len(expected_keywords),
        'relevance_score': relevance,
        'result_count': len(results),
        'type_distribution': dict(type_dist),
    }


def diversity_score(results: list[RetrievalItem]) -> float:
    """Calculate diversity score based on text dissimilarity."""
    if len(results) <= 1:
        return 1.0

    total_sim = 0.0
    pairs = 0

    for i in range(len(results)):
        for j in range(i + 1, len(results)):
            total_sim += simple_text_similarity(results[i].text, results[j].text)
            pairs += 1

    avg_sim = total_sim / pairs if pairs > 0 else 0
    return 1.0 - avg_sim  # Higher = more diverse


# =============================================================================
# Test Cases
# =============================================================================

TEST_CASES = [
    {
        'name': 'Sync Service (Relationship)',
        'query': 'How does the sync service transfer data between FalkorDB and Neo4j?',
        'expected_keywords': [
            'sync',
            'falkordb',
            'neo4j',
            'transfer',
            'data',
            'migration',
            'graphiti-sync',
        ],
    },
    {
        'name': 'Emmanuel Context (Factual)',
        'query': 'What is Emmanuel working on with Graphiti?',
        'expected_keywords': ['emmanuel', 'graphiti', 'knowledge', 'graph', 'opencode'],
    },
    {
        'name': 'Architecture (Exploratory)',
        'query': 'Tell me about the main components of the knowledge graph system',
        'expected_keywords': [
            'entity',
            'edge',
            'node',
            'falkordb',
            'neo4j',
            'episodic',
            'component',
        ],
    },
    {
        'name': 'Reranker Fix (Temporal)',
        'query': 'When was the reranker score inversion bug fixed?',
        'expected_keywords': ['rerank', 'score', 'invert', 'fix', 'vllm', 'qwen'],
    },
    {
        'name': 'Letta Integration (Relationship)',
        'query': 'How do Letta agents interact with the knowledge graph?',
        'expected_keywords': ['letta', 'agent', 'graph', 'memory', 'tool', 'mcp', 'graphiti'],
    },
    {
        'name': 'File Path Query (Lexical)',
        'query': 'What is in /opt/stacks/graphiti/docker-compose.yml?',
        'expected_keywords': ['docker', 'compose', 'yml', 'service', 'container', 'falkordb'],
    },
    {
        'name': 'Procedure Query',
        'query': 'How to configure FalkorDB persistence?',
        'expected_keywords': ['falkordb', 'persist', 'rdb', 'snapshot', 'volume', 'docker'],
    },
    {
        'name': 'Community Detection',
        'query': 'What community detection algorithm is used for entity clustering?',
        'expected_keywords': ['community', 'cdlp', 'label', 'propagation', 'cluster', 'entity'],
    },
]


def main():
    print('=' * 90)
    print('RETRIEVAL STRATEGIES V2 - REFINED GRAPH-AWARE RETRIEVAL')
    print('=' * 90)

    strategies = [
        ('Baseline (Vector + CE)', strategy_baseline),
        ('Tri-Bucket (Facts/Entities/Episodes)', strategy_tri_bucket),
        ('Entity-Seeded + Propagation', strategy_entity_seeded_propagation),
        ('Fact-First (Relationship)', strategy_fact_first_relationship),
        ('Lexical Rescue', strategy_lexical_rescue),
        ('Multi-Rewrite + MMR', strategy_multi_rewrite),
        ('Adaptive (Intent-Based)', strategy_adaptive),
    ]

    all_results = defaultdict(list)

    for test_case in TEST_CASES:
        print(f'\n{"─" * 70}')
        print(f'TEST: {test_case["name"]}')
        print(f'Query: {test_case["query"][:65]}...')
        print(f'{"─" * 70}')

        for strategy_name, strategy_fn in strategies:
            try:
                result = strategy_fn(test_case['query'])
                metrics = evaluate_results(
                    result.results, test_case['query'], test_case['expected_keywords']
                )
                diversity = diversity_score(result.results)

                all_results[strategy_name].append(
                    {
                        'test': test_case['name'],
                        'metrics': metrics,
                        'latency': result.latency_ms,
                        'intent': result.intent.value,
                        'diversity': diversity,
                        'breakdown': result.breakdown,
                    }
                )

                print(f'\n  {strategy_name}:')
                print(f'    Intent: {result.intent.value}')
                print(
                    f'    Keywords: {metrics["keyword_hits"]}/{metrics["keyword_total"]} ({metrics["keyword_coverage"] * 100:.1f}%)'
                )
                print(f'    Relevance: {metrics["relevance_score"] * 100:.1f}%')
                print(f'    Diversity: {diversity * 100:.1f}%')
                print(f'    Latency: {result.latency_ms:.0f}ms')
                if metrics.get('type_distribution'):
                    print(f'    Types: {metrics["type_distribution"]}')
                if result.results:
                    print(f'    Top: {result.results[0].text[:60]}...')

            except Exception as e:
                print(f'\n  {strategy_name}: ERROR - {e}')
                import traceback

                traceback.print_exc()

    # Summary
    print('\n' + '=' * 90)
    print('SUMMARY')
    print('=' * 90)

    print(
        f'\n{"Strategy":<38} {"Keywords":<10} {"Relevance":<10} {"Diversity":<10} {"Latency":<10}'
    )
    print('-' * 78)

    summaries = []
    for strategy_name, results in all_results.items():
        if results:
            avg_coverage = np.mean([r['metrics']['keyword_coverage'] for r in results])
            avg_relevance = np.mean([r['metrics']['relevance_score'] for r in results])
            avg_diversity = np.mean([r['diversity'] for r in results])
            avg_latency = np.mean([r['latency'] for r in results])

            summaries.append(
                {
                    'name': strategy_name,
                    'coverage': avg_coverage,
                    'relevance': avg_relevance,
                    'diversity': avg_diversity,
                    'latency': avg_latency,
                }
            )

            print(
                f'{strategy_name:<38} {avg_coverage * 100:>7.1f}% {avg_relevance * 100:>8.1f}% {avg_diversity * 100:>8.1f}% {avg_latency:>8.0f}ms'
            )

    # Rankings
    print('\n' + '─' * 78)
    print('RANKINGS:')

    by_coverage = sorted(summaries, key=lambda x: x['coverage'], reverse=True)
    print(f'\nBy Keyword Coverage:')
    for i, s in enumerate(by_coverage[:3], 1):
        print(f'  {i}. {s["name"]} ({s["coverage"] * 100:.0f}%)')

    by_relevance = sorted(summaries, key=lambda x: x['relevance'], reverse=True)
    print(f'\nBy Relevance:')
    for i, s in enumerate(by_relevance[:3], 1):
        print(f'  {i}. {s["name"]} ({s["relevance"] * 100:.0f}%)')

    by_diversity = sorted(summaries, key=lambda x: x['diversity'], reverse=True)
    print(f'\nBy Diversity:')
    for i, s in enumerate(by_diversity[:3], 1):
        print(f'  {i}. {s["name"]} ({s["diversity"] * 100:.0f}%)')

    by_latency = sorted(summaries, key=lambda x: x['latency'])
    print(f'\nBy Speed:')
    for i, s in enumerate(by_latency[:3], 1):
        print(f'  {i}. {s["name"]} ({s["latency"]:.0f}ms)')

    # Composite score (weighted)
    print('\n' + '─' * 78)
    print('COMPOSITE SCORE (40% coverage + 30% relevance + 20% diversity + 10% speed):')

    max_latency = max(s['latency'] for s in summaries) if summaries else 1
    for s in summaries:
        speed_score = 1 - (s['latency'] / max_latency)
        s['composite'] = (
            0.4 * s['coverage'] + 0.3 * s['relevance'] + 0.2 * s['diversity'] + 0.1 * speed_score
        )

    by_composite = sorted(summaries, key=lambda x: x['composite'], reverse=True)
    for i, s in enumerate(by_composite, 1):
        print(f'  {i}. {s["name"]}: {s["composite"] * 100:.1f}%')


if __name__ == '__main__':
    main()
