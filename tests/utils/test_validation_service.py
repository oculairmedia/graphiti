"""
Tests for centralized validation service.

Copyright 2024, Zep Software, Inc.
Licensed under the Apache License, Version 2.0.
"""

import os
from datetime import datetime
from unittest.mock import patch, MagicMock, AsyncMock

import pytest

from graphiti_core.utils.validation_service import (
    CentralizedValidationService,
    ValidationConfig,
    ValidationIssue,
    ValidationPhase,
    ValidationReport,
    ValidationSeverity,
    get_validation_service,
)


class TestValidationPhase:
    """Tests for ValidationPhase enum."""

    def test_pre_save_value(self):
        assert ValidationPhase.PRE_SAVE.value == 'pre_save'

    def test_post_save_value(self):
        assert ValidationPhase.POST_SAVE.value == 'post_save'

    def test_deduplication_value(self):
        assert ValidationPhase.DEDUPLICATION.value == 'deduplication'

    def test_integrity_check_value(self):
        assert ValidationPhase.INTEGRITY_CHECK.value == 'integrity_check'

    def test_merge_conflict_value(self):
        assert ValidationPhase.MERGE_CONFLICT.value == 'merge_conflict'


class TestValidationSeverity:
    """Tests for ValidationSeverity enum."""

    def test_info_value(self):
        assert ValidationSeverity.INFO.value == 'info'

    def test_warning_value(self):
        assert ValidationSeverity.WARNING.value == 'warning'

    def test_error_value(self):
        assert ValidationSeverity.ERROR.value == 'error'

    def test_critical_value(self):
        assert ValidationSeverity.CRITICAL.value == 'critical'


class TestValidationIssue:
    """Tests for ValidationIssue dataclass."""

    def test_basic_creation(self):
        issue = ValidationIssue(
            phase=ValidationPhase.PRE_SAVE,
            severity=ValidationSeverity.ERROR,
            message='Test error message',
        )
        assert issue.phase == ValidationPhase.PRE_SAVE
        assert issue.severity == ValidationSeverity.ERROR
        assert issue.message == 'Test error message'

    def test_default_values(self):
        issue = ValidationIssue(
            phase=ValidationPhase.PRE_SAVE,
            severity=ValidationSeverity.WARNING,
            message='Test warning',
        )
        assert issue.entity_id is None
        assert issue.field_name is None
        assert issue.suggested_fix is None
        assert issue.metadata == {}

    def test_full_creation(self):
        issue = ValidationIssue(
            phase=ValidationPhase.INTEGRITY_CHECK,
            severity=ValidationSeverity.CRITICAL,
            message='Critical error',
            entity_id='entity-123',
            field_name='name',
            suggested_fix='Fix the name field',
            metadata={'extra': 'data'},
        )
        assert issue.entity_id == 'entity-123'
        assert issue.field_name == 'name'
        assert issue.suggested_fix == 'Fix the name field'
        assert issue.metadata == {'extra': 'data'}

    def test_to_dict(self):
        issue = ValidationIssue(
            phase=ValidationPhase.PRE_SAVE,
            severity=ValidationSeverity.ERROR,
            message='Test message',
            entity_id='test-id',
        )
        result = issue.to_dict()

        assert result['phase'] == 'pre_save'
        assert result['severity'] == 'error'
        assert result['message'] == 'Test message'
        assert result['entity_id'] == 'test-id'
        assert result['field_name'] is None
        assert result['suggested_fix'] is None
        assert result['metadata'] == {}


