"""
DSPy-based ingestion pipeline for Graphiti.

This module provides a DSPy implementation of the Graphiti ingestion pipeline,
running in parallel with the existing implementation for comparison and verification.
"""

from graphiti_core.dspy.config import configure_lm, get_lm_config
from graphiti_core.dspy.signatures import (
    EntityExtractionSignature,
    EdgeExtractionSignature,
    NodeDeduplicationSignature,
    SummaryGenerationSignature,
)
from graphiti_core.dspy.modules import (
    NodeExtractor,
    EdgeExtractor,
    NodeResolver,
    SummaryGenerator,
)
from graphiti_core.dspy.pipeline import (
    DSPyIngestionPipeline,
    PipelineResult,
    GraphState,
    TokenUsage,
    DEFAULT_ENTITY_TYPES,
)
from graphiti_core.dspy.comparison import (
    PipelineComparator,
    ComparisonResult,
    ComparisonMetrics,
)
from graphiti_core.dspy.optimization import (
    TrainingDataCollector,
    TrainingDataset,
    DSPyOptimizer,
    entity_extraction_metric,
    edge_extraction_metric,
    node_resolution_metric,
    summary_metric,
)

__all__ = [
    # Config
    'configure_lm',
    'get_lm_config',
    # Signatures
    'EntityExtractionSignature',
    'EdgeExtractionSignature',
    'NodeDeduplicationSignature',
    'SummaryGenerationSignature',
    # Modules
    'NodeExtractor',
    'EdgeExtractor',
    'NodeResolver',
    'SummaryGenerator',
    # Pipeline
    'DSPyIngestionPipeline',
    'PipelineResult',
    'GraphState',
    'TokenUsage',
    'DEFAULT_ENTITY_TYPES',
    # Comparison
    'PipelineComparator',
    'ComparisonResult',
    'ComparisonMetrics',
    # Optimization
    'TrainingDataCollector',
    'TrainingDataset',
    'DSPyOptimizer',
    'entity_extraction_metric',
    'edge_extraction_metric',
    'node_resolution_metric',
    'summary_metric',
]
