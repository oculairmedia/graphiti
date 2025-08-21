"""
Centralized validation service that orchestrates all validation components.

This service provides a unified interface for all validation operations,
integrating pre-save hooks, post-save integrity checks, centrality validation,
merge policies, and other validation components into a cohesive system.
"""

import logging
import os
import asyncio
from typing import Any, Dict, List, Optional, Union, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from graphiti_core.nodes import EntityNode, EpisodicNode
from graphiti_core.edges import EntityEdge
from graphiti_core.driver.driver import GraphDriver
from graphiti_core.utils.validation_hooks import (
    ValidationResult,
    ValidationService as HookValidationService,
    HookType,
    hook_registry
)
from graphiti_core.utils.post_save_validation import (
    PostSaveValidator,
    IntegrityCheckResult,
    get_post_save_validator
)
from graphiti_core.utils.centrality_validation import (
    CentralityValidator,
    CentralityValidationResult
)
from graphiti_core.utils.merge_policies import (
    EntityMerger,
    MergePolicyConfig,
    get_entity_merger
)
from graphiti_core.utils.fuzzy_matching import (
    FuzzyMatcher,
    FuzzyMatchingConfig,
    get_fuzzy_matcher
)

logger = logging.getLogger(__name__)


class ValidationPhase(Enum):
    """Phases of validation in the data lifecycle."""
    PRE_SAVE = "pre_save"
    POST_SAVE = "post_save"
    DEDUPLICATION = "deduplication"
    CENTRALITY = "centrality"
    INTEGRITY_CHECK = "integrity_check"
    MERGE_CONFLICT = "merge_conflict"


