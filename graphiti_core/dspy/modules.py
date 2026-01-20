"""
DSPy Modules for Graphiti ingestion pipeline.

These modules wrap the signatures with appropriate DSPy predictors,
using ChainOfThought for complex reasoning and TypedPredictor for structured output.
"""

import json
import logging
import os
from typing import Any

import dspy

from .config import with_lm
from .signatures import (
    EntityExtractionSignature,
    EdgeExtractionSignature,
    NodeDeduplicationSignature,
    SummaryGenerationSignature,
    ExtractedEntities,
    ExtractedEdges,
    Edge,
    NodeResolutions,
    Summary,
    SignatureFactory,
)

logger = logging.getLogger(__name__)

_stateful_client = None
_stateful_agent_id = None
_stateful_enabled: bool | None = None

# Training data collection globals
_training_collector = None
_training_collection_enabled: bool | None = None
_training_example_count = 0
_TRAINING_SAVE_INTERVAL = 100  # Save every N examples


def is_stateful_learning_enabled() -> bool:
    """Check if stateful learning is enabled via env var."""
    global _stateful_enabled
    if _stateful_enabled is None:
        _stateful_enabled = os.getenv('ENABLE_STATEFUL_LEARNING', 'true').lower() == 'true'
    return _stateful_enabled


def is_training_collection_enabled() -> bool:
    """Check if training data collection is enabled via env var."""
    global _training_collection_enabled
    if _training_collection_enabled is None:
        _training_collection_enabled = (
            os.getenv('DSPY_COLLECT_TRAINING_DATA', 'false').lower() == 'true'
        )
    return _training_collection_enabled


def _get_training_collector():
    """Get or create the singleton training data collector."""
    global _training_collector

    if not is_training_collection_enabled():
        return None

    if _training_collector is not None:
        return _training_collector

    try:
        from .optimization import TrainingDataCollector

        save_dir = os.getenv('DSPY_TRAINING_DATA_DIR', '/data/training_data')
        _training_collector = TrainingDataCollector(save_dir=save_dir)
        logger.info(f'Training data collection enabled, saving to: {save_dir}')
        return _training_collector
    except Exception as e:
        logger.warning(f'Failed to initialize training data collector: {e}')
        return None


def _maybe_save_training_data() -> None:
    """Save training data periodically based on example count."""
    global _training_example_count
    _training_example_count += 1

    if _training_example_count >= _TRAINING_SAVE_INTERVAL:
        collector = _get_training_collector()
        if collector:
            try:
                collector.save_all()
                stats = collector.get_stats()
                logger.info(f'Saved training data: {stats}')
                _training_example_count = 0
            except Exception as e:
                logger.warning(f'Failed to save training data: {e}')


def save_training_data() -> dict[str, int] | None:
    """
    Explicitly save all collected training data.

    Call this on shutdown or when you want to persist immediately.
    Returns stats dict or None if collection is disabled.
    """
    collector = _get_training_collector()
    if collector is None:
        return None

    try:
        collector.save_all()
        stats = collector.get_stats()
        logger.info(f'Saved training data on demand: {stats}')
        return stats
    except Exception as e:
        logger.warning(f'Failed to save training data: {e}')
        return None


def get_training_stats() -> dict[str, int] | None:
    """Get current training data collection stats without saving."""
    collector = _get_training_collector()
    if collector is None:
        return None
    return collector.get_stats()


def _get_stateful_client():
    global _stateful_client, _stateful_agent_id

    if not is_stateful_learning_enabled():
        return None, None

    if _stateful_client is not None:
        return _stateful_client, _stateful_agent_id

    agent_id = os.getenv('LETTA_GRAPHITI_AGENT_ID')
    if not agent_id:
        return None, None

    try:
        from graphiti_core.utils.stateful_learning import StatefulLearningClient

        _stateful_client = StatefulLearningClient()
        _stateful_agent_id = agent_id
        logger.info(f'Stateful learning enabled with agent: {agent_id[:16]}...')
        return _stateful_client, _stateful_agent_id
    except Exception as e:
        logger.warning(f'Failed to initialize stateful learning: {e}')
        return None, None


