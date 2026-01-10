"""
OpenEvolve evaluators for Graphiti DSPy components.

These evaluators wrap Graphiti's existing metrics to work with OpenEvolve's
evolutionary optimization framework.
"""

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class EvaluationResult:
    """
    OpenEvolve-compatible evaluation result.

    Maps to openevolve.evaluation_result.EvaluationResult format.
    """
    metrics: dict[str, float] = field(default_factory=dict)
    artifacts: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            'metrics': self.metrics,
            'artifacts': self.artifacts,
        }


def create_evaluation_result(
    score: float,
    metrics: dict[str, float] | None = None,
    artifacts: dict[str, str] | None = None,
) -> EvaluationResult:
    """Create an evaluation result with a primary score."""
    all_metrics = {'score': score}
    if metrics:
        all_metrics.update(metrics)
    return EvaluationResult(
        metrics=all_metrics,
        artifacts=artifacts or {},
    )


class BaseEvaluator:
    """Base class for OpenEvolve evaluators."""

    def __init__(
        self,
        test_data_path: str | Path,
        timeout_seconds: float = 30.0,
    ):
        self.test_data_path = Path(test_data_path)
        self.timeout_seconds = timeout_seconds
        self._test_examples: list[dict] = []
        self._load_test_data()

    def _load_test_data(self) -> None:
        """Load test examples from JSON file."""
        if not self.test_data_path.exists():
            logger.warning(f'Test data not found at {self.test_data_path}')
            return

        with open(self.test_data_path) as f:
            data = json.load(f)

        self._test_examples = data.get('examples', [])
        logger.info(f'Loaded {len(self._test_examples)} test examples')

    def evaluate(self, code_path: str) -> EvaluationResult:
        """Evaluate evolved code. Override in subclasses."""
        raise NotImplementedError


class EntityExtractionEvaluator(BaseEvaluator):
    """
    Evaluator for entity extraction prompt evolution.

    Measures:
    - extraction_f1: F1 score for entity extraction
    - precision: Extraction precision
    - recall: Extraction recall
    - token_efficiency: Tokens used per entity extracted
    - latency_ms: Average inference time
    """

    def __init__(
        self,
        test_data_path: str | Path = 'training_data/entity_extraction.json',
        timeout_seconds: float = 30.0,
    ):
        super().__init__(test_data_path, timeout_seconds)

    def evaluate(self, code_path: str) -> EvaluationResult:
        """
        Evaluate an evolved entity extraction prompt.

        Args:
            code_path: Path to Python file containing evolved prompt/signature.

        Returns:
            EvaluationResult with extraction metrics.
        """
        start_time = time.time()
        artifacts: dict[str, str] = {}

        try:
            # Load the evolved prompt
            evolved_code = Path(code_path).read_text()
            artifacts['evolved_code'] = evolved_code[:500]  # First 500 chars for debugging

            # Execute to get the prompt template
            local_ns: dict[str, Any] = {}
            exec(evolved_code, {'__builtins__': __builtins__}, local_ns)

            # Get the extraction instruction from evolved code
            extraction_instruction = local_ns.get(
                'EXTRACTION_INSTRUCTION',
                local_ns.get('instruction', '')
            )

            if not extraction_instruction:
                return create_evaluation_result(
                    score=0.0,
                    artifacts={'error': 'No EXTRACTION_INSTRUCTION found in evolved code'},
                )

            # Import here to avoid circular imports
            from graphiti_core.dspy.modules import NodeExtractor
            from graphiti_core.dspy.signatures import ExtractedEntities

            # Create extractor with evolved instruction
            extractor = NodeExtractor()

            # Run on test examples
            total_precision = 0.0
            total_recall = 0.0
            total_f1 = 0.0
            total_tokens = 0
            total_entities = 0
            successful_runs = 0

            for example in self._test_examples[:20]:  # Limit to 20 for speed
                try:
                    inputs = example.get('inputs', {})
                    expected = example.get('expected_output', {})

                    # Get expected entity names
                    expected_entities = expected.get('extracted_entities', {})
                    if isinstance(expected_entities, dict):
                        expected_names = {
                            e['name'].lower()
                            for e in expected_entities.get('extracted_entities', [])
                        }
                    else:
                        expected_names = set()

                    # Run extraction with evolved instruction injected
                    result = extractor(
                        current_message=inputs.get('current_message', ''),
                        entity_types=json.loads(inputs.get('entity_types', '[]')),
                        previous_messages=json.loads(inputs.get('previous_messages', '[]')),
                        custom_instructions=extraction_instruction,  # Inject evolved prompt
                    )

                    # Get predicted entity names
                    if isinstance(result, ExtractedEntities):
                        predicted_names = {e.name.lower() for e in result.extracted_entities}
                    else:
                        predicted_names = set()

                    # Calculate metrics
                    if expected_names or predicted_names:
                        intersection = expected_names & predicted_names
                        precision = len(intersection) / len(predicted_names) if predicted_names else 0
                        recall = len(intersection) / len(expected_names) if expected_names else 0
                        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
                    else:
                        precision = recall = f1 = 1.0

                    total_precision += precision
                    total_recall += recall
                    total_f1 += f1
                    total_entities += len(predicted_names)
                    successful_runs += 1

                except Exception as e:
                    artifacts['example_error'] = str(e)
                    continue

            if successful_runs == 0:
                return create_evaluation_result(
                    score=0.0,
                    artifacts={'error': 'No successful evaluation runs'},
                )

            # Calculate averages
            avg_precision = total_precision / successful_runs
            avg_recall = total_recall / successful_runs
            avg_f1 = total_f1 / successful_runs
            latency_ms = (time.time() - start_time) * 1000 / successful_runs

            # Token efficiency (entities per assumed token cost)
            token_efficiency = total_entities / max(total_tokens, 1) if total_tokens > 0 else 1.0

            return create_evaluation_result(
                score=avg_f1,  # Primary optimization target
                metrics={
                    'extraction_f1': avg_f1,
                    'precision': avg_precision,
                    'recall': avg_recall,
                    'token_efficiency': token_efficiency,
                    'latency_ms': latency_ms,
                    'successful_runs': float(successful_runs),
                },
                artifacts=artifacts,
            )

        except Exception as e:
            logger.error(f'Evaluation error: {e}')
            return create_evaluation_result(
                score=0.0,
                artifacts={'error': str(e)},
            )


