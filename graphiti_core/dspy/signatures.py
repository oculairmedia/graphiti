"""
DSPy Signatures for Graphiti ingestion pipeline.

These signatures define the input/output contracts for each pipeline stage,
reusing existing Pydantic models where possible for consistency.
"""

from typing import Any

from pydantic import BaseModel, Field, model_validator
import dspy

from graphiti_core.prompts.extract_nodes import ExtractedEntity, ExtractedEntities


# ============================================================================
# Pydantic Output Models (reused from existing prompts)
# ============================================================================


class Edge(BaseModel):
    """A factual relationship between two entities."""

    relation_type: str = Field(
        ..., description='FACT_PREDICATE_IN_SCREAMING_SNAKE_CASE (e.g., WORKS_AT, FOUNDED)'
    )
    source_entity_id: int = Field(..., description='The id of the source entity')
    target_entity_id: int = Field(..., description='The id of the target entity')
    fact: str = Field(..., description='The factual statement describing this relationship')
    valid_at: str | None = Field(
        None,
        description='ISO 8601 datetime when this fact became true (e.g., 2025-01-01T00:00:00Z)',
    )
    invalid_at: str | None = Field(
        None, description='ISO 8601 datetime when this fact stopped being true'
    )


class ExtractedEdges(BaseModel):
    """List of extracted edges/relationships."""

    edges: list[Edge] = Field(default_factory=list, description='List of extracted edges')

    @model_validator(mode='before')
    @classmethod
    def wrap_bare_list(cls, data: Any) -> Any:
        if isinstance(data, list):
            return {'edges': data}
        return data


class NodeDuplicate(BaseModel):
    """Resolution result for a single entity."""

    id: int = Field(..., description='Integer id of the entity (zero-based)')
    duplicate_idx: int = Field(
        ..., description='Index of the duplicate entity, or -1 if no duplicate found'
    )
    name: str = Field(..., description='Most complete and descriptive name for this entity')
    duplicates: list[int] = Field(
        default_factory=list, description='Indices of all duplicate entities'
    )


class NodeResolutions(BaseModel):
    """Deduplication results for a batch of entities."""

    entity_resolutions: list[NodeDuplicate] = Field(
        default_factory=list, description='List of resolved nodes with duplicate information'
    )

    @model_validator(mode='before')
    @classmethod
    def wrap_bare_list(cls, data: Any) -> Any:
        if isinstance(data, list):
            return {'entity_resolutions': data}
        return data


class Summary(BaseModel):
    """Entity summary."""

    summary: str = Field(
        ...,
        description='Summary containing important information about the entity (under 250 words)',
    )


# ============================================================================
# DSPy Signatures
# ============================================================================


class EntityExtractionSignature(dspy.Signature):
    """Extract ALL significant entities from text with high precision.

    You are an expert entity extractor. Identify and classify every significant entity
    mentioned explicitly or implicitly in the current message.

    EXTRACTION RULES:
    1. Extract the speaker (before the colon) as the first entity if present
    2. Entity names must be verbatim substrings from the text (clean boundaries)
    3. Use full names including titles (e.g., "Dr. Elena Garcia", "Python 3.11")
    4. Break down nested references: "Google's BERT" -> extract "Google" AND "BERT" separately
    5. Classify each entity using exactly one entity_type_id from the provided types
    6. Use consistent naming from previous_extractions when referring to the same entity

    WHAT TO EXTRACT:
    - Named people, organizations, products, locations, concepts
    - Technical terms: services, tools, files, projects, APIs, libraries
    - Specific identifiers: versions, paths, configuration names

    WHAT TO EXCLUDE:
    - Relationships or actions (these become edges)
    - Dates, times, temporal information (handled separately)
    - Pronouns, generic nouns ("the project", "the system")
    - Entities only in previous messages (context only)
    """

    previous_messages: str = dspy.InputField(desc='Previous messages for context (JSON array)')
    current_message: str = dspy.InputField(desc='The current message to extract ALL entities from')
    entity_types: str = dspy.InputField(
        desc='Entity types with IDs and descriptions - classify each entity with one type_id'
    )
    previous_extractions: str = dspy.InputField(
        desc='Entity names from recent extractions for naming consistency (use same names for same entities)',
        default='',
    )
    custom_instructions: str = dspy.InputField(
        desc='Optional custom extraction instructions', default=''
    )

    extracted_entities: ExtractedEntities = dspy.OutputField(
        desc='ALL extracted entities with names and type IDs - be thorough'
    )


