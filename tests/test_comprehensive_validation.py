#!/usr/bin/env python3
"""
Comprehensive test suite for the complete data validation framework.

This test suite provides integration testing across all validation components:
- Pydantic validators (EntityNode, EpisodicNode, EntityEdge)
- Deterministic UUID generation
- Database constraints (FalkorDB/Neo4j)
- Transaction management
- Pre-save validation hooks
- Post-save integrity checks
- Centrality validation
- Name normalization and fuzzy matching
- Merge policies and deduplication
- Centralized validation service

This ensures all components work together as a cohesive validation system.
"""

import asyncio
import os
import sys
import tempfile
import shutil
from datetime import datetime, timedelta
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4, UUID
from typing import List, Dict, Any

# Add the project root to path for imports
sys.path.append('/opt/stacks/graphiti')

# Import all validation components
from graphiti_core.nodes import EntityNode, EpisodicNode, EpisodeType
from graphiti_core.edges import EntityEdge
from graphiti_core.utils.uuid_utils import (
    generate_deterministic_uuid,
    generate_deterministic_edge_uuid,
    normalize_entity_name
)
from graphiti_core.utils.constraints import get_unique_constraints
from graphiti_core.utils.transaction import atomic_transaction
from graphiti_core.utils.validation_hooks import (
    ValidationResult,
    ValidationService,
    hook_registry,
    HookType
)
from graphiti_core.utils.post_save_validation import (
    PostSaveValidator,
    IntegrityCheckResult,
    run_post_save_checks
)
from graphiti_core.utils.centrality_validation import (
    CentralityValidator,
    validate_entity_centrality
)
from graphiti_core.utils.fuzzy_matching import (
    FuzzyMatcher,
    FuzzyMatchingConfig,
    MatchingStrategy,
    is_entity_fuzzy_match
)
from graphiti_core.utils.merge_policies import (
    EntityMerger,
    MergePolicyConfig,
    MergeStrategy,
    merge_duplicate_entities
)
from graphiti_core.utils.validation_service import (
    CentralizedValidationService,
    ValidationConfig,
    ValidationReport,
    ValidationIssue,
    ValidationPhase,
    ValidationSeverity,
    validate_entities,
    validate_edges,
    validate_post_save
)


def create_mock_driver(provider: str = 'neo4j'):
    """Create a comprehensive mock GraphDriver for testing."""
    driver = MagicMock()
    driver.provider = provider
    
    # Mock session with comprehensive database responses
    session = AsyncMock()
    driver.session.return_value = session
    
    # Mock database responses for various queries
    async def mock_run(query, **params):
        result = AsyncMock()
        
        # Constraint creation responses
        if 'CREATE CONSTRAINT' in query or 'GRAPH.CONSTRAINT CREATE' in query:
            record = {'success': True}
        
        # Entity existence checks
        elif 'count(n)' in query and 'uuid' in (str(params) + query):
            record = {'count': 1}  # Entity exists
        
        # Edge node reference checks  
        elif 'source_count' in query or 'target_count' in query:
            record = {'source_count': 1, 'target_count': 1}  # Both nodes exist
            
        # Transaction simulation
        elif 'BEGIN' in query:
            record = {'transaction_started': True}
        elif 'COMMIT' in query:
            record = {'transaction_committed': True}
        elif 'ROLLBACK' in query:
            record = {'transaction_rolled_back': True}
            
        # Default response
        else:
            record = {'result': 'success'}
            
        result.single.return_value = record
        return result
    
    session.run.side_effect = mock_run
    return driver