class TestValidationReport:
    """Tests for ValidationReport dataclass."""

    def test_basic_creation(self):
        report = ValidationReport(
            operation_id='test-op-1',
            timestamp=datetime.now(),
            total_entities=10,
            total_edges=5,
        )
        assert report.operation_id == 'test-op-1'
        assert report.total_entities == 10
        assert report.total_edges == 5
        assert report.issues == []

    def test_error_count_empty(self):
        report = ValidationReport(
            operation_id='test',
            timestamp=datetime.now(),
            total_entities=0,
            total_edges=0,
        )
        assert report.error_count == 0

    def test_error_count_with_errors(self):
        report = ValidationReport(
            operation_id='test',
            timestamp=datetime.now(),
            total_entities=0,
            total_edges=0,
            issues=[
                ValidationIssue(
                    phase=ValidationPhase.PRE_SAVE,
                    severity=ValidationSeverity.ERROR,
                    message='Error 1',
                ),
                ValidationIssue(
                    phase=ValidationPhase.PRE_SAVE,
                    severity=ValidationSeverity.CRITICAL,
                    message='Critical 1',
                ),
                ValidationIssue(
                    phase=ValidationPhase.PRE_SAVE,
                    severity=ValidationSeverity.WARNING,
                    message='Warning 1',
                ),
            ],
        )
        assert report.error_count == 2  # ERROR + CRITICAL

    def test_warning_count(self):
        report = ValidationReport(
            operation_id='test',
            timestamp=datetime.now(),
            total_entities=0,
            total_edges=0,
            issues=[
                ValidationIssue(
                    phase=ValidationPhase.PRE_SAVE,
                    severity=ValidationSeverity.WARNING,
                    message='Warning 1',
                ),
                ValidationIssue(
                    phase=ValidationPhase.PRE_SAVE,
                    severity=ValidationSeverity.WARNING,
                    message='Warning 2',
                ),
                ValidationIssue(
                    phase=ValidationPhase.PRE_SAVE,
                    severity=ValidationSeverity.ERROR,
                    message='Error 1',
                ),
            ],
        )
        assert report.warning_count == 2

    def test_has_errors_false(self):
        report = ValidationReport(
            operation_id='test',
            timestamp=datetime.now(),
            total_entities=0,
            total_edges=0,
        )
        assert report.has_errors is False

    def test_has_errors_true(self):
        report = ValidationReport(
            operation_id='test',
            timestamp=datetime.now(),
            total_entities=0,
            total_edges=0,
            issues=[
                ValidationIssue(
                    phase=ValidationPhase.PRE_SAVE,
                    severity=ValidationSeverity.ERROR,
                    message='Error',
                ),
            ],
        )
        assert report.has_errors is True

    def test_is_valid_true(self):
        report = ValidationReport(
            operation_id='test',
            timestamp=datetime.now(),
            total_entities=0,
            total_edges=0,
            issues=[
                ValidationIssue(
                    phase=ValidationPhase.PRE_SAVE,
                    severity=ValidationSeverity.WARNING,
                    message='Warning',
                ),
            ],
        )
        assert report.is_valid is True

    def test_is_valid_false_with_critical(self):
        report = ValidationReport(
            operation_id='test',
            timestamp=datetime.now(),
            total_entities=0,
            total_edges=0,
            issues=[
                ValidationIssue(
                    phase=ValidationPhase.PRE_SAVE,
                    severity=ValidationSeverity.CRITICAL,
                    message='Critical error',
                ),
            ],
        )
        assert report.is_valid is False

    def test_add_issue(self):
        report = ValidationReport(
            operation_id='test',
            timestamp=datetime.now(),
            total_entities=0,
            total_edges=0,
        )
        assert len(report.issues) == 0

        report.add_issue(
            ValidationIssue(
                phase=ValidationPhase.PRE_SAVE,
                severity=ValidationSeverity.INFO,
                message='Info message',
            )
        )
        assert len(report.issues) == 1

    def test_to_dict(self):
        timestamp = datetime.now()
        report = ValidationReport(
            operation_id='test-op',
            timestamp=timestamp,
            total_entities=5,
            total_edges=3,
            issues=[
                ValidationIssue(
                    phase=ValidationPhase.PRE_SAVE,
                    severity=ValidationSeverity.WARNING,
                    message='Test warning',
                ),
            ],
            performance_metrics={'total_time': 1.5},
        )
        result = report.to_dict()

        assert result['operation_id'] == 'test-op'
        assert result['timestamp'] == timestamp.isoformat()
        assert result['total_entities'] == 5
        assert result['total_edges'] == 3
        assert result['error_count'] == 0
        assert result['warning_count'] == 1
        assert result['has_errors'] is False
        assert result['is_valid'] is True
        assert len(result['issues']) == 1
        assert result['performance_metrics'] == {'total_time': 1.5}


