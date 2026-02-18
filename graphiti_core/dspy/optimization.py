"""
MIPROv2 Optimization for DSPy Graphiti Pipeline.

This module provides utilities for:
1. Collecting training data from successful extractions
2. Defining evaluation metrics
3. Running MIPROv2 optimization
4. Saving/loading optimized modules
"""

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import dspy
from dspy.teleprompt import MIPROv2

from .config import configure_lm, get_lm
from .modules import (
    NodeExtractor,
    EdgeExtractor,
    NodeResolver,
    SummaryGenerator,
)
from .signatures import (
    ExtractedEntities,
    ExtractedEdges,
    NodeResolutions,
    Summary,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Training Data Structures
# =============================================================================


@dataclass
class TrainingExample:
    """A single training example for optimization."""

    inputs: dict[str, Any]
    expected_output: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dspy_example(self) -> dspy.Example:
        """Convert to DSPy Example format."""
        example_dict = {**self.inputs}
        # Add expected output fields
        for key, value in self.expected_output.items():
            example_dict[key] = value
        return dspy.Example(**example_dict).with_inputs(*self.inputs.keys())


@dataclass
class TrainingDataset:
    """Collection of training examples for a specific task."""

    task_name: str
    examples: list[TrainingExample] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def add_example(self, inputs: dict, expected_output: dict, metadata: dict | None = None):
        """Add a training example."""
        self.examples.append(
            TrainingExample(
                inputs=inputs,
                expected_output=expected_output,
                metadata=metadata or {},
            )
        )

    def to_dspy_examples(self) -> list[dspy.Example]:
        """Convert all examples to DSPy format."""
        return [ex.to_dspy_example() for ex in self.examples]

    def save(self, path: str | Path):
        """Save dataset to JSON file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            'task_name': self.task_name,
            'created_at': self.created_at,
            'example_count': len(self.examples),
            'examples': [
                {
                    'inputs': ex.inputs,
                    'expected_output': ex.expected_output,
                    'metadata': ex.metadata,
                }
                for ex in self.examples
            ],
        }

        with open(path, 'w') as f:
            json.dump(data, f, indent=2)

        logger.info(f'Saved {len(self.examples)} examples to {path}')

    @classmethod
    def load(cls, path: str | Path) -> 'TrainingDataset':
        """Load dataset from JSON file."""
        with open(path) as f:
            data = json.load(f)

        dataset = cls(
            task_name=data['task_name'],
            created_at=data.get('created_at', ''),
        )

        for ex_data in data['examples']:
            dataset.add_example(
                inputs=ex_data['inputs'],
                expected_output=ex_data['expected_output'],
                metadata=ex_data.get('metadata', {}),
            )

        return dataset


# =============================================================================
# Training Data Collection
# =============================================================================


class TrainingDataCollector:
    """
    DEPRECATED: Use FalkorDB-backed storage instead.

    This JSON file-based collector has been superseded by
    graphiti_core.dspy.training_storage.TrainingDataStorage which provides
    atomic, concurrent-safe storage in FalkorDB.

    This class remains for backwards compatibility but will be removed
    in a future release.

    For new code, use:
        from graphiti_core.dspy.training_storage import (
            record_training_example,
            get_training_examples,
            sample_training_examples,
        )
    """

    def __init__(self, save_dir: str | Path = 'training_data'):
        self.save_dir = Path(save_dir)
        self.save_dir.mkdir(parents=True, exist_ok=True)

        # Load existing datasets or create new ones
        self.entity_extraction = self._load_or_create('entity_extraction')
        self.edge_extraction = self._load_or_create('edge_extraction')
        self.node_resolution = self._load_or_create('node_resolution')
        self.summary_generation = self._load_or_create('summary_generation')

    def _load_or_create(self, task_name: str) -> TrainingDataset:
        """Load existing dataset from disk or create new empty one."""
        path = self.save_dir / f'{task_name}.json'
        if path.exists():
            try:
                dataset = TrainingDataset.load(path)
                logger.info(f'Loaded {len(dataset.examples)} existing {task_name} examples')
                return dataset
            except Exception as e:
                logger.warning(f'Failed to load {task_name} dataset: {e}, creating new')
        return TrainingDataset(task_name)

    def record_entity_extraction(
        self,
        current_message: str,
        entity_types: list[dict],
        result: ExtractedEntities,
        previous_messages: list[dict] | None = None,
    ):
        """Record a successful entity extraction."""
        self.entity_extraction.add_example(
            inputs={
                'current_message': current_message,
                'entity_types': json.dumps(entity_types),
                'previous_messages': json.dumps(previous_messages or []),
                'custom_instructions': '',
            },
            expected_output={
                'extracted_entities': result.model_dump(),
            },
        )

    def record_edge_extraction(
        self,
        current_message: str,
        entities: list[dict],
        reference_time: str,
        result: ExtractedEdges,
        previous_messages: list[dict] | None = None,
    ):
        """Record a successful edge extraction."""
        self.edge_extraction.add_example(
            inputs={
                'current_message': current_message,
                'entities': json.dumps(entities),
                'reference_time': reference_time,
                'previous_messages': json.dumps(previous_messages or []),
                'edge_types': '[]',
                'custom_instructions': '',
            },
            expected_output={
                'extracted_edges': result.model_dump(),
            },
        )

    def record_node_resolution(
        self,
        current_message: str,
        extracted_entities: list[dict],
        existing_entities: list[dict],
        result: NodeResolutions,
        previous_messages: list[dict] | None = None,
    ):
        """Record a successful node resolution."""
        self.node_resolution.add_example(
            inputs={
                'current_message': current_message,
                'extracted_entities': json.dumps(extracted_entities),
                'existing_entities': json.dumps(existing_entities),
                'previous_messages': json.dumps(previous_messages or []),
            },
            expected_output={
                'entity_resolutions': result.model_dump(),
            },
        )

    def record_summary_generation(
        self,
        current_message: str,
        entity_name: str,
        result: Summary,
        previous_messages: list[dict] | None = None,
        existing_summary: str = '',
    ):
        """Record a successful summary generation."""
        self.summary_generation.add_example(
            inputs={
                'current_message': current_message,
                'entity_name': entity_name,
                'previous_messages': json.dumps(previous_messages or []),
                'existing_summary': existing_summary,
            },
            expected_output={
                'summary': result.model_dump(),
            },
        )

    def save_all(self):
        """Save all datasets."""
        self.entity_extraction.save(self.save_dir / 'entity_extraction.json')
        self.edge_extraction.save(self.save_dir / 'edge_extraction.json')
        self.node_resolution.save(self.save_dir / 'node_resolution.json')
        self.summary_generation.save(self.save_dir / 'summary_generation.json')

    def get_stats(self) -> dict[str, int]:
        """Get example counts for each task."""
        return {
            'entity_extraction': len(self.entity_extraction.examples),
            'edge_extraction': len(self.edge_extraction.examples),
            'node_resolution': len(self.node_resolution.examples),
            'summary_generation': len(self.summary_generation.examples),
        }


# =============================================================================
# Evaluation Metrics
# =============================================================================


def entity_extraction_metric(example: dspy.Example, prediction: Any, trace=None) -> float:
    """
    Evaluate entity extraction quality.

    Scores based on:
    - Precision: % of predicted entities that are correct
    - Recall: % of expected entities that were found
    """
    try:
        expected = example.extracted_entities
        if isinstance(expected, str):
            try:
                expected = json.loads(expected)
            except (json.JSONDecodeError, TypeError):
                expected = {}
        if isinstance(expected, dict):
            expected_names = {e['name'].lower() for e in expected.get('extracted_entities', [])}
        elif isinstance(expected, ExtractedEntities):
            expected_names = {e.name.lower() for e in expected.extracted_entities}
        else:
            expected_names = set()

        if isinstance(prediction, ExtractedEntities):
            predicted_names = {e.name.lower() for e in prediction.extracted_entities}
        elif hasattr(prediction, 'extracted_entities'):
            predicted = prediction.extracted_entities
            if isinstance(predicted, ExtractedEntities):
                predicted_names = {e.name.lower() for e in predicted.extracted_entities}
            elif isinstance(predicted, dict):
                predicted_names = {
                    e['name'].lower() for e in predicted.get('extracted_entities', [])
                }
            else:
                predicted_names = set()
        else:
            predicted_names = set()

        if not expected_names and not predicted_names:
            return 1.0

        intersection = expected_names & predicted_names
        precision = len(intersection) / len(predicted_names) if predicted_names else 0
        recall = len(intersection) / len(expected_names) if expected_names else 0

        # F1 score
        if precision + recall == 0:
            return 0.0
        return 2 * (precision * recall) / (precision + recall)
    except Exception as e:
        logger.warning(f'Entity extraction metric error: {e}')
        return 0.0


def edge_extraction_metric(example: dspy.Example, prediction: Any, trace=None) -> float:
    """
    Evaluate edge extraction quality.

    Scores based on matching (source, relation_type, target) triples.
    """
    try:

        def normalize_edge(e):
            if isinstance(e, dict):
                return (
                    str(e.get('source_entity_id', e.get('source', ''))).lower(),
                    e.get('relation_type', '').upper(),
                    str(e.get('target_entity_id', e.get('target', ''))).lower(),
                )
            return (str(e.source_entity_id), e.relation_type.upper(), str(e.target_entity_id))

        expected = example.extracted_edges
        if isinstance(expected, str):
            try:
                expected = json.loads(expected)
            except (json.JSONDecodeError, TypeError):
                expected = {}
        if isinstance(expected, dict):
            expected_edges = {normalize_edge(e) for e in expected.get('edges', [])}
        elif isinstance(expected, ExtractedEdges):
            expected_edges = {normalize_edge(e) for e in expected.edges}
        else:
            expected_edges = set()

        if isinstance(prediction, ExtractedEdges):
            predicted_edges = {normalize_edge(e) for e in prediction.edges}
        elif hasattr(prediction, 'extracted_edges'):
            predicted = prediction.extracted_edges
            if isinstance(predicted, ExtractedEdges):
                predicted_edges = {normalize_edge(e) for e in predicted.edges}
            elif isinstance(predicted, dict):
                predicted_edges = {normalize_edge(e) for e in predicted.get('edges', [])}
            else:
                predicted_edges = set()
        else:
            predicted_edges = set()

        if not expected_edges and not predicted_edges:
            return 1.0

        intersection = expected_edges & predicted_edges
        precision = len(intersection) / len(predicted_edges) if predicted_edges else 0
        recall = len(intersection) / len(expected_edges) if expected_edges else 0

        if precision + recall == 0:
            return 0.0
        return 2 * (precision * recall) / (precision + recall)
    except Exception as e:
        logger.warning(f'Edge extraction metric error: {e}')
        return 0.0


def node_resolution_metric(example: dspy.Example, prediction: Any, trace=None) -> float:
    """
    Evaluate node resolution quality.

    Scores based on correct duplicate detection.
    """
    try:
        expected = example.entity_resolutions
        if isinstance(expected, str):
            try:
                expected = json.loads(expected)
            except (json.JSONDecodeError, TypeError):
                expected = {}
        if isinstance(expected, dict):
            expected_map = {
                r['id']: r['duplicate_idx'] for r in expected.get('entity_resolutions', [])
            }
        elif isinstance(expected, NodeResolutions):
            expected_map = {r.id: r.duplicate_idx for r in expected.entity_resolutions}
        else:
            expected_map = {}

        if isinstance(prediction, NodeResolutions):
            predicted_map = {r.id: r.duplicate_idx for r in prediction.entity_resolutions}
        elif hasattr(prediction, 'entity_resolutions'):
            predicted = prediction.entity_resolutions
            if isinstance(predicted, NodeResolutions):
                predicted_map = {r.id: r.duplicate_idx for r in predicted.entity_resolutions}
            elif isinstance(predicted, dict):
                predicted_map = {
                    r['id']: r['duplicate_idx'] for r in predicted.get('entity_resolutions', [])
                }
            else:
                predicted_map = {}
        else:
            predicted_map = {}

        if not expected_map:
            return 1.0

        correct = sum(1 for k, v in expected_map.items() if predicted_map.get(k) == v)
        return correct / len(expected_map)
    except Exception as e:
        logger.warning(f'Node resolution metric error: {e}')
        return 0.0


def summary_metric(example: dspy.Example, prediction: Any, trace=None) -> float:
    """
    Evaluate summary quality.

    Basic length and content check - summaries should be non-empty
    and under 250 words.
    """
    try:
        predicted = prediction.summary
        if isinstance(predicted, Summary):
            text = predicted.summary
        elif isinstance(predicted, dict):
            text = predicted.get('summary', '')
        elif isinstance(predicted, str):
            text = predicted
        else:
            return 0.0

        if not text or len(text.strip()) < 10:
            return 0.0

        word_count = len(text.split())
        if word_count > 300:  # Allow some flexibility
            return 0.5

        return 1.0
    except Exception as e:
        logger.warning(f'Summary metric error: {e}')
        return 0.0


# =============================================================================
# MIPROv2 Optimizer
# =============================================================================


class DSPyOptimizer:
    """
    MIPROv2 optimizer for DSPy Graphiti modules.

    Optimizes prompts and few-shot examples for each module
    to improve extraction quality.
    """

    def __init__(
        self,
        training_data_dir: str | Path = 'training_data',
        output_dir: str | Path = 'optimized_modules',
        num_candidates: int = 10,
        num_threads: int = 4,
    ):
        self.training_data_dir = Path(training_data_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.num_candidates = num_candidates
        self.num_threads = num_threads

    def load_training_data(self, task: str) -> TrainingDataset | None:
        """Load training data for a task."""
        path = self.training_data_dir / f'{task}.json'
        if not path.exists():
            logger.warning(f'No training data found at {path}')
            return None
        return TrainingDataset.load(path)

    def optimize_entity_extraction(
        self,
        min_examples: int = 50,
    ) -> NodeExtractor | None:
        """
        Optimize entity extraction module with MIPROv2.

        Args:
            min_examples: Minimum training examples required.

        Returns:
            Optimized NodeExtractor or None if insufficient data.
        """
        dataset = self.load_training_data('entity_extraction')
        if not dataset or len(dataset.examples) < min_examples:
            logger.warning(f'Need at least {min_examples} examples for optimization')
            return None

        logger.info(f'Optimizing entity extraction with {len(dataset.examples)} examples')

        # Split into train/dev
        examples = dataset.to_dspy_examples()
        split = int(len(examples) * 0.8)
        trainset = examples[:split]
        devset = examples[split:]

        # Create optimizer
        optimizer = MIPROv2(
            metric=entity_extraction_metric,
            num_candidates=self.num_candidates,
            num_threads=self.num_threads,
            verbose=True,
        )

        # Optimize
        module = NodeExtractor()
        optimized = optimizer.compile(
            module,
            trainset=trainset,
            valset=devset,
        )

        # Save
        output_path = self.output_dir / 'entity_extraction_optimized.json'
        optimized.save(str(output_path))
        logger.info(f'Saved optimized entity extractor to {output_path}')

        return optimized

    def optimize_edge_extraction(
        self,
        min_examples: int = 50,
    ) -> EdgeExtractor | None:
        """Optimize edge extraction module."""
        dataset = self.load_training_data('edge_extraction')
        if not dataset or len(dataset.examples) < min_examples:
            logger.warning(f'Need at least {min_examples} examples for optimization')
            return None

        logger.info(f'Optimizing edge extraction with {len(dataset.examples)} examples')

        examples = dataset.to_dspy_examples()
        split = int(len(examples) * 0.8)
        trainset = examples[:split]
        devset = examples[split:]

        optimizer = MIPROv2(
            metric=edge_extraction_metric,
            num_candidates=self.num_candidates,
            num_threads=self.num_threads,
            verbose=True,
        )

        module = EdgeExtractor()
        optimized = optimizer.compile(
            module,
            trainset=trainset,
            valset=devset,
        )

        output_path = self.output_dir / 'edge_extraction_optimized.json'
        optimized.save(str(output_path))
        logger.info(f'Saved optimized edge extractor to {output_path}')

        return optimized

    def optimize_node_resolution(
        self,
        min_examples: int = 50,
    ) -> NodeResolver | None:
        """Optimize node resolution module."""
        dataset = self.load_training_data('node_resolution')
        if not dataset or len(dataset.examples) < min_examples:
            logger.warning(f'Need at least {min_examples} examples for optimization')
            return None

        logger.info(f'Optimizing node resolution with {len(dataset.examples)} examples')

        examples = dataset.to_dspy_examples()
        split = int(len(examples) * 0.8)
        trainset = examples[:split]
        devset = examples[split:]

        optimizer = MIPROv2(
            metric=node_resolution_metric,
            num_candidates=self.num_candidates,
            num_threads=self.num_threads,
            verbose=True,
        )

        module = NodeResolver()
        optimized = optimizer.compile(
            module,
            trainset=trainset,
            valset=devset,
        )

        output_path = self.output_dir / 'node_resolution_optimized.json'
        optimized.save(str(output_path))
        logger.info(f'Saved optimized node resolver to {output_path}')

        return optimized

    def optimize_all(self, min_examples: int = 50) -> dict[str, Any]:
        """
        Optimize all modules.

        Returns dict with optimization results for each module.
        """
        results = {}

        results['entity_extraction'] = self.optimize_entity_extraction(min_examples)
        results['edge_extraction'] = self.optimize_edge_extraction(min_examples)
        results['node_resolution'] = self.optimize_node_resolution(min_examples)

        return results


def load_optimized_module(path: str | Path, module_class: type) -> Any:
    """Load an optimized module from file."""
    module = module_class()
    module.load(str(path))
    return module
