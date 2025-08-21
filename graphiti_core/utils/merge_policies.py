"""
Configurable merge policies for entity deduplication.

This module provides configurable policies for merging duplicate entities,
allowing fine-tuned control over how entity data is combined and preserved.
"""

import os
import logging
from enum import Enum
from typing import Dict, List, Optional, Any, Callable, Union
from dataclasses import dataclass
from datetime import datetime
import json

logger = logging.getLogger(__name__)


class MergeStrategy(Enum):
    """Strategy for merging duplicate entities"""
    PRESERVE_OLDEST = "preserve_oldest"       # Keep data from oldest entity
    PRESERVE_NEWEST = "preserve_newest"       # Keep data from newest entity
    PRESERVE_MOST_COMPLETE = "preserve_most_complete"  # Keep entity with most attributes
    PRESERVE_HIGHEST_CENTRALITY = "preserve_highest_centrality"  # Keep entity with highest centrality scores
    AGGREGATE_ALL = "aggregate_all"           # Combine data from all duplicates
    CUSTOM = "custom"                         # Use custom merge function


class ConflictResolution(Enum):
    """Strategy for resolving field conflicts"""
    FIRST_WINS = "first_wins"                 # Use value from first entity
    LAST_WINS = "last_wins"                   # Use value from last entity
    LONGEST_WINS = "longest_wins"             # Use longest string value
    NUMERIC_MAX = "numeric_max"               # Use maximum numeric value
    NUMERIC_MIN = "numeric_min"               # Use minimum numeric value
    NUMERIC_AVERAGE = "numeric_average"       # Average numeric values
    CONCATENATE = "concatenate"               # Concatenate string values
    LIST_UNION = "list_union"                 # Union of list values
    CUSTOM = "custom"                         # Use custom resolution function


class FieldMergeMode(Enum):
    """Mode for merging specific fields"""
    OVERWRITE = "overwrite"                   # Replace field completely
    MERGE = "merge"                           # Merge field values
    PRESERVE = "preserve"                     # Keep original value unchanged
    SKIP = "skip"                             # Don't merge this field


@dataclass
class FieldMergeRule:
    """Rule for merging a specific field"""
    field_name: str
    mode: FieldMergeMode
    conflict_resolution: ConflictResolution
    custom_function: Optional[Callable] = None
    priority_weight: float = 1.0
    preserve_history: bool = False


