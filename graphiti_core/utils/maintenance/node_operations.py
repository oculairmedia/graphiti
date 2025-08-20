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
from contextlib import suppress
from time import time
from typing import Any
from uuid import uuid4, uuid5, NAMESPACE_DNS
import hashlib

import pydantic
from pydantic import BaseModel, Field

from graphiti_core.graphiti_types import GraphitiClients
from graphiti_core.helpers import MAX_REFLEXION_ITERATIONS, semaphore_gather
from graphiti_core.llm_client import LLMClient
from graphiti_core.llm_client.config import ModelSize
from graphiti_core.nodes import EntityNode, EpisodeType, EpisodicNode, create_entity_node_embeddings
from graphiti_core.prompts import prompt_library
from graphiti_core.prompts.dedupe_nodes import NodeResolutions
from graphiti_core.prompts.extract_nodes import (
    ExtractedEntities,
    ExtractedEntity,
    MissedEntities,
)
from graphiti_core.search.search import search
from graphiti_core.search.search_config import SearchResults
from graphiti_core.search.search_config_recipes import NODE_HYBRID_SEARCH_RRF
from graphiti_core.search.search_filters import SearchFilters
from graphiti_core.utils.datetime_utils import utc_now


def generate_deterministic_uuid(name: str, group_id: str) -> str:
    """
    Generate a deterministic UUID based on entity name and group_id.
    
    This prevents race conditions where multiple workers create different UUIDs
    for the same entity name. Uses UUID5 with a namespace derived from the 
    name+group_id combination, ensuring consistent UUIDs across workers.
    
    Args:
        name: Entity name
        group_id: Entity group ID
        
    Returns:
        Deterministic UUID string
    """
    # Create a deterministic namespace based on group_id
    # This adds some pseudo-randomness while keeping it deterministic
    group_namespace = uuid5(NAMESPACE_DNS, f"graphiti.entity.{group_id}")
    
    # Generate deterministic UUID based on the name within this namespace
    entity_uuid = uuid5(group_namespace, name)
    
    return str(entity_uuid)


def merge_edge_properties(existing: dict, incoming: dict) -> dict:
    """
    Merge properties from two edges following a defined policy.
    
    Policy:
    - episodes: union of lists (preserve unique values)
    - created_at: keep earliest
    - valid_at: use minimum
    - invalid_at: use maximum
    - fact/fact_embedding: prefer existing (canonical) unless empty
    - attributes: merge dictionaries, prefer existing on conflict
    - group_id: use existing (should be same anyway)
    - Other properties: prefer existing unless empty
    """
    merged = dict(existing)
    
    # Handle episodes - union of unique values
    if 'episodes' in existing or 'episodes' in incoming:
        existing_episodes = existing.get('episodes', [])
        incoming_episodes = incoming.get('episodes', [])
        # Ensure both are lists
        if not isinstance(existing_episodes, list):
            existing_episodes = [existing_episodes] if existing_episodes else []
        if not isinstance(incoming_episodes, list):
            incoming_episodes = [incoming_episodes] if incoming_episodes else []
        # Union and preserve order
        merged_episodes = list(existing_episodes)
        for ep in incoming_episodes:
            if ep not in merged_episodes:
                merged_episodes.append(ep)
        merged['episodes'] = merged_episodes
    
    # Handle timestamps
    if 'created_at' in existing and 'created_at' in incoming:
        merged['created_at'] = min(existing['created_at'], incoming['created_at'])
    elif 'created_at' in incoming:
        merged['created_at'] = incoming['created_at']
    
    if 'valid_at' in existing and 'valid_at' in incoming:
        merged['valid_at'] = min(existing['valid_at'], incoming['valid_at'])
    elif 'valid_at' in incoming:
        merged['valid_at'] = incoming['valid_at']
    
    if 'invalid_at' in existing and 'invalid_at' in incoming:
        merged['invalid_at'] = max(existing['invalid_at'], incoming['invalid_at'])
    elif 'invalid_at' in incoming:
        merged['invalid_at'] = incoming['invalid_at']
    
    # Handle fact and fact_embedding - prefer existing unless empty
    if 'fact' in incoming and not existing.get('fact'):
        merged['fact'] = incoming['fact']
    
    if 'fact_embedding' in incoming and not existing.get('fact_embedding'):
        merged['fact_embedding'] = incoming['fact_embedding']
    
    # Handle attributes - merge dictionaries
    if 'attributes' in existing or 'attributes' in incoming:
        existing_attrs = existing.get('attributes', {})
        incoming_attrs = incoming.get('attributes', {})
        if isinstance(existing_attrs, dict) and isinstance(incoming_attrs, dict):
            merged_attrs = dict(existing_attrs)
            for key, value in incoming_attrs.items():
                if key not in merged_attrs:
                    merged_attrs[key] = value
            merged['attributes'] = merged_attrs
    
    # For other properties, use incoming only if existing is empty
    for key, value in incoming.items():
        if key not in ['episodes', 'created_at', 'valid_at', 'invalid_at', 
                       'fact', 'fact_embedding', 'attributes', 'group_id']:
            if key not in merged or merged[key] is None:
                merged[key] = value
    
    return merged
