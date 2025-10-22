#!/usr/bin/env python3
"""
Simple script to delete unconnected nodes using direct Redis queries.
"""

import sys
import subprocess
import json


def run_redis_query(query, *params):
    """Run a Redis graph query and return results"""
    cmd = ['redis-cli', '-h', 'localhost', '-p', '6379', 'GRAPH.QUERY', 'graphiti_migration', query]
    if params:
        cmd.extend(str(p) for p in params)
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error running query: {result.stderr}")
        return None
    
    return result.stdout.strip()


def count_unconnected_nodes():
    """Count unconnected nodes"""
    # Count disconnected episodes
    episode_query = """MATCH (ep:Episodic) WHERE NOT (ep)-[:MENTIONS]->() RETURN count(ep) as count"""
    episode_result = run_redis_query(episode_query)
    
    # Count disconnected entities  
    entity_query = """MATCH (ent:Entity) WHERE NOT ()-[:MENTIONS]->(ent) RETURN count(ent) as count"""
    entity_result = run_redis_query(entity_query)
    
    # Parse results - Redis returns in format: "1) count\n2) \"123\""
    episode_count = 0
    entity_count = 0
    
    if episode_result:
        lines = episode_result.split('\n')
        if len(lines) >= 2:
            episode_count = int(lines[1].strip('"'))
    
    if entity_result:
        lines = entity_result.split('\n')
        if len(lines) >= 2:
            entity_count = int(lines[1].strip('"'))
    
    return episode_count, entity_count


def delete_unconnected_episodes(dry_run=False):
    """Delete unconnected episodic nodes"""
    count_query = """MATCH (ep:Episodic) WHERE NOT (ep)-[:MENTIONS]->() RETURN count(ep) as count"""
    delete_query = """MATCH (ep:Episodic) WHERE NOT (ep)-[:MENTIONS]->() DELETE ep"""
    
    # Get count
    result = run_redis_query(count_query)
    count = 0
    if result:
        lines = result.split('\n')
        if len(lines) >= 2:
            count = int(lines[1].strip('"'))
    
    if dry_run:
        print(f"Would delete {count} unconnected episodic nodes")
        return count
    
    if count == 0:
        print("No unconnected episodic nodes to delete")
        return 0
    
    # Delete nodes
    run_redis_query(delete_query)
    print(f"Deleted {count} unconnected episodic nodes")
    return count


def delete_unconnected_entities(dry_run=False):
    """Delete unconnected entity nodes"""
    count_query = """MATCH (ent:Entity) WHERE NOT ()-[:MENTIONS]->(ent) RETURN count(ent) as count"""
    delete_query = """MATCH (ent:Entity) WHERE NOT ()-[:MENTIONS]->(ent) DELETE ent"""
    
    # Get count
    result = run_redis_query(count_query)
    count = 0
    if result:
        lines = result.split('\n')
        if len(lines) >= 2:
            count = int(lines[1].strip('"'))
    
    if dry_run:
        print(f"Would delete {count} unconnected entity nodes")
        return count
    
    if count == 0:
        print("No unconnected entity nodes to delete")
        return 0
    
    # Delete nodes
    run_redis_query(delete_query)
    print(f"Deleted {count} unconnected entity nodes")
    return count


def main():
    dry_run = '--dry-run' in sys.argv
    force = '--force' in sys.argv
    
    print("Checking for unconnected nodes...")
    episode_count, entity_count = count_unconnected_nodes()
    
    print(f"Found {episode_count} unconnected episodes and {entity_count} unconnected entities")
    
    if episode_count == 0 and entity_count == 0:
        print("No unconnected nodes found")
        return
    
    if dry_run:
        print("\nDRY RUN MODE - No nodes will be deleted")
        episodes_deleted = delete_unconnected_episodes(dry_run=True)
        entities_deleted = delete_unconnected_entities(dry_run=True)
    else:
        # Show what would be deleted and ask for confirmation
        print(f"\nThis will delete {episode_count} episodes and {entity_count} entities")
        
        if force:
            print("Force flag detected - proceeding without confirmation")
        else:
            try:
                confirmation = input("Proceed? (yes/no): ")
                if confirmation.lower() not in ['yes', 'y']:
                    print("Operation cancelled")
                    return
            except (EOFError, KeyboardInterrupt):
                print("\nOperation cancelled")
                return
        
        episodes_deleted = delete_unconnected_episodes(dry_run=False)
        entities_deleted = delete_unconnected_entities(dry_run=False)
    
    print(f"\n{'=' * 50}")
    print("CLEANUP SUMMARY")
    print(f"{'=' * 50}")
    
    if dry_run:
        print(f"Would delete {episodes_deleted} episodic nodes")
        print(f"Would delete {entities_deleted} entity nodes")
        print(f"Total nodes that would be removed: {episodes_deleted + entities_deleted}")
    else:
        print(f"Deleted {episodes_deleted} episodic nodes")
        print(f"Deleted {entities_deleted} entity nodes")
        print(f"Total nodes removed: {episodes_deleted + entities_deleted}")


if __name__ == '__main__':
    main()