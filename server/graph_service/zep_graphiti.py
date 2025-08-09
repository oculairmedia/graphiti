import logging
import os
import sys
from typing import Annotated
from urllib.parse import urlparse

# Ensure /app is in Python path for development mode imports
if '/app' not in sys.path:
    sys.path.insert(0, '/app')

from fastapi import Depends, HTTPException
from graphiti_core import Graphiti
from graphiti_core.edges import EntityEdge
from graphiti_core.embedder import EmbedderClient
from graphiti_core.errors import EdgeNotFoundError, GroupsEdgesNotFoundError, NodeNotFoundError
from graphiti_core.llm_client import LLMClient
from graphiti_core.nodes import EntityNode, EpisodicNode

from graph_service.config import ZepEnvDep
from graph_service.dto import FactResult

logger = logging.getLogger(__name__)

# Import drivers with error handling and debugging
try:
    import sys

    logger.info(f'Attempting FalkorDB import. Python path: {sys.path[:3]}')
    logger.info(f'Current working directory: {os.getcwd()}')

    from graphiti_core.driver.falkordb_driver import FalkorDriver

    FALKORDB_AVAILABLE = True
    logger.info('✅ Successfully imported FalkorDriver')
except ImportError as e:
    FALKORDB_AVAILABLE = False
    FalkorDriver = None
    logger.error(f'❌ Failed to import FalkorDriver: {e}')
    import traceback

    logger.error(f'Full traceback: {traceback.format_exc()}')

try:
    from graphiti_core.driver.neo4j_driver import Neo4jDriver

    NEO4J_AVAILABLE = True
except ImportError:
    NEO4J_AVAILABLE = False
    Neo4jDriver = None


class ZepGraphiti(Graphiti):
    def __init__(
        self,
        uri: str,
        user: str,
        password: str,
        llm_client: LLMClient | None = None,
        embedder: EmbedderClient | None = None,
        use_falkordb: bool = False,
    ):
        # Create appropriate driver based on URI or use_falkordb flag
        if use_falkordb or uri.startswith('redis://'):
            if not FALKORDB_AVAILABLE:
                raise ImportError('FalkorDB driver not available. Install falkordb package.')
            # Parse redis URI for FalkorDriver - follow examples pattern
            parsed = urlparse(uri)
            host = parsed.hostname or 'localhost'
            port = parsed.port or 6379
            database = 'graphiti_migration'  # Use same database as migration scripts
            driver = FalkorDriver(host=host, port=port, database=database)
            logger.info(f'Using FalkorDB driver with host: {host}:{port}, database: {database}')
        else:
            if not NEO4J_AVAILABLE:
                raise ImportError('Neo4j driver not available. Install neo4j package.')
            driver = Neo4jDriver(uri, user, password)
            logger.info(f'Using Neo4j driver with URI: {uri}')

        super().__init__(uri, user, password, llm_client, embedder, graph_driver=driver)

    async def save_entity_node(self, name: str, uuid: str, group_id: str, summary: str = ''):
        new_node = EntityNode(
            name=name,
            uuid=uuid,
            group_id=group_id,
            summary=summary,
        )
        await new_node.generate_name_embedding(self.embedder)
        await new_node.save(self.driver)
        return new_node

    async def get_entity_edge(self, uuid: str):
        try:
            edge = await EntityEdge.get_by_uuid(self.driver, uuid)
            return edge
        except EdgeNotFoundError as e:
            raise HTTPException(status_code=404, detail=e.message) from e

    async def delete_group(self, group_id: str):
        try:
            edges = await EntityEdge.get_by_group_ids(self.driver, [group_id])
        except GroupsEdgesNotFoundError:
            logger.warning(f'No edges found for group {group_id}')
            edges = []

        nodes = await EntityNode.get_by_group_ids(self.driver, [group_id])

        episodes = await EpisodicNode.get_by_group_ids(self.driver, [group_id])

        for edge in edges:
            await edge.delete(self.driver)

        for node in nodes:
            await node.delete(self.driver)

        for episode in episodes:
            await episode.delete(self.driver)

    async def delete_entity_edge(self, uuid: str):
        try:
            edge = await EntityEdge.get_by_uuid(self.driver, uuid)
            await edge.delete(self.driver)
        except EdgeNotFoundError as e:
            raise HTTPException(status_code=404, detail=e.message) from e

    async def delete_episodic_node(self, uuid: str):
        try:
            episode = await EpisodicNode.get_by_uuid(self.driver, uuid)
            await episode.delete(self.driver)
        except NodeNotFoundError as e:
            raise HTTPException(status_code=404, detail=e.message) from e