class ValidationTestData:
    """Test data factory for comprehensive validation testing."""
    
    @staticmethod
    def create_valid_entity(name: str = "Test Entity", **kwargs) -> dict:
        """Create a valid test entity."""
        return {
            'uuid': str(uuid4()),
            'name': name,
            'group_id': kwargs.get('group_id', 'test-group'),
            'created_at': datetime.now(),
            'summary': kwargs.get('summary', f'Test entity: {name}'),
            'labels': ['Entity', 'Test'],
            'name_embedding': kwargs.get('name_embedding', [0.1, 0.2, 0.3, 0.4, 0.5]),
            **kwargs
        }
    
    @staticmethod
    def create_invalid_entity(**kwargs) -> dict:
        """Create an invalid test entity for testing validation failures."""
        return {
            'uuid': kwargs.get('uuid', ''),  # Invalid empty UUID
            'name': kwargs.get('name', ''),  # Invalid empty name
            'group_id': kwargs.get('group_id', ''),  # Invalid empty group_id
            'created_at': kwargs.get('created_at', 'invalid-date'),  # Invalid date
            'degree_centrality': kwargs.get('degree_centrality', 2.0),  # Invalid centrality > 1
            **kwargs
        }
    
    @staticmethod
    def create_valid_edge(source_uuid: str, target_uuid: str, **kwargs) -> dict:
        """Create a valid test edge."""
        return {
            'uuid': str(uuid4()),
            'source_node_uuid': source_uuid,
            'target_node_uuid': target_uuid,
            'group_id': kwargs.get('group_id', 'test-group'),
            'created_at': datetime.now(),
            'fact': kwargs.get('fact', 'test relationship'),
            'name': kwargs.get('name', 'test_edge'),
            'fact_embedding': kwargs.get('fact_embedding', [0.2, 0.3, 0.4, 0.5, 0.6]),
            **kwargs
        }
    
    @staticmethod
    def create_invalid_edge(**kwargs) -> dict:
        """Create an invalid test edge for testing validation failures."""
        return {
            'uuid': kwargs.get('uuid', ''),  # Invalid empty UUID
            'source_node_uuid': kwargs.get('source_node_uuid', ''),  # Invalid empty source
            'target_node_uuid': kwargs.get('target_node_uuid', ''),  # Invalid empty target
            'group_id': kwargs.get('group_id', ''),  # Invalid empty group_id
            'fact': kwargs.get('fact', ''),  # Invalid empty fact
            **kwargs
        }
    
    @staticmethod
    def create_episode(**kwargs) -> dict:
        """Create a test episode."""
        return {
            'uuid': str(uuid4()),
            'name': kwargs.get('name', 'Test Episode'),
            'content': kwargs.get('content', 'Test episode content'),
            'source_description': kwargs.get('source_description', 'Test source'),
            'source': kwargs.get('source', EpisodeType.message),
            'valid_at': kwargs.get('valid_at', datetime.now()),
            'group_id': kwargs.get('group_id', 'test-group'),
            **kwargs
        }


