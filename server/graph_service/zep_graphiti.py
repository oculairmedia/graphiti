import logging
import asyncio
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

from graphiti_core.driver.falkordb_driver import FalkorDriver

_entity_locks: dict[str, asyncio.Lock] = {}
_entity_locks_lock = asyncio.Lock()


class ZepGraphiti(Graphiti):
    def __init__(
        self,
        uri: str,
        llm_client: LLMClient | None = None,
        embedder: EmbedderClient | None = None,
        use_dspy: bool = False,
    ):
        parsed = urlparse(uri)
        host = parsed.hostname or 'localhost'
        port = parsed.port or 6379
        database = os.getenv('FALKORDB_DATABASE', 'graphiti_migration')
        driver = FalkorDriver(host=host, port=port, username='', password='', database=database)
        logger.info(f'Using FalkorDB driver with host: {host}, port: {port}, database: {database}')

        super().__init__(
            driver=driver,
            llm_client=llm_client,
            embedder=embedder,
            use_dspy=use_dspy,
        )
        logger.info(f'ZepGraphiti initialized with use_dspy={use_dspy}')

    async def save_entity_node(
        self, name: str, uuid: str, group_id: str, summary: str = ''
    ) -> EntityNode:
        return await self._upsert_entity_by_name(name, uuid, group_id, summary)

    async def _upsert_entity_by_name(
        self, name: str, uuid: str, group_id: str, summary: str = ''
    ) -> EntityNode:
        """Atomic upsert with per-entity mutex to prevent race conditions."""
        from datetime import datetime, timezone

        lock_key = f'{group_id}:{name}'
        async with _entity_locks_lock:
            if lock_key not in _entity_locks:
                _entity_locks[lock_key] = asyncio.Lock()
            entity_lock = _entity_locks[lock_key]

        async with entity_lock:
            now = datetime.now(timezone.utc).isoformat()
            node = EntityNode(name=name, uuid=uuid, group_id=group_id, summary=summary)
            await node.generate_name_embedding(self.embedder)
            embedding = node.name_embedding or []

            existing = await self._find_existing_entity(name, group_id)
            if existing:
                existing.summary = summary or existing.summary
                existing.name_embedding = embedding
                query = """
                    MATCH (n:Entity {name: $name, group_id: $group_id})
                    SET n.summary = $summary,
                        n.updated_at = $now,
                        n.name_embedding = vecf32($embedding)
                    RETURN n.uuid as uuid
                """
                await self.driver.execute_query(
                    query,
                    name=name,
                    group_id=group_id,
                    summary=existing.summary,
                    now=now,
                    embedding=embedding,
                )
                return existing

            create_query = """
                CREATE (n:Entity {
                    uuid: $uuid,
                    name: $name,
                    group_id: $group_id,
                    summary: $summary,
                    created_at: $now,
                    updated_at: $now,
                    name_embedding: vecf32($embedding)
                })
                RETURN n.uuid as uuid
            """
            await self.driver.execute_query(
                create_query,
                uuid=uuid,
                name=name,
                group_id=group_id,
                summary=summary,
                now=now,
                embedding=embedding,
            )
            return node

    async def _find_existing_entity(self, name: str, group_id: str) -> EntityNode | None:
        query = """
            MATCH (n:Entity {name: $name, group_id: $group_id})
            RETURN n.uuid as uuid, n.name as name, n.group_id as group_id, 
                   n.summary as summary, n.created_at as created_at, n.updated_at as updated_at,
                   n.name_embedding as name_embedding
            LIMIT 1
        """
        try:
            result = await self.driver.execute_query(query, name=name, group_id=group_id)  # type: ignore[union-attr]
            records = result[0] if result else []
            if records and len(records) > 0:
                row = records[0]
                if row and row.get('uuid'):
                    return EntityNode(
                        uuid=row['uuid'],
                        name=row['name'],
                        group_id=row['group_id'],
                        summary=row.get('summary', ''),
                        created_at=row.get('created_at'),
                        name_embedding=list(row['name_embedding'])
                        if row.get('name_embedding')
                        else None,
                    )
        except Exception as e:
            logger.warning(f'Error checking for existing entity: {e}', exc_info=True)
        return None

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

        # Publish delete events for real-time sync (GRAPH-111)
        if self.event_publisher is not None and self.event_publisher.is_enabled:
            for edge in edges:
                await self.event_publisher.publish_edge_change('delete', edge, include_data=False)
            for node in nodes:
                await self.event_publisher.publish_node_change('delete', node, include_data=False)
            for episode in episodes:
                await self.event_publisher.publish_episode_change(
                    'delete', episode, include_data=False
                )
            logger.info(
                f'Published delete events for group {group_id}: '
                f'{len(edges)} edges, {len(nodes)} nodes, {len(episodes)} episodes'
            )

    async def delete_entity_edge(self, uuid: str) -> None:
        try:
            edge = await EntityEdge.get_by_uuid(self.driver, uuid)
            await EntityEdge.delete(self.driver, edge.uuid)
            # Publish delete event for real-time sync (GRAPH-111)
            if self.event_publisher is not None and self.event_publisher.is_enabled:
                await self.event_publisher.publish_edge_change('delete', edge, include_data=False)
                logger.debug(f'Published delete event for edge {uuid}')
        except EdgeNotFoundError as e:
            raise HTTPException(status_code=404, detail=e.message) from e

    async def delete_episodic_node(self, uuid: str) -> None:
        try:
            episode = await EpisodicNode.get_by_uuid(self.driver, uuid)  # type: ignore[attr-defined]
            await episode.delete(self.driver)
            # Publish delete event for real-time sync (GRAPH-111)
            if self.event_publisher is not None and self.event_publisher.is_enabled:
                await self.event_publisher.publish_episode_change(
                    'delete', episode, include_data=False
                )
                logger.debug(f'Published delete event for episode {uuid}')
        except NodeNotFoundError as e:
            raise HTTPException(status_code=404, detail=e.message) from e