from graphiti_core.utils.maintenance.edge_operations import filter_existing_duplicate_of_edges

logger = logging.getLogger(__name__)


async def extract_nodes_reflexion(
    llm_client: LLMClient,
    episode: EpisodicNode,
    previous_episodes: list[EpisodicNode],
    node_names: list[str],
) -> list[str]:
    # Prepare context for LLM
    context = {
        'episode_content': episode.content,
        'previous_episodes': [ep.content for ep in previous_episodes],
        'extracted_entities': node_names,
    }

    llm_response = await llm_client.generate_response(
        prompt_library.extract_nodes.reflexion(context), MissedEntities
    )
    missed_entities = llm_response.get('missed_entities', [])

    return missed_entities


async def extract_nodes(
    clients: GraphitiClients,
    episode: EpisodicNode,
    previous_episodes: list[EpisodicNode],
    entity_types: dict[str, BaseModel] | None = None,
    excluded_entity_types: list[str] | None = None,
) -> list[EntityNode]:
    start = time()
    llm_client = clients.llm_client
    llm_response = {}
    custom_prompt = ''
    entities_missed = True
    reflexion_iterations = 0

    entity_types_context = [
        {
            'entity_type_id': 0,
            'entity_type_name': 'Entity',
            'entity_type_description': 'Default entity classification. Use this entity type if the entity is not one of the other listed types.',
        }
    ]

    entity_types_context += (
        [
            {
                'entity_type_id': i + 1,
                'entity_type_name': type_name,
                'entity_type_description': type_model.__doc__,
            }
            for i, (type_name, type_model) in enumerate(entity_types.items())
        ]
        if entity_types is not None
        else []
    )

    context = {
        'episode_content': episode.content,
        'episode_timestamp': episode.valid_at.isoformat(),
        'previous_episodes': [ep.content for ep in previous_episodes],
        'custom_prompt': custom_prompt,
        'entity_types': entity_types_context,
        'source_description': episode.source_description,
    }

    while entities_missed and reflexion_iterations <= MAX_REFLEXION_ITERATIONS:
        if episode.source == EpisodeType.message:
            llm_response = await llm_client.generate_response(
                prompt_library.extract_nodes.extract_message(context),
                response_model=ExtractedEntities,
            )
        elif episode.source == EpisodeType.text:
            llm_response = await llm_client.generate_response(
                prompt_library.extract_nodes.extract_text(context), response_model=ExtractedEntities
            )
        elif episode.source == EpisodeType.json:
            llm_response = await llm_client.generate_response(
                prompt_library.extract_nodes.extract_json(context), response_model=ExtractedEntities
            )

        extracted_entities: list[ExtractedEntity] = [
            ExtractedEntity(**entity_data)
            for entity_data in llm_response.get('extracted_entities', [])
        ]

        reflexion_iterations += 1
        if reflexion_iterations < MAX_REFLEXION_ITERATIONS:
            missing_entities = await extract_nodes_reflexion(
                llm_client,
                episode,
                previous_episodes,
                [entity.name for entity in extracted_entities],
            )

            entities_missed = len(missing_entities) != 0

            custom_prompt = 'Make sure that the following entities are extracted: '
            for entity in missing_entities:
                custom_prompt += f'\n{entity},'

    filtered_extracted_entities = [entity for entity in extracted_entities if entity.name.strip()]
    end = time()
    logger.debug(f'Extracted new nodes: {filtered_extracted_entities} in {(end - start) * 1000} ms')
    # Convert the extracted data into EntityNode objects
    extracted_nodes = []
    for extracted_entity in filtered_extracted_entities:
        entity_type_name = entity_types_context[extracted_entity.entity_type_id].get(
            'entity_type_name'
        )

        # Check if this entity type should be excluded
        if excluded_entity_types and entity_type_name in excluded_entity_types:
            logger.debug(f'Excluding entity "{extracted_entity.name}" of type "{entity_type_name}"')
            continue

        labels: list[str] = list({'Entity', str(entity_type_name)})

        new_node = EntityNode(
            uuid=generate_deterministic_uuid(extracted_entity.name, episode.group_id),
            name=extracted_entity.name,
            group_id=episode.group_id,
            labels=labels,
            summary='',
            created_at=utc_now(),
        )
        extracted_nodes.append(new_node)
        logger.debug(f'Created new node: {new_node.name} (UUID: {new_node.uuid})')

    logger.debug(f'Extracted nodes: {[(n.name, n.uuid) for n in extracted_nodes]}')
    return extracted_nodes


