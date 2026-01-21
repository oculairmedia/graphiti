#!/usr/bin/env python3
"""Evaluate hybrid search quality vs pure vector and pure graph approaches."""

import math
from time import time
import httpx
import redis

EMBEDDING_URL = 'http://100.81.139.20:11450/v1/embeddings'
EMBEDDING_MODEL = 'qwen3-embedding'

# Test queries with expected relevant entities (ground truth)
# These are entities we KNOW should be relevant based on domain knowledge
TEST_CASES = [
    {
        'query': 'Emmanuel',
        'relevant': {
            'Emmanuel', 'emmanuel umukoro', 'emmanuel_bernard',  # Direct matches
            'Claude', 'Letta', 'graphiti',  # Things Emmanuel works with
            'matrix', 'opencode', 'huly',  # Projects Emmanuel uses
        },
    },
    {
        'query': 'Graphiti knowledge graph',
        'relevant': {
            'Graphiti knowledge graph', 'graphiti', 'graphiti_knowledge_graph',
            'falkordb', 'neo4j',  # Database backends
            'temporal', 'ingestion',  # Related systems
            'entity', 'edge', 'node',  # Graph concepts
            'embedding', 'vector',  # Search components
        },
    },
    {
        'query': 'Temporal workflow',
        'relevant': {
            'Temporal', 'temporal', 'Temporal workflows', 'temporalio',
            'workflow', 'activity', 'worker',  # Temporal concepts
            'ingestion', 'graphiti',  # Uses Temporal
            'docker-compose', 'python',  # Infrastructure
        },
    },
    {
        'query': 'FalkorDB database',
        'relevant': {
            'FalkorDB', 'falkordb', 'FalkorDB database',
            'redis', 'graph', 'cypher',  # Related tech
            'graphiti', 'vector', 'HNSW',  # Uses FalkorDB
            'docker', 'container',  # Infrastructure
        },
    },
    {
        'query': 'project management',
        'relevant': {
            'project management', 'project_manager', 'project',
            'huly', 'hully',  # PM tool used
            'task', 'issue', 'sprint',  # PM concepts
            'agent', 'graphiti',  # Related systems
        },
    },
]