class NodeExtractor(dspy.Module):
    """
    Extract entities from text using DSPy.

    Uses ChainOfThought for step-by-step entity identification
    with the complex GLM model (GLM-4.7).
    """

    def __init__(self, enable_stateful: bool = True, signature_class: type | None = None):
        super().__init__()
        sig = signature_class or EntityExtractionSignature
        self.predictor = dspy.ChainOfThought(sig)
        self.enable_stateful = enable_stateful
        self._prompt_version: int | None = None

    @classmethod
    async def create(cls, enable_stateful: bool = True) -> 'NodeExtractor':
        sig, version = await SignatureFactory.get_signature('entity_extraction')
        instance = cls(enable_stateful=enable_stateful, signature_class=sig)
        instance._prompt_version = version
        if version:
            logger.info(f'NodeExtractor using dynamic prompt v{version}')
        return instance

    def _get_extraction_hints(self, current_message: str) -> str:
        if not self.enable_stateful:
            return ''
        client, agent_id = _get_stateful_client()
        if client is None or agent_id is None:
            return ''
        try:
            return client.get_extraction_hints(agent_id, current_message)
        except Exception as e:
            logger.debug(f'Failed to get extraction hints: {e}')
            return ''

    def _store_extraction(self, episode_content: str, entities: list[dict]) -> None:
        if not self.enable_stateful:
            return
        client, agent_id = _get_stateful_client()
        if client is None or agent_id is None:
            return
        try:
            client.store_extraction_memory(agent_id, episode_content, entities)
        except Exception as e:
            logger.debug(f'Failed to store extraction memory: {e}')

    def _record_training_example(
        self,
        current_message: str,
        entity_types: list[dict],
        previous_messages: list[dict] | None,
        result: ExtractedEntities,
    ) -> None:
        collector = _get_training_collector()
        if collector is None:
            return
        try:
            collector.record_entity_extraction(
                current_message=current_message,
                entity_types=entity_types,
                result=result,
                previous_messages=previous_messages,
            )
            _maybe_save_training_data()
        except Exception as e:
            logger.debug(f'Failed to record entity extraction training example: {e}')

    def forward(
        self,
        current_message: str,
        entity_types: list[dict[str, Any]],
        previous_messages: list[dict[str, Any]] | None = None,
        custom_instructions: str = '',
    ) -> ExtractedEntities:
        if self._prompt_version:
            logger.debug(f'NodeExtractor.forward using prompt v{self._prompt_version}')

        previous_extractions = self._get_extraction_hints(current_message)

        with with_lm('complex'):
            result = self.predictor(
                previous_messages=json.dumps(previous_messages or [], indent=2),
                current_message=current_message,
                entity_types=json.dumps(entity_types, indent=2),
                previous_extractions=previous_extractions,
                custom_instructions=custom_instructions,
            )

        extracted = result.extracted_entities
        if isinstance(extracted, ExtractedEntities):
            entities_dicts = [e.model_dump() for e in extracted.extracted_entities]
            self._store_extraction(current_message, entities_dicts)
            self._record_training_example(
                current_message, entity_types, previous_messages, extracted
            )
            return extracted
        elif isinstance(extracted, dict):
            result_obj = ExtractedEntities(**extracted)
            self._store_extraction(current_message, extracted.get('extracted_entities', []))
            self._record_training_example(
                current_message, entity_types, previous_messages, result_obj
            )
            return result_obj
        else:
            logger.warning(f'Unexpected extraction result type: {type(extracted)}')
            return ExtractedEntities(extracted_entities=[])


