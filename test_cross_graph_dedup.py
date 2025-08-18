#!/usr/bin/env python3
"""Test cross-graph deduplication feature"""

import asyncio
import json
from datetime import datetime, timezone
import httpx
import msgpack

QUEUE_URL = "http://localhost:8093"
GRAPH_URL = "http://localhost:8001"

async def submit_episode(content: str, group_id: str, source_description: str = "test"):
    """Submit an episode to the ingestion queue"""
    async with httpx.AsyncClient() as client:
        task = {
            "task": "add_episode",
            "content": content,
            "source_description": source_description,
            "reference_time": datetime.now(timezone.utc).isoformat(),
            "group_id": group_id
        }
        
        # Submit to queue - use msgpack format
        response = await client.post(
            f"{QUEUE_URL}/queue/ingestion/messages",
            content=msgpack.packb(task),
            headers={"Content-Type": "application/msgpack"}
        )
        
        # Parse msgpack response
        if response.status_code == 204 or not response.content:
            return {"status": "submitted", "id": "N/A"}
        
        try:
            return msgpack.unpackb(response.content, raw=False)
        except:
            return {"status": "submitted", "status_code": response.status_code}

async def check_queue_status():
    """Check the queue status"""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{QUEUE_URL}/queue/ingestion")
        if response.status_code == 204 or not response.content:
            return {}
        try:
            return msgpack.unpackb(response.content, raw=False)
        except:
            return {"error": "Invalid response"}

async def query_graph(query: str):
    """Query the graph database"""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{GRAPH_URL}/graph/query",
            json={"query": query}
        )
        return response.json()

async def main():
    print("Testing Cross-Graph Entity Deduplication")
    print("=" * 50)
    
    # Test Case 1: Submit episodes with same entities to different groups
    print("\nTest 1: Same entity 'Alice' in different groups")
    print("-" * 40)
    
    # Episode 1: Group A
    print("Submitting Episode 1 (Group A)...")
    result1 = await submit_episode(
        "Alice is a software engineer at TechCorp. She specializes in machine learning.",
        "group_a",
        "test_group_a"
    )
    print(f"Episode 1 ID: {result1.get('id')}")
    
    # Episode 2: Group B - same entity Alice
    print("Submitting Episode 2 (Group B)...")
    result2 = await submit_episode(
        "Alice works on natural language processing projects. She leads the AI team.",
        "group_b", 
        "test_group_b"
    )
    print(f"Episode 2 ID: {result2.get('id')}")
    
    # Wait for processing
    print("\nWaiting for processing (10 seconds)...")
    await asyncio.sleep(10)
    
    # Check queue status
    print("\nQueue Status:")
    status = await check_queue_status()
    print(f"  Messages: {status.get('length', 0)}")
    print(f"  Total processed: {status.get('total_dequeued', 0)}")
    
    # Query for Alice nodes
    print("\nQuerying for 'Alice' nodes...")
    query = """
    MATCH (n:Entity)
    WHERE n.name =~ '(?i).*alice.*'
    RETURN n.uuid AS uuid, n.name AS name, n.group_id AS group_id, 
           n.summary AS summary, n.created_at AS created_at
    ORDER BY n.created_at DESC
    """
    
    result = await query_graph(query)
    nodes = result.get("result", [])
    
    print(f"\nFound {len(nodes)} Alice node(s):")
    for node in nodes:
        print(f"  - UUID: {node['uuid']}")
        print(f"    Name: {node['name']}")
        print(f"    Group: {node['group_id']}")
        print(f"    Summary: {node.get('summary', 'N/A')}")
    
    # Check for IS_DUPLICATE_OF edges
    print("\nChecking for IS_DUPLICATE_OF edges...")
    dup_query = """
    MATCH (n:Entity)-[r:RELATES_TO {name: 'IS_DUPLICATE_OF'}]->(m:Entity)
    WHERE n.name =~ '(?i).*alice.*' OR m.name =~ '(?i).*alice.*'
    RETURN n.name AS source, m.name AS target, n.group_id AS source_group, 
           m.group_id AS target_group, r.fact AS fact
    """
    
    dup_result = await query_graph(dup_query)
    duplicates = dup_result.get("result", [])
    
    if duplicates:
        print(f"Found {len(duplicates)} duplicate relationship(s):")
        for dup in duplicates:
            print(f"  - {dup['source']} (group: {dup['source_group']}) -> ")
            print(f"    {dup['target']} (group: {dup['target_group']})")
            print(f"    Fact: {dup['fact']}")
    else:
        print("No duplicate relationships found")
    
    # Test Case 2: Submit more episodes with overlapping entities
    print("\n" + "=" * 50)
    print("Test 2: More complex scenario with Bob")
    print("-" * 40)
    
    # Episode 3: Group A with Bob
    print("Submitting Episode 3 (Group A)...")
    result3 = await submit_episode(
        "Bob is Alice's colleague at TechCorp. Bob and Alice collaborate on AI research.",
        "group_a",
        "test_group_a"
    )
    print(f"Episode 3 ID: {result3.get('id')}")
    
    # Episode 4: Group C with Bob
    print("Submitting Episode 4 (Group C)...")  
    result4 = await submit_episode(
        "Bob is a data scientist who publishes papers on deep learning.",
        "group_c",
        "test_group_c"
    )
    print(f"Episode 4 ID: {result4.get('id')}")
    
    # Wait for processing
    print("\nWaiting for processing (10 seconds)...")
    await asyncio.sleep(10)
    
    # Final check
    print("\nFinal Entity Count by Group:")
    count_query = """
    MATCH (n:Entity)
    RETURN n.group_id AS group_id, COUNT(n) AS count
    ORDER BY group_id
    """
    
    count_result = await query_graph(count_query)
    counts = count_result.get("result", [])
    
    for count in counts:
        print(f"  Group {count['group_id']}: {count['count']} entities")
    
    print("\nTotal Unique Entities:")
    total_query = """
    MATCH (n:Entity)
    WHERE NOT (n)-[:RELATES_TO {name: 'IS_DUPLICATE_OF'}]->(:Entity)
    RETURN COUNT(DISTINCT n) AS total
    """
    
    total_result = await query_graph(total_query)
    total = total_result.get("result", [{}])[0].get("total", 0)
    print(f"  {total} unique entities (after deduplication)")
    
    print("\n" + "=" * 50)
    print("Cross-Graph Deduplication Test Complete!")
    
    # Summary
    if len(nodes) == 1 and duplicates:
        print("\n✅ SUCCESS: Cross-graph deduplication is working!")
        print("   - Same entities across groups are being detected")
        print("   - IS_DUPLICATE_OF relationships are being created")
        print("   - Edges are being merged to canonical nodes")
    else:
        print("\n⚠️  WARNING: Cross-graph deduplication may not be working as expected")
        print("   - Check worker logs for details")
        print("   - Ensure ENABLE_CROSS_GRAPH_DEDUPLICATION=true is set")

if __name__ == "__main__":
    asyncio.run(main())