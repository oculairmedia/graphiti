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
    TrainingDataCollector,  # Deprecated: use training_storage instead
    TrainingDataset,
    DSPyOptimizer,
    entity_extraction_metric,
    edge_extraction_metric,
    node_resolution_metric,
    summary_metric,
)
from graphiti_core.dspy.training_storage import (
    TrainingDataStorage,
    StoredTrainingExample,
    record_training_example,
    get_training_examples,
    sample_training_examples,
    get_training_stats,
    split_train_val,
)
from graphiti_core.dspy.response_logger import (
    ResponseLogger,
    ResponseLoggerConfig,
    StageLogEntry,
    get_response_logger,
    configure_response_logger,
)
from graphiti_core.dspy.hot_reload import (
    HotReloader,
    HotReloadConfig,
    get_hot_reloader,
    configure_hot_reload,
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
    'TrainingDataCollector',  # Deprecated
    'TrainingDataset',
    'DSPyOptimizer',
    'entity_extraction_metric',
    'edge_extraction_metric',
    'node_resolution_metric',
    'summary_metric',
    # Training Storage (FalkorDB-backed, replaces TrainingDataCollector)
    'TrainingDataStorage',
    'StoredTrainingExample',
    'record_training_example',
    'get_training_examples',
    'sample_training_examples',
    'get_training_stats',
    'split_train_val',
    # Response Logging
    'ResponseLogger',
    'ResponseLoggerConfig',
    'StageLogEntry',
    'get_response_logger',
    'configure_response_logger',
    # Hot Reload
    'HotReloader',
    'HotReloadConfig',
    'get_hot_reloader',
    'configure_hot_reload',
]