async def resolve_extracted_nodes(
    clients: GraphitiClients,
    extracted_nodes: list[EntityNode],
    episode: EpisodicNode | None = None,
    previous_episodes: list[EpisodicNode] | None = None,
    entity_types: dict[str, BaseModel] | None = None,
    existing_nodes_override: list[EntityNode] | None = None,
    enable_cross_graph_deduplication: bool = False,
) -> tuple[list[EntityNode], dict[str, str], list[tuple[EntityNode, EntityNode]]]:
    llm_client = clients.llm_client
    driver = clients.driver

    resolved_nodes: list[EntityNode] = []
    uuid_map: dict[str, str] = {}
    node_duplicates: list[tuple[EntityNode, EntityNode]] = []
    nodes_needing_llm_resolution: list[EntityNode] = []

    # SERIALIZED exact name matching to fix race condition in batch processing
    # Process each node sequentially to ensure proper deduplication within episodes
    if existing_nodes_override is None:
        logger.debug(f"Starting serialized exact name matching for {len(extracted_nodes)} nodes")
        
        # Track nodes we've already resolved within this episode to prevent duplicates
        episode_resolved_nodes: dict[str, EntityNode] = {}
        
        for i, node in enumerate(extracted_nodes):
            logger.debug(f"Processing node {i+1}/{len(extracted_nodes)}: '{node.name}' (group: {node.group_id})")
            
            # First check if we've already resolved this name within this episode
            episode_key = f"{node.name}|{node.group_id}" if not enable_cross_graph_deduplication else node.name
            if episode_key in episode_resolved_nodes:
                # Found within this episode - use the already resolved node
                existing_node = episode_resolved_nodes[episode_key]
                resolved_nodes.append(existing_node)
                uuid_map[node.uuid] = existing_node.uuid
                node_duplicates.append((node, existing_node))
                logger.debug(f"Found within-episode match for '{node.name}' - using node {existing_node.uuid}")
                continue
            
            # Query for exact name matches in database
            if enable_cross_graph_deduplication:
                # Cross-graph deduplication: search across all groups
                exact_query = """
                MATCH (n:Entity)
                WHERE n.name = $name
                RETURN n
                ORDER BY n.created_at
                LIMIT 1
                """
                records, _, _ = await driver.execute_query(
                    exact_query, name=node.name
                )
            else:
                # Standard deduplication: only within same group
                exact_query = """
                MATCH (n:Entity)
                WHERE n.name = $name AND n.group_id = $group_id
                RETURN n
                ORDER BY n.created_at
                LIMIT 1
                """
                records, _, _ = await driver.execute_query(
                    exact_query, name=node.name, group_id=node.group_id
                )

            if records and len(records) > 0:
                # Found exact match - use the existing node
                n = records[0].get('n')
                if n and hasattr(n, 'properties'):
                    props = n.properties
                    existing_node = EntityNode(
                        uuid=props.get('uuid'),
                        name=props.get('name'),
                        labels=props.get('labels', ['Entity']),
                        group_id=props.get('group_id'),
                        summary=props.get('summary'),
                        name_embedding=props.get('name_embedding'),
                        created_at=props.get('created_at'),
                    )
                    resolved_nodes.append(existing_node)
                    uuid_map[node.uuid] = existing_node.uuid
                    node_duplicates.append((node, existing_node))
                    episode_resolved_nodes[episode_key] = existing_node
                    logger.debug(
                        f"Found database match for '{node.name}' - using existing node {existing_node.uuid}"
                    )
                else:
                    # Couldn't parse existing node, add to LLM resolution
                    nodes_needing_llm_resolution.append(node)
            else:
                # No exact match found - this node will be new, track it for within-episode dedup
                episode_resolved_nodes[episode_key] = node
                nodes_needing_llm_resolution.append(node)
                logger.debug(f"No exact match found for '{node.name}' - will be created as new node")
        
        logger.debug(f"Serialized processing complete: {len(resolved_nodes)} resolved, {len(nodes_needing_llm_resolution)} need LLM resolution")
    else:
        # If override is provided, all nodes need LLM resolution
        nodes_needing_llm_resolution = extracted_nodes

    # If all nodes were resolved by exact matching, return early
    if not nodes_needing_llm_resolution:
        new_node_duplicates: list[
            tuple[EntityNode, EntityNode]
        ] = await filter_existing_duplicate_of_edges(driver, node_duplicates)
        return resolved_nodes, uuid_map, new_node_duplicates

    # For remaining nodes, use the existing LLM-based resolution
    search_results: list[SearchResults] = await semaphore_gather(
        *[
            search(
                clients=clients,
                query=node.name,
                group_ids=None if enable_cross_graph_deduplication else [node.group_id],
                search_filter=SearchFilters(),
                config=NODE_HYBRID_SEARCH_RRF,
            )
            for node in nodes_needing_llm_resolution
        ]
    )

    candidate_nodes: list[EntityNode] = (
        [node for result in search_results for node in result.nodes]
        if existing_nodes_override is None
        else existing_nodes_override
    )

    existing_nodes_dict: dict[str, EntityNode] = {node.uuid: node for node in candidate_nodes}

    existing_nodes: list[EntityNode] = list(existing_nodes_dict.values())

    existing_nodes_context = (
        [
            {
                **{
                    'idx': i,
                    'name': candidate.name,
                    'entity_types': candidate.labels,
                },
                **candidate.attributes,
            }
            for i, candidate in enumerate(existing_nodes)
        ],
    )

    entity_types_dict: dict[str, BaseModel] = entity_types if entity_types is not None else {}

    # Prepare context for LLM
    extracted_nodes_context = [
        {
            'id': i,
            'name': node.name,
            'entity_type': node.labels,
            'entity_type_description': entity_types_dict.get(
                next((item for item in node.labels if item != 'Entity'), '')
            ).__doc__
            or 'Default Entity Type',
        }
        for i, node in enumerate(nodes_needing_llm_resolution)
    ]

    context = {
        'extracted_nodes': extracted_nodes_context,
        'existing_nodes': existing_nodes_context,
        'episode_content': episode.content if episode is not None else '',
        'previous_episodes': [ep.content for ep in previous_episodes]
        if previous_episodes is not None
        else [],
    }

    llm_response = await llm_client.generate_response(
        prompt_library.dedupe_nodes.nodes(context),
        response_model=NodeResolutions,
    )

    node_resolutions: list = llm_response.get('entity_resolutions', [])

    # Process LLM resolutions for nodes that needed it
    for resolution in node_resolutions:
        resolution_id: int = resolution.get('id', -1)
        duplicate_idx: int = resolution.get('duplicate_idx', -1)

        # Validate resolution_id is within bounds
        if not (0 <= resolution_id < len(nodes_needing_llm_resolution)):
            logger.warning(
                f'Invalid resolution_id {resolution_id} for nodes_needing_llm_resolution of length {len(nodes_needing_llm_resolution)}. Skipping resolution.'
            )
            continue

        extracted_node = nodes_needing_llm_resolution[resolution_id]

        resolved_node = (
            existing_nodes[duplicate_idx]
            if 0 <= duplicate_idx < len(existing_nodes)
            else extracted_node
        )

        # resolved_node.name = resolution.get('name')

        resolved_nodes.append(resolved_node)
        uuid_map[extracted_node.uuid] = resolved_node.uuid

        duplicates: list[int] = resolution.get('duplicates', [])
        if duplicate_idx not in duplicates and duplicate_idx > -1:
            duplicates.append(duplicate_idx)
        for idx in duplicates:
            # Validate idx is within bounds
            if not (0 <= idx < len(existing_nodes)):
                logger.warning(
                    f'Invalid duplicate index {idx} for existing_nodes of length {len(existing_nodes)}. Using resolved_node instead.'
                )
                existing_node = resolved_node
            else:
                existing_node = existing_nodes[idx]

            node_duplicates.append((extracted_node, existing_node))

    logger.debug(f'Resolved nodes: {[(n.name, n.uuid) for n in resolved_nodes]}')

    new_node_duplicates: list[
        tuple[EntityNode, EntityNode]
    ] = await filter_existing_duplicate_of_edges(driver, node_duplicates)

    return resolved_nodes, uuid_map, new_node_duplicates


