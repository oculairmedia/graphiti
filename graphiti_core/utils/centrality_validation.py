"""
Centrality validation module for ensuring centrality metrics remain within valid ranges.

This module provides validation, normalization, and correction functions for graph
centrality metrics including PageRank, degree centrality, betweenness centrality,
and eigenvector centrality scores.
"""

import logging
import math
from typing import Dict, List, Optional, Tuple, Union
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class CentralityType(Enum):
    """Types of centrality metrics supported."""
    PAGERANK = "pagerank_centrality"
    DEGREE = "degree_centrality" 
    BETWEENNESS = "betweenness_centrality"
    EIGENVECTOR = "eigenvector_centrality"
    IMPORTANCE_SCORE = "importance_score"


@dataclass
class CentralityBounds:
    """Defines valid bounds for centrality metrics."""
    min_value: float
    max_value: float
    default_value: float
    
    def is_valid(self, value: Union[int, float]) -> bool:
        """Check if a value is within valid bounds."""
        if not isinstance(value, (int, float)):
            return False
        return self.min_value <= value <= self.max_value
    
    def clamp(self, value: Union[int, float]) -> float:
        """Clamp a value to valid bounds."""
        if not isinstance(value, (int, float)):
            return self.default_value
        return max(self.min_value, min(self.max_value, float(value)))


# Standard bounds for different centrality metrics
CENTRALITY_BOUNDS = {
    CentralityType.PAGERANK: CentralityBounds(0.0, 1.0, 0.0),
    CentralityType.DEGREE: CentralityBounds(0.0, 1.0, 0.0), 
    CentralityType.BETWEENNESS: CentralityBounds(0.0, 1.0, 0.0),
    CentralityType.EIGENVECTOR: CentralityBounds(0.0, 1.0, 0.0),
    CentralityType.IMPORTANCE_SCORE: CentralityBounds(0.0, 1.0, 0.0),
}


class CentralityValidationError(Exception):
    """Raised when centrality validation fails."""
    pass


@dataclass
class CentralityValidationResult:
    """Result of centrality validation."""
    is_valid: bool
    corrected_values: Dict[str, float]
    errors: List[str]
    warnings: List[str]
    
    @classmethod
    def success(cls, corrected_values: Dict[str, float] = None, warnings: List[str] = None):
        """Create a successful validation result."""
        return cls(
            is_valid=True,
            corrected_values=corrected_values or {},
            errors=[],
            warnings=warnings or []
        )
    
    @classmethod 
    def failure(cls, errors: List[str], corrected_values: Dict[str, float] = None):
        """Create a failed validation result."""
        return cls(
            is_valid=False,
            corrected_values=corrected_values or {},
            errors=errors,
            warnings=[]
        )