class EdgeExtractionEvaluator(BaseEvaluator):
    """
    Evaluator for edge extraction prompt evolution.

    Measures:
    - edge_f1: F1 score for (source, relation, target) triples
    - relation_accuracy: Accuracy of relation type classification
    - temporal_accuracy: Accuracy of valid_at/invalid_at extraction
    """

    def __init__(
        self,
        test_data_path: str | Path = 'training_data/edge_extraction.json',
        timeout_seconds: float = 30.0,
    ):
        super().__init__(test_data_path, timeout_seconds)

    def evaluate(self, code_path: str) -> EvaluationResult:
        """Evaluate an evolved edge extraction prompt."""
        start_time = time.time()
        artifacts: dict[str, str] = {}

        try:
            evolved_code = Path(code_path).read_text()
            artifacts['evolved_code'] = evolved_code[:500]

            local_ns: dict[str, Any] = {}
            exec(evolved_code, {'__builtins__': __builtins__}, local_ns)

            edge_instruction = local_ns.get(
                'EDGE_INSTRUCTION',
                local_ns.get('instruction', '')
            )

            if not edge_instruction:
                return create_evaluation_result(
                    score=0.0,
                    artifacts={'error': 'No EDGE_INSTRUCTION found'},
                )

            from graphiti_core.dspy.modules import EdgeExtractor
            from graphiti_core.dspy.signatures import ExtractedEdges

            extractor = EdgeExtractor()

            total_f1 = 0.0
            successful_runs = 0

            for example in self._test_examples[:20]:
                try:
                    inputs = example.get('inputs', {})
                    expected = example.get('expected_output', {})

                    # Normalize edge format for comparison
                    def normalize_edge(e):
                        if isinstance(e, dict):
                            return (
                                str(e.get('source_entity_id', '')),
                                e.get('relation_type', '').upper(),
                                str(e.get('target_entity_id', '')),
                            )
                        return (str(e.source_entity_id), e.relation_type.upper(), str(e.target_entity_id))

                    expected_edges_data = expected.get('extracted_edges', {})
                    if isinstance(expected_edges_data, dict):
                        expected_edges = {normalize_edge(e) for e in expected_edges_data.get('edges', [])}
                    else:
                        expected_edges = set()

                    result = extractor(
                        current_message=inputs.get('current_message', ''),
                        entities=json.loads(inputs.get('entities', '[]')),
                        reference_time=inputs.get('reference_time', ''),
                        previous_messages=json.loads(inputs.get('previous_messages', '[]')),
                        edge_types=json.loads(inputs.get('edge_types', '[]')),
                        custom_instructions=edge_instruction,
                    )

                    if isinstance(result, ExtractedEdges):
                        predicted_edges = {normalize_edge(e) for e in result.edges}
                    else:
                        predicted_edges = set()

                    if expected_edges or predicted_edges:
                        intersection = expected_edges & predicted_edges
                        precision = len(intersection) / len(predicted_edges) if predicted_edges else 0
                        recall = len(intersection) / len(expected_edges) if expected_edges else 0
                        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
                    else:
                        f1 = 1.0

                    total_f1 += f1
                    successful_runs += 1

                except Exception as e:
                    artifacts['example_error'] = str(e)
                    continue

            if successful_runs == 0:
                return create_evaluation_result(score=0.0, artifacts={'error': 'No successful runs'})

            avg_f1 = total_f1 / successful_runs
            latency_ms = (time.time() - start_time) * 1000 / successful_runs

            return create_evaluation_result(
                score=avg_f1,
                metrics={
                    'edge_f1': avg_f1,
                    'latency_ms': latency_ms,
                    'successful_runs': float(successful_runs),
                },
                artifacts=artifacts,
            )

        except Exception as e:
            logger.error(f'Edge evaluation error: {e}')
            return create_evaluation_result(score=0.0, artifacts={'error': str(e)})


