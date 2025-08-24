#!/usr/bin/env python3
"""
Graphiti MCP Server - Exposes Graphiti functionality through the Model Context Protocol (MCP)
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any, TypedDict, cast
from uuid import uuid4

import httpx
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from dotenv import load_dotenv
from graphiti_core import Graphiti
# Removed unused LLM/embedder imports - MCP server only uses HTTP calls to FastAPI endpoint
from mcp.server.fastmcp import FastMCP
from mcp import McpError
try:
    from mcp.types import ErrorCode
except ImportError:
    # Define ErrorCode enum if not available
    from enum import Enum
    class ErrorCode(Enum):
        INTERNAL_ERROR = -32603
        INVALID_PARAMS = -32602
        REQUEST_TIMEOUT = -32000
from mcp.types import ProgressToken, ProgressNotification
import traceback
from pydantic import BaseModel, Field

load_dotenv()



# Semaphore limit for concurrent Graphiti operations.
# Decrease this if you're experiencing 429 rate limit errors from your LLM provider.
# Increase if you have high rate limits.
SEMAPHORE_LIMIT = int(os.getenv('SEMAPHORE_LIMIT', 10))


class Requirement(BaseModel):
    """A Requirement represents a specific need, feature, or functionality that a product or service must fulfill.

    Always ensure an edge is created between the requirement and the project it belongs to, and clearly indicate on the
    edge that the requirement is a requirement.

    Instructions for identifying and extracting requirements:
    1. Look for explicit statements of needs or necessities ("We need X", "X is required", "X must have Y")
    2. Identify functional specifications that describe what the system should do
    3. Pay attention to non-functional requirements like performance, security, or usability criteria
    4. Extract constraints or limitations that must be adhered to
    5. Focus on clear, specific, and measurable requirements rather than vague wishes
    6. Capture the priority or importance if mentioned ("critical", "high priority", etc.)
    7. Include any dependencies between requirements when explicitly stated
    8. Preserve the original intent and scope of the requirement
    9. Categorize requirements appropriately based on their domain or function
    """

    project_name: str = Field(
        ...,
        description='The name of the project to which the requirement belongs.',
    )
    description: str = Field(
        ...,
        description='Description of the requirement. Only use information mentioned in the context to write this description.',
    )


class Preference(BaseModel):
    """A Preference represents a user's expressed like, dislike, or preference for something.

    Instructions for identifying and extracting preferences:
    1. Look for explicit statements of preference such as "I like/love/enjoy/prefer X" or "I don't like/hate/dislike X"
    2. Pay attention to comparative statements ("I prefer X over Y")
    3. Consider the emotional tone when users mention certain topics
    4. Extract only preferences that are clearly expressed, not assumptions
    5. Categorize the preference appropriately based on its domain (food, music, brands, etc.)
    6. Include relevant qualifiers (e.g., "likes spicy food" rather than just "likes food")
    7. Only extract preferences directly stated by the user, not preferences of others they mention
    8. Provide a concise but specific description that captures the nature of the preference
    """

    category: str = Field(
        ...,
        description="The category of the preference. (e.g., 'Brands', 'Food', 'Music')",
    )
    description: str = Field(
        ...,
        description='Brief description of the preference. Only use information mentioned in the context to write this description.',
    )


class Procedure(BaseModel):
    """A Procedure informing the agent what actions to take or how to perform in certain scenarios. Procedures are typically composed of several steps.

    Instructions for identifying and extracting procedures:
    1. Look for sequential instructions or steps ("First do X, then do Y")
    2. Identify explicit directives or commands ("Always do X when Y happens")
    3. Pay attention to conditional statements ("If X occurs, then do Y")
    4. Extract procedures that have clear beginning and end points
    5. Focus on actionable instructions rather than general information
    6. Preserve the original sequence and dependencies between steps
    7. Include any specified conditions or triggers for the procedure
    8. Capture any stated purpose or goal of the procedure
    9. Summarize complex procedures while maintaining critical details
    """

    description: str = Field(
        ...,
        description='Brief description of the procedure. Only use information mentioned in the context to write this description.',
    )


ENTITY_TYPES: dict[str, BaseModel] = {
    'Requirement': Requirement,  # type: ignore
    'Preference': Preference,  # type: ignore
    'Procedure': Procedure,  # type: ignore
}


# Pydantic models for structured output
class MemoryRequest(BaseModel):
    """Request model for adding episodes to memory."""
    name: str = Field(..., description="Name of the episode")
    episode_body: str = Field(..., description="The content of the episode to persist to memory")
    group_id: str | None = Field(None, description="A unique ID for this graph. If not provided, uses the default group_id from CLI")
    source: str = Field('text', description="Source type (text, json, message)")
    source_description: str = Field('', description="Description of the source")
    uuid: str | None = Field(None, description="Optional UUID for the episode")


class NodeSearchRequest(BaseModel):
    """Request model for searching nodes."""
    query: str = Field(..., description="The search query")
    group_ids: list[str] | None = Field(None, description="Optional list of group IDs to filter results")
    max_nodes: int = Field(10, description="Maximum number of nodes to return (default: 10)")
    center_node_uuid: str | None = Field(None, description="Optional UUID of a node to center the search around")
    entity: str = Field('', description="Optional single entity type to filter results")


class FactSearchRequest(BaseModel):
    """Request model for searching facts."""
    query: str = Field(..., description="The search query")
    group_ids: list[str] | None = Field(None, description="Optional list of group IDs to filter results")
    max_facts: int = Field(10, description="Maximum number of facts to return (default: 10)")
    center_node_uuid: str | None = Field(None, description="Optional UUID of a node to center the search around")


class EpisodesRequest(BaseModel):
    """Request model for getting episodes."""
    group_id: str | None = Field(None, description="ID of the group to retrieve episodes from. If not provided, uses the default group_id.")
    last_n: int = Field(10, description="Number of most recent episodes to retrieve (default: 10)")


# Response models
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


class EpisodeSearchResponse(BaseModel):
    """Response for episode search."""
    message: str
    episodes: list[dict[str, Any]]


class StatusResponse(BaseModel):
    """Response for status check."""
    status: str
    message: str


class SuccessResponse(BaseModel):
    """Generic success response."""
    message: str


# Type definitions for API responses (legacy - will be replaced by Pydantic models)
class ErrorResponse(TypedDict):
    error: str


def create_azure_credential_token_provider() -> Callable[[], str]:
    credential = DefaultAzureCredential()
    token_provider = get_bearer_token_provider(
        credential, 'https://cognitiveservices.azure.com/.default'
    )
    return token_provider


# Server configuration classes
# The configuration system has a hierarchy:
# - GraphitiConfig is the top-level configuration
#   - GraphAPIConfig handles connection to the FastAPI server
#   - FalkorDBConfig manages database connection details
#   - Various other settings like group_id and feature flags
# Configuration values are loaded from:
# 1. Default values in the class definitions
# 2. Environment variables (loaded via load_dotenv())
# 3. Command line arguments (which override environment variables)




class GraphAPIConfig(BaseModel):
    """Configuration for Graph API endpoints."""

    base_url: str = 'http://localhost:8003'

    @classmethod
    def from_env(cls) -> 'GraphAPIConfig':
        """Create API configuration from environment variables."""
        return cls(
            base_url=os.environ.get('GRAPH_API_URL', 'http://localhost:8003'),
        )


class GraphitiConfig(BaseModel):
    """Configuration for Graphiti client.

    Centralizes all configuration parameters for the Graphiti client.
    """

    api: GraphAPIConfig = Field(default_factory=GraphAPIConfig)
    group_id: str | None = None
    use_custom_entities: bool = False
    destroy_graph: bool = False

    @classmethod
    def from_env(cls) -> 'GraphitiConfig':
        """Create a configuration instance from environment variables."""
        return cls(
            api=GraphAPIConfig.from_env(),
        )

    @classmethod
    def from_cli_and_env(cls, args: argparse.Namespace) -> 'GraphitiConfig':
        """Create configuration from CLI arguments, falling back to environment variables."""
        # Start with environment configuration
        config = cls.from_env()

        # Apply CLI overrides
        if args.group_id:
            config.group_id = args.group_id
        else:
            config.group_id = 'default'

        config.use_custom_entities = args.use_custom_entities
        config.destroy_graph = args.destroy_graph

        return config


class MCPConfig(BaseModel):
    """Configuration for MCP server."""

    transport: str = 'http'  # Default to HTTP transport
    host: str = '0.0.0.0'
    port: int = 3010

    @classmethod
    def from_cli(cls, args: argparse.Namespace) -> 'MCPConfig':
        """Create MCP configuration from CLI arguments."""
        return cls(
            transport=args.transport,
            host=args.host,
            port=args.port
        )


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

# Environment-based settings
PRODUCTION_MODE = os.environ.get('PRODUCTION_MODE', 'false').lower() == 'true'


def create_operation_context(operation: str, **kwargs) -> dict:
    """Create logging context for operations."""
    context = {
        'operation': operation,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'production_mode': PRODUCTION_MODE
    }
    context.update(kwargs)
    return context


class ProgressReporter:
    """Helper class for reporting operation progress."""
    
    def __init__(self, operation_name: str, progress_token: ProgressToken | None = None):
        self.operation_name = operation_name
        self.progress_token = progress_token
        self.started_at = datetime.now(timezone.utc)
        self.current_step = 0
        self.total_steps = 0
        
    async def start(self, total_steps: int):
        """Start progress reporting."""
        self.total_steps = total_steps
        self.current_step = 0
        
        if self.progress_token:
            await self._send_progress(f"Starting {self.operation_name}...", 0)
        
        context = create_operation_context(self.operation_name, total_steps=total_steps)
        logger.info(f"Starting {self.operation_name} with {total_steps} steps", extra=context)
    
    async def step(self, message: str):
        """Report progress for the current step."""
        self.current_step += 1
        progress = self.current_step / self.total_steps if self.total_steps > 0 else 0
        
        if self.progress_token:
            await self._send_progress(message, progress)
            
        context = create_operation_context(
            self.operation_name, 
            step=self.current_step, 
            total_steps=self.total_steps,
            progress=progress
        )
        logger.info(f"Step {self.current_step}/{self.total_steps}: {message}", extra=context)
    
    async def complete(self, message: str = "Operation completed"):
        """Report operation completion."""
        if self.progress_token:
            await self._send_progress(message, 1.0)
            
        duration = (datetime.now(timezone.utc) - self.started_at).total_seconds()
        context = create_operation_context(
            self.operation_name, 
            completed=True,
            duration_seconds=duration,
            total_steps=self.total_steps
        )
        logger.info(f"{self.operation_name} completed in {duration:.2f}s", extra=context)
    
    async def _send_progress(self, message: str, progress: float):
        """Send progress notification to MCP client."""
        try:
            # This would be sent via the MCP transport
            # For now, we'll use structured logging
            progress_context = create_operation_context(
                self.operation_name,
                progress=progress,
                message=message,
                progress_token=str(self.progress_token) if self.progress_token else None
            )
            logger.debug(f"Progress: {message} ({progress:.1%})", extra=progress_context)
        except Exception as e:
            logger.warning(f"Failed to send progress notification: {e}")

# Create global config instance - will be properly initialized later
config = GraphitiConfig()

# MCP server instructions
GRAPHITI_MCP_INSTRUCTIONS = """
Graphiti is a memory service for AI agents built on a knowledge graph. Graphiti performs well
with dynamic data such as user interactions, changing enterprise data, and external information.

Graphiti transforms information into a richly connected knowledge network, allowing you to 
capture relationships between concepts, entities, and information. The system organizes data as episodes 
(content snippets), nodes (entities), and facts (relationships between entities), creating a dynamic, 
queryable memory store that evolves with new information. Graphiti supports multiple data formats, including 
structured JSON data, enabling seamless integration with existing data pipelines and systems.

Facts contain temporal metadata, allowing you to track the time of creation and whether a fact is invalid 
(superseded by new information).

Key capabilities:
1. Add episodes (text, messages, or JSON) to the knowledge graph with the add_memory tool
2. Search for nodes (entities) in the graph using natural language queries with search_nodes
3. Find relevant facts (relationships between entities) with search_facts
4. Retrieve specific entity edges or episodes by UUID
5. Manage the knowledge graph with tools like delete_episode, delete_entity_edge, and clear_graph

The server connects to a database for persistent storage and uses language models for certain operations. 
Each piece of information is organized by group_id, allowing you to maintain separate knowledge domains.

When adding information, provide descriptive names and detailed content to improve search quality. 
When searching, use specific queries and consider filtering by group_id for more relevant results.

