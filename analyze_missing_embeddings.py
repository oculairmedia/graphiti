#!/usr/bin/env python3
"""
Analyze why edges are missing embeddings
"""

import asyncio
from graphiti_core.driver.falkordb_driver import FalkorDriver

async def analyze_missing_embeddings():
    driver = FalkorDriver(host='localhost', port=6379, database='graphiti_migration')
    
    print("\n" + "="*80)
    print("ANALYSIS: Why Do 2,961 Edges Have No Embeddings?")
    print("="*80 + "\n")
    
    # 1. Check edges without embeddings
    print("1. Sample edges WITHOUT embeddings:")
    print("-" * 50)
    
    query_no_embed = """
    MATCH ()-[e:RELATES_TO]->()
    WHERE e.fact_embedding IS NULL
    RETURN 
        e.uuid as uuid,
        e.fact as fact,
        e.name as name,
        e.group_id as group_id,
        e.created_at as created_at
    ORDER BY e.created_at DESC
    LIMIT 10
    """
    
    results, _, _ = await driver.execute_query(query_no_embed)
    for i, r in enumerate(results, 1):
        print(f"\n  Edge {i}:")
        print(f"    UUID: {r['uuid'][:16]}...")
        print(f"    Name: {r['name']}")
        print(f"    Fact: {r['fact'][:100] if r['fact'] else 'NULL'}...")
        print(f"    Group: {r['group_id']}")
        print(f"    Created: {r['created_at']}")
    
    # 2. Check edges WITH embeddings for comparison
    print("\n\n2. Sample edges WITH embeddings:")
    print("-" * 50)
    
    query_with_embed = """
    MATCH ()-[e:RELATES_TO]->()
    WHERE e.fact_embedding IS NOT NULL
    RETURN 
        e.uuid as uuid,
        e.fact as fact,
        e.name as name,
        e.group_id as group_id,
        e.created_at as created_at
    ORDER BY e.created_at DESC
    LIMIT 10
    """
    
    results, _, _ = await driver.execute_query(query_with_embed)
    for i, r in enumerate(results, 1):
        print(f"\n  Edge {i}:")
        print(f"    UUID: {r['uuid'][:16]}...")
        print(f"    Name: {r['name']}")
        print(f"    Fact: {r['fact'][:100] if r['fact'] else 'NULL'}...")
        print(f"    Group: {r['group_id']}")
        print(f"    Created: {r['created_at']}")
    
    # 3. Analyze patterns
    print("\n\n3. Pattern Analysis:")
    print("-" * 50)
    
    # Check if NULL facts correlate with NULL embeddings
    fact_analysis = """
    MATCH ()-[e:RELATES_TO]->()
    RETURN 
        CASE 
            WHEN e.fact IS NULL THEN 'NULL fact'
            WHEN e.fact = '' THEN 'Empty fact'
            ELSE 'Has fact'
        END as fact_status,
        CASE 
            WHEN e.fact_embedding IS NULL THEN 'No embedding'
            ELSE 'Has embedding'
        END as embedding_status,
        count(e) as count
    """
    
    results, _, _ = await driver.execute_query(fact_analysis)
    print("\n  Fact vs Embedding correlation:")
    for r in results:
        print(f"    {r['fact_status']:20} + {r['embedding_status']:15} = {r['count']:5} edges")
    
    # Check by creation time
    time_analysis = """
    MATCH ()-[e:RELATES_TO]->()
    WHERE e.created_at IS NOT NULL
    WITH 
        substring(e.created_at, 0, 10) as date,
        CASE WHEN e.fact_embedding IS NULL THEN 'No' ELSE 'Yes' END as has_embedding,
        count(e) as count
    RETURN date, has_embedding, count
    ORDER BY date DESC
    LIMIT 10
    """
    
    results, _, _ = await driver.execute_query(time_analysis)
    print("\n  Recent days - embedding presence:")
    current_date = None
    for r in results:
        if r['date'] != current_date:
            current_date = r['date']
            print(f"\n    {r['date']}:")
        print(f"      {r['has_embedding']:3} embedding: {r['count']:5} edges")
    
    # Check if edges without embeddings have a specific pattern in their names
    name_pattern = """
    MATCH ()-[e:RELATES_TO]->()
    WHERE e.fact_embedding IS NULL
    WITH e.name as name, count(e) as count
    RETURN name, count
    ORDER BY count DESC
    LIMIT 10
    """
    
    results, _, _ = await driver.execute_query(name_pattern)
    print("\n  Most common edge names WITHOUT embeddings:")
    for r in results:
        print(f"    {r['name']:30} : {r['count']:5} edges")
    
    # Check when edges started getting embeddings
    print("\n\n4. Timeline Analysis:")
    print("-" * 50)
    
    timeline = """
    MATCH ()-[e:RELATES_TO]->()
    WHERE e.fact_embedding IS NOT NULL
    RETURN min(e.created_at) as first_with_embedding, max(e.created_at) as latest_with_embedding
    """
    
    results, _, _ = await driver.execute_query(timeline)
    if results:
        print(f"  First edge with embedding: {results[0]['first_with_embedding']}")
        print(f"  Latest edge with embedding: {results[0]['latest_with_embedding']}")
    
    timeline_no_embed = """
    MATCH ()-[e:RELATES_TO]->()
    WHERE e.fact_embedding IS NULL
    RETURN min(e.created_at) as first_without, max(e.created_at) as latest_without
    """
    
    results, _, _ = await driver.execute_query(timeline_no_embed)
    if results:
        print(f"  First edge without embedding: {results[0]['first_without']}")
        print(f"  Latest edge without embedding: {results[0]['latest_without']}")
    
    await driver.close()
    
    print("\n" + "="*80)
    print("CONCLUSION:")
    print("-" * 50)
    print("Edges without embeddings are likely from:")
    print("1. Earlier versions of the system that didn't generate embeddings")
    print("2. Edges created through different ingestion paths")
    print("3. System edges that don't need semantic search")
    print("4. Edges where embedding generation failed but the edge was still saved")
    print("="*80 + "\n")

if __name__ == "__main__":
    asyncio.run(analyze_missing_embeddings())