def _edge_extraction_reward(args: dict, pred: Any) -> float:
    """
    Reward function for edge extraction refinement.

    Returns 1.0 if edges were extracted, 0.0 if empty.
    Used by dspy.Refine to retry extraction on failure.
    """
    try:
        extracted = pred.extracted_edges
        if isinstance(extracted, ExtractedEdges):
            edge_count = len(extracted.edges)
        elif isinstance(extracted, dict):
            edge_count = len(extracted.get('edges', []))
        else:
            edge_count = 0

        return 1.0 if edge_count > 0 else 0.0
    except Exception as e:
        logger.warning(f'Edge extraction reward error: {e}')
        return 0.0


# Few-shot examples for edge extraction - curated golden examples
EDGE_EXTRACTION_DEMOS = [
    {
        'current_message': 'Emmanuel: I just pushed a fix for the FalkorDB sync issue to the graphiti repo.',
        'entities': json.dumps(
            [
                {'id': 0, 'name': 'Emmanuel', 'type': 'Person'},
                {'id': 1, 'name': 'FalkorDB sync issue', 'type': 'Concept'},
                {'id': 2, 'name': 'graphiti repo', 'type': 'Product'},
            ]
        ),
        'reference_time': '2025-01-17T12:00:00Z',
        'previous_messages': '[]',
        'edge_types': '[]',
        'custom_instructions': '',
        'extracted_edges': ExtractedEdges(
            edges=[
                Edge(
                    source_entity_id=0,
                    target_entity_id=1,
                    relation_type='FIXED',
                    fact='Emmanuel pushed a fix for the FalkorDB sync issue',
                    valid_at='2025-01-17T12:00:00Z',
                    invalid_at=None,
                ),
                Edge(
                    source_entity_id=0,
                    target_entity_id=2,
                    relation_type='PUSHED_TO',
                    fact='Emmanuel pushed to the graphiti repo',
                    valid_at='2025-01-17T12:00:00Z',
                    invalid_at=None,
                ),
                Edge(
                    source_entity_id=1,
                    target_entity_id=2,
                    relation_type='LOCATED_IN',
                    fact='The FalkorDB sync issue fix was pushed to graphiti repo',
                    valid_at=None,
                    invalid_at=None,
                ),
            ]
        ),
    },
    {
        'current_message': 'The Temporal worker uses DSPy for entity extraction and stores results in FalkorDB.',
        'entities': json.dumps(
            [
                {'id': 0, 'name': 'Temporal worker', 'type': 'Product'},
                {'id': 1, 'name': 'DSPy', 'type': 'Product'},
                {'id': 2, 'name': 'entity extraction', 'type': 'Concept'},
                {'id': 3, 'name': 'FalkorDB', 'type': 'Product'},
            ]
        ),
        'reference_time': '2025-01-17T12:00:00Z',
        'previous_messages': '[]',
        'edge_types': '[]',
        'custom_instructions': '',
        'extracted_edges': ExtractedEdges(
            edges=[
                Edge(
                    source_entity_id=0,
                    target_entity_id=1,
                    relation_type='USES',
                    fact='Temporal worker uses DSPy',
                    valid_at=None,
                    invalid_at=None,
                ),
                Edge(
                    source_entity_id=1,
                    target_entity_id=2,
                    relation_type='PERFORMS',
                    fact='DSPy is used for entity extraction',
                    valid_at=None,
                    invalid_at=None,
                ),
                Edge(
                    source_entity_id=0,
                    target_entity_id=3,
                    relation_type='STORES_IN',
                    fact='Temporal worker stores results in FalkorDB',
                    valid_at=None,
                    invalid_at=None,
                ),
            ]
        ),
    },
    {
        'current_message': 'Alice joined Google as a senior engineer in their Cloud team last month.',
        'entities': json.dumps(
            [
                {'id': 0, 'name': 'Alice', 'type': 'Person'},
                {'id': 1, 'name': 'Google', 'type': 'Organization'},
                {'id': 2, 'name': 'senior engineer', 'type': 'Concept'},
                {'id': 3, 'name': 'Cloud team', 'type': 'Organization'},
            ]
        ),
        'reference_time': '2025-01-17T12:00:00Z',
        'previous_messages': '[]',
        'edge_types': '[]',
        'custom_instructions': '',
        'extracted_edges': ExtractedEdges(
            edges=[
                Edge(
                    source_entity_id=0,
                    target_entity_id=1,
                    relation_type='WORKS_AT',
                    fact='Alice joined Google',
                    valid_at='2024-12-17T00:00:00Z',
                    invalid_at=None,
                ),
                Edge(
                    source_entity_id=0,
                    target_entity_id=2,
                    relation_type='HAS_ROLE',
                    fact='Alice is a senior engineer',
                    valid_at='2024-12-17T00:00:00Z',
                    invalid_at=None,
                ),
                Edge(
                    source_entity_id=0,
                    target_entity_id=3,
                    relation_type='MEMBER_OF',
                    fact='Alice joined the Cloud team',
                    valid_at='2024-12-17T00:00:00Z',
                    invalid_at=None,
                ),
                Edge(
                    source_entity_id=3,
                    target_entity_id=1,
                    relation_type='PART_OF',
                    fact='Cloud team is part of Google',
                    valid_at=None,
                    invalid_at=None,
                ),
            ]
        ),
    },
]


