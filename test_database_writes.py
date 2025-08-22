import asyncio
from graphiti_core.driver.falkordb_driver import FalkorDriver
from datetime import datetime

async def test_database_connection():
    """Test basic FalkorDB connectivity and write operations"""
    driver = FalkorDriver(
        host="falkordb",  # Use your FalkorDB host
        port=6379,
        database="graphiti_migration"
    )
    
    print("=== Testing FalkorDB Connection ===")
    
    try:
        # Test 1: Basic connectivity
        result = await driver.execute_query("RETURN 1 as test")
        print(f"✅ Connection test: {result}")
        
        # Test 2: Node creation
        test_uuid = f"test-{datetime.now().timestamp()}"
        await driver.execute_query("""
            CREATE (n:TestNode {uuid: $uuid, name: $name, created_at: $created_at})
            RETURN n.uuid as uuid
        """, uuid=test_uuid, name="Test Node", created_at=datetime.now().isoformat())
        
        # Test 3: Verify node was created
        result = await driver.execute_query("""
            MATCH (n:TestNode {uuid: $uuid}) 
            RETURN count(n) as count, n.name as name
        """, uuid=test_uuid)
        print(f"✅ Node creation test: {result}")
        
        # Test 4: Episodic node creation (same as worker)
        episode_uuid = f"episode-{datetime.now().timestamp()}"
        await driver.execute_query("""
            CREATE (n:Episodic {
                uuid: $uuid, 
                name: $name, 
                group_id: $group_id,
                source: $source,
                content: $content,
                created_at: $created_at,
                valid_at: $valid_at
            })
            RETURN n.uuid as uuid
        """, 
        uuid=episode_uuid,
        name="Test Episode",
        group_id="test_group",
        source="message",
        content="Test episode content",
        created_at=datetime.now().isoformat(),
        valid_at=datetime.now().isoformat())
        
        # Test 5: Verify episodic node
        result = await driver.execute_query("""
            MATCH (n:Episodic {uuid: $uuid}) 
            RETURN count(n) as count
        """, uuid=episode_uuid)
        print(f"✅ Episodic node test: {result}")
        
        # Test 6: Check total episodic nodes
        result = await driver.execute_query("MATCH (n:Episodic) RETURN count(n) as total")
        print(f"📊 Total episodic nodes in database: {result}")
        
        # Cleanup
        await driver.execute_query("MATCH (n:TestNode) DELETE n")
        await driver.execute_query(f"MATCH (n:Episodic {{uuid: '{episode_uuid}'}}) DELETE n")
        
        print("✅ Database connection test PASSED")
        return True
        
    except Exception as e:
        print(f"❌ Database test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    asyncio.run(test_database_connection())