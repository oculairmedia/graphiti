import logging
import os
import sys
from typing import Annotated, Any
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
FALKORDB_AVAILABLE = False
NEO4J_AVAILABLE = False

try:
    import sys

    logger.info(f'Attempting FalkorDB import. Python path: {sys.path[:3]}')
    logger.info(f'Current working directory: {os.getcwd()}')

    from graphiti_core.driver.falkordb_driver import FalkorDriver

    FALKORDB_AVAILABLE = True
    logger.info('✅ Successfully imported FalkorDriver')
except ImportError as e:
    FalkorDriver = None  # type: ignore[misc, assignment]
    logger.error(f'❌ Failed to import FalkorDriver: {e}')
    import traceback

    logger.error(f'Full traceback: {traceback.format_exc()}')

try:
    from graphiti_core.driver.neo4j_driver import Neo4jDriver

    NEO4J_AVAILABLE = True
except ImportError:
    Neo4jDriver = None  # type: ignore[misc, assignment]


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
            # FalkorDriver expects host and port parameters
            parsed = urlparse(uri)
            host = parsed.hostname or 'localhost'
            port = parsed.port or 6379
            # Use graphiti_migration database instead of default_db
            driver = FalkorDriver(host=host, port=port, username='', password='', database='graphiti_migration')
            logger.info(f'Using FalkorDB driver with host: {host}, port: {port}, database: graphiti_migration')
        else:
            if not NEO4J_AVAILABLE:
                raise ImportError('Neo4j driver not available. Install neo4j package.')
            driver = Neo4jDriver(uri, user, password)  # type: ignore[assignment]
            logger.info(f'Using Neo4j driver with URI: {uri}')

        super().__init__(uri=uri, user=user, password=password, graph_driver=driver, llm_client=llm_client, embedder=embedder)

    async def save_entity_node(self, name: str, uuid: str, group_id: str, summary: str = '') -> EntityNode:
        new_node = EntityNode(
            name=name,
            uuid=uuid,
            group_id=group_id,
            summary=summary,
        )
        await new_node.generate_name_embedding(self.embedder)
        await new_node.save(self.driver)
        return new_node

    async def get_entity_edge(self, uuid: str) -> EntityEdge:
        try:
            edge = await EntityEdge.get_by_uuid(self.driver, uuid)
            return edge
        except EdgeNotFoundError as e:
            raise HTTPException(status_code=404, detail=e.message) from e

    async def delete_group(self, group_id: str) -> None:
        try:
            edges = await EntityEdge.get_by_group_ids(self.driver, [group_id])
        except GroupsEdgesNotFoundError:
            logger.warning(f'No edges found for group {group_id}')
            edges = []

        nodes = await EntityNode.get_by_group_ids(self.driver, [group_id])

        episodes = await EpisodicNode.get_by_group_ids(self.driver, [group_id])  # type: ignore[attr-defined]

        for edge in edges:
            await EntityEdge.delete(self.driver, edge.uuid)

        for node in nodes:
            await EntityNode.delete(self.driver, node.uuid)

        for episode in episodes:
            await episode.delete(self.driver)

    async def delete_entity_edge(self, uuid: str) -> None:
        try:
            edge = await EntityEdge.get_by_uuid(self.driver, uuid)
            await EntityEdge.delete(self.driver, edge.uuid)
        except EdgeNotFoundError as e:
            raise HTTPException(status_code=404, detail=e.message) from e

    async def delete_episodic_node(self, uuid: str) -> None:
        try:
            episode = await EpisodicNode.get_by_uuid(self.driver, uuid)  # type: ignore[attr-defined]
            await episode.delete(self.driver)
        except NodeNotFoundError as e:
            raise HTTPException(status_code=404, detail=e.message) from e


async def get_graphiti(settings: ZepEnvDep) -> Any:  # Returns generator
    from graph_service.factories import create_llm_client, create_embedder_client, configure_non_ollama_clients
    
    # Delegate client creation to factories
    llm_client = create_llm_client(settings)
    embedder = create_embedder_client(settings)

    client = ZepGraphiti(
        uri=settings.database_uri,
        user=settings.database_user,
        password=settings.database_password,
        llm_client=llm_client,
        embedder=embedder,
        use_falkordb=settings.use_falkordb or bool(settings.falkordb_uri or settings.falkordb_host),
    )

    logger.info(
        f'ZepGraphiti embedder model: {client.embedder.config.embedding_model if client.embedder else "None"}'
    )

    # Configure non-Ollama clients if needed
    configure_non_ollama_clients(client, settings)

    try:
        yield client
    finally:
        await client.close()


async def initialize_graphiti(settings: ZepEnvDep) -> None:
    from graph_service.factories import create_llm_client, create_embedder_client
    
    # Delegate client creation to factories
    llm_client = create_llm_client(settings)
    embedder = create_embedder_client(settings)

    client = ZepGraphiti(
        uri=settings.database_uri,
        user=settings.database_user,
        password=settings.database_password,
        llm_client=llm_client,
        embedder=embedder,
        use_falkordb=settings.use_falkordb or bool(settings.falkordb_uri or settings.falkordb_host),
    )
    await client.build_indices_and_constraints()


def get_fact_result_from_edge(edge: EntityEdge) -> FactResult:
    return FactResult(
        uuid=edge.uuid,
        name=edge.name,
        fact=edge.fact or "",  # Provide empty string if fact is None
        valid_at=edge.valid_at,
        invalid_at=edge.invalid_at,
        created_at=edge.created_at,
        expired_at=edge.expired_at,
    )


ZepGraphitiDep = Annotated[ZepGraphiti, Depends(get_graphiti)]
