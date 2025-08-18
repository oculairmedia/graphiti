#!/usr/bin/env python3
"""Test script to verify merge_node_into function with centrality service."""

import asyncio
import os
from graphiti_core.utils.maintenance.node_operations import merge_node_into
from graphiti_core.driver import FalkorDriver

async def test_merge():
    # Connect to FalkorDB
    driver = FalkorDriver(
        host=os.getenv('FALKORDB_HOST', 'localhost'),
        port=int(os.getenv('FALKORDB_PORT', '6389')),
        database=os.getenv('GRAPH_NAME', 'graphiti_migration')
    )
    
    # Get two nodes to test merging
    query = """
    MATCH (n1:Entity)-[:IS_DUPLICATE_OF]->(n2:Entity)
    RETURN n1.uuid as duplicate_uuid, n2.uuid as canonical_uuid
    LIMIT 1
    """
    
    result, _, _ = await driver.execute_query(query)
    
    if not result:
        print("No duplicate nodes found for testing. Creating test duplicates...")
        # Create test nodes
        create_query = """
        CREATE (n1:Entity {uuid: 'test-duplicate-001', name: 'Test Duplicate', summary: 'Test node 1'})
        CREATE (n2:Entity {uuid: 'test-canonical-001', name: 'Test Canonical', summary: 'Test node 2'})
        CREATE (n3:Entity {uuid: 'test-other-001', name: 'Test Other', summary: 'Test node 3'})
        CREATE (n1)-[:KNOWS]->(n3)
        CREATE (n3)-[:RELATED_TO]->(n1)
        CREATE (n1)-[:IS_DUPLICATE_OF]->(n2)
        RETURN n1.uuid as duplicate_uuid, n2.uuid as canonical_uuid
        """
        result, _, _ = await driver.execute_query(create_query)
    
    if result:
        duplicate_uuid = result[0]['duplicate_uuid']
        canonical_uuid = result[0]['canonical_uuid']
        
        print(f"Testing merge of {duplicate_uuid} into {canonical_uuid}")
        
        # Perform the merge
        stats = await merge_node_into(
            driver,
            canonical_uuid=canonical_uuid,
            duplicate_uuid=duplicate_uuid,
            maintain_audit_trail=True,
            recalculate_centrality=True
        )
        
        print(f"Merge completed: {stats}")
        
        # Verify centrality was updated
        verify_query = """
        MATCH (n:Entity {uuid: $uuid})
        RETURN n.degree_centrality, n.pagerank_centrality, n.betweenness_centrality
        """
        result, _, _ = await driver.execute_query(verify_query, uuid=canonical_uuid)
        
        if result:
            print(f"Centrality values after merge:")
            print(f"  Degree: {result[0].get('n.degree_centrality', 0)}")
            print(f"  PageRank: {result[0].get('n.pagerank_centrality', 0)}")
            print(f"  Betweenness: {result[0].get('n.betweenness_centrality', 0)}")
    else:
        print("Could not set up test nodes")
    
    await driver.close()

if __name__ == "__main__":
    asyncio.run(test_merge())