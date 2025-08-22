#!/usr/bin/env python3
"""
Test script for post-save integrity checks system.

This script validates the functionality of post-save validation
to ensure data integrity after database operations.
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta
from unittest.mock import MagicMock, AsyncMock
from uuid import uuid4

# Add the project root to path for imports
sys.path.append('/opt/stacks/graphiti')

from graphiti_core.utils.post_save_validation import (
    PostSaveValidator,
    IntegrityCheckResult,
    get_post_save_config,
    run_post_save_checks
)
from graphiti_core.nodes import EntityNode
from graphiti_core.edges import EntityEdge


def create_mock_driver():
    """Create a mock GraphDriver for testing."""
    driver = MagicMock()
    driver.provider = 'neo4j'
    
    # Mock session
    session = AsyncMock()
    driver.session.return_value = session
    
    # Mock database responses
    async def mock_run(query, **params):
        result = AsyncMock()
        
        # Edge reference check: both nodes exist
        if 'source_uuid' in params or 'target_uuid' in params or 'source_count' in query or 'target_count' in query:
            record = {'source_count': 1, 'target_count': 1}
        # Default: entity exists
        else:
            record = {'count': 1}
            
        result.single.return_value = record
        return result
    
    session.run.side_effect = mock_run
    
    return driver


def create_test_entity(name: str, uuid: str = None, **kwargs) -> dict:
    """Create a test entity dictionary."""
    entity = {
        'uuid': uuid or str(uuid4()),
        'name': name,
        'group_id': 'test-group',
        'created_at': datetime.now(),
        'summary': kwargs.get('summary', f'Test entity: {name}'),
        'labels': ['Entity', 'Test']
    }
    entity.update(kwargs)
    return entity


def create_test_edge(source_uuid: str, target_uuid: str, uuid: str = None, **kwargs) -> dict:
    """Create a test edge dictionary."""
    edge = {
        'uuid': uuid or str(uuid4()),
        'source_node_uuid': source_uuid,
        'target_node_uuid': target_uuid,
        'group_id': 'test-group',
        'created_at': datetime.now(),
        'fact': kwargs.get('fact', 'test relationship'),
        'name': kwargs.get('name', 'test_edge')
    }
    edge.update(kwargs)
    return edge


async def test_entity_existence_check():
    """Test entity existence verification."""
    print("Testing entity existence check...")
    
    driver = create_mock_driver()
    validator = PostSaveValidator(driver)
    
    # Test valid entity
    entity = create_test_entity("Test Entity")
    results = await validator.validate_entity_post_save(entity)
    
    existence_results = [r for r in results if r.check_name == "entity_exists"]
    assert len(existence_results) == 1, "Should have one existence check result"
    assert existence_results[0].passed, f"Entity existence check should pass: {existence_results[0].message}"
    print("✅ Entity existence check passed")
    
    # Test entity without UUID
    entity_no_uuid = create_test_entity("No UUID Entity")
    del entity_no_uuid['uuid']
    results = await validator.validate_entity_post_save(entity_no_uuid)
    
    existence_results = [r for r in results if r.check_name == "entity_exists"]
    assert len(existence_results) == 1, "Should have one existence check result"
    assert not existence_results[0].passed, "Entity without UUID should fail existence check"
    print("✅ Entity without UUID correctly fails existence check")


async def test_edge_reference_check():
    """Test edge node reference validation."""
    print("Testing edge node reference check...")
    
    driver = create_mock_driver()
    validator = PostSaveValidator(driver)
    
    # Test valid edge
    source_uuid = str(uuid4())
    target_uuid = str(uuid4())
    edge = create_test_edge(source_uuid, target_uuid)
    
    results = await validator.validate_edge_post_save(edge)
    reference_results = [r for r in results if r.check_name == "edge_node_references"]
    
    assert len(reference_results) == 1, "Should have one reference check result"
    assert reference_results[0].passed, f"Edge reference check should pass: {reference_results[0].message}"
    print("✅ Valid edge reference check passed")
    
    # Test edge with missing source UUID
    edge_missing_source = create_test_edge("", target_uuid)
    results = await validator.validate_edge_post_save(edge_missing_source)
    
    reference_results = [r for r in results if r.check_name == "edge_node_references"]
    assert len(reference_results) == 1, "Should have one reference check result"
    assert not reference_results[0].passed, "Edge with missing source should fail reference check"
    print("✅ Edge with missing source UUID correctly fails reference check")


async def test_uuid_uniqueness_check():
    """Test UUID uniqueness validation."""
    print("Testing UUID uniqueness check...")
    
    driver = create_mock_driver()
    validator = PostSaveValidator(driver)
    
    entity = create_test_entity("Test Entity")
    results = await validator.validate_entity_post_save(entity)
    
    uniqueness_results = [r for r in results if r.check_name == "uuid_uniqueness"]
    assert len(uniqueness_results) == 1, "Should have one uniqueness check result"
    assert uniqueness_results[0].passed, f"UUID uniqueness check should pass: {uniqueness_results[0].message}"
    print("✅ UUID uniqueness check passed")


async def test_centrality_bounds_check():
    """Test centrality value bounds validation."""
    print("Testing centrality bounds check...")
    
    driver = create_mock_driver()
    validator = PostSaveValidator(driver)
    
    # Test valid centrality values
    entity = create_test_entity("Test Entity", 
                               degree_centrality=0.5,
                               pagerank_centrality=0.3,
                               betweenness_centrality=0.1,
                               eigenvector_centrality=0.8)
    
    results = await validator.validate_entity_post_save(entity)
    centrality_results = [r for r in results if r.check_name == "centrality_bounds"]
    
    assert len(centrality_results) == 1, "Should have one centrality check result"
    assert centrality_results[0].passed, f"Valid centrality values should pass: {centrality_results[0].message}"
    print("✅ Valid centrality bounds check passed")
    
    # Test invalid centrality values
    entity_invalid = create_test_entity("Invalid Centrality Entity",
                                       degree_centrality=1.5,  # Invalid: > 1
                                       pagerank_centrality=-0.1)  # Invalid: < 0
    
    results = await validator.validate_entity_post_save(entity_invalid)
    centrality_results = [r for r in results if r.check_name == "centrality_bounds"]
    
    assert len(centrality_results) == 1, "Should have one centrality check result"
    assert not centrality_results[0].passed, "Invalid centrality values should fail check"
    print("✅ Invalid centrality bounds correctly fail check")


async def test_required_fields_check():
    """Test required fields validation."""
    print("Testing required fields check...")
    
    driver = create_mock_driver()
    validator = PostSaveValidator(driver)
    
    # Test complete entity
    entity = create_test_entity("Complete Entity")
    results = await validator.validate_entity_post_save(entity)
    
    required_results = [r for r in results if r.check_name == "required_fields"]
    assert len(required_results) == 1, "Should have one required fields check result"
    assert required_results[0].passed, f"Complete entity should pass required fields check: {required_results[0].message}"
    print("✅ Complete entity passes required fields check")
    
    # Test entity missing required field
    entity_incomplete = create_test_entity("Incomplete Entity")
    del entity_incomplete['name']  # Remove required field
    
    results = await validator.validate_entity_post_save(entity_incomplete)
    required_results = [r for r in results if r.check_name == "required_fields"]
    
    assert len(required_results) == 1, "Should have one required fields check result"
    assert not required_results[0].passed, "Entity missing required field should fail check"
    print("✅ Incomplete entity correctly fails required fields check")


async def test_embedding_consistency_check():
    """Test embedding consistency validation."""
    print("Testing embedding consistency check...")
    
    driver = create_mock_driver()
    validator = PostSaveValidator(driver)
    
    # Test entity with consistent embeddings
    entity = create_test_entity("Test Entity", 
                               name_embedding=[0.1, 0.2, 0.3, 0.4])
    
    results = await validator.validate_entity_post_save(entity)
    embedding_results = [r for r in results if r.check_name == "embedding_consistency"]
    
    assert len(embedding_results) == 1, "Should have one embedding consistency check result"
    assert embedding_results[0].passed, f"Consistent embeddings should pass: {embedding_results[0].message}"
    print("✅ Consistent embeddings check passed")
    
    # Test entity with missing embedding
    entity_no_embedding = create_test_entity("No Embedding Entity")
    # Name present but no name_embedding
    
    results = await validator.validate_entity_post_save(entity_no_embedding)
    embedding_results = [r for r in results if r.check_name == "embedding_consistency"]
    
    assert len(embedding_results) == 1, "Should have one embedding consistency check result"
    # This should be a warning, not a failure
    assert embedding_results[0].severity == "WARNING", "Missing embedding should be a warning"
    print("✅ Missing embedding correctly generates warning")


async def test_temporal_consistency_check():
    """Test temporal consistency validation."""
    print("Testing temporal consistency check...")
    
    driver = create_mock_driver()
    validator = PostSaveValidator(driver)
    
    # Test entity with consistent timestamps
    base_time = datetime.now() - timedelta(hours=1)
    entity = create_test_entity("Test Entity",
                               created_at=base_time,
                               updated_at=base_time + timedelta(minutes=30))
    
    results = await validator.validate_entity_post_save(entity)
    temporal_results = [r for r in results if r.check_name == "temporal_consistency"]
    
    assert len(temporal_results) == 1, "Should have one temporal consistency check result"
    assert temporal_results[0].passed, f"Consistent timestamps should pass: {temporal_results[0].message}"
    print("✅ Consistent temporal check passed")
    
    # Test entity with inconsistent timestamps
    entity_inconsistent = create_test_entity("Inconsistent Entity",
                                           created_at=datetime.now(),
                                           updated_at=datetime.now() - timedelta(hours=1))  # Updated before created
    
    results = await validator.validate_entity_post_save(entity_inconsistent)
    temporal_results = [r for r in results if r.check_name == "temporal_consistency"]
    
    assert len(temporal_results) == 1, "Should have one temporal consistency check result"
    # This should be a warning for temporal inconsistency
    assert temporal_results[0].severity == "WARNING", "Temporal inconsistency should be a warning"
    print("✅ Inconsistent timestamps correctly generate warning")


async def test_batch_validation():
    """Test batch post-save validation."""
    print("Testing batch validation...")
    
    driver = create_mock_driver()
    validator = PostSaveValidator(driver)
    
    # Create test batch with mixed entities and edges
    entities = [
        create_test_entity("Entity 1"),
        create_test_entity("Entity 2"),
    ]
    
    source_uuid = entities[0]['uuid']
    target_uuid = entities[1]['uuid']
    edge = create_test_edge(source_uuid, target_uuid)
    
    batch = entities + [edge]
    
    results = await validator.validate_batch_post_save(batch)
    
    # Should have results for all entities and edges, plus batch consistency
    print(f"Batch validation produced {len(results)} check results")
    
    # Check for batch consistency result
    batch_results = [r for r in results if r.check_name == "batch_consistency"]
    assert len(batch_results) == 1, "Should have one batch consistency check result"
    assert batch_results[0].passed, f"Batch consistency should pass: {batch_results[0].message}"
    print("✅ Batch validation passed")
    
    # Test batch with duplicate UUIDs
    duplicate_uuid = str(uuid4())
    duplicate_batch = [
        create_test_entity("Entity 1", uuid=duplicate_uuid),
        create_test_entity("Entity 2", uuid=duplicate_uuid),  # Same UUID
    ]
    
    results = await validator.validate_batch_post_save(duplicate_batch)
    batch_results = [r for r in results if r.check_name == "batch_consistency"]
    
    assert len(batch_results) == 1, "Should have one batch consistency check result"
    assert not batch_results[0].passed, "Batch with duplicate UUIDs should fail consistency check"
    print("✅ Batch with duplicates correctly fails consistency check")


async def test_configuration():
    """Test post-save validation configuration."""
    print("Testing configuration...")
    
    # Test default configuration
    config = get_post_save_config()
    assert 'enabled' in config, "Config should have 'enabled' setting"
    assert 'auto_repair' in config, "Config should have 'auto_repair' setting"
    print(f"Default config: {config}")
    print("✅ Configuration loaded successfully")
    
    # Test environment variable override
    os.environ['POST_SAVE_VALIDATION_ENABLED'] = 'false'
    os.environ['POST_SAVE_AUTO_REPAIR'] = 'true'
    
    config = get_post_save_config()
    assert not config['enabled'], "Environment variable should disable validation"
    assert config['auto_repair'], "Environment variable should enable auto repair"
    print("✅ Environment variable configuration works")
    
    # Clean up environment
    os.environ.pop('POST_SAVE_VALIDATION_ENABLED', None)
    os.environ.pop('POST_SAVE_AUTO_REPAIR', None)


async def test_integration_with_run_post_save_checks():
    """Test integration function."""
    print("Testing integration function...")
    
    driver = create_mock_driver()
    entities = [create_test_entity("Integration Test Entity")]
    
    # Test with validation enabled
    os.environ['POST_SAVE_VALIDATION_ENABLED'] = 'true'
    results = await run_post_save_checks(driver, entities)
    
    assert len(results) > 0, "Should have validation results when enabled"
    print(f"Integration function returned {len(results)} results")
    print("✅ Integration function works when enabled")
    
    # Test with validation disabled
    os.environ['POST_SAVE_VALIDATION_ENABLED'] = 'false'
    results = await run_post_save_checks(driver, entities)
    
    assert len(results) == 0, "Should have no results when disabled"
    print("✅ Integration function respects disabled setting")
    
    # Clean up environment
    os.environ.pop('POST_SAVE_VALIDATION_ENABLED', None)


async def test_custom_integrity_check():
    """Test registering custom integrity checks."""
    print("Testing custom integrity check registration...")
    
    driver = create_mock_driver()
    validator = PostSaveValidator(driver)
    
    # Register custom check
    async def custom_check(entity, context):
        name = entity.get('name', '') if isinstance(entity, dict) else getattr(entity, 'name', '')
        if 'forbidden' in name.lower():
            return IntegrityCheckResult.failure(
                "custom_forbidden_name",
                f"Entity name contains forbidden word: {name}",
                entity.get('uuid') if isinstance(entity, dict) else getattr(entity, 'uuid', None)
            )
        return IntegrityCheckResult.success("custom_forbidden_name", "Name is allowed")
    
    validator.register_integrity_check("custom_forbidden_name", custom_check)
    
    # Test with allowed name
    entity_allowed = create_test_entity("Allowed Entity")
    results = await validator.validate_entity_post_save(entity_allowed)
    
    custom_results = [r for r in results if r.check_name == "custom_forbidden_name"]
    assert len(custom_results) == 1, "Should have custom check result"
    assert custom_results[0].passed, "Allowed name should pass custom check"
    print("✅ Custom check passes for allowed name")
    
    # Test with forbidden name
    entity_forbidden = create_test_entity("Forbidden Entity")
    results = await validator.validate_entity_post_save(entity_forbidden)
    
    custom_results = [r for r in results if r.check_name == "custom_forbidden_name"]
    assert len(custom_results) == 1, "Should have custom check result"
    assert not custom_results[0].passed, "Forbidden name should fail custom check"
    print("✅ Custom check correctly fails for forbidden name")


async def run_all_tests():
    """Run all post-save validation tests."""
    print("=" * 60)
    print("TESTING POST-SAVE INTEGRITY CHECKS SYSTEM")
    print("=" * 60)
    
    try:
        await test_entity_existence_check()
        await test_edge_reference_check()
        await test_uuid_uniqueness_check()
        await test_centrality_bounds_check()
        await test_required_fields_check()
        await test_embedding_consistency_check()
        await test_temporal_consistency_check()
        await test_batch_validation()
        await test_configuration()
        await test_integration_with_run_post_save_checks()
        await test_custom_integrity_check()
        
        print("=" * 60)
        print("✅ ALL POST-SAVE VALIDATION TESTS PASSED!")
        print("The post-save integrity checks system is working correctly.")
        print("=" * 60)
        return True
        
    except Exception as e:
        print(f"❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    exit(0 if success else 1)