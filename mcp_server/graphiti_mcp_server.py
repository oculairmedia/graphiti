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
from graphiti_core.embedder.azure_openai import AzureOpenAIEmbedderClient
from graphiti_core.embedder.client import EmbedderClient
from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
from graphiti_core.llm_client.azure_openai_client import AzureOpenAILLMClient
from graphiti_core.llm_client.client import LLMClient
from graphiti_core.llm_client.openai_client import OpenAIClient
from mcp.server.fastmcp import FastMCP
from openai import AsyncAzureOpenAI
from pydantic import BaseModel, Field

load_dotenv()


DEFAULT_LLM_MODEL = 'gpt-4.1-mini'
SMALL_LLM_MODEL = 'gpt-4.1-nano'
DEFAULT_EMBEDDER_MODEL = 'text-embedding-3-small'

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


# Type definitions for API responses
class ErrorResponse(TypedDict):
    error: str


class SuccessResponse(TypedDict):
    message: str


class NodeResult(TypedDict):
    uuid: str
    name: str
    summary: str
    labels: list[str]
    group_id: str
    created_at: str
    attributes: dict[str, Any]


class NodeSearchResponse(TypedDict):
    message: str
    nodes: list[NodeResult]


class FactSearchResponse(TypedDict):
    message: str
    facts: list[dict[str, Any]]


class EpisodeSearchResponse(TypedDict):
    message: str
    episodes: list[dict[str, Any]]


class StatusResponse(TypedDict):
    status: str
    message: str


def create_azure_credential_token_provider() -> Callable[[], str]:
    credential = DefaultAzureCredential()
    token_provider = get_bearer_token_provider(
        credential, 'https://cognitiveservices.azure.com/.default'
    )
    return token_provider