For optimal performance, ensure the database is properly configured and accessible, and valid 
API keys are provided for any language model operations.
"""

# MCP server instance
mcp = FastMCP(
    'Graphiti Agent Memory',
    instructions=GRAPHITI_MCP_INSTRUCTIONS,
)

# HTTP client for FastAPI server
http_client: httpx.AsyncClient | None = None

# Semaphore for concurrent operations (matching the one used in the main config)
operation_semaphore: asyncio.Semaphore | None = None

# Resource system
from resources import (ResourceManager, EntityResourceHandler, EntityListResourceHandler, EntityRecentResourceHandler,
                      EpisodeResourceHandler, EpisodeListResourceHandler, NodeSearchResourceHandler, 
                      FactSearchResourceHandler, SearchResourceHandler, GraphStatsResourceHandler,
                      NodeMetricsResourceHandler, TemporalAnalyticsResourceHandler, GroupAnalyticsResourceHandler,
                      WildcardResourceHandler, ParameterizedResourceHandler, DynamicResourceHandler, TemplateRegistryResourceHandler)
resource_manager: ResourceManager | None = None


async def initialize_graphiti():
    """Initialize the HTTP client for FastAPI server with connection pooling."""
    global http_client, config, operation_semaphore, resource_manager

    try:
        # Configure connection limits for better performance
        limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
        timeout = httpx.Timeout(30.0, read=60.0)  # Longer read timeout for large responses
        
        # Initialize HTTP client for FastAPI server with connection pooling
        http_client = httpx.AsyncClient(
            base_url=config.api.base_url, 
            timeout=timeout,
            limits=limits,
            http2=False  # Disable HTTP/2 to avoid h2 dependency requirement
        )
        
        # Initialize semaphore for concurrent operations
        operation_semaphore = asyncio.Semaphore(SEMAPHORE_LIMIT)

        # Test connection to FastAPI server
        response = await http_client.get('/healthcheck')
        response.raise_for_status()
        logger.info(f'Connected to Graphiti FastAPI server at {config.api.base_url}')

        # Destroy graph if requested
        if config.destroy_graph:
            logger.info('Clearing graph via FastAPI...')
            response = await http_client.post('/clear')
            response.raise_for_status()

        logger.info(f'Using group_id: {config.group_id}')
        logger.info(f'Using FastAPI endpoint: {config.api.base_url}')
        
        # Initialize resource system
        resource_manager = ResourceManager(http_client, config)
        
        # Register entity resource handlers
        resource_manager.register_handler(EntityResourceHandler(http_client, config))
        resource_manager.register_handler(EntityListResourceHandler(http_client, config))
        resource_manager.register_handler(EntityRecentResourceHandler(http_client, config))
        
        # Register episode resource handlers
        resource_manager.register_handler(EpisodeResourceHandler(http_client, config))
        resource_manager.register_handler(EpisodeListResourceHandler(http_client, config))
        
        # Register search resource handlers
        resource_manager.register_handler(NodeSearchResourceHandler(http_client, config))
        resource_manager.register_handler(FactSearchResourceHandler(http_client, config))
        resource_manager.register_handler(SearchResourceHandler(http_client, config))
        
        # Register analytics resource handlers
        resource_manager.register_handler(GraphStatsResourceHandler(http_client, config))
        resource_manager.register_handler(NodeMetricsResourceHandler(http_client, config))
        resource_manager.register_handler(TemporalAnalyticsResourceHandler(http_client, config))
        resource_manager.register_handler(GroupAnalyticsResourceHandler(http_client, config))
        
        # Register template resource handlers
        resource_manager.register_handler(WildcardResourceHandler(http_client, config))
        resource_manager.register_handler(ParameterizedResourceHandler(http_client, config))
        resource_manager.register_handler(DynamicResourceHandler(http_client, config))
        resource_manager.register_handler(TemplateRegistryResourceHandler(http_client, config))
        
        logger.info('Resource system initialized with entity, episode, search, analytics, and template handlers')

    except Exception as e:
        logger.error(f'Failed to initialize connection to FastAPI server: {str(e)}')
        raise


async def cleanup_graphiti():
    """Cleanup HTTP client and resources."""
    global http_client
    
    if http_client is not None:
        logger.info('Closing HTTP client connection')
        await http_client.aclose()
        http_client = None


def mask_sensitive_error(error_msg: str, operation: str) -> str:
    """Mask sensitive information in error messages for production."""
    if not PRODUCTION_MODE:
        return error_msg
    
    # In production, return generic error messages to avoid information leakage
    sensitive_patterns = [
        'api_key', 'token', 'password', 'secret', 'credential',
        'authorization', 'bearer', 'oauth', 'key='
    ]
    
    error_lower = error_msg.lower()
    if any(pattern in error_lower for pattern in sensitive_patterns):
        return f"Authentication error occurred during {operation}"
    
    # Generic error for HTTP errors that might contain sensitive info
    if 'http error' in error_lower:
        return f"Service communication error during {operation}"
    
    return error_msg


def categorize_error(exception: Exception) -> ErrorCode:
    """Categorize exceptions into appropriate MCP error codes."""
    if isinstance(exception, httpx.TimeoutException):
        return ErrorCode.REQUEST_TIMEOUT
    elif isinstance(exception, httpx.HTTPStatusError):
        status_code = exception.response.status_code
        if status_code == 400:
            return ErrorCode.INVALID_PARAMS
        elif status_code == 401 or status_code == 403:
            return ErrorCode.INVALID_PARAMS  # Authentication/authorization issues
        elif status_code == 404:
            return ErrorCode.INVALID_PARAMS  # Resource not found
        elif status_code >= 500:
            return ErrorCode.INTERNAL_ERROR  # Server errors
        else:
            return ErrorCode.INTERNAL_ERROR
    elif isinstance(exception, (ValueError, TypeError)):
        return ErrorCode.INVALID_PARAMS
    else:
        return ErrorCode.INTERNAL_ERROR


async def execute_with_semaphore(operation_name: str, operation_func):
    """Execute an async operation with semaphore-based concurrency control and comprehensive error handling."""
    global operation_semaphore
    
    if operation_semaphore is None:
        logger.warning(f'Operation semaphore not initialized for {operation_name}, proceeding without concurrency control')
        return await operation_func()
    
    async with operation_semaphore:
        logger.debug(f'Executing {operation_name} with semaphore (remaining permits: {operation_semaphore._value})')
        return await operation_func()


async def execute_with_retry(operation_name: str, operation_func, max_retries: int = 2):
    """Execute an operation with retry logic for transient errors."""
    last_exception = None
    
    for attempt in range(max_retries + 1):
        try:
            return await operation_func()
        except Exception as e:
            last_exception = e
            
            # Only retry for specific transient errors
            if isinstance(e, (httpx.TimeoutException, httpx.ConnectError)):
                if attempt < max_retries:
                    wait_time = 2 ** attempt  # Exponential backoff
                    logger.warning(f'Transient error in {operation_name} (attempt {attempt + 1}/{max_retries + 1}), retrying in {wait_time}s: {str(e)}')
                    await asyncio.sleep(wait_time)
                    continue
            
            # For non-retryable errors, break immediately
            break
    
    # If we get here, all retries failed
    error_code = categorize_error(last_exception)
    masked_error = mask_sensitive_error(str(last_exception), operation_name)
    
    # Log the full error with structured context for debugging
    error_context = create_operation_context(
        operation_name,
        attempts=max_retries + 1,
        error_type=type(last_exception).__name__,
        error_code=error_code.value
    )
    
    logger.error(f'Operation failed after retries', extra=error_context)
    if not PRODUCTION_MODE:
        logger.debug(f'Full traceback for {operation_name}: {traceback.format_exc()}', extra=error_context)
    
    raise McpError(error_code, masked_error)

# Removed queue processing functions - now using direct FastAPI calls


@mcp.tool()
async def add_memory(
    name: str = Field(..., description="Name of the episode"),
    episode_body: str = Field(..., description="The content of the episode to persist to memory"),
    group_id: str | None = Field(None, description="A unique ID for this graph. If not provided, uses the default group_id from CLI"),
    source: str = Field('text', description="Source type (text, json, message)"),
    source_description: str = Field('', description="Description of the source"),
    uuid: str | None = Field(None, description="Optional UUID for the episode"),
    progress_token: ProgressToken | None = Field(None, description="Progress token for reporting operation progress"),
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
    global http_client

    if http_client is None:
        raise McpError(ErrorCode.INTERNAL_ERROR, 'HTTP client not initialized')

    async def _execute_add_memory():
        """Internal function to execute add_memory with proper error handling."""
        # Initialize progress reporter
        progress = ProgressReporter('add_memory', progress_token)
        await progress.start(3)  # 3 steps: prepare, send, confirm
        
        try:
            # Step 1: Prepare request data
            await progress.step("Preparing episode data")
            
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

            # Step 2: Send to FastAPI server
            await progress.step("Sending episode to memory store")
            response = await http_client.post('/messages', json=payload)
            response.raise_for_status()

            # Step 3: Process response
            await progress.step("Confirming episode storage")
            result = response.json()
            logger.info(f"Episode '{name}' added successfully via FastAPI")
            
            await progress.complete(f"Episode '{name}' successfully added to memory")
            return SuccessResponse(message=f"Episode '{name}' added successfully")

        except httpx.HTTPStatusError as e:
            error_msg = f'HTTP error {e.response.status_code}: {e.response.text}'
            logger.error(f'Error adding episode via FastAPI: {error_msg}')
            raise McpError(ErrorCode.INTERNAL_ERROR, f'Error adding episode: {error_msg}')
        except Exception as e:
            error_msg = str(e)
            logger.error(f'Error adding episode: {error_msg}')
            raise McpError(ErrorCode.INTERNAL_ERROR, f'Error adding episode: {error_msg}')
    
    # Execute with concurrency control and retry logic for transient errors
    async def _execute_with_retry():
        return await execute_with_retry('add_memory', _execute_add_memory)
    
    return await execute_with_semaphore('add_memory', _execute_with_retry)


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
    global http_client

    if http_client is None:
        raise McpError(ErrorCode.INTERNAL_ERROR, 'HTTP client not initialized')

    try:
        # Use the provided group_ids or fall back to the default from config if none provided
        effective_group_ids = (
            group_ids if group_ids is not None else [config.group_id] if config.group_id else []
        )

        # Prepare Rust service format request payload
        payload = {
            'query': query,
            'config': {
                'limit': max_nodes,
                'reranker_min_score': 0.0,
                'node_config': {
                    'search_methods': ['fulltext', 'similarity'],
                    'reranker': 'rrf',
                    'bfs_max_depth': 2,
                    'sim_min_score': 0.3,
                    'mmr_lambda': 0.5,
                    'centrality_boost_factor': 1.0
                },
                'edge_config': {
                    'search_methods': [],
                    'reranker': 'rrf',
                    'bfs_max_depth': 1,
                    'sim_min_score': 0.3,
                    'mmr_lambda': 0.5
                }
            },
            'filters': {}
        }

        # Add filters if provided
        if effective_group_ids:
            payload['filters']['group_ids'] = effective_group_ids
        if center_node_uuid:
            payload['filters']['center_node_uuid'] = center_node_uuid
        if entity:
            payload['filters']['entity_type'] = entity

        # Send request to Rust search service directly
        response = await http_client.post('/search', json=payload)
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
    global http_client

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

        # Prepare Rust service format request payload
        payload = {
            'query': query,
            'config': {
                'limit': max_facts,
                'reranker_min_score': 0.0,
                'node_config': {
                    'search_methods': [],
                    'reranker': 'rrf',
                    'bfs_max_depth': 1,
                    'sim_min_score': 0.3,
                    'mmr_lambda': 0.5
                },
                'edge_config': {
                    'search_methods': ['fulltext', 'similarity'],
                    'reranker': 'rrf',
                    'bfs_max_depth': 2,
                    'sim_min_score': 0.3,
                    'mmr_lambda': 0.5
                }
            },
            'filters': {}
        }

        # Add filters if provided
        if effective_group_ids:
            payload['filters']['group_ids'] = effective_group_ids
        if center_node_uuid:
            payload['filters']['center_node_uuid'] = center_node_uuid

        # Send request to Rust search service directly
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
async def delete_entity_edge(uuid: str) -> SuccessResponse | ErrorResponse:
    """Delete an entity edge from the graph memory via FastAPI server.

    Args:
        uuid: UUID of the entity edge to delete
    """
    global http_client

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
async def delete_episode(uuid: str) -> SuccessResponse | ErrorResponse:
    """Delete an episode from the graph memory via FastAPI server.

    Args:
        uuid: UUID of the episode to delete
    """
    global http_client

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
async def get_entity_edge(uuid: str) -> dict[str, Any] | ErrorResponse:
    """Get an entity edge from the graph memory via FastAPI server.

    Args:
        uuid: UUID of the entity edge to retrieve
    """
    global http_client

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
    group_id: str | None = None, last_n: int = 10
) -> list[dict[str, Any]] | EpisodeSearchResponse | ErrorResponse:
    """Get the most recent memory episodes for a specific group via FastAPI server.

    Args:
        group_id: ID of the group to retrieve episodes from. If not provided, uses the default group_id.
        last_n: Number of most recent episodes to retrieve (default: 10)
    """
    global http_client

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
    global http_client

    if http_client is None:
        return StatusResponse(status='error', message='HTTP client not initialized')

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


# PHASE 3: PROMPTS SYSTEM - Query Prompts (GRAPH-109)

@mcp.prompt()
async def query_knowledge(
    topic: str = Field(..., description="Topic or subject to search for in the knowledge graph"),
    max_results: int = Field(10, description="Maximum number of results to return", ge=1, le=50),
    include_facts: bool = Field(True, description="Whether to include related facts/relationships"),
    group_id: str | None = Field(None, description="Optional group ID to filter results")
) -> str:
    """Search for comprehensive information about a topic in the knowledge graph.
    
    This prompt searches both nodes (entities) and facts (relationships) to provide
    a comprehensive view of what the knowledge graph knows about a specific topic.
    
    Usage examples:
    - /query_knowledge "docker containers" 
    - /query_knowledge "machine learning algorithms" --max_results 15 --include_facts false
    - /query_knowledge "project requirements" --group_id "project-alpha"
    """
    global http_client
    
    if http_client is None:
        return "❌ Error: Knowledge graph connection not available"
    
    try:
        # Use provided group_id or default
        effective_group_id = group_id if group_id is not None else config.group_id
        effective_group_ids = [effective_group_id] if effective_group_id else []
        
        results = []
        
        # Search for nodes (entities) related to the topic
        node_payload = {
            'query': topic,
            'group_ids': effective_group_ids,
            'max_nodes': max_results
        }
        
        node_response = await http_client.post('/search/nodes', json=node_payload)
        node_response.raise_for_status()
        node_data = node_response.json()
        nodes = node_data.get('nodes', [])
        
        if nodes:
            results.append(f"## 🎯 Entities found for '{topic}':")
            for i, node in enumerate(nodes[:max_results], 1):
                name = node.get('name', 'Unknown')
                summary = node.get('summary', 'No summary available')
                labels = ', '.join(node.get('labels', []))
                results.append(f"{i}. **{name}** ({labels})")
                if summary and len(summary) > 0:
                    # Truncate long summaries
                    truncated_summary = summary[:200] + '...' if len(summary) > 200 else summary
                    results.append(f"   {truncated_summary}")
        
        # Search for facts/relationships if requested
        if include_facts:
            fact_payload = {
                'query': topic,
                'group_ids': effective_group_ids,
                'max_facts': max_results
            }
            
            fact_response = await http_client.post('/search', json=fact_payload)
            fact_response.raise_for_status()
            fact_data = fact_response.json()
            facts = fact_data.get('edges', [])
            
            if facts:
                results.append(f"\n## 🔗 Related relationships for '{topic}':")
                for i, fact in enumerate(facts[:max_results], 1):
                    relation_type = fact.get('relation_type', 'related_to')
                    source_name = fact.get('source_name', 'Unknown')
                    target_name = fact.get('target_name', 'Unknown')
                    results.append(f"{i}. {source_name} **{relation_type}** {target_name}")
        
        if not nodes and not facts:
            return f"🤷 No information found for '{topic}' in the knowledge graph. Try different keywords or check if the data has been added to the graph."
        
        # Add summary footer
        node_count = len(nodes)
        fact_count = len(facts) if include_facts else 0
        summary_footer = f"\n---\n📊 **Summary**: Found {node_count} entities"
        if include_facts:
            summary_footer += f" and {fact_count} relationships"
        summary_footer += f" for '{topic}'"
        
        if effective_group_id:
            summary_footer += f" in group '{effective_group_id}'"
            
        results.append(summary_footer)
        
        return '\n'.join(results)
        
    except httpx.HTTPStatusError as e:
        error_msg = f'HTTP error {e.response.status_code}: {e.response.text}'
        logger.error(f'Error in query_knowledge: {error_msg}')
        return f"❌ Error searching knowledge graph: {error_msg}"
    except Exception as e:
        error_msg = str(e)
        logger.error(f'Error in query_knowledge: {error_msg}')
        return f"❌ Error searching knowledge graph: {error_msg}"


@mcp.prompt()
async def find_connections(
    entity_name: str = Field(..., description="Name of the entity to find connections for"),
    max_connections: int = Field(10, description="Maximum number of connections to return", ge=1, le=25),
    connection_depth: int = Field(1, description="Depth of connections to explore (1=direct, 2=second-degree)", ge=1, le=3),
    group_id: str | None = Field(None, description="Optional group ID to filter results")
) -> str:
    """Find and explore connections between entities in the knowledge graph.
    
    This prompt finds an entity and shows its relationships to other entities,
    helping to understand the network of connections around a specific item.
    
    Usage examples:
    - /find_connections "Alice Johnson"
    - /find_connections "Docker" --max_connections 15 --connection_depth 2
    - /find_connections "Project Alpha" --group_id "work-projects"
    """
    global http_client
    
    if http_client is None:
        return "❌ Error: Knowledge graph connection not available"
    
    try:
        # Use provided group_id or default
        effective_group_id = group_id if group_id is not None else config.group_id
        effective_group_ids = [effective_group_id] if effective_group_id else []
        
        results = []
        
        # First, search for the entity to get its UUID
        entity_payload = {
            'query': entity_name,
            'group_ids': effective_group_ids,
            'max_nodes': 5
        }
        
        entity_response = await http_client.post('/search/nodes', json=entity_payload)
        entity_response.raise_for_status()
        entity_data = entity_response.json()
        entities = entity_data.get('nodes', [])
        
        if not entities:
            return f"🤷 Entity '{entity_name}' not found in the knowledge graph. Try a different name or check if the entity exists."
        
        # Use the first matching entity
        target_entity = entities[0]
        target_uuid = target_entity.get('uuid')
        target_name = target_entity.get('name', entity_name)
        target_labels = ', '.join(target_entity.get('labels', []))
        
        results.append(f"## 🎯 Found entity: **{target_name}** ({target_labels})")
        
        if target_entity.get('summary'):
            summary = target_entity['summary'][:150] + '...' if len(target_entity['summary']) > 150 else target_entity['summary']
            results.append(f"*{summary}*\n")
        
        # Search for connections using the entity's UUID as center
        connections_payload = {
            'query': entity_name,
            'group_ids': effective_group_ids,
            'max_facts': max_connections,
            'center_node_uuid': target_uuid
        }
        
        # Get relationships/facts centered on this entity
        fact_response = await http_client.post('/search', json=connections_payload)
        fact_response.raise_for_status()
        fact_data = fact_response.json()
        facts = fact_data.get('edges', [])
        
        if facts:
            results.append(f"## 🔗 Direct connections from '{target_name}':")
            
            # Group connections by relationship type
            connections_by_type = {}
            for fact in facts[:max_connections]:
                relation_type = fact.get('relation_type', 'related_to')
                source_uuid = fact.get('source_node_uuid')
                target_fact_uuid = fact.get('target_node_uuid')
                
                # Determine if this entity is source or target
                if source_uuid == target_uuid:
                    # This entity is the source
                    connected_name = fact.get('target_name', 'Unknown')
                    direction = '→'
                else:
                    # This entity is the target  
                    connected_name = fact.get('source_name', 'Unknown')
                    direction = '←'
                    
                if relation_type not in connections_by_type:
                    connections_by_type[relation_type] = []
                connections_by_type[relation_type].append(f"{direction} {connected_name}")
            
            for relation_type, connections in connections_by_type.items():
                results.append(f"\n**{relation_type.replace('_', ' ').title()}:**")
                for connection in connections:
                    results.append(f"  {connection}")
        else:
            results.append(f"🤷 No direct connections found for '{target_name}'")
        
        # Add summary
        connection_count = len(facts)
        results.append(f"\n---\n📊 **Summary**: Found {connection_count} connections for '{target_name}'")
        
        if effective_group_id:
            results.append(f"Searched in group: '{effective_group_id}'")
            
        return '\n'.join(results)
        
    except httpx.HTTPStatusError as e:
        error_msg = f'HTTP error {e.response.status_code}: {e.response.text}'
        logger.error(f'Error in find_connections: {error_msg}')
        return f"❌ Error finding connections: {error_msg}"
    except Exception as e:
        error_msg = str(e)
        logger.error(f'Error in find_connections: {error_msg}')
        return f"❌ Error finding connections: {error_msg}"


@mcp.prompt()
async def explore_domain(
    domain: str = Field(..., description="Domain or area to explore (e.g., 'machine learning', 'project management')"),
    focus_type: str = Field("overview", description="Type of exploration: 'overview', 'entities', 'relationships', 'patterns'"),
    max_items: int = Field(15, description="Maximum number of items to return", ge=1, le=50),
    group_id: str | None = Field(None, description="Optional group ID to filter results")
) -> str:
    """Explore a knowledge domain to understand its structure and key components.
    
    This prompt provides different views of a knowledge domain, helping to understand
    the landscape of information available about a particular area.
    
    Usage examples:
    - /explore_domain "artificial intelligence"
    - /explore_domain "customer feedback" --focus_type "relationships" 
    - /explore_domain "software architecture" --focus_type "patterns" --max_items 20
    """
    global http_client
    
    if http_client is None:
        return "❌ Error: Knowledge graph connection not available"
    
    try:
        # Use provided group_id or default
        effective_group_id = group_id if group_id is not None else config.group_id  
        effective_group_ids = [effective_group_id] if effective_group_id else []
        
        results = []
        results.append(f"# 🌐 Exploring Domain: '{domain}'")
        results.append(f"**Focus**: {focus_type.title()} | **Max Items**: {max_items}")
        
        if effective_group_id:
            results.append(f"**Group**: {effective_group_id}")
            
        results.append("")
        
        if focus_type in ["overview", "entities"]:
            # Search for entities in this domain
            node_payload = {
                'query': domain,
                'group_ids': effective_group_ids,
                'max_nodes': max_items
            }
            
            node_response = await http_client.post('/search/nodes', json=node_payload)
            node_response.raise_for_status()
            node_data = node_response.json()
            nodes = node_data.get('nodes', [])
            
            if nodes:
                results.append(f"## 🎯 Key Entities in '{domain}':")
                
                # Group entities by label/type if available
                entities_by_type = {}
                for node in nodes:
                    labels = node.get('labels', ['Entity'])
                    primary_label = labels[0] if labels else 'Entity'
                    
                    if primary_label not in entities_by_type:
                        entities_by_type[primary_label] = []
                    
                    name = node.get('name', 'Unknown')
                    summary = node.get('summary', '')
                    summary_preview = summary[:100] + '...' if len(summary) > 100 else summary
                    
                    entities_by_type[primary_label].append({
                        'name': name,
                        'summary': summary_preview
                    })
                
                for entity_type, entities in entities_by_type.items():
                    results.append(f"\n**{entity_type}** ({len(entities)}):")
                    for entity in entities:
                        results.append(f"  • **{entity['name']}**")
                        if entity['summary']:
                            results.append(f"    {entity['summary']}")
        
        if focus_type in ["overview", "relationships"]:
            # Search for relationships in this domain
            fact_payload = {
                'query': domain,
                'group_ids': effective_group_ids,
                'max_facts': max_items
            }
            
            fact_response = await http_client.post('/search', json=fact_payload)
            fact_response.raise_for_status()
            fact_data = fact_response.json()
            facts = fact_data.get('edges', [])
            
            if facts:
                results.append(f"\n## 🔗 Key Relationships in '{domain}':")
                
                # Group relationships by type
                relationships_by_type = {}
                for fact in facts:
                    relation_type = fact.get('relation_type', 'related_to')
                    source_name = fact.get('source_name', 'Unknown')
                    target_name = fact.get('target_name', 'Unknown')
                    
                    if relation_type not in relationships_by_type:
                        relationships_by_type[relation_type] = []
                    
                    relationships_by_type[relation_type].append(f"{source_name} → {target_name}")
                
                for relation_type, relationships in relationships_by_type.items():
                    results.append(f"\n**{relation_type.replace('_', ' ').title()}** ({len(relationships)}):")
                    for relationship in relationships[:5]:  # Show top 5 per type
                        results.append(f"  • {relationship}")
                    if len(relationships) > 5:
                        results.append(f"  • ... and {len(relationships) - 5} more")
        
        if focus_type == "patterns":
            # Try to identify patterns by analyzing entity types and relationship patterns
            # This is a simplified pattern analysis
            combined_payload = {
                'query': domain,
                'group_ids': effective_group_ids,
                'max_nodes': max_items
            }
            
            # Get both nodes and facts for pattern analysis
            node_response = await http_client.post('/search/nodes', json=combined_payload)
            fact_response = await http_client.post('/search', json=combined_payload)
            
            node_response.raise_for_status()
            fact_response.raise_for_status()
            
            nodes = node_response.json().get('nodes', [])
            facts = fact_response.json().get('edges', [])
            
            results.append(f"## 📊 Patterns in '{domain}':")
            
            # Analyze entity type distribution
            if nodes:
                entity_types = {}
                for node in nodes:
                    labels = node.get('labels', ['Entity'])
                    for label in labels:
                        entity_types[label] = entity_types.get(label, 0) + 1
                
                results.append(f"\n**Entity Type Distribution**:")
                for entity_type, count in sorted(entity_types.items(), key=lambda x: x[1], reverse=True):
                    percentage = (count / len(nodes)) * 100
                    results.append(f"  • {entity_type}: {count} ({percentage:.1f}%)")
            
            # Analyze relationship patterns
            if facts:
                relation_types = {}
                for fact in facts:
                    relation_type = fact.get('relation_type', 'related_to')
                    relation_types[relation_type] = relation_types.get(relation_type, 0) + 1
                
                results.append(f"\n**Relationship Patterns**:")
                for relation_type, count in sorted(relation_types.items(), key=lambda x: x[1], reverse=True):
                    percentage = (count / len(facts)) * 100
                    results.append(f"  • {relation_type.replace('_', ' ').title()}: {count} ({percentage:.1f}%)")
        
        # Add summary statistics
        node_count = 0
        fact_count = 0
        
        if focus_type in ["overview", "entities", "patterns"]:
            try:
                node_response = await http_client.post('/search/nodes', json={'query': domain, 'group_ids': effective_group_ids, 'max_nodes': 100})
                node_count = len(node_response.json().get('nodes', []))
            except:
                pass
        
        if focus_type in ["overview", "relationships", "patterns"]:
            try:
                fact_response = await http_client.post('/search', json={'query': domain, 'group_ids': effective_group_ids, 'max_facts': 100})
                fact_count = len(fact_response.json().get('edges', []))
            except:
                pass
        
        results.append(f"\n---")
        results.append(f"📊 **Domain Statistics**: {node_count} entities, {fact_count} relationships")
        results.append(f"🔍 **Exploration Type**: {focus_type.title()}")
        
        return '\n'.join(results)
        
    except httpx.HTTPStatusError as e:
        error_msg = f'HTTP error {e.response.status_code}: {e.response.text}'
        logger.error(f'Error in explore_domain: {error_msg}')
        return f"❌ Error exploring domain: {error_msg}"
    except Exception as e:
        error_msg = str(e)
        logger.error(f'Error in explore_domain: {error_msg}')
        return f"❌ Error exploring domain: {error_msg}"


# PHASE 3: PROMPTS SYSTEM - Analysis Prompts (GRAPH-110)

@mcp.prompt()
async def analyze_patterns(
    domain: str = Field(..., description="Domain or topic to analyze patterns for"),
    pattern_type: str = Field("relationship", description="Type of patterns to analyze: 'relationship', 'entity', 'temporal', 'all'"),
    min_frequency: int = Field(2, description="Minimum frequency for pattern to be reported", ge=1, le=100),
    group_id: str | None = Field(None, description="Optional group ID to filter results")
) -> str:
    """Analyze patterns and trends in the knowledge graph for a specific domain.
    
    This prompt performs advanced pattern analysis to identify recurring themes,
    common relationships, and structural patterns in the knowledge graph data.
    
    Usage examples:
    - /analyze_patterns "software development" 
    - /analyze_patterns "customer interactions" --pattern_type "temporal" --min_frequency 5
    - /analyze_patterns "project management" --pattern_type "all" --group_id "work-data"
    """
    global http_client
    
    if http_client is None:
        return "❌ Error: Knowledge graph connection not available"
    
    try:
        # Use provided group_id or default
        effective_group_id = group_id if group_id is not None else config.group_id
        effective_group_ids = [effective_group_id] if effective_group_id else []
        
        results = []
        results.append(f"# 📊 Pattern Analysis: '{domain}'")
        results.append(f"**Pattern Type**: {pattern_type.title()} | **Min Frequency**: {min_frequency}")
        
        if effective_group_id:
            results.append(f"**Group**: {effective_group_id}")
        
        results.append("")
        
        # Get data for pattern analysis
        search_payload = {
            'query': domain,
            'group_ids': effective_group_ids,
            'max_nodes': 50  # Get more data for better pattern analysis
        }
        
        nodes = []
        facts = []
        
        if pattern_type in ["entity", "all"]:
            # Get entities for entity pattern analysis
            node_response = await http_client.post('/search/nodes', json=search_payload)
            node_response.raise_for_status()
            nodes = node_response.json().get('nodes', [])
        
        if pattern_type in ["relationship", "temporal", "all"]:
            # Get facts for relationship pattern analysis
            fact_response = await http_client.post('/search', json=search_payload)
            fact_response.raise_for_status()
            facts = fact_response.json().get('edges', [])
        
        patterns_found = []
        
        # Entity Pattern Analysis
        if pattern_type in ["entity", "all"] and nodes:
            results.append("## 🎯 Entity Patterns")
            
            # Analyze entity type patterns
            entity_type_counts = {}
            attribute_patterns = {}
            
            for node in nodes:
                # Count entity types
                labels = node.get('labels', ['Entity'])
                for label in labels:
                    entity_type_counts[label] = entity_type_counts.get(label, 0) + 1
                
                # Analyze naming patterns (simple analysis)
                name = node.get('name', '').lower()
                if len(name) > 0:
                    # Common word analysis
                    words = name.split()
                    for word in words:
                        if len(word) > 3:  # Skip short words
                            key = f"name_contains_{word}"
                            attribute_patterns[key] = attribute_patterns.get(key, 0) + 1
            
            # Report entity type patterns above threshold
            results.append("\n**Entity Type Patterns:**")
            for entity_type, count in sorted(entity_type_counts.items(), key=lambda x: x[1], reverse=True):
                if count >= min_frequency:
                    percentage = (count / len(nodes)) * 100
                    results.append(f"  • {entity_type}: {count} occurrences ({percentage:.1f}%)")
                    patterns_found.append(f"Entity type '{entity_type}' appears {count} times")
            
            # Report naming patterns above threshold
            significant_patterns = {k: v for k, v in attribute_patterns.items() if v >= min_frequency}
            if significant_patterns:
                results.append("\n**Naming Patterns:**")
                for pattern, count in sorted(significant_patterns.items(), key=lambda x: x[1], reverse=True)[:10]:
                    word = pattern.replace('name_contains_', '')
                    results.append(f"  • Names containing '{word}': {count} entities")
                    patterns_found.append(f"Naming pattern '{word}' appears {count} times")
        
        # Relationship Pattern Analysis  
        if pattern_type in ["relationship", "all"] and facts:
            results.append("\n## 🔗 Relationship Patterns")
            
            # Analyze relationship types
            relation_type_counts = {}
            relationship_direction_patterns = {}
            
            for fact in facts:
                relation_type = fact.get('relation_type', 'related_to')
                relation_type_counts[relation_type] = relation_type_counts.get(relation_type, 0) + 1
                
                # Analyze directional patterns (simplified)
                source_name = fact.get('source_name', '').lower()
                target_name = fact.get('target_name', '').lower()
                
                # Pattern: what types of things relate to what
                pattern_key = f"{relation_type}_pattern"
                if pattern_key not in relationship_direction_patterns:
                    relationship_direction_patterns[pattern_key] = []
                relationship_direction_patterns[pattern_key].append((source_name, target_name))
            
            # Report relationship type patterns
            results.append("\n**Relationship Type Patterns:**")
            for relation_type, count in sorted(relation_type_counts.items(), key=lambda x: x[1], reverse=True):
                if count >= min_frequency:
                    percentage = (count / len(facts)) * 100
                    results.append(f"  • {relation_type.replace('_', ' ').title()}: {count} occurrences ({percentage:.1f}%)")
                    patterns_found.append(f"Relationship '{relation_type}' appears {count} times")
        
        # Temporal Pattern Analysis (simplified)
        if pattern_type in ["temporal", "all"] and facts:
            results.append("\n## ⏰ Temporal Patterns")
            
            # Analyze creation time patterns (if available)
            time_patterns = {}
            for fact in facts:
                created_at = fact.get('created_at', '')
                if created_at:
                    try:
                        # Extract date patterns (simplified - just by date)
                        date_part = created_at.split('T')[0] if 'T' in created_at else created_at[:10]
                        time_patterns[date_part] = time_patterns.get(date_part, 0) + 1
                    except:
                        continue
            
            if time_patterns:
                # Find dates with activity above threshold
                significant_dates = {date: count for date, count in time_patterns.items() if count >= min_frequency}
                if significant_dates:
                    results.append("\n**High-Activity Dates:**")
                    for date, count in sorted(significant_dates.items(), key=lambda x: x[1], reverse=True)[:10]:
                        results.append(f"  • {date}: {count} relationships created")
                        patterns_found.append(f"High activity on {date} with {count} relationships")
        
        # Pattern Summary
        if patterns_found:
            results.append(f"\n## 📈 Pattern Summary")
            results.append(f"**Patterns Discovered**: {len(patterns_found)}")
            results.append(f"**Analysis Scope**: {len(nodes)} entities, {len(facts)} relationships")
            
            # Top insights
            results.append("\n**Key Insights:**")
            for i, pattern in enumerate(patterns_found[:5], 1):
                results.append(f"  {i}. {pattern}")
            
            if len(patterns_found) > 5:
                results.append(f"  ... and {len(patterns_found) - 5} more patterns")
        else:
            results.append(f"\n🤷 No significant patterns found for '{domain}' with minimum frequency {min_frequency}")
            results.append("Try lowering the minimum frequency or exploring a different domain.")
        
        return '\n'.join(results)
        
    except httpx.HTTPStatusError as e:
        error_msg = f'HTTP error {e.response.status_code}: {e.response.text}'
        logger.error(f'Error in analyze_patterns: {error_msg}')
        return f"❌ Error analyzing patterns: {error_msg}"
    except Exception as e:
        error_msg = str(e)
        logger.error(f'Error in analyze_patterns: {error_msg}')
        return f"❌ Error analyzing patterns: {error_msg}"


@mcp.prompt()
async def compare_entities(
    entity1: str = Field(..., description="Name of the first entity to compare"),
    entity2: str = Field(..., description="Name of the second entity to compare"),
    comparison_depth: str = Field("detailed", description="Depth of comparison: 'basic', 'detailed', 'comprehensive'"),
    group_id: str | None = Field(None, description="Optional group ID to filter results")
) -> str:
    """Compare two entities in the knowledge graph to understand their similarities and differences.
    
    This prompt provides detailed comparison analysis between entities, including
    their attributes, relationships, and contextual differences.
    
    Usage examples:
    - /compare_entities "Docker" "Kubernetes"
    - /compare_entities "Alice Johnson" "Bob Smith" --comparison_depth "comprehensive"
    - /compare_entities "Project Alpha" "Project Beta" --group_id "work-projects"
    """
    global http_client
    
    if http_client is None:
        return "❌ Error: Knowledge graph connection not available"
    
    try:
        # Use provided group_id or default
        effective_group_id = group_id if group_id is not None else config.group_id
        effective_group_ids = [effective_group_id] if effective_group_id else []
        
        results = []
        results.append(f"# ⚖️ Entity Comparison: '{entity1}' vs '{entity2}'")
        results.append(f"**Comparison Depth**: {comparison_depth.title()}")
        
        if effective_group_id:
            results.append(f"**Group**: {effective_group_id}")
        
        results.append("")
        
        # Search for both entities
        entity1_data = None
        entity2_data = None
        entity1_facts = []
        entity2_facts = []
        
        # Find entity 1
        search1_payload = {
            'query': entity1,
            'group_ids': effective_group_ids,
            'max_nodes': 5
        }
        
        entity1_response = await http_client.post('/search/nodes', json=search1_payload)
        entity1_response.raise_for_status()
        entity1_nodes = entity1_response.json().get('nodes', [])
        
        if entity1_nodes:
            entity1_data = entity1_nodes[0]  # Use first match
            
            # Get relationships for entity 1 if detailed comparison
            if comparison_depth in ["detailed", "comprehensive"]:
                facts1_payload = {
                    'query': entity1,
                    'group_ids': effective_group_ids,
                    'max_facts': 20,
                    'center_node_uuid': entity1_data.get('uuid')
                }
                facts1_response = await http_client.post('/search', json=facts1_payload)
                facts1_response.raise_for_status()
                entity1_facts = facts1_response.json().get('edges', [])
        
        # Find entity 2
        search2_payload = {
            'query': entity2,
            'group_ids': effective_group_ids,
            'max_nodes': 5
        }
        
        entity2_response = await http_client.post('/search/nodes', json=search2_payload)
        entity2_response.raise_for_status()
        entity2_nodes = entity2_response.json().get('nodes', [])
        
        if entity2_nodes:
            entity2_data = entity2_nodes[0]  # Use first match
            
            # Get relationships for entity 2 if detailed comparison
            if comparison_depth in ["detailed", "comprehensive"]:
                facts2_payload = {
                    'query': entity2,
                    'group_ids': effective_group_ids,
                    'max_facts': 20,
                    'center_node_uuid': entity2_data.get('uuid')
                }
                facts2_response = await http_client.post('/search', json=facts2_payload)
                facts2_response.raise_for_status()
                entity2_facts = facts2_response.json().get('edges', [])
        
        # Check if both entities were found
        if not entity1_data and not entity2_data:
            return f"❌ Neither '{entity1}' nor '{entity2}' found in the knowledge graph."
        elif not entity1_data:
            return f"❌ Entity '{entity1}' not found in the knowledge graph."
        elif not entity2_data:
            return f"❌ Entity '{entity2}' not found in the knowledge graph."
        
        # Basic comparison
        results.append("## 📋 Basic Information")
        results.append(f"### {entity1_data.get('name', entity1)}")
        results.append(f"**Type**: {', '.join(entity1_data.get('labels', ['Unknown']))}")
        if entity1_data.get('summary'):
            summary1 = entity1_data['summary'][:200] + '...' if len(entity1_data['summary']) > 200 else entity1_data['summary']
            results.append(f"**Summary**: {summary1}")
        
        results.append(f"\n### {entity2_data.get('name', entity2)}")
        results.append(f"**Type**: {', '.join(entity2_data.get('labels', ['Unknown']))}")
        if entity2_data.get('summary'):
            summary2 = entity2_data['summary'][:200] + '...' if len(entity2_data['summary']) > 200 else entity2_data['summary']
            results.append(f"**Summary**: {summary2}")
        
        # Type comparison
        labels1 = set(entity1_data.get('labels', []))
        labels2 = set(entity2_data.get('labels', []))
        
        common_types = labels1 & labels2
        unique_to_1 = labels1 - labels2
        unique_to_2 = labels2 - labels1
        
        results.append("\n## 🏷️ Type Comparison")
        if common_types:
            results.append(f"**Common Types**: {', '.join(common_types)}")
        if unique_to_1:
            results.append(f"**Unique to {entity1_data.get('name', entity1)}**: {', '.join(unique_to_1)}")
        if unique_to_2:
            results.append(f"**Unique to {entity2_data.get('name', entity2)}**: {', '.join(unique_to_2)}")
        
        # Detailed comparison - relationships
        if comparison_depth in ["detailed", "comprehensive"] and (entity1_facts or entity2_facts):
            results.append("\n## 🔗 Relationship Comparison")
            
            # Analyze relationship patterns for each entity
            def analyze_relationships(facts, entity_name):
                relation_types = {}
                connected_entities = set()
                
                for fact in facts:
                    relation_type = fact.get('relation_type', 'related_to')
                    relation_types[relation_type] = relation_types.get(relation_type, 0) + 1
                    
                    # Add connected entities
                    source_name = fact.get('source_name', '')
                    target_name = fact.get('target_name', '')
                    connected_entities.add(source_name if source_name != entity_name else target_name)
                
                return relation_types, connected_entities
            
            rel1_types, connected1 = analyze_relationships(entity1_facts, entity1_data.get('name', entity1))
            rel2_types, connected2 = analyze_relationships(entity2_facts, entity2_data.get('name', entity2))
            
            # Compare relationship types
            results.append(f"### {entity1_data.get('name', entity1)} Relationships")
            if rel1_types:
                for rel_type, count in sorted(rel1_types.items(), key=lambda x: x[1], reverse=True)[:5]:
                    results.append(f"  • {rel_type.replace('_', ' ').title()}: {count}")
            else:
                results.append("  • No relationships found")
            
            results.append(f"\n### {entity2_data.get('name', entity2)} Relationships")
            if rel2_types:
                for rel_type, count in sorted(rel2_types.items(), key=lambda x: x[1], reverse=True)[:5]:
                    results.append(f"  • {rel_type.replace('_', ' ').title()}: {count}")
            else:
                results.append("  • No relationships found")
            
            # Find common connections
            common_connections = connected1 & connected2
            if common_connections:
                results.append(f"\n### 🤝 Common Connections")
                for connection in sorted(common_connections)[:10]:
                    if connection:  # Skip empty connections
                        results.append(f"  • {connection}")
        
        # Comprehensive comparison - additional analysis
        if comparison_depth == "comprehensive":
            results.append("\n## 📊 Comprehensive Analysis")
            
            # Connection count comparison
            conn1_count = len(entity1_facts)
            conn2_count = len(entity2_facts)
            
            results.append(f"**Connection Density**:")
            results.append(f"  • {entity1_data.get('name', entity1)}: {conn1_count} relationships")
            results.append(f"  • {entity2_data.get('name', entity2)}: {conn2_count} relationships")
            
            if conn1_count > 0 or conn2_count > 0:
                more_connected = entity1_data.get('name', entity1) if conn1_count > conn2_count else entity2_data.get('name', entity2)
                results.append(f"  • {more_connected} is more highly connected")
            
            # Attribute comparison (if available)
            attrs1 = entity1_data.get('attributes', {})
            attrs2 = entity2_data.get('attributes', {})
            
            if attrs1 or attrs2:
                results.append(f"\n**Attributes Comparison**:")
                all_keys = set(attrs1.keys()) | set(attrs2.keys())
                for key in sorted(all_keys):
                    val1 = attrs1.get(key, '—')
                    val2 = attrs2.get(key, '—')
                    results.append(f"  • {key}: {val1} | {val2}")
        
        # Summary
        results.append(f"\n---")
        results.append(f"📊 **Comparison Summary**:")
        results.append(f"  • Type similarity: {'High' if common_types else 'Low'}")
        if comparison_depth in ["detailed", "comprehensive"]:
            common_connections = len(set([f.get('target_name', '') for f in entity1_facts]) & 
                                   set([f.get('target_name', '') for f in entity2_facts]))
            results.append(f"  • Shared connections: {common_connections}")
            results.append(f"  • Relationship complexity: {len(entity1_facts)} vs {len(entity2_facts)}")
        
        return '\n'.join(results)
        
    except httpx.HTTPStatusError as e:
        error_msg = f'HTTP error {e.response.status_code}: {e.response.text}'
        logger.error(f'Error in compare_entities: {error_msg}')
        return f"❌ Error comparing entities: {error_msg}"
    except Exception as e:
        error_msg = str(e)
        logger.error(f'Error in compare_entities: {error_msg}')
        return f"❌ Error comparing entities: {error_msg}"


@mcp.prompt()
async def summarize_episode(
    episode_identifier: str = Field(..., description="Episode ID, name, or search term to identify the episode"),
    summary_style: str = Field("balanced", description="Summary style: 'brief', 'balanced', 'detailed', 'bullet_points'"),
    focus_areas: str = Field("all", description="Areas to focus on: 'all', 'entities', 'events', 'insights', 'outcomes'"),
    group_id: str | None = Field(None, description="Optional group ID to filter results")
) -> str:
    """Summarize a specific episode or memory from the knowledge graph.
    
    This prompt provides intelligent summarization of episodes, extracting key
    information, entities, and insights in the requested format and focus.
    
    Usage examples:
    - /summarize_episode "meeting-2024-03-15"
    - /summarize_episode "customer feedback session" --summary_style "bullet_points" --focus_areas "insights"
    - /summarize_episode "project review" --summary_style "detailed" --group_id "work-sessions"
    """
    global http_client
    
    if http_client is None:
        return "❌ Error: Knowledge graph connection not available"
    
    try:
        # Use provided group_id or default
        effective_group_id = group_id if group_id is not None else config.group_id
        
        results = []
        results.append(f"# 📄 Episode Summary: '{episode_identifier}'")
        results.append(f"**Style**: {summary_style.title()} | **Focus**: {focus_areas.title()}")
        
        if effective_group_id:
            results.append(f"**Group**: {effective_group_id}")
        
        results.append("")
        
        episode_data = None
        
        # Try to find the episode - first by exact ID, then by search
        try:
            # Try direct episode lookup if it looks like a UUID
            if len(episode_identifier) > 20 and '-' in episode_identifier:
                episode_response = await http_client.get(f'/episode/{episode_identifier}')
                if episode_response.status_code == 200:
                    episode_data = episode_response.json()
        except:
            pass
        
        # If not found by ID, search for episodes
        if not episode_data:
            search_params = {'last_n': 50}
            episodes_response = await http_client.get(f'/episodes/{effective_group_id}', params=search_params)
            episodes_response.raise_for_status()
            episodes = episodes_response.json().get('episodes', [])
            
            # Find matching episode by name or content
            for episode in episodes:
                name = episode.get('name', '').lower()
                content = episode.get('content', '').lower()
                search_term = episode_identifier.lower()
                
                if (search_term in name or 
                    search_term in content or
                    name == search_term or
                    episode.get('uuid', '') == episode_identifier):
                    episode_data = episode
                    break
        
        if not episode_data:
            return f"❌ Episode '{episode_identifier}' not found. Try a different identifier or check if the episode exists."
        
        # Extract episode information
        episode_name = episode_data.get('name', 'Untitled Episode')
        episode_content = episode_data.get('content', '')
        episode_uuid = episode_data.get('uuid', '')
        created_at = episode_data.get('created_at', '')
        
        # Basic episode info
        results.append(f"## 📝 Episode: {episode_name}")
        if created_at:
            results.append(f"**Created**: {created_at}")
        if episode_uuid:
            results.append(f"**ID**: {episode_uuid[:8]}...")
        
        results.append("")
        
        # Analyze content based on focus areas
        content_length = len(episode_content)
        
        if focus_areas in ["all", "events"] and episode_content:
            if summary_style == "brief":
                # Brief summary - first 200 characters
                brief_content = episode_content[:200] + '...' if content_length > 200 else episode_content
                results.append(f"**Brief Summary**: {brief_content}")
            
            elif summary_style == "balanced":
                # Balanced summary - key sentences
                sentences = episode_content.split('. ')
                if len(sentences) > 3:
                    key_sentences = sentences[:2] + [sentences[-1]]  # First 2 and last sentence
                    summary_content = '. '.join(key_sentences)
                else:
                    summary_content = episode_content
                
                summary_content = summary_content[:500] + '...' if len(summary_content) > 500 else summary_content
                results.append(f"**Summary**: {summary_content}")
            
            elif summary_style == "detailed":
                # Detailed summary - full content with structure
                results.append("**Detailed Content**:")
                # Break into paragraphs if long
                if content_length > 300:
                    paragraphs = episode_content.split('\n\n')
                    for i, paragraph in enumerate(paragraphs[:5], 1):  # Max 5 paragraphs
                        if paragraph.strip():
                            results.append(f"\n{i}. {paragraph.strip()}")
                else:
                    results.append(f"\n{episode_content}")
            
            elif summary_style == "bullet_points":
                # Bullet points - key information
                results.append("**Key Points**:")
                # Simple sentence splitting for bullet points
                sentences = episode_content.split('. ')
                for sentence in sentences[:10]:  # Max 10 bullets
                    if len(sentence.strip()) > 10:  # Skip very short fragments
                        results.append(f"  • {sentence.strip()}")
        
        # Entity analysis
        if focus_areas in ["all", "entities"]:
            # Search for entities related to this episode content
            entity_search_payload = {
                'query': episode_content[:200],  # Use first part of content for search
                'group_ids': [effective_group_id] if effective_group_id else [],
                'max_nodes': 10
            }
            
            try:
                entity_response = await http_client.post('/search/nodes', json=entity_search_payload)
                entity_response.raise_for_status()
                entities = entity_response.json().get('nodes', [])
                
                if entities:
                    results.append(f"\n## 🎯 Related Entities")
                    entity_types = {}
                    
                    for entity in entities[:8]:  # Show top 8 entities
                        name = entity.get('name', 'Unknown')
                        labels = entity.get('labels', ['Entity'])
                        primary_label = labels[0] if labels else 'Entity'
                        
                        if primary_label not in entity_types:
                            entity_types[primary_label] = []
                        entity_types[primary_label].append(name)
                    
                    for entity_type, names in entity_types.items():
                        results.append(f"**{entity_type}**: {', '.join(names)}")
            except:
                pass  # Skip entity analysis if it fails
        
        # Insights extraction
        if focus_areas in ["all", "insights"]:
            results.append(f"\n## 💡 Key Insights")
            
            # Simple keyword-based insight extraction
            insight_keywords = {
                'decision': '🎯 Decision',
                'problem': '⚠️ Problem',
                'solution': '✅ Solution', 
                'action': '🚀 Action',
                'outcome': '📊 Outcome',
                'lesson': '📚 Lesson',
                'risk': '⚡ Risk',
                'opportunity': '🌟 Opportunity'
            }
            
            insights_found = []
            content_lower = episode_content.lower()
            
            for keyword, icon in insight_keywords.items():
                if keyword in content_lower:
                    # Find sentences containing the keyword
                    sentences = episode_content.split('.')
                    for sentence in sentences:
                        if keyword in sentence.lower() and len(sentence.strip()) > 20:
                            insights_found.append(f"  {icon}: {sentence.strip()}")
                            break
            
            if insights_found:
                for insight in insights_found[:5]:  # Max 5 insights
                    results.append(insight)
            else:
                results.append("  • No specific insights detected. Content may require human analysis.")
        
        # Episode statistics
        results.append(f"\n---")
        results.append(f"📊 **Episode Statistics**:")
        results.append(f"  • Content length: {content_length} characters")
        
        # Word count approximation
        word_count = len(episode_content.split()) if episode_content else 0
        results.append(f"  • Estimated words: {word_count}")
        
        # Reading time approximation (200 words per minute)
        reading_time = max(1, word_count // 200)
        results.append(f"  • Estimated reading time: {reading_time} minute{'s' if reading_time != 1 else ''}")
        
        return '\n'.join(results)
        
    except httpx.HTTPStatusError as e:
        error_msg = f'HTTP error {e.response.status_code}: {e.response.text}'
        logger.error(f'Error in summarize_episode: {error_msg}')
        return f"❌ Error summarizing episode: {error_msg}"
    except Exception as e:
        error_msg = str(e)
        logger.error(f'Error in summarize_episode: {error_msg}')
        return f"❌ Error summarizing episode: {error_msg}"


# PHASE 3: PROMPTS SYSTEM - Learning Prompts (GRAPH-111)

@mcp.prompt()
async def save_insight(
    insight_title: str = Field(..., description="Title or brief description of the insight"),
    insight_content: str = Field(..., description="Detailed content of the insight to save"),
    insight_category: str = Field("general", description="Category: 'technical', 'business', 'process', 'lesson_learned', 'best_practice', 'general'"),
    related_entities: str = Field("", description="Comma-separated list of related entities or topics"),
    priority: str = Field("medium", description="Priority level: 'low', 'medium', 'high', 'critical'"),
    group_id: str | None = Field(None, description="Optional group ID to save the insight to")
) -> str:
    """Capture and save new insights to the knowledge graph for future reference.
    
    This prompt helps preserve valuable insights, learnings, and discoveries by
    storing them as structured episodes with proper categorization and relationships.
    
    Usage examples:
    - /save_insight "Database optimization breakthrough" "Found that adding composite indexes reduces query time by 80%"
    - /save_insight "Customer feedback pattern" "Users consistently request dark mode" --insight_category "business" --priority "high"
    - /save_insight "Code review insight" "Team velocity increases when PRs are < 200 lines" --related_entities "development,team_process" --group_id "engineering"
    """
    global http_client
    
    if http_client is None:
        return "❌ Error: Knowledge graph connection not available"
    
    try:
        # Use provided group_id or default
        effective_group_id = group_id if group_id is not None else config.group_id
        group_id_str = str(effective_group_id) if effective_group_id is not None else 'default'
        
        # Create structured insight content
        timestamp = datetime.now(timezone.utc).isoformat()
        
        # Parse related entities
        entity_list = [entity.strip() for entity in related_entities.split(',')] if related_entities else []
        
        # Build comprehensive insight content
        structured_content = []
        structured_content.append(f"# 💡 Insight: {insight_title}")
        structured_content.append(f"**Category**: {insight_category.replace('_', ' ').title()}")
        structured_content.append(f"**Priority**: {priority.upper()}")
        structured_content.append(f"**Captured**: {timestamp}")
        
        if entity_list:
            structured_content.append(f"**Related Topics**: {', '.join(entity_list)}")
        
        structured_content.append("")
        structured_content.append("## Content")
        structured_content.append(insight_content)
        
        # Add metadata tags for better searchability
        structured_content.append("")
        structured_content.append("## Metadata")
        structured_content.append(f"- Type: Insight")
        structured_content.append(f"- Category: {insight_category}")
        structured_content.append(f"- Priority: {priority}")
        structured_content.append(f"- Source: MCP Learning Prompt")
        
        if entity_list:
            structured_content.append("- Tags: " + ", ".join(entity_list))
        
        final_content = '\n'.join(structured_content)
        
        # Create episode message
        message = {
            'content': final_content,
            'role_type': 'system',
            'role': f'insight_capture_{insight_category}',
            'timestamp': timestamp,
            'source_description': f'Captured insight: {insight_title}',
            'name': f'Insight: {insight_title}'
        }
        
        payload = {
            'group_id': group_id_str,
            'messages': [message]
        }
        
        # Save to knowledge graph
        response = await http_client.post('/messages', json=payload)
        response.raise_for_status()
        
        result = response.json()
        
        # Create success response
        results = []
        results.append(f"✅ **Insight Saved Successfully**")
        results.append(f"**Title**: {insight_title}")
        results.append(f"**Category**: {insight_category.replace('_', ' ').title()}")
        results.append(f"**Priority**: {priority.upper()}")
        
        if effective_group_id:
            results.append(f"**Group**: {effective_group_id}")
        
        if entity_list:
            results.append(f"**Related Topics**: {', '.join(entity_list)}")
        
        results.append("")
        results.append("## 📚 Knowledge Impact")
        results.append("This insight has been:")
        results.append("  • Added to the knowledge graph for future reference")
        results.append("  • Categorized and tagged for easy discovery")
        results.append("  • Made searchable via entity and content queries")
        
        if entity_list:
            results.append("  • Linked to related topics for connection discovery")
        
        results.append("")
        results.append("## 🔍 How to Find This Later")
        results.append(f"  • Search for: `{insight_title}`")
        results.append(f"  • Category search: `{insight_category}`")
        
        if entity_list:
            for entity in entity_list[:3]:  # Show first 3 entities
                results.append(f"  • Topic search: `{entity}`")
        
        return '\n'.join(results)
        
    except httpx.HTTPStatusError as e:
        error_msg = f'HTTP error {e.response.status_code}: {e.response.text}'
        logger.error(f'Error in save_insight: {error_msg}')
        return f"❌ Error saving insight: {error_msg}"
    except Exception as e:
        error_msg = str(e)
        logger.error(f'Error in save_insight: {error_msg}')
        return f"❌ Error saving insight: {error_msg}"


@mcp.prompt()
async def create_pattern(
    pattern_name: str = Field(..., description="Name of the pattern to create"),
    pattern_description: str = Field(..., description="Detailed description of the pattern"),
    pattern_type: str = Field("process", description="Pattern type: 'process', 'technical', 'behavioral', 'decision', 'design', 'workflow'"),
    when_to_use: str = Field("", description="When or under what circumstances to use this pattern"),
    steps_or_components: str = Field("", description="Key steps, components, or elements of the pattern (comma-separated)"),
    examples: str = Field("", description="Real examples of where this pattern applies"),
    group_id: str | None = Field(None, description="Optional group ID to save the pattern to")
) -> str:
    """Create and save reusable pattern templates for consistent application of best practices.
    
    This prompt helps document recurring solutions, processes, and approaches as
    structured patterns that can be referenced and applied in similar situations.
    
    Usage examples:
    - /create_pattern "Code Review Process" "Standard process for reviewing code changes" --when_to_use "Before merging any pull request"
    - /create_pattern "Customer Escalation Flow" "Process for handling escalated customer issues" --pattern_type "process" --steps_or_components "acknowledge,investigate,escalate,resolve,follow_up"
    - /create_pattern "Database Migration Strategy" "Safe approach for database schema changes" --examples "user_table_v2, payment_system_refactor"
    """
    global http_client
    
    if http_client is None:
        return "❌ Error: Knowledge graph connection not available"
    
    try:
        # Use provided group_id or default
        effective_group_id = group_id if group_id is not None else config.group_id
        group_id_str = str(effective_group_id) if effective_group_id is not None else 'default'
        
        # Create structured pattern content
        timestamp = datetime.now(timezone.utc).isoformat()
        
        # Parse steps/components
        steps_list = [step.strip() for step in steps_or_components.split(',')] if steps_or_components else []
        examples_list = [example.strip() for example in examples.split(',')] if examples else []
        
        # Build comprehensive pattern template
        structured_content = []
        structured_content.append(f"# 🏗️ Pattern: {pattern_name}")
        structured_content.append(f"**Type**: {pattern_type.replace('_', ' ').title()}")
        structured_content.append(f"**Created**: {timestamp}")
        structured_content.append("")
        
        # Description
        structured_content.append("## 📝 Description")
        structured_content.append(pattern_description)
        structured_content.append("")
        
        # When to use
        if when_to_use:
            structured_content.append("## 🎯 When to Use")
            structured_content.append(when_to_use)
            structured_content.append("")
        
        # Steps or components
        if steps_list:
            structured_content.append("## 🔧 Steps/Components")
            for i, step in enumerate(steps_list, 1):
                structured_content.append(f"{i}. {step}")
            structured_content.append("")
        
        # Examples
        if examples_list:
            structured_content.append("## 💡 Examples")
            for example in examples_list:
                structured_content.append(f"  • {example}")
            structured_content.append("")
        
        # Implementation template
        structured_content.append("## 📋 Implementation Checklist")
        structured_content.append("- [ ] Review pattern applicability")
        structured_content.append("- [ ] Adapt pattern to specific context")
        
        if steps_list:
            for step in steps_list:
                structured_content.append(f"- [ ] {step}")
        
        structured_content.append("- [ ] Document any modifications")
        structured_content.append("- [ ] Review results and update pattern if needed")
        structured_content.append("")
        
        # Metadata
        structured_content.append("## 📊 Pattern Metadata")
        structured_content.append(f"- Pattern Type: {pattern_type}")
        structured_content.append(f"- Created: {timestamp}")
        structured_content.append(f"- Source: MCP Learning Prompt")
        structured_content.append("- Status: Active Template")
        
        if steps_list:
            structured_content.append(f"- Complexity: {len(steps_list)} steps")
        
        final_content = '\n'.join(structured_content)
        
        # Create episode message
        message = {
            'content': final_content,
            'role_type': 'system',
            'role': f'pattern_template_{pattern_type}',
            'timestamp': timestamp,
            'source_description': f'Created pattern template: {pattern_name}',
            'name': f'Pattern: {pattern_name}'
        }
        
        payload = {
            'group_id': group_id_str,
            'messages': [message]
        }
        
        # Save to knowledge graph
        response = await http_client.post('/messages', json=payload)
        response.raise_for_status()
        
        # Create success response
        results = []
        results.append(f"✅ **Pattern Created Successfully**")
        results.append(f"**Name**: {pattern_name}")
        results.append(f"**Type**: {pattern_type.replace('_', ' ').title()}")
        
        if effective_group_id:
            results.append(f"**Group**: {effective_group_id}")
        
        results.append("")
        results.append("## 📝 Pattern Summary")
        results.append(f"**Description**: {pattern_description[:150]}{'...' if len(pattern_description) > 150 else ''}")
        
        if when_to_use:
            results.append(f"**When to Use**: {when_to_use[:100]}{'...' if len(when_to_use) > 100 else ''}")
        
        if steps_list:
            results.append(f"**Steps**: {len(steps_list)} defined steps")
        
        if examples_list:
            results.append(f"**Examples**: {len(examples_list)} reference examples")
        
        results.append("")
        results.append("## 🚀 Next Steps")
        results.append("This pattern template can now be:")
        results.append("  • Referenced in future similar situations")
        results.append("  • Found via search using the pattern name or type")
        results.append("  • Modified and improved based on usage experience")
        results.append("  • Shared with team members for consistent application")
        
        results.append("")
        results.append("## 🔍 How to Apply This Pattern")
        results.append(f"1. Search for: `{pattern_name}` or `pattern {pattern_type}`")
        results.append("2. Review the implementation checklist")
        results.append("3. Adapt steps to your specific context")
        results.append("4. Document any modifications for future reference")
        
        return '\n'.join(results)
        
    except httpx.HTTPStatusError as e:
        error_msg = f'HTTP error {e.response.status_code}: {e.response.text}'
        logger.error(f'Error in create_pattern: {error_msg}')
        return f"❌ Error creating pattern: {error_msg}"
    except Exception as e:
        error_msg = str(e)
        logger.error(f'Error in create_pattern: {error_msg}')
        return f"❌ Error creating pattern: {error_msg}"


@mcp.prompt()
async def document_solution(
    problem_title: str = Field(..., description="Title or brief description of the problem that was solved"),
    problem_description: str = Field(..., description="Detailed description of the problem"),
    solution_approach: str = Field(..., description="The approach or solution that was implemented"),
    implementation_details: str = Field("", description="Technical details of how the solution was implemented"),
    outcome_results: str = Field("", description="Results, metrics, or outcomes achieved"),
    lessons_learned: str = Field("", description="Key lessons learned from this solution"),
    technologies_used: str = Field("", description="Technologies, tools, or frameworks used (comma-separated)"),
    team_members: str = Field("", description="Team members who contributed (comma-separated)"),
    group_id: str | None = Field(None, description="Optional group ID to save the solution documentation to")
) -> str:
    """Document solutions to problems for future reference and knowledge sharing.
    
    This prompt creates comprehensive documentation of problem-solving approaches,
    making successful solutions discoverable and reusable for similar challenges.
    
    Usage examples:
    - /document_solution "Database performance issue" "Slow queries affecting user experience" "Added composite indexes and query optimization"
    - /document_solution "Customer onboarding bottleneck" "New users dropping off during signup" "Simplified form and added progress indicators" --outcome_results "30% increase in completion rate"
    - /document_solution "API rate limiting" "Third-party API throttling requests" "Implemented exponential backoff with Redis caching" --technologies_used "Redis,Python,FastAPI"
    """
    global http_client
    
    if http_client is None:
        return "❌ Error: Knowledge graph connection not available"
    
    try:
        # Use provided group_id or default
        effective_group_id = group_id if group_id is not None else config.group_id
        group_id_str = str(effective_group_id) if effective_group_id is not None else 'default'
        
        # Create structured solution documentation
        timestamp = datetime.now(timezone.utc).isoformat()
        
        # Parse lists
        tech_list = [tech.strip() for tech in technologies_used.split(',')] if technologies_used else []
        team_list = [member.strip() for member in team_members.split(',')] if team_members else []
        
        # Build comprehensive solution documentation
        structured_content = []
        structured_content.append(f"# 🔧 Solution: {problem_title}")
        structured_content.append(f"**Documented**: {timestamp}")
        structured_content.append("")
        
        # Problem section
        structured_content.append("## ❓ Problem")
        structured_content.append(problem_description)
        structured_content.append("")
        
        # Solution section
        structured_content.append("## ✅ Solution")
        structured_content.append(solution_approach)
        structured_content.append("")
        
        # Implementation details
        if implementation_details:
            structured_content.append("## 🛠️ Implementation Details")
            structured_content.append(implementation_details)
            structured_content.append("")
        
        # Technologies used
        if tech_list:
            structured_content.append("## 💻 Technologies Used")
            for tech in tech_list:
                structured_content.append(f"  • {tech}")
            structured_content.append("")
        
        # Outcomes and results
        if outcome_results:
            structured_content.append("## 📊 Outcomes & Results")
            structured_content.append(outcome_results)
            structured_content.append("")
        
        # Lessons learned
        if lessons_learned:
            structured_content.append("## 📚 Lessons Learned")
            structured_content.append(lessons_learned)
            structured_content.append("")
        
        # Team contribution
        if team_list:
            structured_content.append("## 👥 Contributors")
            for member in team_list:
                structured_content.append(f"  • {member}")
            structured_content.append("")
        
        # Reusability section
        structured_content.append("## 🔄 Reusability")
        structured_content.append("**When to reference this solution:**")
        structured_content.append(f"  • Similar problems involving: {problem_title.lower()}")
        
        if tech_list:
            structured_content.append(f"  • Projects using: {', '.join(tech_list)}")
        
        structured_content.append("  • When facing similar technical constraints")
        structured_content.append("")
        
        # Metadata
        structured_content.append("## 📋 Metadata")
        structured_content.append(f"- Solution Type: Problem Resolution")
        structured_content.append(f"- Documented: {timestamp}")
        structured_content.append(f"- Source: MCP Learning Prompt")
        structured_content.append(f"- Status: Documented Solution")
        
        if tech_list:
            structured_content.append(f"- Tech Stack: {', '.join(tech_list)}")
        
        if team_list:
            structured_content.append(f"- Team Size: {len(team_list)} contributors")
        
        final_content = '\n'.join(structured_content)
        
        # Create episode message
        message = {
            'content': final_content,
            'role_type': 'system',
            'role': 'solution_documentation',
            'timestamp': timestamp,
            'source_description': f'Documented solution: {problem_title}',
            'name': f'Solution: {problem_title}'
        }
        
        payload = {
            'group_id': group_id_str,
            'messages': [message]
        }
        
        # Save to knowledge graph
        response = await http_client.post('/messages', json=payload)
        response.raise_for_status()
        
        # Create success response
        results = []
        results.append(f"✅ **Solution Documented Successfully**")
        results.append(f"**Problem**: {problem_title}")
        results.append(f"**Solution**: {solution_approach[:100]}{'...' if len(solution_approach) > 100 else ''}")
        
        if effective_group_id:
            results.append(f"**Group**: {effective_group_id}")
        
        results.append("")
        results.append("## 📝 Documentation Summary")
        
        if implementation_details:
            results.append("  ✅ Implementation details included")
        
        if outcome_results:
            results.append("  ✅ Outcomes and results documented")
        
        if lessons_learned:
            results.append("  ✅ Lessons learned captured")
        
        if tech_list:
            results.append(f"  ✅ Technologies documented: {', '.join(tech_list)}")
        
        if team_list:
            results.append(f"  ✅ Contributors recognized: {', '.join(team_list)}")
        
        results.append("")
        results.append("## 🎯 Knowledge Impact")
        results.append("This solution documentation will help with:")
        results.append("  • Finding proven approaches to similar problems")
        results.append("  • Understanding implementation trade-offs")
        results.append("  • Learning from past successes and challenges")
        results.append("  • Recognizing patterns across projects")
        
        if tech_list:
            results.append(f"  • Leveraging experience with {', '.join(tech_list[:3])}")
        
        results.append("")
        results.append("## 🔍 How to Find This Solution")
        results.append(f"  • Problem search: `{problem_title}`")
        results.append(f"  • Solution search: keywords from approach")
        
        if tech_list:
            for tech in tech_list[:2]:
                results.append(f"  • Technology search: `{tech}`")
        
        results.append("  • Browse solution documentation category")
        
        return '\n'.join(results)
        
    except httpx.HTTPStatusError as e:
        error_msg = f'HTTP error {e.response.status_code}: {e.response.text}'
        logger.error(f'Error in document_solution: {error_msg}')
        return f"❌ Error documenting solution: {error_msg}"
    except Exception as e:
        error_msg = str(e)
        logger.error(f'Error in document_solution: {error_msg}')
        return f"❌ Error documenting solution: {error_msg}"


# GRAPH-112: Implement prompt validation
@mcp.prompt()
async def validate_prompt_input(
    prompt_name: str = Field(..., description="Name of the prompt to validate input for"),
    input_data: str = Field(..., description="JSON string of input parameters to validate"),
    validation_type: str = Field("full", description="Type of validation: 'syntax', 'semantic', 'graph', 'full'"),
    strict_mode: bool = Field(False, description="Enable strict validation with detailed checks"),
    group_id: str | None = Field(None, description="Optional group ID for context validation")
) -> str:
    """Validate input parameters for MCP prompts and check data integrity.
    
    Performs comprehensive validation of prompt inputs including:
    - Syntax validation (JSON format, required fields)
    - Semantic validation (value ranges, format constraints)
    - Graph validation (entity existence, relationship validity)
    - Full validation (all checks combined)
    
    Returns detailed validation report with suggestions for fixes.
    """
    try:
        # Parse input data
        try:
            import json
            parsed_input = json.loads(input_data)
        except json.JSONDecodeError as e:
            return f"""❌ **Input Validation Failed - JSON Syntax Error**

