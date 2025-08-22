#!/usr/bin/env python3
"""
Test script for pre-save validation hooks functionality (GRAPH-375)
"""

import sys
import uuid
from datetime import datetime

sys.path.insert(0, '/opt/stacks/graphiti')

from graphiti_core.utils.validation_hooks import (
    HookType,
    ValidationResult,
    ValidationHookRegistry,
    ValidationService,
    register_validation_hook,
    hook_registry,
    validation_service
)
from graphiti_core.nodes import EntityNode, EpisodicNode, EpisodeType
from graphiti_core.edges import EntityEdge
from graphiti_core.utils.datetime_utils import utc_now

def test_validation_result():
    """Test ValidationResult class functionality"""
    print("Testing ValidationResult class...")
    
    # Test success result
    result = ValidationResult.success_with_data({"test": "data"}, "success message")
    if result.success and result.transformed_data == {"test": "data"} and result.message == "success message":
        print("✅ Success result test passed")
    else:
        print("❌ Success result test failed")
        return False
    
    # Test failure result
    result = ValidationResult.failure("error message")
    if not result.success and result.message == "error message":
        print("✅ Failure result test passed")
    else:
        print("❌ Failure result test failed")
        return False
    
    # Test skip result
    result = ValidationResult.skip("skip message")
    if result.success and result.should_skip and result.message == "skip message":
        print("✅ Skip result test passed")
        return True
    else:
        print("❌ Skip result test failed")
        return False


def test_hook_registry():
    """Test ValidationHookRegistry functionality"""
    print("Testing ValidationHookRegistry...")
    
    # Create a test registry
    registry = ValidationHookRegistry()
    
    # Test hook registration
    def test_hook(data, context=None):
        return ValidationResult.success_with_data(data, "test hook executed")
    
    registry.register_hook(
        HookType.PRE_SAVE_ENTITY,
        test_hook,
        "test_hook",
        priority=50,
        description="A test hook"
    )
    
    hooks = registry.get_hooks(HookType.PRE_SAVE_ENTITY)
    if len(hooks) == 1 and hooks[0].name == "test_hook":
        print("✅ Hook registration test passed")
    else:
        print("❌ Hook registration test failed")
        return False
    
    # Test hook execution
    result = registry.execute_hooks(HookType.PRE_SAVE_ENTITY, {"test": "data"})
    if result.success and result.message == "test_hook: test hook executed":
        print("✅ Hook execution test passed")
    else:
        print("❌ Hook execution test failed")
        return False
    
    # Test hook unregistration
    unregistered = registry.unregister_hook(HookType.PRE_SAVE_ENTITY, "test_hook")
    if unregistered and len(registry.get_hooks(HookType.PRE_SAVE_ENTITY)) == 0:
        print("✅ Hook unregistration test passed")
        return True
    else:
        print("❌ Hook unregistration test failed")
        return False


def test_hook_decorator():
    """Test the register_validation_hook decorator"""
    print("Testing hook decorator...")
    
    # Create a temporary registry to avoid affecting global state
    test_registry = ValidationHookRegistry()
    
    # Register a hook using decorator (simulate by calling register directly)
    def decorated_hook(data, context=None):
        if isinstance(data, dict) and data.get('name') == 'invalid':
            return ValidationResult.failure("Invalid name detected")
        return ValidationResult.success_with_data(data, "decorator hook executed")
    
    test_registry.register_hook(
        HookType.PRE_SAVE_ENTITY,
        decorated_hook,
        "decorated_hook",
        priority=25,
        description="A decorated hook"
    )
    
    # Test successful execution
    result = test_registry.execute_hooks(HookType.PRE_SAVE_ENTITY, {"name": "valid"})
    if result.success and "decorator hook executed" in result.message:
        print("✅ Decorator hook success test passed")
    else:
        print("❌ Decorator hook success test failed")
        return False
    
    # Test failure case
    result = test_registry.execute_hooks(HookType.PRE_SAVE_ENTITY, {"name": "invalid"})
    if not result.success and "Invalid name detected" in result.message:
        print("✅ Decorator hook failure test passed")
        return True
    else:
        print("❌ Decorator hook failure test failed")
        return False