class TestValidationConfig:
    """Tests for ValidationConfig dataclass."""

    def test_default_values(self):
        config = ValidationConfig()
        assert config.enable_pre_save_validation is True
        assert config.enable_post_save_validation is True
        assert config.enable_deduplication is True
        assert config.enable_integrity_checks is True
        assert config.fail_on_warnings is False
        assert config.max_validation_time == 300
        assert config.batch_size == 100
        assert config.parallel_validation is True
        assert config.max_workers == 4
        assert config.detailed_reports is True
        assert config.audit_logging is True

    def test_custom_values(self):
        config = ValidationConfig(
            enable_pre_save_validation=False,
            fail_on_warnings=True,
            max_validation_time=600,
            batch_size=50,
        )
        assert config.enable_pre_save_validation is False
        assert config.fail_on_warnings is True
        assert config.max_validation_time == 600
        assert config.batch_size == 50

    def test_from_environment_defaults(self):
        with patch.dict(os.environ, {}, clear=True):
            config = ValidationConfig.from_environment()
            assert config.enable_pre_save_validation is True
            assert config.batch_size == 100

    def test_from_environment_custom_bools(self):
        with patch.dict(
            os.environ,
            {
                'VALIDATION_ENABLE_PRE_SAVE': 'false',
                'VALIDATION_FAIL_ON_WARNINGS': 'true',
                'VALIDATION_PARALLEL': 'false',
            },
        ):
            config = ValidationConfig.from_environment()
            assert config.enable_pre_save_validation is False
            assert config.fail_on_warnings is True
            assert config.parallel_validation is False

    def test_from_environment_custom_ints(self):
        with patch.dict(
            os.environ,
            {
                'VALIDATION_MAX_TIME': '600',
                'VALIDATION_BATCH_SIZE': '50',
                'VALIDATION_MAX_WORKERS': '8',
            },
        ):
            config = ValidationConfig.from_environment()
            assert config.max_validation_time == 600
            assert config.batch_size == 50
            assert config.max_workers == 8

    def test_from_environment_invalid_int(self):
        with patch.dict(os.environ, {'VALIDATION_BATCH_SIZE': 'invalid'}):
            config = ValidationConfig.from_environment()
            # Should use default on invalid value
            assert config.batch_size == 100


