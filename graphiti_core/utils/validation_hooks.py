"""
Pre-save validation hooks for ensuring data integrity before database operations.

This module provides a hook system that allows validation and transformation
functions to be registered and executed before entities are saved to the database.
Hooks can validate data, transform it, or reject invalid operations entirely.
"""

import logging
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Protocol, TypeVar, Union
from dataclasses import dataclass
from datetime import datetime

from graphiti_core.nodes import EntityNode, EpisodicNode, CommunityNode
from graphiti_core.edges import EntityEdge

logger = logging.getLogger(__name__)

T = TypeVar('T')

class HookType(Enum):
    """Types of validation hooks that can be registered."""
    PRE_SAVE_ENTITY = "pre_save_entity"
    PRE_SAVE_EPISODE = "pre_save_episode" 
    PRE_SAVE_EDGE = "pre_save_edge"
    PRE_SAVE_COMMUNITY = "pre_save_community"
    PRE_BATCH_SAVE = "pre_batch_save"
    POST_VALIDATION = "post_validation"


class ValidationResult:
    """Result of a validation hook execution."""
    
    def __init__(self, success: bool = True, message: str = "", 
                 transformed_data: Any = None, should_skip: bool = False):
        self.success = success
        self.message = message
        self.transformed_data = transformed_data  # Modified data if transformation occurred
        self.should_skip = should_skip  # Skip saving this entity entirely
    
    @classmethod
    def success_with_data(cls, data: Any, message: str = ""):
        """Create a successful result with transformed data."""
        return cls(success=True, message=message, transformed_data=data)
    
    @classmethod
    def failure(cls, message: str):
        """Create a failed validation result."""
        return cls(success=False, message=message)
    
    @classmethod
    def skip(cls, message: str = "Entity skipped by validation hook"):
        """Create a result that skips saving this entity."""
        return cls(success=True, message=message, should_skip=True)


class ValidationHookProtocol(Protocol):
    """Protocol for validation hook functions."""
    
    def __call__(self, data: Any, context: Dict[str, Any] = None) -> ValidationResult:
        """
        Execute the validation hook.
        
        Args:
            data: The entity/edge data to validate
            context: Additional context (group_id, operation type, etc.)
            
        Returns:
            ValidationResult indicating success/failure and any transformations
        """
        ...


@dataclass
class HookRegistration:
    """Registration information for a validation hook."""
    hook_type: HookType
    priority: int
    name: str
    function: ValidationHookProtocol
    description: str
    enabled: bool = True


