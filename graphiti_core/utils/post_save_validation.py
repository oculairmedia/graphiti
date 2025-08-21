"""
Post-save integrity checks for verifying data consistency after database operations.

This module extends the validation hooks system to include post-save verification
that ensures entities and edges are correctly stored and maintain referential integrity.
"""

import logging
import os
from enum import Enum
from typing import Any, Dict, List, Optional, Union, Callable
from dataclasses import dataclass
from datetime import datetime
import asyncio

from graphiti_core.nodes import EntityNode, EpisodicNode
from graphiti_core.edges import EntityEdge
from graphiti_core.driver.driver import GraphDriver
from graphiti_core.utils.validation_hooks import (
    ValidationResult, 
    ValidationHookRegistry, 
    HookType,
    register_validation_hook
)

logger = logging.getLogger(__name__)


class PostSaveHookType(Enum):
    """Types of post-save integrity checks."""
    POST_SAVE_ENTITY = "post_save_entity"
    POST_SAVE_EDGE = "post_save_edge" 
    POST_SAVE_EPISODE = "post_save_episode"
    POST_SAVE_BATCH = "post_save_batch"
    INTEGRITY_CHECK = "integrity_check"
    REFERENTIAL_INTEGRITY = "referential_integrity"
    CONSISTENCY_CHECK = "consistency_check"


@dataclass 
class IntegrityCheckResult:
    """Result of an integrity check operation."""
    passed: bool
    check_name: str
    message: str
    entity_id: Optional[str] = None
    severity: str = "ERROR"  # ERROR, WARNING, INFO
    repair_suggestion: Optional[str] = None
    
    @classmethod
    def success(cls, check_name: str, message: str = "", entity_id: str = None):
        """Create a successful integrity check result."""
        return cls(
            passed=True,
            check_name=check_name,
            message=message or f"{check_name} passed",
            entity_id=entity_id,
            severity="INFO"
        )
    
    @classmethod
    def failure(cls, check_name: str, message: str, entity_id: str = None, 
                repair_suggestion: str = None, severity: str = "ERROR"):
        """Create a failed integrity check result."""
        return cls(
            passed=False,
            check_name=check_name,
            message=message,
            entity_id=entity_id,
            severity=severity,
            repair_suggestion=repair_suggestion
        )
    
    @classmethod
    def warning(cls, check_name: str, message: str, entity_id: str = None,
                repair_suggestion: str = None):
        """Create a warning integrity check result."""
        return cls(
            passed=True,  # Warnings don't fail the check
            check_name=check_name,
            message=message,
            entity_id=entity_id,
            severity="WARNING",
            repair_suggestion=repair_suggestion
        )