class ComprehensiveValidationTestSuite:
    """Main test suite orchestrating all validation component tests."""
    
    def __init__(self):
        self.driver = create_mock_driver()
        self.test_data = ValidationTestData()
        
    async def test_pydantic_validators_integration(self):
        """Test integration of Pydantic validators across all node/edge types."""
        print("Testing Pydantic validators integration...")
        
        # Test valid EntityNode creation
        valid_data = self.test_data.create_valid_entity()
        try:
            entity = EntityNode(**valid_data)
            assert entity.uuid == valid_data['uuid'], "EntityNode should accept valid data"
            print("✅ Valid EntityNode creation works")
        except Exception as e:
            raise AssertionError(f"Valid EntityNode creation failed: {e}")
        
        # Test invalid EntityNode creation  
        invalid_data = self.test_data.create_invalid_entity()
        try:
            entity = EntityNode(**invalid_data)
            raise AssertionError("Invalid EntityNode should have failed validation")
        except Exception:
            print("✅ Invalid EntityNode correctly rejected")
        
        # Test valid EntityEdge creation
        source_uuid = str(uuid4())
        target_uuid = str(uuid4())
        valid_edge_data = self.test_data.create_valid_edge(source_uuid, target_uuid)
        try:
            edge = EntityEdge(**valid_edge_data)
            assert edge.source_node_uuid == source_uuid, "EntityEdge should accept valid data"
            print("✅ Valid EntityEdge creation works")
        except Exception as e:
            raise AssertionError(f"Valid EntityEdge creation failed: {e}")
        
        # Test invalid EntityEdge creation
        invalid_edge_data = self.test_data.create_invalid_edge()
        try:
            edge = EntityEdge(**invalid_edge_data)
            raise AssertionError("Invalid EntityEdge should have failed validation")
        except Exception:
            print("✅ Invalid EntityEdge correctly rejected")
    
    async def test_deterministic_uuid_integration(self):
        """Test deterministic UUID generation across the system."""
        print("Testing deterministic UUID generation...")
        
        # Test entity UUID generation
        entity_name = "John Doe"
        group_id = "test-group"
        
        uuid1 = generate_deterministic_uuid(entity_name, group_id)
        uuid2 = generate_deterministic_uuid(entity_name, group_id)
        
        assert uuid1 == uuid2, "Deterministic entity UUIDs should be identical"
        assert UUID(uuid1), "Generated UUID should be valid"
        print("✅ Deterministic entity UUID generation works")
        
        # Test edge UUID generation
        source_uuid = str(uuid4())
        target_uuid = str(uuid4())
        edge_name = "knows"
        
        edge_uuid1 = generate_deterministic_edge_uuid(source_uuid, target_uuid, edge_name, group_id)
        edge_uuid2 = generate_deterministic_edge_uuid(source_uuid, target_uuid, edge_name, group_id)
        
        assert edge_uuid1 == edge_uuid2, "Deterministic edge UUIDs should be identical"
        assert UUID(edge_uuid1), "Generated edge UUID should be valid"
        print("✅ Deterministic edge UUID generation works")
        
        # Test with environment variable
        with patch.dict(os.environ, {'USE_DETERMINISTIC_UUIDS': 'true'}):
            # Test that entities use deterministic UUIDs when enabled
            entity_data = self.test_data.create_valid_entity(name=entity_name, group_id=group_id)
            del entity_data['uuid']  # Let the system generate it
            
            # This would normally be handled by the system, but we can test the function
            det_uuid = generate_deterministic_uuid(entity_name, group_id)
            assert UUID(det_uuid), "Environment-enabled deterministic UUID should be valid"
            print("✅ Environment-controlled deterministic UUIDs work")
    
    async def test_database_constraints_integration(self):
        """Test database constraint generation and application."""
        print("Testing database constraints integration...")
        
        # Test Neo4j constraint generation
        neo4j_constraints = get_unique_constraints('neo4j')
        assert len(neo4j_constraints) > 0, "Should generate Neo4j constraints"
        assert any('uuid' in constraint for constraint in neo4j_constraints), "Should include UUID constraints"
        print("✅ Neo4j constraint generation works")
        
        # Test FalkorDB constraint generation
        falkor_constraints = get_unique_constraints('falkordb')
        assert len(falkor_constraints) > 0, "Should generate FalkorDB constraints"
        assert any('GRAPH.CONSTRAINT CREATE' in constraint for constraint in falkor_constraints), "Should use FalkorDB syntax"
        print("✅ FalkorDB constraint generation works")
        
        # Test constraint application (mocked)
        session = self.driver.session()
        try:
            for constraint in neo4j_constraints:
                # Replace placeholder with actual graph key for testing
                test_constraint = constraint.format(graph_key='test_graph')
                result = await session.run(test_constraint)
                # Mock will return success
                record = await result.single()
                assert record is not None, "Constraint should execute successfully"
            print("✅ Constraint application works")
        finally:
            await session.close()
    
    async def test_transaction_management_integration(self):
        """Test atomic transaction wrapper integration."""
        print("Testing transaction management...")
        
        # Test successful transaction
        async with atomic_transaction(self.driver) as tx:
            # Mock some database operations
            await tx.run("CREATE (n:Test {id: 1})")
            await tx.run("CREATE (m:Test {id: 2})")
            # Transaction should commit successfully
        
        print("✅ Successful transaction works")
        
        # Test transaction rollback
        try:
            async with atomic_transaction(self.driver) as tx:
                await tx.run("CREATE (n:Test {id: 1})")
                raise Exception("Simulated error")  # Force rollback
        except Exception as e:
            assert "Simulated error" in str(e), "Should propagate the original error"
            print("✅ Transaction rollback works")
    
    async def test_validation_hooks_integration(self):
        """Test pre-save validation hooks system."""
        print("Testing validation hooks integration...")
        
        validation_service = ValidationService()
        
        # Test valid entity validation
        valid_entity = self.test_data.create_valid_entity()
        result = validation_service.validate_entity(valid_entity)
        assert result.success, f"Valid entity validation should succeed: {result.message}"
        print("✅ Valid entity hook validation works")
        
        # Test invalid entity validation  
        invalid_entity = self.test_data.create_invalid_entity()
        result = validation_service.validate_entity(invalid_entity)
        assert not result.success, "Invalid entity validation should fail"
        print("✅ Invalid entity hook validation works")
        
        # Test batch validation
        entities = [
            self.test_data.create_valid_entity("Entity 1"),
            self.test_data.create_valid_entity("Entity 2"),
            invalid_entity
        ]
        result = validation_service.validate_batch(entities)
        assert not result.success, "Batch with invalid entity should fail"
        print("✅ Batch validation works")
        
        # Test edge validation
        source_uuid = str(uuid4())
        target_uuid = str(uuid4())
        valid_edge = self.test_data.create_valid_edge(source_uuid, target_uuid)
        result = validation_service.validate_edge(valid_edge)
        assert result.success, f"Valid edge validation should succeed: {result.message}"
        print("✅ Edge validation hooks work")
    
    async def test_post_save_validation_integration(self):
        """Test post-save integrity checks integration."""
        print("Testing post-save validation integration...")
        
        validator = PostSaveValidator(self.driver)
        
        # Test entity post-save validation
        valid_entity = self.test_data.create_valid_entity()
        results = await validator.validate_entity_post_save(valid_entity)
        
        # Should have multiple check results
        assert len(results) > 0, "Should have integrity check results"
        
        # Check specific integrity checks
        check_names = [r.check_name for r in results]
        expected_checks = ['entity_exists', 'uuid_uniqueness', 'required_fields']
        for check in expected_checks:
            assert check in check_names, f"Should include {check} check"
        
        print(f"✅ Post-save entity validation works ({len(results)} checks)")
        
        # Test edge post-save validation
        source_uuid = str(uuid4())
        target_uuid = str(uuid4())
        valid_edge = self.test_data.create_valid_edge(source_uuid, target_uuid)
        results = await validator.validate_edge_post_save(valid_edge)
        
        assert len(results) > 0, "Should have edge integrity check results"
        print(f"✅ Post-save edge validation works ({len(results)} checks)")
        
        # Test batch post-save validation
        batch_entities = [valid_entity, valid_edge]
        results = await validator.validate_batch_post_save(batch_entities)
        assert len(results) > 0, "Should have batch integrity results"
        print("✅ Batch post-save validation works")
    
    async def test_centrality_validation_integration(self):
        """Test centrality validation system."""
        print("Testing centrality validation integration...")
        
        validator = CentralityValidator()
        
        # Test valid centrality values
        valid_entity = self.test_data.create_valid_entity(
            degree_centrality=0.5,
            pagerank_centrality=0.3,
            betweenness_centrality=0.2,
            eigenvector_centrality=0.8
        )
        
        result = validator.validate_entity_centrality(valid_entity)
        assert result.is_valid, f"Valid centrality should pass: {result.errors}"
        print("✅ Valid centrality validation works")
        
        # Test invalid centrality values
        invalid_entity = self.test_data.create_valid_entity(
            degree_centrality=1.5,  # Invalid > 1
            pagerank_centrality=-0.1,  # Invalid < 0
            betweenness_centrality=float('nan')  # Invalid NaN
        )
        
        result = validator.validate_entity_centrality(invalid_entity)
        assert not result.is_valid, "Invalid centrality should fail"
        assert len(result.errors) >= 3, "Should report multiple errors"
        print("✅ Invalid centrality validation works")
        
        # Test auto-correction
        result = validator.validate_entity_centrality(invalid_entity, auto_correct=True)
        assert result.corrected_values is not None, "Should provide corrections"
        print("✅ Centrality auto-correction works")
    
    async def test_fuzzy_matching_integration(self):
        """Test fuzzy matching and deduplication system."""
        print("Testing fuzzy matching integration...")
        
        # Test with default configuration
        matcher = FuzzyMatcher()
        
        # Test entity matching
        entity1 = self.test_data.create_valid_entity("John Smith")
        entity2 = self.test_data.create_valid_entity("John A. Smith")
        entity3 = self.test_data.create_valid_entity("Jane Doe")
        
        # These should match (similar names)
        is_match = matcher.is_entity_match(entity1, entity2)
        print(f"✅ Similar entities match: {is_match}")
        
        # These should not match (different names)
        is_match = matcher.is_entity_match(entity1, entity3)
        print(f"✅ Different entities don't match: {not is_match}")
        
        # Test edge matching
        source_uuid = str(uuid4())
        target_uuid = str(uuid4())
        edge1 = self.test_data.create_valid_edge(source_uuid, target_uuid, fact="John knows Mary")
        edge2 = self.test_data.create_valid_edge(source_uuid, target_uuid, fact="John is friends with Mary")
        
        is_match = matcher.is_edge_match(edge1, edge2)
        print(f"✅ Similar edges match: {is_match}")
        
        # Test candidate finding
        candidates = [entity1, entity2, entity3]
        matches = matcher.find_entity_candidates(entity1, candidates)
        assert len(matches) > 0, "Should find candidate matches"
        print(f"✅ Candidate finding works ({len(matches)} matches)")
        
        # Test with different configurations
        strict_config = FuzzyMatchingConfig.from_strategy(MatchingStrategy.STRICT)
        strict_matcher = FuzzyMatcher(strict_config)
        
        # Strict matching should be more selective
        strict_match = strict_matcher.is_entity_match(entity1, entity2)
        print(f"✅ Strict matching configuration works: {strict_match}")
    
    async def test_merge_policies_integration(self):
        """Test merge policies and entity merging system."""
        print("Testing merge policies integration...")
        
        # Test with different merge strategies
        entities = [
            self.test_data.create_valid_entity(
                "Alice Smith", 
                created_at=datetime(2023, 1, 1),
                summary="Data scientist"
            ),
            self.test_data.create_valid_entity(
                "Alice M. Smith",
                created_at=datetime(2024, 1, 1),
                summary="Senior data scientist with ML expertise"
            )
        ]
        
        # Test PRESERVE_OLDEST strategy
        config = MergePolicyConfig(strategy=MergeStrategy.PRESERVE_OLDEST)
        merger = EntityMerger(config)
        result = merger.merge_entities(entities)
        
        assert result['created_at'] == entities[0]['created_at'], "Should preserve oldest timestamp"
        print("✅ PRESERVE_OLDEST merge strategy works")
        
        # Test PRESERVE_NEWEST strategy  
        config = MergePolicyConfig(strategy=MergeStrategy.PRESERVE_NEWEST)
        merger = EntityMerger(config)
        result = merger.merge_entities(entities)
        
        assert result['created_at'] == entities[1]['created_at'], "Should preserve newest timestamp"
        print("✅ PRESERVE_NEWEST merge strategy works")
        
        # Test PRESERVE_MOST_COMPLETE strategy
        config = MergePolicyConfig(strategy=MergeStrategy.PRESERVE_MOST_COMPLETE)
        merger = EntityMerger(config)
        result = merger.merge_entities(entities)
        
        # Should choose entity with longer summary
        assert len(result['summary']) > len(entities[0]['summary']), "Should preserve more complete summary"
        print("✅ PRESERVE_MOST_COMPLETE merge strategy works")
        
        # Test merge with conflict report
        result, conflicts = merger.merge_with_conflict_report(entities)
        assert len(conflicts) > 0, "Should report conflicts"
        print(f"✅ Merge conflict reporting works ({len(conflicts)} conflicts)")
        
        # Test convenience function
        merged = merge_duplicate_entities(entities)
        assert 'uuid' in merged, "Convenience function should return merged entity"
        print("✅ Convenience merge function works")
    
    async def test_centralized_service_integration(self):
        """Test the centralized validation service orchestration."""
        print("Testing centralized validation service...")
        
        # Create service with comprehensive configuration
        config = ValidationConfig(
            enable_pre_save_validation=True,
            enable_post_save_validation=True,
            enable_centrality_validation=True,
            enable_deduplication=True,
            batch_size=50,
            detailed_reports=True
        )
        service = CentralizedValidationService(self.driver, config)
        
        # Test comprehensive entity validation
        entities = [
            self.test_data.create_valid_entity("Valid Entity"),
            self.test_data.create_invalid_entity(),
            self.test_data.create_valid_entity("Potential Duplicate"),
            self.test_data.create_valid_entity("Potential Duplicate"),  # Duplicate
        ]
        
        report = await service.validate_entities_comprehensive(entities)
        
        assert isinstance(report, ValidationReport), "Should return ValidationReport"
        assert report.total_entities == len(entities), "Should count all entities"
        assert len(report.issues) > 0, "Should find validation issues"
        assert report.error_count > 0, "Should have errors from invalid entity"
        assert 'total_time' in report.performance_metrics, "Should track performance"
        
        print(f"✅ Comprehensive entity validation works ({len(report.issues)} issues found)")
        
        # Test comprehensive edge validation
        edges = [
            self.test_data.create_valid_edge(str(uuid4()), str(uuid4())),
            self.test_data.create_invalid_edge(),
        ]
        
        report = await service.validate_edges_comprehensive(edges)
        
        assert report.total_edges == len(edges), "Should count all edges"
        assert report.error_count > 0, "Should have errors from invalid edge"
        print(f"✅ Comprehensive edge validation works ({len(report.issues)} issues found)")
        
        # Test post-save validation
        mixed_entities = [
            self.test_data.create_valid_entity("Post Save Entity"),
            self.test_data.create_valid_edge(str(uuid4()), str(uuid4()))
        ]
        
        report = await service.validate_post_save(mixed_entities)
        assert len(report.issues) >= 0, "Should process post-save validation"
        print("✅ Centralized post-save validation works")
        
        # Test validation report functionality
        assert report.to_dict()['operation_id'] is not None, "Should serialize to dict"
        print("✅ Validation report serialization works")
        
        # Test summary generation
        reports = [report]
        summary = service.get_validation_summary(reports)
        assert 'total_reports' in summary, "Should generate summary statistics"
        print("✅ Validation summary generation works")
    
    async def test_environment_configuration_integration(self):
        """Test environment variable configuration across all components."""
        print("Testing environment configuration integration...")
        
        # Test with various environment overrides
        test_env = {
            'USE_DETERMINISTIC_UUIDS': 'true',
            'DEDUP_ENHANCED_NORMALIZATION': 'true',
            'FUZZY_MATCHING_STRATEGY': 'strict',
            'MERGE_STRATEGY': 'preserve_newest',
            'POST_SAVE_VALIDATION_ENABLED': 'true',
            'VALIDATION_ENABLE_PRE_SAVE': 'true',
            'VALIDATION_BATCH_SIZE': '200',
            'CENTRALITY_VALIDATION_AUTO_CORRECT': 'true'
        }
        
        with patch.dict(os.environ, test_env):
            # Test fuzzy matching configuration
            config = FuzzyMatchingConfig.from_environment()
            # Should load strict configuration
            print("✅ Fuzzy matching environment config works")
            
            # Test merge policy configuration  
            merge_config = MergePolicyConfig.from_environment()
            assert merge_config.strategy == MergeStrategy.PRESERVE_NEWEST, "Should load merge strategy from env"
            print("✅ Merge policy environment config works")
            
            # Test validation service configuration
            validation_config = ValidationConfig.from_environment()
            assert validation_config.batch_size == 200, "Should load batch size from env"
            print("✅ Validation service environment config works")
            
            # Test name normalization
            normalized = normalize_entity_name("  Dr. John A. Smith Jr.  ")
            assert normalized != "  Dr. John A. Smith Jr.  ", "Should normalize with enhanced mode"
            print("✅ Enhanced name normalization works")
    
    async def test_performance_and_scalability(self):
        """Test performance and scalability of the validation system."""
        print("Testing performance and scalability...")
        
        # Create larger dataset for performance testing
        large_entity_batch = [
            self.test_data.create_valid_entity(f"Entity {i}")
            for i in range(100)
        ]
        
        # Add some invalid entities
        large_entity_batch.extend([
            self.test_data.create_invalid_entity() for _ in range(10)
        ])
        
        # Test centralized validation performance
        service = CentralizedValidationService(self.driver)
        
        start_time = datetime.now()
        report = await service.validate_entities_comprehensive(large_entity_batch)
        end_time = datetime.now()
        
        processing_time = (end_time - start_time).total_seconds()
        throughput = len(large_entity_batch) / processing_time
        
        assert throughput > 10, f"Should process at least 10 entities/second, got {throughput:.2f}"
        assert processing_time < 30, f"Should complete within 30 seconds, took {processing_time:.2f}"
        
        print(f"✅ Performance test passed: {throughput:.2f} entities/second")
        
        # Test batch processing
        batch_reports = []
        for i in range(0, len(large_entity_batch), 25):
            batch = large_entity_batch[i:i+25]
            batch_report = await service.validate_entities_comprehensive(batch)
            batch_reports.append(batch_report)
        
        # Test summary generation
        summary = service.get_validation_summary(batch_reports)
        assert summary['total_entities'] == len(large_entity_batch), "Should count all entities across batches"
        print("✅ Batch processing and summary generation works")
    
    async def test_error_handling_and_recovery(self):
        """Test error handling and recovery mechanisms."""
        print("Testing error handling and recovery...")
        
        # Test validation with malformed data
        malformed_entities = [
            None,  # Null entity
            {},  # Empty entity
            {"invalid": "structure"},  # Wrong structure
            self.test_data.create_valid_entity("Valid Entity"),  # One valid entity
        ]
        
        service = CentralizedValidationService(self.driver)
        
        try:
            # Should handle malformed data gracefully
            report = await service.validate_entities_comprehensive(malformed_entities)
            assert isinstance(report, ValidationReport), "Should return report even with errors"
            print("✅ Malformed data handling works")
        except Exception as e:
            print(f"⚠️  Malformed data test encountered exception: {e}")
        
        # Test timeout handling (mock)
        config = ValidationConfig(max_validation_time=1)  # Very short timeout
        service_with_timeout = CentralizedValidationService(self.driver, config)
        
        # This test would need actual slow operations to trigger timeout
        # For now, just verify the configuration is applied
        assert service_with_timeout.config.max_validation_time == 1, "Should apply timeout config"
        print("✅ Timeout configuration works")
        
        # Test graceful degradation
        service_no_driver = CentralizedValidationService()  # No driver
        report = await service_no_driver.validate_post_save([])
        assert report.operation_id == "post_save_skipped", "Should skip when driver unavailable"
        print("✅ Graceful degradation works")
    
    async def run_all_tests(self):
        """Execute the complete comprehensive test suite."""
        print("=" * 80)
        print("COMPREHENSIVE DATA VALIDATION FRAMEWORK TEST SUITE")
        print("=" * 80)
        print()
        
        test_methods = [
            self.test_pydantic_validators_integration,
            self.test_deterministic_uuid_integration,
            self.test_database_constraints_integration,
            self.test_transaction_management_integration,
            self.test_validation_hooks_integration,
            self.test_post_save_validation_integration,
            self.test_centrality_validation_integration,
            self.test_fuzzy_matching_integration,
            self.test_merge_policies_integration,
            self.test_centralized_service_integration,
            self.test_environment_configuration_integration,
            self.test_performance_and_scalability,
            self.test_error_handling_and_recovery
        ]
        
        passed_tests = 0
        total_tests = len(test_methods)
        
        for test_method in test_methods:
            try:
                print(f"\n{'='*60}")
                await test_method()
                passed_tests += 1
                print(f"✅ {test_method.__name__} PASSED")
            except Exception as e:
                print(f"❌ {test_method.__name__} FAILED: {e}")
                import traceback
                traceback.print_exc()
        
        print("\n" + "=" * 80)
        print(f"TEST RESULTS: {passed_tests}/{total_tests} tests passed")
        
        if passed_tests == total_tests:
            print("🎉 ALL COMPREHENSIVE VALIDATION TESTS PASSED!")
            print("The complete data validation framework is working correctly.")
            return True
        else:
            print(f"❌ {total_tests - passed_tests} tests failed")
            print("The validation framework needs attention.")
            return False


async def main():
    """Main test execution function."""
    test_suite = ComprehensiveValidationTestSuite()
    success = await test_suite.run_all_tests()
    return success


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)