class EdgeExtractor(dspy.Module):
    """
    Extract relationships/edges between entities using DSPy.

    Uses Predict wrapped in Refine for automatic retry with feedback
    when extraction fails (returns 0 edges). ChainOfThought available
    as opt-in for complex cases requiring explicit reasoning.

    Supports stateful learning via Letta to maintain relation type consistency.
    """

    def __init__(
        self,
        use_cot: bool = False,
        use_refine: bool = True,
        max_retries: int = 3,
        use_demos: bool = True,
        enable_stateful: bool = True,
        signature_class: type | None = None,
    ):
        super().__init__()
        self.use_refine = use_refine
        self.use_demos = use_demos
        self.enable_stateful = enable_stateful
        self._prompt_version: int | None = None

        sig = signature_class or EdgeExtractionSignature

        if use_cot:
            base_predictor = dspy.ChainOfThought(sig)
        else:
            base_predictor = dspy.Predict(sig)

        if use_demos and hasattr(base_predictor, 'demos'):
            base_predictor.demos = EDGE_EXTRACTION_DEMOS  # type: ignore[attr-defined]
            logger.info(f'EdgeExtractor loaded {len(EDGE_EXTRACTION_DEMOS)} few-shot demos')

        if use_refine:
            self.predictor = dspy.Refine(
                module=base_predictor,
                N=max_retries,
                reward_fn=_edge_extraction_reward,
                threshold=1.0,
                fail_count=max_retries,
            )
            logger.info(f'EdgeExtractor initialized with Refine (max_retries={max_retries})')
        else:
            self.predictor = base_predictor

    @classmethod
    async def create(
        cls,
        use_cot: bool = False,
        use_refine: bool = True,
        max_retries: int = 3,
        use_demos: bool = True,
        enable_stateful: bool = True,
    ) -> 'EdgeExtractor':
        sig, version = await SignatureFactory.get_signature('edge_extraction')
        instance = cls(
            use_cot=use_cot,
            use_refine=use_refine,
            max_retries=max_retries,
            use_demos=use_demos,
            enable_stateful=enable_stateful,
            signature_class=sig,
        )
        instance._prompt_version = version
        if version:
            logger.info(f'EdgeExtractor using dynamic prompt v{version}')
        return instance

    def _get_edge_hints(self, entity_names: list[str]) -> str:
        if not self.enable_stateful:
            return ''
        client, agent_id = _get_stateful_client()
        if client is None or agent_id is None:
            return ''
        try:
            return client.get_edge_hints(agent_id, entity_names)
        except Exception as e:
            logger.warning(f'Failed to get edge hints: {e}')
            return ''

    def _store_edges(self, edges: list[Any]) -> None:
        if not self.enable_stateful:
            return
        client, agent_id = _get_stateful_client()
        if client is None or agent_id is None:
            return
        try:
            for edge in edges[:5]:
                client.store_edge_memory(
                    agent_id,
                    edge.get('source_entity_name', ''),
                    edge.get('target_entity_name', ''),
                    edge.get('relation_type', ''),
                    edge.get('fact', ''),
                )
        except Exception as e:
            logger.warning(f'Failed to store edges: {e}')

    def _record_training_example(
        self,
        current_message: str,
        entities: list[dict],
        reference_time: str,
        previous_messages: list[dict] | None,
        result: ExtractedEdges,
    ) -> None:
        collector = _get_training_collector()
        if collector is None:
            return
        try:
            collector.record_edge_extraction(
                current_message=current_message,
                entities=entities,
                reference_time=reference_time,
                result=result,
                previous_messages=previous_messages,
            )
            _maybe_save_training_data()
        except Exception as e:
            logger.debug(f'Failed to record edge extraction training example: {e}')

    def forward(
        self,
        current_message: str,
        entities: list[dict[str, Any]],
        reference_time: str,
        previous_messages: list[dict[str, Any]] | None = None,
        edge_types: list[dict[str, Any]] | None = None,
        custom_instructions: str = '',
    ) -> ExtractedEdges:
        if self._prompt_version:
            logger.debug(f'EdgeExtractor.forward using prompt v{self._prompt_version}')

        entity_names = [e.get('name', '') for e in entities]
        edge_patterns = self._get_edge_hints(entity_names)

        with with_lm('complex'):
            result = self.predictor(
                previous_messages=json.dumps(previous_messages or [], indent=2),
                current_message=current_message,
                entities=json.dumps(entities, indent=2),
                reference_time=reference_time,
                edge_types=json.dumps(edge_types or [], indent=2),
                custom_instructions=custom_instructions,
                edge_patterns=edge_patterns,
            )

        extracted = result.extracted_edges
        if isinstance(extracted, ExtractedEdges):
            parsed = extracted
        elif isinstance(extracted, dict):
            parsed = ExtractedEdges(**extracted)
        else:
            logger.warning(f'Unexpected edge extraction result type: {type(extracted)}')
            return ExtractedEdges(edges=[])

        if parsed.edges:
            self._store_edges(
                [e.model_dump() if hasattr(e, 'model_dump') else e for e in parsed.edges]
            )
            self._record_training_example(
                current_message, entities, reference_time, previous_messages, parsed
            )

        return parsed


