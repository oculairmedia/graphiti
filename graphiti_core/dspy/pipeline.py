"""
DSPy Ingestion Pipeline for Graphiti.

This module provides a complete DSPy-based ingestion pipeline that can run
in parallel with the existing Graphiti pipeline for comparison and verification.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import dspy

from .config import configure_lm, get_lm_config


def _extract_token_usage(lm: dspy.LM | None = None) -> tuple[int, int]:
    """
    Extract token usage from the last DSPy LM call.

    Returns:
        Tuple of (prompt_tokens, completion_tokens).
    """
    try:
        # Get history from the configured LM
        target_lm = lm or dspy.settings.lm
        if target_lm and hasattr(target_lm, 'history') and target_lm.history:
            last_call = target_lm.history[-1]
            # LiteLLM/OpenAI format
            if isinstance(last_call, dict):
                usage = last_call.get('usage', {})
                return (
                    usage.get('prompt_tokens', 0),
                    usage.get('completion_tokens', 0),
                )
            # DSPy response format
            if hasattr(last_call, 'usage'):
                return (
                    getattr(last_call.usage, 'prompt_tokens', 0),
                    getattr(last_call.usage, 'completion_tokens', 0),
                )
    except Exception:
        pass
    return (0, 0)


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
from .response_logger import ResponseLogger, get_response_logger

logger = logging.getLogger(__name__)

# Default entity types for DSPy pipeline
DEFAULT_ENTITY_TYPES = [
    {'id': 0, 'name': 'Person', 'description': 'A human individual'},
    {'id': 1, 'name': 'Organization', 'description': 'A company, institution, or group'},
    {'id': 2, 'name': 'Location', 'description': 'A physical place or location'},
    {'id': 3, 'name': 'Event', 'description': 'A significant occurrence or happening'},
    {'id': 4, 'name': 'Concept', 'description': 'An abstract idea or concept'},
    {'id': 5, 'name': 'Product', 'description': 'A product, service, or technology'},
]


@dataclass
class TokenUsage:
    """Token usage metrics for optimization."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    # Per-stage breakdown
    extraction_tokens: int = 0
    resolution_tokens: int = 0
    edge_tokens: int = 0
    summary_tokens: int = 0

    # Cost estimation (GLM pricing approximation)
    estimated_cost_usd: float = 0.0

    def add(self, prompt: int, completion: int, stage: str = '') -> None:
        """Add token counts from an LLM call."""
        self.prompt_tokens += prompt
        self.completion_tokens += completion
        self.total_tokens += prompt + completion

        if stage == 'extraction':
            self.extraction_tokens += prompt + completion
        elif stage == 'resolution':
            self.resolution_tokens += prompt + completion
        elif stage == 'edge':
            self.edge_tokens += prompt + completion
        elif stage == 'summary':
            self.summary_tokens += prompt + completion

        # GLM pricing approximation: ~$0.001 per 1K tokens
        self.estimated_cost_usd = self.total_tokens * 0.000001

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            'prompt_tokens': self.prompt_tokens,
            'completion_tokens': self.completion_tokens,
            'total_tokens': self.total_tokens,
            'by_stage': {
                'extraction': self.extraction_tokens,
                'resolution': self.resolution_tokens,
                'edge': self.edge_tokens,
                'summary': self.summary_tokens,
            },
            'estimated_cost_usd': round(self.estimated_cost_usd, 6),
        }


