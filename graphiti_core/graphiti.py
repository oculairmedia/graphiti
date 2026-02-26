"""
Copyright 2024, Zep Software, Inc.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import logging
import os
from datetime import datetime
from time import time
from typing import Any, cast
from collections.abc import Mapping

from dotenv import load_dotenv
from pydantic import BaseModel
from typing_extensions import LiteralString

from graphiti_core.client_factory import GraphitiClientFactory
from graphiti_core.cross_encoder.client import CrossEncoderClient
from graphiti_core.cross_encoder.openai_reranker_client import OpenAIRerankerClient
from graphiti_core.driver.driver import GraphDriver
from graphiti_core.edges import EntityEdge, EpisodicEdge
from graphiti_core.embedder import EmbedderClient, OpenAIEmbedder
from graphiti_core.events import ChangeEventPublisher, set_event_publisher
from graphiti_core.graphiti_types import GraphitiClients
from graphiti_core.helpers import (
    get_default_group_id,
    semaphore_gather,
    validate_excluded_entity_types,
    validate_group_id,
)
from graphiti_core.llm_client import LLMClient, OpenAIClient
from graphiti_core.utils.resilient_ingestion import (
    ResilientIngestionState,
    ingestion_cache,
    retry_with_backoff,
)
from graphiti_core.nodes import CommunityNode, EntityNode, EpisodeType, EpisodicNode
from graphiti_core.errors import NodeNotFoundError
from graphiti_core.search.search import SearchConfig, search
from graphiti_core.search.search_config import DEFAULT_SEARCH_LIMIT, SearchResults
from graphiti_core.search.search_config_recipes import (
    COMBINED_HYBRID_SEARCH_CROSS_ENCODER,
    EDGE_HYBRID_SEARCH_NODE_DISTANCE,
    EDGE_HYBRID_SEARCH_RRF,
)
from graphiti_core.search.search_filters import SearchFilters
from graphiti_core.search.search_utils import (
    RELEVANT_SCHEMA_LIMIT,
    get_edge_invalidation_candidates,
    get_mentioned_nodes,
    get_relevant_edges,
)
from graphiti_core.telemetry import capture_event
from graphiti_core.utils.bulk_utils import (
    RawEpisode,
    add_nodes_and_edges_bulk,
    dedupe_edges_bulk,
    dedupe_nodes_bulk,
    extract_nodes_and_edges_bulk,
    resolve_edge_pointers,
    retrieve_previous_episodes_bulk,
)
from graphiti_core.utils.datetime_utils import utc_now, ensure_utc
from graphiti_core.utils.content_sanitizer import sanitize_content
from graphiti_core.utils.maintenance.community_operations import (
    build_communities,
    remove_communities,
    update_community,
)
from graphiti_core.utils.maintenance.edge_operations import (
    build_duplicate_of_edges,
    build_episodic_edges,
    extract_edges,
    resolve_extracted_edge,
    resolve_extracted_edges,
)
from graphiti_core.utils.maintenance.graph_data_operations import (
    EPISODE_WINDOW_LEN,
    build_indices_and_constraints,
    retrieve_episodes,
)
from graphiti_core.utils.maintenance.node_operations import (
    create_entity_node_embeddings,
    extract_attributes_from_nodes,
    extract_nodes,
    resolve_extracted_nodes,
)
from graphiti_core.utils.ontology_utils.entity_types_utils import validate_entity_types

# DSPy pipeline imports (lazy loaded when use_dspy=True)
_dspy_pipeline = None


def _get_dspy_pipeline(group_id: str = 'default'):
    """Lazy-load DSPy pipeline to avoid import overhead when not used."""
    global _dspy_pipeline
    if _dspy_pipeline is None or _dspy_pipeline.group_id != group_id:
        from graphiti_core.dspy import DSPyIngestionPipeline, configure_lm

        configure_lm()
        _dspy_pipeline = DSPyIngestionPipeline(group_id=group_id, generate_summaries=False)
    return _dspy_pipeline


logger = logging.getLogger(__name__)

load_dotenv()


class AddEpisodeResults(BaseModel):
    episode: EpisodicNode
    nodes: list[EntityNode]
    edges: list[EntityEdge]


class Graphiti:
    def __init__(
        self,
        driver: GraphDriver | None = None,
        llm_client: LLMClient | None = None,
        embedder: EmbedderClient | None = None,
        cross_encoder: CrossEncoderClient | None = None,
        store_raw_episode_content: bool = True,
        graph_driver: GraphDriver | None = None,
        max_coroutines: int | None = None,
        enable_cross_graph_deduplication: bool = True,
        use_dspy: bool = False,
    ):
        """
        Initialize a Graphiti instance.

        Parameters
        ----------
        driver : GraphDriver
            An instance of GraphDriver for database operations (e.g., FalkorDriver).
            Either driver or graph_driver must be provided.
        llm_client : LLMClient | None, optional
            An instance of LLMClient for natural language processing tasks.
            If not provided, a default OpenAIClient will be initialized.
        embedder : EmbedderClient | None, optional
            An instance of EmbedderClient for embedding tasks.
            If not provided, a default OpenAIEmbedder will be initialized.
        cross_encoder : CrossEncoderClient | None, optional
            An instance of CrossEncoderClient for reranking tasks.
            If not provided, a default OpenAIRerankerClient will be initialized.
        store_raw_episode_content : bool, optional
            Whether to store the raw content of episodes. Defaults to True.
        graph_driver : GraphDriver | None, optional
            Alias for driver parameter (deprecated, use driver instead).
        max_coroutines : int | None, optional
            The maximum number of concurrent operations allowed. Overrides SEMAPHORE_LIMIT set in the environment.
            If not set, the Graphiti default is used.
        enable_cross_graph_deduplication : bool, optional
            Enable deduplication of entities across different group_ids.
            If True, entities with the same name in different groups can be merged.
            Default is False to maintain backward compatibility.
        use_dspy : bool, optional
            Whether to use DSPy for LLM extraction. Defaults to False.

        Returns
        -------
        None

        Notes
        -----
        FalkorDB is the only supported database backend.
        The OpenAI API key is expected to be set in the environment variables.
        Make sure to set the OPENAI_API_KEY environment variable before initializing
        Graphiti if you're using the default OpenAIClient.
        """

        resolved_driver = driver or graph_driver
        if resolved_driver is None:
            raise ValueError('driver is required. Use FalkorDriver to create a driver instance.')
        self.driver = resolved_driver

        self.store_raw_episode_content = store_raw_episode_content
        self.max_coroutines = max_coroutines
        resolved_llm_client = llm_client or GraphitiClientFactory.create_llm_client()
        if resolved_llm_client is None:
            raise ValueError('Failed to initialize llm_client')
        self.llm_client: LLMClient = resolved_llm_client

        resolved_embedder = embedder or GraphitiClientFactory.create_embedder()
        if resolved_embedder is None:
            raise ValueError('Failed to initialize embedder')
        self.embedder: EmbedderClient = resolved_embedder
        if cross_encoder:
            self.cross_encoder = cross_encoder
        else:
            self.cross_encoder = GraphitiClientFactory.create_cross_encoder()

        self.store_raw_episode_content = store_raw_episode_content
        self.enable_cross_graph_deduplication = enable_cross_graph_deduplication
        self.use_dspy = use_dspy

        if use_dspy:
            logger.info('DSPy pipeline enabled - will use DSPy for LLM extraction')

        self.clients = GraphitiClients(
            driver=self.driver,
            llm_client=self.llm_client,
            embedder=self.embedder,
            cross_encoder=self.cross_encoder,
        )

        # Initialize event publisher for real-time change sync (GRAPH-106)
        self._init_event_publisher()

        # Capture telemetry event
        self._capture_initialization_telemetry()

    def _init_event_publisher(self):
        """Initialize the event publisher for real-time change sync (GRAPH-106)."""
        redis_client = None
        driver_client = getattr(cast(Any, self.driver), 'client', None)

        if driver_client is not None and hasattr(driver_client, 'connection'):
            redis_client = driver_client.connection
            logger.info('Event publisher: using FalkorDB Redis connection')
        else:
            redis_url = os.getenv('GRAPHITI_REDIS_URL')
            if redis_url:
                try:
                    import redis.asyncio as aioredis

                    redis_client = aioredis.from_url(redis_url)
                    logger.info(f'Event publisher: using Redis from GRAPHITI_REDIS_URL')
                except ImportError:
                    logger.warning('Event publisher: redis package not installed')
                except Exception as e:
                    logger.warning(f'Event publisher: failed to connect to Redis: {e}')
            else:
                logger.info('Event publisher: no Redis connection available')

        # Create and set the publisher
        self.event_publisher = ChangeEventPublisher(redis_client)
        set_event_publisher(self.event_publisher)

    def _capture_initialization_telemetry(self):
        """Capture telemetry event for Graphiti initialization."""
        try:
            # Detect provider types from class names
            llm_provider = self._get_provider_type(self.llm_client)
            embedder_provider = self._get_provider_type(self.embedder)
            reranker_provider = self._get_provider_type(self.cross_encoder)
            database_provider = self._get_provider_type(self.driver)

            properties = {
                'llm_provider': llm_provider,
                'embedder_provider': embedder_provider,
                'reranker_provider': reranker_provider,
                'database_provider': database_provider,
            }

            capture_event('graphiti_initialized', properties)
        except Exception:
            # Silently handle telemetry errors
            pass

    def _get_provider_type(self, client) -> str:
        """Get provider type from client class name."""
        if client is None:
            return 'none'

        class_name = client.__class__.__name__.lower()

        # LLM providers
        if 'openai' in class_name:
            return 'openai'
        elif 'azure' in class_name:
            return 'azure'
        elif 'anthropic' in class_name:
            return 'anthropic'
        elif 'crossencoder' in class_name:
            return 'crossencoder'
        elif 'gemini' in class_name:
            return 'gemini'
        elif 'groq' in class_name:
            return 'groq'
        # Database providers
        elif 'falkor' in class_name:
            return 'falkordb'
        # Embedder providers
        elif 'voyage' in class_name:
            return 'voyage'
        else:
            return 'unknown'

    async def close(self):
        """Close the connection to the graph database."""
        await self.driver.close()

    async def build_indices_and_constraints(
        self, delete_existing: bool = False, embedding_dim: int | None = None
    ):
        """Build indices and constraints in the graph database."""
        if embedding_dim is None:
            from graphiti_core.embedder.client import EMBEDDING_DIM

            embedding_dim = EMBEDDING_DIM
        await build_indices_and_constraints(self.driver, delete_existing, embedding_dim)

    async def retrieve_episodes(
        self,
        reference_time: datetime,
        last_n: int = EPISODE_WINDOW_LEN,
        group_ids: list[str] | None = None,
        source: EpisodeType | None = None,
    ) -> list[EpisodicNode]:
        """
        Retrieve the last n episodic nodes from the graph.

        This method fetches a specified number of the most recent episodic nodes
        from the graph, relative to the given reference time.

        Parameters
        ----------
        reference_time : datetime
            The reference time to retrieve episodes before.
        last_n : int, optional
            The number of episodes to retrieve. Defaults to EPISODE_WINDOW_LEN.
        group_ids : list[str | None], optional
            The group ids to return data from.

        Returns
        -------
        list[EpisodicNode]
            A list of the most recent EpisodicNode objects.

        Notes
        -----
        The actual retrieval is performed by the `retrieve_episodes` function
        from the `graphiti_core.utils` module.
        """
        return await retrieve_episodes(self.driver, reference_time, last_n, group_ids, source)

    async def add_episode(
        self,
        name: str,
        episode_body: str,
        source_description: str,
        reference_time: datetime,
        source: EpisodeType = EpisodeType.message,
        group_id: str | None = None,
        uuid: str | None = None,
        update_communities: bool = False,
        entity_types: dict[str, BaseModel] | None = None,
        excluded_entity_types: list[str] | None = None,
        previous_episode_uuids: list[str] | None = None,
        edge_types: dict[str, BaseModel] | None = None,
        edge_type_map: dict[tuple[str, str], list[str]] | None = None,
    ) -> AddEpisodeResults:
        """
        Process an episode and update the graph.

        .. deprecated::
            This method is deprecated and will be removed in a future release.
            Use :meth:`add_episode_resilient` instead, which provides:
            - Granular retry logic for each extraction stage
            - State caching to resume from failures
            - Temporal workflow integration for observability
            - DSPy support for optimized extraction

        This method extracts information from the episode, creates nodes and edges,
        and updates the graph database accordingly.

        Parameters
        ----------
        name : str
            The name of the episode.
        episode_body : str
            The content of the episode.
        source_description : str
            A description of the episode's source.
        reference_time : datetime
            The reference time for the episode.
        source : EpisodeType, optional
            The type of the episode. Defaults to EpisodeType.message.
        group_id : str | None
            An id for the graph partition the episode is a part of.
        uuid : str | None
            Optional uuid of the episode.
        update_communities : bool
            Optional. Whether to update communities with new node information
        entity_types : dict[str, BaseModel] | None
            Optional. Dictionary mapping entity type names to their Pydantic model definitions.
        excluded_entity_types : list[str] | None
            Optional. List of entity type names to exclude from the graph. Entities classified
            into these types will not be added to the graph. Can include 'Entity' to exclude
            the default entity type.
        previous_episode_uuids : list[str] | None
            Optional.  list of episode uuids to use as the previous episodes. If this is not provided,
            the most recent episodes by created_at date will be used.

        Returns
        -------
        AddEpisodeResults

        Notes
        -----
        This method performs several steps including node extraction, edge extraction,
        deduplication, and database updates. It also handles embedding generation
        and edge invalidation.

        It is recommended to run this method as a background process, such as in a queue.
        It's important that each episode is added sequentially and awaited before adding
        the next one. For web applications, consider using FastAPI's background tasks
        or a dedicated task queue like Celery for this purpose.

        Example using FastAPI background tasks:
            @app.post("/add_episode")
            async def add_episode_endpoint(episode_data: EpisodeData):
                background_tasks.add_task(graphiti.add_episode, **episode_data.dict())
                return {"message": "Episode processing started"}

        Migration
        ---------
        Replace calls to ``add_episode()`` with ``add_episode_resilient()``:

        .. code-block:: python

            # Before (deprecated)
            result = await graphiti.add_episode(
                name="...", episode_body="...", ...
            )

            # After (recommended)
            result = await graphiti.add_episode_resilient(
                name="...", episode_body="...", ...
            )
        """
        import warnings

        warnings.warn(
            'add_episode() is deprecated and will be removed in a future release. '
            'Use add_episode_resilient() instead for better retry handling, '
            'state caching, and Temporal integration.',
            DeprecationWarning,
            stacklevel=2,
        )

        try:
            start = time()
            now = utc_now()

            # if group_id is None, use the default group id by the provider
            group_id = group_id or get_default_group_id(self.driver.provider)
            validate_entity_types(entity_types)

            validate_excluded_entity_types(excluded_entity_types, entity_types)
            validate_group_id(group_id)
            episode_body = sanitize_content(episode_body)

            previous_episodes = (
                await self.retrieve_episodes(
                    reference_time,
                    last_n=RELEVANT_SCHEMA_LIMIT,
                    group_ids=[group_id],
                    source=source,
                )
                if previous_episode_uuids is None
                else await EpisodicNode.get_by_uuids(self.driver, previous_episode_uuids)
            )

            episode = (
                await EpisodicNode.get_by_uuid(self.driver, uuid)
                if uuid is not None
                else EpisodicNode(
                    name=name,
                    group_id=group_id,
                    labels=[],
                    source=source,
                    content=episode_body,
                    source_description=source_description,
                    created_at=now,
                    valid_at=ensure_utc(reference_time) or now,
                )
            )

            # Debug logging for group_id
            logger.info(
                f'Created EpisodicNode with group_id: {episode.group_id} (uuid: {episode.uuid})'
            )

            # Create default edge type map
            edge_type_map_default = (
                {('Entity', 'Entity'): list(edge_types.keys())}
                if edge_types is not None
                else {('Entity', 'Entity'): []}
            )
            resolved_edge_types: dict[str, BaseModel | type[BaseModel]] | None = (
                {name: model for name, model in edge_types.items()}
                if edge_types is not None
                else None
            )

            # Extract entities as nodes
            if self.use_dspy:
                extracted_nodes = await self._extract_nodes_dspy(
                    episode, previous_episodes, entity_types
                )
            else:
                extracted_nodes = await extract_nodes(
                    self.clients, episode, previous_episodes, entity_types, excluded_entity_types
                )

            # Extract edges and resolve nodes
            if self.use_dspy:
                edges_coro = self._extract_edges_dspy(
                    episode, extracted_nodes, previous_episodes, resolved_edge_types
                )
            else:
                edges_coro = extract_edges(
                    self.clients,
                    episode,
                    extracted_nodes,
                    previous_episodes,
                    edge_type_map or edge_type_map_default,
                    group_id,
                    resolved_edge_types,
                )

            (nodes, uuid_map, node_duplicates), extracted_edges = await semaphore_gather(
                resolve_extracted_nodes(
                    self.clients,
                    extracted_nodes,
                    episode,
                    previous_episodes,
                    entity_types,
                    existing_nodes_override=None,
                    enable_cross_graph_deduplication=self.enable_cross_graph_deduplication,
                ),
                edges_coro,
                max_coroutines=self.max_coroutines,
            )

            edges = resolve_edge_pointers(extracted_edges, uuid_map)

            (resolved_edges, invalidated_edges), hydrated_nodes = await semaphore_gather(
                resolve_extracted_edges(
                    self.clients,
                    edges,
                    episode,
                    nodes,
                    resolved_edge_types or {},
                    edge_type_map or edge_type_map_default,
                ),
                extract_attributes_from_nodes(
                    self.clients, nodes, episode, previous_episodes, entity_types
                ),
                max_coroutines=self.max_coroutines,
            )

            duplicate_of_edges, merge_operations, duplicate_nodes_to_save = (
                build_duplicate_of_edges(episode, now, node_duplicates)
            )

            entity_edges = resolved_edges + invalidated_edges + duplicate_of_edges

            episodic_edges = build_episodic_edges(
                nodes, episode.uuid, now, episode_group_id=episode.group_id
            )

            episode.entity_edges = [edge.uuid for edge in entity_edges]

            if not self.store_raw_episode_content:
                episode.content = ''

            # Combine all nodes to be saved (hydrated nodes + duplicate nodes)
            all_nodes_to_save = hydrated_nodes + duplicate_nodes_to_save

            await add_nodes_and_edges_bulk(
                self.driver,
                [episode],
                episodic_edges,
                all_nodes_to_save,
                entity_edges,
                self.embedder,
                event_publisher=self.event_publisher,
            )

            # Execute merge operations after nodes and edges are saved
            # Feature flag: GRAPHITI_ENABLE_AUTO_MERGE (default: false for safety)
            import os

            auto_merge_enabled = os.getenv('GRAPHITI_ENABLE_AUTO_MERGE', 'false').lower() == 'true'

            if merge_operations and auto_merge_enabled:
                from graphiti_core.utils.maintenance.edge_operations import execute_merge_operations

                logger.info(
                    f'Auto-merge enabled: executing {len(merge_operations)} merge operations'
                )
                await execute_merge_operations(
                    self.driver,
                    merge_operations,
                    allow_cross_graph_merge=self.enable_cross_graph_deduplication,
                )
            elif merge_operations and not auto_merge_enabled:
                logger.info(
                    f'Auto-merge disabled: skipping {len(merge_operations)} merge operations (set GRAPHITI_ENABLE_AUTO_MERGE=true to enable)'
                )

            # Update any communities
            if update_communities:
                await semaphore_gather(
                    *[
                        update_community(self.driver, self.llm_client, self.embedder, node)
                        for node in nodes
                    ],
                    max_coroutines=self.max_coroutines,
                )
            end = time()
            logger.info(f'Completed add_episode in {(end - start) * 1000} ms')

            return AddEpisodeResults(episode=episode, nodes=nodes, edges=entity_edges)

        except Exception as e:
            raise e

    ##### RESILIENT INGESTION #####

    async def add_episode_resilient(
        self,
        name: str,
        episode_body: str,
        source_description: str,
        reference_time: datetime,
        source: EpisodeType = EpisodeType.message,
        group_id: str | None = None,
        uuid: str | None = None,
        update_communities: bool = False,
        entity_types: dict[str, BaseModel] | None = None,
        excluded_entity_types: list[str] | None = None,
        edge_types: dict[str, BaseModel] | None = None,
        edge_type_map: dict[tuple[str, str], list[str]] | None = None,
        previous_episode_uuids: list[str] | None = None,
    ) -> 'AddEpisodeResults':
        """
        Resilient version of add_episode that can recover from partial failures.

        This method implements granular retry logic for each stage of ingestion:
        1. Node extraction
        2. Node resolution
        3. Edge extraction
        4. Episode creation

        Each stage can be retried independently, preventing loss of progress when
        providers like Cerebras have elevated error rates.
        """
        resolved_group_id = group_id or get_default_group_id(self.driver.provider)

        try:
            start = time()
            now = utc_now()

            visibility = None
            visibility_enabled = False
            try:
                from graphiti_core.utils.temporal_visibility import TemporalVisibilityClient

                visibility = TemporalVisibilityClient.get()
                visibility_enabled = visibility.enabled()
            except Exception as e:
                logger.debug('Temporal visibility client unavailable: %s', e)

            validate_entity_types(entity_types)
            validate_excluded_entity_types(excluded_entity_types, entity_types)
            validate_group_id(resolved_group_id)
            episode_body = sanitize_content(episode_body)
            resolved_edge_types: dict[str, BaseModel | type[BaseModel]] = (
                {name: model for name, model in edge_types.items()}
                if edge_types is not None
                else {}
            )

            # Create episode node first (before other processing)
            # If UUID provided, try to fetch existing; if not found, create new with that UUID
            episode = None
            if uuid is not None:
                try:
                    episode = await EpisodicNode.get_by_uuid(self.driver, uuid)
                except NodeNotFoundError:
                    # UUID provided but not found - create new episode with this UUID
                    logger.info(f'Episode with uuid {uuid} not found, creating new episode')
                    episode = EpisodicNode(
                        uuid=uuid,
                        name=name,
                        group_id=resolved_group_id,
                        labels=[],
                        source=source,
                        content=episode_body,
                        source_description=source_description,
                        created_at=now,
                        valid_at=ensure_utc(reference_time) or now,
                    )
            else:
                episode = EpisodicNode(
                    name=name,
                    group_id=resolved_group_id,
                    labels=[],
                    source=source,
                    content=episode_body,
                    source_description=source_description,
                    created_at=now,
                    valid_at=ensure_utc(reference_time) or now,
                )

            logger.info(
                f'Created EpisodicNode with group_id: {episode.group_id} (uuid: {episode.uuid})'
            )

            if visibility_enabled and visibility is not None:
                import asyncio

                asyncio.create_task(
                    visibility.ensure_workflow_started(episode.uuid, resolved_group_id)
                )

            # Get or create resilient ingestion state
            state = ingestion_cache.get_or_create_state(episode.uuid, resolved_group_id)

            # Get previous episodes
            previous_episodes = (
                await self.retrieve_episodes(
                    reference_time,
                    last_n=RELEVANT_SCHEMA_LIMIT,
                    group_ids=[resolved_group_id],
                    source=source,
                )
                if previous_episode_uuids is None
                else await EpisodicNode.get_by_uuids(self.driver, previous_episode_uuids)
            )

            # Stage 1: Extract nodes (with retry)
            if not state.nodes_extracted:
                stage_started_at = time()
                if visibility_enabled and visibility is not None:
                    import asyncio

                    asyncio.create_task(
                        visibility.stage_started(
                            episode.uuid,
                            resolved_group_id,
                            'extract_nodes',
                            {'cached': False},
                        )
                    )

                try:
                    extracted_nodes = await self._extract_nodes_with_retry(
                        episode, previous_episodes, entity_types, excluded_entity_types, state
                    )
                except Exception as e:
                    if visibility_enabled and visibility is not None:
                        import asyncio

                        asyncio.create_task(
                            visibility.ingestion_failed(
                                episode.uuid,
                                resolved_group_id,
                                'extract_nodes',
                                str(e),
                                e.__class__.__name__,
                            )
                        )
                    raise

                state.mark_nodes_extracted(extracted_nodes)

                if visibility_enabled and visibility is not None:
                    import asyncio

                    asyncio.create_task(
                        visibility.stage_completed(
                            episode.uuid,
                            resolved_group_id,
                            'extract_nodes',
                            {
                                'cached': False,
                                'duration_ms': int((time() - stage_started_at) * 1000),
                                'node_count': len(extracted_nodes),
                            },
                        )
                    )
            else:
                extracted_nodes = state.extracted_nodes or []
                logger.info(
                    f'Episode {episode.uuid}: Using cached extracted nodes ({len(extracted_nodes)} nodes)'
                )
                if visibility_enabled and visibility is not None:
                    import asyncio

                    asyncio.create_task(
                        visibility.stage_completed(
                            episode.uuid,
                            resolved_group_id,
                            'extract_nodes',
                            {
                                'cached': True,
                                'node_count': len(extracted_nodes),
                            },
                        )
                    )

            # Stage 2: Resolve nodes (with retry)
            if not state.nodes_resolved:
                stage_started_at = time()
                if visibility_enabled and visibility is not None:
                    import asyncio

                    asyncio.create_task(
                        visibility.stage_started(
                            episode.uuid,
                            resolved_group_id,
                            'resolve_nodes',
                            {'cached': False},
                        )
                    )

                try:
                    nodes, uuid_map, node_duplicates = await self._resolve_nodes_with_retry(
                        extracted_nodes, episode, previous_episodes, entity_types, state
                    )
                except Exception as e:
                    if visibility_enabled and visibility is not None:
                        import asyncio

                        asyncio.create_task(
                            visibility.ingestion_failed(
                                episode.uuid,
                                resolved_group_id,
                                'resolve_nodes',
                                str(e),
                                e.__class__.__name__,
                            )
                        )
                    raise

                state.mark_nodes_resolved(nodes)
                state.uuid_map = uuid_map
                state.node_duplicates = node_duplicates

                if visibility_enabled and visibility is not None:
                    import asyncio

                    asyncio.create_task(
                        visibility.stage_completed(
                            episode.uuid,
                            resolved_group_id,
                            'resolve_nodes',
                            {
                                'cached': False,
                                'duration_ms': int((time() - stage_started_at) * 1000),
                                'node_count': len(nodes),
                                'uuid_map_size': len(uuid_map),
                                'duplicate_count': len(node_duplicates),
                            },
                        )
                    )
            else:
                nodes = state.resolved_nodes or []
                logger.info(
                    f'Episode {episode.uuid}: Using cached resolved nodes ({len(nodes)} nodes)'
                )
                uuid_map = state.uuid_map or {}
                node_duplicates = state.node_duplicates or []
                if visibility_enabled and visibility is not None:
                    import asyncio

                    asyncio.create_task(
                        visibility.stage_completed(
                            episode.uuid,
                            resolved_group_id,
                            'resolve_nodes',
                            {
                                'cached': True,
                                'node_count': len(nodes),
                                'uuid_map_size': len(uuid_map),
                                'duplicate_count': len(node_duplicates),
                            },
                        )
                    )

            # Stage 3: Extract edges (with retry)
            if not state.edges_extracted:
                stage_started_at = time()
                if visibility_enabled and visibility is not None:
                    import asyncio

                    asyncio.create_task(
                        visibility.stage_started(
                            episode.uuid,
                            resolved_group_id,
                            'extract_edges',
                            {'cached': False},
                        )
                    )

                try:
                    extracted_edges = await self._extract_edges_with_retry(
                        episode,
                        extracted_nodes,
                        previous_episodes,
                        edge_type_map,
                        resolved_group_id,
                        resolved_edge_types,
                        state,
                    )
                except Exception as e:
                    if visibility_enabled and visibility is not None:
                        import asyncio

                        asyncio.create_task(
                            visibility.ingestion_failed(
                                episode.uuid,
                                resolved_group_id,
                                'extract_edges',
                                str(e),
                                e.__class__.__name__,
                            )
                        )
                    raise

                state.mark_edges_extracted(extracted_edges)

                if visibility_enabled and visibility is not None:
                    import asyncio

                    asyncio.create_task(
                        visibility.stage_completed(
                            episode.uuid,
                            resolved_group_id,
                            'extract_edges',
                            {
                                'cached': False,
                                'duration_ms': int((time() - stage_started_at) * 1000),
                                'edge_count': len(extracted_edges),
                            },
                        )
                    )
            else:
                extracted_edges = state.extracted_edges or []
                logger.info(
                    f'Episode {episode.uuid}: Using cached extracted edges ({len(extracted_edges)} edges)'
                )
                if visibility_enabled and visibility is not None:
                    import asyncio

                    asyncio.create_task(
                        visibility.stage_completed(
                            episode.uuid,
                            resolved_group_id,
                            'extract_edges',
                            {
                                'cached': True,
                                'edge_count': len(extracted_edges),
                            },
                        )
                    )

            # Continue with edge processing (non-LLM operations, less likely to fail)
            edge_type_map_default = (
                {('Entity', 'Entity'): list(resolved_edge_types.keys())}
                if resolved_edge_types
                else {('Entity', 'Entity'): []}
            )

            edges = resolve_edge_pointers(extracted_edges, uuid_map)

            # Extract attributes with graceful degradation
            # If attribute extraction fails, we still want to save nodes/edges
            resolution_started_at = time()
            resolution_attr_error: str | None = None
            if visibility_enabled and visibility is not None:
                import asyncio

                asyncio.create_task(
                    visibility.stage_started(
                        episode.uuid,
                        resolved_group_id,
                        'resolve_edges',
                        {'use_dspy': self.use_dspy},
                    )
                )

            try:
                if self.use_dspy:
                    logger.info(f'Episode {episode.uuid}: Extracting attributes [DSPy]')
                    (resolved_edges, invalidated_edges), hydrated_nodes = await semaphore_gather(
                        resolve_extracted_edges(
                            self.clients,
                            edges,
                            episode,
                            nodes,
                            resolved_edge_types,
                            edge_type_map or edge_type_map_default,
                        ),
                        self._extract_attributes_dspy(nodes, episode, previous_episodes),
                        max_coroutines=self.max_coroutines,
                    )
                else:
                    (resolved_edges, invalidated_edges), hydrated_nodes = await semaphore_gather(
                        resolve_extracted_edges(
                            self.clients,
                            edges,
                            episode,
                            nodes,
                            resolved_edge_types,
                            edge_type_map or edge_type_map_default,
                        ),
                        extract_attributes_from_nodes(
                            self.clients, nodes, episode, previous_episodes, entity_types
                        ),
                        max_coroutines=self.max_coroutines,
                    )
            except Exception as attr_error:
                resolution_attr_error = str(attr_error)
                logger.warning(
                    f'Attribute extraction failed: {attr_error}. '
                    f'Continuing with nodes without enriched attributes.'
                )
                (resolved_edges, invalidated_edges) = await resolve_extracted_edges(
                    self.clients,
                    edges,
                    episode,
                    nodes,
                    resolved_edge_types,
                    edge_type_map or edge_type_map_default,
                )
                hydrated_nodes = nodes

            if visibility_enabled and visibility is not None:
                import asyncio

                asyncio.create_task(
                    visibility.stage_completed(
                        episode.uuid,
                        resolved_group_id,
                        'resolve_edges',
                        {
                            'duration_ms': int((time() - resolution_started_at) * 1000),
                            'resolved_edge_count': len(resolved_edges),
                            'invalidated_edge_count': len(invalidated_edges),
                            'attribute_extraction_error': resolution_attr_error,
                        },
                    )
                )

            duplicate_of_edges, merge_operations, duplicate_nodes_to_save = (
                build_duplicate_of_edges(episode, now, node_duplicates)
            )

            entity_edges = resolved_edges + invalidated_edges + duplicate_of_edges
            episodic_edges = build_episodic_edges(
                nodes, episode.uuid, now, episode_group_id=episode.group_id
            )
            episode.entity_edges = [edge.uuid for edge in entity_edges]

            # Save to database
            if not state.episode_created:
                persist_started_at = time()
                if visibility_enabled and visibility is not None:
                    import asyncio

                    asyncio.create_task(
                        visibility.stage_started(
                            episode.uuid,
                            resolved_group_id,
                            'persist',
                            {},
                        )
                    )

                try:
                    if not self.store_raw_episode_content:
                        episode.content = ''

                    all_nodes_to_save = hydrated_nodes + duplicate_nodes_to_save

                    await add_nodes_and_edges_bulk(
                        self.driver,
                        [episode],
                        episodic_edges,
                        all_nodes_to_save,
                        entity_edges,
                        self.embedder,
                    )

                    auto_merge_enabled = (
                        os.getenv('GRAPHITI_ENABLE_AUTO_MERGE', 'false').lower() == 'true'
                    )

                    if merge_operations and auto_merge_enabled:
                        from graphiti_core.utils.maintenance.edge_operations import (
                            execute_merge_operations,
                        )

                        logger.info(
                            f'Auto-merge enabled: executing {len(merge_operations)} merge operations'
                        )
                        await execute_merge_operations(
                            self.driver,
                            merge_operations,
                            allow_cross_graph_merge=self.enable_cross_graph_deduplication,
                        )
                    elif merge_operations and not auto_merge_enabled:
                        logger.info(
                            f'Auto-merge disabled: skipping {len(merge_operations)} merge operations (set GRAPHITI_ENABLE_AUTO_MERGE=true to enable)'
                        )

                    state.mark_completed()
                    logger.info(f'Episode {episode.uuid}: Successfully saved to database')

                    if visibility_enabled and visibility is not None:
                        import asyncio

                        asyncio.create_task(
                            visibility.stage_completed(
                                episode.uuid,
                                resolved_group_id,
                                'persist',
                                {
                                    'duration_ms': int((time() - persist_started_at) * 1000),
                                    'node_count': len(all_nodes_to_save),
                                    'entity_edge_count': len(entity_edges),
                                    'episodic_edge_count': len(episodic_edges),
                                    'merge_operation_count': len(merge_operations),
                                },
                            )
                        )

                except Exception as e:
                    if visibility_enabled and visibility is not None:
                        import asyncio

                        asyncio.create_task(
                            visibility.ingestion_failed(
                                episode.uuid,
                                resolved_group_id,
                                'persist',
                                str(e),
                                e.__class__.__name__,
                            )
                        )
                    raise

            # Update communities if requested
            if update_communities:
                await semaphore_gather(
                    *[
                        update_community(self.driver, self.llm_client, self.embedder, node)
                        for node in nodes
                    ],
                    max_coroutines=self.max_coroutines,
                )

            # Clean up cache for completed episodes
            ingestion_cache.remove_state(episode.uuid)

            end = time()
            logger.info(f'Completed resilient add_episode in {(end - start) * 1000} ms')

            if visibility_enabled and visibility is not None:
                import asyncio

                asyncio.create_task(
                    visibility.ingestion_completed(
                        episode.uuid,
                        resolved_group_id,
                        {
                            'duration_ms': int((end - start) * 1000),
                            'node_count': len(nodes),
                            'entity_edge_count': len(entity_edges),
                        },
                    )
                )

            return AddEpisodeResults(episode=episode, nodes=nodes, edges=entity_edges)

        except Exception as e:
            failed_episode = episode if 'episode' in locals() and episode is not None else None
            failed_episode_uuid = failed_episode.uuid if failed_episode is not None else 'unknown'
            logger.error(f'Resilient ingestion failed for episode {failed_episode_uuid}: {e}')

            if visibility_enabled and visibility is not None and failed_episode is not None:
                import asyncio

                asyncio.create_task(
                    visibility.ingestion_failed(
                        failed_episode.uuid,
                        resolved_group_id,
                        'add_episode_resilient',
                        str(e),
                        e.__class__.__name__,
                    )
                )

            raise e

    @retry_with_backoff(max_retries=3, base_delay=2.0)
    async def _extract_nodes_with_retry(
        self,
        episode: EpisodicNode,
        previous_episodes: list[EpisodicNode],
        entity_types: dict[str, BaseModel] | None,
        excluded_entity_types: list[str] | None,
        state: ResilientIngestionState,
    ) -> list[EntityNode]:
        """Extract nodes with retry logic."""
        state.nodes_extract_attempts += 1
        logger.info(
            f'Episode {episode.uuid}: Extracting nodes (attempt {state.nodes_extract_attempts})'
            f'{" [DSPy]" if self.use_dspy else ""}'
        )

        if self.use_dspy:
            return await self._extract_nodes_dspy(episode, previous_episodes, entity_types)

        return await extract_nodes(
            self.clients, episode, previous_episodes, entity_types, excluded_entity_types
        )

    async def _extract_nodes_dspy(
        self,
        episode: EpisodicNode,
        previous_episodes: list[EpisodicNode],
        entity_types: dict[str, BaseModel] | None,
    ) -> list[EntityNode]:
        """Extract nodes using DSPy pipeline."""
        import asyncio
        from graphiti_core.utils.datetime_utils import utc_now

        pipeline = _get_dspy_pipeline(episode.group_id)

        # Convert entity_types to DSPy format if provided
        dspy_entity_types = None
        if entity_types:
            dspy_entity_types = [
                {'id': i, 'name': name, 'description': f'{name} entity type'}
                for i, name in enumerate(entity_types.keys())
            ]

        # Format previous episodes for DSPy
        prev_messages = [{'content': ep.content} for ep in previous_episodes if ep.content]

        # Run DSPy extraction (sync, so wrap in executor)
        def run_extraction():
            return pipeline.node_extractor(
                current_message=episode.content,
                entity_types=dspy_entity_types or pipeline.entity_types,
                previous_messages=prev_messages,
                custom_instructions='',
            )

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, run_extraction)

        from graphiti_core.utils.maintenance.node_operations import is_garbage_entity

        now = utc_now()
        extracted = []
        filtered_count = 0
        for entity in result.extracted_entities:
            if is_garbage_entity(entity.name):
                logger.debug(f"DSPy filtering garbage entity: '{entity.name}'")
                filtered_count += 1
                continue

            entity_type = (
                pipeline.entity_types[entity.entity_type_id]['name']
                if entity.entity_type_id < len(pipeline.entity_types)
                else 'Entity'
            )
            node = EntityNode(
                name=entity.name,
                group_id=episode.group_id,
                labels=[entity_type],
                created_at=now,
                summary='',
            )
            extracted.append(node)

        logger.info(
            f'DSPy extracted {len(extracted)} entities from episode {episode.uuid}'
            f'{f" (filtered {filtered_count} garbage)" if filtered_count else ""}'
        )
        return extracted

    @retry_with_backoff(max_retries=3, base_delay=2.0)
    async def _resolve_nodes_with_retry(
        self,
        extracted_nodes: list[EntityNode],
        episode: EpisodicNode,
        previous_episodes: list[EpisodicNode],
        entity_types: dict[str, BaseModel] | None,
        state: ResilientIngestionState,
    ) -> tuple[list[EntityNode], dict[str, str], list[tuple[EntityNode, EntityNode]]]:
        """Resolve nodes with retry logic."""
        state.nodes_resolve_attempts += 1
        logger.info(
            f'Episode {episode.uuid}: Resolving nodes (attempt {state.nodes_resolve_attempts})'
            f'{" [DSPy]" if self.use_dspy else ""}'
        )

        if self.use_dspy:
            return await self._resolve_nodes_dspy(extracted_nodes, episode, previous_episodes)

        return await resolve_extracted_nodes(
            self.clients,
            extracted_nodes,
            episode,
            previous_episodes,
            entity_types,
            existing_nodes_override=None,
            enable_cross_graph_deduplication=self.enable_cross_graph_deduplication,
        )

    async def _resolve_nodes_dspy(
        self,
        extracted_nodes: list[EntityNode],
        episode: EpisodicNode,
        previous_episodes: list[EpisodicNode],
    ) -> tuple[list[EntityNode], dict[str, str], list[tuple[EntityNode, EntityNode]]]:
        """Resolve nodes using DSPy NodeResolver."""
        import asyncio
        from graphiti_core.utils.datetime_utils import utc_now

        pipeline = _get_dspy_pipeline(episode.group_id)

        # Format extracted entities for DSPy
        extracted_entities = [
            {'id': i, 'name': node.name, 'entity_type': node.labels[0] if node.labels else 'Entity'}
            for i, node in enumerate(extracted_nodes)
        ]

        # Get existing entities from database for comparison
        existing_entities = await self._get_existing_entities_for_resolution(
            episode.group_id, extracted_nodes
        )

        # Format previous episodes for DSPy
        prev_messages = [{'content': ep.content} for ep in previous_episodes if ep.content]

        # If no existing entities, all extracted nodes are new
        if not existing_entities:
            logger.info(
                f'DSPy resolution: No existing entities, all {len(extracted_nodes)} are new'
            )
            uuid_map = {node.uuid: node.uuid for node in extracted_nodes}
            return extracted_nodes, uuid_map, []

        # Run DSPy resolution (sync, so wrap in executor)
        def run_resolution():
            return pipeline.node_resolver(
                current_message=episode.content,
                extracted_entities=extracted_entities,
                existing_entities=existing_entities,
                previous_messages=prev_messages,
            )

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, run_resolution)

        # Convert DSPy output to legacy format
        resolved_nodes: list[EntityNode] = []
        uuid_map: dict[str, str] = {}
        node_duplicates: list[tuple[EntityNode, EntityNode]] = []

        for resolution in result.entity_resolutions:
            original_node = (
                extracted_nodes[resolution.id] if resolution.id < len(extracted_nodes) else None
            )
            if not original_node:
                continue

            if resolution.duplicate_idx >= 0 and resolution.duplicate_idx < len(existing_entities):
                # Found duplicate - use existing entity
                existing = existing_entities[resolution.duplicate_idx]
                existing_node = EntityNode(
                    uuid=existing.get('uuid', original_node.uuid),
                    name=existing.get('name', resolution.name),
                    group_id=episode.group_id,
                    labels=original_node.labels,
                    created_at=original_node.created_at,
                    summary=existing.get('summary', ''),
                )
                resolved_nodes.append(existing_node)
                uuid_map[original_node.uuid] = existing_node.uuid
                node_duplicates.append((original_node, existing_node))
                logger.debug(
                    f"DSPy resolved '{original_node.name}' as duplicate of '{existing_node.name}'"
                )
            else:
                # New entity - keep original
                resolved_nodes.append(original_node)
                uuid_map[original_node.uuid] = original_node.uuid

        logger.info(
            f'DSPy resolved {len(extracted_nodes)} nodes: '
            f'{len(resolved_nodes)} resolved, {len(node_duplicates)} duplicates'
        )
        return resolved_nodes, uuid_map, node_duplicates

    async def _get_existing_entities_for_resolution(
        self,
        group_id: str,
        extracted_nodes: list[EntityNode],
    ) -> list[dict[str, Any]]:
        """Get existing entities from database for DSPy resolution comparison."""
        if not extracted_nodes:
            return []

        # Query existing entities with similar names
        names = [node.name for node in extracted_nodes]

        if self.enable_cross_graph_deduplication:
            query = """
            MATCH (n:Entity)
            WHERE n.name IN $names
            RETURN n.uuid AS uuid, n.name AS name, n.summary AS summary, 
                   labels(n) AS labels, n.group_id AS group_id
            ORDER BY n.created_at
            """
            records, _, _ = await self.driver.execute_query(query, names=names)
        else:
            query = """
            MATCH (n:Entity)
            WHERE n.name IN $names AND n.group_id = $group_id
            RETURN n.uuid AS uuid, n.name AS name, n.summary AS summary,
                   labels(n) AS labels, n.group_id AS group_id
            ORDER BY n.created_at
            """
            records, _, _ = await self.driver.execute_query(query, names=names, group_id=group_id)

        existing = []
        for i, record in enumerate(records):
            existing.append(
                {
                    'idx': i,
                    'uuid': record.get('uuid'),
                    'name': record.get('name'),
                    'summary': record.get('summary', ''),
                    'entity_type': record.get('labels', ['Entity'])[0]
                    if record.get('labels')
                    else 'Entity',
                }
            )

        return existing

    @retry_with_backoff(max_retries=3, base_delay=2.0)
    async def _extract_edges_with_retry(
        self,
        episode: EpisodicNode,
        extracted_nodes: list[EntityNode],
        previous_episodes: list[EpisodicNode],
        edge_type_map: dict[tuple[str, str], list[str]] | None,
        group_id: str,
        edge_types: dict[str, BaseModel | type[BaseModel]] | None,
        state: ResilientIngestionState,
    ) -> list[EntityEdge]:
        """Extract edges with retry logic."""
        state.edges_extract_attempts += 1
        logger.info(
            f'Episode {episode.uuid}: Extracting edges (attempt {state.edges_extract_attempts})'
            f'{" [DSPy]" if self.use_dspy else ""}'
        )

        if self.use_dspy:
            return await self._extract_edges_dspy(
                episode, extracted_nodes, previous_episodes, edge_types
            )

        edge_type_map_default = (
            {('Entity', 'Entity'): list(edge_types.keys())}
            if edge_types is not None
            else {('Entity', 'Entity'): []}
        )

        return await extract_edges(
            self.clients,
            episode,
            extracted_nodes,
            previous_episodes,
            edge_type_map or edge_type_map_default,
            group_id,
            edge_types,
        )

    async def _extract_edges_dspy(
        self,
        episode: EpisodicNode,
        extracted_nodes: list[EntityNode],
        previous_episodes: list[EpisodicNode],
        edge_types: dict[str, BaseModel | type[BaseModel]] | None,
    ) -> list[EntityEdge]:
        """Extract edges using DSPy pipeline."""
        import asyncio
        from graphiti_core.utils.datetime_utils import utc_now

        if len(extracted_nodes) < 2:
            return []

        pipeline = _get_dspy_pipeline(episode.group_id)
        now = utc_now()

        # Format entities for DSPy (extracted_nodes are EntityNode objects)
        entities = [
            {'id': i, 'name': node.name, 'type': node.labels[0] if node.labels else 'Entity'}
            for i, node in enumerate(extracted_nodes)
        ]

        # Format previous episodes
        prev_messages = [{'content': ep.content} for ep in previous_episodes if ep.content]

        # Convert edge_types if provided
        dspy_edge_types = []
        if edge_types:
            dspy_edge_types = [
                {'name': name, 'description': f'{name} relationship'} for name in edge_types.keys()
            ]

        # Run DSPy extraction
        def run_extraction():
            return pipeline.edge_extractor(
                current_message=episode.content,
                entities=entities,
                reference_time=episode.valid_at.isoformat() if episode.valid_at else '',
                previous_messages=prev_messages,
                edge_types=dspy_edge_types,
                custom_instructions='',
            )

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, run_extraction)

        # Convert DSPy output to EntityEdge objects (matching extract_edges output)
        extracted_edges = []
        for edge in result.edges:
            source_idx = edge.source_entity_id
            target_idx = edge.target_entity_id

            if source_idx < len(extracted_nodes) and target_idx < len(extracted_nodes):
                entity_edge = EntityEdge(
                    source_node_uuid=extracted_nodes[source_idx].uuid,
                    target_node_uuid=extracted_nodes[target_idx].uuid,
                    name=edge.relation_type,
                    fact=edge.fact,
                    group_id=episode.group_id,
                    created_at=now,
                    episodes=[episode.uuid],
                    valid_at=episode.valid_at,
                    invalid_at=None,
                )
                extracted_edges.append(entity_edge)

        logger.info(f'DSPy extracted {len(extracted_edges)} edges from episode {episode.uuid}')
        return extracted_edges

    async def _extract_attributes_dspy(
        self,
        nodes: list[EntityNode],
        episode: EpisodicNode,
        previous_episodes: list[EpisodicNode],
    ) -> list[EntityNode]:
        """Extract attributes (summaries) using DSPy pipeline."""
        import asyncio

        if not nodes:
            return nodes

        pipeline = _get_dspy_pipeline(episode.group_id)
        prev_messages = [{'content': ep.content} for ep in previous_episodes if ep.content]

        use_batch = os.environ.get('USE_BATCH_EXTRACTION', 'true').lower() == 'true'
        batch_size = int(os.environ.get('BATCH_EXTRACTION_SIZE', '5'))

        if use_batch and len(nodes) > 1:
            updated_nodes = await self._extract_attributes_dspy_batch(
                nodes, episode, prev_messages, pipeline, batch_size
            )
        else:

            def run_summaries():
                updated = []
                for node in nodes:
                    try:
                        result = pipeline.summary_generator(
                            current_message=episode.content,
                            entity_name=node.name,
                            previous_messages=prev_messages,
                            existing_summary=node.summary or '',
                        )
                        node.summary = result.summary
                    except Exception as e:
                        logger.warning(f'DSPy summary failed for {node.name}: {e}')
                    updated.append(node)
                return updated

            loop = asyncio.get_event_loop()
            updated_nodes = await loop.run_in_executor(None, run_summaries)

        await create_entity_node_embeddings(self.embedder, updated_nodes)
        logger.info(f'DSPy generated summaries for {len(updated_nodes)} nodes')
        return updated_nodes

    async def _extract_attributes_dspy_batch(
        self,
        nodes: list[EntityNode],
        episode: EpisodicNode,
        prev_messages: list[dict],
        pipeline: Any,
        batch_size: int,
    ) -> list[EntityNode]:
        """Batch extract summaries using DSPy BatchSummaryGenerationSignature."""
        import asyncio
        import json

        import dspy

        from graphiti_core.dspy.config import with_lm
        from graphiti_core.dspy.signatures import BatchSummaries, BatchSummaryGenerationSignature

        for i in range(0, len(nodes), batch_size):
            batch = nodes[i : i + batch_size]

            entities_data = [
                {'name': node.name, 'existing_summary': node.summary or ''} for node in batch
            ]

            try:
                entities_json = json.dumps(entities_data, indent=2)
                prev_json = json.dumps(prev_messages, indent=2)
                content = episode.content

                def run_batch(
                    ej: str = entities_json, c: str = content, pj: str = prev_json
                ) -> Any:
                    predictor = dspy.Predict(BatchSummaryGenerationSignature)
                    with with_lm('simple'):
                        result = predictor(
                            previous_messages=pj,
                            current_message=c,
                            entities=ej,
                        )
                    return result.summaries

                loop = asyncio.get_event_loop()
                batch_result = await loop.run_in_executor(None, run_batch)

                if isinstance(batch_result, BatchSummaries):
                    summaries_list = batch_result.summaries
                elif isinstance(batch_result, dict):
                    summaries_list = BatchSummaries(**batch_result).summaries
                elif isinstance(batch_result, list):
                    summaries_list = batch_result
                else:
                    raise ValueError(f'Unexpected batch result type: {type(batch_result)}')

                summary_map: dict[str, str] = {}
                for s in summaries_list:
                    if hasattr(s, 'entity_name'):
                        summary_map[s.entity_name.lower()] = s.summary
                    elif isinstance(s, dict):
                        summary_map[s.get('entity_name', '').lower()] = s.get('summary', '')

                updated_count = 0
                for node in batch:
                    summary = summary_map.get(node.name.lower())
                    if summary:
                        node.summary = summary
                        updated_count += 1

                logger.info(
                    f'DSPy batch extracted summaries for {updated_count}/{len(batch)} nodes '
                    f'in one LLM call'
                )

            except Exception as e:
                logger.warning(
                    f'DSPy batch summary extraction failed, falling back to individual: {e}'
                )
                cur_batch = batch
                cur_pipeline = pipeline
                cur_content = episode.content
                cur_prev = prev_messages

                def run_individual(
                    b: list = cur_batch,
                    p: Any = cur_pipeline,
                    c: str = cur_content,
                    pm: list = cur_prev,
                ) -> None:
                    for node in b:
                        try:
                            result = p.summary_generator(
                                current_message=c,
                                entity_name=node.name,
                                previous_messages=pm,
                                existing_summary=node.summary or '',
                            )
                            node.summary = result.summary
                        except Exception as ex:
                            logger.warning(f'DSPy summary failed for {node.name}: {ex}')

                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, run_individual)

        return nodes

    ##### EXPERIMENTAL #####
    async def add_episode_bulk(
        self,
        bulk_episodes: list[RawEpisode],
        group_id: str | None = None,
        entity_types: dict[str, BaseModel] | None = None,
        excluded_entity_types: list[str] | None = None,
        edge_types: dict[str, BaseModel] | None = None,
        edge_type_map: dict[tuple[str, str], list[str]] | None = None,
    ):
        """
        Process multiple episodes in bulk and update the graph.

        This method extracts information from multiple episodes, creates nodes and edges,
        and updates the graph database accordingly, all in a single batch operation.

        Parameters
        ----------
        bulk_episodes : list[RawEpisode]
            A list of RawEpisode objects to be processed and added to the graph.
        group_id : str | None
            An id for the graph partition the episode is a part of.

        Returns
        -------
        None

        Notes
        -----
        This method performs several steps including:
        - Saving all episodes to the database
        - Retrieving previous episode context for each new episode
        - Extracting nodes and edges from all episodes
        - Generating embeddings for nodes and edges
        - Deduplicating nodes and edges
        - Saving nodes, episodic edges, and entity edges to the knowledge graph

        This bulk operation is designed for efficiency when processing multiple episodes
        at once. However, it's important to ensure that the bulk operation doesn't
        overwhelm system resources. Consider implementing rate limiting or chunking for
        very large batches of episodes.

        Important: This method does not perform edge invalidation or date extraction steps.
        If these operations are required, use the `add_episode` method instead for each
        individual episode.
        """
        try:
            start = time()
            now = utc_now()

            # if group_id is None, use the default group id by the provider
            group_id = group_id or get_default_group_id(self.driver.provider)
            validate_group_id(group_id)
            resolved_edge_types: dict[str, BaseModel | type[BaseModel]] = (
                {name: model for name, model in edge_types.items()}
                if edge_types is not None
                else {}
            )

            # Create default edge type map
            edge_type_map_default = (
                {('Entity', 'Entity'): list(resolved_edge_types.keys())}
                if resolved_edge_types
                else {('Entity', 'Entity'): []}
            )

            # Filter out episodes that already exist to prevent duplicate processing
            new_episodes = []
            for episode in bulk_episodes:
                if episode.uuid is not None:
                    existing_episode = await EpisodicNode.get_by_uuid(self.driver, episode.uuid)
                    if existing_episode is not None:
                        logger.info(f'Skipping already processed episode: {episode.uuid}')
                        continue  # Skip this episode as it's already been processed

                # Create new episode (either UUID is None or episode doesn't exist in DB)
                new_episode = EpisodicNode(
                    name=episode.name,
                    labels=[],
                    source=episode.source,
                    content=episode.content,
                    source_description=episode.source_description,
                    group_id=group_id,
                    created_at=now,
                    valid_at=ensure_utc(episode.reference_time) or episode.reference_time,
                )
                # If episode had a UUID, preserve it for deterministic processing
                if episode.uuid is not None:
                    new_episode.uuid = episode.uuid

                new_episodes.append(new_episode)

            episodes = new_episodes

            # Early return if no new episodes to process
            if not episodes:
                logger.info('No new episodes to process - all episodes already exist')
                return

            episodes_by_uuid: dict[str, EpisodicNode] = {
                episode.uuid: episode for episode in episodes
            }

            # Save all episodes
            await add_nodes_and_edges_bulk(
                driver=self.driver,
                episodic_nodes=episodes,
                episodic_edges=[],
                entity_nodes=[],
                entity_edges=[],
                embedder=self.embedder,
            )

            # Get previous episode context for each episode
            episode_context = await retrieve_previous_episodes_bulk(self.driver, episodes)

            # Extract all nodes and edges for each episode
            extracted_nodes_bulk, extracted_edges_bulk = await extract_nodes_and_edges_bulk(
                self.clients,
                episode_context,
                edge_type_map=edge_type_map or edge_type_map_default,
                edge_types=edge_types,
                entity_types=entity_types,
                excluded_entity_types=excluded_entity_types,
            )

            # Dedupe extracted nodes in memory
            nodes_by_episode, uuid_map = await dedupe_nodes_bulk(
                self.clients,
                extracted_nodes_bulk,
                episode_context,
                entity_types,
                enable_cross_graph_deduplication=self.enable_cross_graph_deduplication,
            )

            # Create Episodic Edges
            episodic_edges: list[EpisodicEdge] = []
            for episode_uuid, nodes in nodes_by_episode.items():
                # Get episode's group_id for cross-group edge UUID generation
                episode_node = episodes_by_uuid.get(episode_uuid)
                episode_group_id = (
                    episode_node.group_id if episode_node is not None else episodes[0].group_id
                )
                episodic_edges.extend(
                    build_episodic_edges(
                        nodes,
                        episode_uuid,
                        now,
                        episode_group_id=episode_group_id or group_id,
                    )
                )

            # re-map edge pointers so that they don't point to discard dupe nodes
            extracted_edges_bulk_updated: list[list[EntityEdge]] = [
                resolve_edge_pointers(edges, uuid_map) for edges in extracted_edges_bulk
            ]

            # Dedupe extracted edges in memory
            edges_by_episode = await dedupe_edges_bulk(
                self.clients,
                extracted_edges_bulk_updated,
                episode_context,
                [],
                edge_types or {},
                edge_type_map or edge_type_map_default,
            )

            # Extract node attributes
            nodes_by_uuid: dict[str, EntityNode] = {
                node.uuid: node for nodes in nodes_by_episode.values() for node in nodes
            }

            extract_attributes_params: list[tuple[EntityNode, list[EpisodicNode]]] = []
            for node in nodes_by_uuid.values():
                episode_uuids: list[str] = []
                for episode_uuid, mentioned_nodes in nodes_by_episode.items():
                    for mentioned_node in mentioned_nodes:
                        if node.uuid == mentioned_node.uuid:
                            episode_uuids.append(episode_uuid)
                            break

                episode_mentions: list[EpisodicNode] = [
                    episodes_by_uuid[episode_uuid] for episode_uuid in episode_uuids
                ]
                episode_mentions.sort(key=lambda x: x.valid_at, reverse=True)

                extract_attributes_params.append((node, episode_mentions))

            new_hydrated_nodes: list[list[EntityNode]] = await semaphore_gather(
                *[
                    extract_attributes_from_nodes(
                        self.clients,
                        [params[0]],
                        params[1][0],
                        params[1][0:],
                        entity_types,
                    )
                    for params in extract_attributes_params
                ]
            )

            hydrated_nodes = [node for nodes in new_hydrated_nodes for node in nodes]

            # Update nodes_by_uuid map with the hydrated nodes
            for hydrated_node in hydrated_nodes:
                nodes_by_uuid[hydrated_node.uuid] = hydrated_node

            # Resolve nodes and edges against the existing graph
            nodes_by_episode_unique: dict[str, list[EntityNode]] = {}
            nodes_uuid_set: set[str] = set()
            for episode, _ in episode_context:
                nodes_by_episode_unique[episode.uuid] = []
                nodes = [nodes_by_uuid[node.uuid] for node in nodes_by_episode[episode.uuid]]
                for node in nodes:
                    if node.uuid not in nodes_uuid_set:
                        nodes_by_episode_unique[episode.uuid].append(node)
                        nodes_uuid_set.add(node.uuid)

            node_results = await semaphore_gather(
                *[
                    resolve_extracted_nodes(
                        self.clients,
                        nodes_by_episode_unique[episode.uuid],
                        episode,
                        previous_episodes,
                        entity_types,
                        existing_nodes_override=None,
                        enable_cross_graph_deduplication=self.enable_cross_graph_deduplication,
                    )
                    for episode, previous_episodes in episode_context
                ]
            )

            resolved_nodes: list[EntityNode] = []
            uuid_map: dict[str, str] = {}
            node_duplicates: list[tuple[EntityNode, EntityNode]] = []
            for result in node_results:
                resolved_nodes.extend(result[0])
                uuid_map.update(result[1])
                node_duplicates.extend(result[2])

            # Update nodes_by_uuid map with the resolved nodes
            for resolved_node in resolved_nodes:
                nodes_by_uuid[resolved_node.uuid] = resolved_node

            # update nodes_by_episode_unique mapping
            for episode_uuid, nodes in nodes_by_episode_unique.items():
                updated_nodes: list[EntityNode] = []
                for node in nodes:
                    updated_node_uuid = uuid_map.get(node.uuid, node.uuid)
                    updated_node = nodes_by_uuid[updated_node_uuid]
                    updated_nodes.append(updated_node)

                nodes_by_episode_unique[episode_uuid] = updated_nodes

            hydrated_nodes_results: list[list[EntityNode]] = await semaphore_gather(
                *[
                    extract_attributes_from_nodes(
                        self.clients,
                        nodes_by_episode_unique[episode.uuid],
                        episode,
                        previous_episodes,
                        entity_types,
                    )
                    for episode, previous_episodes in episode_context
                ]
            )

            final_hydrated_nodes = [node for nodes in hydrated_nodes_results for node in nodes]

            edges_by_episode_unique: dict[str, list[EntityEdge]] = {}
            edges_uuid_set: set[str] = set()
            for episode_uuid, edges in edges_by_episode.items():
                edges_with_updated_pointers = resolve_edge_pointers(edges, uuid_map)
                edges_by_episode_unique[episode_uuid] = []

                for edge in edges_with_updated_pointers:
                    if edge.uuid not in edges_uuid_set:
                        edges_by_episode_unique[episode_uuid].append(edge)
                        edges_uuid_set.add(edge.uuid)

            edge_results = await semaphore_gather(
                *[
                    resolve_extracted_edges(
                        self.clients,
                        edges_by_episode_unique[episode.uuid],
                        episode,
                        hydrated_nodes,
                        resolved_edge_types,
                        edge_type_map or edge_type_map_default,
                    )
                    for episode in episodes
                ]
            )

            resolved_edges: list[EntityEdge] = []
            invalidated_edges: list[EntityEdge] = []
            for result in edge_results:
                resolved_edges.extend(result[0])
                invalidated_edges.extend(result[1])

            # Resolved pointers for episodic edges
            resolved_episodic_edges = resolve_edge_pointers(episodic_edges, uuid_map)

            # Build duplicate edges for audit trail (similar to single episode flow)
            duplicate_of_edges: list[EntityEdge] = []
            merge_operations: list[tuple[str, str]] = []
            duplicate_nodes_to_save: list[EntityNode] = []

            if node_duplicates:
                # Use the first episode's timestamp for duplicate edges
                # (or could aggregate across all episodes if preferred)
                duplicate_of_edges, merge_operations, duplicate_nodes_to_save = (
                    build_duplicate_of_edges(episodes[0], now, node_duplicates)
                )
                logger.info(f'Found {len(node_duplicates)} duplicates to merge in bulk pipeline')

            # Combine all nodes to be saved (including duplicate nodes)
            all_nodes_to_save = final_hydrated_nodes + duplicate_nodes_to_save

            # save data to KG
            await add_nodes_and_edges_bulk(
                self.driver,
                episodes,
                resolved_episodic_edges,
                all_nodes_to_save,
                resolved_edges + invalidated_edges + duplicate_of_edges,
                self.embedder,
            )

            # Execute merge operations after nodes and edges are saved
            # Feature flag: GRAPHITI_ENABLE_AUTO_MERGE (default: false for safety)
            auto_merge_enabled = os.getenv('GRAPHITI_ENABLE_AUTO_MERGE', 'false').lower() == 'true'

            if merge_operations and auto_merge_enabled:
                from graphiti_core.utils.maintenance.edge_operations import execute_merge_operations

                logger.info(
                    f'Auto-merge enabled: executing {len(merge_operations)} merge operations (bulk)'
                )
                merge_stats = await execute_merge_operations(
                    self.driver,
                    merge_operations,
                    allow_cross_graph_merge=self.enable_cross_graph_deduplication,
                )
                logger.info(
                    f'Bulk merge complete: {merge_stats["total_merges"]} merges, '
                    f'{merge_stats["total_edges_transferred"]} edges transferred'
                )

            end = time()
            logger.info(f'Completed add_episode_bulk in {(end - start) * 1000} ms')

        except Exception as e:
            raise e

    async def build_communities(self, group_ids: list[str] | None = None) -> list[CommunityNode]:
        """
        Use a community clustering algorithm to find communities of nodes. Create community nodes summarising
        the content of these communities.
        ----------
        query : list[str] | None
            Optional. Create communities only for the listed group_ids. If blank the entire graph will be used.
        """
        # Clear existing communities
        await remove_communities(self.driver)

        community_nodes, community_edges = await build_communities(
            self.driver, self.llm_client, group_ids
        )

        await semaphore_gather(
            *[node.generate_name_embedding(self.embedder) for node in community_nodes],
            max_coroutines=self.max_coroutines,
        )

        await semaphore_gather(
            *[node.save(self.driver) for node in community_nodes],
            max_coroutines=self.max_coroutines,
        )
        await semaphore_gather(
            *[edge.save(self.driver) for edge in community_edges],
            max_coroutines=self.max_coroutines,
        )

        # Publish change events for community nodes/edges (GRAPH-106)
        if self.event_publisher is not None and self.event_publisher.is_enabled:
            try:
                await self.event_publisher.publish_bulk_changes(
                    'create', nodes=community_nodes, edges=community_edges, include_data=False
                )
                logger.info(
                    f'Published community change events: {len(community_nodes)} nodes, '
                    f'{len(community_edges)} edges'
                )
            except Exception as e:
                logger.warning(f'Failed to publish community change events: {e}')

        return community_nodes

    async def search(
        self,
        query: str,
        center_node_uuid: str | None = None,
        group_ids: list[str] | None = None,
        num_results=DEFAULT_SEARCH_LIMIT,
        search_filter: SearchFilters | None = None,
    ) -> list[EntityEdge]:
        """
        Perform a hybrid search on the knowledge graph.

        This method executes a search query on the graph, combining vector and
        text-based search techniques to retrieve relevant facts, returning the edges as a string.

        This is our basic out-of-the-box search, for more robust results we recommend using our more advanced
        search method graphiti.search_().

        Parameters
        ----------
        query : str
            The search query string.
        center_node_uuid: str, optional
            Facts will be reranked based on proximity to this node
        group_ids : list[str | None] | None, optional
            The graph partitions to return data from.
        num_results : int, optional
            The maximum number of results to return. Defaults to 10.

        Returns
        -------
        list
            A list of EntityEdge objects that are relevant to the search query.

        Notes
        -----
        This method uses a SearchConfig with num_episodes set to 0 and
        num_results set to the provided num_results parameter.

        The search is performed using the current date and time as the reference
        point for temporal relevance.
        """
        search_config = (
            EDGE_HYBRID_SEARCH_RRF if center_node_uuid is None else EDGE_HYBRID_SEARCH_NODE_DISTANCE
        )
        search_config.limit = num_results

        edges = (
            await search(
                self.clients,
                query,
                group_ids,
                search_config,
                search_filter if search_filter is not None else SearchFilters(),
                center_node_uuid,
            )
        ).edges

        return edges

    async def _search(
        self,
        query: str,
        config: SearchConfig,
        group_ids: list[str] | None = None,
        center_node_uuid: str | None = None,
        bfs_origin_node_uuids: list[str] | None = None,
        search_filter: SearchFilters | None = None,
    ) -> SearchResults:
        """DEPRECATED"""
        return await self.search_(
            query, config, group_ids, center_node_uuid, bfs_origin_node_uuids, search_filter
        )

    async def search_(
        self,
        query: str,
        config: SearchConfig = COMBINED_HYBRID_SEARCH_CROSS_ENCODER,
        group_ids: list[str] | None = None,
        center_node_uuid: str | None = None,
        bfs_origin_node_uuids: list[str] | None = None,
        search_filter: SearchFilters | None = None,
    ) -> SearchResults:
        """search_ (replaces _search) is our advanced search method that returns Graph objects (nodes and edges) rather
        than a list of facts. This endpoint allows the end user to utilize more advanced features such as filters and
        different search and reranker methodologies across different layers in the graph.

        For different config recipes refer to search/search_config_recipes.
        """

        return await search(
            self.clients,
            query,
            group_ids,
            config,
            search_filter if search_filter is not None else SearchFilters(),
            center_node_uuid,
            bfs_origin_node_uuids,
        )

    async def get_nodes_and_edges_by_episode(self, episode_uuids: list[str]) -> SearchResults:
        episodes = await EpisodicNode.get_by_uuids(self.driver, episode_uuids)

        edges_list = await semaphore_gather(
            *[EntityEdge.get_by_uuids(self.driver, episode.entity_edges) for episode in episodes],
            max_coroutines=self.max_coroutines,
        )

        edges: list[EntityEdge] = [edge for lst in edges_list for edge in lst]

        nodes = await get_mentioned_nodes(self.driver, episodes)

        return SearchResults(edges=edges, nodes=nodes, episodes=[], communities=[])

    async def add_triplet(self, source_node: EntityNode, edge: EntityEdge, target_node: EntityNode):
        if source_node.name_embedding is None:
            await source_node.generate_name_embedding(self.embedder)
        if target_node.name_embedding is None:
            await target_node.generate_name_embedding(self.embedder)
        if edge.fact_embedding is None:
            await edge.generate_embedding(self.embedder)

        resolved_nodes, uuid_map, _ = await resolve_extracted_nodes(
            self.clients,
            [source_node, target_node],
            episode=None,
            previous_episodes=None,
            entity_types=None,
            existing_nodes_override=None,
            enable_cross_graph_deduplication=self.enable_cross_graph_deduplication,
        )

        updated_edge = resolve_edge_pointers([edge], uuid_map)[0]

        related_edges = (await get_relevant_edges(self.driver, [updated_edge], SearchFilters()))[0]
        existing_edges = (
            await get_edge_invalidation_candidates(self.driver, [updated_edge], SearchFilters())
        )[0]

        resolved_edge, invalidated_edges, _ = await resolve_extracted_edge(
            self.llm_client,
            updated_edge,
            related_edges,
            existing_edges,
            EpisodicNode(
                name='',
                source=EpisodeType.text,
                source_description='',
                content='',
                valid_at=edge.valid_at or utc_now(),
                entity_edges=[],
                group_id=edge.group_id,
            ),
        )

        await add_nodes_and_edges_bulk(
            self.driver, [], [], resolved_nodes, [resolved_edge] + invalidated_edges, self.embedder
        )

    async def remove_episode(self, episode_uuid: str):
        # Find the episode to be deleted
        episode = await EpisodicNode.get_by_uuid(self.driver, episode_uuid)

        # Find edges mentioned by the episode
        edges = await EntityEdge.get_by_uuids(self.driver, episode.entity_edges)

        # We should only delete edges created by the episode
        edges_to_delete: list[EntityEdge] = []
        for edge in edges:
            if edge.episodes and edge.episodes[0] == episode.uuid:
                edges_to_delete.append(edge)

        # Find nodes mentioned by the episode
        nodes = await get_mentioned_nodes(self.driver, [episode])
        # We should delete all nodes that are only mentioned in the deleted episode
        nodes_to_delete: list[EntityNode] = []
        for node in nodes:
            query: LiteralString = 'MATCH (e:Episodic)-[:MENTIONS]->(n:Entity {uuid: $uuid}) RETURN count(*) AS episode_count'
            records, _, _ = await self.driver.execute_query(query, uuid=node.uuid, routing_='r')

            for record in records:
                if record['episode_count'] == 1:
                    nodes_to_delete.append(node)

        await semaphore_gather(
            *[node.delete(self.driver) for node in nodes_to_delete],
            max_coroutines=self.max_coroutines,
        )
        await semaphore_gather(
            *[edge.delete(self.driver) for edge in edges_to_delete],
            max_coroutines=self.max_coroutines,
        )
        await episode.delete(self.driver)

        # Publish delete events for real-time sync (GRAPH-111)
        if self.event_publisher is not None and self.event_publisher.is_enabled:
            # Publish node deletions
            for node in nodes_to_delete:
                await self.event_publisher.publish_node_change('delete', node, include_data=False)
            # Publish edge deletions
            for edge in edges_to_delete:
                await self.event_publisher.publish_edge_change('delete', edge, include_data=False)
            # Publish episode deletion
            await self.event_publisher.publish_episode_change('delete', episode, include_data=False)
            logger.info(
                f'Published delete events: {len(nodes_to_delete)} nodes, '
                f'{len(edges_to_delete)} edges, 1 episode'
            )
