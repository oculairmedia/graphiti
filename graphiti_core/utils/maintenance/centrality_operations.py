"""
Copyright 2024, Zep Software, Inc.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import asyncio
import random
from collections import defaultdict, deque
import logging
import math
import os
from typing import Dict, List, Optional, Tuple

from graphiti_core.driver.driver import GraphDriver
from graphiti_core.nodes import EntityNode

logger = logging.getLogger(__name__)

# Import Rust client if available
try:
    from .rust_centrality_client import RustCentralityClient

    _rust_client = None

    def _get_rust_client() -> RustCentralityClient:
        global _rust_client
        if _rust_client is None:
            _rust_client = RustCentralityClient()
        return _rust_client

    RUST_AVAILABLE = True
except ImportError:
    logger.warning('Rust centrality client not available, falling back to Python implementation')
    RUST_AVAILABLE = False

    def _get_rust_client():
        raise ImportError('Rust centrality client not available')


def _should_use_rust() -> bool:
    """Check if we should use the Rust centrality service."""
    return RUST_AVAILABLE and os.getenv('USE_RUST_CENTRALITY', 'false').lower() in (
        'true',
        '1',
        'yes',
    )


async def calculate_pagerank(
    driver: GraphDriver,
    damping_factor: float = 0.85,
    iterations: int = 20,
    group_id: Optional[str] = None,
) -> Dict[str, float]:
    """
    Calculate PageRank centrality for all nodes in the graph.

    Args:
        driver: Graph database driver
        damping_factor: Probability of following an edge (default 0.85)
        iterations: Number of iterations for convergence (default 20)
        group_id: Optional group ID to filter nodes

    Returns:
        Dictionary mapping node UUIDs to PageRank scores
    """
    # Route to Rust service if enabled
    if _should_use_rust():
        try:
            logger.info('Using Rust centrality service for PageRank calculation')
            client = _get_rust_client()
            return await client.calculate_pagerank(
                damping_factor=damping_factor,
                iterations=iterations,
                group_id=group_id,
                store_results=False,  # Don't store from proxy layer
            )
        except Exception as e:
            logger.error(f'Rust centrality service failed, falling back to Python: {e}')
            # Fall through to Python implementation

    logger.info(f'Calculating PageRank with damping={damping_factor}, iterations={iterations}')

    # Get all nodes
    if group_id:
        nodes_query = """
        MATCH (n)
        WHERE n.group_id = $group_id
        RETURN n.uuid AS uuid
        """
        records, _, _ = await driver.execute_query(nodes_query, group_id=group_id)
    else:
        nodes_query = """
        MATCH (n)
        RETURN n.uuid AS uuid
        """
        records, _, _ = await driver.execute_query(nodes_query)

    node_ids = [record['uuid'] for record in records]
    num_nodes = len(node_ids)

    if num_nodes == 0:
        return {}

    # Load ALL edges once — O(1) query instead of O(n²) per iteration
    if group_id:
        edges_query = """
        MATCH (source)-[e]->(target)
        WHERE source.group_id = $group_id OR target.group_id = $group_id
        RETURN source.uuid AS source_id, target.uuid AS target_id
        """
        edge_records, _, _ = await driver.execute_query(edges_query, group_id=group_id)
    else:
        edges_query = """
        MATCH (source)-[e]->(target)
        RETURN source.uuid AS source_id, target.uuid AS target_id
        """
        edge_records, _, _ = await driver.execute_query(edges_query)

    # Build adjacency structures in memory

    incoming: Dict[str, List[str]] = defaultdict(list)  # target -> [source, ...]
    out_degree: Dict[str, int] = defaultdict(int)  # source -> count

    node_set = set(node_ids)
    for record in edge_records:
        src = record['source_id']
        tgt = record['target_id']
        if src in node_set and tgt in node_set:
            incoming[tgt].append(src)
            out_degree[src] += 1

    logger.info(
        f'Loaded {len(edge_records)} edges for {num_nodes} nodes — running {iterations} iterations in-memory'
    )

    # Initialize PageRank scores
    initial_score = 1.0 / num_nodes
    pagerank = {node_id: initial_score for node_id in node_ids}

    # Run PageRank iterations — pure Python, zero DB queries
    for iteration in range(iterations):
        new_pagerank = {}

        for node_id in node_ids:
            rank_sum = 0.0
            for source_id in incoming.get(node_id, []):
                rank_sum += pagerank.get(source_id, initial_score) / max(out_degree.get(source_id, 1), 1)

            new_pagerank[node_id] = (1 - damping_factor) / num_nodes + damping_factor * rank_sum

        pagerank = new_pagerank

        if iteration % 5 == 0:
            logger.debug(f'PageRank iteration {iteration + 1}/{iterations}')

    logger.info(
        f'PageRank calculation complete. Scores range: {min(pagerank.values()):.4f} - {max(pagerank.values()):.4f}'
    )
    return pagerank


async def calculate_degree_centrality(
    driver: GraphDriver,
    direction: str = 'both',
    group_id: Optional[str] = None,
) -> Dict[str, Dict[str, int]]:
    """
    Calculate degree centrality (number of connections) for all nodes.

    Args:
        driver: Graph database driver
        direction: "in", "out", or "both" for edge direction
        group_id: Optional group ID to filter nodes

    Returns:
        Dictionary mapping node UUIDs to degree counts
    """
    # Route to Rust service if enabled
    if _should_use_rust():
        try:
            logger.info('Using Rust centrality service for degree centrality calculation')
            client = _get_rust_client()
            return await client.calculate_degree_centrality(
                direction=direction,
                group_id=group_id,
                store_results=False,  # Don't store from proxy layer
            )
        except Exception as e:
            logger.error(f'Rust centrality service failed, falling back to Python: {e}')
            # Fall through to Python implementation

    logger.info(f'Calculating degree centrality with direction={direction}')

    where_clause = 'WHERE n.group_id = $group_id' if group_id else ''
    params = {'group_id': group_id} if group_id else {}

    if direction == 'both':
        query = f"""
        MATCH (n)
        {where_clause}
        OPTIONAL MATCH (n)-[e]-()
        RETURN n.uuid AS uuid, 
               count(DISTINCT e) AS total_degree
        """
    elif direction == 'in':
        query = f"""
        MATCH (n)
        {where_clause}
        OPTIONAL MATCH ()-[e]->(n)
        RETURN n.uuid AS uuid, 
               count(DISTINCT e) AS in_degree
        """
    elif direction == 'out':
        query = f"""
        MATCH (n)
        {where_clause}
        OPTIONAL MATCH (n)-[e]->()
        RETURN n.uuid AS uuid, 
               count(DISTINCT e) AS out_degree
        """
    else:
        raise ValueError(f"Invalid direction: {direction}. Must be 'in', 'out', or 'both'")

    records, _, _ = await driver.execute_query(query, **params)

    if direction == 'both':
        degrees = {record['uuid']: {'total': record['total_degree']} for record in records}
    elif direction == 'in':
        degrees = {record['uuid']: {'in': record['in_degree']} for record in records}
    else:
        degrees = {record['uuid']: {'out': record['out_degree']} for record in records}

    logger.info(f'Degree centrality calculation complete for {len(degrees)} nodes')
    return degrees


async def calculate_betweenness_centrality(
    driver: GraphDriver,
    sample_size: Optional[int] = None,
    group_id: Optional[str] = None,
) -> Dict[str, float]:
    """
    Calculate betweenness centrality using sampling for efficiency.

    Betweenness centrality measures how often a node appears on shortest paths
    between other nodes, indicating its importance as a bridge.

    Args:
        driver: Graph database driver
        sample_size: Number of nodes to sample (None for all nodes)
        group_id: Optional group ID to filter nodes

    Returns:
        Dictionary mapping node UUIDs to betweenness scores
    """
    # Route to Rust service if enabled
    if _should_use_rust():
        try:
            logger.info('Using Rust centrality service for betweenness centrality calculation')
            client = _get_rust_client()
            return await client.calculate_betweenness_centrality(
                sample_size=sample_size,
                group_id=group_id,
                store_results=False,  # Don't store from proxy layer
            )
        except Exception as e:
            logger.error(f'Rust centrality service failed, falling back to Python: {e}')
            # Fall through to Python implementation

    logger.info(f'Calculating betweenness centrality with sample_size={sample_size}')

    # Get all nodes
    if group_id:
        nodes_query = """
        MATCH (n)
        WHERE n.group_id = $group_id
        RETURN n.uuid AS uuid
        """
        records, _, _ = await driver.execute_query(nodes_query, group_id=group_id)
    else:
        nodes_query = """
        MATCH (n)
        RETURN n.uuid AS uuid
        """
        records, _, _ = await driver.execute_query(nodes_query)

    all_node_ids = [record['uuid'] for record in records]
    num_nodes = len(all_node_ids)

    if num_nodes == 0:
        return {}

    # Load ALL edges once — O(1) query instead of O(n²) shortestPath queries
    if group_id:
        edges_query = """
        MATCH (source)-[e]->(target)
        WHERE source.group_id = $group_id OR target.group_id = $group_id
        RETURN source.uuid AS source_id, target.uuid AS target_id
        """
        edge_records, _, _ = await driver.execute_query(edges_query, group_id=group_id)
    else:
        edges_query = """
        MATCH (source)-[e]->(target)
        RETURN source.uuid AS source_id, target.uuid AS target_id
        """
        edge_records, _, _ = await driver.execute_query(edges_query)

    # Build adjacency list in memory (directed: source -> [targets])


    adjacency: Dict[str, List[str]] = defaultdict(list)
    node_set = set(all_node_ids)

    for record in edge_records:
        src = record['source_id']
        tgt = record['target_id']
        if src in node_set and tgt in node_set:
            adjacency[src].append(tgt)

    logger.info(
        f'Loaded {len(edge_records)} edges for {num_nodes} nodes — running Brandes algorithm in-memory'
    )

    # Sample source nodes for BFS (betweenness is expensive even in-memory for large graphs)
    if sample_size and sample_size < num_nodes:

        source_nodes = random.sample(all_node_ids, sample_size)
    else:
        source_nodes = all_node_ids

    # Initialize betweenness scores for ALL nodes (not just sampled)
    betweenness: Dict[str, float] = {node_id: 0.0 for node_id in all_node_ids}

    # Brandes' algorithm: BFS from each source, accumulate dependency
    for i, source in enumerate(source_nodes):
        if i % 10 == 0:
            logger.debug(f'Brandes BFS from source {i + 1}/{len(source_nodes)}')

        # BFS / shortest path counting
        stack: List[str] = []  # nodes in order of non-increasing distance
        predecessors: Dict[str, List[str]] = defaultdict(list)
        sigma: Dict[str, int] = defaultdict(int)  # number of shortest paths
        sigma[source] = 1
        dist: Dict[str, int] = {source: 0}
        queue: deque = deque([source])

        while queue:
            v = queue.popleft()
            stack.append(v)
            for w in adjacency.get(v, []):
                # w found for the first time?
                if w not in dist:
                    dist[w] = dist[v] + 1
                    queue.append(w)
                # shortest path to w via v?
                if dist.get(w) == dist[v] + 1:
                    sigma[w] += sigma[v]
                    predecessors[w].append(v)

        # Accumulation — back-propagation of dependencies
        delta: Dict[str, float] = defaultdict(float)
        while stack:
            w = stack.pop()
            for v in predecessors[w]:
                delta[v] += (sigma[v] / sigma[w]) * (1.0 + delta[w])
            if w != source:
                betweenness[w] += delta[w]

    # Normalize scores
    # For directed graphs with sampling, normalize by n*(n-1) scaled by sampling ratio
    if num_nodes > 2:
        if sample_size and sample_size < num_nodes:
            # Scale up: we only sampled a fraction of sources
            scale = num_nodes / len(source_nodes)
            normalization = scale / ((num_nodes - 1) * (num_nodes - 2))
        else:
            normalization = 1.0 / ((num_nodes - 1) * (num_nodes - 2))
        betweenness = {k: v * normalization for k, v in betweenness.items()}

    logger.info(
        f'Betweenness centrality complete: {len(source_nodes)} source BFS runs, '
        f'{num_nodes} nodes scored'
    )
    return betweenness


async def store_centrality_scores(
    driver: GraphDriver,
    scores: Dict[str, Dict[str, float]],
    use_atomic: bool = True,
) -> None:
    """
    Store centrality scores as node properties.

    Args:
        driver: Graph database driver
        scores: Dictionary mapping node UUIDs to score dictionaries
        use_atomic: Whether to use atomic transaction-safe storage
    """
    if use_atomic:
        # Use atomic storage with transaction safety
        from .atomic_centrality_storage import AtomicCentralityStorage
        
        storage = AtomicCentralityStorage(
            driver=driver,
            batch_size=100,
            max_retries=3,
            checkpoint_interval=500,
        )
        
        try:
            transaction = await storage.store_centrality_atomic(scores)
            logger.info(
                f'Atomic storage completed: {transaction.processed_nodes}/{transaction.total_nodes} nodes, '
                f'transaction_id={transaction.transaction_id}'
            )
        except Exception as e:
            logger.error(f'Atomic storage failed: {e}')
            raise
    else:
        # Legacy non-atomic storage (kept for compatibility)
        logger.info(f'Storing centrality scores for {len(scores)} nodes (non-atomic)')

        for node_uuid, node_scores in scores.items():
            # Build SET clause for scores
            set_clauses = []
            params = {'uuid': node_uuid}

            for score_name, score_value in node_scores.items():
                set_clauses.append(f'n.centrality_{score_name} = ${score_name}')
                params[score_name] = score_value

            if set_clauses:
                query = f"""
                MATCH (n {{uuid: $uuid}})
                SET {', '.join(set_clauses)}
                """
                await driver.execute_query(query, **params)

        logger.info('Centrality scores stored successfully')


async def calculate_all_centralities(
    driver: GraphDriver,
    group_id: Optional[str] = None,
    store_results: bool = True,
) -> Dict[str, Dict[str, float]]:
    """
    Calculate all centrality metrics and optionally store them.

    Args:
        driver: Graph database driver
        group_id: Optional group ID to filter nodes
        store_results: Whether to store results in the database

    Returns:
        Dictionary mapping node UUIDs to all centrality scores
    """
    # Route to Rust service if enabled
    if _should_use_rust():
        try:
            logger.info('Using Rust centrality service for all centrality calculations')
            client = _get_rust_client()
            return await client.calculate_all_centralities(
                group_id=group_id,
                store_results=store_results,
            )
        except Exception as e:
            logger.error(f'Rust centrality service failed, falling back to Python: {e}')
            # Fall through to Python implementation

    logger.info('Calculating all centrality metrics')

    # Calculate individual metrics
    pagerank = await calculate_pagerank(driver, group_id=group_id)
    degree = await calculate_degree_centrality(driver, direction='both', group_id=group_id)

    # For large graphs, betweenness is expensive - sample
    node_count_query = 'MATCH (n) RETURN count(n) AS count'
    count_records, _, _ = await driver.execute_query(node_count_query)
    node_count = count_records[0]['count'] if count_records else 0

    sample_size = min(50, node_count) if node_count > 100 else None
    betweenness = await calculate_betweenness_centrality(
        driver, sample_size=sample_size, group_id=group_id
    )

    # Combine all scores
    all_scores = {}

    for node_id in set(pagerank.keys()) | set(degree.keys()) | set(betweenness.keys()):
        all_scores[node_id] = {
            'pagerank': pagerank.get(node_id, 0.0),
            'degree': degree.get(node_id, {}).get('total', 0),
            'betweenness': betweenness.get(node_id, 0.0),
        }

    # Calculate composite importance score
    for node_id, scores in all_scores.items():
        # Normalize and weight different metrics
        normalized_pagerank = scores['pagerank'] * 1000  # Scale up small values
        normalized_degree = math.log(scores['degree'] + 1)  # Log scale for degree
        normalized_betweenness = scores['betweenness'] * 100  # Scale up

        # Weighted combination (can be tuned)
        scores['importance'] = (
            0.5 * normalized_pagerank + 0.3 * normalized_degree + 0.2 * normalized_betweenness
        )

    if store_results:
        await store_centrality_scores(driver, all_scores)

    logger.info('All centrality calculations complete')
    return all_scores
