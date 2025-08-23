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
from mcp import McpError, ErrorCode
from mcp.types import ProgressToken, ProgressNotification
import traceback
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


async def initialize_graphiti():
    """Initialize the HTTP client for FastAPI server with connection pooling."""
    global http_client, config, operation_semaphore

    try:
        # Configure connection limits for better performance
        limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
        timeout = httpx.Timeout(30.0, read=60.0)  # Longer read timeout for large responses
        
        # Initialize HTTP client for FastAPI server with connection pooling
        http_client = httpx.AsyncClient(
            base_url=config.api.base_url, 
            timeout=timeout,
            limits=limits,
            http2=True  # Enable HTTP/2 if available
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
    _progress_token: ProgressToken | None = Field(None, description="Progress token for reporting operation progress"),
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
        progress = ProgressReporter('add_memory', _progress_token)
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
        default=os.environ.get('MCP_TRANSPORT', 'http'),
        help='Transport to use for communication with the client. (default: MCP_TRANSPORT environment variable or http)',
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
