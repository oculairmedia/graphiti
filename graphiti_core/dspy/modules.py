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


class EdgeExtractor(dspy.Module):
    """
    Extract relationships/edges between entities using DSPy.

    Uses Predict for faster extraction (ChainOfThought adds ~30s overhead).
    """

    def __init__(self, use_cot: bool = False):
        super().__init__()
        # Predict is faster; ChainOfThought adds reasoning but 30s+ latency
        if use_cot:
            self.predictor = dspy.ChainOfThought(EdgeExtractionSignature)
        else:
            self.predictor = dspy.Predict(EdgeExtractionSignature)

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
