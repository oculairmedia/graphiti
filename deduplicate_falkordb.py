#!/usr/bin/env python3
"""
Deduplication script for FalkorDB graph database.
Removes duplicate nodes and edges based on UUID to fix constraint violations.
"""

import redis
from collections import defaultdict
import sys

# FalkorDB connection
FALKORDB_HOST = 'localhost'
FALKORDB_PORT = 6379
GRAPH_NAME = 'graphiti_migration'

def connect_falkordb():
    """Connect to FalkorDB via Redis protocol."""
    try:
        client = redis.Redis(host=FALKORDB_HOST, port=FALKORDB_PORT, decode_responses=True)
        client.ping()
        print(f"✓ Connected to FalkorDB at {FALKORDB_HOST}:{FALKORDB_PORT}")
        return client
    except Exception as e:
        print(f"✗ Failed to connect to FalkorDB: {e}")
        sys.exit(1)

def find_duplicate_nodes(client):
    """Find all duplicate node UUIDs in the graph."""
    print("\nSearching for duplicate nodes...")

    query = """
    MATCH (n)
    WITH n.uuid AS uuid, COUNT(n) AS count, COLLECT(ID(n)) AS node_ids
    WHERE count > 1
    RETURN uuid, count, node_ids
    """

    result = client.execute_command('GRAPH.QUERY', GRAPH_NAME, query)

    duplicates = []
    if result and len(result) > 1:
        rows = result[1]  # Skip header
        for row in rows:
            uuid = row[0]
            count = row[1]
            node_ids = row[2]
            duplicates.append({
                'uuid': uuid,
                'count': count,
                'node_ids': node_ids
            })

    return duplicates

def find_duplicate_edges(client):
    """Find all duplicate edge UUIDs in the graph."""
    print("\nSearching for duplicate edges...")

    query = """
    MATCH ()-[r]->()
    WITH r.uuid AS uuid, COUNT(r) AS count, COLLECT(ID(r)) AS edge_ids
    WHERE count > 1
    RETURN uuid, count, edge_ids
    """

    result = client.execute_command('GRAPH.QUERY', GRAPH_NAME, query)

    duplicates = []
    if result and len(result) > 1:
        rows = result[1]  # Skip header
        for row in rows:
            uuid = row[0]
            count = row[1]
            edge_ids = row[2]
            duplicates.append({
                'uuid': uuid,
                'count': count,
                'edge_ids': edge_ids
            })

    return duplicates

def delete_duplicate_nodes(client, duplicates, dry_run=False):
    """Delete duplicate nodes, keeping only the first occurrence."""
    print(f"\n{'[DRY RUN] ' if dry_run else ''}Removing duplicate nodes...")

    deleted_count = 0

    for dup in duplicates:
        uuid = dup['uuid']
        count = dup['count']

        # Delete all but one instance of this UUID
        duplicates_to_remove = count - 1

        print(f"  UUID: {uuid} - removing {duplicates_to_remove} duplicate(s)")

        if not dry_run:
            # Get all nodes with this UUID and delete all but the first
            query = f'''
            MATCH (n {{uuid: "{uuid}"}})
            WITH n
            SKIP 1
            DELETE n
            '''
            result = client.execute_command('GRAPH.QUERY', GRAPH_NAME, query)
            deleted_count += duplicates_to_remove

    return deleted_count

def delete_duplicate_edges(client, duplicates, dry_run=False):
    """Delete duplicate edges, keeping only the first occurrence."""
    print(f"\n{'[DRY RUN] ' if dry_run else ''}Removing duplicate edges...")

    deleted_count = 0

    for dup in duplicates:
        uuid = dup['uuid']
        count = dup['count']

        # Delete all but one instance of this UUID
        duplicates_to_remove = count - 1

        print(f"  UUID: {uuid} - removing {duplicates_to_remove} duplicate(s)")

        if not dry_run:
            # Get all edges with this UUID and delete all but the first
            query = f'''
            MATCH ()-[r {{uuid: "{uuid}"}}]->()
            WITH r
            SKIP 1
            DELETE r
            '''
            result = client.execute_command('GRAPH.QUERY', GRAPH_NAME, query)
            deleted_count += duplicates_to_remove

    return deleted_count

def main():
    """Main deduplication workflow."""
    print("=" * 60)
    print("FalkorDB Deduplication Script")
    print("=" * 60)

    dry_run = '--dry-run' in sys.argv

    if dry_run:
        print("\n⚠️  DRY RUN MODE - No changes will be made")

    client = connect_falkordb()

    # Find duplicates
    duplicate_nodes = find_duplicate_nodes(client)
    duplicate_edges = find_duplicate_edges(client)

    print(f"\nFound {len(duplicate_nodes)} duplicate node UUIDs")
    print(f"Found {len(duplicate_edges)} duplicate edge UUIDs")

    if not duplicate_nodes and not duplicate_edges:
        print("\n✓ No duplicates found! Database is clean.")
        return

    # Show summary
    total_duplicate_nodes = sum(d['count'] - 1 for d in duplicate_nodes)
    total_duplicate_edges = sum(d['count'] - 1 for d in duplicate_edges)

    print(f"\nTotal duplicate nodes to remove: {total_duplicate_nodes}")
    print(f"Total duplicate edges to remove: {total_duplicate_edges}")

    if dry_run:
        print("\nRun without --dry-run to perform deduplication")
        return

    # Perform deduplication
    print("\n⚠️  Performing deduplication...")
    nodes_deleted = delete_duplicate_nodes(client, duplicate_nodes)
    edges_deleted = delete_duplicate_edges(client, duplicate_edges)

    print("\n" + "=" * 60)
    print("Deduplication Complete!")
    print("=" * 60)
    print(f"  Nodes deleted: {nodes_deleted}")
    print(f"  Edges deleted: {edges_deleted}")
    print()

    # Verify
    remaining_node_dupes = find_duplicate_nodes(client)
    remaining_edge_dupes = find_duplicate_edges(client)

    if remaining_node_dupes or remaining_edge_dupes:
        print(f"⚠️  Warning: {len(remaining_node_dupes)} node duplicates and {len(remaining_edge_dupes)} edge duplicates still remain")
    else:
        print("✓ All duplicates removed successfully!")

if __name__ == '__main__':
    main()