class ValidationHookRegistry:
    """Registry for managing validation hooks."""
    
    def __init__(self):
        self._hooks: Dict[HookType, List[HookRegistration]] = {
            hook_type: [] for hook_type in HookType
        }
        self.logger = logging.getLogger(f"{__name__}.ValidationHookRegistry")
    
    def register_hook(self, 
                     hook_type: HookType, 
                     function: ValidationHookProtocol,
                     name: str,
                     priority: int = 100,
                     description: str = "",
                     enabled: bool = True) -> None:
        """
        Register a validation hook.
        
        Args:
            hook_type: Type of hook to register
            function: The validation function
            name: Unique name for the hook
            priority: Priority (lower numbers execute first)
            description: Description of what the hook does
            enabled: Whether the hook is enabled
        """
        registration = HookRegistration(
            hook_type=hook_type,
            priority=priority,
            name=name,
            function=function,
            description=description,
            enabled=enabled
        )
        
        # Check if hook with same name already exists
        existing = [h for h in self._hooks[hook_type] if h.name == name]
        if existing:
            self.logger.warning(f"Hook '{name}' already registered for {hook_type.value}, replacing")
            self._hooks[hook_type] = [h for h in self._hooks[hook_type] if h.name != name]
        
        self._hooks[hook_type].append(registration)
        # Sort by priority (lower numbers first)
        self._hooks[hook_type].sort(key=lambda h: h.priority)
        
        self.logger.info(f"Registered validation hook '{name}' for {hook_type.value} (priority: {priority})")
    
    def unregister_hook(self, hook_type: HookType, name: str) -> bool:
        """
        Unregister a validation hook.
        
        Args:
            hook_type: Type of hook
            name: Name of hook to remove
            
        Returns:
            True if hook was found and removed
        """
        initial_count = len(self._hooks[hook_type])
        self._hooks[hook_type] = [h for h in self._hooks[hook_type] if h.name != name]
        removed = len(self._hooks[hook_type]) < initial_count
        
        if removed:
            self.logger.info(f"Unregistered validation hook '{name}' from {hook_type.value}")
        else:
            self.logger.warning(f"Hook '{name}' not found for {hook_type.value}")
        
        return removed
    
    def get_hooks(self, hook_type: HookType) -> List[HookRegistration]:
        """Get all registered hooks for a specific type."""
        return [h for h in self._hooks[hook_type] if h.enabled]
    
    def execute_hooks(self, hook_type: HookType, data: Any, 
                     context: Dict[str, Any] = None) -> ValidationResult:
        """
        Execute all hooks for a specific type.
        
        Args:
            hook_type: Type of hooks to execute
            data: Data to validate
            context: Additional context information
            
        Returns:
            Combined validation result
        """
        if context is None:
            context = {}
        
        hooks = self.get_hooks(hook_type)
        if not hooks:
            return ValidationResult.success_with_data(data)
        
        current_data = data
        combined_message = []
        
        for hook in hooks:
            try:
                self.logger.debug(f"Executing hook '{hook.name}' for {hook_type.value}")
                result = hook.function(current_data, context)
                
                if not result.success:
                    self.logger.error(f"Hook '{hook.name}' failed: {result.message}")
                    return ValidationResult.failure(
                        f"Validation failed at hook '{hook.name}': {result.message}"
                    )
                
                if result.should_skip:
                    self.logger.info(f"Hook '{hook.name}' requested skip: {result.message}")
                    return ValidationResult.skip(result.message)
                
                # Use transformed data if provided
                if result.transformed_data is not None:
                    current_data = result.transformed_data
                    self.logger.debug(f"Hook '{hook.name}' transformed data")
                
                if result.message:
                    combined_message.append(f"{hook.name}: {result.message}")
                
            except Exception as e:
                self.logger.error(f"Hook '{hook.name}' raised exception: {e}")
                return ValidationResult.failure(
                    f"Hook '{hook.name}' raised exception: {str(e)}"
                )
        
        message = "; ".join(combined_message) if combined_message else ""
        return ValidationResult.success_with_data(current_data, message)
    
    def list_hooks(self) -> Dict[str, List[Dict[str, Any]]]:
        """List all registered hooks."""
        result = {}
        for hook_type, hooks in self._hooks.items():
            result[hook_type.value] = [
                {
                    "name": h.name,
                    "priority": h.priority,
                    "description": h.description,
                    "enabled": h.enabled
                }
                for h in hooks
            ]
        return result


# Global registry instance
hook_registry = ValidationHookRegistry()


def register_validation_hook(hook_type: HookType, 
                           name: str, 
                           priority: int = 100,
                           description: str = "",
                           enabled: bool = True):
    """
    Decorator for registering validation hooks.
    
    Args:
        hook_type: Type of hook to register
        name: Unique name for the hook
        priority: Priority (lower numbers execute first)
        description: Description of what the hook does
        enabled: Whether the hook is enabled
        
    Example:
        @register_validation_hook(HookType.PRE_SAVE_ENTITY, "uuid_validator", priority=10)
        def validate_uuid(entity, context):
            if not entity.get('uuid'):
                return ValidationResult.failure("UUID is required")
            return ValidationResult.success_with_data(entity)
    """
    def decorator(func: ValidationHookProtocol):
        hook_registry.register_hook(
            hook_type=hook_type,
            function=func,
            name=name,
            priority=priority,
            description=description,
            enabled=enabled
        )
        return func
    return decorator


