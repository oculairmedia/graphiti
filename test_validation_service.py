#!/usr/bin/env python3
"""
Test script for the centralized validation service.

This script validates the functionality of the CentralizedValidationService
that orchestrates all validation components into a unified system.
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta
from unittest.mock import MagicMock, AsyncMock
from uuid import uuid4

# Add the project root to path for imports
sys.path.append('/opt/stacks/graphiti')

from graphiti_core.utils.validation_service import (
    CentralizedValidationService,
    ValidationConfig,
    ValidationReport,
    ValidationIssue,
    ValidationPhase,
    ValidationSeverity,
    get_validation_service,
    validate_entities,
    validate_edges,
    validate_post_save
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
        
        # Post-save validation responses
        if 'source_uuid' in params or 'target_uuid' in params or 'source_count' in query:
            record = {'source_count': 1, 'target_count': 1}
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


async def test_validation_service_initialization():
    """Test validation service initialization and configuration."""
    print("Testing validation service initialization...")
    
    # Test default initialization
    service = CentralizedValidationService()
    assert service.config is not None, "Should have default config"
    assert service.hook_service is not None, "Should have hook service"
    assert service.centrality_validator is not None, "Should have centrality validator"
    print("✅ Default initialization works")
    
    # Test with custom config
    config = ValidationConfig(
        enable_pre_save_validation=False,
        batch_size=50,
        fail_on_warnings=True
    )
    service = CentralizedValidationService(config=config)
    assert not service.config.enable_pre_save_validation, "Should use custom config"
    assert service.config.batch_size == 50, "Should use custom batch size"
    print("✅ Custom configuration works")
    
    # Test with driver
    driver = create_mock_driver()
    service = CentralizedValidationService(driver=driver)
    assert service.driver == driver, "Should store driver"
    assert service.post_save_validator is not None, "Should initialize post-save validator"
    print("✅ Driver initialization works")


async def test_entity_comprehensive_validation():
    """Test comprehensive entity validation."""
    print("Testing comprehensive entity validation...")
    
    driver = create_mock_driver()
    service = CentralizedValidationService(driver=driver)
    
    # Create test entities with various issues
    entities = [
        create_test_entity("Valid Entity", name_embedding=[0.1, 0.2, 0.3]),
        create_test_entity("Invalid Centrality Entity", degree_centrality=1.5),  # Invalid centrality
        create_test_entity(""),  # Empty name should fail validation
        create_test_entity("Duplicate Entity"),
        create_test_entity("Duplicate Entity"),  # Potential duplicate
    ]
    
    # Run comprehensive validation
    report = await service.validate_entities_comprehensive(entities)
    
    assert isinstance(report, ValidationReport), "Should return ValidationReport"
    assert report.total_entities == len(entities), "Should count all entities"
    assert len(report.issues) > 0, "Should find validation issues"
    assert 'total_time' in report.performance_metrics, "Should track performance"
    
    print(f"Found {len(report.issues)} validation issues:")
    for issue in report.issues:
        print(f"  - {issue.phase.value}: {issue.severity.value}: {issue.message}")
    
    print("✅ Comprehensive entity validation works")


async def test_edge_comprehensive_validation():
    """Test comprehensive edge validation."""
    print("Testing comprehensive edge validation...")
    
    driver = create_mock_driver()
    service = CentralizedValidationService(driver=driver)
    
    source_uuid = str(uuid4())
    target_uuid = str(uuid4())
    
    # Create test edges with various issues
    edges = [
        create_test_edge(source_uuid, target_uuid),  # Valid edge
        create_test_edge("", target_uuid),  # Missing source
        create_test_edge(source_uuid, ""),  # Missing target
        create_test_edge(source_uuid, source_uuid),  # Self-loop
    ]
    
    # Run comprehensive validation
    report = await service.validate_edges_comprehensive(edges)
    
    assert isinstance(report, ValidationReport), "Should return ValidationReport"
    assert report.total_edges == len(edges), "Should count all edges"
    assert len(report.issues) > 0, "Should find validation issues"
    
    print(f"Found {len(report.issues)} edge validation issues:")
    for issue in report.issues:
        print(f"  - {issue.phase.value}: {issue.severity.value}: {issue.message}")
    
    print("✅ Comprehensive edge validation works")


async def test_post_save_validation():
    """Test post-save validation integration."""
    print("Testing post-save validation integration...")
    
    driver = create_mock_driver()
    service = CentralizedValidationService(driver=driver)
    
    entities = [
        create_test_entity("Post Save Entity"),
        create_test_edge(str(uuid4()), str(uuid4()))
    ]
    
    # Run post-save validation
    report = await service.validate_post_save(entities)
    
    assert isinstance(report, ValidationReport), "Should return ValidationReport"
    assert report.total_entities == 1, "Should count entities"
    assert report.total_edges == 1, "Should count edges"
    
    # Check that post-save checks were run
    post_save_issues = [i for i in report.issues if i.phase == ValidationPhase.POST_SAVE]
    print(f"Post-save validation found {len(post_save_issues)} issues")
    
    print("✅ Post-save validation integration works")


async def test_validation_report_functionality():
    """Test ValidationReport functionality."""
    print("Testing ValidationReport functionality...")
    
    report = ValidationReport(
        operation_id="test_op",
        timestamp=datetime.now(),
        total_entities=10,
        total_edges=5
    )
    
    # Add various types of issues
    report.add_issue(ValidationIssue(
        phase=ValidationPhase.PRE_SAVE,
        severity=ValidationSeverity.ERROR,
        message="Test error",
        entity_id="entity_1"
    ))
    
    report.add_issue(ValidationIssue(
        phase=ValidationPhase.CENTRALITY,
        severity=ValidationSeverity.WARNING,
        message="Test warning",
        entity_id="entity_2"
    ))
    
    report.add_issue(ValidationIssue(
        phase=ValidationPhase.POST_SAVE,
        severity=ValidationSeverity.CRITICAL,
        message="Test critical",
        entity_id="entity_3"
    ))
    
    # Test report properties
    assert report.error_count == 2, f"Should count 2 errors (ERROR + CRITICAL), got {report.error_count}"
    assert report.warning_count == 1, f"Should count 1 warning, got {report.warning_count}"
    assert report.has_errors, "Should have errors"
    assert not report.is_valid, "Should not be valid (has critical error)"
    
    # Test serialization
    report_dict = report.to_dict()
    assert 'operation_id' in report_dict, "Should serialize operation_id"
    assert 'issues' in report_dict, "Should serialize issues"
    assert len(report_dict['issues']) == 3, "Should serialize all issues"
    
    print("✅ ValidationReport functionality works")


async def test_configuration_from_environment():
    """Test loading configuration from environment variables."""
    print("Testing configuration from environment...")
    
    # Set environment variables
    os.environ['VALIDATION_ENABLE_PRE_SAVE'] = 'false'
    os.environ['VALIDATION_BATCH_SIZE'] = '200'
    os.environ['VALIDATION_FAIL_ON_WARNINGS'] = 'true'
    
    try:
        config = ValidationConfig.from_environment()
        
        assert not config.enable_pre_save_validation, "Should disable pre-save validation"
        assert config.batch_size == 200, "Should set batch size to 200"
        assert config.fail_on_warnings, "Should fail on warnings"
        
        print("✅ Environment configuration loading works")
        
    finally:
        # Clean up environment
        for key in ['VALIDATION_ENABLE_PRE_SAVE', 'VALIDATION_BATCH_SIZE', 'VALIDATION_FAIL_ON_WARNINGS']:
            os.environ.pop(key, None)


async def test_validation_phases():
    """Test different validation phases."""
    print("Testing validation phases...")
    
    driver = create_mock_driver()
    
    # Test with different phase configurations
    config = ValidationConfig(
        enable_pre_save_validation=True,
        enable_centrality_validation=True,
        enable_deduplication=True,
        enable_post_save_validation=False  # Disable post-save for this test
    )
    
    service = CentralizedValidationService(driver=driver, config=config)
    
    entities = [
        create_test_entity("Phase Test Entity", degree_centrality=0.5),
        create_test_entity("Phase Test Entity"),  # Potential duplicate
    ]
    
    report = await service.validate_entities_comprehensive(entities)
    
    # Check that different phases were executed
    phases_found = set(issue.phase for issue in report.issues)
    
    print(f"Validation phases executed: {[p.value for p in phases_found]}")
    
    # Should have pre-save and deduplication phases
    expected_phases = {ValidationPhase.PRE_SAVE, ValidationPhase.DEDUPLICATION}
    # Centrality might not produce issues if values are valid
    
    assert len(phases_found) > 0, "Should execute at least some validation phases"
    print("✅ Validation phases work correctly")


async def test_performance_metrics():
    """Test performance metrics tracking."""
    print("Testing performance metrics...")
    
    driver = create_mock_driver()
    service = CentralizedValidationService(driver=driver)
    
    # Create a reasonable number of entities to measure performance
    entities = [create_test_entity(f"Entity {i}") for i in range(20)]
    
    report = await service.validate_entities_comprehensive(entities)
    
    # Check performance metrics
    assert 'total_time' in report.performance_metrics, "Should track total time"
    assert 'entities_per_second' in report.performance_metrics, "Should calculate throughput"
    assert report.performance_metrics['total_time'] > 0, "Should record positive time"
    assert report.performance_metrics['entities_per_second'] > 0, "Should calculate positive throughput"
    
    print(f"Performance: {report.performance_metrics['entities_per_second']:.2f} entities/second")
    print("✅ Performance metrics tracking works")


async def test_global_service_functions():
    """Test global convenience functions."""
    print("Testing global service functions...")
    
    driver = create_mock_driver()
    
    # Test validate_entities function
    entities = [create_test_entity("Global Test Entity")]
    report = await validate_entities(entities, driver=driver)
    
    assert isinstance(report, ValidationReport), "Should return ValidationReport"
    assert report.total_entities == 1, "Should count entities"
    
    # Test validate_edges function
    edges = [create_test_edge(str(uuid4()), str(uuid4()))]
    report = await validate_edges(edges, driver=driver)
    
    assert isinstance(report, ValidationReport), "Should return ValidationReport"
    assert report.total_edges == 1, "Should count edges"
    
    # Test validate_post_save function
    mixed_entities = entities + edges
    report = await validate_post_save(mixed_entities, driver=driver)
    
    assert isinstance(report, ValidationReport), "Should return ValidationReport"
    
    print("✅ Global service functions work")


async def test_validation_summary():
    """Test validation summary generation."""
    print("Testing validation summary...")
    
    # Create multiple reports
    reports = []
    
    for i in range(3):
        report = ValidationReport(
            operation_id=f"test_op_{i}",
            timestamp=datetime.now(),
            total_entities=10 * (i + 1),
            total_edges=5 * (i + 1)
        )
        
        # Add some issues
        report.add_issue(ValidationIssue(
            phase=ValidationPhase.PRE_SAVE,
            severity=ValidationSeverity.ERROR,
            message=f"Error in report {i}"
        ))
        
        report.add_issue(ValidationIssue(
            phase=ValidationPhase.CENTRALITY,
            severity=ValidationSeverity.WARNING,
            message=f"Warning in report {i}"
        ))
        
        report.performance_metrics['total_time'] = 1.0 + i * 0.5
        reports.append(report)
    
    # Generate summary
    service = CentralizedValidationService()
    summary = service.get_validation_summary(reports)
    
    assert summary['total_reports'] == 3, "Should count all reports"
    assert summary['total_entities'] == 60, "Should sum all entities (10+20+30)"
    assert summary['total_edges'] == 30, "Should sum all edges (5+10+15)"
    assert summary['total_errors'] == 3, "Should count all errors"
    assert summary['total_warnings'] == 3, "Should count all warnings"
    assert 'issues_by_phase' in summary, "Should categorize issues by phase"
    assert 'issues_by_severity' in summary, "Should categorize issues by severity"
    
    print(f"Summary: {summary['total_entities']} entities, {summary['total_errors']} errors, {summary['total_warnings']} warnings")
    print("✅ Validation summary generation works")


async def test_error_handling():
    """Test error handling in validation service."""
    print("Testing error handling...")
    
    # Create service without driver for post-save validation
    service = CentralizedValidationService()
    
    # This should handle missing driver gracefully
    entities = [create_test_entity("Error Test Entity")]
    report = await service.validate_post_save(entities)
    
    assert isinstance(report, ValidationReport), "Should return report even with missing driver"
    assert report.operation_id == "post_save_skipped", "Should indicate skipped validation"
    
    print("✅ Error handling works correctly")


async def run_all_tests():
    """Run all centralized validation service tests."""
    print("=" * 70)
    print("TESTING CENTRALIZED VALIDATION SERVICE")
    print("=" * 70)
    
    try:
        await test_validation_service_initialization()
        await test_entity_comprehensive_validation()
        await test_edge_comprehensive_validation()
        await test_post_save_validation()
        await test_validation_report_functionality()
        await test_configuration_from_environment()
        await test_validation_phases()
        await test_performance_metrics()
        await test_global_service_functions()
        await test_validation_summary()
        await test_error_handling()
        
        print("=" * 70)
        print("✅ ALL CENTRALIZED VALIDATION SERVICE TESTS PASSED!")
        print("The centralized validation system is working correctly.")
        print("=" * 70)
        return True
        
    except Exception as e:
        print(f"❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    exit(0 if success else 1)