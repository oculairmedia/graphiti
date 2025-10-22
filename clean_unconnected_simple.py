#!/usr/bin/env python3
"""
Simple script to delete unconnected nodes directly using FalkorDB.
"""

import redis
import json

def main():
    # Connect to FalkorDB
    r = redis.Redis(host='localhost', port=6379, decode_responses=True)
    
    # Check connection
    try:
        r.ping()
        print("✅ Connected to FalkorDB")
    except:
        print("❌ Could not connect to FalkorDB")
        return
    
    print("\n🔍 Checking unconnected nodes...")
    
    # Count unconnected episodic nodes
    episode_count_query = """
    MATCH (ep:Episodic)
    WHERE NOT (ep)-[:MENTIONS]->()
    RETURN count(ep) as count
    """
    
    result = r.execute_command('GRAPH.QUERY', 'graphiti_migration', episode_count_query)
    print(f"Episode query result: {result}")
    # Parse FalkorDB result format
    episode_count = result[1][0][0] if result[1] else 0
    print(f"📊 Found {episode_count} unconnected episodic nodes")
    
    # Count unconnected entity nodes  
    entity_count_query = """
    MATCH (ent:Entity)
    WHERE NOT ()-[:MENTIONS]->(ent)
    RETURN count(ent) as count
    """
    
    result = r.execute_command('GRAPH.QUERY', 'graphiti_migration', entity_count_query)
    print(f"Entity query result: {result}")
    entity_count = result[1][0][0] if result[1] else 0
    print(f"📊 Found {entity_count} unconnected entity nodes")
    
    total_to_delete = episode_count + entity_count
    
    if total_to_delete == 0:
        print("✅ No unconnected nodes found!")
        return
        
    print(f"\n⚠️  Total nodes to delete: {total_to_delete}")
    print("🚀 Proceeding with deletion...")
    
    # Skip confirmation in automated environment
    
    print("\n🧹 Deleting unconnected nodes...")
    
    # Delete unconnected episodic nodes
    if episode_count > 0:
        episode_delete_query = """
        MATCH (ep:Episodic)
        WHERE NOT (ep)-[:MENTIONS]->()
        DELETE ep
        """
        r.execute_command('GRAPH.QUERY', 'graphiti_migration', episode_delete_query)
        print(f"✅ Deleted {episode_count} episodic nodes")
    
    # Delete unconnected entity nodes
    if entity_count > 0:
        entity_delete_query = """
        MATCH (ent:Entity)
        WHERE NOT ()-[:MENTIONS]->(ent)
        DELETE ent
        """
        r.execute_command('GRAPH.QUERY', 'graphiti_migration', entity_delete_query)
        print(f"✅ Deleted {entity_count} entity nodes")
    
    # Verify cleanup
    print("\n🔍 Verifying cleanup...")
    
    result = r.execute_command('GRAPH.QUERY', 'graphiti_migration', episode_count_query)
    remaining_episodes = result[1][0][0] if result[1] else 0
    
    result = r.execute_command('GRAPH.QUERY', 'graphiti_migration', entity_count_query) 
    remaining_entities = result[1][0][0] if result[1] else 0
    
    print(f"📊 Remaining unconnected episodes: {remaining_episodes}")
    print(f"📊 Remaining unconnected entities: {remaining_entities}")
    
    if remaining_episodes == 0 and remaining_entities == 0:
        print("✅ All unconnected nodes successfully removed!")
    else:
        print("⚠️  Some unconnected nodes remain")

if __name__ == '__main__':
    main()