# Built-in validation hooks

@register_validation_hook(
    HookType.PRE_SAVE_ENTITY, 
    "entity_required_fields",
    priority=10,
    description="Validates that required fields are present for entities"
)
def validate_entity_required_fields(entity: Union[EntityNode, dict], 
                                   context: Dict[str, Any] = None) -> ValidationResult:
    """Validate that entity has required fields."""
    if isinstance(entity, EntityNode):
        # Pydantic validation already handled this
        return ValidationResult.success_with_data(entity)
    
    if isinstance(entity, dict):
        required_fields = ['uuid', 'name', 'group_id']
        missing_fields = [field for field in required_fields if not entity.get(field)]
        
        if missing_fields:
            return ValidationResult.failure(
                f"Entity missing required fields: {missing_fields}"
            )
    
    return ValidationResult.success_with_data(entity)


@register_validation_hook(
    HookType.PRE_SAVE_ENTITY,
    "entity_name_normalization", 
    priority=20,
    description="Normalizes entity names for consistency"
)
def normalize_entity_name(entity: Union[EntityNode, dict],
                         context: Dict[str, Any] = None) -> ValidationResult:
    """Normalize entity names for consistency."""
    if isinstance(entity, EntityNode):
        # Create a copy with normalized name
        normalized_name = entity.name.strip().title() if entity.name else entity.name
        if normalized_name != entity.name:
            # Create new instance with normalized name
            entity_dict = entity.dict()
            entity_dict['name'] = normalized_name
            return ValidationResult.success_with_data(
                entity_dict, 
                f"Normalized name from '{entity.name}' to '{normalized_name}'"
            )
    elif isinstance(entity, dict):
        name = entity.get('name', '')
        if name and isinstance(name, str):
            normalized_name = name.strip().title()
            if normalized_name != name:
                entity = entity.copy()
                entity['name'] = normalized_name
                return ValidationResult.success_with_data(
                    entity,
                    f"Normalized name from '{name}' to '{normalized_name}'"
                )
    
    return ValidationResult.success_with_data(entity)


@register_validation_hook(
    HookType.PRE_SAVE_ENTITY,
    "entity_duplicate_detection",
    priority=30, 
    description="Detects potential duplicate entities within the same batch"
)
def detect_entity_duplicates(entity: Union[EntityNode, dict],
                           context: Dict[str, Any] = None) -> ValidationResult:
    """Detect potential duplicate entities in batch operations."""
    if not context or 'batch_entities' not in context:
        return ValidationResult.success_with_data(entity)
    
    # Get entity identifiers
    if isinstance(entity, EntityNode):
        current_uuid = entity.uuid
        current_name = entity.name
        current_group = entity.group_id
    else:
        current_uuid = entity.get('uuid')
        current_name = entity.get('name')
        current_group = entity.get('group_id')
    
    # Check against other entities in batch
    batch_entities = context.get('batch_entities', [])
    current_index = context.get('current_entity_index')
    
    for i, other_entity in enumerate(batch_entities):
        if current_index is not None and i == current_index:  # Skip self by index
            continue
        
        if isinstance(other_entity, EntityNode):
            other_uuid = other_entity.uuid
            other_name = other_entity.name
            other_group = other_entity.group_id
        else:
            other_uuid = other_entity.get('uuid')
            other_name = other_entity.get('name')
            other_group = other_entity.get('group_id')
        
        # Check for UUID collision
        if current_uuid and current_uuid == other_uuid:
            return ValidationResult.failure(
                f"Duplicate UUID detected in batch: {current_uuid}"
            )
        
        # Check for name+group collision
        if (current_name and current_group and 
            current_name == other_name and current_group == other_group):
            return ValidationResult.skip(
                f"Duplicate entity detected (name: {current_name}, group: {current_group}), skipping"
            )
    
    return ValidationResult.success_with_data(entity)