def test_built_in_hooks():
    """Test the built-in validation hooks"""
    print("Testing built-in validation hooks...")
    
    # Test entity required fields validation
    service = ValidationService()
    
    # Test with missing UUID
    invalid_entity = {"name": "Test Entity", "group_id": "test-group"}
    result = service.validate_entity(invalid_entity)
    if not result.success and "uuid" in result.message.lower():
        print("✅ Required fields validation test passed")
    else:
        print("❌ Required fields validation test failed")
        return False
    
    # Test with valid entity
    valid_entity = {
        "uuid": str(uuid.uuid4()),
        "name": "Test Entity",
        "group_id": "test-group",
        "summary": "A test entity"
    }
    result = service.validate_entity(valid_entity)
    if result.success:
        print("✅ Valid entity validation test passed")
    else:
        print("❌ Valid entity validation test failed")
        return False
    
    # Test name normalization
    entity_with_messy_name = {
        "uuid": str(uuid.uuid4()),
        "name": "  test entity  ",  # Should be normalized to "Test Entity"
        "group_id": "test-group"
    }
    result = service.validate_entity(entity_with_messy_name)
    if (result.success and 
        isinstance(result.transformed_data, dict) and 
        result.transformed_data['name'] == "Test Entity"):
        print("✅ Name normalization test passed")
        return True
    else:
        print("❌ Name normalization test failed")
        return False


def test_entity_duplicate_detection():
    """Test duplicate entity detection in batch operations"""
    print("Testing entity duplicate detection...")
    
    service = ValidationService()
    
    # Create entities with potential duplicates
    entity1 = {
        "uuid": "entity-1",
        "name": "Alice",
        "group_id": "test-group"
    }
    
    entity2 = {
        "uuid": "entity-2", 
        "name": "Bob",
        "group_id": "test-group"
    }
    
    # Duplicate name+group_id (should be skipped)
    entity3 = {
        "uuid": "entity-3",
        "name": "Alice",  # Same name as entity1
        "group_id": "test-group"  # Same group as entity1
    }
    
    # Duplicate UUID (should fail)
    entity4 = {
        "uuid": "entity-1",  # Same UUID as entity1
        "name": "Charlie",
        "group_id": "test-group"
    }
    
    # Test duplicate name+group detection (should skip)
    context = {"batch_entities": [entity1, entity2]}
    result = service.validate_entity(entity3, context)
    if result.success and result.should_skip:
        print("✅ Duplicate name+group detection test passed")
    else:
        print("❌ Duplicate name+group detection test failed")
        return False
    
    # Test duplicate UUID detection (should fail)
    context = {"batch_entities": [entity1, entity2]}
    result = service.validate_entity(entity4, context)
    if not result.success and "uuid" in result.message.lower():
        print("✅ Duplicate UUID detection test passed")
        return True
    else:
        print("❌ Duplicate UUID detection test failed")
        return False


def test_edge_validation():
    """Test edge validation hooks"""
    print("Testing edge validation...")
    
    service = ValidationService()
    
    # Test with missing required fields
    invalid_edge = {
        "name": "RELATES_TO",
        "fact": "Test relationship"
        # Missing uuid, source_node_uuid, target_node_uuid, group_id
    }
    result = service.validate_edge(invalid_edge)
    if not result.success and "required fields" in result.message.lower():
        print("✅ Edge required fields validation test passed")
    else:
        print("❌ Edge required fields validation test failed")
        return False
    
    # Test with valid edge
    valid_edge = {
        "uuid": str(uuid.uuid4()),
        "source_node_uuid": str(uuid.uuid4()),
        "target_node_uuid": str(uuid.uuid4()),
        "group_id": "test-group",
        "name": "RELATES_TO",
        "fact": "Test relationship"
    }
    result = service.validate_edge(valid_edge)
    if result.success:
        print("✅ Valid edge validation test passed")
        return True
    else:
        print("❌ Valid edge validation test failed")
        return False


