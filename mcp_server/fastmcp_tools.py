#!/usr/bin/env python3
"""
FastMCP Tools for Graphiti MCP Server
Enhanced tools using FastMCP decorator patterns with proper Pydantic validation
"""

import httpx
import logging
from typing import Any
from mcp import McpError, ErrorCode
from pydantic import BaseModel, Field
from datetime import datetime, timezone

# Initialize logger
logger = logging.getLogger(__name__)

# Global references (will be set by main server)
http_client: httpx.AsyncClient | None = None
config = None
mcp = None

def initialize_tools(client: httpx.AsyncClient, server_config, mcp_server):
    """Initialize tools with client and config."""
    global http_client, config, mcp
    http_client = client
    config = server_config
    mcp = mcp_server

# Response models using Pydantic
class NodeResult(BaseModel):
    """Node search result."""
    uuid: str
    name: str
    summary: str
    labels: list[str]
    group_id: str
    created_at: str
    attributes: dict[str, Any] = Field(default_factory=dict)

class NodeSearchResponse(BaseModel):
    """Response for node search."""
    message: str
    nodes: list[NodeResult]

class FactSearchResponse(BaseModel):
    """Response for fact search."""
    message: str
    facts: list[dict[str, Any]]

class StatusResponse(BaseModel):
    """Response for status check."""
    status: str
    message: str

class SuccessResponse(BaseModel):
    """Generic success response."""
    message: str

@mcp.tool()
async def add_memory(
    name: str = Field(..., description="Name of the episode"),
    episode_body: str = Field(..., description="The content of the episode to persist to memory"),
    group_id: str | None = Field(None, description="A unique ID for this graph. If not provided, uses the default group_id from CLI"),
    source: str = Field('text', description="Source type (text, json, message)"),
    source_description: str = Field('', description="Description of the source"),
    uuid: str | None = Field(None, description="Optional UUID for the episode"),
) -> SuccessResponse:
    """Add an episode to memory via FastAPI server.

    Args:
        name (str): Name of the episode
        episode_body (str): The content of the episode to persist to memory
        group_id (str, optional): A unique ID for this graph. If not provided, uses the default group_id from CLI
        source (str, optional): Source type (text, json, message)
        source_description (str, optional): Description of the source
        uuid (str, optional): Optional UUID for the episode
    """
    if http_client is None:
        raise McpError(ErrorCode.INTERNAL_ERROR, 'HTTP client not initialized')

    try:
        # Use the provided group_id or fall back to the default from config
        effective_group_id = group_id if group_id is not None else config.group_id
        group_id_str = str(effective_group_id) if effective_group_id is not None else 'default'

        # Prepare request payload according to AddMessagesRequest schema
        message = {
            'content': episode_body,
            'role_type': 'system',
            'role': name,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'source_description': source_description,
            'name': name
        }
        
        if uuid:
            message['uuid'] = uuid
            
        payload = {
            'group_id': group_id_str,
            'messages': [message]
        }

        # Send request to FastAPI server
        response = await http_client.post('/messages', json=payload)
        response.raise_for_status()

        result = response.json()
        logger.info(f"Episode '{name}' added successfully via FastAPI")

        return SuccessResponse(message=f"Episode '{name}' added successfully")

    except httpx.HTTPStatusError as e:
        error_msg = f'HTTP error {e.response.status_code}: {e.response.text}'
        logger.error(f'Error adding episode via FastAPI: {error_msg}')
        raise McpError(ErrorCode.INTERNAL_ERROR, f'Error adding episode: {error_msg}')
    except Exception as e:
        error_msg = str(e)
        logger.error(f'Error adding episode: {error_msg}')
        raise McpError(ErrorCode.INTERNAL_ERROR, f'Error adding episode: {error_msg}')