async def get_graphiti(settings: ZepEnvDep) -> Any:  # Returns generator
    from graph_service.factories import (
        create_llm_client,
        create_embedder_client,
        configure_non_ollama_clients,
    )

    # Delegate client creation to factories
    llm_client = create_llm_client(settings)
    embedder = create_embedder_client(settings)

    use_dspy = os.getenv('USE_DSPY', 'false').lower() == 'true'
    falkordb_uri = (
        settings.falkordb_uri
        or f'redis://{settings.falkordb_host}:{settings.falkordb_port or 6379}'
    )
    client = ZepGraphiti(
        uri=falkordb_uri,
        llm_client=llm_client,
        embedder=embedder,
        use_dspy=use_dspy,
    )

    logger.info(
        f'ZepGraphiti embedder model: {client.embedder.config.embedding_model if client.embedder else "None"}'
    )

    configure_non_ollama_clients(client, settings)

    try:
        yield client
    finally:
        await client.close()


async def initialize_graphiti(settings: ZepEnvDep) -> None:
    from graph_service.factories import create_llm_client, create_embedder_client

    llm_client = create_llm_client(settings)
    embedder = create_embedder_client(settings)

    use_dspy = os.getenv('USE_DSPY', 'false').lower() == 'true'
    falkordb_uri = (
        settings.falkordb_uri
        or f'redis://{settings.falkordb_host}:{settings.falkordb_port or 6379}'
    )
    client = ZepGraphiti(
        uri=falkordb_uri,
        llm_client=llm_client,
        embedder=embedder,
        use_dspy=use_dspy,
    )
    await client.build_indices_and_constraints()


def get_fact_result_from_edge(edge: EntityEdge) -> FactResult:
    return FactResult(
        uuid=edge.uuid,
        name=edge.name,
        fact=edge.fact or '',  # Provide empty string if fact is None
        valid_at=edge.valid_at,
        invalid_at=edge.invalid_at,
        created_at=edge.created_at,
        expired_at=edge.expired_at,
    )


ZepGraphitiDep = Annotated[ZepGraphiti, Depends(get_graphiti)]
