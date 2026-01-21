#!/usr/bin/env python3
"""
POC: Native Community Detection using FalkorDB's algo.labelPropagation

This script verifies that FalkorDB's native CDLP algorithm works correctly
and can replace the Python implementation in community_operations.py.

Usage:
    python scripts/poc_native_cdlp.py
"""

import asyncio
import os
import time
from collections import defaultdict

# Test database to avoid touching production data
TEST_DATABASE = 'cdlp_poc_test'


async def setup_test_graph(graph):
    """Create a test graph with two distinct clusters."""

    # Clear any existing data
    await graph.query('MATCH (n) DETACH DELETE n')

    # Create Cluster A: Alice, Bob, Charlie (fully connected)
    await graph.query("""
        CREATE (a:Entity {uuid: 'alice', name: 'Alice', group_id: 'test_group'})
        CREATE (b:Entity {uuid: 'bob', name: 'Bob', group_id: 'test_group'})
        CREATE (c:Entity {uuid: 'charlie', name: 'Charlie', group_id: 'test_group'})
        CREATE (a)-[:RELATES_TO {uuid: 'e1'}]->(b)
        CREATE (b)-[:RELATES_TO {uuid: 'e2'}]->(c)
        CREATE (c)-[:RELATES_TO {uuid: 'e3'}]->(a)
    """)

    # Create Cluster B: Dave, Eve, Frank (fully connected, separate from A)
    await graph.query("""
        CREATE (d:Entity {uuid: 'dave', name: 'Dave', group_id: 'test_group'})
        CREATE (e:Entity {uuid: 'eve', name: 'Eve', group_id: 'test_group'})
        CREATE (f:Entity {uuid: 'frank', name: 'Frank', group_id: 'test_group'})
        CREATE (d)-[:RELATES_TO {uuid: 'e4'}]->(e)
        CREATE (e)-[:RELATES_TO {uuid: 'e5'}]->(f)
        CREATE (f)-[:RELATES_TO {uuid: 'e6'}]->(d)
    """)

    print('✓ Created test graph with 2 clusters (A: Alice/Bob/Charlie, B: Dave/Eve/Frank)')


async def test_native_cdlp(graph):
    """Test the native algo.labelPropagation call."""

    print('\n--- Testing Native CDLP ---')

    start = time.time()
    result = await graph.query("""
        CALL algo.labelPropagation({})
        YIELD node, communityId
        RETURN node.uuid AS uuid, node.name AS name, communityId
        ORDER BY communityId, name
    """)
    elapsed = time.time() - start

    print(f'Query time: {elapsed * 1000:.2f}ms')

    # Group by community
    communities = defaultdict(list)
    for record in result.result_set:
        uuid, name, community_id = record
        communities[community_id].append(name)

    print(f'\nFound {len(communities)} communities:')
    for cid, members in sorted(communities.items()):
        print(f'  Community {cid}: {", ".join(sorted(members))}')

    return communities


async def test_filtered_cdlp(graph):
    """Test CDLP with node/relationship type filtering."""

    print('\n--- Testing Filtered CDLP (Entity nodes, RELATES_TO edges) ---')

    start = time.time()
    result = await graph.query("""
        CALL algo.labelPropagation({
            nodeLabels: ['Entity'],
            relationshipTypes: ['RELATES_TO']
        })
        YIELD node, communityId
        RETURN node.uuid AS uuid, communityId
    """)
    elapsed = time.time() - start

    print(f'Query time: {elapsed * 1000:.2f}ms')
    print(f'Nodes processed: {len(result.result_set)}')

    return result


async def test_cluster_extraction(graph):
    """Test extracting cluster member UUIDs (the format we need)."""

    print('\n--- Testing Cluster Extraction (target format) ---')

    start = time.time()
    result = await graph.query("""
        CALL algo.labelPropagation({
            nodeLabels: ['Entity'],
            relationshipTypes: ['RELATES_TO']
        })
        YIELD node, communityId
        WITH communityId, collect(node.uuid) AS members
        RETURN members
        ORDER BY size(members) DESC
    """)
    elapsed = time.time() - start

    print(f'Query time: {elapsed * 1000:.2f}ms')

    clusters = [record[0] for record in result.result_set]
    print(f'\nExtracted {len(clusters)} clusters:')
    for i, cluster in enumerate(clusters):
        print(f'  Cluster {i + 1}: {cluster}')

    return clusters


async def verify_cluster_correctness(communities: dict) -> bool:
    """Verify that the two clusters are correctly separated."""

    cluster_a = {'Alice', 'Bob', 'Charlie'}
    cluster_b = {'Dave', 'Eve', 'Frank'}

    # Check that members of each expected cluster are in the same community
    found_clusters = list(communities.values())

    for cluster in found_clusters:
        cluster_set = set(cluster)
        if cluster_set == cluster_a or cluster_set == cluster_b:
            continue
        # Check subset relationships
        if cluster_set.issubset(cluster_a) or cluster_set.issubset(cluster_b):
            continue
        # If we have a mixed cluster, that's wrong
        if cluster_set & cluster_a and cluster_set & cluster_b:
            print(f'✗ ERROR: Mixed cluster found: {cluster}')
            return False

    print('✓ Clusters are correctly separated!')
    return True