def get_embedding(text: str) -> list[float]:
    response = httpx.post(
        EMBEDDING_URL,
        json={'model': EMBEDDING_MODEL, 'input': text},
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()['data'][0]['embedding']


def parse_vectorf32(raw_bytes) -> list[float]:
    if isinstance(raw_bytes, bytes):
        text = raw_bytes.decode('utf-8')
    else:
        text = str(raw_bytes)
    inner = text.strip()[1:-1]
    return [float(x.strip()) for x in inner.split(',')]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def hnsw_search(r, embedding: list[float], top_k: int = 10) -> list[tuple[str, float]]:
    """Pure HNSW vector search."""
    emb_str = ','.join(map(str, embedding))
    query = f"""
        CALL db.idx.vector.queryNodes('Entity', 'name_embedding', {top_k}, vecf32([{emb_str}]))
        YIELD node, score
        RETURN node.name, score
        ORDER BY score ASC
    """
    result = r.execute_command('GRAPH.QUERY', 'graphiti_migration', query)
    rows = result[1] if result and len(result) > 1 else []
    return [
        (row[0].decode() if isinstance(row[0], bytes) else row[0], 
         1.0 - float(row[1].decode() if isinstance(row[1], bytes) else row[1]))
        for row in rows
    ]


def hipporag_search(r, embedding: list[float], top_k: int = 10) -> list[tuple[str, float]]:
    """Pure graph-based spreading activation."""
    emb_str = ','.join(map(str, embedding))
    
    # Get seeds
    seed_query = f"""
        CALL db.idx.vector.queryNodes('Entity', 'name_embedding', 5, vecf32([{emb_str}]))
        YIELD node, score
        RETURN node.uuid, node.name, score
        ORDER BY score ASC
    """
    result = r.execute_command('GRAPH.QUERY', 'graphiti_migration', seed_query)
    seeds = []
    seed_scores = {}
    for row in (result[1] if result and len(result) > 1 else []):
        uuid = row[0].decode() if isinstance(row[0], bytes) else row[0]
        name = row[1].decode() if isinstance(row[1], bytes) else row[1]
        sim = 1.0 - float(row[2].decode() if isinstance(row[2], bytes) else row[2])
        seeds.append(uuid)
        seed_scores[uuid] = sim
    
    if not seeds:
        return []
    
    # Propagate
    uuid_list = str(seeds)
    prop_query = f"""
        MATCH path = (seed:Entity)-[*1..2]-(target:Entity)
        WHERE seed.uuid IN {uuid_list} AND seed <> target
        WITH DISTINCT target, seed, length(path) as hops
        WITH target, seed.uuid as seed_uuid, 0.5 ^ hops as decay
        RETURN target.name, collect(seed_uuid), sum(decay) as activation
        ORDER BY activation DESC LIMIT {top_k}
    """
    result = r.execute_command('GRAPH.QUERY', 'graphiti_migration', prop_query)
    results = []
    for row in (result[1] if result and len(result) > 1 else []):
        name = row[0].decode() if isinstance(row[0], bytes) else row[0]
        contributing = [s.decode() if isinstance(s, bytes) else s for s in row[1]]
        activation = float(row[2].decode() if isinstance(row[2], bytes) else row[2])
        weighted = activation
        for seed_uuid in contributing:
            if seed_uuid in seed_scores:
                weighted *= seed_scores[seed_uuid]
        results.append((name, weighted))
    return results


def hybrid_search(r, embedding: list[float], top_k: int = 10, vector_weight: float = 0.7) -> list[tuple[str, float]]:
    """Hybrid: vector + graph."""
    emb_str = ','.join(map(str, embedding))
    
    # Get seeds with HNSW
    seed_query = f"""
        CALL db.idx.vector.queryNodes('Entity', 'name_embedding', {top_k}, vecf32([{emb_str}]))
        YIELD node, score
        RETURN node.uuid, node.name, score
        ORDER BY score ASC
    """
    result = r.execute_command('GRAPH.QUERY', 'graphiti_migration', seed_query)
    
    candidates = {}
    seed_uuids = []
    seed_sims = {}
    
    for row in (result[1] if result and len(result) > 1 else []):
        uuid = row[0].decode() if isinstance(row[0], bytes) else row[0]
        name = row[1].decode() if isinstance(row[1], bytes) else row[1]
        sim = 1.0 - float(row[2].decode() if isinstance(row[2], bytes) else row[2])
        seed_uuids.append(uuid)
        seed_sims[uuid] = sim
        candidates[uuid] = {'name': name, 'vector': sim, 'graph': 0.0}
    
    if not seed_uuids:
        return []
    
    # Get neighbors and their graph scores
    uuid_list = str(seed_uuids)
    neighbor_query = f"""
        MATCH path = (seed:Entity)-[*1..2]-(neighbor:Entity)
        WHERE seed.uuid IN {uuid_list} AND neighbor.name_embedding IS NOT NULL
        WITH neighbor, seed, min(length(path)) as min_hops
        RETURN neighbor.uuid, neighbor.name, collect(seed.uuid), collect(min_hops)
    """
    result = r.execute_command('GRAPH.QUERY', 'graphiti_migration', neighbor_query)
    
    neighbor_uuids = []
    for row in (result[1] if result and len(result) > 1 else []):
        uuid = row[0].decode() if isinstance(row[0], bytes) else row[0]
        name = row[1].decode() if isinstance(row[1], bytes) else row[1]
        contributing = [s.decode() if isinstance(s, bytes) else s for s in row[2]]
        hops = [int(h.decode() if isinstance(h, bytes) else h) for h in row[3]]
        
        graph_score = 0.0
        for seed_uuid, hop in zip(contributing, hops):
            decay = 0.5 ** hop
            graph_score += decay * seed_sims.get(seed_uuid, 0.5)
        
        if uuid in candidates:
            candidates[uuid]['graph'] = max(candidates[uuid]['graph'], graph_score)
        else:
            neighbor_uuids.append(uuid)
            candidates[uuid] = {'name': name, 'vector': 0.0, 'graph': graph_score}
    
    # Get vector scores for neighbors
    if neighbor_uuids:
        neighbor_list = str(neighbor_uuids)
        vec_query = f"""
            CALL db.idx.vector.queryNodes('Entity', 'name_embedding', {len(neighbor_uuids) * 2}, vecf32([{emb_str}]))
            YIELD node, score
            WHERE node.uuid IN {neighbor_list}
            RETURN node.uuid, score
        """
        result = r.execute_command('GRAPH.QUERY', 'graphiti_migration', vec_query)
        for row in (result[1] if result and len(result) > 1 else []):
            uuid = row[0].decode() if isinstance(row[0], bytes) else row[0]
            sim = 1.0 - float(row[1].decode() if isinstance(row[1], bytes) else row[1])
            if uuid in candidates:
                candidates[uuid]['vector'] = sim
    
    # Compute combined scores
    graph_weight = 1.0 - vector_weight
    results = []
    for uuid, data in candidates.items():
        combined = vector_weight * data['vector'] + graph_weight * data['graph']
        results.append((data['name'], combined))
    
    results.sort(key=lambda x: x[1], reverse=True)
    return results[:top_k]


def precision_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    """Precision@K: fraction of top-K results that are relevant."""
    top_k = retrieved[:k]
    relevant_found = sum(1 for r in top_k if any(rel.lower() in r.lower() or r.lower() in rel.lower() for rel in relevant))
    return relevant_found / k if k > 0 else 0.0


def recall_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    """Recall@K: fraction of relevant items found in top-K."""
    top_k = retrieved[:k]
    relevant_found = sum(1 for r in top_k if any(rel.lower() in r.lower() or r.lower() in rel.lower() for rel in relevant))
    return relevant_found / len(relevant) if relevant else 0.0


def mrr(retrieved: list[str], relevant: set[str]) -> float:
    """Mean Reciprocal Rank: 1/rank of first relevant result."""
    for i, r in enumerate(retrieved, 1):
        if any(rel.lower() in r.lower() or r.lower() in rel.lower() for rel in relevant):
            return 1.0 / i
    return 0.0


def evaluate():
    r = redis.Redis(host='localhost', port=6379)
    print('Evaluating retrieval quality...\n')
    
    metrics = {
        'hnsw': {'p@5': [], 'p@10': [], 'r@10': [], 'mrr': []},
        'hipporag': {'p@5': [], 'p@10': [], 'r@10': [], 'mrr': []},
        'hybrid': {'p@5': [], 'p@10': [], 'r@10': [], 'mrr': []},
    }
    
    for case in TEST_CASES:
        query = case['query']
        relevant = case['relevant']
        
        print(f"Query: '{query}'")
        print(f"  Relevant entities: {len(relevant)}")
        
        emb = get_embedding(query)
        
        # HNSW
        hnsw_results = hnsw_search(r, emb, 10)
        hnsw_names = [name for name, _ in hnsw_results]
        metrics['hnsw']['p@5'].append(precision_at_k(hnsw_names, relevant, 5))
        metrics['hnsw']['p@10'].append(precision_at_k(hnsw_names, relevant, 10))
        metrics['hnsw']['r@10'].append(recall_at_k(hnsw_names, relevant, 10))
        metrics['hnsw']['mrr'].append(mrr(hnsw_names, relevant))
        
        # HippoRAG
        hippo_results = hipporag_search(r, emb, 10)
        hippo_names = [name for name, _ in hippo_results]
        metrics['hipporag']['p@5'].append(precision_at_k(hippo_names, relevant, 5))
        metrics['hipporag']['p@10'].append(precision_at_k(hippo_names, relevant, 10))
        metrics['hipporag']['r@10'].append(recall_at_k(hippo_names, relevant, 10))
        metrics['hipporag']['mrr'].append(mrr(hippo_names, relevant))
        
        # Hybrid
        hybrid_results = hybrid_search(r, emb, 10, 0.7)
        hybrid_names = [name for name, _ in hybrid_results]
        metrics['hybrid']['p@5'].append(precision_at_k(hybrid_names, relevant, 5))
        metrics['hybrid']['p@10'].append(precision_at_k(hybrid_names, relevant, 10))
        metrics['hybrid']['r@10'].append(recall_at_k(hybrid_names, relevant, 10))
        metrics['hybrid']['mrr'].append(mrr(hybrid_names, relevant))
        
        print(f"  HNSW:    P@5={metrics['hnsw']['p@5'][-1]:.2f} P@10={metrics['hnsw']['p@10'][-1]:.2f} R@10={metrics['hnsw']['r@10'][-1]:.2f} MRR={metrics['hnsw']['mrr'][-1]:.2f}")
        print(f"  HippoRAG: P@5={metrics['hipporag']['p@5'][-1]:.2f} P@10={metrics['hipporag']['p@10'][-1]:.2f} R@10={metrics['hipporag']['r@10'][-1]:.2f} MRR={metrics['hipporag']['mrr'][-1]:.2f}")
        print(f"  Hybrid:  P@5={metrics['hybrid']['p@5'][-1]:.2f} P@10={metrics['hybrid']['p@10'][-1]:.2f} R@10={metrics['hybrid']['r@10'][-1]:.2f} MRR={metrics['hybrid']['mrr'][-1]:.2f}")
        print()
    
    print('=' * 60)
    print('AGGREGATE METRICS (averaged across all queries)')
    print('=' * 60)
    print(f"{'Method':<12} {'P@5':>8} {'P@10':>8} {'R@10':>8} {'MRR':>8}")
    print('-' * 60)
    for method in ['hnsw', 'hipporag', 'hybrid']:
        avg_p5 = sum(metrics[method]['p@5']) / len(metrics[method]['p@5'])
        avg_p10 = sum(metrics[method]['p@10']) / len(metrics[method]['p@10'])
        avg_r10 = sum(metrics[method]['r@10']) / len(metrics[method]['r@10'])
        avg_mrr = sum(metrics[method]['mrr']) / len(metrics[method]['mrr'])
        print(f"{method:<12} {avg_p5:>8.3f} {avg_p10:>8.3f} {avg_r10:>8.3f} {avg_mrr:>8.3f}")
    
    print()
    print("Legend:")
    print("  P@K  = Precision at K (fraction of top-K that are relevant)")
    print("  R@K  = Recall at K (fraction of relevant items found in top-K)")
    print("  MRR  = Mean Reciprocal Rank (1/rank of first relevant result)")


if __name__ == '__main__':
    evaluate()