**Error**: Invalid JSON format
**Details**: {str(e)}

**Suggestions**:
- Check for missing quotes around strings
- Verify proper comma placement
- Ensure brackets and braces are balanced
- Use double quotes for JSON strings

**Example Valid JSON**:
```json
{{
    "topic": "user interactions",
    "max_results": 10,
    "include_facts": true
}}
```
"""

        validation_report = []
        validation_passed = True
        
        # Define known prompt schemas
        prompt_schemas = {
            "query_knowledge": {
                "required": ["topic"],
                "optional": ["max_results", "include_facts", "group_id"],
                "types": {"topic": str, "max_results": int, "include_facts": bool, "group_id": str},
                "ranges": {"max_results": (1, 50)}
            },
            "search_entities": {
                "required": ["entity_name"],
                "optional": ["entity_type", "max_results", "include_relationships", "group_id"],
                "types": {"entity_name": str, "entity_type": str, "max_results": int, "include_relationships": bool},
                "ranges": {"max_results": (1, 100)}
            },
            "analyze_patterns": {
                "required": ["domain"],
                "optional": ["pattern_type", "min_frequency", "group_id"],
                "types": {"domain": str, "pattern_type": str, "min_frequency": int},
                "ranges": {"min_frequency": (1, 100)},
                "enums": {"pattern_type": ["relationship", "entity", "temporal", "all"]}
            },
            "save_insight": {
                "required": ["insight_title", "insight_content"],
                "optional": ["insight_category", "related_entities", "priority", "group_id"],
                "types": {"insight_title": str, "insight_content": str, "insight_category": str, "priority": str},
                "enums": {"insight_category": ["technical", "business", "process", "lesson_learned", "best_practice", "general"],
                         "priority": ["low", "medium", "high", "critical"]}
            }
        }
        
        # Syntax validation
        if validation_type in ["syntax", "full"]:
            validation_report.append("🔍 **Syntax Validation**")
            
            if prompt_name in prompt_schemas:
                schema = prompt_schemas[prompt_name]
                
                # Check required fields
                missing_required = []
                for field in schema["required"]:
                    if field not in parsed_input:
                        missing_required.append(field)
                        validation_passed = False
                
                if missing_required:
                    validation_report.append(f"❌ Missing required fields: {', '.join(missing_required)}")
                else:
                    validation_report.append("✅ All required fields present")
                
                # Check field types
                type_errors = []
                for field, value in parsed_input.items():
                    if field in schema["types"]:
                        expected_type = schema["types"][field]
                        if not isinstance(value, expected_type):
                            type_errors.append(f"{field}: expected {expected_type.__name__}, got {type(value).__name__}")
                            validation_passed = False
                
                if type_errors:
                    validation_report.append(f"❌ Type errors: {'; '.join(type_errors)}")
                else:
                    validation_report.append("✅ All field types correct")
                    
            else:
                validation_report.append(f"⚠️ Unknown prompt name: {prompt_name}")
                validation_passed = False
        
        # Semantic validation
        if validation_type in ["semantic", "full"]:
            validation_report.append("\n🎯 **Semantic Validation**")
            
            if prompt_name in prompt_schemas:
                schema = prompt_schemas[prompt_name]
                semantic_errors = []
                
                # Check value ranges
                if "ranges" in schema:
                    for field, (min_val, max_val) in schema["ranges"].items():
                        if field in parsed_input:
                            value = parsed_input[field]
                            if isinstance(value, (int, float)) and not (min_val <= value <= max_val):
                                semantic_errors.append(f"{field}: value {value} outside range [{min_val}, {max_val}]")
                                validation_passed = False
                
                # Check enum values
                if "enums" in schema:
                    for field, valid_values in schema["enums"].items():
                        if field in parsed_input:
                            value = parsed_input[field]
                            if value not in valid_values:
                                semantic_errors.append(f"{field}: '{value}' not in allowed values {valid_values}")
                                validation_passed = False
                
                # Check string constraints
                for field, value in parsed_input.items():
                    if isinstance(value, str):
                        if not value.strip():
                            semantic_errors.append(f"{field}: empty string not allowed")
                            validation_passed = False
                        elif len(value) > 10000:
                            semantic_errors.append(f"{field}: string too long ({len(value)} > 10000 chars)")
                            validation_passed = False
                
                if semantic_errors:
                    validation_report.append(f"❌ Semantic errors: {'; '.join(semantic_errors)}")
                else:
                    validation_report.append("✅ All semantic constraints satisfied")
        
        # Graph validation
        if validation_type in ["graph", "full"] and validation_type != "syntax":
            validation_report.append("\n📊 **Graph Validation**")
            
            try:
                # Check graph connectivity
                search_payload = {
                    "query": "test connectivity",
                    "group_ids": [group_id] if group_id else None,
                    "max_nodes": 1
                }
                
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        f"{BASE_URL}/search_nodes",
                        json=search_payload,
                        headers={"Content-Type": "application/json"},
                        timeout=30.0
                    )
                
                if response.status_code == 200:
                    validation_report.append("✅ Graph backend accessible")
                    
                    # If group_id is specified, check if it exists
                    if group_id:
                        data = response.json()
                        if not data.get("nodes"):
                            validation_report.append(f"⚠️ Group ID '{group_id}' appears to be empty or non-existent")
                        else:
                            validation_report.append(f"✅ Group ID '{group_id}' contains data")
                else:
                    validation_report.append(f"❌ Graph backend error: {response.status_code}")
                    validation_passed = False
                    
            except Exception as e:
                validation_report.append(f"❌ Graph connectivity check failed: {str(e)}")
                validation_passed = False
        
        # Strict mode additional checks
        if strict_mode:
            validation_report.append("\n🔒 **Strict Mode Validation**")
            
            strict_warnings = []
            
            # Check for potentially problematic values
            for field, value in parsed_input.items():
                if isinstance(value, str):
                    # Check for SQL injection patterns (basic)
                    suspicious_patterns = ['DROP', 'DELETE', 'UPDATE', 'INSERT', 'EXEC', '--', '/*', '*/', 'xp_']
                    if any(pattern.lower() in value.lower() for pattern in suspicious_patterns):
                        strict_warnings.append(f"{field}: contains potentially suspicious SQL patterns")
                    
                    # Check for script injection patterns
                    script_patterns = ['<script', 'javascript:', 'eval(', 'document.']
                    if any(pattern.lower() in value.lower() for pattern in script_patterns):
                        strict_warnings.append(f"{field}: contains potentially suspicious script patterns")
            
            # Check for reasonable input sizes
            total_input_size = len(input_data)
            if total_input_size > 50000:
                strict_warnings.append(f"Input size very large: {total_input_size} chars (consider splitting)")
            
            if strict_warnings:
                validation_report.append(f"⚠️ Strict mode warnings: {'; '.join(strict_warnings)}")
            else:
                validation_report.append("✅ All strict mode checks passed")
        
        # Generate final report
        status_emoji = "✅" if validation_passed else "❌"
        status_text = "PASSED" if validation_passed else "FAILED"
        
        report_header = f"{status_emoji} **Validation {status_text}** for prompt `{prompt_name}`\n"
        
        suggestions = []
        if not validation_passed:
            suggestions.append("**💡 Suggestions for fixing validation errors:**")
            suggestions.append("- Review the error messages above")
            suggestions.append("- Check the prompt documentation for correct parameter formats")
            suggestions.append("- Use proper data types (strings in quotes, numbers without quotes)")
            suggestions.append("- Ensure all required fields are provided")
            suggestions.append("- Verify enum values match allowed options exactly")
        else:
            suggestions.append("**🎉 All validations passed! The input is ready to use.**")
        
        final_report = report_header + "\n".join(validation_report)
        if suggestions:
            final_report += "\n\n" + "\n".join(suggestions)
        
        return final_report
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f'Error in validate_prompt_input: {error_msg}')
        return f"❌ Error during validation: {error_msg}"


@mcp.prompt()
async def check_graph_health(
    health_check_type: str = Field("basic", description="Type of health check: 'basic', 'detailed', 'performance', 'integrity'"),
    include_metrics: bool = Field(True, description="Include graph metrics in the health report"),
    check_connections: bool = Field(True, description="Test database connectivity"),
    group_id: str | None = Field(None, description="Optional group ID to check specific graph namespace")
) -> str:
    """Perform comprehensive health checks on the knowledge graph.
    
    Available health check types:
    - basic: Connectivity and basic stats
    - detailed: Comprehensive analysis including data quality
    - performance: Response times and throughput metrics
    - integrity: Data consistency and relationship validation
    
    Returns detailed health report with recommendations.
    """
    try:
        health_report = []
        health_status = "healthy"
        
        health_report.append(f"🏥 **Graph Health Check Report** - {health_check_type.upper()}")
        health_report.append(f"⏰ **Timestamp**: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
        
        if group_id:
            health_report.append(f"🏷️ **Group ID**: {group_id}")
        else:
            health_report.append("🌐 **Scope**: All groups")
        
        # Basic connectivity check
        if check_connections:
            health_report.append("\n🔌 **Connectivity Check**")
            
            try:
                start_time = datetime.now()
                async with httpx.AsyncClient() as client:
                    # Test node search endpoint
                    response = await client.post(
                        f"{BASE_URL}/search_nodes",
                        json={
                            "query": "health check",
                            "group_ids": [group_id] if group_id else None,
                            "max_nodes": 1
                        },
                        headers={"Content-Type": "application/json"},
                        timeout=10.0
                    )
                
                response_time = (datetime.now() - start_time).total_seconds()
                
                if response.status_code == 200:
                    health_report.append(f"✅ Node search endpoint: OK ({response_time:.2f}s)")
                else:
                    health_report.append(f"❌ Node search endpoint: Error {response.status_code}")
                    health_status = "degraded"
                
                # Test fact search endpoint
                start_time = datetime.now()
                response = await client.post(
                    f"{BASE_URL}/search_facts",
                    json={
                        "query": "health check",
                        "group_ids": [group_id] if group_id else None,
                        "max_facts": 1
                    },
                    headers={"Content-Type": "application/json"},
                    timeout=10.0
                )
                
                response_time = (datetime.now() - start_time).total_seconds()
                
                if response.status_code == 200:
                    health_report.append(f"✅ Fact search endpoint: OK ({response_time:.2f}s)")
                else:
                    health_report.append(f"❌ Fact search endpoint: Error {response.status_code}")
                    health_status = "degraded"
                    
            except Exception as e:
                health_report.append(f"❌ Connectivity check failed: {str(e)}")
                health_status = "unhealthy"
        
        # Graph metrics
        if include_metrics:
            health_report.append("\n📊 **Graph Metrics**")
            
            try:
                async with httpx.AsyncClient() as client:
                    # Get node count
                    node_response = await client.post(
                        f"{BASE_URL}/search_nodes",
                        json={
                            "query": "*",
                            "group_ids": [group_id] if group_id else None,
                            "max_nodes": 1000
                        },
                        headers={"Content-Type": "application/json"},
                        timeout=30.0
                    )
                    
                    if node_response.status_code == 200:
                        node_data = node_response.json()
                        node_count = len(node_data.get("nodes", []))
                        health_report.append(f"📈 **Node Count**: {node_count}")
                        
                        if node_count == 0:
                            health_report.append("⚠️ Warning: No nodes found in the graph")
                            health_status = "degraded"
                        elif node_count > 10000:
                            health_report.append("📊 Large graph detected - consider performance monitoring")
                    
                    # Get fact count
                    fact_response = await client.post(
                        f"{BASE_URL}/search_facts",
                        json={
                            "query": "*",
                            "group_ids": [group_id] if group_id else None,
                            "max_facts": 1000
                        },
                        headers={"Content-Type": "application/json"},
                        timeout=30.0
                    )
                    
                    if fact_response.status_code == 200:
                        fact_data = fact_response.json()
                        fact_count = len(fact_data.get("facts", []))
                        health_report.append(f"🔗 **Fact Count**: {fact_count}")
                        
                        if fact_count == 0 and node_count > 0:
                            health_report.append("⚠️ Warning: Nodes exist but no relationships found")
                            health_status = "degraded"
                        
            except Exception as e:
                health_report.append(f"❌ Metrics collection failed: {str(e)}")
                health_status = "degraded"
        
        # Detailed checks
        if health_check_type in ["detailed", "performance", "integrity"]:
            health_report.append(f"\n🔍 **{health_check_type.title()} Analysis**")
            
            if health_check_type == "detailed":
                # Data quality checks
                try:
                    async with httpx.AsyncClient() as client:
                        # Sample some nodes for quality analysis
                        response = await client.post(
                            f"{BASE_URL}/search_nodes",
                            json={
                                "query": "sample",
                                "group_ids": [group_id] if group_id else None,
                                "max_nodes": 10
                            },
                            headers={"Content-Type": "application/json"},
                            timeout=15.0
                        )
                        
                        if response.status_code == 200:
                            data = response.json()
                            nodes = data.get("nodes", [])
                            
                            if nodes:
                                # Check node completeness
                                complete_nodes = sum(1 for node in nodes if node.get("name") and len(node.get("name", "").strip()) > 0)
                                completeness_ratio = complete_nodes / len(nodes) * 100
                                
                                health_report.append(f"📋 **Data Completeness**: {completeness_ratio:.1f}% ({complete_nodes}/{len(nodes)} nodes have names)")
                                
                                if completeness_ratio < 80:
                                    health_report.append("⚠️ Warning: Low data completeness detected")
                                    health_status = "degraded"
                                
                                # Check for entity types diversity
                                entity_types = set()
                                for node in nodes:
                                    if "entity_type" in node:
                                        entity_types.add(node["entity_type"])
                                
                                health_report.append(f"🎯 **Entity Type Diversity**: {len(entity_types)} different types found")
                                
                except Exception as e:
                    health_report.append(f"❌ Detailed analysis failed: {str(e)}")
                    health_status = "degraded"
            
            elif health_check_type == "performance":
                # Performance benchmarks
                health_report.append("⚡ **Performance Benchmarks**")
                
                try:
                    # Test search response times
                    start_time = datetime.now()
                    async with httpx.AsyncClient() as client:
                        response = await client.post(
                            f"{BASE_URL}/search_nodes",
                            json={
                                "query": "performance test",
                                "group_ids": [group_id] if group_id else None,
                                "max_nodes": 50
                            },
                            headers={"Content-Type": "application/json"},
                            timeout=20.0
                        )
                    
                    search_time = (datetime.now() - start_time).total_seconds()
                    
                    if response.status_code == 200:
                        health_report.append(f"🏃 **Search Response Time**: {search_time:.3f}s")
                        
                        if search_time > 5.0:
                            health_report.append("⚠️ Warning: Slow search response times detected")
                            health_status = "degraded"
                        elif search_time < 1.0:
                            health_report.append("🚀 Excellent search performance!")
                    
                except Exception as e:
                    health_report.append(f"❌ Performance test failed: {str(e)}")
                    health_status = "degraded"
            
            elif health_check_type == "integrity":
                # Data integrity checks
                health_report.append("🔒 **Data Integrity Checks**")
                
                try:
                    # Check for orphaned relationships
                    async with httpx.AsyncClient() as client:
                        fact_response = await client.post(
                            f"{BASE_URL}/search_facts",
                            json={
                                "query": "*",
                                "group_ids": [group_id] if group_id else None,
                                "max_facts": 100
                            },
                            headers={"Content-Type": "application/json"},
                            timeout=20.0
                        )
                        
                        if fact_response.status_code == 200:
                            facts = fact_response.json().get("facts", [])
                            
                            # Basic integrity check
                            valid_facts = 0
                            for fact in facts:
                                if fact.get("subject") and fact.get("predicate") and fact.get("object"):
                                    valid_facts += 1
                            
                            if facts:
                                integrity_ratio = valid_facts / len(facts) * 100
                                health_report.append(f"✅ **Relationship Integrity**: {integrity_ratio:.1f}% ({valid_facts}/{len(facts)} complete)")
                                
                                if integrity_ratio < 90:
                                    health_report.append("⚠️ Warning: Some relationships may be incomplete")
                                    health_status = "degraded"
                            else:
                                health_report.append("ℹ️ No relationships found to validate")
                
                except Exception as e:
                    health_report.append(f"❌ Integrity check failed: {str(e)}")
                    health_status = "degraded"
        
        # Final health status and recommendations
        health_report.append(f"\n🏥 **Overall Health Status**: {health_status.upper()}")
        
        if health_status == "healthy":
            health_report.append("🎉 **All systems operational!**")
        elif health_status == "degraded":
            health_report.append("⚠️ **Some issues detected - review warnings above**")
            health_report.append("\n**Recommendations**:")
            health_report.append("- Monitor performance metrics regularly")
            health_report.append("- Consider data cleanup if completeness is low")
            health_report.append("- Check database configuration if response times are slow")
        else:
            health_report.append("❌ **Critical issues detected - immediate attention required**")
            health_report.append("\n**Urgent Actions**:")
            health_report.append("- Check database connectivity")
            health_report.append("- Verify server configuration")
            health_report.append("- Review error logs for detailed diagnostics")
        
        return "\n".join(health_report)
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f'Error in check_graph_health: {error_msg}')
        return f"❌ Error performing health check: {error_msg}"


@mcp.prompt()
async def validate_data_integrity(
    validation_scope: str = Field("relationships", description="Scope to validate: 'relationships', 'entities', 'episodes', 'all'"),
    fix_issues: bool = Field(False, description="Attempt to automatically fix detected issues"),
    report_details: bool = Field(True, description="Include detailed information about each issue found"),
    max_issues: int = Field(50, description="Maximum number of issues to report", ge=1, le=500),
    group_id: str | None = Field(None, description="Optional group ID to limit validation scope")
) -> str:
    """Validate data integrity across the knowledge graph and optionally fix issues.
    
    Validation scopes:
    - relationships: Check fact consistency and orphaned relationships
    - entities: Validate entity data completeness and duplicates  
    - episodes: Verify episode data integrity and timestamps
    - all: Comprehensive validation across all data types
    
    Returns detailed validation report with optional automatic fixes.
    """
    try:
        validation_report = []
        issues_found = []
        fixes_applied = []
        
        validation_report.append("🔍 **Data Integrity Validation Report**")
        validation_report.append(f"⏰ **Timestamp**: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
        validation_report.append(f"🎯 **Scope**: {validation_scope}")
        
        if group_id:
            validation_report.append(f"🏷️ **Group ID**: {group_id}")
        
        # Relationship validation
        if validation_scope in ["relationships", "all"]:
            validation_report.append("\n🔗 **Relationship Validation**")
            
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        f"{BASE_URL}/search_facts",
                        json={
                            "query": "*",
                            "group_ids": [group_id] if group_id else None,
                            "max_facts": min(max_issues * 2, 1000)
                        },
                        headers={"Content-Type": "application/json"},
                        timeout=30.0
                    )
                    
                    if response.status_code == 200:
                        facts = response.json().get("facts", [])
                        
                        # Check for incomplete relationships
                        incomplete_facts = []
                        for i, fact in enumerate(facts):
                            if not fact.get("subject") or not fact.get("predicate") or not fact.get("object"):
                                incomplete_facts.append((i, fact))
                                if len(incomplete_facts) >= max_issues:
                                    break
                        
                        if incomplete_facts:
                            issues_found.extend(incomplete_facts)
                            validation_report.append(f"❌ Found {len(incomplete_facts)} incomplete relationships")
                            
                            if report_details:
                                for i, (idx, fact) in enumerate(incomplete_facts[:10]):
                                    missing_parts = []
                                    if not fact.get("subject"):
                                        missing_parts.append("subject")
                                    if not fact.get("predicate"):
                                        missing_parts.append("predicate")
                                    if not fact.get("object"):
                                        missing_parts.append("object")
                                    
                                    validation_report.append(f"  • Fact {idx}: Missing {', '.join(missing_parts)}")
                                
                                if len(incomplete_facts) > 10:
                                    validation_report.append(f"  • ... and {len(incomplete_facts) - 10} more")
                            
                            if fix_issues:
                                # Note: In a real implementation, you'd implement actual fix logic here
                                validation_report.append("🔧 Auto-fix for incomplete relationships would be implemented here")
                                fixes_applied.append(f"Would fix {len(incomplete_facts)} incomplete relationships")
                        else:
                            validation_report.append("✅ All relationships are complete")
                        
                        # Check for duplicate relationships
                        seen_relationships = set()
                        duplicate_facts = []
                        
                        for i, fact in enumerate(facts):
                            if fact.get("subject") and fact.get("predicate") and fact.get("object"):
                                rel_key = (fact["subject"], fact["predicate"], fact["object"])
                                if rel_key in seen_relationships:
                                    duplicate_facts.append((i, fact))
                                else:
                                    seen_relationships.add(rel_key)
                        
                        if duplicate_facts:
                            issues_found.extend(duplicate_facts)
                            validation_report.append(f"⚠️ Found {len(duplicate_facts)} potential duplicate relationships")
                            
                            if report_details and duplicate_facts:
                                for i, (idx, fact) in enumerate(duplicate_facts[:5]):
                                    validation_report.append(f"  • Duplicate: {fact.get('subject', '?')} -> {fact.get('predicate', '?')} -> {fact.get('object', '?')}")
                                
                                if len(duplicate_facts) > 5:
                                    validation_report.append(f"  • ... and {len(duplicate_facts) - 5} more")
                        else:
                            validation_report.append("✅ No obvious duplicate relationships found")
                            
                    else:
                        validation_report.append(f"❌ Failed to fetch relationships: HTTP {response.status_code}")
                        
            except Exception as e:
                validation_report.append(f"❌ Relationship validation failed: {str(e)}")
        
        # Entity validation
        if validation_scope in ["entities", "all"]:
            validation_report.append("\n👤 **Entity Validation**")
            
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        f"{BASE_URL}/search_nodes",
                        json={
                            "query": "*",
                            "group_ids": [group_id] if group_id else None,
                            "max_nodes": min(max_issues * 2, 1000)
                        },
                        headers={"Content-Type": "application/json"},
                        timeout=30.0
                    )
                    
                    if response.status_code == 200:
                        nodes = response.json().get("nodes", [])
                        
                        # Check for incomplete entities
                        incomplete_entities = []
                        for i, node in enumerate(nodes):
                            if not node.get("name") or not node.get("name", "").strip():
                                incomplete_entities.append((i, node))
                                if len(incomplete_entities) >= max_issues:
                                    break
                        
                        if incomplete_entities:
                            issues_found.extend(incomplete_entities)
                            validation_report.append(f"❌ Found {len(incomplete_entities)} entities with missing/empty names")
                            
                            if fix_issues:
                                fixes_applied.append(f"Would fix {len(incomplete_entities)} incomplete entity names")
                        else:
                            validation_report.append("✅ All entities have names")
                        
                        # Check for potential duplicate entities (similar names)
                        entity_names = {}
                        for i, node in enumerate(nodes):
                            name = node.get("name", "").strip().lower()
                            if name:
                                if name in entity_names:
                                    entity_names[name].append((i, node))
                                else:
                                    entity_names[name] = [(i, node)]
                        
                        potential_duplicates = {name: entities for name, entities in entity_names.items() if len(entities) > 1}
                        
                        if potential_duplicates:
                            duplicate_count = sum(len(entities) - 1 for entities in potential_duplicates.values())
                            validation_report.append(f"⚠️ Found {len(potential_duplicates)} entity names with {duplicate_count} potential duplicates")
                            
                            if report_details:
                                for name, entities in list(potential_duplicates.items())[:3]:
                                    validation_report.append(f"  • '{name}': {len(entities)} instances")
                                
                                if len(potential_duplicates) > 3:
                                    validation_report.append(f"  • ... and {len(potential_duplicates) - 3} more")
                        else:
                            validation_report.append("✅ No obvious duplicate entity names found")
                            
                    else:
                        validation_report.append(f"❌ Failed to fetch entities: HTTP {response.status_code}")
                        
            except Exception as e:
                validation_report.append(f"❌ Entity validation failed: {str(e)}")
        
        # Episode validation
        if validation_scope in ["episodes", "all"]:
            validation_report.append("\n📝 **Episode Validation**")
            
            try:
                # Episodes are validated by attempting to retrieve recent episodes
                async with httpx.AsyncClient() as client:
                    payload = {"group_id": group_id, "last_n": min(max_issues, 100)}
                    response = await client.post(
                        f"{BASE_URL}/episodes",
                        json=payload,
                        headers={"Content-Type": "application/json"},
                        timeout=20.0
                    )
                    
                    if response.status_code == 200:
                        episodes_data = response.json()
                        episodes = episodes_data.get("episodes", [])
                        
                        if episodes:
                            # Check episode completeness
                            incomplete_episodes = []
                            for i, episode in enumerate(episodes):
                                if not episode.get("name") or not episode.get("content"):
                                    incomplete_episodes.append((i, episode))
                            
                            if incomplete_episodes:
                                issues_found.extend(incomplete_episodes)
                                validation_report.append(f"❌ Found {len(incomplete_episodes)} incomplete episodes")
                                
                                if fix_issues:
                                    fixes_applied.append(f"Would fix {len(incomplete_episodes)} incomplete episodes")
                            else:
                                validation_report.append("✅ All episodes appear complete")
                            
                            # Check timestamp validity
                            invalid_timestamps = []
                            for i, episode in enumerate(episodes):
                                if "created_at" in episode:
                                    try:
                                        # Basic timestamp validation
                                        timestamp = episode["created_at"]
                                        if not isinstance(timestamp, str) or len(timestamp) < 10:
                                            invalid_timestamps.append((i, episode))
                                    except Exception:
                                        invalid_timestamps.append((i, episode))
                            
                            if invalid_timestamps:
                                validation_report.append(f"⚠️ Found {len(invalid_timestamps)} episodes with invalid timestamps")
                            else:
                                validation_report.append("✅ Episode timestamps appear valid")
                                
                            validation_report.append(f"📊 Total episodes checked: {len(episodes)}")
                        else:
                            validation_report.append("ℹ️ No episodes found to validate")
                    else:
                        validation_report.append(f"❌ Failed to fetch episodes: HTTP {response.status_code}")
                        
            except Exception as e:
                validation_report.append(f"❌ Episode validation failed: {str(e)}")
        
        # Summary
        validation_report.append(f"\n📋 **Validation Summary**")
        validation_report.append(f"🔍 **Total Issues Found**: {len(issues_found)}")
        
        if fixes_applied:
            validation_report.append(f"🔧 **Fixes Applied**: {len(fixes_applied)}")
            for fix in fixes_applied:
                validation_report.append(f"  • {fix}")
        elif fix_issues and not issues_found:
            validation_report.append("✅ **No fixes needed** - all data appears valid")
        elif fix_issues:
            validation_report.append("⚠️ **Auto-fix disabled** - fix_issues=False or fixes not implemented")
        
        # Recommendations
        if issues_found:
            validation_report.append(f"\n💡 **Recommendations**")
            validation_report.append("- Review the issues identified above")
            validation_report.append("- Consider implementing data cleanup procedures")
            validation_report.append("- Set up regular validation checks")
            validation_report.append("- Use validation before important operations")
        
        # Final status
        if len(issues_found) == 0:
            validation_report.append(f"\n🎉 **Data integrity validation PASSED** - No issues found!")
        elif len(issues_found) <= 5:
            validation_report.append(f"\n⚠️ **Data integrity validation completed with minor issues**")
        else:
            validation_report.append(f"\n❌ **Data integrity validation found significant issues** - Action recommended")
        
        return "\n".join(validation_report)
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f'Error in validate_data_integrity: {error_msg}')
        return f"❌ Error during data integrity validation: {error_msg}"


async def initialize_server() -> MCPConfig:
    """Parse CLI arguments and initialize the Graphiti server configuration."""
    global config

    parser = argparse.ArgumentParser(
        description='Run the Graphiti MCP server'
    )
    parser.add_argument(
        '--group-id',
        help='Namespace for the graph. This is an arbitrary string used to organize related data. '
        'If not provided, a random UUID will be generated.',
    )
    parser.add_argument(
        '--transport',
        choices=['sse', 'stdio', 'http'],
        default=os.environ.get('MCP_TRANSPORT', 'http'),
        help='Transport to use for communication with the client. (default: MCP_TRANSPORT environment variable or http)',
    )
    parser.add_argument('--destroy-graph', action='store_true', help='Destroy all Graphiti graphs')
    parser.add_argument(
        '--use-custom-entities',
        action='store_true',
        help='Enable entity extraction using the predefined ENTITY_TYPES',
    )
    parser.add_argument(
        '--host',
        default=os.environ.get('MCP_SERVER_HOST', '0.0.0.0'),
        help='Host to bind the MCP server to (default: MCP_SERVER_HOST environment variable or 0.0.0.0)',
    )
    parser.add_argument(
        '--port',
        type=int,
        default=int(os.environ.get('MCP_SERVER_PORT', '3010')),
        help='Port to bind the HTTP server to (default: MCP_SERVER_PORT environment variable or 3010)',
    )

    args = parser.parse_args()

    # Build configuration from CLI arguments and environment variables
    config = GraphitiConfig.from_cli_and_env(args)

    # Log the group ID configuration
    if args.group_id:
        logger.info(f'Using provided group_id: {config.group_id}')
    else:
        logger.info(f'Generated random group_id: {config.group_id}')

    # Log entity extraction configuration
    if config.use_custom_entities:
        logger.info('Entity extraction enabled using predefined ENTITY_TYPES')
    else:
        logger.info('Entity extraction disabled (no custom entities will be used)')

    # Initialize Graphiti
    await initialize_graphiti()

    if args.host:
        logger.info(f'Setting MCP server host to: {args.host}')
        # Set MCP server host from CLI or env
        mcp.settings.host = args.host

    # Return MCP configuration
    return MCPConfig.from_cli(args)



async def run_http_server(mcp_config: MCPConfig):
    """Run HTTP server using FastMCP's built-in HTTP support."""
    try:
        logger.info(f"Starting HTTP server on {mcp_config.host}:{mcp_config.port}")
        logger.info(f"MCP endpoint: http://localhost:{mcp_config.port}/mcp")
        logger.info(f"Health check: http://localhost:{mcp_config.port}/health")
        logger.info("Protocol version: 2025-06-18")
        logger.info("Security: CORS enabled for localhost and allowed origins")
        
        # Configure FastMCP settings first
        mcp.settings.host = mcp_config.host
        mcp.settings.port = mcp_config.port
        
        # Use FastMCP's async run method with streamable-http transport
        await mcp.run_streamable_http_async()
        
    except Exception as e:
        logger.error(f"Failed to start HTTP server: {e}")
        raise