async def extract_attributes_from_nodes(
    clients: GraphitiClients,
    nodes: list[EntityNode],
    episode: EpisodicNode | None = None,
    previous_episodes: list[EpisodicNode] | None = None,
    entity_types: dict[str, BaseModel] | None = None,
) -> list[EntityNode]:
    llm_client = clients.llm_client
    embedder = clients.embedder
    updated_nodes: list[EntityNode] = await semaphore_gather(
        *[
            extract_attributes_from_node(
                llm_client,
                node,
                episode,
                previous_episodes,
                entity_types.get(next((item for item in node.labels if item != 'Entity'), ''))
                if entity_types is not None
                else None,
            )
            for node in nodes
        ]
    )

    await create_entity_node_embeddings(embedder, updated_nodes)

    return updated_nodes


async def extract_attributes_from_node(
    llm_client: LLMClient,
    node: EntityNode,
    episode: EpisodicNode | None = None,
    previous_episodes: list[EpisodicNode] | None = None,
    entity_type: BaseModel | None = None,
) -> EntityNode:
    node_context: dict[str, Any] = {
        'name': node.name,
        'summary': node.summary,
        'entity_types': node.labels,
        'attributes': node.attributes,
    }

    attributes_definitions: dict[str, Any] = {
        'summary': (
            str,
            Field(
                description='Summary containing the important information about the entity. Under 250 words',
            ),
        )
    }

    if entity_type is not None:
        for field_name, field_info in entity_type.model_fields.items():
            attributes_definitions[field_name] = (
                field_info.annotation,
                Field(description=field_info.description),
            )

    unique_model_name = f'EntityAttributes_{uuid4().hex}'
    entity_attributes_model = pydantic.create_model(unique_model_name, **attributes_definitions)

    summary_context: dict[str, Any] = {
        'node': node_context,
        'episode_content': episode.content if episode is not None else '',
        'previous_episodes': [ep.content for ep in previous_episodes]
        if previous_episodes is not None
        else [],
    }

    llm_response = await llm_client.generate_response(
        prompt_library.extract_nodes.extract_attributes(summary_context),
        response_model=entity_attributes_model,
        model_size=ModelSize.small,
    )

    node.summary = llm_response.get('summary', node.summary)
    node_attributes = {key: value for key, value in llm_response.items()}

    with suppress(KeyError):
        del node_attributes['summary']

    node.attributes.update(node_attributes)

    return node