@dataclass
class MergePolicyConfig:
    """Configuration for merge policies"""
    
    # Primary merge strategy
    strategy: MergeStrategy = MergeStrategy.PRESERVE_MOST_COMPLETE
    
    # Default conflict resolution
    default_conflict_resolution: ConflictResolution = ConflictResolution.FIRST_WINS
    
    # Field-specific merge rules
    field_rules: Dict[str, FieldMergeRule] = None
    
    # Entity selection criteria
    preserve_entity_with_most_edges: bool = True
    preserve_entity_with_highest_degree: bool = True
    preserve_entity_with_longest_summary: bool = True
    
    # Centrality preference weights
    centrality_weights: Dict[str, float] = None
    
    # Attribute merging options
    merge_labels: bool = True
    merge_attributes: bool = True
    preserve_timestamps: bool = True
    
    # History tracking
    track_merge_history: bool = True
    max_history_entries: int = 10
    
    # Validation options
    validate_merged_entity: bool = True
    require_manual_review: bool = False
    
    def __post_init__(self):
        if self.field_rules is None:
            self.field_rules = self._create_default_field_rules()
        
        if self.centrality_weights is None:
            self.centrality_weights = {
                'degree_centrality': 0.3,
                'pagerank_centrality': 0.3,
                'betweenness_centrality': 0.2,
                'eigenvector_centrality': 0.2
            }
    
    def _create_default_field_rules(self) -> Dict[str, FieldMergeRule]:
        """Create default field merge rules"""
        return {
            'uuid': FieldMergeRule('uuid', FieldMergeMode.PRESERVE, ConflictResolution.FIRST_WINS),
            'name': FieldMergeRule('name', FieldMergeMode.MERGE, ConflictResolution.LONGEST_WINS, preserve_history=True),
            'summary': FieldMergeRule('summary', FieldMergeMode.MERGE, ConflictResolution.LONGEST_WINS),
            'labels': FieldMergeRule('labels', FieldMergeMode.MERGE, ConflictResolution.LIST_UNION),
            'group_id': FieldMergeRule('group_id', FieldMergeMode.PRESERVE, ConflictResolution.FIRST_WINS),
            'created_at': FieldMergeRule('created_at', FieldMergeMode.PRESERVE, ConflictResolution.NUMERIC_MIN),
            'updated_at': FieldMergeRule('updated_at', FieldMergeMode.OVERWRITE, ConflictResolution.NUMERIC_MAX),
            'name_embedding': FieldMergeRule('name_embedding', FieldMergeMode.MERGE, ConflictResolution.LONGEST_WINS),
            
            # Centrality fields
            'degree_centrality': FieldMergeRule('degree_centrality', FieldMergeMode.MERGE, ConflictResolution.NUMERIC_MAX),
            'pagerank_centrality': FieldMergeRule('pagerank_centrality', FieldMergeMode.MERGE, ConflictResolution.NUMERIC_MAX),
            'betweenness_centrality': FieldMergeRule('betweenness_centrality', FieldMergeMode.MERGE, ConflictResolution.NUMERIC_MAX),
            'eigenvector_centrality': FieldMergeRule('eigenvector_centrality', FieldMergeMode.MERGE, ConflictResolution.NUMERIC_MAX),
            'importance_score': FieldMergeRule('importance_score', FieldMergeMode.MERGE, ConflictResolution.NUMERIC_MAX),
        }
    
    @classmethod
    def from_environment(cls) -> 'MergePolicyConfig':
        """Load configuration from environment variables"""
        
        def get_enum_env(key: str, enum_class: type, default):
            try:
                value = os.getenv(key, default.value if default else '').lower()
                return enum_class(value)
            except ValueError:
                logger.warning(f"Invalid {enum_class.__name__} value for {key}: {value}, using default")
                return default
        
        def get_bool_env(key: str, default: bool) -> bool:
            return os.getenv(key, str(default)).lower() in ('true', '1', 'yes', 'on')
        
        def get_int_env(key: str, default: int) -> int:
            try:
                return int(os.getenv(key, str(default)))
            except ValueError:
                logger.warning(f"Invalid int value for {key}, using default: {default}")
                return default
        
        def get_float_env(key: str, default: float) -> float:
            try:
                return float(os.getenv(key, str(default)))
            except ValueError:
                logger.warning(f"Invalid float value for {key}, using default: {default}")
                return default
        
        # Load centrality weights from environment
        centrality_weights = {}
        for centrality_type in ['degree', 'pagerank', 'betweenness', 'eigenvector']:
            key = f"MERGE_CENTRALITY_WEIGHT_{centrality_type.upper()}"
            default_weight = 0.25  # Default equal weights
            centrality_weights[f"{centrality_type}_centrality"] = get_float_env(key, default_weight)
        
        return cls(
            strategy=get_enum_env('MERGE_STRATEGY', MergeStrategy, MergeStrategy.PRESERVE_MOST_COMPLETE),
            default_conflict_resolution=get_enum_env('MERGE_DEFAULT_CONFLICT_RESOLUTION', ConflictResolution, ConflictResolution.FIRST_WINS),
            preserve_entity_with_most_edges=get_bool_env('MERGE_PRESERVE_MOST_EDGES', True),
            preserve_entity_with_highest_degree=get_bool_env('MERGE_PRESERVE_HIGHEST_DEGREE', True),
            preserve_entity_with_longest_summary=get_bool_env('MERGE_PRESERVE_LONGEST_SUMMARY', True),
            centrality_weights=centrality_weights,
            merge_labels=get_bool_env('MERGE_LABELS', True),
            merge_attributes=get_bool_env('MERGE_ATTRIBUTES', True),
            preserve_timestamps=get_bool_env('MERGE_PRESERVE_TIMESTAMPS', True),
            track_merge_history=get_bool_env('MERGE_TRACK_HISTORY', True),
            max_history_entries=get_int_env('MERGE_MAX_HISTORY', 10),
            validate_merged_entity=get_bool_env('MERGE_VALIDATE_RESULT', True),
            require_manual_review=get_bool_env('MERGE_REQUIRE_MANUAL_REVIEW', False)
        )


