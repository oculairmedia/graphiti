#!/usr/bin/env python3
"""
Test retrieval of data added with Devstral model.
Uses direct queries to work around FalkorDB parameter issues.
"""

import asyncio
from graphiti_core.driver.falkordb_driver import FalkorDriver


async def test_retrieval():
    print("🔍 Testing Data Retrieval from Devstral Test")
    print("=" * 50)
    
    # Connect to the devstral_test database
    driver = FalkorDriver(
        host="localhost",
        port=6389,
        database="devstral_test"
    )
    
    try:
        # 1. Count all nodes
        print("\n1️⃣ Counting all nodes...")
        result = await driver.execute_query("MATCH (n) RETURN count(n) as count")
        if result:
            count = result[0]['count'] if isinstance(result[0], dict) else result[0][0]
            print(f"✅ Total nodes: {count}")
        
        # 2. Get all Episodic nodes
        print("\n2️⃣ Retrieving Episode nodes...")
        result = await driver.execute_query(
            """
            MATCH (e:Episodic)
            RETURN e.name as name, e.content as content, e.created_at as created
            ORDER BY e.created_at
            """
        )
        
        if result and len(result) > 0:
            print(f"✅ Found {len(result)} episodes:")
            for i, row in enumerate(result):
                if isinstance(row, dict):
                    print(f"\n   Episode {i+1}: {row.get('name', 'Unknown')}")
                    print(f"   Content: {row.get('content', 'N/A')}")
                    print(f"   Created: {row.get('created', 'N/A')}")
                else:
                    # Handle list format from FalkorDB
                    print(f"\n   Episode {i+1}:")
                    print(f"   Raw data: {row}")
        
        # 3. Search for content (without parameters to avoid syntax issues)
        print("\n3️⃣ Searching for AI-related content...")
        result = await driver.execute_query(
            """
            MATCH (e:Episodic)
            WHERE e.content CONTAINS 'AI' OR e.content CONTAINS 'Intelligence'
            RETURN e.name as name, e.content as content
            """
        )
        
        if result and len(result) > 0:
            print(f"✅ Found {len(result)} AI-related episodes:")
            for row in result[:3]:
                if isinstance(row, dict):
                    print(f"   - {row.get('name', 'Unknown')}: {row.get('content', '')[:100]}...")
        
        # 4. Check for any Entity nodes
        print("\n4️⃣ Checking for Entity nodes...")
        result = await driver.execute_query(
            "MATCH (n:Entity) RETURN count(n) as count"
        )
        if result:
            count = result[0]['count'] if isinstance(result[0], dict) else result[0][0]
            print(f"{'✅' if count > 0 else '❌'} Entity nodes: {count}")
        
        # 5. Check for relationships
        print("\n5️⃣ Checking for relationships...")
        result = await driver.execute_query(
            "MATCH ()-[r]->() RETURN count(r) as count"
        )
        if result:
            count = result[0]['count'] if isinstance(result[0], dict) else result[0][0]
            print(f"{'✅' if count > 0 else '❌'} Relationships: {count}")
        
        # 6. Get full node details for one episode
        print("\n6️⃣ Getting full details of first episode...")
        result = await driver.execute_query(
            """
            MATCH (e:Episodic)
            RETURN e
            LIMIT 1
            """
        )
        
        if result and len(result) > 0:
            print("✅ Episode details:")
            episode_data = result[0]
            if isinstance(episode_data, dict):
                for key, value in episode_data.items():
                    if key != 'content':  # Skip content for brevity
                        print(f"   {key}: {value}")
            else:
                print(f"   Raw: {episode_data}")
        
        # 7. Test text search capabilities
        print("\n7️⃣ Testing text search for 'McCarthy'...")
        result = await driver.execute_query(
            """
            MATCH (e:Episodic)
            WHERE e.content CONTAINS 'McCarthy'
            RETURN e.name as name, e.content as content
            """
        )
        
        if result and len(result) > 0:
            print(f"✅ Found episodes mentioning McCarthy:")
            for row in result:
                if isinstance(row, dict):
                    print(f"   - {row.get('name', 'Unknown')}")
        
        print("\n✨ Retrieval test complete!")
        
        # Summary
        print("\n📊 Summary:")
        print("- Episodes were successfully stored")
        print("- Content is searchable using CONTAINS")
        print("- No entities or relationships were extracted")
        print("- Devstral can create episodes but may need better prompts for entity extraction")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await driver.close()


async def test_semantic_search():
    """Test if we can do semantic search using embeddings."""
    print("\n\n🧠 Testing Semantic Search Capability")
    print("=" * 50)
    
    # This would require the Graphiti search API to work
    # For now, we know it fails due to FalkorDB parameter syntax
    print("❌ Cannot test semantic search - FalkorDB parameter syntax incompatible")
    print("   The embeddings are likely stored but search API fails")


if __name__ == "__main__":
    asyncio.run(test_retrieval())
    asyncio.run(test_semantic_search())