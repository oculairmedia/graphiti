#!/usr/bin/env python3
"""Compare HippoRAG spreading activation vs Graphiti direct vector search.

NOTE: FalkorDB has a bug where vec.cosineDistance() fails with "Type mismatch: expected Null or Vectorf32 but was List"
even when comparing stored Vectorf32 embeddings. This script works around the bug by:
1. Fetching all entity embeddings from FalkorDB
2. Computing cosine similarity in Python
"""

import math
from time import time

import httpx
import redis

# VLLM embedding endpoint (qwen3-embedding)
EMBEDDING_URL = 'http://100.81.139.20:11450/v1/embeddings'
EMBEDDING_MODEL = 'qwen3-embedding'


def get_query_embedding(text: str) -> list[float]:
    """Get embedding from VLLM endpoint."""
    response = httpx.post(
        EMBEDDING_URL,
        json={'model': EMBEDDING_MODEL, 'input': text},
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()['data'][0]['embedding']


def parse_vectorf32(raw_bytes) -> list[float]:
    """Parse FalkorDB Vectorf32 bytes '<0.1, 0.2, ...>' into float list."""
    if isinstance(raw_bytes, bytes):
        text = raw_bytes.decode('utf-8')
    else:
        text = str(raw_bytes)
    inner = text.strip()[1:-1]
    return [float(x.strip()) for x in inner.split(',')]


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    if len(vec_a) != len(vec_b):
        return 0.0
    dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot_product / (norm_a * norm_b)


def fetch_all_entities_with_embeddings(
    r, batch_size=1000
) -> dict[str, tuple[str, str, list[float]]]:
    entities = {}
    offset = 0

    while True:
        query = f"""
            MATCH (n:Entity) 
            WHERE n.name_embedding IS NOT NULL 
            RETURN n.uuid, n.name, n.summary, n.name_embedding 
            SKIP {offset} LIMIT {batch_size}
        """
        result = r.execute_command('GRAPH.QUERY', 'graphiti_migration', query)
        rows = result[1] if result and len(result) > 1 else []

        if not rows:
            break

        for row in rows:
            uuid = row[0].decode() if isinstance(row[0], bytes) else row[0]
            name = row[1].decode() if isinstance(row[1], bytes) else row[1]
            summary = (row[2].decode() if isinstance(row[2], bytes) else row[2]) or ''
            embedding = parse_vectorf32(row[3])
            entities[uuid] = (name, summary, embedding)

        offset += batch_size
        if len(rows) < batch_size:
            break

    return entities


def graphiti_search(entities: dict, query_embedding: list[float], top_k=10, threshold=0.5):
    start = time()

    scored = []
    for uuid, (name, summary, emb) in entities.items():
        sim = cosine_similarity(query_embedding, emb)
        if sim > threshold:
            scored.append((name, summary, sim, uuid))

    scored.sort(key=lambda x: x[2], reverse=True)

    results = [(name, summary, sim) for name, summary, sim, _ in scored[:top_k]]
    return results, time() - start


def graphiti_search_with_uuids(
    entities: dict, query_embedding: list[float], top_k=10, threshold=0.5
):
    start = time()

    scored = []
    for uuid, (name, summary, emb) in entities.items():
        sim = cosine_similarity(query_embedding, emb)
        if sim > threshold:
            scored.append((uuid, name, sim))

    scored.sort(key=lambda x: x[2], reverse=True)
    return scored[:top_k], time() - start


def hipporag_search(
    r, entities: dict, query_embedding: list[float], top_k=10, max_hops=2, decay=0.5, threshold=0.5
):
    start = time()

    seeds, _ = graphiti_search_with_uuids(entities, query_embedding, top_k=5, threshold=threshold)

    if not seeds:
        return [], time() - start, []

    seed_uuids = [s[0] for s in seeds]
    seed_scores = {s[0]: s[2] for s in seeds}

    uuid_list = str(seed_uuids)

    prop_query = f"""
        MATCH path = (seed:Entity)-[*1..{max_hops}]-(target:Entity) 
        WHERE seed.uuid IN {uuid_list} AND seed <> target 
        WITH DISTINCT target, seed, length(path) as hops 
        WITH target, seed.uuid as seed_uuid, {decay} ^ hops as decay_score 
        RETURN target.uuid, target.name, target.summary, collect(seed_uuid), sum(decay_score) as activation 
        ORDER BY activation DESC LIMIT {top_k}
    """

    try:
        result = r.execute_command('GRAPH.QUERY', 'graphiti_migration', prop_query)
        rows = result[1] if result and len(result) > 1 else []
        results = []
        for row in rows:
            uuid = row[0].decode() if isinstance(row[0], bytes) else row[0]
            name = row[1].decode() if isinstance(row[1], bytes) else row[1]
            summary = (row[2].decode() if isinstance(row[2], bytes) else row[2]) or ''
            contributing = [s.decode() if isinstance(s, bytes) else s for s in row[3]]
            activation = float(row[4].decode() if isinstance(row[4], bytes) else row[4])

            weighted = activation
            for seed_uuid in contributing:
                if seed_uuid in seed_scores:
                    weighted *= seed_scores[seed_uuid]
            results.append((name, summary, weighted))

        seed_info = [(uuid, name, score) for uuid, name, score in seeds]
        return results, time() - start, seed_info
    except Exception as e:
        print(f'Propagation error: {e}')
        return [], time() - start, [(uuid, name, score) for uuid, name, score in seeds]


def compare(r, entities: dict, query_text: str, query_embedding: list[float]):
    print(f'\n{"=" * 70}\nQuery: {query_text!r}\n{"=" * 70}')

    print('\n[GRAPHITI - Direct Vector Similarity]')
    g_results, g_time = graphiti_search(entities, query_embedding)
    print(f'Time: {g_time * 1000:.1f}ms | Results: {len(g_results)}')
    for i, (n, s, score) in enumerate(g_results[:5], 1):
        print(f'  {i}. {n[:40]}: {score:.4f}')

    print('\n[HIPPORAG - Spreading Activation (2-hop)]')
    h_results, h_time, seeds = hipporag_search(r, entities, query_embedding)
    print(f'Time: {h_time * 1000:.1f}ms | Seeds: {[s[1] for s in seeds][:3]}')
    for i, (n, s, act) in enumerate(h_results[:5], 1):
        print(f'  {i}. {n[:40]}: {act:.4f}')

    g_names = {row[0] for row in g_results[:10]}
    h_names = {row[0] for row in h_results[:10]}

    only_hippo = h_names - g_names
    only_graphiti = g_names - h_names
    overlap = len(g_names & h_names)

    print('\n[COMPARISON]')
    print(f'  Overlap: {overlap}/{min(len(g_names), len(h_names))} entities in common')
    if only_hippo:
        print(f'  Unique to HippoRAG: {only_hippo}')
    if only_graphiti:
        print(f'  Unique to Graphiti: {only_graphiti}')


def main():
    r = redis.Redis(host='localhost', port=6379)
    print('Connected to FalkorDB via redis-py')

    print('\nFetching all entities with embeddings (one-time load)...')
    start = time()
    entities = fetch_all_entities_with_embeddings(r)
    print(f'Loaded {len(entities)} entities in {time() - start:.1f}s')

    queries = [
        'Emmanuel',
        'Graphiti knowledge graph',
        'Temporal workflow',
        'FalkorDB database',
        'project management',
    ]
    for query in queries:
        print(f'\nGenerating embedding for {query!r}...')
        emb = get_query_embedding(query)
        compare(r, entities, query, emb)


if __name__ == '__main__':
    main()