@register_validation_hook(
    HookType.PRE_SAVE_EDGE,
    "edge_required_fields",
    priority=10,
    description="Validates that required fields are present for edges"
)
def validate_edge_required_fields(edge: Union[EntityEdge, dict],
                                context: Dict[str, Any] = None) -> ValidationResult:
    """Validate that edge has required fields."""
    if isinstance(edge, EntityEdge):
        return ValidationResult.success_with_data(edge)
    
    if isinstance(edge, dict):
        required_fields = ['uuid', 'source_node_uuid', 'target_node_uuid', 'group_id']
        missing_fields = [field for field in required_fields if not edge.get(field)]
        
        if missing_fields:
            return ValidationResult.failure(
                f"Edge missing required fields: {missing_fields}"
            )
    
    return ValidationResult.success_with_data(edge)


@register_validation_hook(
    HookType.POST_VALIDATION,
    "validation_audit_log",
    priority=1000,  # Run last
    description="Logs validation results for audit purposes"
)
def audit_validation_results(data: Any, context: Dict[str, Any] = None) -> ValidationResult:
    """Log validation results for audit purposes."""
    if context and context.get('audit_enabled', False):
        operation_type = context.get('operation_type', 'unknown')
        entity_count = 1
        if isinstance(data, list):
            entity_count = len(data)
        
        logger.info(f"Validation audit: {operation_type} operation with {entity_count} entities")
    
    return ValidationResult.success_with_data(data)


class ValidationService:
    """High-level service for executing validation hooks."""
    
    def __init__(self, registry: ValidationHookRegistry = None):
        self.registry = registry or hook_registry
        self.logger = logging.getLogger(f"{__name__}.ValidationService")
    
    def validate_entity(self, entity: Union[EntityNode, dict], 
                       context: Dict[str, Any] = None) -> ValidationResult:
        """Validate an entity using registered hooks."""
        return self.registry.execute_hooks(HookType.PRE_SAVE_ENTITY, entity, context)
    
    def validate_edge(self, edge: Union[EntityEdge, dict],
                     context: Dict[str, Any] = None) -> ValidationResult:
        """Validate an edge using registered hooks.""" 
        return self.registry.execute_hooks(HookType.PRE_SAVE_EDGE, edge, context)
    
    def validate_episode(self, episode: Union[EpisodicNode, dict],
                        context: Dict[str, Any] = None) -> ValidationResult:
        """Validate an episode using registered hooks."""
        return self.registry.execute_hooks(HookType.PRE_SAVE_EPISODE, episode, context)
    
    def validate_batch(self, entities: List[Any],
                      context: Dict[str, Any] = None) -> ValidationResult:
        """Validate a batch of entities using registered hooks."""
        if context is None:
            context = {}
        
        # Add batch context
        context['batch_entities'] = entities
        context['operation_type'] = 'batch_save'
        
        # First run batch-level validation
        batch_result = self.registry.execute_hooks(HookType.PRE_BATCH_SAVE, entities, context)
        if not batch_result.success:
            return batch_result
        
        # Then validate each entity individually
        validated_entities = []
        for i, entity in enumerate(entities):
            # Add current entity index to context for duplicate detection
            entity_context = context.copy()
            entity_context['current_entity_index'] = i
            
            if isinstance(entity, EntityNode) or (isinstance(entity, dict) and 'name' in entity):
                result = self.validate_entity(entity, entity_context)
            elif isinstance(entity, EntityEdge) or (isinstance(entity, dict) and 'source_node_uuid' in entity):
                result = self.validate_edge(entity, entity_context)
            elif isinstance(entity, EpisodicNode) or (isinstance(entity, dict) and 'content' in entity):
                result = self.validate_episode(entity, entity_context)
            else:
                result = ValidationResult.success_with_data(entity)
            
            if not result.success:
                return result
            
            if not result.should_skip:
                validated_entities.append(result.transformed_data or entity)
        
        # Run post-validation hooks
        final_result = self.registry.execute_hooks(HookType.POST_VALIDATION, validated_entities, context)
        return final_result


# Global validation service instance
validation_service = ValidationService()