@mcp.tool()
async def search_memory_nodes(
    query: str = Field(..., description="The search query"),
    group_ids: list[str] | None = Field(None, description="Optional list of group IDs to filter results"),
    max_nodes: int = Field(10, description="Maximum number of nodes to return (default: 10)"),
    center_node_uuid: str | None = Field(None, description="Optional UUID of a node to center the search around"),
    entity: str = Field('', description="Optional single entity type to filter results"),
) -> NodeSearchResponse:
    """Search the graph memory for relevant nodes via FastAPI server.

    Args:
        query: The search query
        group_ids: Optional list of group IDs to filter results
        max_nodes: Maximum number of nodes to return (default: 10)
        center_node_uuid: Optional UUID of a node to center the search around
        entity: Optional single entity type to filter results
    """
    if http_client is None:
        raise McpError(ErrorCode.INTERNAL_ERROR, 'HTTP client not initialized')

    try:
        # Use the provided group_ids or fall back to the default from config if none provided
        effective_group_ids = (
            group_ids if group_ids is not None else [config.group_id] if config.group_id else []
        )

        # Prepare request payload
        payload = {
            'query': query,
            'group_ids': effective_group_ids,
            'num_results': max_nodes,
        }

        if center_node_uuid:
            payload['center_node_uuid'] = center_node_uuid
        if entity:
            payload['entity_types'] = [entity]

        # Send request to FastAPI server
        response = await http_client.post('/search/nodes', json=payload)
        response.raise_for_status()

        result = response.json()
        nodes = result.get('nodes', [])

        # Create structured node results using Pydantic models
        structured_nodes = []
        for node in nodes:
            node_result = NodeResult(
                uuid=node.get('uuid', ''),
                name=node.get('name', ''),
                summary=(node.get('summary', '') or '')[:50] + ('...' if len(node.get('summary', '') or '') > 50 else ''),
                labels=node.get('labels', []),
                group_id=node.get('group_id', ''),
                created_at=node.get('created_at', ''),
                attributes={}  # Remove attributes entirely to reduce size
            )
            structured_nodes.append(node_result)

        return NodeSearchResponse(message='Nodes retrieved successfully', nodes=structured_nodes)

    except httpx.HTTPStatusError as e:
        error_msg = f'HTTP error {e.response.status_code}: {e.response.text}'
        logger.error(f'Error searching nodes via FastAPI: {error_msg}')
        raise McpError(ErrorCode.INTERNAL_ERROR, f'Error searching nodes: {error_msg}')
    except Exception as e:
        error_msg = str(e)
        logger.error(f'Error searching nodes: {error_msg}')
        raise McpError(ErrorCode.INTERNAL_ERROR, f'Error searching nodes: {error_msg}')


@mcp.tool()
async def search_memory_facts(
    query: str = Field(..., description="The search query"),
    group_ids: list[str] | None = Field(None, description="Optional list of group IDs to filter results"),
    max_facts: int = Field(10, description="Maximum number of facts to return (default: 10)"),
    center_node_uuid: str | None = Field(None, description="Optional UUID of a node to center the search around"),
) -> FactSearchResponse:
    """Search the graph memory for relevant facts via FastAPI server.

    Args:
        query: The search query
        group_ids: Optional list of group IDs to filter results
        max_facts: Maximum number of facts to return (default: 10)
        center_node_uuid: Optional UUID of a node to center the search around
    """
    if http_client is None:
        raise McpError(ErrorCode.INTERNAL_ERROR, 'HTTP client not initialized')

    try:
        # Validate max_facts parameter
        if max_facts <= 0:
            raise McpError(ErrorCode.INVALID_PARAMS, 'max_facts must be a positive integer')

        # Use the provided group_ids or fall back to the default from config if none provided
        effective_group_ids = (
            group_ids if group_ids is not None else [config.group_id] if config.group_id else []
        )

        # Prepare request payload
        payload = {
            'query': query,
            'group_ids': effective_group_ids,
            'num_results': max_facts,
        }

        if center_node_uuid:
            payload['center_node_uuid'] = center_node_uuid

        # Send request to FastAPI server
        response = await http_client.post('/search', json=payload)
        response.raise_for_status()

        result = response.json()
        facts = result.get('edges', [])

        # Create simplified fact results to reduce response size
        simplified_facts = []
        for fact in facts:
            simplified_fact = {}
            for key, value in fact.items():
                if key in ['uuid', 'relation_type', 'source_node_uuid', 'target_node_uuid', 'group_id', 'created_at']:
                    simplified_fact[key] = value
                elif isinstance(value, str) and len(value) > 50:
                    simplified_fact[key] = value[:50] + '...'
                elif isinstance(value, dict):
                    # Skip complex nested dicts to reduce size
                    simplified_fact[key] = {'...': 'truncated'}
                else:
                    simplified_fact[key] = value
            simplified_facts.append(simplified_fact)

        return FactSearchResponse(message='Facts retrieved successfully', facts=simplified_facts)

    except httpx.HTTPStatusError as e:
        error_msg = f'HTTP error {e.response.status_code}: {e.response.text}'
        logger.error(f'Error searching facts via FastAPI: {error_msg}')
        raise McpError(ErrorCode.INTERNAL_ERROR, f'Error searching facts: {error_msg}')
    except Exception as e:
        error_msg = str(e)
        logger.error(f'Error searching facts: {error_msg}')
        raise McpError(ErrorCode.INTERNAL_ERROR, f'Error searching facts: {error_msg}')


@mcp.tool()
async def delete_entity_edge(
    uuid: str = Field(..., description="UUID of the entity edge to delete")
) -> SuccessResponse:
    """Delete an entity edge from the graph memory via FastAPI server.

    Args:
        uuid: UUID of the entity edge to delete
    """
    if http_client is None:
        raise McpError(ErrorCode.INTERNAL_ERROR, 'HTTP client not initialized')

    try:
        # Send DELETE request to FastAPI server
        response = await http_client.delete(f'/entity-edge/{uuid}')
        response.raise_for_status()

        return SuccessResponse(message=f'Entity edge with UUID {uuid} deleted successfully')

    except httpx.HTTPStatusError as e:
        error_msg = f'HTTP error {e.response.status_code}: {e.response.text}'
        logger.error(f'Error deleting entity edge via FastAPI: {error_msg}')
        raise McpError(ErrorCode.INTERNAL_ERROR, f'Error deleting entity edge: {error_msg}')
    except Exception as e:
        error_msg = str(e)
        logger.error(f'Error deleting entity edge: {error_msg}')
        raise McpError(ErrorCode.INTERNAL_ERROR, f'Error deleting entity edge: {error_msg}')