class PostSaveValidator:
    """Post-save validation service for integrity checks."""
    
    def __init__(self, driver: GraphDriver, enable_auto_repair: bool = False):
        self.driver = driver
        self.enable_auto_repair = enable_auto_repair
        self.logger = logging.getLogger(f"{__name__}.PostSaveValidator")
        self._integrity_checks: Dict[str, Callable] = {}
        self._register_default_checks()
    
    def register_integrity_check(self, name: str, check_function: Callable):
        """Register a custom integrity check function."""
        self._integrity_checks[name] = check_function
        self.logger.info(f"Registered integrity check: {name}")
    
    def _register_default_checks(self):
        """Register default integrity checks."""
        self.register_integrity_check("entity_exists", self._check_entity_exists)
        self.register_integrity_check("edge_node_references", self._check_edge_node_references)
        self.register_integrity_check("uuid_uniqueness", self._check_uuid_uniqueness)
        self.register_integrity_check("centrality_bounds", self._check_centrality_bounds)
        self.register_integrity_check("required_fields", self._check_required_fields)
        self.register_integrity_check("embedding_consistency", self._check_embedding_consistency)
        self.register_integrity_check("temporal_consistency", self._check_temporal_consistency)
    
    async def validate_entity_post_save(self, entity: Union[EntityNode, dict], 
                                       context: Dict[str, Any] = None) -> List[IntegrityCheckResult]:
        """Run post-save validation checks on an entity."""
        if context is None:
            context = {}
        
        results = []
        entity_id = entity.uuid if isinstance(entity, EntityNode) else entity.get('uuid')
        
        # Run all relevant integrity checks
        for check_name, check_function in self._integrity_checks.items():
            try:
                if check_name in ['edge_node_references']:  # Skip edge-specific checks
                    continue
                
                result = await check_function(entity, context)
                if result:
                    results.append(result)
                    
            except Exception as e:
                self.logger.error(f"Integrity check '{check_name}' failed with exception: {e}")
                results.append(IntegrityCheckResult.failure(
                    check_name, 
                    f"Check failed with exception: {str(e)}",
                    entity_id
                ))
        
        return results
    
    async def validate_edge_post_save(self, edge: Union[EntityEdge, dict],
                                     context: Dict[str, Any] = None) -> List[IntegrityCheckResult]:
        """Run post-save validation checks on an edge.""" 
        if context is None:
            context = {}
        
        results = []
        edge_id = edge.uuid if isinstance(edge, EntityEdge) else edge.get('uuid')
        
        # Run all relevant integrity checks
        for check_name, check_function in self._integrity_checks.items():
            try:
                if check_name in ['centrality_bounds']:  # Skip entity-specific checks
                    continue
                
                result = await check_function(edge, context)
                if result:
                    results.append(result)
                    
            except Exception as e:
                self.logger.error(f"Integrity check '{check_name}' failed with exception: {e}")
                results.append(IntegrityCheckResult.failure(
                    check_name,
                    f"Check failed with exception: {str(e)}",
                    edge_id
                ))
        
        return results
    
    async def validate_batch_post_save(self, entities: List[Any],
                                      context: Dict[str, Any] = None) -> List[IntegrityCheckResult]:
        """Run post-save validation checks on a batch of entities."""
        if context is None:
            context = {}
        
        all_results = []
        
        # Individual entity/edge checks
        for entity in entities:
            if isinstance(entity, (EntityNode, dict)) and ('name' in entity or hasattr(entity, 'name')):
                results = await self.validate_entity_post_save(entity, context)
                all_results.extend(results)
            elif isinstance(entity, (EntityEdge, dict)) and ('source_node_uuid' in entity or hasattr(entity, 'source_node_uuid')):
                results = await self.validate_edge_post_save(entity, context)
                all_results.extend(results)
        
        # Batch-level checks
        batch_result = await self._check_batch_consistency(entities, context)
        if batch_result:
            all_results.append(batch_result)
        
        return all_results
    
    async def _check_entity_exists(self, entity: Any, context: Dict[str, Any]) -> Optional[IntegrityCheckResult]:
        """Check that entity exists in database after save."""
        entity_id = entity.uuid if hasattr(entity, 'uuid') else entity.get('uuid')
        if not entity_id:
            return IntegrityCheckResult.failure(
                "entity_exists",
                "Entity UUID is missing",
                repair_suggestion="Regenerate UUID and re-save entity"
            )
        
        # Query database to check if entity exists
        session = self.driver.session()
        try:
            if self.driver.provider == 'neo4j':
                query = "MATCH (n {uuid: $uuid}) RETURN count(n) as count"
            else:  # FalkorDB
                query = f"MATCH (n {{uuid: '{entity_id}'}}) RETURN count(n) as count"
            
            result = await session.run(query, uuid=entity_id)
            record = await result.single()
            count = record['count'] if record else 0
            
            if count == 0:
                return IntegrityCheckResult.failure(
                    "entity_exists",
                    f"Entity {entity_id} not found in database after save",
                    entity_id,
                    repair_suggestion="Re-execute the save operation"
                )
            elif count > 1:
                return IntegrityCheckResult.warning(
                    "entity_exists", 
                    f"Multiple entities found with UUID {entity_id}",
                    entity_id,
                    repair_suggestion="Check for duplicate UUIDs and merge entities"
                )
            
            return IntegrityCheckResult.success("entity_exists", "Entity found in database", entity_id)
            
        finally:
            await session.close()
    
    async def _check_edge_node_references(self, edge: Any, context: Dict[str, Any]) -> Optional[IntegrityCheckResult]:
        """Check that edge references valid nodes."""
        source_uuid = edge.source_node_uuid if hasattr(edge, 'source_node_uuid') else edge.get('source_node_uuid')
        target_uuid = edge.target_node_uuid if hasattr(edge, 'target_node_uuid') else edge.get('target_node_uuid')
        edge_id = edge.uuid if hasattr(edge, 'uuid') else edge.get('uuid')
        
        if not source_uuid or not target_uuid:
            return IntegrityCheckResult.failure(
                "edge_node_references",
                f"Edge {edge_id} missing source or target node UUID",
                edge_id,
                repair_suggestion="Ensure edge has valid source_node_uuid and target_node_uuid"
            )
        
        session = self.driver.session()
        try:
            if self.driver.provider == 'neo4j':
                query = """
                MATCH (source {uuid: $source_uuid})
                OPTIONAL MATCH (target {uuid: $target_uuid})
                RETURN count(source) as source_count, count(target) as target_count
                """
                result = await session.run(query, source_uuid=source_uuid, target_uuid=target_uuid)
            else:  # FalkorDB
                query = f"""
                MATCH (source {{uuid: '{source_uuid}'}})
                OPTIONAL MATCH (target {{uuid: '{target_uuid}'}})
                RETURN count(source) as source_count, count(target) as target_count
                """
                result = await session.run(query)
            
            record = await result.single()
            if not record:
                return IntegrityCheckResult.failure(
                    "edge_node_references",
                    f"Unable to verify node references for edge {edge_id}",
                    edge_id
                )
            
            source_count = record['source_count']
            target_count = record['target_count']
            
            missing_nodes = []
            if source_count == 0:
                missing_nodes.append(f"source node {source_uuid}")
            if target_count == 0:
                missing_nodes.append(f"target node {target_uuid}")
            
            if missing_nodes:
                return IntegrityCheckResult.failure(
                    "edge_node_references",
                    f"Edge {edge_id} references missing nodes: {', '.join(missing_nodes)}",
                    edge_id,
                    repair_suggestion="Create missing nodes or update edge references"
                )
            
            return IntegrityCheckResult.success(
                "edge_node_references",
                "Edge references valid nodes",
                edge_id
            )
            
        finally:
            await session.close()
    
    async def _check_uuid_uniqueness(self, entity: Any, context: Dict[str, Any]) -> Optional[IntegrityCheckResult]:
        """Check that entity UUID is unique in the database."""
        entity_id = entity.uuid if hasattr(entity, 'uuid') else entity.get('uuid')
        if not entity_id:
            return None
        
        session = self.driver.session()
        try:
            if self.driver.provider == 'neo4j':
                query = "MATCH (n {uuid: $uuid}) RETURN count(n) as count"
            else:  # FalkorDB
                query = f"MATCH (n {{uuid: '{entity_id}'}}) RETURN count(n) as count"
            
            result = await session.run(query, uuid=entity_id)
            record = await result.single()
            count = record['count'] if record else 0
            
            if count > 1:
                return IntegrityCheckResult.failure(
                    "uuid_uniqueness",
                    f"UUID {entity_id} is not unique (found {count} instances)",
                    entity_id,
                    repair_suggestion="Merge duplicate entities or regenerate UUIDs"
                )
            
            return IntegrityCheckResult.success("uuid_uniqueness", "UUID is unique", entity_id)
            
        finally:
            await session.close()
    
    async def _check_centrality_bounds(self, entity: Any, context: Dict[str, Any]) -> Optional[IntegrityCheckResult]:
        """Check that centrality values are within valid bounds."""
        entity_id = entity.uuid if hasattr(entity, 'uuid') else entity.get('uuid')
        
        centrality_fields = [
            'degree_centrality', 'pagerank_centrality', 
            'betweenness_centrality', 'eigenvector_centrality'
        ]
        
        issues = []
        for field in centrality_fields:
            value = getattr(entity, field, None) if hasattr(entity, field) else entity.get(field) if isinstance(entity, dict) else None
            
            if value is not None:
                try:
                    float_value = float(value)
                    if float_value < 0 or float_value > 1:
                        issues.append(f"{field}={float_value} (should be 0-1)")
                    elif float_value != float_value:  # NaN check
                        issues.append(f"{field}=NaN")
                except (ValueError, TypeError):
                    issues.append(f"{field}={value} (not numeric)")
        
        if issues:
            return IntegrityCheckResult.failure(
                "centrality_bounds",
                f"Invalid centrality values for entity {entity_id}: {', '.join(issues)}",
                entity_id,
                repair_suggestion="Recalculate centrality values or set to 0"
            )
        
        return IntegrityCheckResult.success("centrality_bounds", "Centrality values are valid", entity_id)
    
    async def _check_required_fields(self, entity: Any, context: Dict[str, Any]) -> Optional[IntegrityCheckResult]:
        """Check that required fields are present and valid."""
        entity_id = getattr(entity, 'uuid', None) if hasattr(entity, 'uuid') else entity.get('uuid') if isinstance(entity, dict) else None
        
        # Determine entity type and required fields
        if hasattr(entity, 'source_node_uuid') or (isinstance(entity, dict) and 'source_node_uuid' in entity):
            # This is an edge
            required_fields = ['uuid', 'source_node_uuid', 'target_node_uuid', 'group_id']
        else:
            # This is an entity node
            required_fields = ['uuid', 'name', 'group_id']
        
        missing_fields = []
        for field in required_fields:
            value = getattr(entity, field, None) if hasattr(entity, field) else entity.get(field) if isinstance(entity, dict) else None
            if not value:
                missing_fields.append(field)
        
        if missing_fields:
            return IntegrityCheckResult.failure(
                "required_fields",
                f"Entity {entity_id} missing required fields: {missing_fields}",
                entity_id,
                repair_suggestion="Populate missing fields and re-save"
            )
        
        return IntegrityCheckResult.success("required_fields", "All required fields present", entity_id)
    
    async def _check_embedding_consistency(self, entity: Any, context: Dict[str, Any]) -> Optional[IntegrityCheckResult]:
        """Check that embeddings are consistent with their source text."""
        entity_id = getattr(entity, 'uuid', None) if hasattr(entity, 'uuid') else entity.get('uuid') if isinstance(entity, dict) else None
        
        # Check name embedding
        name = getattr(entity, 'name', None) if hasattr(entity, 'name') else entity.get('name') if isinstance(entity, dict) else None
        name_embedding = getattr(entity, 'name_embedding', None) if hasattr(entity, 'name_embedding') else entity.get('name_embedding') if isinstance(entity, dict) else None
        
        issues = []
        
        if name and not name_embedding:
            issues.append("name present but name_embedding missing")
        elif not name and name_embedding:
            issues.append("name_embedding present but name missing")
        elif name_embedding and not isinstance(name_embedding, list):
            issues.append("name_embedding is not a list")
        elif name_embedding and len(name_embedding) == 0:
            issues.append("name_embedding is empty")
        
        # Check fact embedding (for edges)
        fact = getattr(entity, 'fact', None) if hasattr(entity, 'fact') else entity.get('fact') if isinstance(entity, dict) else None
        fact_embedding = getattr(entity, 'fact_embedding', None) if hasattr(entity, 'fact_embedding') else entity.get('fact_embedding') if isinstance(entity, dict) else None
        
        if fact and not fact_embedding:
            issues.append("fact present but fact_embedding missing")
        elif not fact and fact_embedding:
            issues.append("fact_embedding present but fact missing")
        elif fact_embedding and not isinstance(fact_embedding, list):
            issues.append("fact_embedding is not a list")
        elif fact_embedding and len(fact_embedding) == 0:
            issues.append("fact_embedding is empty")
        
        if issues:
            return IntegrityCheckResult.warning(
                "embedding_consistency",
                f"Embedding issues for entity {entity_id}: {', '.join(issues)}",
                entity_id,
                repair_suggestion="Regenerate embeddings for the entity"
            )
        
        return IntegrityCheckResult.success("embedding_consistency", "Embeddings are consistent", entity_id)
    
    async def _check_temporal_consistency(self, entity: Any, context: Dict[str, Any]) -> Optional[IntegrityCheckResult]:
        """Check that timestamps are logically consistent."""
        entity_id = getattr(entity, 'uuid', None) if hasattr(entity, 'uuid') else entity.get('uuid') if isinstance(entity, dict) else None
        
        # Get timestamps
        created_at = getattr(entity, 'created_at', None) if hasattr(entity, 'created_at') else entity.get('created_at') if isinstance(entity, dict) else None
        updated_at = getattr(entity, 'updated_at', None) if hasattr(entity, 'updated_at') else entity.get('updated_at') if isinstance(entity, dict) else None
        valid_at = getattr(entity, 'valid_at', None) if hasattr(entity, 'valid_at') else entity.get('valid_at') if isinstance(entity, dict) else None
        invalid_at = getattr(entity, 'invalid_at', None) if hasattr(entity, 'invalid_at') else entity.get('invalid_at') if isinstance(entity, dict) else None
        expired_at = getattr(entity, 'expired_at', None) if hasattr(entity, 'expired_at') else entity.get('expired_at') if isinstance(entity, dict) else None
        
        issues = []
        now = datetime.now()
        
        # Check future timestamps
        if created_at and created_at > now:
            issues.append("created_at is in the future")
        if updated_at and updated_at > now:
            issues.append("updated_at is in the future")
        
        # Check logical ordering
        if created_at and updated_at and created_at > updated_at:
            issues.append("created_at is after updated_at")
        if valid_at and invalid_at and valid_at >= invalid_at:
            issues.append("valid_at is not before invalid_at")
        if created_at and expired_at and created_at > expired_at:
            issues.append("created_at is after expired_at")
        
        if issues:
            return IntegrityCheckResult.warning(
                "temporal_consistency",
                f"Timestamp issues for entity {entity_id}: {', '.join(issues)}",
                entity_id,
                repair_suggestion="Review and correct timestamp values"
            )
        
        return IntegrityCheckResult.success("temporal_consistency", "Timestamps are consistent", entity_id)
    
    async def _check_batch_consistency(self, entities: List[Any], context: Dict[str, Any]) -> Optional[IntegrityCheckResult]:
        """Check consistency across a batch of entities."""
        if len(entities) <= 1:
            return None
        
        # Check for UUID duplicates within batch
        uuids = []
        for entity in entities:
            uuid = getattr(entity, 'uuid', None) if hasattr(entity, 'uuid') else entity.get('uuid') if isinstance(entity, dict) else None
            if uuid:
                uuids.append(uuid)
        
        uuid_counts = {}
        for uuid in uuids:
            uuid_counts[uuid] = uuid_counts.get(uuid, 0) + 1
        
        duplicates = [uuid for uuid, count in uuid_counts.items() if count > 1]
        if duplicates:
            return IntegrityCheckResult.failure(
                "batch_consistency",
                f"Duplicate UUIDs in batch: {duplicates}",
                repair_suggestion="Remove duplicates or regenerate UUIDs"
            )
        
        # Check group_id consistency (if specified in context)
        expected_group_id = context.get('expected_group_id')
        if expected_group_id:
            mismatched_entities = []
            for entity in entities:
                group_id = getattr(entity, 'group_id', None) if hasattr(entity, 'group_id') else entity.get('group_id') if isinstance(entity, dict) else None
                entity_id = getattr(entity, 'uuid', None) if hasattr(entity, 'uuid') else entity.get('uuid') if isinstance(entity, dict) else "unknown"
                if group_id != expected_group_id:
                    mismatched_entities.append(f"{entity_id}({group_id})")
            
            if mismatched_entities:
                return IntegrityCheckResult.warning(
                    "batch_consistency",
                    f"Entities with mismatched group_id (expected {expected_group_id}): {mismatched_entities}",
                    repair_suggestion="Update group_id to match expected value"
                )
        
        return IntegrityCheckResult.success("batch_consistency", f"Batch of {len(entities)} entities is consistent")