class CentralityValidator:
    """Validator for centrality metrics with configurable bounds and correction strategies."""
    
    def __init__(self, bounds: Dict[CentralityType, CentralityBounds] = None):
        self.bounds = bounds or CENTRALITY_BOUNDS.copy()
        self.logger = logging.getLogger(f"{__name__}.CentralityValidator")
    
    def validate_single_metric(self, 
                              centrality_type: CentralityType,
                              value: Union[int, float],
                              auto_correct: bool = False) -> Tuple[bool, float, List[str]]:
        """
        Validate a single centrality metric.
        
        Args:
            centrality_type: Type of centrality metric
            value: The value to validate
            auto_correct: Whether to auto-correct invalid values
            
        Returns:
            Tuple of (is_valid, corrected_value, error_messages)
        """
        bounds = self.bounds.get(centrality_type)
        if not bounds:
            return False, 0.0, [f"Unknown centrality type: {centrality_type}"]
        
        errors = []
        
        # Check if value is numeric
        if not isinstance(value, (int, float)):
            error_msg = f"{centrality_type.value} must be numeric, got {type(value).__name__}"
            errors.append(error_msg)
            return False, bounds.default_value, errors
        
        # Check for NaN or infinity
        if math.isnan(value) or math.isinf(value):
            error_msg = f"{centrality_type.value} cannot be NaN or infinite"
            errors.append(error_msg)
            corrected_value = bounds.default_value if auto_correct else value
            return auto_correct, corrected_value, errors
        
        # Check bounds
        if not bounds.is_valid(value):
            error_msg = f"{centrality_type.value} {value} is outside valid range [{bounds.min_value}, {bounds.max_value}]"
            errors.append(error_msg)
            corrected_value = bounds.clamp(value) if auto_correct else value
            return auto_correct, corrected_value, errors
        
        return True, float(value), []
    
    def validate_entity_centrality(self,
                                  entity_attributes: Dict[str, any],
                                  auto_correct: bool = False,
                                  require_all_metrics: bool = False) -> CentralityValidationResult:
        """
        Validate all centrality metrics for an entity.
        
        Args:
            entity_attributes: Dictionary containing entity attributes
            auto_correct: Whether to auto-correct invalid values
            require_all_metrics: Whether all centrality metrics must be present
            
        Returns:
            CentralityValidationResult with validation status and corrections
        """
        corrected_values = {}
        errors = []
        warnings = []
        
        # Check each centrality metric
        for centrality_type in CentralityType:
            field_name = centrality_type.value
            value = entity_attributes.get(field_name)
            
            if value is None:
                if require_all_metrics:
                    errors.append(f"Required centrality metric '{field_name}' is missing")
                else:
                    warnings.append(f"Centrality metric '{field_name}' is missing, using default")
                    corrected_values[field_name] = self.bounds[centrality_type].default_value
                continue
            
            is_valid, corrected_value, metric_errors = self.validate_single_metric(
                centrality_type, value, auto_correct
            )
            
            if metric_errors:
                errors.extend(metric_errors)
            
            if not is_valid and not auto_correct:
                # If not auto-correcting, validation fails
                continue
            
            # Store corrected value if it changed
            if corrected_value != value or value is None:
                corrected_values[field_name] = corrected_value
        
        # Additional cross-metric validation
        cross_validation_errors = self._validate_metric_relationships(
            entity_attributes, corrected_values
        )
        errors.extend(cross_validation_errors)
        
        if errors and not auto_correct:
            return CentralityValidationResult.failure(errors, corrected_values)
        
        return CentralityValidationResult.success(corrected_values, warnings)
    
    def _validate_metric_relationships(self,
                                     original_attributes: Dict[str, any],
                                     corrected_values: Dict[str, float]) -> List[str]:
        """
        Validate relationships between different centrality metrics.
        
        Args:
            original_attributes: Original entity attributes
            corrected_values: Corrected centrality values
            
        Returns:
            List of validation error messages
        """
        errors = []
        
        # Get current values (corrected if available, otherwise original)
        def get_value(field_name):
            return corrected_values.get(field_name, original_attributes.get(field_name, 0.0))
        
        pagerank = get_value('pagerank_centrality')
        degree = get_value('degree_centrality')
        betweenness = get_value('betweenness_centrality')
        eigenvector = get_value('eigenvector_centrality')
        importance = get_value('importance_score')
        
        # Validate that values are numeric before relationship checks
        metrics = {
            'pagerank_centrality': pagerank,
            'degree_centrality': degree,
            'betweenness_centrality': betweenness,
            'eigenvector_centrality': eigenvector,
            'importance_score': importance
        }
        
        numeric_metrics = {}
        for name, value in metrics.items():
            if isinstance(value, (int, float)) and not (math.isnan(value) or math.isinf(value)):
                numeric_metrics[name] = float(value)
        
        if len(numeric_metrics) < 2:
            return errors  # Need at least 2 metrics for relationship validation
        
        # Check for impossible combinations
        # If degree centrality is 0, most other centralities should also be 0 or very low
        if 'degree_centrality' in numeric_metrics and numeric_metrics['degree_centrality'] == 0.0:
            high_centrality_metrics = []
            for name, value in numeric_metrics.items():
                if name != 'degree_centrality' and value > 0.1:  # Threshold for "high"
                    high_centrality_metrics.append(name)
            
            if high_centrality_metrics:
                errors.append(
                    f"Inconsistent centrality: degree_centrality is 0 but {high_centrality_metrics} are high"
                )
        
        # Check that importance score is reasonable compared to other metrics
        if 'importance_score' in numeric_metrics and len(numeric_metrics) > 1:
            other_metrics = [v for k, v in numeric_metrics.items() if k != 'importance_score']
            avg_other = sum(other_metrics) / len(other_metrics)
            importance_value = numeric_metrics['importance_score']
            
            # Importance score should generally correlate with other centralities
            if avg_other > 0.5 and importance_value < 0.1:
                errors.append(
                    f"Importance score {importance_value:.3f} seems too low compared to other centralities (avg: {avg_other:.3f})"
                )
            elif avg_other < 0.1 and importance_value > 0.7:
                errors.append(
                    f"Importance score {importance_value:.3f} seems too high compared to other centralities (avg: {avg_other:.3f})"
                )
        
        return errors
    
    def normalize_centrality_suite(self,
                                  entities: List[Dict[str, any]],
                                  normalization_method: str = "min_max") -> List[Dict[str, float]]:
        """
        Normalize centrality metrics across a collection of entities.
        
        Args:
            entities: List of entity attribute dictionaries
            normalization_method: Method to use ('min_max', 'z_score', or 'none')
            
        Returns:
            List of normalized centrality corrections for each entity
        """
        if not entities or normalization_method == "none":
            return [{} for _ in entities]
        
        corrections = []
        
        # Extract centrality values for normalization
        centrality_data = {}
        for centrality_type in CentralityType:
            field_name = centrality_type.value
            values = []
            for entity in entities:
                value = entity.get(field_name)
                if isinstance(value, (int, float)) and not (math.isnan(value) or math.isinf(value)):
                    values.append(float(value))
            
            if values:
                centrality_data[field_name] = values
            
        # Apply normalization method
        if normalization_method == "min_max":
            normalization_params = {}
            for field_name, values in centrality_data.items():
                min_val = min(values)
                max_val = max(values)
                normalization_params[field_name] = (min_val, max_val)
            
            # Generate corrections for each entity
            for entity in entities:
                entity_corrections = {}
                for field_name, (min_val, max_val) in normalization_params.items():
                    value = entity.get(field_name)
                    if isinstance(value, (int, float)) and not (math.isnan(value) or math.isinf(value)):
                        if max_val > min_val:
                            normalized = (value - min_val) / (max_val - min_val)
                            entity_corrections[field_name] = normalized
                        else:
                            # All values are the same
                            entity_corrections[field_name] = 0.5
                
                corrections.append(entity_corrections)
        
        elif normalization_method == "z_score":
            normalization_params = {}
            for field_name, values in centrality_data.items():
                mean_val = sum(values) / len(values)
                variance = sum((x - mean_val) ** 2 for x in values) / len(values)
                std_dev = math.sqrt(variance) if variance > 0 else 1.0
                normalization_params[field_name] = (mean_val, std_dev)
            
            # Generate corrections for each entity  
            for entity in entities:
                entity_corrections = {}
                for field_name, (mean_val, std_dev) in normalization_params.items():
                    value = entity.get(field_name)
                    if isinstance(value, (int, float)) and not (math.isnan(value) or math.isinf(value)):
                        z_score = (value - mean_val) / std_dev
                        # Convert z-score to 0-1 range using sigmoid
                        normalized = 1.0 / (1.0 + math.exp(-z_score))
                        entity_corrections[field_name] = normalized
                
                corrections.append(entity_corrections)
        
        return corrections
    
    def get_centrality_summary(self, entities: List[Dict[str, any]]) -> Dict[str, any]:
        """
        Generate summary statistics for centrality metrics across entities.
        
        Args:
            entities: List of entity attribute dictionaries
            
        Returns:
            Dictionary with summary statistics for each centrality type
        """
        summary = {}
        
        for centrality_type in CentralityType:
            field_name = centrality_type.value
            values = []
            invalid_count = 0
            
            for entity in entities:
                value = entity.get(field_name)
                if isinstance(value, (int, float)) and not (math.isnan(value) or math.isinf(value)):
                    values.append(float(value))
                else:
                    invalid_count += 1
            
            if values:
                summary[field_name] = {
                    "count": len(values),
                    "invalid_count": invalid_count,
                    "min": min(values),
                    "max": max(values),
                    "mean": sum(values) / len(values),
                    "median": sorted(values)[len(values) // 2],
                    "valid_percentage": len(values) / (len(values) + invalid_count) * 100
                }
            else:
                summary[field_name] = {
                    "count": 0,
                    "invalid_count": invalid_count,
                    "valid_percentage": 0.0
                }
        
        return summary


# Global validator instance
centrality_validator = CentralityValidator()


def validate_entity_centrality(entity_attributes: Dict[str, any], 
                              auto_correct: bool = True) -> CentralityValidationResult:
    """
    Convenience function to validate centrality metrics for a single entity.
    
    Args:
        entity_attributes: Entity attributes dictionary
        auto_correct: Whether to auto-correct invalid values
        
    Returns:
        CentralityValidationResult
    """
    return centrality_validator.validate_entity_centrality(entity_attributes, auto_correct)


def clamp_centrality_values(entity_attributes: Dict[str, any]) -> Dict[str, float]:
    """
    Clamp all centrality values to valid ranges.
    
    Args:
        entity_attributes: Entity attributes dictionary
        
    Returns:
        Dictionary of clamped centrality values
    """
    corrections = {}
    
    for centrality_type in CentralityType:
        field_name = centrality_type.value
        value = entity_attributes.get(field_name)
        
        if value is not None:
            bounds = CENTRALITY_BOUNDS[centrality_type]
            clamped_value = bounds.clamp(value)
            if clamped_value != value:
                corrections[field_name] = clamped_value
    
    return corrections


def detect_centrality_anomalies(entities: List[Dict[str, any]], 
                               threshold_std_dev: float = 2.0) -> List[Dict[str, any]]:
    """
    Detect entities with anomalous centrality values.
    
    Args:
        entities: List of entity attribute dictionaries
        threshold_std_dev: Number of standard deviations for anomaly detection
        
    Returns:
        List of anomaly reports for entities with suspicious centrality values
    """
    anomalies = []
    
    # Calculate statistics for each centrality metric
    centrality_stats = {}
    for centrality_type in CentralityType:
        field_name = centrality_type.value
        values = []
        
        for entity in entities:
            value = entity.get(field_name)
            if isinstance(value, (int, float)) and not (math.isnan(value) or math.isinf(value)):
                values.append(float(value))
        
        if len(values) > 1:
            mean_val = sum(values) / len(values)
            variance = sum((x - mean_val) ** 2 for x in values) / len(values)
            std_dev = math.sqrt(variance)
            centrality_stats[field_name] = (mean_val, std_dev)
    
    # Check each entity for anomalies
    for i, entity in enumerate(entities):
        entity_anomalies = []
        
        for field_name, (mean_val, std_dev) in centrality_stats.items():
            value = entity.get(field_name)
            if isinstance(value, (int, float)) and not (math.isnan(value) or math.isinf(value)):
                z_score = abs(value - mean_val) / std_dev if std_dev > 0 else 0
                if z_score > threshold_std_dev:
                    entity_anomalies.append({
                        "metric": field_name,
                        "value": value,
                        "z_score": z_score,
                        "mean": mean_val,
                        "std_dev": std_dev
                    })
        
        if entity_anomalies:
            anomalies.append({
                "entity_index": i,
                "entity_uuid": entity.get("uuid", "unknown"),
                "entity_name": entity.get("name", "unknown"),
                "anomalies": entity_anomalies
            })
    
    return anomalies