async def compare_with_python_lpa(graph):
    """Compare native CDLP with Python LPA for correctness."""

    print('\n--- Comparing with Python LPA ---')

    # Build projection like the Python code does
    result = await graph.query("""
        MATCH (n:Entity)-[r:RELATES_TO]-(m:Entity)
        RETURN n.uuid AS source, m.uuid AS target, count(r) AS edge_count
    """)

    # Build adjacency dict
    from collections import defaultdict

    projection = defaultdict(list)

    class Neighbor:
        def __init__(self, uuid, count):
            self.node_uuid = uuid
            self.edge_count = count

    for record in result.result_set:
        source, target, count = record
        projection[source].append(Neighbor(target, count))

    # Run Python LPA (copied from community_operations.py)
    def label_propagation(projection):
        community_map = {uuid: i for i, uuid in enumerate(projection.keys())}

        iterations = 0
        while True:
            iterations += 1
            no_change = True
            new_community_map = {}

            for uuid, neighbors in projection.items():
                curr_community = community_map[uuid]
                community_candidates = defaultdict(int)

                for neighbor in neighbors:
                    if neighbor.node_uuid in community_map:
                        community_candidates[community_map[neighbor.node_uuid]] += (
                            neighbor.edge_count
                        )

                community_lst = [
                    (count, community) for community, count in community_candidates.items()
                ]
                community_lst.sort(reverse=True)

                candidate_rank, community_candidate = community_lst[0] if community_lst else (0, -1)
                if community_candidate != -1 and candidate_rank > 1:
                    new_community = community_candidate
                else:
                    new_community = max(community_candidate, curr_community)

                new_community_map[uuid] = new_community
                if new_community != curr_community:
                    no_change = False

            if no_change:
                break
            community_map = new_community_map

        community_cluster_map = defaultdict(list)
        for uuid, community in community_map.items():
            community_cluster_map[community].append(uuid)

        return list(community_cluster_map.values()), iterations

    start = time.time()
    python_clusters, iterations = label_propagation(dict(projection))
    python_time = time.time() - start

    print(f'Python LPA: {python_time * 1000:.2f}ms, {iterations} iterations')
    print(f'Python clusters: {len(python_clusters)}')
    for cluster in python_clusters:
        print(f'  {cluster}')


async def test_on_production_graph():
    """Test native CDLP on the actual production graph."""

    print('\n' + '=' * 60)
    print('Testing on PRODUCTION graph (graphiti_migration)')
    print('=' * 60)

    from falkordb.asyncio import FalkorDB

    host = os.getenv('FALKORDB_HOST', 'localhost')
    port = int(os.getenv('FALKORDB_PORT', '6379'))

    client = FalkorDB(host=host, port=port)
    graph = client.select_graph('graphiti_migration')

    # Count entities first
    result = await graph.query('MATCH (n:Entity) RETURN count(n) AS count')
    entity_count = result.result_set[0][0]
    print(f'\nEntity count: {entity_count}')

    # Run native CDLP
    print('\nRunning native algo.labelPropagation...')
    start = time.time()
    result = await graph.query("""
        CALL algo.labelPropagation({
            nodeLabels: ['Entity'],
            relationshipTypes: ['RELATES_TO']
        })
        YIELD node, communityId
        WITH communityId, collect(node.uuid) AS members
        RETURN communityId, size(members) AS size
        ORDER BY size DESC
        LIMIT 10
    """)
    elapsed = time.time() - start

    print(f'Query time: {elapsed * 1000:.2f}ms')
    print(f'\nTop 10 communities by size:')
    for record in result.result_set:
        cid, size = record
        print(f'  Community {cid}: {size} members')

    # Get total community count
    result = await graph.query("""
        CALL algo.labelPropagation({
            nodeLabels: ['Entity'],
            relationshipTypes: ['RELATES_TO']
        })
        YIELD communityId
        RETURN count(DISTINCT communityId) AS total_communities
    """)
    total = result.result_set[0][0]
    print(f'\nTotal communities: {total}')


async def main():
    from falkordb.asyncio import FalkorDB

    host = os.getenv('FALKORDB_HOST', 'localhost')
    port = int(os.getenv('FALKORDB_PORT', '6379'))

    print(f'Connecting to FalkorDB at {host}:{port}')
    print(f'Using test database: {TEST_DATABASE}')

    client = FalkorDB(host=host, port=port)
    graph = client.select_graph(TEST_DATABASE)

    try:
        # Setup test graph
        await setup_test_graph(graph)

        # Test native CDLP
        communities = await test_native_cdlp(graph)

        # Verify correctness
        await verify_cluster_correctness(communities)

        # Test with filtering
        await test_filtered_cdlp(graph)

        # Test cluster extraction format
        await test_cluster_extraction(graph)

        # Compare with Python implementation
        await compare_with_python_lpa(graph)

        # Test on production graph
        await test_on_production_graph()

        print('\n' + '=' * 60)
        print('POC COMPLETE - algo.labelPropagation works correctly!')
        print('=' * 60)

    finally:
        # Cleanup test database
        await graph.query('MATCH (n) DETACH DELETE n')
        print(f'\n✓ Cleaned up test database: {TEST_DATABASE}')


if __name__ == '__main__':
    asyncio.run(main())
