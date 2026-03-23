"""
MIPROv2-compatible quality metrics for Graphiti DSPy pipeline.

This module provides evaluation metrics for:
- Entity extraction quality (precision, recall, F1)
- Deduplication accuracy
- Edge/relationship resolution
- Efficiency (tokens, processing time)
"""

from typing import Any, Dict, List, Optional, Set, Tuple
import time
from dataclasses import dataclass


@dataclass
class EntityMetrics:
    """Entity extraction quality metrics."""
    precision: float
    recall: float
    f1: float
    
    def to_dict(self) -> Dict[str, float]:
        return {
            'precision': self.precision,
            'recall': self.recall,
            'f1': self.f1
        }


@dataclass
class DeduplicationMetrics:
    """Deduplication quality metrics."""
    false_positive_rate: float  # Incorrectly merged distinct entities
    false_negative_rate: float  # Failed to merge duplicates
    accuracy: float
    
    def to_dict(self) -> Dict[str, float]:
        return {
            'false_positive_rate': self.false_positive_rate,
            'false_negative_rate': self.false_negative_rate,
            'accuracy': self.accuracy
        }


@dataclass
class EdgeMetrics:
    """Edge/relationship resolution metrics."""
    relationship_accuracy: float
    temporal_accuracy: float
    overall_accuracy: float
    
    def to_dict(self) -> Dict[str, float]:
        return {
            'relationship_accuracy': self.relationship_accuracy,
            'temporal_accuracy': self.temporal_accuracy,
            'overall_accuracy': self.overall_accuracy
        }


@dataclass
class EfficiencyMetrics:
    """Efficiency and performance metrics."""
    tokens_per_extraction: float
    processing_time_ms: float
    extractions_per_second: float
    
    def to_dict(self) -> Dict[str, float]:
        return {
            'tokens_per_extraction': self.tokens_per_extraction,
            'processing_time_ms': self.processing_time_ms,
            'extractions_per_second': self.extractions_per_second
        }


def entity_precision(expected: List[Dict[str, Any]], extracted: List[Dict[str, Any]]) -> float:
    """
    Calculate precision: % of extracted entities that are valid.
    
    Args:
        expected: Ground truth entities
        extracted: Entities extracted by the system
        
    Returns:
        Precision score (0.0 to 1.0)
    """
    if not extracted:
        return 0.0
    
    # Match by entity name (case-insensitive)
    expected_names = {e.get('name', '').lower() for e in expected if e.get('name')}
    extracted_names = {e.get('name', '').lower() for e in extracted if e.get('name')}
    
    true_positives = len(expected_names & extracted_names)
    return true_positives / len(extracted_names) if extracted_names else 0.0


def entity_recall(expected: List[Dict[str, Any]], extracted: List[Dict[str, Any]]) -> float:
    """
    Calculate recall: % of expected entities that were extracted.
    
    Args:
        expected: Ground truth entities
        extracted: Entities extracted by the system
        
    Returns:
        Recall score (0.0 to 1.0)
    """
    if not expected:
        return 1.0  # No entities to extract
    
    expected_names = {e.get('name', '').lower() for e in expected if e.get('name')}
    extracted_names = {e.get('name', '').lower() for e in extracted if e.get('name')}
    
    true_positives = len(expected_names & extracted_names)
    return true_positives / len(expected_names) if expected_names else 0.0


def entity_f1(expected: List[Dict[str, Any]], extracted: List[Dict[str, Any]]) -> float:
    """
    Calculate F1 score: harmonic mean of precision and recall.
    
    Args:
        expected: Ground truth entities
        extracted: Entities extracted by the system
        
    Returns:
        F1 score (0.0 to 1.0)
    """
    precision = entity_precision(expected, extracted)
    recall = entity_recall(expected, extracted)
    
    if precision + recall == 0:
        return 0.0
    
    return 2 * (precision * recall) / (precision + recall)


