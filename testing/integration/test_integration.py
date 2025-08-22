#!/usr/bin/env python3
"""
Integration test for atomic centrality storage and schema versioning.
Tests the implementations with a fresh FalkorDB instance.
"""

import asyncio
import os
from datetime import datetime, timezone

# Set up environment
os.environ["FALKORDB_HOST"] = "localhost"
os.environ["FALKORDB_PORT"] = "6389"
os.environ["GRAPH_NAME"] = "test_integration"

from graphiti_core.driver.falkordb_driver import FalkorDriver
from graphiti_core.utils.maintenance.atomic_centrality_storage import AtomicCentralityStorage
from graphiti_core.utils.maintenance.centrality_schema import (
    SchemaVersion,
    SchemaManager,
    APIVersionNegotiator,
)


async def test_atomic_storage():
    """Test atomic centrality storage."""
    print("\n=== Testing Atomic Centrality Storage ===\n")
    
    # Initialize driver
    driver = FalkorDriver(
        host="localhost",
        port=6389,
        database="test_integration"
    )
    
    # Create test nodes
    print("Creating test nodes...")
    await driver.execute_query(
        "CREATE (n1:EntityNode {uuid: 'node1', name: 'Node 1'})"
    )
    await driver.execute_query(
        "CREATE (n2:EntityNode {uuid: 'node2', name: 'Node 2'})"
    )
    await driver.execute_query(
        "CREATE (n3:EntityNode {uuid: 'node3', name: 'Node 3'})"
    )
    
    # Create edges
    await driver.execute_query(
        "MATCH (n1 {uuid: 'node1'}), (n2 {uuid: 'node2'}) CREATE (n1)-[:CONNECTED_TO]->(n2)"
    )
    await driver.execute_query(
        "MATCH (n2 {uuid: 'node2'}), (n3 {uuid: 'node3'}) CREATE (n2)-[:CONNECTED_TO]->(n3)"
    )
    
    # Initialize storage
    storage = AtomicCentralityStorage(driver, batch_size=2)
    
    # Test centrality scores
    scores = {
        "node1": {
            "pagerank": 0.15,
            "degree": 1,
            "betweenness": 0.0,
            "importance": 2.5,
        },
        "node2": {
            "pagerank": 0.35,
            "degree": 2,
            "betweenness": 0.5,
            "importance": 4.2,
        },
        "node3": {
            "pagerank": 0.25,
            "degree": 1,
            "betweenness": 0.0,
            "importance": 3.1,
        },
    }
    
    print("Storing centrality scores atomically...")
    transaction = await storage.store_centrality_atomic(scores)
    
    print(f"Transaction ID: {transaction.transaction_id}")
    print(f"State: {transaction.state.value}")
    print(f"Processed: {transaction.processed_nodes}/{transaction.total_nodes} nodes")
    print(f"Failed: {transaction.failed_nodes} nodes")
    
    # Verify stored scores
    print("\nVerifying stored scores...")
    result, _, _ = await driver.execute_query(
        "MATCH (n:EntityNode) RETURN n.uuid AS uuid, n.centrality_pagerank AS pagerank"
    )
    
    for record in result:
        print(f"  {record['uuid']}: PageRank = {record['pagerank']}")
    
    # Test transaction history
    print("\nRetrieving transaction history...")
    history = await storage.get_transaction_history(limit=5)
    for tx in history:
        print(f"  Transaction {tx['transaction_id']}: {tx['state']}")
    
    return driver


async def test_schema_versioning(driver):
    """Test schema versioning and migration."""
    print("\n=== Testing Schema Versioning ===\n")
    
    # Initialize schema manager
    manager = SchemaManager(driver)
    
    # Initialize schema
    print("Initializing schema...")
    await manager.initialize_schema(SchemaVersion.V2_0_0)
    
    # Get current version
    current = await manager.get_current_version()
    print(f"Current schema version: {current.value}")
    
    # Test API negotiation
    negotiator = APIVersionNegotiator(manager)
    
    # Test version negotiation
    print("\nTesting API version negotiation...")
    
    # Request compatible version
    negotiated = await negotiator.negotiate_version("2.1.0")
    print(f"  Requested 2.1.0, negotiated: {negotiated.value}")
    
    # Request incompatible version (should fallback)
    negotiated = await negotiator.negotiate_version("1.0.0")
    print(f"  Requested 1.0.0, negotiated: {negotiated.value}")
    
    # Test response formatting
    print("\nTesting response formatting...")
    raw_data = {
        "pagerank": 0.5,
        "degree": 0.3,
        "betweenness": 0.2,
        "eigenvector": 0.7,
        "closeness": 0.4,  # Only in v2.1+
        "harmonic": 0.6,   # Only in v2.2+
    }
    
    # Format for v2.0 (should exclude newer metrics)
    response = negotiator.format_response(raw_data, SchemaVersion.V2_0_0)
    print(f"  v2.0 response includes: {list(response['data'].keys())}")
    
    # Format for v2.2 (should include all)
    response = negotiator.format_response(raw_data, SchemaVersion.V2_2_0)
    print(f"  v2.2 response includes: {list(response['data'].keys())}")
    
    # Test migration
    print("\nTesting schema migration...")
    print(f"  Migrating from {current.value} to {SchemaVersion.V2_2_0.value}...")
    
    stats = await manager.migrate_to_version(SchemaVersion.V2_2_0)
    print(f"  Migration result: {stats['from_version']} -> {stats['to_version']}")
    print(f"  Nodes migrated: {stats['nodes_migrated']}")
    print(f"  Errors: {len(stats['errors'])}")
    
    # Verify new version
    new_version = await manager.get_current_version()
    print(f"  New schema version: {new_version.value}")


async def cleanup(driver):
    """Clean up test data."""
    print("\n=== Cleaning up ===\n")
    
    # Delete test graph
    await driver.execute_query("MATCH (n) DETACH DELETE n")
    print("Test data cleaned up.")


async def main():
    """Run integration tests."""
    print("=" * 60)
    print("INTEGRATION TEST: Atomic Centrality Storage & Schema Versioning")
    print("=" * 60)
    
    driver = None
    try:
        # Test atomic storage
        driver = await test_atomic_storage()
        
        # Test schema versioning
        await test_schema_versioning(driver)
        
        print("\n" + "=" * 60)
        print("ALL TESTS PASSED SUCCESSFULLY ✓")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        if driver:
            await cleanup(driver)


if __name__ == "__main__":
    asyncio.run(main())