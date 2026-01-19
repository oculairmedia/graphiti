#!/usr/bin/env python3
"""
Deduplication script for FalkorDB graph database - NODES ONLY.
Removes duplicate nodes based on UUID to fix constraint violations.
Does NOT touch edges.
"""

import redis
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

def delete_duplicate_nodes(client, duplicates):
    """Delete duplicate nodes, keeping only the first occurrence."""
    print(f"\nRemoving duplicate nodes...")

    deleted_count = 0

    for dup in duplicates:
        uuid = dup['uuid']
        count = dup['count']

        # Delete all but one instance of this UUID
        duplicates_to_remove = count - 1

        print(f"  UUID: {uuid} - removing {duplicates_to_remove} duplicate(s)")

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

def main():
    """Main deduplication workflow."""
    print("=" * 60)
    print("FalkorDB Node Deduplication Script")
    print("=" * 60)

    client = connect_falkordb()

    # Find duplicates
    duplicate_nodes = find_duplicate_nodes(client)

    print(f"\nFound {len(duplicate_nodes)} duplicate node UUIDs")

    if not duplicate_nodes:
        print("\n✓ No duplicate nodes found! Database is clean.")
        return

    # Show summary
    total_duplicate_nodes = sum(d['count'] - 1 for d in duplicate_nodes)

    print(f"\nTotal duplicate nodes to remove: {total_duplicate_nodes}")

    # Perform deduplication
    print("\n⚠️  Performing deduplication...")
    nodes_deleted = delete_duplicate_nodes(client, duplicate_nodes)

    print("\n" + "=" * 60)
    print("Deduplication Complete!")
    print("=" * 60)
    print(f"  Nodes deleted: {nodes_deleted}")
    print()

    # Verify
    remaining_node_dupes = find_duplicate_nodes(client)

    if remaining_node_dupes:
        print(f"⚠️  Warning: {len(remaining_node_dupes)} node duplicates still remain")
    else:
        print("✓ All duplicate nodes removed successfully!")

if __name__ == '__main__':
    main()