class EntityMerger:
    """Entity merger with configurable policies"""
    
    def __init__(self, config: Optional[MergePolicyConfig] = None):
        self.config = config or MergePolicyConfig.from_environment()
        logger.info(f"Initialized EntityMerger with strategy: {self.config.strategy}")
    
    def merge_entities(self, entities: List[Dict[str, Any]], metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Merge multiple entities into a single entity"""
        
        if not entities:
            raise ValueError("Cannot merge empty entity list")
        
        if len(entities) == 1:
            return entities[0]
        
        # Select primary entity based on strategy
        primary_entity = self._select_primary_entity(entities, metadata)
        
        # Merge data from all entities into the primary entity
        merged_entity = self._merge_entity_data(primary_entity, entities, metadata)
        
        # Add merge history if enabled
        if self.config.track_merge_history:
            merged_entity = self._add_merge_history(merged_entity, entities)
        
        # Validate merged entity if enabled
        if self.config.validate_merged_entity:
            self._validate_merged_entity(merged_entity)
        
        return merged_entity
    
    def _select_primary_entity(self, entities: List[Dict[str, Any]], metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Select the primary entity based on configured strategy"""
        
        if self.config.strategy == MergeStrategy.PRESERVE_OLDEST:
            return min(entities, key=lambda e: e.get('created_at', datetime.now()))
        
        elif self.config.strategy == MergeStrategy.PRESERVE_NEWEST:
            return max(entities, key=lambda e: e.get('created_at', datetime.min))
        
        elif self.config.strategy == MergeStrategy.PRESERVE_MOST_COMPLETE:
            return max(entities, key=lambda e: self._calculate_completeness_score(e))
        
        elif self.config.strategy == MergeStrategy.PRESERVE_HIGHEST_CENTRALITY:
            return max(entities, key=lambda e: self._calculate_centrality_score(e))
        
        elif self.config.strategy == MergeStrategy.AGGREGATE_ALL:
            # For aggregation, use the first entity as base
            return entities[0]
        
        else:  # Default to first entity
            return entities[0]
    
    def _calculate_completeness_score(self, entity: Dict[str, Any]) -> float:
        """Calculate how complete an entity is"""
        score = 0.0
        
        # Basic completeness
        if entity.get('name'): score += 1.0
        if entity.get('summary'): score += 2.0 * len(str(entity.get('summary', ''))) / 100
        if entity.get('labels'): score += 0.5 * len(entity.get('labels', []))
        if entity.get('name_embedding'): score += 1.0
        
        # Centrality completeness
        centrality_fields = ['degree_centrality', 'pagerank_centrality', 'betweenness_centrality', 'eigenvector_centrality']
        for field in centrality_fields:
            if entity.get(field) is not None and entity.get(field) > 0:
                score += 0.5
        
        # Custom attributes
        attributes = entity.get('attributes', {})
        if isinstance(attributes, dict):
            score += 0.1 * len(attributes)
        
        # Connection information (if available in metadata)
        edge_count = entity.get('edge_count', 0)
        if edge_count > 0:
            score += min(2.0, edge_count / 10.0)  # Up to 2 points for connectivity
        
        return score
    
    def _calculate_centrality_score(self, entity: Dict[str, Any]) -> float:
        """Calculate weighted centrality score"""
        score = 0.0
        
        for centrality_field, weight in self.config.centrality_weights.items():
            value = entity.get(centrality_field, 0.0)
            if isinstance(value, (int, float)) and value > 0:
                score += weight * value
        
        return score
    
    def _merge_entity_data(self, primary_entity: Dict[str, Any], all_entities: List[Dict[str, Any]], metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Merge data from all entities into the primary entity"""
        
        merged = primary_entity.copy()
        
        # Process each field according to its merge rule
        for field_name, rule in self.config.field_rules.items():
            if rule.mode == FieldMergeMode.PRESERVE:
                # Keep primary entity's value
                continue
            elif rule.mode == FieldMergeMode.SKIP:
                # Don't process this field
                continue
            elif rule.mode in [FieldMergeMode.OVERWRITE, FieldMergeMode.MERGE]:
                # Collect values from all entities
                values = []
                for entity in all_entities:
                    if field_name in entity and entity[field_name] is not None:
                        values.append(entity[field_name])
                
                if values:
                    merged_value = self._resolve_field_conflict(values, rule.conflict_resolution, rule.custom_function)
                    if merged_value is not None:
                        merged[field_name] = merged_value
        
        # Handle attributes separately if merging is enabled
        if self.config.merge_attributes:
            merged_attributes = {}
            for entity in all_entities:
                attributes = entity.get('attributes', {})
                if isinstance(attributes, dict):
                    merged_attributes.update(attributes)
            if merged_attributes:
                merged['attributes'] = merged_attributes
        
        # Handle labels separately if merging is enabled
        if self.config.merge_labels:
            all_labels = set()
            for entity in all_entities:
                labels = entity.get('labels', [])
                if isinstance(labels, list):
                    all_labels.update(labels)
            if all_labels:
                merged['labels'] = list(all_labels)
        
        # Update timestamp to now
        merged['updated_at'] = datetime.now()
        
        return merged
    
    def _resolve_field_conflict(self, values: List[Any], resolution: ConflictResolution, custom_function: Optional[Callable] = None) -> Any:
        """Resolve conflicts between field values"""
        
        if not values:
            return None
        
        if len(values) == 1:
            return values[0]
        
        if resolution == ConflictResolution.FIRST_WINS:
            return values[0]
        
        elif resolution == ConflictResolution.LAST_WINS:
            return values[-1]
        
        elif resolution == ConflictResolution.LONGEST_WINS:
            return max(values, key=lambda v: len(str(v)) if v is not None else 0)
        
        elif resolution == ConflictResolution.NUMERIC_MAX:
            numeric_values = [v for v in values if isinstance(v, (int, float)) and v is not None]
            return max(numeric_values) if numeric_values else values[0]
        
        elif resolution == ConflictResolution.NUMERIC_MIN:
            numeric_values = [v for v in values if isinstance(v, (int, float)) and v is not None]
            return min(numeric_values) if numeric_values else values[0]
        
        elif resolution == ConflictResolution.NUMERIC_AVERAGE:
            numeric_values = [v for v in values if isinstance(v, (int, float)) and v is not None]
            return sum(numeric_values) / len(numeric_values) if numeric_values else values[0]
        
        elif resolution == ConflictResolution.CONCATENATE:
            string_values = [str(v) for v in values if v is not None]
            return ' | '.join(string_values) if string_values else None
        
        elif resolution == ConflictResolution.LIST_UNION:
            all_items = set()
            for value in values:
                if isinstance(value, list):
                    all_items.update(value)
                elif value is not None:
                    all_items.add(value)
            return list(all_items)
        
        elif resolution == ConflictResolution.CUSTOM and custom_function:
            return custom_function(values)
        
        else:
            # Default to first value
            return values[0]
    
    def _add_merge_history(self, merged_entity: Dict[str, Any], source_entities: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Add merge history to the entity"""
        
        merge_history = merged_entity.get('merge_history', [])
        
        # Create new merge record
        merge_record = {
            'timestamp': datetime.now().isoformat(),
            'merged_entity_uuids': [e.get('uuid') for e in source_entities if e.get('uuid')],
            'merge_strategy': self.config.strategy.value,
            'entity_count': len(source_entities)
        }
        
        merge_history.append(merge_record)
        
        # Limit history entries
        if len(merge_history) > self.config.max_history_entries:
            merge_history = merge_history[-self.config.max_history_entries:]
        
        merged_entity['merge_history'] = merge_history
        return merged_entity
    
    def _validate_merged_entity(self, merged_entity: Dict[str, Any]):
        """Validate the merged entity"""
        
        # Basic validation
        if not merged_entity.get('uuid'):
            raise ValueError("Merged entity must have a UUID")
        
        if not merged_entity.get('name'):
            raise ValueError("Merged entity must have a name")
        
        # Centrality validation (if centrality validation is available)
        try:
            from graphiti_core.utils.centrality_validation import validate_entity_centrality
            result = validate_entity_centrality(merged_entity, auto_correct=True)
            if not result.is_valid:
                logger.warning(f"Merged entity failed centrality validation: {result.errors}")
                if result.corrected_values:
                    merged_entity.update(result.corrected_values)
        except ImportError:
            pass  # Centrality validation not available
    
    def merge_with_conflict_report(self, entities: List[Dict[str, Any]], metadata: Optional[Dict[str, Any]] = None) -> tuple[Dict[str, Any], Dict[str, List[str]]]:
        """Merge entities and return conflict report"""
        
        conflicts = {}
        
        # Track conflicts during merge
        if len(entities) > 1:
            for field_name in self.config.field_rules.keys():
                values = [e.get(field_name) for e in entities if e.get(field_name) is not None]
                unique_values = list(set(str(v) for v in values))
                if len(unique_values) > 1:
                    conflicts[field_name] = unique_values
        
        merged_entity = self.merge_entities(entities, metadata)
        
        return merged_entity, conflicts
    
    def can_auto_merge(self, entities: List[Dict[str, Any]]) -> bool:
        """Determine if entities can be automatically merged"""
        
        if self.config.require_manual_review:
            return False
        
        # Check for high-conflict scenarios
        if len(entities) > 5:  # Too many duplicates
            return False
        
        # Check for conflicting critical fields
        critical_fields = ['name', 'group_id']
        for field in critical_fields:
            values = [e.get(field) for e in entities if e.get(field) is not None]
            unique_values = list(set(str(v) for v in values))
            if len(unique_values) > 2:  # Too many different values
                return False
        
        return True
    
    def get_merge_preview(self, entities: List[Dict[str, Any]], metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Get a preview of what the merge would produce without actually merging"""
        
        primary_entity = self._select_primary_entity(entities, metadata)
        completeness_scores = [self._calculate_completeness_score(e) for e in entities]
        centrality_scores = [self._calculate_centrality_score(e) for e in entities]
        
        return {
            'primary_entity_uuid': primary_entity.get('uuid'),
            'primary_entity_name': primary_entity.get('name'),
            'total_entities': len(entities),
            'merge_strategy': self.config.strategy.value,
            'completeness_scores': completeness_scores,
            'centrality_scores': centrality_scores,
            'can_auto_merge': self.can_auto_merge(entities),
            'estimated_conflicts': self._estimate_conflicts(entities)
        }
    
    def _estimate_conflicts(self, entities: List[Dict[str, Any]]) -> int:
        """Estimate number of field conflicts"""
        
        conflicts = 0
        for field_name in self.config.field_rules.keys():
            values = [e.get(field_name) for e in entities if e.get(field_name) is not None]
            unique_values = list(set(str(v) for v in values))
            if len(unique_values) > 1:
                conflicts += 1
        
        return conflicts


# Global merger instance
default_merger = EntityMerger()


def get_entity_merger(config: Optional[MergePolicyConfig] = None) -> EntityMerger:
    """Get an entity merger instance"""
    if config:
        return EntityMerger(config)
    return default_merger


def merge_duplicate_entities(entities: List[Dict[str, Any]], metadata: Optional[Dict[str, Any]] = None, config: Optional[MergePolicyConfig] = None) -> Dict[str, Any]:
    """Convenience function to merge duplicate entities"""
    merger = get_entity_merger(config)
    return merger.merge_entities(entities, metadata)


def create_merge_policy_from_strategy(strategy: str) -> MergePolicyConfig:
    """Create a merge policy configuration from a strategy name"""
    
    try:
        strategy_enum = MergeStrategy(strategy.lower())
    except ValueError:
        strategy_enum = MergeStrategy.PRESERVE_MOST_COMPLETE
    
    config = MergePolicyConfig(strategy=strategy_enum)
    
    # Adjust other settings based on strategy
    if strategy_enum == MergeStrategy.PRESERVE_OLDEST:
        config.preserve_timestamps = True
        config.default_conflict_resolution = ConflictResolution.FIRST_WINS
    elif strategy_enum == MergeStrategy.PRESERVE_NEWEST:
        config.default_conflict_resolution = ConflictResolution.LAST_WINS
    elif strategy_enum == MergeStrategy.AGGREGATE_ALL:
        config.merge_labels = True
        config.merge_attributes = True
        config.default_conflict_resolution = ConflictResolution.CONCATENATE
    
    return config