@mcp.tool()
async def delete_episode(
    uuid: str = Field(..., description="UUID of the episode to delete")
) -> SuccessResponse:
    """Delete an episode from the graph memory via FastAPI server.

    Args:
        uuid: UUID of the episode to delete
    """
    if http_client is None:
        raise McpError(ErrorCode.INTERNAL_ERROR, 'HTTP client not initialized')

    try:
        # Send DELETE request to FastAPI server
        response = await http_client.delete(f'/episode/{uuid}')
        response.raise_for_status()

        return SuccessResponse(message=f'Episode with UUID {uuid} deleted successfully')

    except httpx.HTTPStatusError as e:
        error_msg = f'HTTP error {e.response.status_code}: {e.response.text}'
        logger.error(f'Error deleting episode via FastAPI: {error_msg}')
        raise McpError(ErrorCode.INTERNAL_ERROR, f'Error deleting episode: {error_msg}')
    except Exception as e:
        error_msg = str(e)
        logger.error(f'Error deleting episode: {error_msg}')
        raise McpError(ErrorCode.INTERNAL_ERROR, f'Error deleting episode: {error_msg}')


@mcp.tool()
async def get_entity_edge(
    uuid: str = Field(..., description="UUID of the entity edge to retrieve")
) -> dict[str, Any]:
    """Get an entity edge from the graph memory via FastAPI server.

    Args:
        uuid: UUID of the entity edge to retrieve
    """
    if http_client is None:
        raise McpError(ErrorCode.INTERNAL_ERROR, 'HTTP client not initialized')

    try:
        # Send GET request to FastAPI server
        response = await http_client.get(f'/entity-edge/{uuid}')
        response.raise_for_status()

        return response.json()

    except httpx.HTTPStatusError as e:
        error_msg = f'HTTP error {e.response.status_code}: {e.response.text}'
        logger.error(f'Error getting entity edge via FastAPI: {error_msg}')
        raise McpError(ErrorCode.INTERNAL_ERROR, f'Error getting entity edge: {error_msg}')
    except Exception as e:
        error_msg = str(e)
        logger.error(f'Error getting entity edge: {error_msg}')
        raise McpError(ErrorCode.INTERNAL_ERROR, f'Error getting entity edge: {error_msg}')


@mcp.tool()
async def get_episodes(
    group_id: str | None = Field(None, description="ID of the group to retrieve episodes from. If not provided, uses the default group_id."),
    last_n: int = Field(10, description="Number of most recent episodes to retrieve (default: 10)")
) -> list[dict[str, Any]]:
    """Get the most recent memory episodes for a specific group via FastAPI server.

    Args:
        group_id: ID of the group to retrieve episodes from. If not provided, uses the default group_id.
        last_n: Number of most recent episodes to retrieve (default: 10)
    """
    if http_client is None:
        raise McpError(ErrorCode.INTERNAL_ERROR, 'HTTP client not initialized')

    try:
        # Use the provided group_id or fall back to the default from config
        effective_group_id = group_id if group_id is not None else config.group_id

        if not isinstance(effective_group_id, str):
            raise McpError(ErrorCode.INVALID_PARAMS, 'Group ID must be a string')

        # Send GET request to FastAPI server
        response = await http_client.get(
            f'/episodes/{effective_group_id}', params={'last_n': last_n}
        )
        response.raise_for_status()

        result = response.json()
        episodes = result.get('episodes', [])

        return episodes

    except httpx.HTTPStatusError as e:
        error_msg = f'HTTP error {e.response.status_code}: {e.response.text}'
        logger.error(f'Error getting episodes via FastAPI: {error_msg}')
        raise McpError(ErrorCode.INTERNAL_ERROR, f'Error getting episodes: {error_msg}')
    except Exception as e:
        error_msg = str(e)
        logger.error(f'Error getting episodes: {error_msg}')
        raise McpError(ErrorCode.INTERNAL_ERROR, f'Error getting episodes: {error_msg}')


@mcp.resource(uri='graphiti://status')
async def get_status() -> StatusResponse:
    """Get the status of the Graphiti MCP server and FastAPI connection."""
    if http_client is None:
        raise McpError(ErrorCode.INTERNAL_ERROR, 'HTTP client not initialized')

    try:
        # Test FastAPI server connection
        response = await http_client.get('/healthcheck')
        response.raise_for_status()

        return StatusResponse(
            status='ok', message='Graphiti MCP server is running and connected to FastAPI server'
        )
    except Exception as e:
        error_msg = str(e)
        logger.error(f'Error checking FastAPI server connection: {error_msg}')
        return StatusResponse(
            status='error',
            message=f'Graphiti MCP server is running but FastAPI server connection failed: {error_msg}',
        )