# Server configuration classes
# The configuration system has a hierarchy:
# - GraphitiConfig is the top-level configuration
#   - LLMConfig handles all OpenAI/LLM related settings
#   - EmbedderConfig manages embedding settings
#   - FalkorDBConfig manages database connection details
#   - Various other settings like group_id and feature flags
# Configuration values are loaded from:
# 1. Default values in the class definitions
# 2. Environment variables (loaded via load_dotenv())
# 3. Command line arguments (which override environment variables)
class GraphitiLLMConfig(BaseModel):
    """Configuration for the LLM client.

    Centralizes all LLM-specific configuration parameters including API keys and model selection.
    """

    api_key: str | None = None
    model: str = DEFAULT_LLM_MODEL
    small_model: str = SMALL_LLM_MODEL
    temperature: float = 0.0
    azure_openai_endpoint: str | None = None
    azure_openai_deployment_name: str | None = None
    azure_openai_api_version: str | None = None
    azure_openai_use_managed_identity: bool = False

    @classmethod
    def from_env(cls) -> 'GraphitiLLMConfig':
        """Create LLM configuration from environment variables."""
        # Get model from environment, or use default if not set or empty
        model_env = os.environ.get('MODEL_NAME', '')
        model = model_env if model_env.strip() else DEFAULT_LLM_MODEL

        # Get small_model from environment, or use default if not set or empty
        small_model_env = os.environ.get('SMALL_MODEL_NAME', '')
        small_model = small_model_env if small_model_env.strip() else SMALL_LLM_MODEL

        azure_openai_endpoint = os.environ.get('AZURE_OPENAI_ENDPOINT', None)
        azure_openai_api_version = os.environ.get('AZURE_OPENAI_API_VERSION', None)
        azure_openai_deployment_name = os.environ.get('AZURE_OPENAI_DEPLOYMENT_NAME', None)
        azure_openai_use_managed_identity = (
            os.environ.get('AZURE_OPENAI_USE_MANAGED_IDENTITY', 'false').lower() == 'true'
        )

        if azure_openai_endpoint is None:
            # Setup for OpenAI API
            # Log if empty model was provided
            if model_env == '':
                logger.debug(
                    f'MODEL_NAME environment variable not set, using default: {DEFAULT_LLM_MODEL}'
                )
            elif not model_env.strip():
                logger.warning(
                    f'Empty MODEL_NAME environment variable, using default: {DEFAULT_LLM_MODEL}'
                )

            return cls(
                api_key=os.environ.get('OPENAI_API_KEY'),
                model=model,
                small_model=small_model,
                temperature=float(os.environ.get('LLM_TEMPERATURE', '0.0')),
            )
        else:
            # Setup for Azure OpenAI API
            # Log if empty deployment name was provided
            if azure_openai_deployment_name is None:
                logger.error('AZURE_OPENAI_DEPLOYMENT_NAME environment variable not set')

                raise ValueError('AZURE_OPENAI_DEPLOYMENT_NAME environment variable not set')
            if not azure_openai_use_managed_identity:
                # api key
                api_key = os.environ.get('OPENAI_API_KEY', None)
            else:
                # Managed identity
                api_key = None

            return cls(
                azure_openai_use_managed_identity=azure_openai_use_managed_identity,
                azure_openai_endpoint=azure_openai_endpoint,
                api_key=api_key,
                azure_openai_api_version=azure_openai_api_version,
                azure_openai_deployment_name=azure_openai_deployment_name,
                model=model,
                small_model=small_model,
                temperature=float(os.environ.get('LLM_TEMPERATURE', '0.0')),
            )

    @classmethod
    def from_cli_and_env(cls, args: argparse.Namespace) -> 'GraphitiLLMConfig':
        """Create LLM configuration from CLI arguments, falling back to environment variables."""
        # Start with environment-based config
        config = cls.from_env()

        # CLI arguments override environment variables when provided
        if hasattr(args, 'model') and args.model:
            # Only use CLI model if it's not empty
            if args.model.strip():
                config.model = args.model
            else:
                # Log that empty model was provided and default is used
                logger.warning(f'Empty model name provided, using default: {DEFAULT_LLM_MODEL}')

        if hasattr(args, 'small_model') and args.small_model:
            if args.small_model.strip():
                config.small_model = args.small_model
            else:
                logger.warning(f'Empty small_model name provided, using default: {SMALL_LLM_MODEL}')

        if hasattr(args, 'temperature') and args.temperature is not None:
            config.temperature = args.temperature

        return config

    def create_client(self) -> LLMClient:
        """Create an LLM client based on this configuration.

        Returns:
            LLMClient instance
        """

        if self.azure_openai_endpoint is not None:
            # Azure OpenAI API setup
            if self.azure_openai_use_managed_identity:
                # Use managed identity for authentication
                token_provider = create_azure_credential_token_provider()
                return AzureOpenAILLMClient(
                    azure_client=AsyncAzureOpenAI(
                        azure_endpoint=self.azure_openai_endpoint,
                        azure_deployment=self.azure_openai_deployment_name,
                        api_version=self.azure_openai_api_version,
                        azure_ad_token_provider=token_provider,
                    ),
                    config=LLMConfig(
                        api_key=self.api_key,
                        model=self.model,
                        small_model=self.small_model,
                        temperature=self.temperature,
                    ),
                )
            elif self.api_key:
                # Use API key for authentication
                return AzureOpenAILLMClient(
                    azure_client=AsyncAzureOpenAI(
                        azure_endpoint=self.azure_openai_endpoint,
                        azure_deployment=self.azure_openai_deployment_name,
                        api_version=self.azure_openai_api_version,
                        api_key=self.api_key,
                    ),
                    config=LLMConfig(
                        api_key=self.api_key,
                        model=self.model,
                        small_model=self.small_model,
                        temperature=self.temperature,
                    ),
                )
            else:
                raise ValueError('OPENAI_API_KEY must be set when using Azure OpenAI API')

        if not self.api_key:
            raise ValueError('OPENAI_API_KEY must be set when using OpenAI API')

        llm_client_config = LLMConfig(
            api_key=self.api_key, model=self.model, small_model=self.small_model
        )

        # Set temperature
        llm_client_config.temperature = self.temperature

        return OpenAIClient(config=llm_client_config)