class NodeResolver(dspy.Module):
    """
    Resolve/deduplicate entities against existing entities using DSPy.

    Uses ChainOfThought for semantic comparison and duplicate detection
    with the complex GLM model (GLM-4.7).

    Supports stateful learning via Letta to remember past resolution decisions.
    """

    def __init__(self, enable_stateful: bool = True, signature_class: type | None = None):
        super().__init__()
        sig = signature_class or NodeDeduplicationSignature
        self.predictor = dspy.ChainOfThought(sig)
        self.enable_stateful = enable_stateful
        self._prompt_version: int | None = None

    @classmethod
    async def create(cls, enable_stateful: bool = True) -> 'NodeResolver':
        sig, version = await SignatureFactory.get_signature('node_resolution')
        instance = cls(enable_stateful=enable_stateful, signature_class=sig)
        instance._prompt_version = version
        if version:
            logger.info(f'NodeResolver using dynamic prompt v{version}')
        return instance

    def _get_resolution_hints(self, entity_names: list[str]) -> str:
        """Get resolution hints from Letta memory."""
        if not self.enable_stateful:
            return ''
        client, agent_id = _get_stateful_client()
        if client is None or agent_id is None:
            return ''
        try:
            return client.get_resolution_hints(agent_id, entity_names)
        except Exception as e:
            logger.warning(f'Failed to get resolution hints: {e}')
            return ''

    def _store_resolution(
        self,
        entity_name: str,
        resolved_to: str,
        is_duplicate: bool,
        context: str = '',
    ) -> None:
        """Store a resolution decision to Letta memory."""
        if not self.enable_stateful:
            return
        client, agent_id = _get_stateful_client()
        if client is None or agent_id is None:
            return
        try:
            client.store_resolution_memory(
                agent_id, entity_name, resolved_to, is_duplicate, context
            )
        except Exception as e:
            logger.warning(f'Failed to store resolution: {e}')

    def _record_training_example(
        self,
        current_message: str,
        extracted_entities: list[dict],
        existing_entities: list[dict],
        previous_messages: list[dict] | None,
        result: NodeResolutions,
    ) -> None:
        collector = _get_training_collector()
        if collector is None:
            return
        try:
            collector.record_node_resolution(
                current_message=current_message,
                extracted_entities=extracted_entities,
                existing_entities=existing_entities,
                result=result,
                previous_messages=previous_messages,
            )
            _maybe_save_training_data()
        except Exception as e:
            logger.debug(f'Failed to record node resolution training example: {e}')

    def forward(
        self,
        current_message: str,
        extracted_entities: list[dict[str, Any]],
        existing_entities: list[dict[str, Any]],
        previous_messages: list[dict[str, Any]] | None = None,
    ) -> NodeResolutions:
        """
        Resolve entities against existing entities for deduplication.

        Args:
            current_message: The source message for context.
            extracted_entities: Newly extracted entities to deduplicate.
            existing_entities: Existing entities with candidate idx.
            previous_messages: Previous context messages.

        Returns:
            NodeResolutions with duplicate information for each entity.
        """
        if self._prompt_version:
            logger.debug(f'NodeResolver.forward using prompt v{self._prompt_version}')

        entity_names = [e.get('name', '') for e in extracted_entities]
        resolution_history = self._get_resolution_hints(entity_names)

        with with_lm('complex'):
            result = self.predictor(
                previous_messages=json.dumps(previous_messages or [], indent=2),
                current_message=current_message,
                extracted_entities=json.dumps(extracted_entities, indent=2),
                existing_entities=json.dumps(existing_entities, indent=2),
                resolution_history=resolution_history,
            )

        resolutions = result.entity_resolutions
        if isinstance(resolutions, NodeResolutions):
            parsed_resolutions = resolutions
        elif isinstance(resolutions, dict):
            parsed_resolutions = NodeResolutions(**resolutions)
        else:
            logger.warning(f'Unexpected resolution result type: {type(resolutions)}')
            return NodeResolutions(entity_resolutions=[])

        for resolution in parsed_resolutions.entity_resolutions:
            entity_name = resolution.name
            is_duplicate = resolution.duplicate_idx >= 0

            if is_duplicate and existing_entities:
                resolved_to = existing_entities[resolution.duplicate_idx].get('name', 'unknown')
                self._store_resolution(
                    entity_name=entity_name,
                    resolved_to=resolved_to,
                    is_duplicate=True,
                    context=f'Resolved in context: {current_message[:100]}...',
                )

        self._record_training_example(
            current_message,
            extracted_entities,
            existing_entities,
            previous_messages,
            parsed_resolutions,
        )

        return parsed_resolutions


