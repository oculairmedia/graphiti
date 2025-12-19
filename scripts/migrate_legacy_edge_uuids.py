#!/usr/bin/env python3
"""
Migrate legacy edge UUIDs to deterministic UUIDs.

This script finds all RELATES_TO edges in FalkorDB that have UUIDs that don't match
what the deterministic algorithm would generate, and updates them.

For conflicts (multiple edges that would get the same UUID), it keeps one and deletes duplicates.

Usage:
    python migrate_legacy_edge_uuids.py --dry-run  # Preview changes
    python migrate_legacy_edge_uuids.py            # Apply changes
"""

import argparse
import logging
import sys
from collections import defaultdict
from uuid import uuid5, NAMESPACE_DNS
from falkordb import FalkorDB

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
FALKORDB_HOST = "localhost"
FALKORDB_PORT = 6379
GRAPH_NAME = "graphiti_migration"
BATCH_SIZE = 100


def generate_deterministic_edge_uuid(source_uuid: str, target_uuid: str, name: str, group_id: str) -> str:
    """Generate deterministic UUID for an edge (matches graphiti_core/utils/uuid_utils.py)"""
    group_namespace = uuid5(NAMESPACE_DNS, f"graphiti.edge.{group_id}")
    normalized_name = name.strip().upper() if name and name.strip() else 'RELATES_TO'
    edge_key = f"{source_uuid}|{target_uuid}|{normalized_name}"
    edge_uuid = uuid5(group_namespace, edge_key)
    return str(edge_uuid)


def get_all_edges(graph):
    """Fetch all RELATES_TO edges with their source/target node UUIDs"""
    query = """
    MATCH (s)-[r:RELATES_TO]->(t)
    RETURN r.uuid AS uuid, 
           s.uuid AS source_uuid, 
           t.uuid AS target_uuid, 
           r.name AS name, 
           r.group_id AS group_id,
           r.fact AS fact,
           r.created_at AS created_at
    """
    result = graph.query(query)
    edges = []
    for row in result.result_set:
        edges.append({
            'uuid': row[0],
            'source_uuid': row[1],
            'target_uuid': row[2],
            'name': row[3],
            'group_id': row[4],
            'fact': row[5][:50] + '...' if row[5] and len(row[5]) > 50 else row[5],
            'created_at': row[6]
        })
    return edges


def analyze_edges(edges):
    """Analyze edges and group by expected deterministic UUID"""
    # Group edges by their expected deterministic UUID
    uuid_groups = defaultdict(list)
    
    for edge in edges:
        if not edge['source_uuid'] or not edge['target_uuid'] or not edge['group_id']:
            logger.warning(f"Skipping edge {edge['uuid']} - missing required fields")
            continue
        
        expected_uuid = generate_deterministic_edge_uuid(
            edge['source_uuid'],
            edge['target_uuid'],
            edge['name'] or 'RELATES_TO',
            edge['group_id']
        )
        
        uuid_groups[expected_uuid].append({
            **edge,
            'expected_uuid': expected_uuid,
            'needs_update': edge['uuid'] != expected_uuid
        })
    
    return uuid_groups


def plan_migration(uuid_groups):
    """
    Plan the migration:
    - For groups with 1 edge: update UUID if needed
    - For groups with multiple edges: keep newest, delete others
    """
    to_update = []
    to_delete = []
    already_correct = 0
    
    for expected_uuid, edges in uuid_groups.items():
        if len(edges) == 1:
            edge = edges[0]
            if edge['needs_update']:
                to_update.append(edge)
            else:
                already_correct += 1
        else:
            # Multiple edges would get same UUID - duplicates!
            # Sort by created_at (keep newest) or by uuid (deterministic)
            edges_sorted = sorted(edges, key=lambda e: e['created_at'] or '', reverse=True)
            
            # Keep the first one (newest), update its UUID if needed
            keep = edges_sorted[0]
            if keep['needs_update']:
                to_update.append(keep)
            else:
                already_correct += 1
            
            # Delete the rest
            for dup in edges_sorted[1:]:
                to_delete.append(dup)
    
    return to_update, to_delete, already_correct


def update_edge_uuid(graph, old_uuid: str, new_uuid: str):
    """Update an edge's UUID"""
    query = """
    MATCH ()-[r:RELATES_TO {uuid: $old_uuid}]->()
    SET r.uuid = $new_uuid
    RETURN r.uuid
    """
    try:
        result = graph.query(query, {'old_uuid': old_uuid, 'new_uuid': new_uuid})
        return bool(result.result_set)
    except Exception as e:
        logger.error(f"Failed to update {old_uuid}: {e}")
        return False