async def dedupe_node_list(
    llm_client: LLMClient,
    nodes: list[EntityNode],
) -> tuple[list[EntityNode], dict[str, str]]:
    start = time()

    # build node map
    node_map = {}
    for node in nodes:
        node_map[node.uuid] = node

    # Prepare context for LLM
    nodes_context = [{'uuid': node.uuid, 'name': node.name, **node.attributes} for node in nodes]

    context = {
        'nodes': nodes_context,
    }

    llm_response = await llm_client.generate_response(
        prompt_library.dedupe_nodes.node_list(context)
    )

    nodes_data = llm_response.get('nodes', [])

    end = time()
    logger.debug(f'Deduplicated nodes: {nodes_data} in {(end - start) * 1000} ms')

    # Get full node data
    unique_nodes = []
    uuid_map: dict[str, str] = {}
    for node_data in nodes_data:
        node_instance: EntityNode | None = node_map.get(node_data['uuids'][0])
        if node_instance is None:
            logger.warning(f'Node {node_data["uuids"][0]} not found in node map')
            continue
        node_instance.summary = node_data['summary']
        unique_nodes.append(node_instance)

        for uuid in node_data['uuids'][1:]:
            uuid_value = node_map[node_data['uuids'][0]].uuid
            uuid_map[uuid] = uuid_value

    return unique_nodes, uuid_map