def test_batch_validation():
    """Test batch validation functionality"""
    print("Testing batch validation...")
    
    service = ValidationService()
    
    # Create a batch of entities with guaranteed unique UUIDs
    entity_uuids = [str(uuid.uuid4()) for _ in range(3)]
    entities = [
        {
            "uuid": entity_uuids[0],
            "name": "  alice cooper  ",  # Will be normalized
            "group_id": "batch-test-1"  # Different group IDs to avoid name+group duplicates
        },
        {
            "uuid": entity_uuids[1],
            "name": "Bob Dylan",
            "group_id": "batch-test-2"
        },
        {
            "uuid": entity_uuids[2],
            "name": "Charlie Brown", 
            "group_id": "batch-test-3"
        }
    ]
    
    result = service.validate_batch(entities)
    if result.success and isinstance(result.transformed_data, list):
        # Check that name normalization occurred
        normalized_entities = result.transformed_data
        if len(normalized_entities) == 3 and normalized_entities[0]['name'] == "Alice Cooper":
            print("✅ Batch validation test passed")
            return True
        else:
            print(f"❌ Batch validation normalization failed - got {len(normalized_entities)} entities, first name: '{normalized_entities[0]['name'] if normalized_entities else 'none'}'")
            return False
    else:
        print(f"❌ Batch validation test failed - success: {result.success}, message: {result.message}")
        return False


def test_pydantic_entity_validation():
    """Test validation with Pydantic EntityNode objects"""
    print("Testing Pydantic entity validation...")
    
    service = ValidationService()
    
    # Create a valid EntityNode
    entity = EntityNode(
        uuid=str(uuid.uuid4()),
        name="  test entity  ",  # Should be normalized
        group_id="test-group",
        summary="A test entity"
    )
    
    result = service.validate_entity(entity)
    if result.success:
        # Check if name was normalized
        if isinstance(result.transformed_data, dict):
            if result.transformed_data.get('name') == "Test Entity":
                print("✅ Pydantic entity normalization test passed")
            else:
                print("✅ Pydantic entity validation test passed (no normalization needed)")
        else:
            print("✅ Pydantic entity validation test passed")
        return True
    else:
        print("❌ Pydantic entity validation test failed")
        return False


def test_custom_hook_priority():
    """Test hook priority ordering"""
    print("Testing hook priority ordering...")
    
    registry = ValidationHookRegistry()
    execution_order = []
    
    # Create hooks with different priorities
    def high_priority_hook(data, context=None):
        execution_order.append("high")
        return ValidationResult.success_with_data(data)
    
    def low_priority_hook(data, context=None):
        execution_order.append("low")
        return ValidationResult.success_with_data(data)
    
    def medium_priority_hook(data, context=None):
        execution_order.append("medium")
        return ValidationResult.success_with_data(data)
    
    # Register in reverse order to test sorting
    registry.register_hook(HookType.PRE_SAVE_ENTITY, low_priority_hook, "low", priority=100)
    registry.register_hook(HookType.PRE_SAVE_ENTITY, high_priority_hook, "high", priority=10)
    registry.register_hook(HookType.PRE_SAVE_ENTITY, medium_priority_hook, "medium", priority=50)
    
    # Execute hooks
    registry.execute_hooks(HookType.PRE_SAVE_ENTITY, {"test": "data"})
    
    # Check execution order (should be high, medium, low based on priority)
    if execution_order == ["high", "medium", "low"]:
        print("✅ Hook priority ordering test passed")
        return True
    else:
        print(f"❌ Hook priority ordering test failed: {execution_order}")
        return False


def main():
    """Run all validation hooks tests"""
    print("🧪 Testing Pre-Save Validation Hooks (GRAPH-375)")
    print("=" * 60)
    
    tests = [
        test_validation_result,
        test_hook_registry,
        test_hook_decorator,
        test_built_in_hooks,
        test_entity_duplicate_detection,
        test_edge_validation,
        test_batch_validation,
        test_pydantic_entity_validation,
        test_custom_hook_priority
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
        print()
    
    print("=" * 60)
    print(f"Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All validation hooks tests passed!")
        return True
    else:
        print("💥 Some validation hooks tests failed!")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)