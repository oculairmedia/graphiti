"""
DSPy Modules for Graphiti ingestion pipeline.

These modules wrap the signatures with appropriate DSPy predictors,
using ChainOfThought for complex reasoning and TypedPredictor for structured output.
"""

import json
import logging
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
)

logger = logging.getLogger(__name__)


class NodeExtractor(dspy.Module):
    """
    Extract entities from text using DSPy.

    Uses ChainOfThought for step-by-step entity identification
    with the complex GLM model (GLM-4.7).
    """

    def __init__(self):
        super().__init__()
        self.predictor = dspy.ChainOfThought(EntityExtractionSignature)

    def forward(
        self,
        current_message: str,
        entity_types: list[dict[str, Any]],
        previous_messages: list[dict[str, Any]] | None = None,
        custom_instructions: str = '',
    ) -> ExtractedEntities:
        """
        Extract entities from text.

        Args:
            current_message: The text to extract entities from.
            entity_types: List of entity type definitions with id, name, description.
            previous_messages: Previous context messages.
            custom_instructions: Additional extraction instructions.

        Returns:
            ExtractedEntities with list of extracted entities.
        """
        with with_lm('complex'):
            result = self.predictor(
                previous_messages=json.dumps(previous_messages or [], indent=2),
                current_message=current_message,
                entity_types=json.dumps(entity_types, indent=2),
                custom_instructions=custom_instructions,
            )

        # Extract the structured output
        extracted = result.extracted_entities
        if isinstance(extracted, ExtractedEntities):
            return extracted
        elif isinstance(extracted, dict):
            return ExtractedEntities(**extracted)
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
    """

    def __init__(
        self,
        use_cot: bool = False,
        use_refine: bool = True,
        max_retries: int = 3,
        use_demos: bool = True,
    ):
        """
        Initialize EdgeExtractor.

        Args:
            use_cot: Use ChainOfThought for explicit reasoning (adds ~30s latency).
            use_refine: Use dspy.Refine to auto-retry on empty extraction.
            max_retries: Maximum retry attempts for Refine (default 3).
            use_demos: Include few-shot examples to guide extraction.
        """
        super().__init__()
        self.use_refine = use_refine
        self.use_demos = use_demos

        if use_cot:
            base_predictor = dspy.ChainOfThought(EdgeExtractionSignature)
        else:
            base_predictor = dspy.Predict(EdgeExtractionSignature)

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

    def forward(
        self,
        current_message: str,
        entities: list[dict[str, Any]],
        reference_time: str,
        previous_messages: list[dict[str, Any]] | None = None,
        edge_types: list[dict[str, Any]] | None = None,
        custom_instructions: str = '',
    ) -> ExtractedEdges:
        """
        Extract edges/relationships from text.

        Args:
            current_message: The text to extract relationships from.
            entities: Extracted entities with id, name, type.
            reference_time: ISO 8601 timestamp for resolving relative times.
            previous_messages: Previous context messages.
            edge_types: Available edge type definitions.
            custom_instructions: Additional extraction instructions.

        Returns:
            ExtractedEdges with list of extracted relationships.
        """
        # Use complex model for edge extraction - more reliable
        with with_lm('complex'):
            result = self.predictor(
                previous_messages=json.dumps(previous_messages or [], indent=2),
                current_message=current_message,
                entities=json.dumps(entities, indent=2),
                reference_time=reference_time,
                edge_types=json.dumps(edge_types or [], indent=2),
                custom_instructions=custom_instructions,
            )

        # Extract the structured output
        extracted = result.extracted_edges
        if isinstance(extracted, ExtractedEdges):
            return extracted
        elif isinstance(extracted, dict):
            return ExtractedEdges(**extracted)
        else:
            logger.warning(f'Unexpected edge extraction result type: {type(extracted)}')
            return ExtractedEdges(edges=[])


class NodeResolver(dspy.Module):
    """
    Resolve/deduplicate entities against existing entities using DSPy.

    Uses ChainOfThought for semantic comparison and duplicate detection
    with the complex GLM model (GLM-4.7).
    """

    def __init__(self):
        super().__init__()
        self.predictor = dspy.ChainOfThought(NodeDeduplicationSignature)

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
        with with_lm('complex'):
            result = self.predictor(
                previous_messages=json.dumps(previous_messages or [], indent=2),
                current_message=current_message,
                extracted_entities=json.dumps(extracted_entities, indent=2),
                existing_entities=json.dumps(existing_entities, indent=2),
            )

        # Extract the structured output
        resolutions = result.entity_resolutions
        if isinstance(resolutions, NodeResolutions):
            return resolutions
        elif isinstance(resolutions, dict):
            return NodeResolutions(**resolutions)
        else:
            logger.warning(f'Unexpected resolution result type: {type(resolutions)}')
            return NodeResolutions(entity_resolutions=[])


class SummaryGenerator(dspy.Module):
    """
    Generate entity summaries using DSPy.

    Uses basic Predict (not ChainOfThought) for efficiency
    with the simple GLM model (GLM-4.5) for cost optimization.
    """

    def __init__(self):
        super().__init__()
        # Use basic Predict for summaries - simpler task, lower cost model
        self.predictor = dspy.Predict(SummaryGenerationSignature)

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
        # Use simple model for summaries (high volume, lower complexity)
        with with_lm('simple'):
            result = self.predictor(
                previous_messages=json.dumps(previous_messages or [], indent=2),
                current_message=current_message,
                entity_name=entity_name,
                existing_summary=existing_summary,
            )

        # Extract the structured output
        summary = result.summary
        if isinstance(summary, Summary):
            return summary
        elif isinstance(summary, dict):
            return Summary(**summary)
        elif isinstance(summary, str):
            return Summary(summary=summary)
        else:
            logger.warning(f'Unexpected summary result type: {type(summary)}')
            return Summary(summary='')


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