@dataclass
class PipelineResult:
    """Result from a single episode ingestion."""
    episode_id: str
    episode_content: str
    timestamp: str
    group_id: str  # Required for Graphiti EntityNode compatibility

    # Extraction results
    extracted_entities: list[dict[str, Any]] = field(default_factory=list)
    resolved_entities: list[dict[str, Any]] = field(default_factory=list)
    extracted_edges: list[dict[str, Any]] = field(default_factory=list)
    summaries: dict[str, str] = field(default_factory=dict)

    # Timing metrics
    extraction_time_ms: float = 0.0
    resolution_time_ms: float = 0.0
    edge_time_ms: float = 0.0
    summary_time_ms: float = 0.0
    total_time_ms: float = 0.0

    # Token usage metrics
    token_usage: TokenUsage = field(default_factory=TokenUsage)

    # Status
    success: bool = True
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'episode_id': self.episode_id,
            'episode_content': self.episode_content,
            'timestamp': self.timestamp,
            'group_id': self.group_id,
            'extracted_entities': self.extracted_entities,
            'resolved_entities': self.resolved_entities,
            'extracted_edges': self.extracted_edges,
            'summaries': self.summaries,
            'timing_metrics': {
                'extraction_time_ms': self.extraction_time_ms,
                'resolution_time_ms': self.resolution_time_ms,
                'edge_time_ms': self.edge_time_ms,
                'summary_time_ms': self.summary_time_ms,
                'total_time_ms': self.total_time_ms,
            },
            'token_usage': self.token_usage.to_dict(),
            'success': self.success,
            'errors': self.errors,
        }


@dataclass
class GraphState:
    """In-memory graph state for DSPy pipeline."""
    entities: list[dict[str, Any]] = field(default_factory=list)
    edges: list[dict[str, Any]] = field(default_factory=list)
    entity_index: dict[str, int] = field(default_factory=dict)  # name -> idx

    def add_entity(self, entity: dict[str, Any]) -> int:
        """Add entity and return its index."""
        # Check for existing
        name_lower = entity['name'].lower()
        if name_lower in self.entity_index:
            return self.entity_index[name_lower]

        idx = len(self.entities)
        entity['idx'] = idx
        self.entities.append(entity)
        self.entity_index[name_lower] = idx
        return idx

    def get_entity(self, idx: int) -> dict[str, Any] | None:
        """Get entity by index."""
        if 0 <= idx < len(self.entities):
            return self.entities[idx]
        return None

    def add_edge(self, edge: dict[str, Any]) -> None:
        """Add edge to graph."""
        self.edges.append(edge)

    def get_entities_for_resolution(self) -> list[dict[str, Any]]:
        """Get entities formatted for resolution."""
        return [
            {
                'idx': e['idx'],
                'name': e['name'],
                'type': e.get('type', 'Unknown'),
                'summary': e.get('summary', ''),
            }
            for e in self.entities
        ]


