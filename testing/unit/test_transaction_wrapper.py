#!/usr/bin/env python3
"""
Test script for transaction wrapper functionality (GRAPH-377)
"""

import sys
import asyncio
import uuid
from datetime import datetime

sys.path.insert(0, '/opt/stacks/graphiti')

from graphiti_core.driver.falkordb_driver import FalkorDriver
from graphiti_core.utils.transaction import (
    atomic_transaction,
    execute_atomic_operation,
    batch_execute_atomic,
    safe_merge_entity,
    TransactionManager,
    TransactionError
)

async def test_atomic_transaction_success():
    """Test that atomic transactions work correctly for successful operations"""
    print("Testing atomic transaction success...")
    
    try:
        driver = FalkorDriver(host='localhost', port=6379, database='test_transactions')
        
        # Clean up any existing test data
        await driver.execute_query("MATCH (n:TestEntity) DELETE n")
        
        # Test successful atomic transaction
        async with atomic_transaction(driver) as tx:
            await tx.run(
                "CREATE (n:TestEntity {uuid: $uuid, name: $name})",
                uuid="test-1",
                name="First Entity"
            )
            await tx.run(
                "CREATE (n:TestEntity {uuid: $uuid, name: $name})",
                uuid="test-2", 
                name="Second Entity"
            )
        
        # Verify both entities were created
        result, _, _ = await driver.execute_query(
            "MATCH (n:TestEntity) RETURN count(n) as count"
        )
        
        if result and len(result) > 0 and result[0]['count'] == 2:
            print("✅ Atomic transaction success test passed")
            return True
        else:
            print(f"❌ Expected 2 entities, got {result[0]['count'] if result else 0}")
            return False
            
    except Exception as e:
        print(f"❌ Atomic transaction success test failed: {e}")
        return False
    finally:
        if 'driver' in locals():
            await driver.close()


async def test_atomic_transaction_rollback():
    """Test that atomic transactions roll back on failure"""
    print("Testing atomic transaction rollback...")
    
    try:
        driver = FalkorDriver(host='localhost', port=6379, database='test_transactions')
        
        # Clean up any existing test data more thoroughly 
        await driver.execute_query("MATCH (n) DETACH DELETE n")
        
        # Verify cleanup worked
        initial_count, _, _ = await driver.execute_query(
            "MATCH (n:TestEntity) RETURN count(n) as count"
        )
        initial_entities = initial_count[0]['count'] if initial_count else 0
        print(f"Initial entity count: {initial_entities}")
        
        # Test transaction rollback on failure
        rollback_occurred = False
        try:
            async with atomic_transaction(driver) as tx:
                await tx.run(
                    "CREATE (n:TestEntity {uuid: $uuid, name: $name})",
                    uuid="test-rollback",
                    name="Should Be Rolled Back"
                )
                # This should cause the transaction to fail
                await tx.run("INVALID CYPHER QUERY")
                
        except TransactionError:
            # Expected to fail
            rollback_occurred = True
        
        if not rollback_occurred:
            print("❌ Transaction should have failed but didn't")
            return False
        
        # Verify no new entities were created (rollback worked)
        result, _, _ = await driver.execute_query(
            "MATCH (n:TestEntity) RETURN count(n) as count"
        )
        final_entities = result[0]['count'] if result else 0
        
        print(f"Final entity count: {final_entities}")
        
        if final_entities == initial_entities:
            print("✅ Atomic transaction rollback test passed")
            return True
        else:
            print(f"❌ Expected {initial_entities} entities after rollback, got {final_entities}")
            return False
            
    except Exception as e:
        print(f"❌ Atomic transaction rollback test failed: {e}")
        return False
    finally:
        if 'driver' in locals():
            await driver.close()


async def test_batch_execute_atomic():
    """Test batch execution of multiple queries atomically"""
    print("Testing batch atomic execution...")
    
    try:
        driver = FalkorDriver(host='localhost', port=6379, database='test_transactions')
        
        # Clean up any existing test data
        await driver.execute_query("MATCH (n:TestEntity) DELETE n")
        
        # Define batch of queries
        queries = [
            ("CREATE (n:TestEntity {uuid: $uuid, name: $name})", 
             {"uuid": "batch-1", "name": "Batch Entity 1"}),
            ("CREATE (n:TestEntity {uuid: $uuid, name: $name})", 
             {"uuid": "batch-2", "name": "Batch Entity 2"}),
            ("CREATE (n:TestEntity {uuid: $uuid, name: $name})", 
             {"uuid": "batch-3", "name": "Batch Entity 3"}),
        ]
        
        # Execute batch atomically
        results = await batch_execute_atomic(driver, queries)
        
        # Verify all entities were created
        result, _, _ = await driver.execute_query(
            "MATCH (n:TestEntity) RETURN count(n) as count"
        )
        
        if result and len(result) > 0 and result[0]['count'] == 3:
            print("✅ Batch atomic execution test passed")
            return True
        else:
            print(f"❌ Expected 3 entities, got {result[0]['count'] if result else 0}")
            return False
            
    except Exception as e:
        print(f"❌ Batch atomic execution test failed: {e}")
        return False
    finally:
        if 'driver' in locals():
            await driver.close()