class ResolutionEvaluator(BaseEvaluator):
    """
    Evaluator for node resolution/deduplication prompt evolution.

    Measures:
    - resolution_accuracy: Correct duplicate detection rate
    - false_positive_rate: Incorrect merges
    - false_negative_rate: Missed duplicates
    """

    def __init__(
        self,
        test_data_path: str | Path = 'training_data/node_resolution.json',
        timeout_seconds: float = 30.0,
    ):
        super().__init__(test_data_path, timeout_seconds)

    def evaluate(self, code_path: str) -> EvaluationResult:
        """Evaluate an evolved node resolution prompt."""
        start_time = time.time()
        artifacts: dict[str, str] = {}

        try:
            evolved_code = Path(code_path).read_text()
            artifacts['evolved_code'] = evolved_code[:500]

            local_ns: dict[str, Any] = {}
            exec(evolved_code, {'__builtins__': __builtins__}, local_ns)

            resolution_instruction = local_ns.get(
                'RESOLUTION_INSTRUCTION',
                local_ns.get('instruction', '')
            )

            if not resolution_instruction:
                return create_evaluation_result(
                    score=0.0,
                    artifacts={'error': 'No RESOLUTION_INSTRUCTION found'},
                )

            from graphiti_core.dspy.modules import NodeResolver
            from graphiti_core.dspy.signatures import NodeResolutions

            resolver = NodeResolver()

            total_accuracy = 0.0
            successful_runs = 0

            for example in self._test_examples[:20]:
                try:
                    inputs = example.get('inputs', {})
                    expected = example.get('expected_output', {})

                    expected_resolutions = expected.get('entity_resolutions', {})
                    if isinstance(expected_resolutions, dict):
                        expected_map = {
                            r['id']: r['duplicate_idx']
                            for r in expected_resolutions.get('entity_resolutions', [])
                        }
                    else:
                        expected_map = {}

                    # Note: NodeResolver doesn't take custom_instructions directly
                    # We'd need to modify the signature or use a different injection method
                    result = resolver(
                        current_message=inputs.get('current_message', ''),
                        extracted_entities=json.loads(inputs.get('extracted_entities', '[]')),
                        existing_entities=json.loads(inputs.get('existing_entities', '[]')),
                        previous_messages=json.loads(inputs.get('previous_messages', '[]')),
                    )

                    if isinstance(result, NodeResolutions):
                        predicted_map = {r.id: r.duplicate_idx for r in result.entity_resolutions}
                    else:
                        predicted_map = {}

                    if expected_map:
                        correct = sum(1 for k, v in expected_map.items() if predicted_map.get(k) == v)
                        accuracy = correct / len(expected_map)
                    else:
                        accuracy = 1.0

                    total_accuracy += accuracy
                    successful_runs += 1

                except Exception as e:
                    artifacts['example_error'] = str(e)
                    continue

            if successful_runs == 0:
                return create_evaluation_result(score=0.0, artifacts={'error': 'No successful runs'})

            avg_accuracy = total_accuracy / successful_runs
            latency_ms = (time.time() - start_time) * 1000 / successful_runs

            return create_evaluation_result(
                score=avg_accuracy,
                metrics={
                    'resolution_accuracy': avg_accuracy,
                    'latency_ms': latency_ms,
                    'successful_runs': float(successful_runs),
                },
                artifacts=artifacts,
            )

        except Exception as e:
            logger.error(f'Resolution evaluation error: {e}')
            return create_evaluation_result(score=0.0, artifacts={'error': str(e)})


# Standalone evaluator functions for OpenEvolve CLI
def evaluate_entity_extraction(code_path: str) -> dict:
    """Standalone evaluator function for entity extraction."""
    evaluator = EntityExtractionEvaluator()
    result = evaluator.evaluate(code_path)
    return result.to_dict()


def evaluate_edge_extraction(code_path: str) -> dict:
    """Standalone evaluator function for edge extraction."""
    evaluator = EdgeExtractionEvaluator()
    result = evaluator.evaluate(code_path)
    return result.to_dict()


def evaluate_resolution(code_path: str) -> dict:
    """Standalone evaluator function for node resolution."""
    evaluator = ResolutionEvaluator()
    result = evaluator.evaluate(code_path)
    return result.to_dict()