class SummaryGenerator(dspy.Module):
    """
    Generate entity summaries using DSPy.

    Uses basic Predict (not ChainOfThought) for efficiency
    with the simple GLM model (GLM-4.5) for cost optimization.
    """

    def __init__(self, signature_class: type | None = None):
        super().__init__()
        sig = signature_class or SummaryGenerationSignature
        self.predictor = dspy.Predict(sig)
        self._prompt_version: int | None = None

    @classmethod
    async def create(cls) -> 'SummaryGenerator':
        sig, version = await SignatureFactory.get_signature('summary_generation')
        instance = cls(signature_class=sig)
        instance._prompt_version = version
        if version:
            logger.info(f'SummaryGenerator using dynamic prompt v{version}')
        return instance

    def _record_training_example(
        self,
        current_message: str,
        entity_name: str,
        previous_messages: list[dict] | None,
        existing_summary: str,
        result: Summary,
    ) -> None:
        collector = _get_training_collector()
        if collector is None:
            return
        try:
            collector.record_summary_generation(
                current_message=current_message,
                entity_name=entity_name,
                result=result,
                previous_messages=previous_messages,
                existing_summary=existing_summary,
            )
            _maybe_save_training_data()
        except Exception as e:
            logger.debug(f'Failed to record summary generation training example: {e}')

    def forward(
        self,
        current_message: str,
        entity_name: str,
        previous_messages: list[dict[str, Any]] | None = None,
        existing_summary: str = '',
    ) -> Summary:
        """
        Generate or update a summary for an entity.

        Args:
            current_message: The source message containing entity info.
            entity_name: Name of the entity to summarize.
            previous_messages: Previous context messages.
            existing_summary: Existing summary to update.

        Returns:
            Summary with updated entity summary.
        """
        if self._prompt_version:
            logger.debug(f'SummaryGenerator.forward using prompt v{self._prompt_version}')

        with with_lm('simple'):
            result = self.predictor(
                previous_messages=json.dumps(previous_messages or [], indent=2),
                current_message=current_message,
                entity_name=entity_name,
                existing_summary=existing_summary,
            )

        summary = result.summary
        if isinstance(summary, Summary):
            parsed = summary
        elif isinstance(summary, dict):
            parsed = Summary(**summary)
        elif isinstance(summary, str):
            parsed = Summary(summary=summary)
        else:
            logger.warning(f'Unexpected summary result type: {type(summary)}')
            return Summary(summary='')

        if parsed.summary:
            self._record_training_example(
                current_message, entity_name, previous_messages, existing_summary, parsed
            )

        return parsed