def delete_edge(graph, uuid: str):
    """Delete an edge by UUID"""
    query = """
    MATCH ()-[r:RELATES_TO {uuid: $uuid}]->()
    DELETE r
    RETURN count(r) AS deleted
    """
    try:
        result = graph.query(query, {'uuid': uuid})
        return True
    except Exception as e:
        logger.error(f"Failed to delete {uuid}: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description='Migrate legacy edge UUIDs to deterministic UUIDs')
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without applying them')
    parser.add_argument('--batch-size', type=int, default=BATCH_SIZE, help='Batch size for updates')
    parser.add_argument('--limit', type=int, default=0, help='Limit number of edges to process (0 = all)')
    args = parser.parse_args()
    
    logger.info(f"Connecting to FalkorDB at {FALKORDB_HOST}:{FALKORDB_PORT}")
    db = FalkorDB(host=FALKORDB_HOST, port=FALKORDB_PORT)
    graph = db.select_graph(GRAPH_NAME)
    
    # Step 1: Get all edges
    logger.info("Fetching all RELATES_TO edges...")
    edges = get_all_edges(graph)
    logger.info(f"Found {len(edges)} RELATES_TO edges")
    
    # Step 2: Analyze and group by expected UUID
    logger.info("Analyzing edges and computing deterministic UUIDs...")
    uuid_groups = analyze_edges(edges)
    logger.info(f"Found {len(uuid_groups)} unique deterministic UUIDs")
    
    # Step 3: Plan migration
    logger.info("Planning migration...")
    to_update, to_delete, already_correct = plan_migration(uuid_groups)
    
    logger.info(f"\nMigration plan:")
    logger.info(f"  Already correct: {already_correct}")
    logger.info(f"  To update: {len(to_update)}")
    logger.info(f"  To delete (duplicates): {len(to_delete)}")
    
    # Step 4: Show samples
    if to_update:
        logger.info("\nSample edges to UPDATE:")
        for edge in to_update[:3]:
            logger.info(f"  {edge['uuid'][:12]}... -> {edge['expected_uuid'][:12]}...")
            logger.info(f"    {edge['source_uuid'][:8]}... -[{edge['name']}]-> {edge['target_uuid'][:8]}...")
    
    if to_delete:
        logger.info("\nSample DUPLICATE edges to DELETE:")
        for edge in to_delete[:3]:
            logger.info(f"  {edge['uuid'][:12]}... (duplicate of {edge['expected_uuid'][:12]}...)")
            logger.info(f"    {edge['source_uuid'][:8]}... -[{edge['name']}]-> {edge['target_uuid'][:8]}...")
            logger.info(f"    fact: {edge['fact']}")
    
    if args.dry_run:
        logger.info(f"\n[DRY-RUN] Would update {len(to_update)} edges and delete {len(to_delete)} duplicates")
        logger.info("Run without --dry-run to apply changes")
        return 0
    
    # Step 5: Apply deletions first (to avoid conflicts)
    if to_delete:
        logger.info(f"\nDeleting {len(to_delete)} duplicate edges...")
        delete_success = 0
        delete_fail = 0
        
        for i, edge in enumerate(to_delete):
            if i > 0 and i % args.batch_size == 0:
                logger.info(f"Delete progress: {i}/{len(to_delete)}")
            
            if delete_edge(graph, edge['uuid']):
                delete_success += 1
            else:
                delete_fail += 1
        
        logger.info(f"Deleted: {delete_success}, Failed: {delete_fail}")
    
    # Step 6: Apply updates
    if to_update:
        if args.limit > 0:
            to_update = to_update[:args.limit]
            logger.info(f"Limited to {args.limit} updates")
        
        logger.info(f"\nUpdating {len(to_update)} edge UUIDs...")
        update_success = 0
        update_fail = 0
        
        for i, edge in enumerate(to_update):
            if i > 0 and i % args.batch_size == 0:
                logger.info(f"Update progress: {i}/{len(to_update)}")
            
            if update_edge_uuid(graph, edge['uuid'], edge['expected_uuid']):
                update_success += 1
            else:
                update_fail += 1
        
        logger.info(f"Updated: {update_success}, Failed: {update_fail}")
    
    logger.info("\nMigration complete!")
    return 0


if __name__ == '__main__':
    sys.exit(main())