async def get_graphiti(settings: ZepEnvDep):
    # Check if we should use Ollama
    llm_client = None
    embedder = None
    if os.getenv('USE_OLLAMA', '').lower() == 'true':
        from graphiti_core.embedder import OpenAIEmbedder, OpenAIEmbedderConfig
        from graphiti_core.llm_client import LLMConfig, OpenAIClient
        from openai import AsyncOpenAI

        ollama_base_url = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434/v1')
        ollama_model = os.getenv('OLLAMA_MODEL', 'mistral:latest')
        ollama_embed_model = os.getenv('OLLAMA_EMBEDDING_MODEL', 'mxbai-embed-large:latest')

        logger.info(
            f'Using Ollama at {ollama_base_url} with LLM model {ollama_model} and embedding model {ollama_embed_model}'
        )

        # Create Ollama client
        client = AsyncOpenAI(base_url=ollama_base_url, api_key='ollama')

        # Configure LLM
        config = LLMConfig(
            model=ollama_model, small_model=ollama_model, temperature=0.7, max_tokens=2000
        )

        llm_client = OpenAIClient(config=config, client=client)

        # Configure Embedder
        embed_config = OpenAIEmbedderConfig(embedding_model=ollama_embed_model)
        embedder = OpenAIEmbedder(config=embed_config, client=client)
        logger.info(f'Created Ollama embedder with model: {embed_config.embedding_model}')

    client = ZepGraphiti(
        uri=settings.database_uri,
        user=settings.database_user,
        password=settings.database_password,
        llm_client=llm_client,  # Will be None if not using Ollama
        embedder=embedder,  # Will be None if not using Ollama
        use_falkordb=settings.use_falkordb or bool(settings.falkordb_uri or settings.falkordb_host),
    )

    logger.info(
        f'ZepGraphiti embedder model: {client.embedder.config.embedding_model if client.embedder else "None"}'
    )

    # Only configure OpenAI settings if not using Ollama
    if not llm_client:
        if settings.openai_base_url is not None:
            client.llm_client.config.base_url = settings.openai_base_url
        if settings.openai_api_key is not None:
            client.llm_client.config.api_key = settings.openai_api_key
        if settings.model_name is not None:
            client.llm_client.model = settings.model_name

    try:
        yield client
    finally:
        await client.close()


async def initialize_graphiti(settings: ZepEnvDep):
    # Check if we should use Ollama
    llm_client = None
    embedder = None
    if os.getenv('USE_OLLAMA', '').lower() == 'true':
        from graphiti_core.embedder import OpenAIEmbedder, OpenAIEmbedderConfig
        from graphiti_core.llm_client import LLMConfig, OpenAIClient
        from openai import AsyncOpenAI

        ollama_base_url = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434/v1')
        ollama_model = os.getenv('OLLAMA_MODEL', 'mistral:latest')
        ollama_embed_model = os.getenv('OLLAMA_EMBEDDING_MODEL', 'mxbai-embed-large:latest')

        logger.info(
            f'Using Ollama at {ollama_base_url} with LLM model {ollama_model} and embedding model {ollama_embed_model}'
        )

        # Create Ollama client
        client = AsyncOpenAI(base_url=ollama_base_url, api_key='ollama')

        # Configure LLM
        config = LLMConfig(
            model=ollama_model, small_model=ollama_model, temperature=0.7, max_tokens=2000
        )

        llm_client = OpenAIClient(config=config, client=client)

        # Configure Embedder
        embed_config = OpenAIEmbedderConfig(embedding_model=ollama_embed_model)
        embedder = OpenAIEmbedder(config=embed_config, client=client)

    client = ZepGraphiti(
        uri=settings.database_uri,
        user=settings.database_user,
        password=settings.database_password,
        llm_client=llm_client,  # Will be None if not using Ollama
        embedder=embedder,  # Will be None if not using Ollama
        use_falkordb=settings.use_falkordb or bool(settings.falkordb_uri or settings.falkordb_host),
    )
    await client.build_indices_and_constraints()


def get_fact_result_from_edge(edge: EntityEdge):
    return FactResult(
        uuid=edge.uuid,
        name=edge.name,
        fact=edge.fact,
        valid_at=edge.valid_at,
        invalid_at=edge.invalid_at,
        created_at=edge.created_at,
        expired_at=edge.expired_at,
    )


ZepGraphitiDep = Annotated[ZepGraphiti, Depends(get_graphiti)]