class EdgeExtractionSignature(dspy.Signature):
    """Extract ALL factual relationships between entities from text.

    You are an expert fact extractor. Given entities and context, identify every factual
    relationship between them. Be thorough - extract all relationships, not just obvious ones.

    EXTRACTION RULES:
    1. Extract ALL facts where both subject and object are in the entities list
    2. Each fact must involve two DISTINCT entities (not self-referential)
    3. Use SCREAMING_SNAKE_CASE for relation_type (e.g., WORKS_AT, CREATED, USES, DEPENDS_ON)
    4. The fact field should quote or closely paraphrase the source text
    5. Do not emit duplicate or semantically redundant facts
    6. Look for: actions, ownership, membership, creation, usage, dependencies, locations, etc.

    COMMON RELATION TYPES (not exhaustive - use any appropriate type):
    - WORKS_AT, WORKS_ON, CREATED, MODIFIED, USES, DEPENDS_ON
    - MEMBER_OF, PART_OF, LOCATED_IN, OWNS, MANAGES
    - RELATED_TO, REFERENCES, CALLS, IMPLEMENTS, EXTENDS

    DATETIME RULES:
    - Use ISO 8601 with Z suffix (e.g., 2025-04-30T00:00:00Z)
    - Set valid_at to reference_time for present-tense facts
    - Leave timestamps null if no time is stated or implied
    """

    previous_messages: str = dspy.InputField(desc='Previous messages for context (JSON array)')
    current_message: str = dspy.InputField(desc='The current message to extract ALL facts from')
    entities: str = dspy.InputField(
        desc='Entities extracted from the message (JSON array with id, name, type)'
    )
    reference_time: str = dspy.InputField(
        desc='Reference timestamp for resolving relative time expressions (ISO 8601)'
    )
    edge_types: str = dspy.InputField(
        desc='Suggested edge types (JSON) - extract these AND any other relationships found',
        default='',
    )
    custom_instructions: str = dspy.InputField(
        desc='Optional custom extraction instructions', default=''
    )

    extracted_edges: ExtractedEdges = dspy.OutputField(
        desc='ALL extracted edges/relationships between entities - be thorough'
    )


class NodeDeduplicationSignature(dspy.Signature):
    """Determine if extracted entities are duplicates of existing entities.

    You are an expert at entity resolution. Compare each NEW entity against EXISTING entities
    to identify duplicates, considering semantic equivalence and real-world identity.

    IMPORTANT ID RULES:
    1. Entity "id" values are zero-based integers - return them exactly as given
    2. Candidate "idx" values are also zero-based - use the provided values
    3. Do NOT renumber or convert to 1-based indexing

    DUPLICATE DETECTION RULES:
    1. Entities are duplicates ONLY if they refer to the SAME real-world object or concept
    2. Semantic equivalence: if a descriptive label clearly refers to a named entity, treat as duplicate
       Example: "the knowledge graph system" and "Graphiti" are duplicates if context confirms they're the same
    3. Use context from previous messages to resolve ambiguous references

    DO NOT MARK AS DUPLICATES:
    - Related but distinct entities (e.g., "Python" vs "Python 3.11" if both are mentioned separately)
    - Similar names referring to different instances (e.g., two different "John Smith" people)
    - Parent/child relationships (e.g., "Google" and "Google Cloud" are separate entities)

    OUTPUT REQUIREMENTS:
    For each entity, return:
    - id: the exact integer id from the input (zero-based)
    - duplicate_idx: index of the FIRST matching existing entity, or -1 if none
    - duplicates: list of ALL matching existing entity indices (empty if none)
    - name: the most complete/descriptive name (from new entity, existing, or combined)
    """

    previous_messages: str = dspy.InputField(desc='Previous messages for context (JSON array)')
    current_message: str = dspy.InputField(desc='The current message entities were extracted from')
    extracted_entities: str = dspy.InputField(
        desc='Newly extracted entities to deduplicate (JSON array with id, name, entity_type)'
    )
    existing_entities: str = dspy.InputField(
        desc='Existing entities to compare against (JSON array with candidate idx, name, entity_type)'
    )
    resolution_history: str = dspy.InputField(
        desc='Previous resolution decisions for context (may be empty)',
        default='',
    )

    entity_resolutions: NodeResolutions = dspy.OutputField(
        desc='Resolution for EACH extracted entity with duplicate information'
    )


class SummaryGenerationSignature(dspy.Signature):
    """Generate or update an entity summary based on new context.

    You are an expert at synthesizing information about entities. Create a concise,
    informative summary (under 250 words) that captures the most important facts.

    SUMMARY RULES:
    1. If existing_summary is provided, UPDATE it by integrating new information
    2. Preserve important facts from the existing summary - don't lose information
    3. Resolve contradictions: newer information takes precedence over older
    4. Focus on factual, verifiable information from the messages

    CONTENT GUIDELINES:
    - Include: roles, relationships, key actions, attributes, affiliations
    - Exclude: speculation, opinions, ephemeral details
    - Use third person ("X is..." not "You are...")
    - Be specific: prefer "CEO of Acme Corp since 2020" over "a business leader"

    STYLE:
    - Concise, professional prose
    - No bullet points or lists
    - Under 250 words
    """

    previous_messages: str = dspy.InputField(desc='Previous messages for context (JSON array)')
    current_message: str = dspy.InputField(desc='The current message containing entity information')
    entity_name: str = dspy.InputField(desc='Name of the entity to summarize')
    existing_summary: str = dspy.InputField(desc='Existing summary to update (if any)', default='')

    summary: Summary = dspy.OutputField(desc='Updated summary for the entity (under 250 words)')
