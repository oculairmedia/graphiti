#!/usr/bin/env python3
"""Evaluate hybrid search with expanded ground truth including contextual relationships."""

import math
import httpx
import redis

EMBEDDING_URL = 'http://100.81.139.20:11450/v1/embeddings'
EMBEDDING_MODEL = 'qwen3-embedding'

# Expanded ground truth: semantic matches + contextual relationships
TEST_CASES = [
    {
        'query': 'Emmanuel',
        'semantic': {'Emmanuel', 'emmanuel umukoro', 'emmanuel_bernard', 'emmanuelbernard'},
        'contextual': {'Claude', 'Letta', 'graphiti', 'matrix', 'opencode', 'huly', 
                       'falkordb', 'temporal', 'assistant', 'agentassistant'},
    },
    {
        'query': 'Graphiti knowledge graph',
        'semantic': {'Graphiti knowledge graph', 'graphiti', 'graphiti_knowledge_graph',
                     'knowledge_graph', 'knowledge graph'},
        'contextual': {'falkordb', 'neo4j', 'temporal', 'ingestion', 'entity', 'edge',
                       'embedding', 'vector', 'agentassistant', 'Claude'},
    },
    {
        'query': 'Temporal workflow',
        'semantic': {'Temporal', 'temporal', 'Temporal workflows', 'temporalio',
                     'workflow', 'workflows', 'temporal.io'},
        'contextual': {'activity', 'worker', 'ingestion', 'graphiti', 'docker-compose',
                       'python', 'docker', 'container', 'Letta'},
    },
    {
        'query': 'FalkorDB database',  
        'semantic': {'FalkorDB', 'falkordb', 'FalkorDB database', 'FALKORDB_DATABASE'},
        'contextual': {'redis', 'graph', 'graphiti', 'vector', 'HNSW', 'docker',
                       'Claude', 'assistant', 'Entity'},
    },
    {
        'query': 'project management',
        'semantic': {'project management', 'project_manager', 'project'},
        'contextual': {'huly', 'hully', 'task', 'issue', 'agent', 'graphiti',
                       'claude_code', 'development_subagents'},
    },
]


def get_embedding(text: str) -> list[float]:
    response = httpx.post(EMBEDDING_URL, json={'model': EMBEDDING_MODEL, 'input': text}, timeout=30.0)
    response.raise_for_status()
    return response.json()['data'][0]['embedding']


def hnsw_search(r, embedding: list[float], top_k: int = 10) -> list[str]:
    emb_str = ','.join(map(str, embedding))
    query = f"""
        CALL db.idx.vector.queryNodes('Entity', 'name_embedding', {top_k}, vecf32([{emb_str}]))
        YIELD node, score RETURN node.name ORDER BY score ASC
    """
    result = r.execute_command('GRAPH.QUERY', 'graphiti_migration', query)
    return [row[0].decode() if isinstance(row[0], bytes) else row[0] for row in (result[1] if result and len(result) > 1 else [])]


