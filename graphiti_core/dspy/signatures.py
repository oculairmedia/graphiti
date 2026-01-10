"""
DSPy Signatures for Graphiti ingestion pipeline.

These signatures define the input/output contracts for each pipeline stage,
reusing existing Pydantic models where possible for consistency.
"""

from pydantic import BaseModel, Field
import dspy


# ============================================================================
# Pydantic Output Models (reused from existing prompts)
# ============================================================================

class ExtractedEntity(BaseModel):
    """A single extracted entity."""
    name: str = Field(..., description='Name of the extracted entity')
    entity_type_id: int = Field(
        ...,
        description='ID of the classified entity type from the provided entity types list'
    )


class ExtractedEntities(BaseModel):
    """List of extracted entities from text."""
    extracted_entities: list[ExtractedEntity] = Field(
        default_factory=list,
        description='List of extracted entities'
    )


class Edge(BaseModel):
    """A factual relationship between two entities."""
    relation_type: str = Field(
        ...,
        description='FACT_PREDICATE_IN_SCREAMING_SNAKE_CASE (e.g., WORKS_AT, FOUNDED)'
    )
    source_entity_id: int = Field(
        ...,
        description='The id of the source entity'
    )
    target_entity_id: int = Field(
        ...,
        description='The id of the target entity'
    )
    fact: str = Field(
        ...,
        description='The factual statement describing this relationship'
    )
    valid_at: str | None = Field(
        None,
        description='ISO 8601 datetime when this fact became true (e.g., 2025-01-01T00:00:00Z)'
    )
    invalid_at: str | None = Field(
        None,
        description='ISO 8601 datetime when this fact stopped being true'
    )


class ExtractedEdges(BaseModel):
    """List of extracted edges/relationships."""
    edges: list[Edge] = Field(
        default_factory=list,
        description='List of extracted edges'
    )


class NodeDuplicate(BaseModel):
    """Resolution result for a single entity."""
    id: int = Field(..., description='Integer id of the entity (zero-based)')
    duplicate_idx: int = Field(
        ...,
        description='Index of the duplicate entity, or -1 if no duplicate found'
    )
    name: str = Field(
        ...,
        description='Most complete and descriptive name for this entity'
    )
    duplicates: list[int] = Field(
        default_factory=list,
        description='Indices of all duplicate entities'
    )


class NodeResolutions(BaseModel):
    """Deduplication results for a batch of entities."""
    entity_resolutions: list[NodeDuplicate] = Field(
        default_factory=list,
        description='List of resolved nodes with duplicate information'
    )


class Summary(BaseModel):
    """Entity summary."""
    summary: str = Field(
        ...,
        description='Summary containing important information about the entity (under 250 words)'
    )


# ============================================================================
# DSPy Signatures
# ============================================================================

class EntityExtractionSignature(dspy.Signature):
    """Extract entities from conversational text or documents.

    Given a current message and optional previous context, identify and classify
    all significant entities mentioned explicitly or implicitly.
    """

    previous_messages: str = dspy.InputField(
        desc='Previous messages for context (JSON array)'
    )
    current_message: str = dspy.InputField(
        desc='The current message to extract entities from'
    )
    entity_types: str = dspy.InputField(
        desc='Available entity types with their IDs and descriptions (JSON)'
    )
    custom_instructions: str = dspy.InputField(
        desc='Optional custom extraction instructions',
        default=''
    )

    extracted_entities: ExtractedEntities = dspy.OutputField(
        desc='Extracted entities with their names and type IDs'
    )


class EdgeExtractionSignature(dspy.Signature):
    """Extract factual relationships between entities.

    Given entities and context, identify all factual relationships between them
    with temporal information when available.
    """

    previous_messages: str = dspy.InputField(
        desc='Previous messages for context (JSON array)'
    )
    current_message: str = dspy.InputField(
        desc='The current message to extract facts from'
    )
    entities: str = dspy.InputField(
        desc='Entities extracted from the message (JSON array with id, name, type)'
    )
    reference_time: str = dspy.InputField(
        desc='Reference timestamp for resolving relative time expressions (ISO 8601)'
    )
    edge_types: str = dspy.InputField(
        desc='Available edge/fact types with descriptions (JSON)',
        default=''
    )
    custom_instructions: str = dspy.InputField(
        desc='Optional custom extraction instructions',
        default=''
    )

    extracted_edges: ExtractedEdges = dspy.OutputField(
        desc='Extracted edges/relationships between entities'
    )


class NodeDeduplicationSignature(dspy.Signature):
    """Determine if extracted entities are duplicates of existing entities.

    Compare new entities against existing ones to identify duplicates,
    considering semantic equivalence and real-world identity.
    """

    previous_messages: str = dspy.InputField(
        desc='Previous messages for context (JSON array)'
    )
    current_message: str = dspy.InputField(
        desc='The current message entities were extracted from'
    )
    extracted_entities: str = dspy.InputField(
        desc='Newly extracted entities to deduplicate (JSON array)'
    )
    existing_entities: str = dspy.InputField(
        desc='Existing entities to compare against (JSON array with candidate idx)'
    )

    entity_resolutions: NodeResolutions = dspy.OutputField(
        desc='Resolution results indicating duplicates for each entity'
    )


class SummaryGenerationSignature(dspy.Signature):
    """Generate a summary for an entity based on available context.

    Create a concise summary (under 250 words) capturing the important
    information about an entity from the provided messages.
    """

    previous_messages: str = dspy.InputField(
        desc='Previous messages for context (JSON array)'
    )
    current_message: str = dspy.InputField(
        desc='The current message containing entity information'
    )
    entity_name: str = dspy.InputField(
        desc='Name of the entity to summarize'
    )
    existing_summary: str = dspy.InputField(
        desc='Existing summary to update (if any)',
        default=''
    )

    summary: Summary = dspy.OutputField(
        desc='Updated summary for the entity (under 250 words)'
    )