class ValidationSeverity(Enum):
    """Severity levels for validation results."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class ValidationIssue:
    """A validation issue discovered during processing."""
    phase: ValidationPhase
    severity: ValidationSeverity
    message: str
    entity_id: Optional[str] = None
    field_name: Optional[str] = None
    suggested_fix: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'phase': self.phase.value,
            'severity': self.severity.value,
            'message': self.message,
            'entity_id': self.entity_id,
            'field_name': self.field_name,
            'suggested_fix': self.suggested_fix,
            'metadata': self.metadata
        }


@dataclass
class ValidationReport:
    """Complete validation report for an operation."""
    operation_id: str
    timestamp: datetime
    total_entities: int
    total_edges: int
    issues: List[ValidationIssue] = field(default_factory=list)
    performance_metrics: Dict[str, float] = field(default_factory=dict)
    
    @property
    def error_count(self) -> int:
        """Count of error-level issues."""
        return len([i for i in self.issues if i.severity in [ValidationSeverity.ERROR, ValidationSeverity.CRITICAL]])
    
    @property
    def warning_count(self) -> int:
        """Count of warning-level issues."""
        return len([i for i in self.issues if i.severity == ValidationSeverity.WARNING])
    
    @property
    def has_errors(self) -> bool:
        """Whether the report contains any errors."""
        return self.error_count > 0
    
    @property
    def is_valid(self) -> bool:
        """Whether validation passed (no critical errors)."""
        return len([i for i in self.issues if i.severity == ValidationSeverity.CRITICAL]) == 0
    
    def add_issue(self, issue: ValidationIssue):
        """Add a validation issue to the report."""
        self.issues.append(issue)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'operation_id': self.operation_id,
            'timestamp': self.timestamp.isoformat(),
            'total_entities': self.total_entities,
            'total_edges': self.total_edges,
            'error_count': self.error_count,
            'warning_count': self.warning_count,
            'has_errors': self.has_errors,
            'is_valid': self.is_valid,
            'issues': [issue.to_dict() for issue in self.issues],
            'performance_metrics': self.performance_metrics
        }


@dataclass
class ValidationConfig:
    """Configuration for the centralized validation service."""
    
    # Phase enablement
    enable_pre_save_validation: bool = True
    enable_post_save_validation: bool = True
    enable_centrality_validation: bool = True
    enable_deduplication: bool = True
    enable_integrity_checks: bool = True
    
    # Validation strictness
    fail_on_warnings: bool = False
    fail_on_centrality_errors: bool = False
    max_validation_time: int = 300  # seconds
    
    # Deduplication settings
    fuzzy_matching_config: Optional[FuzzyMatchingConfig] = None
    merge_policy_config: Optional[MergePolicyConfig] = None
    
    # Performance settings
    batch_size: int = 100
    parallel_validation: bool = True
    max_workers: int = 4
    
    # Reporting
    detailed_reports: bool = True
    audit_logging: bool = True
    
    @classmethod
    def from_environment(cls) -> 'ValidationConfig':
        """Load configuration from environment variables."""
        
        def get_bool_env(key: str, default: bool) -> bool:
            return os.getenv(key, str(default)).lower() in ('true', '1', 'yes', 'on')
        
        def get_int_env(key: str, default: int) -> int:
            try:
                return int(os.getenv(key, str(default)))
            except ValueError:
                logger.warning(f"Invalid int value for {key}, using default: {default}")
                return default
        
        return cls(
            enable_pre_save_validation=get_bool_env('VALIDATION_ENABLE_PRE_SAVE', True),
            enable_post_save_validation=get_bool_env('VALIDATION_ENABLE_POST_SAVE', True),
            enable_centrality_validation=get_bool_env('VALIDATION_ENABLE_CENTRALITY', True),
            enable_deduplication=get_bool_env('VALIDATION_ENABLE_DEDUPLICATION', True),
            enable_integrity_checks=get_bool_env('VALIDATION_ENABLE_INTEGRITY', True),
            fail_on_warnings=get_bool_env('VALIDATION_FAIL_ON_WARNINGS', False),
            fail_on_centrality_errors=get_bool_env('VALIDATION_FAIL_ON_CENTRALITY', False),
            max_validation_time=get_int_env('VALIDATION_MAX_TIME', 300),
            batch_size=get_int_env('VALIDATION_BATCH_SIZE', 100),
            parallel_validation=get_bool_env('VALIDATION_PARALLEL', True),
            max_workers=get_int_env('VALIDATION_MAX_WORKERS', 4),
            detailed_reports=get_bool_env('VALIDATION_DETAILED_REPORTS', True),
            audit_logging=get_bool_env('VALIDATION_AUDIT_LOGGING', True)
        )


class CentralizedValidationService:
    """Central service for orchestrating all validation operations."""
    
    def __init__(self, driver: Optional[GraphDriver] = None, config: Optional[ValidationConfig] = None):
        self.driver = driver
        self.config = config or ValidationConfig.from_environment()
        self.logger = logging.getLogger(f"{__name__}.CentralizedValidationService")
        
        # Initialize component validators
        self.hook_service = HookValidationService()
        self.centrality_validator = CentralityValidator()
        
        # Driver-dependent services (initialized when driver is available)
        self.post_save_validator: Optional[PostSaveValidator] = None
        
        # Initialize other components
        self.fuzzy_matcher = get_fuzzy_matcher(self.config.fuzzy_matching_config)
        self.entity_merger = get_entity_merger(self.config.merge_policy_config)
        
        if self.driver:
            self.post_save_validator = get_post_save_validator(self.driver)
    
    def set_driver(self, driver: GraphDriver):
        """Set the graph driver for database-dependent operations."""
        self.driver = driver
        self.post_save_validator = get_post_save_validator(driver)
    
    async def validate_entities_comprehensive(self, 
                                            entities: List[Union[EntityNode, dict]], 
                                            context: Optional[Dict[str, Any]] = None) -> ValidationReport:
        """Run comprehensive validation on a list of entities."""
        
        operation_id = f"validate_{datetime.now().timestamp()}"
        report = ValidationReport(
            operation_id=operation_id,
            timestamp=datetime.now(),
            total_entities=len(entities),
            total_edges=0
        )
        
        if context is None:
            context = {}
        
        start_time = datetime.now()
        
        try:
            # Phase 1: Pre-save validation
            if self.config.enable_pre_save_validation:
                await self._run_pre_save_validation(entities, report, context)
            
            # Phase 2: Centrality validation
            if self.config.enable_centrality_validation:
                await self._run_centrality_validation(entities, report, context)
            
            # Phase 3: Deduplication analysis (without actual merging)
            if self.config.enable_deduplication:
                await self._run_deduplication_analysis(entities, report, context)
            
            # Calculate performance metrics
            end_time = datetime.now()
            report.performance_metrics['total_time'] = (end_time - start_time).total_seconds()
            report.performance_metrics['entities_per_second'] = len(entities) / report.performance_metrics['total_time']
            
            # Audit logging
            if self.config.audit_logging:
                self._log_validation_report(report)
            
            return report
            
        except asyncio.TimeoutError:
            report.add_issue(ValidationIssue(
                phase=ValidationPhase.INTEGRITY_CHECK,
                severity=ValidationSeverity.ERROR,
                message=f"Validation timed out after {self.config.max_validation_time} seconds"
            ))
            return report
        
        except Exception as e:
            self.logger.error(f"Validation failed with exception: {e}")
            report.add_issue(ValidationIssue(
                phase=ValidationPhase.INTEGRITY_CHECK,
                severity=ValidationSeverity.CRITICAL,
                message=f"Validation failed with exception: {str(e)}"
            ))
            return report
    
    async def validate_edges_comprehensive(self,
                                         edges: List[Union[EntityEdge, dict]],
                                         context: Optional[Dict[str, Any]] = None) -> ValidationReport:
        """Run comprehensive validation on a list of edges."""
        
        operation_id = f"validate_edges_{datetime.now().timestamp()}"
        report = ValidationReport(
            operation_id=operation_id,
            timestamp=datetime.now(),
            total_entities=0,
            total_edges=len(edges)
        )
        
        if context is None:
            context = {}
        
        start_time = datetime.now()
        
        try:
            # Phase 1: Pre-save validation for edges
            if self.config.enable_pre_save_validation:
                await self._run_pre_save_edge_validation(edges, report, context)
            
            # Phase 2: Edge-specific integrity checks
            if self.config.enable_integrity_checks:
                await self._run_edge_integrity_validation(edges, report, context)
            
            # Calculate performance metrics
            end_time = datetime.now()
            report.performance_metrics['total_time'] = (end_time - start_time).total_seconds()
            report.performance_metrics['edges_per_second'] = len(edges) / report.performance_metrics['total_time']
            
            # Audit logging
            if self.config.audit_logging:
                self._log_validation_report(report)
            
            return report
            
        except Exception as e:
            self.logger.error(f"Edge validation failed with exception: {e}")
            report.add_issue(ValidationIssue(
                phase=ValidationPhase.INTEGRITY_CHECK,
                severity=ValidationSeverity.CRITICAL,
                message=f"Edge validation failed with exception: {str(e)}"
            ))
            return report
    
    async def validate_post_save(self,
                               entities: List[Union[EntityNode, EntityEdge, dict]],
                               context: Optional[Dict[str, Any]] = None) -> ValidationReport:
        """Run post-save integrity validation."""
        
        if not self.config.enable_post_save_validation or not self.post_save_validator:
            return ValidationReport(
                operation_id="post_save_skipped",
                timestamp=datetime.now(),
                total_entities=len(entities),
                total_edges=0
            )
        
        operation_id = f"post_save_{datetime.now().timestamp()}"
        report = ValidationReport(
            operation_id=operation_id,
            timestamp=datetime.now(),
            total_entities=len([e for e in entities if self._is_entity(e)]),
            total_edges=len([e for e in entities if self._is_edge(e)])
        )
        
        start_time = datetime.now()
        
        try:
            # Run post-save integrity checks
            integrity_results = await self.post_save_validator.validate_batch_post_save(entities, context)
            
            # Convert integrity results to validation issues
            for result in integrity_results:
                severity = self._convert_integrity_severity(result.severity)
                report.add_issue(ValidationIssue(
                    phase=ValidationPhase.POST_SAVE,
                    severity=severity,
                    message=result.message,
                    entity_id=result.entity_id,
                    suggested_fix=result.repair_suggestion,
                    metadata={'check_name': result.check_name}
                ))
            
            # Calculate performance metrics
            end_time = datetime.now()
            report.performance_metrics['total_time'] = (end_time - start_time).total_seconds()
            
            # Audit logging
            if self.config.audit_logging:
                self._log_validation_report(report)
            
            return report
            
        except Exception as e:
            self.logger.error(f"Post-save validation failed with exception: {e}")
            report.add_issue(ValidationIssue(
                phase=ValidationPhase.POST_SAVE,
                severity=ValidationSeverity.CRITICAL,
                message=f"Post-save validation failed with exception: {str(e)}"
            ))
            return report
    
    async def _run_pre_save_validation(self, 
                                     entities: List[Any], 
                                     report: ValidationReport, 
                                     context: Dict[str, Any]):
        """Run pre-save validation hooks."""
        
        phase_start = datetime.now()
        
        for i, entity in enumerate(entities):
            entity_context = context.copy()
            entity_context['batch_entities'] = entities
            entity_context['current_entity_index'] = i
            
            # Run pre-save validation
            result = self.hook_service.validate_entity(entity, entity_context)
            
            if not result.success:
                severity = ValidationSeverity.ERROR if result.message else ValidationSeverity.WARNING
                entity_id = entity.uuid if hasattr(entity, 'uuid') else entity.get('uuid') if isinstance(entity, dict) else None
                
                report.add_issue(ValidationIssue(
                    phase=ValidationPhase.PRE_SAVE,
                    severity=severity,
                    message=result.message,
                    entity_id=entity_id,
                    suggested_fix="Review entity data and fix validation errors"
                ))
            
            elif result.should_skip:
                entity_id = entity.uuid if hasattr(entity, 'uuid') else entity.get('uuid') if isinstance(entity, dict) else None
                report.add_issue(ValidationIssue(
                    phase=ValidationPhase.PRE_SAVE,
                    severity=ValidationSeverity.INFO,
                    message=f"Entity will be skipped: {result.message}",
                    entity_id=entity_id
                ))
        
        phase_time = (datetime.now() - phase_start).total_seconds()
        report.performance_metrics['pre_save_time'] = phase_time
    
    async def _run_centrality_validation(self, 
                                       entities: List[Any], 
                                       report: ValidationReport, 
                                       context: Dict[str, Any]):
        """Run centrality validation."""
        
        phase_start = datetime.now()
        
        for entity in entities:
            entity_attrs = entity.__dict__ if hasattr(entity, '__dict__') else entity
            entity_id = entity.uuid if hasattr(entity, 'uuid') else entity.get('uuid') if isinstance(entity, dict) else None
            
            # Run centrality validation
            result = self.centrality_validator.validate_entity_centrality(entity_attrs)
            
            if not result.is_valid:
                severity = ValidationSeverity.ERROR if self.config.fail_on_centrality_errors else ValidationSeverity.WARNING
                
                for error in result.errors:
                    report.add_issue(ValidationIssue(
                        phase=ValidationPhase.CENTRALITY,
                        severity=severity,
                        message=error,
                        entity_id=entity_id,
                        suggested_fix="Recalculate centrality values or set to 0"
                    ))
        
        phase_time = (datetime.now() - phase_start).total_seconds()
        report.performance_metrics['centrality_time'] = phase_time
    
    async def _run_deduplication_analysis(self,
                                        entities: List[Any],
                                        report: ValidationReport,
                                        context: Dict[str, Any]):
        """Analyze entities for potential duplicates."""
        
        phase_start = datetime.now()
        
        if len(entities) < 2:
            return
        
        # Find potential duplicates using fuzzy matching
        duplicates_found = []
        
        for i, entity1 in enumerate(entities):
            for j, entity2 in enumerate(entities[i+1:], i+1):
                # Convert to dict format for fuzzy matching
                entity1_dict = entity1.__dict__ if hasattr(entity1, '__dict__') else entity1
                entity2_dict = entity2.__dict__ if hasattr(entity2, '__dict__') else entity2
                
                # Check if entities are potential duplicates
                if self.fuzzy_matcher.is_entity_match(entity1_dict, entity2_dict):
                    entity1_id = entity1.uuid if hasattr(entity1, 'uuid') else entity1.get('uuid') if isinstance(entity1, dict) else f"entity_{i}"
                    entity2_id = entity2.uuid if hasattr(entity2, 'uuid') else entity2.get('uuid') if isinstance(entity2, dict) else f"entity_{j}"
                    
                    duplicates_found.append((entity1_id, entity2_id))
                    
                    report.add_issue(ValidationIssue(
                        phase=ValidationPhase.DEDUPLICATION,
                        severity=ValidationSeverity.WARNING,
                        message=f"Potential duplicate entities detected",
                        entity_id=entity1_id,
                        suggested_fix=f"Review similarity with entity {entity2_id} and consider merging",
                        metadata={'duplicate_with': entity2_id}
                    ))
        
        phase_time = (datetime.now() - phase_start).total_seconds()
        report.performance_metrics['deduplication_time'] = phase_time
        report.performance_metrics['duplicates_found'] = len(duplicates_found)
    
    async def _run_pre_save_edge_validation(self,
                                          edges: List[Any],
                                          report: ValidationReport,
                                          context: Dict[str, Any]):
        """Run pre-save validation for edges."""
        
        phase_start = datetime.now()
        
        for edge in edges:
            # Run pre-save validation
            result = self.hook_service.validate_edge(edge, context)
            
            if not result.success:
                severity = ValidationSeverity.ERROR if result.message else ValidationSeverity.WARNING
                edge_id = edge.uuid if hasattr(edge, 'uuid') else edge.get('uuid') if isinstance(edge, dict) else None
                
                report.add_issue(ValidationIssue(
                    phase=ValidationPhase.PRE_SAVE,
                    severity=severity,
                    message=result.message,
                    entity_id=edge_id,
                    suggested_fix="Review edge data and fix validation errors"
                ))
        
        phase_time = (datetime.now() - phase_start).total_seconds()
        report.performance_metrics['pre_save_edge_time'] = phase_time
    
    async def _run_edge_integrity_validation(self,
                                           edges: List[Any],
                                           report: ValidationReport,
                                           context: Dict[str, Any]):
        """Run integrity checks specific to edges."""
        
        phase_start = datetime.now()
        
        for edge in edges:
            edge_id = edge.uuid if hasattr(edge, 'uuid') else edge.get('uuid') if isinstance(edge, dict) else None
            
            # Check required fields
            source_uuid = edge.source_node_uuid if hasattr(edge, 'source_node_uuid') else edge.get('source_node_uuid') if isinstance(edge, dict) else None
            target_uuid = edge.target_node_uuid if hasattr(edge, 'target_node_uuid') else edge.get('target_node_uuid') if isinstance(edge, dict) else None
            
            if not source_uuid:
                report.add_issue(ValidationIssue(
                    phase=ValidationPhase.INTEGRITY_CHECK,
                    severity=ValidationSeverity.ERROR,
                    message="Edge missing source node UUID",
                    entity_id=edge_id,
                    field_name="source_node_uuid",
                    suggested_fix="Provide valid source node UUID"
                ))
            
            if not target_uuid:
                report.add_issue(ValidationIssue(
                    phase=ValidationPhase.INTEGRITY_CHECK,
                    severity=ValidationSeverity.ERROR,
                    message="Edge missing target node UUID",
                    entity_id=edge_id,
                    field_name="target_node_uuid",
                    suggested_fix="Provide valid target node UUID"
                ))
            
            # Check for self-loops
            if source_uuid and target_uuid and source_uuid == target_uuid:
                report.add_issue(ValidationIssue(
                    phase=ValidationPhase.INTEGRITY_CHECK,
                    severity=ValidationSeverity.WARNING,
                    message="Edge creates self-loop",
                    entity_id=edge_id,
                    suggested_fix="Consider if self-loop is intentional"
                ))
        
        phase_time = (datetime.now() - phase_start).total_seconds()
        report.performance_metrics['edge_integrity_time'] = phase_time
    
    def _is_entity(self, obj: Any) -> bool:
        """Check if object is an entity."""
        return (isinstance(obj, EntityNode) or 
                (isinstance(obj, dict) and 'name' in obj and 'uuid' in obj and 'source_node_uuid' not in obj))
    
    def _is_edge(self, obj: Any) -> bool:
        """Check if object is an edge."""
        return (isinstance(obj, EntityEdge) or 
                (isinstance(obj, dict) and 'source_node_uuid' in obj and 'target_node_uuid' in obj))
    
    def _convert_integrity_severity(self, integrity_severity: str) -> ValidationSeverity:
        """Convert integrity check severity to validation severity."""
        if integrity_severity == "ERROR":
            return ValidationSeverity.ERROR
        elif integrity_severity == "WARNING":
            return ValidationSeverity.WARNING
        else:
            return ValidationSeverity.INFO
    
    def _log_validation_report(self, report: ValidationReport):
        """Log validation report for audit purposes."""
        
        if report.has_errors:
            self.logger.error(f"Validation report {report.operation_id}: {report.error_count} errors, {report.warning_count} warnings")
        elif report.warning_count > 0:
            self.logger.warning(f"Validation report {report.operation_id}: {report.warning_count} warnings")
        else:
            self.logger.info(f"Validation report {report.operation_id}: validation passed")
        
        # Log performance metrics
        if 'total_time' in report.performance_metrics:
            self.logger.debug(f"Validation performance: {report.performance_metrics}")
    
    def get_validation_summary(self, reports: List[ValidationReport]) -> Dict[str, Any]:
        """Generate summary statistics from multiple validation reports."""
        
        if not reports:
            return {}
        
        total_entities = sum(r.total_entities for r in reports)
        total_edges = sum(r.total_edges for r in reports)
        total_errors = sum(r.error_count for r in reports)
        total_warnings = sum(r.warning_count for r in reports)
        
        # Performance metrics
        total_time = sum(r.performance_metrics.get('total_time', 0) for r in reports)
        avg_entities_per_second = total_entities / total_time if total_time > 0 else 0
        
        # Issue categorization
        issues_by_phase = {}
        issues_by_severity = {}
        
        for report in reports:
            for issue in report.issues:
                phase_key = issue.phase.value
                severity_key = issue.severity.value
                
                issues_by_phase[phase_key] = issues_by_phase.get(phase_key, 0) + 1
                issues_by_severity[severity_key] = issues_by_severity.get(severity_key, 0) + 1
        
        return {
            'total_reports': len(reports),
            'total_entities': total_entities,
            'total_edges': total_edges,
            'total_errors': total_errors,
            'total_warnings': total_warnings,
            'total_time': total_time,
            'avg_entities_per_second': avg_entities_per_second,
            'issues_by_phase': issues_by_phase,
            'issues_by_severity': issues_by_severity
        }


# Global service instance
_validation_service: Optional[CentralizedValidationService] = None

def get_validation_service(driver: Optional[GraphDriver] = None, 
                          config: Optional[ValidationConfig] = None) -> CentralizedValidationService:
    """Get or create the centralized validation service."""
    global _validation_service
    
    if _validation_service is None:
        _validation_service = CentralizedValidationService(driver, config)
    elif driver and _validation_service.driver != driver:
        _validation_service.set_driver(driver)
    
    return _validation_service


# Convenience functions
async def validate_entities(entities: List[Union[EntityNode, dict]], 
                          driver: Optional[GraphDriver] = None,
                          config: Optional[ValidationConfig] = None,
                          context: Optional[Dict[str, Any]] = None) -> ValidationReport:
    """Validate a list of entities using the centralized service."""
    service = get_validation_service(driver, config)
    return await service.validate_entities_comprehensive(entities, context)


async def validate_edges(edges: List[Union[EntityEdge, dict]],
                        driver: Optional[GraphDriver] = None, 
                        config: Optional[ValidationConfig] = None,
                        context: Optional[Dict[str, Any]] = None) -> ValidationReport:
    """Validate a list of edges using the centralized service."""
    service = get_validation_service(driver, config)
    return await service.validate_edges_comprehensive(edges, context)


async def validate_post_save(entities: List[Union[EntityNode, EntityEdge, dict]],
                           driver: GraphDriver,
                           config: Optional[ValidationConfig] = None,
                           context: Optional[Dict[str, Any]] = None) -> ValidationReport:
    """Run post-save validation using the centralized service."""
    service = get_validation_service(driver, config)
    return await service.validate_post_save(entities, context)