def entity_metrics(expected: List[Dict[str, Any]], extracted: List[Dict[str, Any]]) -> EntityMetrics:
    """
    Calculate all entity extraction metrics.
    
    Args:
        expected: Ground truth entities
        extracted: Entities extracted by the system
        
    Returns:
        EntityMetrics object with precision, recall, and F1
    """
    precision = entity_precision(expected, extracted)
    recall = entity_recall(expected, extracted)
    f1 = entity_f1(expected, extracted)
    
    return EntityMetrics(precision=precision, recall=recall, f1=f1)


def dedup_accuracy(
    expected_merges: List[Tuple[str, str]], 
    actual_merges: List[Tuple[str, str]],
    expected_distinct: Optional[List[Tuple[str, str]]] = None
) -> DeduplicationMetrics:
    """
    Calculate deduplication quality metrics.
    
    Args:
        expected_merges: Pairs of entity IDs that should be merged
        actual_merges: Pairs of entity IDs that were actually merged
        expected_distinct: Pairs that should NOT be merged (optional)
        
    Returns:
        DeduplicationMetrics with FP/FN rates and accuracy
    """
    expected_set = {tuple(sorted(pair)) for pair in expected_merges}
    actual_set = {tuple(sorted(pair)) for pair in actual_merges}
    
    # True positives: correctly identified duplicates
    true_positives = len(expected_set & actual_set)
    
    # False negatives: failed to merge duplicates
    false_negatives = len(expected_set - actual_set)
    
    # False positives: incorrectly merged distinct entities
    false_positives = len(actual_set - expected_set)
    
    # Calculate rates
    total_expected = len(expected_set)
    total_actual = len(actual_set)
    
    if expected_distinct:
        distinct_set = {tuple(sorted(pair)) for pair in expected_distinct}
        # FP: merged pairs that should be distinct
        false_positives = len(actual_set & distinct_set)
        total_negative = len(distinct_set)
        fp_rate = false_positives / total_negative if total_negative > 0 else 0.0
    else:
        fp_rate = false_positives / total_actual if total_actual > 0 else 0.0
    
    fn_rate = false_negatives / total_expected if total_expected > 0 else 0.0
    
    # Overall accuracy
    total_decisions = total_expected + (len(expected_distinct) if expected_distinct else 0)
    correct_decisions = true_positives + (
        len(expected_distinct) - false_positives if expected_distinct else 0
    )
    accuracy = correct_decisions / total_decisions if total_decisions > 0 else 0.0
    
    return DeduplicationMetrics(
        false_positive_rate=fp_rate,
        false_negative_rate=fn_rate,
        accuracy=accuracy
    )


def edge_accuracy(
    expected_edges: List[Dict[str, Any]], 
    extracted_edges: List[Dict[str, Any]]
) -> EdgeMetrics:
    """
    Calculate edge/relationship resolution metrics.
    
    Args:
        expected_edges: Ground truth edges with relationships and temporal data
        extracted_edges: Edges extracted by the system
        
    Returns:
        EdgeMetrics with relationship and temporal accuracy
    """
    if not expected_edges:
        return EdgeMetrics(
            relationship_accuracy=1.0,
            temporal_accuracy=1.0,
            overall_accuracy=1.0
        )
    
    # Match edges by source-target pairs
    def edge_key(edge: Dict[str, Any]) -> Tuple[str, str]:
        return (
            edge.get('source_node_uuid', ''),
            edge.get('target_node_uuid', '')
        )
    
    expected_map = {edge_key(e): e for e in expected_edges}
    extracted_map = {edge_key(e): e for e in extracted_edges}
    
    matching_keys = set(expected_map.keys()) & set(extracted_map.keys())
    
    if not matching_keys:
        return EdgeMetrics(
            relationship_accuracy=0.0,
            temporal_accuracy=0.0,
            overall_accuracy=0.0
        )
    
    # Check relationship type accuracy
    correct_relationships = sum(
        1 for key in matching_keys
        if expected_map[key].get('name') == extracted_map[key].get('name')
    )
    relationship_accuracy = correct_relationships / len(matching_keys)
    
    # Check temporal metadata accuracy (if present)
    temporal_matches = 0
    temporal_total = 0
    
    for key in matching_keys:
        expected_edge = expected_map[key]
        extracted_edge = extracted_map[key]
        
        if 'created_at' in expected_edge or 'valid_at' in expected_edge:
            temporal_total += 1
            # Allow some tolerance for timestamps (within 1 second)
            expected_time = expected_edge.get('created_at') or expected_edge.get('valid_at')
            extracted_time = extracted_edge.get('created_at') or extracted_edge.get('valid_at')
            
            if expected_time and extracted_time:
                if abs(expected_time - extracted_time) < 1000:  # 1 second tolerance
                    temporal_matches += 1
    
    temporal_accuracy = temporal_matches / temporal_total if temporal_total > 0 else 1.0
    
    # Overall accuracy: combination of relationship and temporal
    overall_accuracy = (relationship_accuracy + temporal_accuracy) / 2
    
    return EdgeMetrics(
        relationship_accuracy=relationship_accuracy,
        temporal_accuracy=temporal_accuracy,
        overall_accuracy=overall_accuracy
    )