class TestCentralizedValidationService:
    """Tests for CentralizedValidationService class."""

    def test_init_no_driver(self):
        service = CentralizedValidationService()
        assert service.driver is None
        assert service.config is not None
        assert service.post_save_validator is None

    def test_init_with_config(self):
        config = ValidationConfig(enable_pre_save_validation=False)
        service = CentralizedValidationService(config=config)
        assert service.config.enable_pre_save_validation is False

    def test_set_driver(self):
        service = CentralizedValidationService()
        assert service.driver is None

        mock_driver = MagicMock()
        with patch(
            'graphiti_core.utils.validation_service.get_post_save_validator'
        ) as mock_get_validator:
            mock_get_validator.return_value = MagicMock()
            service.set_driver(mock_driver)

        assert service.driver == mock_driver

    def test_is_entity_with_dict(self):
        service = CentralizedValidationService()
        # Entity dict
        entity_dict = {'uuid': 'test-id', 'name': 'Test Entity'}
        assert service._is_entity(entity_dict) is True

        # Edge dict (should be False)
        edge_dict = {
            'uuid': 'edge-id',
            'source_node_uuid': 'a',
            'target_node_uuid': 'b',
        }
        assert service._is_entity(edge_dict) is False

    def test_is_edge_with_dict(self):
        service = CentralizedValidationService()
        # Edge dict
        edge_dict = {'source_node_uuid': 'a', 'target_node_uuid': 'b'}
        assert service._is_edge(edge_dict) is True

        # Entity dict (should be False)
        entity_dict = {'uuid': 'test-id', 'name': 'Test Entity'}
        assert service._is_edge(entity_dict) is False

    def test_convert_integrity_severity_error(self):
        service = CentralizedValidationService()
        result = service._convert_integrity_severity('ERROR')
        assert result == ValidationSeverity.ERROR

    def test_convert_integrity_severity_warning(self):
        service = CentralizedValidationService()
        result = service._convert_integrity_severity('WARNING')
        assert result == ValidationSeverity.WARNING

    def test_convert_integrity_severity_other(self):
        service = CentralizedValidationService()
        result = service._convert_integrity_severity('INFO')
        assert result == ValidationSeverity.INFO

        result = service._convert_integrity_severity('UNKNOWN')
        assert result == ValidationSeverity.INFO

    def test_get_validation_summary_empty(self):
        service = CentralizedValidationService()
        result = service.get_validation_summary([])
        assert result == {}

    def test_get_validation_summary_single_report(self):
        service = CentralizedValidationService()
        report = ValidationReport(
            operation_id='test',
            timestamp=datetime.now(),
            total_entities=10,
            total_edges=5,
            issues=[
                ValidationIssue(
                    phase=ValidationPhase.PRE_SAVE,
                    severity=ValidationSeverity.WARNING,
                    message='Warning',
                ),
            ],
            performance_metrics={'total_time': 2.0},
        )

        result = service.get_validation_summary([report])

        assert result['total_reports'] == 1
        assert result['total_entities'] == 10
        assert result['total_edges'] == 5
        assert result['total_warnings'] == 1
        assert result['total_errors'] == 0
        assert result['total_time'] == 2.0
        assert result['avg_entities_per_second'] == 5.0

    def test_get_validation_summary_multiple_reports(self):
        service = CentralizedValidationService()
        reports = [
            ValidationReport(
                operation_id='test1',
                timestamp=datetime.now(),
                total_entities=10,
                total_edges=5,
                issues=[
                    ValidationIssue(
                        phase=ValidationPhase.PRE_SAVE,
                        severity=ValidationSeverity.WARNING,
                        message='Warning 1',
                    ),
                ],
                performance_metrics={'total_time': 1.0},
            ),
            ValidationReport(
                operation_id='test2',
                timestamp=datetime.now(),
                total_entities=20,
                total_edges=10,
                issues=[
                    ValidationIssue(
                        phase=ValidationPhase.PRE_SAVE,
                        severity=ValidationSeverity.ERROR,
                        message='Error 1',
                    ),
                ],
                performance_metrics={'total_time': 2.0},
            ),
        ]

        result = service.get_validation_summary(reports)

        assert result['total_reports'] == 2
        assert result['total_entities'] == 30
        assert result['total_edges'] == 15
        assert result['total_warnings'] == 1
        assert result['total_errors'] == 1
        assert result['total_time'] == 3.0
        assert result['issues_by_phase']['pre_save'] == 1
        assert result['issues_by_phase']['centrality'] == 1
        assert result['issues_by_severity']['warning'] == 1
        assert result['issues_by_severity']['error'] == 1


