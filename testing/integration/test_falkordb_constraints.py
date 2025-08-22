#!/usr/bin/env python3
"""
Test script for FalkorDB unique constraints enforcement (GRAPH-376)
"""

import sys
import asyncio
from datetime import datetime

sys.path.insert(0, '/opt/stacks/graphiti')

from graphiti_core.driver.falkordb_driver import FalkorDriver
from graphiti_core.utils.maintenance.graph_data_operations import build_indices_and_constraints

async def test_unique_constraints():
    """Test that unique constraints prevent duplicate entities"""
    print("Testing FalkorDB unique constraints...")
    
    try:
        # Connect to FalkorDB
        driver = FalkorDriver(host='localhost', port=6379, database='test_constraints')
        
        # Build indices and constraints
        print("Building indices and constraints...")
        await build_indices_and_constraints(driver, delete_existing=False)
        
        # Test 1: Try to create duplicate Entity nodes with same UUID
        print("\n1. Testing Entity UUID uniqueness...")
        duplicate_uuid = "test-uuid-123"
        
        try:
            # First entity should succeed
            await driver.execute_query(
                "CREATE (n:Entity {uuid: $uuid, name: $name, group_id: $group_id})",
                uuid=duplicate_uuid,
                name="Alice",
                group_id="test_group"
            )
            print("✅ First entity created successfully")
            
            # Second entity with same UUID should fail
            await driver.execute_query(
                "CREATE (n:Entity {uuid: $uuid, name: $name, group_id: $group_id})", 
                uuid=duplicate_uuid,
                name="Bob", 
                group_id="test_group"
            )
            print("❌ Second entity with duplicate UUID should have failed but didn't")
            return False
            
        except Exception as e:
            if "unique" in str(e).lower() or "constraint" in str(e).lower():
                print("✅ UUID uniqueness constraint working correctly")
            else:
                print(f"❌ Unexpected error: {e}")
                return False
        
        # Test 2: Try to create duplicate Entity nodes with same name+group_id
        print("\n2. Testing Entity name+group_id uniqueness...")
        
        try:
            # Clear previous data
            await driver.execute_query("MATCH (n:Entity) DELETE n")
            
            # First entity should succeed
            await driver.execute_query(
                "CREATE (n:Entity {uuid: $uuid1, name: $name, group_id: $group_id})",
                uuid1="uuid-1",
                name="Charlie",
                group_id="test_group"
            )
            print("✅ First entity with name+group_id created successfully")
            
            # Second entity with same name+group_id should fail
            await driver.execute_query(
                "CREATE (n:Entity {uuid: $uuid2, name: $name, group_id: $group_id})",
                uuid2="uuid-2", 
                name="Charlie",
                group_id="test_group"
            )
            print("❌ Second entity with duplicate name+group_id should have failed but didn't")
            return False
            
        except Exception as e:
            if "unique" in str(e).lower() or "constraint" in str(e).lower():
                print("✅ Name+group_id uniqueness constraint working correctly")
            else:
                print(f"❌ Unexpected error: {e}")
                return False
        
        # Test 3: Test existence constraints
        print("\n3. Testing existence constraints...")
        
        try:
            # Clear previous data
            await driver.execute_query("MATCH (n:Entity) DELETE n")
            
            # Try to create entity without required field (should fail)
            await driver.execute_query(
                "CREATE (n:Entity {uuid: $uuid})",  # Missing name and group_id
                uuid="uuid-incomplete"
            )
            print("❌ Entity without required fields should have failed but didn't")
            return False
            
        except Exception as e:
            if "exists" in str(e).lower() or "constraint" in str(e).lower():
                print("✅ Existence constraints working correctly")
            else:
                print(f"❌ Unexpected error: {e}")
                return False
        
        # Test 4: Verify valid entities can still be created
        print("\n4. Testing valid entity creation...")
        
        try:
            # Clear previous data
            await driver.execute_query("MATCH (n) DETACH DELETE n")
            
            # Create valid entity
            await driver.execute_query(
                "CREATE (n:Entity {uuid: $uuid, name: $name, group_id: $group_id})",
                uuid="valid-uuid",
                name="Valid Entity",
                group_id="valid_group"
            )
            
            # Verify it was created
            result, _, _ = await driver.execute_query(
                "MATCH (n:Entity {uuid: $uuid}) RETURN n.name as name",
                uuid="valid-uuid"
            )
            
            if result and len(result) == 1 and result[0]['name'] == 'Valid Entity':
                print("✅ Valid entity creation still works")
                return True
            else:
                print("❌ Valid entity was not created properly")
                return False
                
        except Exception as e:
            print(f"❌ Valid entity creation failed: {e}")
            return False
            
    except Exception as e:
        print(f"❌ Test setup failed: {e}")
        return False
    finally:
        if 'driver' in locals():
            await driver.close()

async def main():
    """Run constraint tests"""
    print("🧪 Testing FalkorDB Unique Constraints (GRAPH-376)")
    print("=" * 60)
    
    success = await test_unique_constraints()
    
    print("=" * 60)
    if success:
        print("🎉 All constraint tests passed!")
        return True
    else:
        print("💥 Some constraint tests failed!")
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)