def efficiency_metrics(
    num_extractions: int,
    total_tokens: int,
    processing_time_ms: float
) -> EfficiencyMetrics:
    """
    Calculate efficiency and performance metrics.
    
    Args:
        num_extractions: Number of successful extractions
        total_tokens: Total tokens used
        processing_time_ms: Total processing time in milliseconds
        
    Returns:
        EfficiencyMetrics with token and time efficiency
    """
    tokens_per_extraction = total_tokens / num_extractions if num_extractions > 0 else 0.0
    processing_time_sec = processing_time_ms / 1000.0
    extractions_per_second = num_extractions / processing_time_sec if processing_time_sec > 0 else 0.0
    
    return EfficiencyMetrics(
        tokens_per_extraction=tokens_per_extraction,
        processing_time_ms=processing_time_ms,
        extractions_per_second=extractions_per_second
    )


def combined_quality_metric(
    example: Dict[str, Any], 
    prediction: Dict[str, Any], 
    trace: Optional[Any] = None
) -> float:
    """
    MIPROv2-compatible combined quality metric.
    
    Weighted combination of:
    - 40% entity extraction F1
    - 30% deduplication accuracy
    - 30% edge accuracy
    
    Args:
        example: Ground truth data with 'entities', 'merges', 'edges'
        prediction: System output with same structure
        trace: Optional DSPy trace (unused, for MIPROv2 compatibility)
        
    Returns:
        Combined quality score (0.0 to 1.0)
    """
    # Entity extraction score
    expected_entities = example.get('entities', [])
    extracted_entities = prediction.get('entities', [])
    entity_score = entity_f1(expected_entities, extracted_entities)
    
    # Deduplication score
    expected_merges = example.get('merges', [])
    actual_merges = prediction.get('merges', [])
    expected_distinct = example.get('distinct', [])
    dedup_result = dedup_accuracy(expected_merges, actual_merges, expected_distinct)
    dedup_score = dedup_result.accuracy
    
    # Edge resolution score
    expected_edges = example.get('edges', [])
    extracted_edges = prediction.get('edges', [])
    edge_result = edge_accuracy(expected_edges, extracted_edges)
    edge_score = edge_result.overall_accuracy
    
    # Weighted combination
    combined_score = (
        0.4 * entity_score +
        0.3 * dedup_score +
        0.3 * edge_score
    )
    
    return combined_score


# Export all public functions and classes
__all__ = [
    'EntityMetrics',
    'DeduplicationMetrics',
    'EdgeMetrics',
    'EfficiencyMetrics',
    'entity_precision',
    'entity_recall',
    'entity_f1',
    'entity_metrics',
    'dedup_accuracy',
    'edge_accuracy',
    'efficiency_metrics',
    'combined_quality_metric',
]