def hipporag_search(r, embedding: list[float], top_k: int = 10) -> list[str]:
    emb_str = ','.join(map(str, embedding))
    seed_query = f"""
        CALL db.idx.vector.queryNodes('Entity', 'name_embedding', 5, vecf32([{emb_str}]))
        YIELD node, score RETURN node.uuid, node.name, score ORDER BY score ASC
    """
    result = r.execute_command('GRAPH.QUERY', 'graphiti_migration', seed_query)
    seeds = []
    seed_scores = {}
    for row in (result[1] if result and len(result) > 1 else []):
        uuid = row[0].decode() if isinstance(row[0], bytes) else row[0]
        sim = 1.0 - float(row[2].decode() if isinstance(row[2], bytes) else row[2])
        seeds.append(uuid)
        seed_scores[uuid] = sim
    
    if not seeds:
        return []
    
    prop_query = f"""
        MATCH path = (seed:Entity)-[*1..2]-(target:Entity)
        WHERE seed.uuid IN {str(seeds)} AND seed <> target
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
        weighted = activation * max((seed_scores.get(s, 0.5) for s in contributing), default=0.5)
        results.append((name, weighted))
    results.sort(key=lambda x: x[1], reverse=True)
    return [name for name, _ in results[:top_k]]


def hybrid_search(r, embedding: list[float], top_k: int = 10, vector_weight: float = 0.7) -> list[str]:
    emb_str = ','.join(map(str, embedding))
    
    seed_query = f"""
        CALL db.idx.vector.queryNodes('Entity', 'name_embedding', {top_k}, vecf32([{emb_str}]))
        YIELD node, score RETURN node.uuid, node.name, score ORDER BY score ASC
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
    
    neighbor_query = f"""
        MATCH path = (seed:Entity)-[*1..2]-(neighbor:Entity)
        WHERE seed.uuid IN {str(seed_uuids)} AND neighbor.name_embedding IS NOT NULL
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
        
        graph_score = sum(0.5 ** h * seed_sims.get(s, 0.5) for s, h in zip(contributing, hops))
        
        if uuid in candidates:
            candidates[uuid]['graph'] = max(candidates[uuid]['graph'], graph_score)
        else:
            neighbor_uuids.append(uuid)
            candidates[uuid] = {'name': name, 'vector': 0.0, 'graph': graph_score}
    
    if neighbor_uuids:
        vec_query = f"""
            CALL db.idx.vector.queryNodes('Entity', 'name_embedding', {len(neighbor_uuids) * 2}, vecf32([{emb_str}]))
            YIELD node, score WHERE node.uuid IN {str(neighbor_uuids)}
            RETURN node.uuid, score
        """
        result = r.execute_command('GRAPH.QUERY', 'graphiti_migration', vec_query)
        for row in (result[1] if result and len(result) > 1 else []):
            uuid = row[0].decode() if isinstance(row[0], bytes) else row[0]
            sim = 1.0 - float(row[1].decode() if isinstance(row[1], bytes) else row[1])
            if uuid in candidates:
                candidates[uuid]['vector'] = sim
    
    graph_weight = 1.0 - vector_weight
    results = [(d['name'], vector_weight * d['vector'] + graph_weight * d['graph']) for d in candidates.values()]
    results.sort(key=lambda x: x[1], reverse=True)
    return [name for name, _ in results[:top_k]]


def matches(retrieved: str, ground_truth: set[str]) -> bool:
    r_lower = retrieved.lower()
    return any(gt.lower() in r_lower or r_lower in gt.lower() for gt in ground_truth)


def semantic_hits(retrieved: list[str], semantic: set[str], k: int) -> int:
    return sum(1 for r in retrieved[:k] if matches(r, semantic))


def contextual_hits(retrieved: list[str], contextual: set[str], k: int) -> int:
    return sum(1 for r in retrieved[:k] if matches(r, contextual))


def evaluate():
    r = redis.Redis(host='localhost', port=6379)
    print('Evaluating retrieval quality (semantic + contextual)...\n')
    
    totals = {
        'hnsw': {'sem': 0, 'ctx': 0, 'total': 0},
        'hipporag': {'sem': 0, 'ctx': 0, 'total': 0},
        'hybrid': {'sem': 0, 'ctx': 0, 'total': 0},
    }
    
    for case in TEST_CASES:
        query = case['query']
        semantic = case['semantic']
        contextual = case['contextual']
        
        print(f"Query: '{query}'")
        emb = get_embedding(query)
        
        for method, search_fn in [('hnsw', hnsw_search), ('hipporag', hipporag_search), ('hybrid', hybrid_search)]:
            results = search_fn(r, emb, 10) if method != 'hybrid' else hybrid_search(r, emb, 10, 0.5)
            sem = semantic_hits(results, semantic, 10)
            ctx = contextual_hits(results, contextual, 10)
            totals[method]['sem'] += sem
            totals[method]['ctx'] += ctx
            totals[method]['total'] += sem + ctx
            print(f"  {method:>8}: semantic={sem}/{len(semantic)} contextual={ctx}/{len(contextual)} total={sem+ctx}")
        print()
    
    print('=' * 70)
    print('AGGREGATE (sum across all queries)')
    print('=' * 70)
    print(f"{'Method':<12} {'Semantic':>10} {'Contextual':>12} {'Total':>10} {'Improvement':>12}")
    print('-' * 70)
    
    baseline = totals['hnsw']['total']
    for method in ['hnsw', 'hipporag', 'hybrid']:
        sem = totals[method]['sem']
        ctx = totals[method]['ctx']
        total = totals[method]['total']
        improvement = ((total - baseline) / baseline * 100) if baseline > 0 else 0
        print(f"{method:<12} {sem:>10} {ctx:>12} {total:>10} {improvement:>+11.1f}%")


if __name__ == '__main__':
    evaluate()