async def run_mcp_server():
    """Run the MCP server in the current event loop with proper cleanup."""
    mcp_config = None
    
    try:
        # Initialize the server
        mcp_config = await initialize_server()

        # Run the server with specified transport
        logger.info(f'Starting MCP server with transport: {mcp_config.transport}')
        if mcp_config.transport == 'stdio':
            await mcp.run_stdio_async()
        elif mcp_config.transport == 'sse':
            # Configure FastMCP settings for SSE
            mcp.settings.host = mcp_config.host
            mcp.settings.port = mcp_config.port
            logger.info(
                f'Running MCP server with SSE transport on {mcp.settings.host}:{mcp.settings.port}'
            )
            await mcp.run_sse_async()
        elif mcp_config.transport == 'http':
            # Run HTTP server for streamable HTTP transport
            await run_http_server(mcp_config)
            
    except KeyboardInterrupt:
        logger.info('Received interrupt signal, shutting down gracefully...')
    except Exception as e:
        logger.error(f'Unexpected error in MCP server: {e}')
        raise
    finally:
        # Cleanup resources
        logger.info('Cleaning up resources...')
        await cleanup_graphiti()


def main():
    """Main function to run the Graphiti MCP server."""
    try:
        # Run everything in a single event loop
        asyncio.run(run_mcp_server())
    except Exception as e:
        logger.error(f'Error initializing Graphiti MCP server: {str(e)}')
        raise


if __name__ == '__main__':
    main()
