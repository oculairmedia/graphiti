#!/usr/bin/env python3
"""Fast centrality calculation with batched UNWIND writes."""

import math
import random
import time
from collections import defaultdict, deque

import falkordb


def main():
    db = falkordb.FalkorDB(host='localhost', port=6379)
    g = db.select_graph('graphiti_migration')

    # Load entity UUIDs
    print('Loading entities...')
    result = g.query('MATCH (n:Entity) RETURN n.uuid')
    node_ids = [r[0] for r in result.result_set]
    num_nodes = len(node_ids)
    node_set = set(node_ids)
    print(f'  {num_nodes} entities')

    # Load RELATES_TO edges
    print('Loading edges...')
    result = g.query('MATCH (s:Entity)-[:RELATES_TO]->(t:Entity) RETURN s.uuid, t.uuid')
    edges = result.result_set
    print(f'  {len(edges)} edges')

    # === PAGERANK ===
    t0 = time.time()
    print('PageRank...')
    incoming = defaultdict(list)
    out_degree = defaultdict(int)
    for src, tgt in edges:
        if src in node_set and tgt in node_set:
            incoming[tgt].append(src)
            out_degree[src] += 1

    damping = 0.85
    initial = 1.0 / num_nodes
    pagerank = {nid: initial for nid in node_ids}
    for _ in range(20):
        new_pr = {}
        for nid in node_ids:
            rank_sum = sum(pagerank[s] / max(out_degree[s], 1) for s in incoming.get(nid, []))
            new_pr[nid] = (1 - damping) / num_nodes + damping * rank_sum
        pagerank = new_pr
    print(f'  done in {time.time() - t0:.1f}s')

    # === DEGREE ===
    t0 = time.time()
    degree = defaultdict(int)
    for src, tgt in edges:
        if src in node_set:
            degree[src] += 1
        if tgt in node_set:
            degree[tgt] += 1
    max_possible = max(num_nodes - 1, 1)
    degree_norm = {nid: degree.get(nid, 0) / max_possible for nid in node_ids}
    print(f'Degree done in {time.time() - t0:.1f}s')

    # === BETWEENNESS (sampled) ===
    t0 = time.time()
    sample_size = min(50, num_nodes)
    print(f'Betweenness (sample={sample_size})...')
    adjacency = defaultdict(list)
    for src, tgt in edges:
        if src in node_set and tgt in node_set:
            adjacency[src].append(tgt)

    sources = random.sample(node_ids, sample_size)
    betweenness = {nid: 0.0 for nid in node_ids}
    for source in sources:
        stack, preds, sigma, dist = [], defaultdict(list), defaultdict(int), {source: 0}
        sigma[source] = 1
        queue = deque([source])
        while queue:
            v = queue.popleft()
            stack.append(v)
            for w in adjacency.get(v, []):
                if w not in dist:
                    dist[w] = dist[v] + 1
                    queue.append(w)
                if dist.get(w) == dist[v] + 1:
                    sigma[w] += sigma[v]
                    preds[w].append(v)
        delta = defaultdict(float)
        while stack:
            w = stack.pop()
            for v in preds[w]:
                delta[v] += (sigma[v] / sigma[w]) * (1.0 + delta[w])
            if w != source:
                betweenness[w] += delta[w]
    if num_nodes > 2:
        scale = num_nodes / sample_size
        norm_factor = scale / ((num_nodes - 1) * (num_nodes - 2))
        betweenness = {k: v * norm_factor for k, v in betweenness.items()}
    print(f'  done in {time.time() - t0:.1f}s')

    # === IMPORTANCE ===
    importance = {}
    for nid in node_ids:
        pr = pagerank.get(nid, 0.0) * 1000
        dg = math.log(degree.get(nid, 0) + 1)
        bw = betweenness.get(nid, 0.0) * 100
        importance[nid] = 0.5 * pr + 0.3 * dg + 0.2 * bw

    # === BATCH STORE WITH UNWIND ===
    BATCH = 500
    t0 = time.time()
    print(f'\nStoring {num_nodes} nodes (batch={BATCH})...')
    stored = 0
    for i in range(0, num_nodes, BATCH):
        batch = node_ids[i : i + BATCH]
        rows = []
        for nid in batch:
            rows.append(
                {
                    'uuid': nid,
                    'pr': float(pagerank.get(nid, 0.0)),
                    'dg': float(degree_norm.get(nid, 0.0)),
                    'bw': float(betweenness.get(nid, 0.0)),
                    'imp': float(importance.get(nid, 0.0)),
                }
            )
        try:
            g.query(
                """UNWIND $rows AS row
                   MATCH (n:Entity {uuid: row.uuid})
                   SET n.pagerank_centrality = row.pr,
                       n.degree_centrality = row.dg,
                       n.betweenness_centrality = row.bw,
                       n.importance_score = row.imp""",
                params={'rows': rows},
            )
            stored += len(batch)
        except Exception as e:
            print(f'  Batch error at {i}: {e}')
            # Fall back to smaller batches
            for nid in batch:
                try:
                    g.query(
                        'MATCH (n:Entity {uuid: $uuid}) SET n.pagerank_centrality = $pr, n.degree_centrality = $dg, n.betweenness_centrality = $bw, n.importance_score = $imp',
                        params={
                            'uuid': nid,
                            'pr': float(pagerank.get(nid, 0.0)),
                            'dg': float(degree_norm.get(nid, 0.0)),
                            'bw': float(betweenness.get(nid, 0.0)),
                            'imp': float(importance.get(nid, 0.0)),
                        },
                    )
                    stored += 1
                except Exception as e2:
                    print(f'    Single write error {nid[:8]}: {e2}')
        if stored % 5000 == 0 or stored == num_nodes:
            print(f'  {stored}/{num_nodes}')

    print(f'Storage done in {time.time() - t0:.1f}s')

    # === VERIFY ===
    result = g.query('MATCH (n:Entity) WHERE n.pagerank_centrality > 0 RETURN count(n)')
    print(f'\nEntities with pagerank > 0: {result.result_set[0][0]}')

    result = g.query(
        'MATCH (n:Entity) RETURN n.name, n.pagerank_centrality, n.degree_centrality, n.importance_score ORDER BY n.importance_score DESC LIMIT 10'
    )
    print('\nTop 10 by importance:')
    for row in result.result_set:
        print(f'  {row[0]}: pr={row[1]:.6f}, deg={row[2]:.6f}, imp={row[3]:.4f}')


if __name__ == '__main__':
    main()