# ============================================================================
# Batch Processing Utilities
# ============================================================================


class BatchNodeExtractor(dspy.Module):
    """
    Extract entities from multiple episodes in batch.

    Useful for processing episode history efficiently.
    """

    def __init__(self):
        super().__init__()
        self.extractor = NodeExtractor()

    def forward(
        self,
        episodes: list[dict[str, Any]],
        entity_types: list[dict[str, Any]],
        custom_instructions: str = '',
    ) -> list[ExtractedEntities]:
        """
        Extract entities from multiple episodes.

        Args:
            episodes: List of episode dicts with 'content' field.
            entity_types: Entity type definitions.
            custom_instructions: Additional instructions.

        Returns:
            List of ExtractedEntities, one per episode.
        """
        results = []
        for i, episode in enumerate(episodes):
            # Previous episodes are all episodes before this one
            previous = episodes[:i] if i > 0 else []
            result = self.extractor(
                current_message=episode.get('content', ''),
                entity_types=entity_types,
                previous_messages=previous,
                custom_instructions=custom_instructions,
            )
            results.append(result)
        return results


class BatchSummaryGenerator(dspy.Module):
    """
    Generate summaries for multiple entities in batch.

    Uses the simple model for cost efficiency on high-volume summary tasks.
    """

    def __init__(self):
        super().__init__()
        self.generator = SummaryGenerator()

    def forward(
        self,
        entities: list[dict[str, Any]],
        current_message: str,
        previous_messages: list[dict[str, Any]] | None = None,
    ) -> list[Summary]:
        """
        Generate summaries for multiple entities.

        Args:
            entities: List of entity dicts with 'name' and optional 'summary' fields.
            current_message: Source message for context.
            previous_messages: Previous context messages.

        Returns:
            List of Summary objects, one per entity.
        """
        results = []
        for entity in entities:
            result = self.generator(
                current_message=current_message,
                entity_name=entity.get('name', ''),
                previous_messages=previous_messages,
                existing_summary=entity.get('summary', ''),
            )
            results.append(result)
        return results