class DSPyIngestionPipeline:
    """
    Complete DSPy-based ingestion pipeline.

    This pipeline mirrors the functionality of Graphiti's add_episode method
    but uses DSPy modules for all LLM operations.
    """

    def __init__(
        self,
        group_id: str = 'default',
        entity_types: list[dict[str, Any]] | None = None,
        edge_types: list[dict[str, Any]] | None = None,
        custom_instructions: str = '',
        generate_summaries: bool = True,
        enable_response_logging: bool = True,
    ):
        """
        Initialize the pipeline.

        Args:
            group_id: Group identifier for EntityNode compatibility.
            entity_types: List of entity type definitions.
            edge_types: List of edge type definitions.
            custom_instructions: Additional extraction instructions.
            generate_summaries: Whether to generate entity summaries.
            enable_response_logging: Whether to log responses for optimization.
        """
        self.group_id = group_id
        # Ensure LM is configured
        try:
            get_lm_config()
        except RuntimeError:
            configure_lm()

        # Initialize modules
        self.node_extractor = NodeExtractor()
        self.edge_extractor = EdgeExtractor()
        self.node_resolver = NodeResolver()
        self.summary_generator = SummaryGenerator()

        # Configuration
        self.entity_types = entity_types or self._default_entity_types()
        self.edge_types = edge_types or []
        self.custom_instructions = custom_instructions
        self.generate_summaries = generate_summaries

        # Response logging for optimization
        self.enable_response_logging = enable_response_logging
        self._response_logger: ResponseLogger | None = None
        if enable_response_logging:
            try:
                self._response_logger = get_response_logger()
            except Exception as e:
                logger.warning(f'Failed to initialize response logger: {e}')

        # Graph state
        self.graph = GraphState()

        # Episode history for context
        self.episode_history: list[dict[str, Any]] = []
        self.max_history = 5  # Keep last N episodes for context

    def _default_entity_types(self) -> list[dict[str, Any]]:
        """Default entity types if none provided."""
        return DEFAULT_ENTITY_TYPES.copy()

    def _time_ms(self, start: datetime) -> float:
        """Calculate milliseconds since start time."""
        return (datetime.now(timezone.utc) - start).total_seconds() * 1000

    def ingest_episode(
        self,
        content: str,
        episode_id: str | None = None,
        reference_time: str | None = None,
    ) -> PipelineResult:
        """
        Ingest a single episode through the pipeline.

        Args:
            content: The episode content to ingest.
            episode_id: Optional episode identifier.
            reference_time: ISO 8601 timestamp for temporal resolution.

        Returns:
            PipelineResult with extraction results and metrics.
        """
        start_time = datetime.now(timezone.utc)

        result = PipelineResult(
            episode_id=episode_id or f'ep_{len(self.episode_history)}',
            episode_content=content,
            timestamp=reference_time or start_time.isoformat(),
            group_id=self.group_id,
        )

        try:
            # Get previous episodes for context
            previous = self.episode_history[-self.max_history:] if self.episode_history else []

            # Step 1: Extract entities
            step_start = datetime.now(timezone.utc)
            extraction_inputs = {
                'current_message': content,
                'entity_types': self.entity_types,
                'previous_messages': previous,
                'custom_instructions': self.custom_instructions,
            }
            extraction_error = None
            try:
                extracted = self.node_extractor(
                    current_message=content,
                    entity_types=self.entity_types,
                    previous_messages=previous,
                    custom_instructions=self.custom_instructions,
                )
            except Exception as e:
                extraction_error = str(e)
                extracted = ExtractedEntities(extracted_entities=[])
                raise

            result.extraction_time_ms = self._time_ms(step_start)
            prompt_tok, comp_tok = _extract_token_usage()
            result.token_usage.add(prompt_tok, comp_tok, 'extraction')

            # Log extraction
            if self._response_logger:
                self._response_logger.log_extraction(
                    episode_id=result.episode_id,
                    group_id=self.group_id,
                    inputs=extraction_inputs,
                    outputs=extracted,
                    duration_ms=result.extraction_time_ms,
                    prompt_tokens=prompt_tok,
                    completion_tokens=comp_tok,
                    success=extraction_error is None,
                    error=extraction_error,
                )

            # Convert to dicts
            extracted_entities = [
                {
                    'id': i,
                    'name': e.name,
                    'type': self.entity_types[e.entity_type_id]['name'] if e.entity_type_id < len(self.entity_types) else 'Unknown',
                    'type_id': e.entity_type_id,
                }
                for i, e in enumerate(extracted.extracted_entities)
            ]
            result.extracted_entities = extracted_entities

            # Step 2: Resolve entities against existing
            step_start = datetime.now(timezone.utc)
            existing_entities = self.graph.get_entities_for_resolution()
            resolution_error = None
            resolutions = None

            if extracted_entities and existing_entities:
                resolution_inputs = {
                    'current_message': content,
                    'extracted_entities': extracted_entities,
                    'existing_entities': existing_entities,
                    'previous_messages': previous,
                }
                try:
                    resolutions = self.node_resolver(
                        current_message=content,
                        extracted_entities=extracted_entities,
                        existing_entities=existing_entities,
                        previous_messages=previous,
                    )
                except Exception as e:
                    resolution_error = str(e)
                    resolutions = NodeResolutions(entity_resolutions=[])

                prompt_tok, comp_tok = _extract_token_usage()
                result.token_usage.add(prompt_tok, comp_tok, 'resolution')

                # Log resolution
                if self._response_logger:
                    self._response_logger.log_resolution(
                        episode_id=result.episode_id,
                        group_id=self.group_id,
                        inputs=resolution_inputs,
                        outputs=resolutions,
                        duration_ms=self._time_ms(step_start),
                        prompt_tokens=prompt_tok,
                        completion_tokens=comp_tok,
                        success=resolution_error is None,
                        error=resolution_error,
                    )

                # Process resolutions
                resolved = []
                for res in resolutions.entity_resolutions:
                    if res.duplicate_idx >= 0:
                        # Duplicate - use existing entity
                        existing = self.graph.get_entity(res.duplicate_idx)
                        if existing:
                            resolved.append({
                                'name': existing['name'],
                                'type': existing.get('type', 'Unknown'),
                                'idx': existing['idx'],
                                'is_new': False,
                                'merged_from': res.name,
                                'group_id': self.group_id,
                            })
                    else:
                        # New entity
                        entity_data = extracted_entities[res.id] if res.id < len(extracted_entities) else {'name': res.name, 'type': 'Unknown'}
                        idx = self.graph.add_entity({
                            'name': res.name,
                            'type': entity_data.get('type', 'Unknown'),
                        })
                        resolved.append({
                            'name': res.name,
                            'type': entity_data.get('type', 'Unknown'),
                            'idx': idx,
                            'is_new': True,
                            'group_id': self.group_id,
                        })
                result.resolved_entities = resolved
            else:
                # No existing entities - all are new
                for entity in extracted_entities:
                    idx = self.graph.add_entity({
                        'name': entity['name'],
                        'type': entity['type'],
                    })
                    result.resolved_entities.append({
                        'name': entity['name'],
                        'type': entity['type'],
                        'idx': idx,
                        'is_new': True,
                        'group_id': self.group_id,
                    })

            result.resolution_time_ms = self._time_ms(step_start)

            # Step 3: Extract edges
            step_start = datetime.now(timezone.utc)
            edge_error = None
            edges = None

            if len(result.resolved_entities) >= 2:
                # Build entity list for edge extraction
                entities_for_edges = [
                    {'id': i, 'name': e['name'], 'type': e['type']}
                    for i, e in enumerate(result.resolved_entities)
                ]

                edge_inputs = {
                    'current_message': content,
                    'entities': entities_for_edges,
                    'reference_time': result.timestamp,
                    'previous_messages': previous,
                    'edge_types': self.edge_types,
                    'custom_instructions': self.custom_instructions,
                }

                try:
                    edges = self.edge_extractor(
                        current_message=content,
                        entities=entities_for_edges,
                        reference_time=result.timestamp,
                        previous_messages=previous,
                        edge_types=self.edge_types,
                        custom_instructions=self.custom_instructions,
                    )
                except Exception as e:
                    edge_error = str(e)
                    edges = ExtractedEdges(edges=[])

                prompt_tok, comp_tok = _extract_token_usage()
                result.token_usage.add(prompt_tok, comp_tok, 'edge')

                # Log edge extraction
                if self._response_logger:
                    self._response_logger.log_edges(
                        episode_id=result.episode_id,
                        group_id=self.group_id,
                        inputs=edge_inputs,
                        outputs=edges,
                        duration_ms=self._time_ms(step_start),
                        prompt_tokens=prompt_tok,
                        completion_tokens=comp_tok,
                        success=edge_error is None,
                        error=edge_error,
                    )

                # Convert and store edges
                if edges and hasattr(edges, 'edges'):
                    for edge in edges.edges:
                        edge_dict = {
                            'source': result.resolved_entities[edge.source_entity_id]['name'] if edge.source_entity_id < len(result.resolved_entities) else f'?{edge.source_entity_id}',
                            'target': result.resolved_entities[edge.target_entity_id]['name'] if edge.target_entity_id < len(result.resolved_entities) else f'?{edge.target_entity_id}',
                            'relation_type': edge.relation_type,
                            'fact': edge.fact,
                            'valid_at': edge.valid_at,
                            'invalid_at': edge.invalid_at,
                        }
                        result.extracted_edges.append(edge_dict)
                        self.graph.add_edge(edge_dict)

            result.edge_time_ms = self._time_ms(step_start)

            # Step 4: Generate summaries for new entities
            step_start = datetime.now(timezone.utc)
            if self.generate_summaries:
                new_entities = [e for e in result.resolved_entities if e.get('is_new', False)]
                for entity in new_entities:
                    summary_error = None
                    summary_start = datetime.now(timezone.utc)
                    summary_inputs = {
                        'current_message': content,
                        'entity_name': entity['name'],
                        'previous_messages': previous,
                        'existing_summary': '',
                    }

                    try:
                        summary = self.summary_generator(
                            current_message=content,
                            entity_name=entity['name'],
                            previous_messages=previous,
                        )
                        prompt_tok, comp_tok = _extract_token_usage()
                        result.token_usage.add(prompt_tok, comp_tok, 'summary')
                        result.summaries[entity['name']] = summary.summary

                        # Update entity in graph
                        graph_entity = self.graph.get_entity(entity['idx'])
                        if graph_entity:
                            graph_entity['summary'] = summary.summary

                    except Exception as e:
                        summary_error = str(e)
                        summary = Summary(summary='')
                        logger.warning(f'Summary generation failed for {entity["name"]}: {e}')

                    # Log summary generation
                    if self._response_logger:
                        self._response_logger.log_summary(
                            episode_id=result.episode_id,
                            group_id=self.group_id,
                            entity_name=entity['name'],
                            inputs=summary_inputs,
                            outputs=summary,
                            duration_ms=self._time_ms(summary_start),
                            prompt_tokens=prompt_tok if summary_error is None else 0,
                            completion_tokens=comp_tok if summary_error is None else 0,
                            success=summary_error is None,
                            error=summary_error,
                        )

            result.summary_time_ms = self._time_ms(step_start)

            # Add to history
            self.episode_history.append({'content': content})

        except Exception as e:
            result.success = False
            result.errors.append(str(e))
            logger.error(f'Pipeline error: {e}')

        result.total_time_ms = self._time_ms(start_time)

        # Log episode completion
        if self._response_logger:
            self._response_logger.log_episode_complete(
                episode_id=result.episode_id,
                group_id=self.group_id,
                content=content,
                total_duration_ms=result.total_time_ms,
                total_tokens=result.token_usage.total_tokens,
                entity_count=len(result.resolved_entities),
                edge_count=len(result.extracted_edges),
                new_entity_count=len([e for e in result.resolved_entities if e.get('is_new', False)]),
                success=result.success,
                errors=result.errors,
            )

        return result

    def ingest_episodes(
        self,
        episodes: list[dict[str, Any]],
    ) -> list[PipelineResult]:
        """
        Ingest multiple episodes sequentially.

        Args:
            episodes: List of episode dicts with 'content' and optional 'id', 'timestamp'.

        Returns:
            List of PipelineResult objects.
        """
        results = []
        for episode in episodes:
            result = self.ingest_episode(
                content=episode.get('content', ''),
                episode_id=episode.get('id'),
                reference_time=episode.get('timestamp'),
            )
            results.append(result)
        return results

    def get_graph_state(self) -> dict[str, Any]:
        """Get current graph state as dict."""
        return {
            'entities': self.graph.entities,
            'edges': self.graph.edges,
            'entity_count': len(self.graph.entities),
            'edge_count': len(self.graph.edges),
        }

    def reset(self) -> None:
        """Reset pipeline state."""
        self.graph = GraphState()
        self.episode_history = []
