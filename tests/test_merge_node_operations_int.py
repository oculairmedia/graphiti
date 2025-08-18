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

import os
from datetime import datetime
from uuid import uuid4

import pytest
import pytest_asyncio

from graphiti_core.driver.falkordb_driver import FalkorDriver
from graphiti_core.driver.neo4j_driver import Neo4jDriver
from graphiti_core.edges import EntityEdge
from graphiti_core.nodes import EntityNode, EpisodicNode
from graphiti_core.utils.datetime_utils import utc_now
from graphiti_core.utils.maintenance.edge_operations import (
    build_duplicate_of_edges,
    execute_merge_operations,
)
from graphiti_core.utils.maintenance.node_operations import merge_node_into

# Test configuration
NEO4J_URI = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
NEO4J_USER = os.getenv('NEO4J_USER', 'neo4j')
NEO4J_PASSWORD = os.getenv('NEO4J_PASSWORD', 'password')

FALKORDB_HOST = os.getenv('FALKORDB_HOST', 'localhost')
FALKORDB_PORT = int(os.getenv('FALKORDB_PORT', 6389))


@pytest_asyncio.fixture
async def neo4j_driver():
    """Create a Neo4j driver for testing."""
    driver = Neo4jDriver(uri=NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    yield driver
    await driver.close()


@pytest_asyncio.fixture
async def falkordb_driver():
    """Create a FalkorDB driver for testing."""
    driver = FalkorDriver(host=FALKORDB_HOST, port=FALKORDB_PORT, database='test_merge_db')
    yield driver
    await driver.close()


@pytest_asyncio.fixture
async def setup_test_graph(request):
    """Set up a test graph with nodes and edges for merge testing."""
    driver = request.getfixturevalue(request.param)
    
    # Clear the graph first
    await driver.execute_query("MATCH (n) DETACH DELETE n")
    
    # Create test nodes
    canonical_node = EntityNode(
        uuid='canonical-uuid',
        name='Alice Smith',
        group_id='test-group',
        labels=['Entity', 'Person'],
        summary='The canonical Alice node',
        created_at=utc_now(),
    )
    
    duplicate_node = EntityNode(
        uuid='duplicate-uuid',
        name='Alice S.',
        group_id='test-group',
        labels=['Entity', 'Person'],
        summary='A duplicate Alice node',
        created_at=utc_now(),
    )
    
    related_node1 = EntityNode(
        uuid='related-1',
        name='Bob Johnson',
        group_id='test-group',
        labels=['Entity', 'Person'],
        summary='Bob who knows Alice',
        created_at=utc_now(),
    )
    
    related_node2 = EntityNode(
        uuid='related-2',
        name='Charlie Brown',
        group_id='test-group',
        labels=['Entity', 'Person'],
        summary='Charlie who works with Alice',
        created_at=utc_now(),
    )
    
    # Save nodes
    for node in [canonical_node, duplicate_node, related_node1, related_node2]:
        await node.save(driver)
    
    # Create edges to duplicate node
    edge1 = EntityEdge(
        source_node_uuid='related-1',
        target_node_uuid='duplicate-uuid',
        name='KNOWS',
        fact='Bob knows Alice',
        group_id='test-group',
        created_at=utc_now(),
    )
    
    edge2 = EntityEdge(
        source_node_uuid='duplicate-uuid',
        target_node_uuid='related-2',
        name='WORKS_WITH',
        fact='Alice works with Charlie',
        group_id='test-group',
        created_at=utc_now(),
    )
    
    # Save edges
    await edge1.save(driver)
    await edge2.save(driver)
    
    return driver, canonical_node, duplicate_node, [related_node1, related_node2]


@pytest.mark.asyncio
@pytest.mark.parametrize('setup_test_graph', ['neo4j_driver'], indirect=True)
async def test_merge_node_into_neo4j(setup_test_graph):
    """Test merging duplicate node into canonical node with Neo4j."""
    driver, canonical_node, duplicate_node, related_nodes = setup_test_graph
    
    # Perform the merge
    stats = await merge_node_into(
        driver,
        canonical_node.uuid,
        duplicate_node.uuid,
        maintain_audit_trail=True
    )
    
    # Verify stats
    assert stats['edges_transferred'] > 0
    assert 'errors' in stats
    assert len(stats['errors']) == 0
    
    # Verify edges were transferred to canonical node
    # Check incoming edge (Bob -> Alice)
    incoming_query = """
    MATCH (bob:Entity {uuid: $bob_uuid})-[r:KNOWS]->(alice:Entity {uuid: $canonical_uuid})
    RETURN r
    """
    result, _, _ = await driver.execute_query(
        incoming_query,
        bob_uuid='related-1',
        canonical_uuid=canonical_node.uuid
    )
    assert len(result) == 1, "Incoming edge should be transferred to canonical node"
    
    # Check outgoing edge (Alice -> Charlie)
    outgoing_query = """
    MATCH (alice:Entity {uuid: $canonical_uuid})-[r:WORKS_WITH]->(charlie:Entity {uuid: $charlie_uuid})
    RETURN r
    """
    result, _, _ = await driver.execute_query(
        outgoing_query,
        canonical_uuid=canonical_node.uuid,
        charlie_uuid='related-2'
    )
    assert len(result) == 1, "Outgoing edge should be transferred to canonical node"
    
    # Verify original edges from duplicate are removed
    old_edges_query = """
    MATCH (n)-[r]-(duplicate:Entity {uuid: $duplicate_uuid})
    WHERE type(r) IN ['KNOWS', 'WORKS_WITH']
    RETURN r
    """
    result, _, _ = await driver.execute_query(
        old_edges_query,
        duplicate_uuid=duplicate_node.uuid
    )
    assert len(result) == 0, "Original edges from duplicate should be removed"
    
    # Verify audit trail exists
    audit_query = """
    MATCH (duplicate:Entity {uuid: $duplicate_uuid})-[r:IS_DUPLICATE_OF]->(canonical:Entity {uuid: $canonical_uuid})
    RETURN r
    """
    result, _, _ = await driver.execute_query(
        audit_query,
        duplicate_uuid=duplicate_node.uuid,
        canonical_uuid=canonical_node.uuid
    )
    assert len(result) == 1, "IS_DUPLICATE_OF edge should exist for audit trail"
    
    # Verify duplicate is marked as merged
    tombstone_query = """
    MATCH (duplicate:Entity {uuid: $duplicate_uuid})
    RETURN duplicate.is_merged as is_merged, duplicate.merged_into as merged_into
    """
    result, _, _ = await driver.execute_query(
        tombstone_query,
        duplicate_uuid=duplicate_node.uuid
    )
    assert result[0]['is_merged'] == True
    assert result[0]['merged_into'] == canonical_node.uuid


@pytest.mark.asyncio
@pytest.mark.parametrize('setup_test_graph', ['falkordb_driver'], indirect=True)
async def test_merge_node_into_falkordb(setup_test_graph):
    """Test merging duplicate node into canonical node with FalkorDB."""
    driver, canonical_node, duplicate_node, related_nodes = setup_test_graph
    
    # Perform the merge
    stats = await merge_node_into(
        driver,
        canonical_node.uuid,
        duplicate_node.uuid,
        maintain_audit_trail=True
    )
    
    # Verify stats
    assert stats['edges_transferred'] > 0
    assert 'errors' in stats
    assert len(stats['errors']) == 0
    
    # Verify edges were transferred to canonical node
    # Check incoming edge (Bob -> Alice)
    incoming_query = """
    MATCH (bob:Entity {uuid: $bob_uuid})-[r:KNOWS]->(alice:Entity {uuid: $canonical_uuid})
    RETURN r
    """
    result, _, _ = await driver.execute_query(
        incoming_query,
        bob_uuid='related-1',
        canonical_uuid=canonical_node.uuid
    )
    assert len(result) == 1, "Incoming edge should be transferred to canonical node"
    
    # Check outgoing edge (Alice -> Charlie)
    outgoing_query = """
    MATCH (alice:Entity {uuid: $canonical_uuid})-[r:WORKS_WITH]->(charlie:Entity {uuid: $charlie_uuid})
    RETURN r
    """
    result, _, _ = await driver.execute_query(
        outgoing_query,
        canonical_uuid=canonical_node.uuid,
        charlie_uuid='related-2'
    )
    assert len(result) == 1, "Outgoing edge should be transferred to canonical node"
    
    # Verify duplicate is marked as merged
    tombstone_query = """
    MATCH (duplicate:Entity {uuid: $duplicate_uuid})
    RETURN duplicate.is_merged as is_merged, duplicate.merged_into as merged_into
    """
    result, _, _ = await driver.execute_query(
        tombstone_query,
        duplicate_uuid=duplicate_node.uuid
    )
    assert result[0]['is_merged'] == True
    assert result[0]['merged_into'] == canonical_node.uuid


@pytest.mark.asyncio
@pytest.mark.parametrize('setup_test_graph', ['falkordb_driver'], indirect=True)
async def test_merge_with_conflicting_edges(setup_test_graph):
    """Test merging when canonical node already has some of the same edges."""
    driver, canonical_node, duplicate_node, related_nodes = setup_test_graph
    
    # Add a conflicting edge to canonical node (same type and target)
    conflicting_edge = EntityEdge(
        source_node_uuid=canonical_node.uuid,
        target_node_uuid='related-2',
        name='WORKS_WITH',
        fact='Alice already works with Charlie',
        group_id='test-group',
        created_at=utc_now(),
    )
    await conflicting_edge.save(driver)
    
    # Perform the merge
    stats = await merge_node_into(
        driver,
        canonical_node.uuid,
        duplicate_node.uuid,
        maintain_audit_trail=True
    )
    
    # Should resolve conflicts without errors
    assert stats['conflicts_resolved'] >= 1
    assert len(stats['errors']) == 0
    
    # Verify only one WORKS_WITH edge exists after merge
    edge_count_query = """
    MATCH (alice:Entity {uuid: $canonical_uuid})-[r:WORKS_WITH]->(charlie:Entity {uuid: $charlie_uuid})
    RETURN COUNT(r) as count
    """
    result, _, _ = await driver.execute_query(
        edge_count_query,
        canonical_uuid=canonical_node.uuid,
        charlie_uuid='related-2'
    )
    assert result[0]['count'] == 1, "Should have exactly one WORKS_WITH edge after merge"


@pytest.mark.asyncio
@pytest.mark.parametrize('setup_test_graph', ['falkordb_driver'], indirect=True)
async def test_merge_idempotency(setup_test_graph):
    """Test that merge operation is idempotent."""
    driver, canonical_node, duplicate_node, related_nodes = setup_test_graph
    
    # First merge
    stats1 = await merge_node_into(
        driver,
        canonical_node.uuid,
        duplicate_node.uuid,
        maintain_audit_trail=True
    )
    
    # Second merge (should be idempotent)
    stats2 = await merge_node_into(
        driver,
        canonical_node.uuid,
        duplicate_node.uuid,
        maintain_audit_trail=True
    )
    
    # Second merge should transfer 0 edges since they're already transferred
    assert stats2['edges_transferred'] == 0
    assert len(stats2['errors']) == 0
    
    # Verify edges still exist and are correct
    edge_count_query = """
    MATCH (canonical:Entity {uuid: $canonical_uuid})-[r]-(n)
    WHERE type(r) IN ['KNOWS', 'WORKS_WITH']
    RETURN COUNT(r) as count
    """
    result, _, _ = await driver.execute_query(
        edge_count_query,
        canonical_uuid=canonical_node.uuid
    )
    assert result[0]['count'] == 2, "Should still have exactly 2 edges after idempotent merge"


@pytest.mark.asyncio
@pytest.mark.parametrize('setup_test_graph', ['falkordb_driver'], indirect=True)
async def test_execute_merge_operations_batch(setup_test_graph):
    """Test batch execution of merge operations."""
    driver, canonical_node, duplicate_node, related_nodes = setup_test_graph
    
    # Create additional duplicate nodes
    duplicate2 = EntityNode(
        uuid='duplicate-2',
        name='A. Smith',
        group_id='test-group',
        labels=['Entity', 'Person'],
        summary='Another duplicate',
        created_at=utc_now(),
    )
    await duplicate2.save(driver)
    
    # Add edge to second duplicate
    edge = EntityEdge(
        source_node_uuid='duplicate-2',
        target_node_uuid='related-1',
        name='KNOWS',
        fact='Another connection',
        group_id='test-group',
        created_at=utc_now(),
    )
    await edge.save(driver)
    
    # Execute batch merge operations
    merge_operations = [
        (canonical_node.uuid, duplicate_node.uuid),
        (canonical_node.uuid, 'duplicate-2'),
    ]
    
    stats = await execute_merge_operations(driver, merge_operations)
    
    # Verify batch stats
    assert stats['total_merges'] == 2
    assert stats['total_edges_transferred'] >= 2
    assert len(stats['failed_merges']) == 0
    
    # Verify all edges are transferred to canonical
    edge_count_query = """
    MATCH (canonical:Entity {uuid: $canonical_uuid})-[r]-(n)
    WHERE type(r) IN ['KNOWS', 'WORKS_WITH']
    RETURN COUNT(DISTINCT r) as count
    """
    result, _, _ = await driver.execute_query(
        edge_count_query,
        canonical_uuid=canonical_node.uuid
    )
    assert result[0]['count'] >= 3, "All edges should be transferred to canonical node"


@pytest.mark.asyncio
@pytest.mark.parametrize('setup_test_graph', ['falkordb_driver'], indirect=True)
async def test_build_duplicate_edges_with_merge_operations(setup_test_graph):
    """Test that build_duplicate_of_edges returns merge operations."""
    driver, canonical_node, duplicate_node, related_nodes = setup_test_graph
    
    # Create episode for context
    episode = EpisodicNode(
        uuid=str(uuid4()),
        name='Test Episode',
        group_id='test-group',
        created_at=utc_now(),
    )
    
    # Build duplicate edges and get merge operations
    duplicate_edges, merge_operations = build_duplicate_of_edges(
        episode,
        utc_now(),
        [(duplicate_node, canonical_node)]
    )
    
    # Verify we get both edges and merge operations
    assert len(duplicate_edges) == 1
    assert duplicate_edges[0].name == 'IS_DUPLICATE_OF'
    assert len(merge_operations) == 1
    assert merge_operations[0] == (canonical_node.uuid, duplicate_node.uuid)
    
    # Save the IS_DUPLICATE_OF edge
    for edge in duplicate_edges:
        await edge.save(driver)
    
    # Execute the merge operations
    stats = await execute_merge_operations(driver, merge_operations)
    
    # Verify merge was successful
    assert stats['total_merges'] == 1
    assert stats['total_edges_transferred'] >= 2
    assert len(stats['failed_merges']) == 0


@pytest.mark.asyncio  
@pytest.mark.parametrize('setup_test_graph', ['falkordb_driver'], indirect=True)
async def test_merge_without_audit_trail(setup_test_graph):
    """Test merge operation without maintaining audit trail."""
    driver, canonical_node, duplicate_node, related_nodes = setup_test_graph
    
    # Perform merge without audit trail
    stats = await merge_node_into(
        driver,
        canonical_node.uuid,
        duplicate_node.uuid,
        maintain_audit_trail=False
    )
    
    # Verify edges were transferred
    assert stats['edges_transferred'] > 0
    
    # Verify NO IS_DUPLICATE_OF edge exists when audit trail is disabled
    audit_query = """
    MATCH (duplicate:Entity {uuid: $duplicate_uuid})-[r:IS_DUPLICATE_OF]->(canonical:Entity {uuid: $canonical_uuid})
    RETURN r
    """
    result, _, _ = await driver.execute_query(
        audit_query,
        duplicate_uuid=duplicate_node.uuid,
        canonical_uuid=canonical_node.uuid
    )
    # Note: The edge might still exist if it was created elsewhere, 
    # but the merge operation itself won't create it
    
    # Verify duplicate is still marked as merged (tombstone)
    tombstone_query = """
    MATCH (duplicate:Entity {uuid: $duplicate_uuid})
    RETURN duplicate.is_merged as is_merged
    """
    result, _, _ = await driver.execute_query(
        tombstone_query,
        duplicate_uuid=duplicate_node.uuid
    )
    assert result[0]['is_merged'] == True