async def test_safe_merge_entity():
    """Test safe entity merging with validation"""
    print("Testing safe entity merging...")
    
    try:
        driver = FalkorDriver(host='localhost', port=6379, database='test_transactions')
        
        # Clean up any existing test data
        await driver.execute_query("MATCH (n:Entity) DELETE n")
        
        # Test creating new entity
        entity_data = {
            "uuid": "merge-test-1",
            "name": "Merge Test Entity",
            "group_id": "test-group",
            "summary": "A test entity for merge validation"
        }
        
        result = await safe_merge_entity(driver, entity_data)
        
        if result == entity_data:
            print("✅ Safe entity merge (create) test passed")
        else:
            print("❌ Safe entity merge (create) test failed")
            return False
        
        # Test updating existing entity
        entity_data["summary"] = "Updated summary"
        result = await safe_merge_entity(driver, entity_data)
        
        if result == entity_data:
            print("✅ Safe entity merge (update) test passed")
        else:
            print("❌ Safe entity merge (update) test failed")
            return False
        
        # Test validation failure
        try:
            invalid_entity = {"name": "No UUID Entity"}
            await safe_merge_entity(driver, invalid_entity)
            print("❌ Safe entity merge should have failed validation")
            return False
        except TransactionError:
            print("✅ Safe entity merge validation test passed")
            return True
            
    except Exception as e:
        print(f"❌ Safe entity merge test failed: {e}")
        return False
    finally:
        if 'driver' in locals():
            await driver.close()


async def test_transaction_manager():
    """Test TransactionManager with retry functionality"""
    print("Testing TransactionManager...")
    
    try:
        driver = FalkorDriver(host='localhost', port=6379, database='test_transactions')
        manager = TransactionManager(driver)
        
        # Clean up any existing test data
        await driver.execute_query("MATCH (n:TestEntity) DELETE n")
        
        # Test successful operation
        async def create_test_entities(tx):
            await tx.run(
                "CREATE (n:TestEntity {uuid: $uuid, name: $name})",
                uuid="manager-1",
                name="Manager Entity 1"
            )
            await tx.run(
                "CREATE (n:TestEntity {uuid: $uuid, name: $name})",
                uuid="manager-2",
                name="Manager Entity 2"
            )
            return "success"
        
        result = await manager.execute_with_retry(create_test_entities)
        
        if result == "success":
            print("✅ TransactionManager operation test passed")
        else:
            print("❌ TransactionManager operation test failed")
            return False
        
        # Test batch entity creation
        entities = [
            {"uuid": "batch-entity-1", "name": "Batch 1", "group_id": "batch-group"},
            {"uuid": "batch-entity-2", "name": "Batch 2", "group_id": "batch-group"},
            {"uuid": "batch-entity-3", "name": "Batch 3", "group_id": "batch-group"}
        ]
        
        results = await manager.batch_create_entities(entities)
        
        if len(results) == 3:
            print("✅ TransactionManager batch creation test passed")
            return True
        else:
            print("❌ TransactionManager batch creation test failed")
            return False
            
    except Exception as e:
        print(f"❌ TransactionManager test failed: {e}")
        return False
    finally:
        if 'driver' in locals():
            await driver.close()


async def test_complex_atomic_operation():
    """Test complex multi-step atomic operation"""
    print("Testing complex atomic operation...")
    
    try:
        driver = FalkorDriver(host='localhost', port=6379, database='test_transactions')
        
        # Clean up any existing test data
        await driver.execute_query("MATCH (n) DETACH DELETE n")
        
        async def create_entity_with_relationships(tx):
            # Create source entity
            await tx.run(
                "CREATE (n:Entity {uuid: $uuid, name: $name, group_id: $group_id})",
                uuid="source-entity",
                name="Source Entity", 
                group_id="test-group"
            )
            
            # Create target entity
            await tx.run(
                "CREATE (n:Entity {uuid: $uuid, name: $name, group_id: $group_id})",
                uuid="target-entity",
                name="Target Entity",
                group_id="test-group"
            )
            
            # Create relationship between them
            await tx.run(
                "MATCH (s:Entity {uuid: $source}), (t:Entity {uuid: $target}) "
                "CREATE (s)-[:RELATES_TO {name: $rel_name, uuid: $rel_uuid, group_id: $group_id}]->(t)",
                source="source-entity",
                target="target-entity",
                rel_name="TEST_RELATIONSHIP",
                rel_uuid=str(uuid.uuid4()),
                group_id="test-group"
            )
            
            return "complex_operation_success"
        
        result = await execute_atomic_operation(driver, create_entity_with_relationships)
        
        if result == "complex_operation_success":
            # Verify the complex structure was created
            entity_count, _, _ = await driver.execute_query(
                "MATCH (n:Entity) RETURN count(n) as count"
            )
            rel_count, _, _ = await driver.execute_query(
                "MATCH ()-[r:RELATES_TO]->() RETURN count(r) as count"
            )
            
            entities = entity_count[0]['count'] if entity_count else 0
            relationships = rel_count[0]['count'] if rel_count else 0
            
            if entities == 2 and relationships == 1:
                print("✅ Complex atomic operation test passed")
                return True
            else:
                print(f"❌ Expected 2 entities and 1 relationship, got {entities} entities and {relationships} relationships")
                return False
        else:
            print("❌ Complex atomic operation failed")
            return False
            
    except Exception as e:
        print(f"❌ Complex atomic operation test failed: {e}")
        return False
    finally:
        if 'driver' in locals():
            await driver.close()


async def main():
    """Run all transaction wrapper tests"""
    print("🧪 Testing Transaction Wrapper Functionality (GRAPH-377)")
    print("=" * 60)
    
    tests = [
        test_atomic_transaction_success,
        test_atomic_transaction_rollback,
        test_batch_execute_atomic,
        test_safe_merge_entity,
        test_transaction_manager,
        test_complex_atomic_operation
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if await test():
            passed += 1
        print()
    
    print("=" * 60)
    print(f"Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All transaction wrapper tests passed!")
        return True
    else:
        print("💥 Some transaction tests failed!")
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)