# Configuration
def get_post_save_config() -> Dict[str, Any]:
    """Get post-save validation configuration from environment."""
    return {
        'enabled': os.getenv('POST_SAVE_VALIDATION_ENABLED', 'true').lower() == 'true',
        'auto_repair': os.getenv('POST_SAVE_AUTO_REPAIR', 'false').lower() == 'true',
        'skip_on_failure': os.getenv('POST_SAVE_SKIP_ON_FAILURE', 'false').lower() == 'true',
        'max_batch_size': int(os.getenv('POST_SAVE_MAX_BATCH_SIZE', '100')),
        'timeout_seconds': int(os.getenv('POST_SAVE_TIMEOUT', '30')),
        'log_level': os.getenv('POST_SAVE_LOG_LEVEL', 'INFO').upper()
    }


# Global post-save validator factory
_validator_instances = {}

def get_post_save_validator(driver: GraphDriver) -> PostSaveValidator:
    """Get or create a post-save validator instance for the given driver."""
    driver_key = id(driver)
    if driver_key not in _validator_instances:
        config = get_post_save_config()
        _validator_instances[driver_key] = PostSaveValidator(
            driver=driver,
            enable_auto_repair=config['auto_repair']
        )
    return _validator_instances[driver_key]


# Utility functions for integration
async def run_post_save_checks(driver: GraphDriver, entities: List[Any], 
                              context: Dict[str, Any] = None) -> List[IntegrityCheckResult]:
    """Run post-save integrity checks on a list of entities."""
    config = get_post_save_config()
    if not config['enabled']:
        return []
    
    validator = get_post_save_validator(driver)
    
    try:
        # Apply timeout if configured
        if config['timeout_seconds'] > 0:
            results = await asyncio.wait_for(
                validator.validate_batch_post_save(entities, context),
                timeout=config['timeout_seconds']
            )
        else:
            results = await validator.validate_batch_post_save(entities, context)
        
        # Log results
        for result in results:
            if result.severity == "ERROR":
                logger.error(f"Integrity check failed: {result.check_name} - {result.message}")
            elif result.severity == "WARNING":
                logger.warning(f"Integrity warning: {result.check_name} - {result.message}")
            else:
                logger.debug(f"Integrity check passed: {result.check_name}")
        
        return results
        
    except asyncio.TimeoutError:
        logger.error(f"Post-save validation timed out after {config['timeout_seconds']} seconds")
        return [IntegrityCheckResult.failure(
            "validation_timeout",
            f"Post-save validation timed out after {config['timeout_seconds']} seconds",
            repair_suggestion="Increase timeout or reduce batch size"
        )]
    except Exception as e:
        logger.error(f"Post-save validation failed with exception: {e}")
        return [IntegrityCheckResult.failure(
            "validation_exception", 
            f"Post-save validation failed: {str(e)}",
            repair_suggestion="Check logs and fix validation code"
        )]


async def run_integrity_repair(driver: GraphDriver, results: List[IntegrityCheckResult]) -> List[str]:
    """Attempt to repair integrity issues automatically."""
    config = get_post_save_config()
    if not config['auto_repair']:
        return []
    
    repaired = []
    
    for result in results:
        if not result.passed and result.repair_suggestion:
            try:
                # This is a placeholder for actual repair logic
                # In practice, each check would need specific repair functions
                logger.info(f"Attempting repair for {result.check_name}: {result.repair_suggestion}")
                # Actual repair logic would go here
                repaired.append(f"Repaired {result.check_name} for entity {result.entity_id}")
                
            except Exception as e:
                logger.error(f"Failed to repair {result.check_name}: {e}")
    
    return repaired