class GraphitiEmbedderConfig(BaseModel):
    """Configuration for the embedder client.

    Centralizes all embedding-related configuration parameters.
    """

    model: str = DEFAULT_EMBEDDER_MODEL
    api_key: str | None = None
    azure_openai_endpoint: str | None = None
    azure_openai_deployment_name: str | None = None
    azure_openai_api_version: str | None = None
    azure_openai_use_managed_identity: bool = False

    @classmethod
    def from_env(cls) -> 'GraphitiEmbedderConfig':
        """Create embedder configuration from environment variables."""

        # Get model from environment, or use default if not set or empty
        model_env = os.environ.get('EMBEDDER_MODEL_NAME', '')
        model = model_env if model_env.strip() else DEFAULT_EMBEDDER_MODEL

        azure_openai_endpoint = os.environ.get('AZURE_OPENAI_EMBEDDING_ENDPOINT', None)
        azure_openai_api_version = os.environ.get('AZURE_OPENAI_EMBEDDING_API_VERSION', None)
        azure_openai_deployment_name = os.environ.get(
            'AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME', None
        )
        azure_openai_use_managed_identity = (
            os.environ.get('AZURE_OPENAI_USE_MANAGED_IDENTITY', 'false').lower() == 'true'
        )
        if azure_openai_endpoint is not None:
            # Setup for Azure OpenAI API
            # Log if empty deployment name was provided
            azure_openai_deployment_name = os.environ.get(
                'AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME', None
            )
            if azure_openai_deployment_name is None:
                logger.error('AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME environment variable not set')

                raise ValueError(
                    'AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME environment variable not set'
                )

            if not azure_openai_use_managed_identity:
                # api key
                api_key = os.environ.get('AZURE_OPENAI_EMBEDDING_API_KEY', None) or os.environ.get(
                    'OPENAI_API_KEY', None
                )
            else:
                # Managed identity
                api_key = None

            return cls(
                azure_openai_use_managed_identity=azure_openai_use_managed_identity,
                azure_openai_endpoint=azure_openai_endpoint,
                api_key=api_key,
                azure_openai_api_version=azure_openai_api_version,
                azure_openai_deployment_name=azure_openai_deployment_name,
            )
        else:
            return cls(
                model=model,
                api_key=os.environ.get('OPENAI_API_KEY'),
            )

    def create_client(self) -> EmbedderClient | None:
        if self.azure_openai_endpoint is not None:
            # Azure OpenAI API setup
            if self.azure_openai_use_managed_identity:
                # Use managed identity for authentication
                token_provider = create_azure_credential_token_provider()
                return AzureOpenAIEmbedderClient(
                    azure_client=AsyncAzureOpenAI(
                        azure_endpoint=self.azure_openai_endpoint,
                        azure_deployment=self.azure_openai_deployment_name,
                        api_version=self.azure_openai_api_version,
                        azure_ad_token_provider=token_provider,
                    ),
                    model=self.model,
                )
            elif self.api_key:
                # Use API key for authentication
                return AzureOpenAIEmbedderClient(
                    azure_client=AsyncAzureOpenAI(
                        azure_endpoint=self.azure_openai_endpoint,
                        azure_deployment=self.azure_openai_deployment_name,
                        api_version=self.azure_openai_api_version,
                        api_key=self.api_key,
                    ),
                    model=self.model,
                )
            else:
                logger.error('OPENAI_API_KEY must be set when using Azure OpenAI API')
                return None
        else:
            # OpenAI API setup
            if not self.api_key:
                return None

            embedder_config = OpenAIEmbedderConfig(api_key=self.api_key, embedding_model=self.model)

            return OpenAIEmbedder(config=embedder_config)


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

    llm: GraphitiLLMConfig = Field(default_factory=GraphitiLLMConfig)
    embedder: GraphitiEmbedderConfig = Field(default_factory=GraphitiEmbedderConfig)
    api: GraphAPIConfig = Field(default_factory=GraphAPIConfig)
    group_id: str | None = None
    use_custom_entities: bool = False
    destroy_graph: bool = False

    @classmethod
    def from_env(cls) -> 'GraphitiConfig':
        """Create a configuration instance from environment variables."""
        return cls(
            llm=GraphitiLLMConfig.from_env(),
            embedder=GraphitiEmbedderConfig.from_env(),
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

        # Update LLM config using CLI args
        config.llm = GraphitiLLMConfig.from_cli_and_env(args)

        return config


class MCPConfig(BaseModel):
    """Configuration for MCP server."""

    transport: str = 'sse'  # Default to SSE transport
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


async def initialize_graphiti():
    """Initialize the HTTP client for FastAPI server."""
    global http_client, config

    try:
        # Initialize HTTP client for FastAPI server
        http_client = httpx.AsyncClient(base_url=config.api.base_url, timeout=30.0)

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

    except Exception as e:
        logger.error(f'Failed to initialize connection to FastAPI server: {str(e)}')
        raise


# Removed queue processing functions - now using direct FastAPI calls


@mcp.tool()
async def add_memory(
    name: str,
    episode_body: str,
    group_id: str | None = None,
    source: str = 'text',
    source_description: str = '',
    uuid: str | None = None,
) -> SuccessResponse | ErrorResponse:
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
        return ErrorResponse(error='HTTP client not initialized')

    try:
        # Use the provided group_id or fall back to the default from config
        effective_group_id = group_id if group_id is not None else config.group_id
        group_id_str = str(effective_group_id) if effective_group_id is not None else 'default'

        # Prepare request payload
        payload = {
            'name': name,
            'episode_body': episode_body,
            'group_id': group_id_str,
            'source': source,
            'source_description': source_description,
        }

        if uuid:
            payload['uuid'] = uuid

        # Send request to FastAPI server
        response = await http_client.post('/messages', json=payload)
        response.raise_for_status()

        result = response.json()
        logger.info(f"Episode '{name}' added successfully via FastAPI")

        return SuccessResponse(message=f"Episode '{name}' added successfully")

    except httpx.HTTPStatusError as e:
        error_msg = f'HTTP error {e.response.status_code}: {e.response.text}'
        logger.error(f'Error adding episode via FastAPI: {error_msg}')
        return ErrorResponse(error=f'Error adding episode: {error_msg}')
    except Exception as e:
        error_msg = str(e)
        logger.error(f'Error adding episode: {error_msg}')
        return ErrorResponse(error=f'Error adding episode: {error_msg}')


@mcp.tool()
async def search_memory_nodes(
    query: str,
    group_ids: list[str] | None = None,
    max_nodes: int = 10,
    center_node_uuid: str | None = None,
    entity: str = '',
) -> NodeSearchResponse | ErrorResponse:
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
        return ErrorResponse(error='HTTP client not initialized')

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

        return NodeSearchResponse(message='Nodes retrieved successfully', nodes=nodes)

    except httpx.HTTPStatusError as e:
        error_msg = f'HTTP error {e.response.status_code}: {e.response.text}'
        logger.error(f'Error searching nodes via FastAPI: {error_msg}')
        return ErrorResponse(error=f'Error searching nodes: {error_msg}')
    except Exception as e:
        error_msg = str(e)
        logger.error(f'Error searching nodes: {error_msg}')
        return ErrorResponse(error=f'Error searching nodes: {error_msg}')


@mcp.tool()
async def search_memory_facts(
    query: str,
    group_ids: list[str] | None = None,
    max_facts: int = 10,
    center_node_uuid: str | None = None,
) -> FactSearchResponse | ErrorResponse:
    """Search the graph memory for relevant facts via FastAPI server.

    Args:
        query: The search query
        group_ids: Optional list of group IDs to filter results
        max_facts: Maximum number of facts to return (default: 10)
        center_node_uuid: Optional UUID of a node to center the search around
    """
    global http_client

    if http_client is None:
        return ErrorResponse(error='HTTP client not initialized')

    try:
        # Validate max_facts parameter
        if max_facts <= 0:
            return ErrorResponse(error='max_facts must be a positive integer')

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

        return FactSearchResponse(message='Facts retrieved successfully', facts=facts)

    except httpx.HTTPStatusError as e:
        error_msg = f'HTTP error {e.response.status_code}: {e.response.text}'
        logger.error(f'Error searching facts via FastAPI: {error_msg}')
        return ErrorResponse(error=f'Error searching facts: {error_msg}')
    except Exception as e:
        error_msg = str(e)
        logger.error(f'Error searching facts: {error_msg}')
        return ErrorResponse(error=f'Error searching facts: {error_msg}')


@mcp.tool()
async def delete_entity_edge(uuid: str) -> SuccessResponse | ErrorResponse:
    """Delete an entity edge from the graph memory via FastAPI server.

    Args:
        uuid: UUID of the entity edge to delete
    """
    global http_client

    if http_client is None:
        return ErrorResponse(error='HTTP client not initialized')

    try:
        # Send DELETE request to FastAPI server
        response = await http_client.delete(f'/entity-edge/{uuid}')
        response.raise_for_status()

        return SuccessResponse(message=f'Entity edge with UUID {uuid} deleted successfully')

    except httpx.HTTPStatusError as e:
        error_msg = f'HTTP error {e.response.status_code}: {e.response.text}'
        logger.error(f'Error deleting entity edge via FastAPI: {error_msg}')
        return ErrorResponse(error=f'Error deleting entity edge: {error_msg}')
    except Exception as e:
        error_msg = str(e)
        logger.error(f'Error deleting entity edge: {error_msg}')
        return ErrorResponse(error=f'Error deleting entity edge: {error_msg}')


@mcp.tool()
async def delete_episode(uuid: str) -> SuccessResponse | ErrorResponse:
    """Delete an episode from the graph memory via FastAPI server.

    Args:
        uuid: UUID of the episode to delete
    """
    global http_client

    if http_client is None:
        return ErrorResponse(error='HTTP client not initialized')

    try:
        # Send DELETE request to FastAPI server
        response = await http_client.delete(f'/episode/{uuid}')
        response.raise_for_status()

        return SuccessResponse(message=f'Episode with UUID {uuid} deleted successfully')

    except httpx.HTTPStatusError as e:
        error_msg = f'HTTP error {e.response.status_code}: {e.response.text}'
        logger.error(f'Error deleting episode via FastAPI: {error_msg}')
        return ErrorResponse(error=f'Error deleting episode: {error_msg}')
    except Exception as e:
        error_msg = str(e)
        logger.error(f'Error deleting episode: {error_msg}')
        return ErrorResponse(error=f'Error deleting episode: {error_msg}')


@mcp.tool()
async def get_entity_edge(uuid: str) -> dict[str, Any] | ErrorResponse:
    """Get an entity edge from the graph memory via FastAPI server.

    Args:
        uuid: UUID of the entity edge to retrieve
    """
    global http_client

    if http_client is None:
        return ErrorResponse(error='HTTP client not initialized')

    try:
        # Send GET request to FastAPI server
        response = await http_client.get(f'/entity-edge/{uuid}')
        response.raise_for_status()

        return response.json()

    except httpx.HTTPStatusError as e:
        error_msg = f'HTTP error {e.response.status_code}: {e.response.text}'
        logger.error(f'Error getting entity edge via FastAPI: {error_msg}')
        return ErrorResponse(error=f'Error getting entity edge: {error_msg}')
    except Exception as e:
        error_msg = str(e)
        logger.error(f'Error getting entity edge: {error_msg}')
        return ErrorResponse(error=f'Error getting entity edge: {error_msg}')


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
        return ErrorResponse(error='HTTP client not initialized')

    try:
        # Use the provided group_id or fall back to the default from config
        effective_group_id = group_id if group_id is not None else config.group_id

        if not isinstance(effective_group_id, str):
            return ErrorResponse(error='Group ID must be a string')

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
        return ErrorResponse(error=f'Error getting episodes: {error_msg}')
    except Exception as e:
        error_msg = str(e)
        logger.error(f'Error getting episodes: {error_msg}')
        return ErrorResponse(error=f'Error getting episodes: {error_msg}')


@mcp.resource('http://graphiti/status')
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


async def initialize_server() -> MCPConfig:
    """Parse CLI arguments and initialize the Graphiti server configuration."""
    global config

    parser = argparse.ArgumentParser(
        description='Run the Graphiti MCP server with optional LLM client'
    )
    parser.add_argument(
        '--group-id',
        help='Namespace for the graph. This is an arbitrary string used to organize related data. '
        'If not provided, a random UUID will be generated.',
    )
    parser.add_argument(
        '--transport',
        choices=['sse', 'stdio', 'http'],
        default='sse',
        help='Transport to use for communication with the client. (default: sse)',
    )
    parser.add_argument(
        '--model', help=f'Model name to use with the LLM client. (default: {DEFAULT_LLM_MODEL})'
    )
    parser.add_argument(
        '--small-model',
        help=f'Small model name to use with the LLM client. (default: {SMALL_LLM_MODEL})',
    )
    parser.add_argument(
        '--temperature',
        type=float,
        help='Temperature setting for the LLM (0.0-2.0). Lower values make output more deterministic. (default: 0.7)',
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
        # Configure the FastMCP server to bind to specified host and port
        mcp.settings.host = mcp_config.host
        mcp.settings.port = mcp_config.port
        
        logger.info(f"Starting HTTP server on {mcp_config.host}:{mcp_config.port}")
        logger.info(f"MCP endpoint: http://localhost:{mcp_config.port}/mcp")
        logger.info(f"Health check: http://localhost:{mcp_config.port}/health")
        logger.info("Protocol version: 2025-06-18")
        logger.info("Security: CORS enabled for localhost and allowed origins")
        
        # Use FastMCP's built-in HTTP support
        await mcp.run_http_async()
        
    except Exception as e:
        logger.error(f"Failed to start HTTP server: {e}")
        raise


async def run_mcp_server():
    """Run the MCP server in the current event loop."""
    # Initialize the server
    mcp_config = await initialize_server()

    # Run the server with specified transport
    logger.info(f'Starting MCP server with transport: {mcp_config.transport}')
    if mcp_config.transport == 'stdio':
        await mcp.run_stdio_async()
    elif mcp_config.transport == 'sse':
        logger.info(
            f'Running MCP server with SSE transport on {mcp.settings.host}:{mcp.settings.port}'
        )
        await mcp.run_sse_async()
    elif mcp_config.transport == 'http':
        # Run HTTP server for streamable HTTP transport
        await run_http_server(mcp_config)


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
