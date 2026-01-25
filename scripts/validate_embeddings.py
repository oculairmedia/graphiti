#!/usr/bin/env python3
"""
Validate and fix corrupted embeddings in FalkorDB.

Embeddings must be stored as Vectorf32 type, not List. This script:
1. Finds nodes/edges with List-type embeddings (corrupted)
2. Either removes them (--fix) or just reports (default)

Usage:
    python3 scripts/validate_embeddings.py           # Report only
    python3 scripts/validate_embeddings.py --fix    # Remove corrupted embeddings
"""

import argparse
import redis
import sys


def check_embeddings(r, entity_type: str, fix: bool = False):
    """Check and optionally fix corrupted embeddings for nodes or edges."""
    
    if entity_type == "node":
        count_query = "MATCH (n:Entity) WHERE n.name_embedding IS NOT NULL RETURN count(n)"
        list_query = "MATCH (n:Entity) WHERE n.name_embedding IS NOT NULL RETURN n.uuid, n.name"
        check_template = "MATCH (n:Entity {{uuid: '{uuid}'}}) RETURN vec.cosineDistance(n.name_embedding, n.name_embedding)"
        fix_template = "MATCH (n:Entity {{uuid: '{uuid}'}}) REMOVE n.name_embedding RETURN n.uuid"
        embedding_field = "name_embedding"
    else:
        count_query = "MATCH ()-[r:RELATES_TO]->() WHERE r.fact_embedding IS NOT NULL RETURN count(r)"
        list_query = "MATCH ()-[r:RELATES_TO]->() WHERE r.fact_embedding IS NOT NULL RETURN r.uuid, r.fact"
        check_template = "MATCH ()-[r:RELATES_TO {{uuid: '{uuid}'}}]->() RETURN vec.cosineDistance(r.fact_embedding, r.fact_embedding)"
        fix_template = "MATCH ()-[r:RELATES_TO {{uuid: '{uuid}'}}]->() REMOVE r.fact_embedding RETURN r.uuid"
        embedding_field = "fact_embedding"
    
    # Get total count
    result = r.execute_command('GRAPH.QUERY', 'graphiti_migration', count_query)
    total = int(result[1][0][0])
    print(f"\n{entity_type.upper()}S: {total} with {embedding_field}")
    
    # Get all entities
    result = r.execute_command('GRAPH.QUERY', 'graphiti_migration', list_query)
    
    bad_entities = []
    for i, row in enumerate(result[1]):
        uuid = row[0]
        name = row[1] if len(row) > 1 else None
        
        check_query = check_template.format(uuid=uuid)
        try:
            r.execute_command('GRAPH.QUERY', 'graphiti_migration', check_query)
        except Exception as e:
            if "List" in str(e):
                bad_entities.append((uuid, name))
        
        if (i + 1) % 10000 == 0:
            print(f"  Checked {i+1}/{len(result[1])}...")
    
    if not bad_entities:
        print(f"  ✓ All {entity_type} embeddings are valid Vectorf32")
        return 0
    
    print(f"  ✗ Found {len(bad_entities)} corrupted {entity_type} embeddings (List type)")
    
    for uuid, name in bad_entities[:10]:
        name_preview = (name[:50] + '...') if name and len(name) > 50 else name
        print(f"    - {uuid}: {name_preview}")
    if len(bad_entities) > 10:
        print(f"    ... and {len(bad_entities) - 10} more")
    
    if fix:
        print(f"\n  Fixing {len(bad_entities)} corrupted {entity_type}s...")
        fixed = 0
        for uuid, name in bad_entities:
            try:
                fix_query = fix_template.format(uuid=uuid)
                r.execute_command('GRAPH.QUERY', 'graphiti_migration', fix_query)
                fixed += 1
            except Exception as e:
                print(f"    ERROR fixing {uuid}: {e}")
        print(f"  ✓ Removed {fixed} corrupted embeddings")
    
    return len(bad_entities)


def main():
    parser = argparse.ArgumentParser(description='Validate and fix corrupted embeddings')
    parser.add_argument('--fix', action='store_true', help='Remove corrupted embeddings')
    parser.add_argument('--host', default='localhost', help='FalkorDB host')
    parser.add_argument('--port', type=int, default=6379, help='FalkorDB port')
    args = parser.parse_args()
    
    r = redis.Redis(host=args.host, port=args.port, decode_responses=True)
    
    print("=" * 60)
    print("Embedding Validation Report")
    print("=" * 60)
    
    node_bad = check_embeddings(r, "node", args.fix)
    edge_bad = check_embeddings(r, "edge", args.fix)
    
    print("\n" + "=" * 60)
    total_bad = node_bad + edge_bad
    if total_bad == 0:
        print("✓ All embeddings are valid!")
        return 0
    elif args.fix:
        print(f"Fixed {total_bad} corrupted embeddings")
        return 0
    else:
        print(f"✗ Found {total_bad} corrupted embeddings")
        print("  Run with --fix to remove them")
        return 1


if __name__ == "__main__":
    sys.exit(main())