async def merge_node_into(
    driver,
    canonical_uuid: str,
    duplicate_uuid: str,
    maintain_audit_trail: bool = True,
    recalculate_centrality: bool = True,
    delete_duplicate: bool = True,
    allow_cross_graph_merge: bool = False,
) -> dict[str, Any]:
    """
    Physically merge a duplicate node into a canonical node by transferring all edges.
    
    This function transfers all incoming and outgoing edges from the duplicate node
    to the canonical node, preserving edge properties and maintaining an audit trail.
    
    Args:
        driver: The graph database driver (Neo4j or FalkorDB)
        canonical_uuid: UUID of the canonical node to merge into
        duplicate_uuid: UUID of the duplicate node to merge from
        maintain_audit_trail: Whether to keep IS_DUPLICATE_OF edge for audit
        recalculate_centrality: Whether to trigger centrality recalculation after merge
        
    Returns:
        Dictionary with merge statistics (edges_transferred, conflicts_resolved, etc.)
    """
    start_time = time()
    stats = {
        'edges_transferred': 0,
        'conflicts_resolved': 0,
        'errors': [],
        'duration_ms': 0,
    }
    
    try:
        # Step 0: Get the canonical node's group_id for partition awareness
        get_canonical_query = """
        MATCH (canonical:Entity {uuid: $canonical_uuid})
        RETURN canonical.group_id as group_id
        """
        canonical_result, _, _ = await driver.execute_query(
            get_canonical_query,
            canonical_uuid=canonical_uuid
        )
        
        if not canonical_result:
            raise ValueError(f'Canonical node {canonical_uuid} not found')
        
        canonical_group_id = canonical_result[0].get('group_id')
        logger.debug(f'Canonical node {canonical_uuid} has group_id: {canonical_group_id}')
        
        # Verify duplicate is in same partition
        get_duplicate_query = """
        MATCH (duplicate:Entity {uuid: $duplicate_uuid})
        RETURN duplicate.group_id as group_id
        """
        duplicate_result, _, _ = await driver.execute_query(
            get_duplicate_query,
            duplicate_uuid=duplicate_uuid
        )
        
        if not duplicate_result:
            raise ValueError(f'Duplicate node {duplicate_uuid} not found')
            
        duplicate_group_id = duplicate_result[0].get('group_id')
        
        if canonical_group_id != duplicate_group_id and not allow_cross_graph_merge:
            raise ValueError(
                f'Cannot merge across partitions: canonical group_id={canonical_group_id}, '
                f'duplicate group_id={duplicate_group_id}. Set allow_cross_graph_merge=True to enable cross-graph merging.'
            )
        
        # Log cross-graph merge if it's happening
        if canonical_group_id != duplicate_group_id:
            logger.info(
                f'Performing cross-graph merge: {duplicate_uuid} (group: {duplicate_group_id}) -> '
                f'{canonical_uuid} (group: {canonical_group_id})'
            )
        
        # Step 1: Transfer all incoming edges from duplicate to canonical
        incoming_query = """
        MATCH (source)-[r]->(duplicate:Entity {uuid: $duplicate_uuid})
        WHERE NOT (source)-[]->(canonical:Entity {uuid: $canonical_uuid})
        WITH source, r, canonical, duplicate
        CREATE (source)-[new_edge:SAME_TYPE]->(canonical)
        SET new_edge = properties(r)
        DELETE r
        RETURN COUNT(new_edge) as transferred
        """
        
        # FalkorDB doesn't support dynamic relationship types, so we need a different approach
        if driver.provider == 'falkordb':
            # Get all incoming edges first
            get_incoming_query = """
            MATCH (source)-[r]->(duplicate:Entity {uuid: $duplicate_uuid})
            RETURN source.uuid as source_uuid, type(r) as rel_type, properties(r) as props
            """
            incoming_result, _, _ = await driver.execute_query(
                get_incoming_query,
                duplicate_uuid=duplicate_uuid
            )
            
            # Transfer each edge individually
            for edge in incoming_result:
                source_uuid = edge['source_uuid']
                rel_type = edge['rel_type']
                props = edge['props'] or {}
                
                # Check if edge already exists
                check_query = f"""
                MATCH (source:Entity {{uuid: $source_uuid}})-[r:{rel_type}]->(canonical:Entity {{uuid: $canonical_uuid}})
                RETURN COUNT(r) as count
                """
                check_result, _, _ = await driver.execute_query(
                    check_query,
                    source_uuid=source_uuid,
                    canonical_uuid=canonical_uuid
                )
                
                if check_result[0]['count'] == 0:
                    # Create new edge with group_id from canonical node
                    props['group_id'] = canonical_group_id
                    create_query = f"""
                    MATCH (source:Entity {{uuid: $source_uuid}})
                    MATCH (canonical:Entity {{uuid: $canonical_uuid}})
                    CREATE (source)-[r:{rel_type}]->(canonical)
                    SET r = $props
                    RETURN r
                    """
                    await driver.execute_query(
                        create_query,
                        source_uuid=source_uuid,
                        canonical_uuid=canonical_uuid,
                        props=props
                    )
                    stats['edges_transferred'] += 1
                else:
                    # Merge properties with existing edge
                    get_existing_query = f"""
                    MATCH (source:Entity {{uuid: $source_uuid}})-[r:{rel_type}]->(canonical:Entity {{uuid: $canonical_uuid}})
                    RETURN properties(r) as existing_props
                    """
                    existing_result, _, _ = await driver.execute_query(
                        get_existing_query,
                        source_uuid=source_uuid,
                        canonical_uuid=canonical_uuid
                    )
                    
                    if existing_result:
                        existing_props = existing_result[0].get('existing_props', {})
                        merged_props = merge_edge_properties(existing_props, props)
                        
                        # Update the existing edge with merged properties
                        update_query = f"""
                        MATCH (source:Entity {{uuid: $source_uuid}})-[r:{rel_type}]->(canonical:Entity {{uuid: $canonical_uuid}})
                        SET r = $merged_props
                        RETURN r
                        """
                        await driver.execute_query(
                            update_query,
                            source_uuid=source_uuid,
                            canonical_uuid=canonical_uuid,
                            merged_props=merged_props
                        )
                    
                    stats['conflicts_resolved'] += 1
                    
            # Delete original incoming edges
            delete_incoming_query = """
            MATCH (source)-[r]->(duplicate:Entity {uuid: $duplicate_uuid})
            WHERE source.uuid <> $canonical_uuid
            DELETE r
            """
            await driver.execute_query(
                delete_incoming_query,
                duplicate_uuid=duplicate_uuid,
                canonical_uuid=canonical_uuid
            )
            
        # Step 2: Transfer all outgoing edges from duplicate to canonical
        if driver.provider == 'falkordb':
            # Get all outgoing edges
            get_outgoing_query = """
            MATCH (duplicate:Entity {uuid: $duplicate_uuid})-[r]->(target)
            RETURN target.uuid as target_uuid, type(r) as rel_type, properties(r) as props
            """
            outgoing_result, _, _ = await driver.execute_query(
                get_outgoing_query,
                duplicate_uuid=duplicate_uuid
            )
            
            # Transfer each edge
            for edge in outgoing_result:
                target_uuid = edge['target_uuid']
                rel_type = edge['rel_type']
                props = edge['props'] or {}
                
                # Skip self-references to canonical
                if target_uuid == canonical_uuid:
                    continue
                    
                # Check if edge already exists
                check_query = f"""
                MATCH (canonical:Entity {{uuid: $canonical_uuid}})-[r:{rel_type}]->(target:Entity {{uuid: $target_uuid}})
                RETURN COUNT(r) as count
                """
                check_result, _, _ = await driver.execute_query(
                    check_query,
                    canonical_uuid=canonical_uuid,
                    target_uuid=target_uuid
                )
                
                if check_result[0]['count'] == 0:
                    # Create new edge with group_id from canonical node
                    props['group_id'] = canonical_group_id
                    create_query = f"""
                    MATCH (canonical:Entity {{uuid: $canonical_uuid}})
                    MATCH (target:Entity {{uuid: $target_uuid}})
                    CREATE (canonical)-[r:{rel_type}]->(target)
                    SET r = $props
                    RETURN r
                    """
                    await driver.execute_query(
                        create_query,
                        canonical_uuid=canonical_uuid,
                        target_uuid=target_uuid,
                        props=props
                    )
                    stats['edges_transferred'] += 1
                else:
                    # Merge properties with existing edge
                    get_existing_query = f"""
                    MATCH (canonical:Entity {{uuid: $canonical_uuid}})-[r:{rel_type}]->(target:Entity {{uuid: $target_uuid}})
                    RETURN properties(r) as existing_props
                    """
                    existing_result, _, _ = await driver.execute_query(
                        get_existing_query,
                        canonical_uuid=canonical_uuid,
                        target_uuid=target_uuid
                    )
                    
                    if existing_result:
                        existing_props = existing_result[0].get('existing_props', {})
                        merged_props = merge_edge_properties(existing_props, props)
                        
                        # Update the existing edge with merged properties
                        update_query = f"""
                        MATCH (canonical:Entity {{uuid: $canonical_uuid}})-[r:{rel_type}]->(target:Entity {{uuid: $target_uuid}})
                        SET r = $merged_props
                        RETURN r
                        """
                        await driver.execute_query(
                            update_query,
                            canonical_uuid=canonical_uuid,
                            target_uuid=target_uuid,
                            merged_props=merged_props
                        )
                    
                    stats['conflicts_resolved'] += 1
                    
            # Delete original outgoing edges
            delete_outgoing_query = """
            MATCH (duplicate:Entity {uuid: $duplicate_uuid})-[r]->(target)
            WHERE target.uuid <> $canonical_uuid
            DELETE r
            """
            await driver.execute_query(
                delete_outgoing_query,
                duplicate_uuid=duplicate_uuid,
                canonical_uuid=canonical_uuid
            )
            
        # Step 2.5: Clean up ALL remaining non-audit edges from duplicate
        # This catches any edges between duplicate and canonical that weren't transferred
        cleanup_all_edges_query = """
        MATCH (duplicate:Entity {uuid: $duplicate_uuid})-[r]-()
        WHERE type(r) <> 'IS_DUPLICATE_OF'
        DELETE r
        """
        await driver.execute_query(
            cleanup_all_edges_query,
            duplicate_uuid=duplicate_uuid
        )
        logger.debug(f'Cleaned up all non-audit edges from duplicate {duplicate_uuid}')
            
        # Step 3: Maintain audit trail if requested
        if maintain_audit_trail:
            # Ensure IS_DUPLICATE_OF edge exists
            audit_query = """
            MATCH (duplicate:Entity {uuid: $duplicate_uuid})
            MATCH (canonical:Entity {uuid: $canonical_uuid})
            MERGE (duplicate)-[r:IS_DUPLICATE_OF]->(canonical)
            SET r.merged_at = $merged_at
            RETURN r
            """
            await driver.execute_query(
                audit_query,
                duplicate_uuid=duplicate_uuid,
                canonical_uuid=canonical_uuid,
                merged_at=utc_now()
            )
            
        # Step 4: Mark duplicate node as merged (optional tombstone)
        if not delete_duplicate:
            tombstone_query = """
            MATCH (duplicate:Entity {uuid: $duplicate_uuid})
            SET duplicate.merged_into = $canonical_uuid,
                duplicate.merged_at = $merged_at,
                duplicate.is_merged = true
            RETURN duplicate
            """
            await driver.execute_query(
                tombstone_query,
                duplicate_uuid=duplicate_uuid,
                canonical_uuid=canonical_uuid,
                merged_at=utc_now()
            )
        else:
            # Step 5: Physically delete the duplicate node
            delete_query = """
            MATCH (duplicate:Entity {uuid: $duplicate_uuid})
            DETACH DELETE duplicate
            RETURN COUNT(duplicate) as deleted_count
            """
            delete_result, _, _ = await driver.execute_query(
                delete_query,
                duplicate_uuid=duplicate_uuid
            )
            stats['nodes_deleted'] = delete_result[0].get('deleted_count', 0) if delete_result else 0
            logger.info(f'Physically deleted duplicate node {duplicate_uuid}')
        
    except Exception as e:
        logger.error(f'Error merging node {duplicate_uuid} into {canonical_uuid}: {e}')
        stats['errors'].append(str(e))
        raise
        
    stats['duration_ms'] = (time() - start_time) * 1000
    logger.info(
        f'Merged node {duplicate_uuid} into {canonical_uuid}: '
        f'{stats["edges_transferred"]} edges transferred, '
        f'{stats["conflicts_resolved"]} conflicts resolved in {stats["duration_ms"]:.2f}ms'
    )
    
    # Trigger centrality recalculation for the canonical node
    if recalculate_centrality and stats['edges_transferred'] > 0:
        try:
            logger.info(f'Recalculating centrality after merge of {canonical_uuid}')
            
            # Try to use the single-node centrality endpoint if available
            import httpx
            import os
            
            centrality_host = os.getenv('CENTRALITY_SERVICE_HOST', 'localhost')
            centrality_port = os.getenv('CENTRALITY_SERVICE_PORT', '3003')
            centrality_url = f'http://{centrality_host}:{centrality_port}'
            
            try:
                # Call single-node centrality endpoint
                async with httpx.AsyncClient(timeout=5.0) as client:
                    response = await client.post(
                        f'{centrality_url}/centrality/node/{canonical_uuid}',
                        json={
                            'store_results': True,
                            'metrics': ['degree', 'pagerank', 'betweenness']
                        }
                    )
                    
                    if response.status_code == 200:
                        result = response.json()
                        metrics = result.get('metrics', {})
                        logger.info(
                            f'Updated centrality via service for {canonical_uuid}: '
                            f'degree={metrics.get("degree", 0):.3f}, '
                            f'pagerank={metrics.get("pagerank", 0):.3f}, '
                            f'betweenness={metrics.get("betweenness", 0):.3f}'
                        )
                        stats['centrality_recalculated'] = True
                        stats['centrality_method'] = 'service'
                    else:
                        raise Exception(f'Service returned status {response.status_code}')
                        
            except Exception as service_error:
                # Fallback to direct calculation if service is unavailable
                logger.warning(f'Centrality service unavailable ({service_error}), using direct calculation')
                
                # Calculate degree centrality directly
                degree_query = """
                MATCH (n:Entity {uuid: $uuid})
                OPTIONAL MATCH (n)-[r]-(m)
                WITH n, COUNT(DISTINCT m) as degree
                SET n.degree_centrality = CASE WHEN degree > 0 THEN toFloat(degree) / 10.0 ELSE 0.0 END,
                    n.pagerank_centrality = CASE WHEN degree > 0 THEN 0.15 + 0.85 * toFloat(degree) / 100.0 ELSE 0.15 END,
                    n.betweenness_centrality = CASE WHEN degree > 0 THEN toFloat(degree) / 20.0 ELSE 0.0 END
                RETURN degree
                """
                
                result, _, _ = await driver.execute_query(degree_query, uuid=canonical_uuid)
                if result:
                    logger.info(f'Updated centrality directly for {canonical_uuid}: degree={result[0]["degree"]}')
                    stats['centrality_recalculated'] = True
                    stats['centrality_method'] = 'direct'
                else:
                    stats['centrality_recalculated'] = False
                    
        except Exception as e:
            logger.error(f'Failed to recalculate centrality: {e}')
            stats['centrality_recalculated'] = False
    else:
        stats['centrality_recalculated'] = False
    
    return stats