class TestCentralizedValidationServiceAsync:
    """Async tests for CentralizedValidationService."""

    @pytest.mark.asyncio
    async def test_validate_entities_comprehensive_empty(self):
        config = ValidationConfig(
            enable_pre_save_validation=False,
            enable_deduplication=False,
            audit_logging=False,
        )
        service = CentralizedValidationService(config=config)

        report = await service.validate_entities_comprehensive([])

        assert report.total_entities == 0
        assert report.is_valid is True

    @pytest.mark.asyncio
    async def test_validate_entities_comprehensive_single(self):
        config = ValidationConfig(
            enable_pre_save_validation=False,
            enable_deduplication=False,
            audit_logging=False,
        )
        service = CentralizedValidationService(config=config)

        entities = [{'uuid': 'test-1', 'name': 'Test Entity'}]
        report = await service.validate_entities_comprehensive(entities)

        assert report.total_entities == 1
        assert 'total_time' in report.performance_metrics
        assert 'entities_per_second' in report.performance_metrics

    @pytest.mark.asyncio
    async def test_validate_edges_comprehensive_empty(self):
        config = ValidationConfig(
            enable_pre_save_validation=False,
            enable_integrity_checks=False,
            audit_logging=False,
        )
        service = CentralizedValidationService(config=config)

        report = await service.validate_edges_comprehensive([])

        assert report.total_edges == 0
        assert report.is_valid is True

    @pytest.mark.asyncio
    async def test_validate_edges_comprehensive_missing_source(self):
        config = ValidationConfig(
            enable_pre_save_validation=False,
            enable_integrity_checks=True,
            audit_logging=False,
        )
        service = CentralizedValidationService(config=config)

        edges = [{'uuid': 'edge-1', 'target_node_uuid': 'node-b'}]
        report = await service.validate_edges_comprehensive(edges)

        assert report.total_edges == 1
        assert report.has_errors is True
        # Should have issue about missing source_node_uuid
        assert any('source node UUID' in issue.message for issue in report.issues)

    @pytest.mark.asyncio
    async def test_validate_edges_comprehensive_missing_target(self):
        config = ValidationConfig(
            enable_pre_save_validation=False,
            enable_integrity_checks=True,
            audit_logging=False,
        )
        service = CentralizedValidationService(config=config)

        edges = [{'uuid': 'edge-1', 'source_node_uuid': 'node-a'}]
        report = await service.validate_edges_comprehensive(edges)

        assert report.has_errors is True
        assert any('target node UUID' in issue.message for issue in report.issues)

    @pytest.mark.asyncio
    async def test_validate_edges_comprehensive_self_loop(self):
        config = ValidationConfig(
            enable_pre_save_validation=False,
            enable_integrity_checks=True,
            audit_logging=False,
        )
        service = CentralizedValidationService(config=config)

        edges = [
            {
                'uuid': 'edge-1',
                'source_node_uuid': 'node-a',
                'target_node_uuid': 'node-a',  # Self-loop
            }
        ]
        report = await service.validate_edges_comprehensive(edges)

        # Self-loop should be a warning, not error
        assert any('self-loop' in issue.message for issue in report.issues)
        self_loop_issues = [i for i in report.issues if 'self-loop' in i.message]
        assert all(i.severity == ValidationSeverity.WARNING for i in self_loop_issues)

    @pytest.mark.asyncio
    async def test_validate_post_save_disabled(self):
        config = ValidationConfig(enable_post_save_validation=False)
        service = CentralizedValidationService(config=config)

        entities = [{'uuid': 'test-1', 'name': 'Test'}]
        report = await service.validate_post_save(entities)

        assert report.operation_id == 'post_save_skipped'

    @pytest.mark.asyncio
    async def test_validate_post_save_no_validator(self):
        config = ValidationConfig(enable_post_save_validation=True)
        service = CentralizedValidationService(config=config)
        # No driver set, so no post_save_validator

        entities = [{'uuid': 'test-1', 'name': 'Test'}]
        report = await service.validate_post_save(entities)

        assert report.operation_id == 'post_save_skipped'


class TestModuleFunctions:
    """Tests for module-level convenience functions."""

    def test_get_validation_service_creates_instance(self):
        # Reset global instance
        import graphiti_core.utils.validation_service as vs

        vs._validation_service = None

        service = get_validation_service()
        assert isinstance(service, CentralizedValidationService)

    def test_get_validation_service_reuses_instance(self):
        import graphiti_core.utils.validation_service as vs

        vs._validation_service = None

        service1 = get_validation_service()
        service2 = get_validation_service()
        assert service1 is service2

    def test_get_validation_service_with_config(self):
        import graphiti_core.utils.validation_service as vs

        vs._validation_service = None

        config = ValidationConfig(batch_size=50)
        service = get_validation_service(config=config)
        assert service.config.batch_size == 50

        # Reset for other tests
        vs._validation_service = None
