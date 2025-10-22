"""
FalkorDB data extraction module for reverse sync service.

This module provides extraction of graph data from FalkorDB for synchronization
to Neo4j, supporting batch processing and incremental sync capabilities.
"""

import asyncio
import logging
import time
import psutil
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, AsyncIterator
from dataclasses import dataclass

from falkordb.asyncio import FalkorDB
from falkordb import Graph as FalkorGraph

logger = logging.getLogger(__name__)


@dataclass
class SyncMetadata:
    """Metadata for sync operations."""

    last_sync_timestamp: Optional[datetime] = None
    total_entity_nodes: int = 0
    total_episodic_nodes: int = 0
    total_community_nodes: int = 0
    total_entity_edges: int = 0
    total_episodic_edges: int = 0


@dataclass
class ExtractionStats:
    """Statistics for extraction operations."""

    entity_nodes: int = 0
    episodic_nodes: int = 0
    community_nodes: int = 0
    entity_edges: int = 0
    episodic_edges: int = 0
    extraction_time_seconds: float = 0.0


ESSENTIAL_EDGE_PROPERTIES = [
    'uuid',  # Primary identifier
    'source_uuid',  # Source node UUID via MATCH binding
    'target_uuid',  # Target node UUID via MATCH binding
    'created_at',  # Creation timestamp
    'updated_at',  # Modification timestamp
    'weight',  # Relationship weight
    'valid_at',  # Validity start time
    'invalid_at',  # Validity end time
]

EDGE_PROPERTY_EXPRESSIONS = {
    'uuid': 'r.uuid',
    'source_uuid': 'source.uuid',
    'target_uuid': 'target.uuid',
    'created_at': 'r.created_at',
    'updated_at': 'r.updated_at',
    'weight': 'r.weight',
    'valid_at': 'r.valid_at',
    'invalid_at': 'r.invalid_at',
}

EDGE_RETURN_FIELDS = [(prop, EDGE_PROPERTY_EXPRESSIONS[prop]) for prop in ESSENTIAL_EDGE_PROPERTIES]


class FalkorDBExtractor:
    """
    Extracts graph data from FalkorDB for reverse synchronization.

    Features:
    - Batch processing for memory efficiency
    - Incremental extraction support
    - Comprehensive data type coverage
    - Connection pooling and error handling
    """

    NODE_DATA_TYPES = {'entity_nodes', 'episodic_nodes', 'community_nodes'}
    EDGE_DATA_TYPES = {'entity_edges', 'episodic_edges'}

    def __init__(
        self,
        host: str = 'localhost',
        port: int = 6379,
        username: Optional[str] = None,
        password: Optional[str] = None,
        database: str = 'graphiti_migration',
        batch_size: int = 1000,
        max_query_limit: int = 15000,
        enable_pagination: bool = True,
        optimization_enabled: bool = True,
        edge_batch_size: int = 8000,
        node_batch_size: int = 15000,
        memory_threshold_mb: int = 100,
        adaptive_sizing: bool = True,
    ):
        """
        Initialize FalkorDB extractor.

        Args:
            host: FalkorDB host
            port: FalkorDB port
            username: Database username (optional)
            password: Database password (optional)
            database: Graph database name
            batch_size: Legacy batch size for backwards compatibility
            max_query_limit: Maximum query limit for ORDER BY operations
            enable_pagination: Enable query-level pagination for large datasets
            optimization_enabled: Toggle for optimized extraction patterns
            edge_batch_size: Maximum batch size for edge extraction
            node_batch_size: Maximum batch size for node extraction
            memory_threshold_mb: Memory threshold for adaptive sizing heuristics
            adaptive_sizing: Enable adaptive batch limit adjustments
        """
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.database = database
        self.batch_size = max(1, batch_size)
        self.max_query_limit = max(1, max_query_limit)
        self.enable_pagination = enable_pagination
        self.optimization_enabled = optimization_enabled
        self.edge_batch_size = max(1, edge_batch_size)
        self.node_batch_size = max(1, node_batch_size)
        self.memory_threshold_mb = max(1, memory_threshold_mb)
        self.adaptive_sizing = adaptive_sizing
        self.client: Optional[FalkorDB] = None
        self.graph: Optional[FalkorGraph] = None

    async def connect(self) -> None:
        """Establish connection to FalkorDB."""
        try:
            self.client = FalkorDB(
                host=self.host,
                port=self.port,
                username=self.username,
                password=self.password,
            )
            self.graph = self.client.select_graph(self.database)

            # Test connectivity
            await self.graph.query('RETURN 1')
            logger.info(f'Connected to FalkorDB at {self.host}:{self.port}/{self.database}')
        except Exception as e:
            logger.error(f'Failed to connect to FalkorDB: {e}')
            raise

    async def disconnect(self) -> None:
        """Close FalkorDB connection."""
        if self.client and hasattr(self.client, 'aclose'):
            await self.client.aclose()
            logger.info('Disconnected from FalkorDB')

    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect()

    def _convert_node_result(self, node_data: Dict[str, Any]) -> Dict[str, Any]:
        """Convert FalkorDB node result to standard format."""
        # FalkorDB stores datetime as ISO strings, convert back to datetime objects
        if 'created_at' in node_data and isinstance(node_data['created_at'], str):
            try:
                node_data['created_at'] = datetime.fromisoformat(
                    node_data['created_at'].replace('Z', '+00:00')
                )
            except (ValueError, AttributeError):
                pass  # Keep as string if conversion fails

        if 'updated_at' in node_data and isinstance(node_data['updated_at'], str):
            try:
                node_data['updated_at'] = datetime.fromisoformat(
                    node_data['updated_at'].replace('Z', '+00:00')
                )
            except (ValueError, AttributeError):
                pass

        return node_data

    def _convert_edge_result(self, edge_data: Dict[str, Any]) -> Dict[str, Any]:
        """Convert FalkorDB edge result to standard format."""
        # Normalize datetime string representations for downstream loaders
        for key in ('created_at', 'updated_at', 'valid_at', 'invalid_at'):
            value = edge_data.get(key)
            if isinstance(value, str):
                try:
                    edge_data[key] = datetime.fromisoformat(value.replace('Z', '+00:00'))
                except (ValueError, AttributeError):
                    pass

        return edge_data

    def _resolve_batch_limit(self, data_type: str, override: Optional[int] = None) -> int:
        """Determine effective batch size for the requested data type."""
        if override is not None:
            limit = override
        elif self.optimization_enabled:
            if data_type in self.NODE_DATA_TYPES:
                limit = self.node_batch_size
            elif data_type in self.EDGE_DATA_TYPES:
                limit = self.edge_batch_size
            else:
                limit = self.batch_size
        else:
            limit = self.batch_size

        limit = max(1, limit)
        return self._apply_adaptive_sizing(data_type, limit)

    def _apply_adaptive_sizing(self, data_type: str, limit: int) -> int:
        """Clamp batch size using simple heuristics pending telemetry hooks."""
        if not (self.optimization_enabled and self.adaptive_sizing):
            return limit

        # Placeholder for future memory-aware logic; ensure bounds stay sane.
        return min(self.max_query_limit, max(1, limit))

    def _resolve_query_limit(self, data_type: str, override: Optional[int] = None) -> int:
        """Resolve LIMIT value for paginated queries respecting configuration."""
        if override is not None:
            return min(self.max_query_limit, max(1, override))

        batch_limit = self._resolve_batch_limit(data_type, None)
        return min(self.max_query_limit, max(batch_limit, self.batch_size))

    def _build_edge_return_clause(self) -> str:
        """Construct optimized RETURN clause for edge extraction queries."""
        return ',\n       '.join(
            f'{expression} as {alias}' for alias, expression in EDGE_RETURN_FIELDS
        )

    def _map_edge_row(self, row: List[Any]) -> Dict[str, Any]:
        """Map raw FalkorDB row data to normalized edge payload."""
        edge_data: Dict[str, Any] = {}
        for idx, (alias, _) in enumerate(EDGE_RETURN_FIELDS):
            if idx >= len(row):
                break
            value = row[idx]
            if value is None:
                continue

            if alias == 'source_uuid':
                edge_data['source_node_uuid'] = value
            elif alias == 'target_uuid':
                edge_data['target_node_uuid'] = value
            else:
                edge_data[alias] = value

        edge_data.setdefault('relationship_type', 'RELATES_TO')
        return self._convert_edge_result(edge_data)

    async def get_sync_metadata(self) -> SyncMetadata:
        """Get metadata about the FalkorDB database."""
        if not self.graph:
            raise RuntimeError('Not connected to FalkorDB')

        metadata = SyncMetadata()

        try:
            # Count entity nodes
            result = await self.graph.query('MATCH (n:Entity) RETURN count(n) as count')
            metadata.total_entity_nodes = result.result_set[0][0] if result.result_set else 0

            # Count episodic nodes
            result = await self.graph.query('MATCH (n:Episodic) RETURN count(n) as count')
            metadata.total_episodic_nodes = result.result_set[0][0] if result.result_set else 0

            # Count community nodes
            result = await self.graph.query('MATCH (n:Community) RETURN count(n) as count')
            metadata.total_community_nodes = result.result_set[0][0] if result.result_set else 0

            # Count entity edges
            result = await self.graph.query('MATCH ()-[r:RELATES_TO]->() RETURN count(r) as count')
            metadata.total_entity_edges = result.result_set[0][0] if result.result_set else 0

            # Count episodic edges
            result = await self.graph.query('MATCH ()-[r:MENTIONS]->() RETURN count(r) as count')
            metadata.total_episodic_edges = result.result_set[0][0] if result.result_set else 0

            logger.info(
                f'FalkorDB metadata: {metadata.total_entity_nodes} entities, '
                f'{metadata.total_episodic_nodes} episodes, '
                f'{metadata.total_entity_edges} entity edges, '
                f'{metadata.total_episodic_edges} episodic edges'
            )

        except Exception as e:
            logger.error(f'Failed to get sync metadata: {e}')

        return metadata

    async def extract_entity_nodes(
        self, since_timestamp: Optional[datetime] = None, limit: Optional[int] = None
    ) -> AsyncIterator[List[Dict[str, Any]]]:
        """Extract entity nodes in batches."""
        if not self.graph:
            raise RuntimeError('Not connected to FalkorDB')

        # Build query with optional timestamp filter
        where_clause = ''
        if since_timestamp:
            iso_timestamp = since_timestamp.isoformat()
            # Include nodes with NULL timestamps to ensure complete extraction
            where_clause = f"WHERE n.updated_at > '{iso_timestamp}' OR n.created_at > '{iso_timestamp}' OR n.updated_at IS NULL OR n.created_at IS NULL"

        query = f"""
        MATCH (n:Entity) 
        {where_clause}
        RETURN n.uuid as uuid, properties(n) as props
        ORDER BY n.uuid
        """

        if limit:
            query += f' LIMIT {limit}'

        try:
            result = await self.graph.query(query)
            if not result.result_set:
                return

            batch = []
            for row in result.result_set:
                uuid_val = row[0]
                props = row[1] if row[1] else {}

                # Ensure uuid is in properties
                props['uuid'] = uuid_val
                props['labels'] = ['Entity']

                batch.append(self._convert_node_result(props))

                if len(batch) >= self._resolve_batch_limit('entity_nodes', limit):
                    yield batch
                    batch = []

            # Yield remaining items
            if batch:
                yield batch

        except Exception as e:
            logger.error(f'Failed to extract entity nodes: {e}')
            raise

    async def extract_episodic_nodes(
        self, since_timestamp: Optional[datetime] = None, limit: Optional[int] = None
    ) -> AsyncIterator[List[Dict[str, Any]]]:
        """Extract episodic nodes in batches."""
        if not self.graph:
            raise RuntimeError('Not connected to FalkorDB')

        where_clause = ''
        if since_timestamp:
            iso_timestamp = since_timestamp.isoformat()
            # Include nodes with NULL timestamps to ensure complete extraction
            where_clause = f"WHERE n.updated_at > '{iso_timestamp}' OR n.created_at > '{iso_timestamp}' OR n.updated_at IS NULL OR n.created_at IS NULL"

        query = f"""
        MATCH (n:Episodic) 
        {where_clause}
        RETURN n.uuid as uuid, properties(n) as props
        ORDER BY n.uuid
        """

        if limit:
            query += f' LIMIT {limit}'

        try:
            result = await self.graph.query(query)
            if not result.result_set:
                return

            batch = []
            for row in result.result_set:
                uuid_val = row[0]
                props = row[1] if row[1] else {}

                props['uuid'] = uuid_val
                props['labels'] = ['Episodic']

                batch.append(self._convert_node_result(props))

                if len(batch) >= self._resolve_batch_limit('episodic_nodes', limit):
                    yield batch
                    batch = []

            if batch:
                yield batch

        except Exception as e:
            logger.error(f'Failed to extract episodic nodes: {e}')
            raise

    async def extract_community_nodes(
        self, since_timestamp: Optional[datetime] = None, limit: Optional[int] = None
    ) -> AsyncIterator[List[Dict[str, Any]]]:
        """Extract community nodes in batches."""
        if not self.graph:
            raise RuntimeError('Not connected to FalkorDB')

        where_clause = ''
        if since_timestamp:
            iso_timestamp = since_timestamp.isoformat()
            # Include nodes with NULL timestamps to ensure complete extraction
            where_clause = f"WHERE n.updated_at > '{iso_timestamp}' OR n.created_at > '{iso_timestamp}' OR n.updated_at IS NULL OR n.created_at IS NULL"

        query = f"""
        MATCH (n:Community) 
        {where_clause}
        RETURN n.uuid as uuid, properties(n) as props
        ORDER BY n.uuid
        """

        if limit:
            query += f' LIMIT {limit}'

        try:
            result = await self.graph.query(query)
            if not result.result_set:
                return

            batch = []
            for row in result.result_set:
                uuid_val = row[0]
                props = row[1] if row[1] else {}

                props['uuid'] = uuid_val
                props['labels'] = ['Community']

                batch.append(self._convert_node_result(props))

                if len(batch) >= self._resolve_batch_limit('community_nodes', limit):
                    yield batch
                    batch = []

            if batch:
                yield batch

        except Exception as e:
            logger.error(f'Failed to extract community nodes: {e}')
            raise

    async def extract_entity_edges(
        self, since_timestamp: Optional[datetime] = None, limit: Optional[int] = None
    ) -> AsyncIterator[List[Dict[str, Any]]]:
        """Extract entity edges (RELATES_TO) with optimized direct access by default."""
        if not self.graph:
            raise RuntimeError('Not connected to FalkorDB')

        if self.optimization_enabled:
            remaining = limit
            batch_override = min(remaining, self.edge_batch_size) if remaining is not None else None

            async for batch in self.extract_entity_edges_optimized(
                since_timestamp=since_timestamp, batch_size=batch_override
            ):
                if remaining is not None:
                    if len(batch) >= remaining:
                        yield batch[:remaining]
                        return
                    yield batch
                    remaining -= len(batch)
                    if remaining <= 0:
                        return
                else:
                    yield batch
            return

        if self.enable_pagination and limit is None:
            async for batch in self._extract_entity_edges_paginated(since_timestamp):
                yield batch
        else:
            async for batch in self._extract_entity_edges_single_query(since_timestamp, limit):
                yield batch

    async def extract_entity_edges_optimized(
        self, since_timestamp: Optional[datetime] = None, batch_size: Optional[int] = None
    ) -> AsyncIterator[List[Dict[str, Any]]]:
        """Optimized entity edge extraction using direct property access."""
        if not self.graph:
            raise RuntimeError('Not connected to FalkorDB')

        offset = 0
        total_processed = 0
        where_clause = ''
        if since_timestamp:
            iso_timestamp = since_timestamp.isoformat()
            where_clause = (
                f"WHERE r.updated_at > '{iso_timestamp}' OR r.created_at > '{iso_timestamp}' "
                'OR r.updated_at IS NULL OR r.created_at IS NULL'
            )

        return_clause = self._build_edge_return_clause()

        while True:
            effective_batch_limit = self._resolve_batch_limit('entity_edges', batch_size)
            page_limit = self._resolve_query_limit('entity_edges', batch_size)
            pagination_clause = (
                f'SKIP {offset} LIMIT {page_limit}'
                if self.enable_pagination
                else f'LIMIT {page_limit}'
            )

            query = f"""
            MATCH (source)-[r:RELATES_TO]->(target)
            {where_clause}
            RETURN {return_clause}
            ORDER BY r.uuid
            {pagination_clause}
            """

            try:
                logger.info(f'Executing edge query: offset={offset}, limit={page_limit}')
                start_time = time.time()

                # Add timeout to prevent infinite hang (GRAPH-574 fix)
                result = await asyncio.wait_for(self.graph.query(query), timeout=30.0)

                duration = time.time() - start_time
                logger.info(f'Query completed in {duration:.2f}s')

            except asyncio.TimeoutError:
                logger.error(f'Edge query timed out after 30s at offset {offset}')
                raise RuntimeError(f'Edge extraction timed out at offset {offset}')
            except Exception as exc:
                logger.error(f'Failed to extract optimized entity edges at offset {offset}: {exc}')
                raise

            rows = result.result_set if result and result.result_set else []
            if not rows:
                logger.info(
                    f'Entity edge optimization completed. Total processed: {total_processed}'
                )
                break

            batch: List[Dict[str, Any]] = []
            for row in rows:
                batch.append(self._map_edge_row(row))
                if len(batch) >= effective_batch_limit:
                    yield batch
                    total_processed += len(batch)
                    batch = []

            if batch:
                yield batch
                total_processed += len(batch)

            if not self.enable_pagination or len(rows) < page_limit:
                break

            offset += page_limit
            logger.debug(
                f'Processed {total_processed} optimized entity edges; continuing from offset {offset}'
            )

    async def _extract_entity_edges_paginated(
        self, since_timestamp: Optional[datetime] = None
    ) -> AsyncIterator[List[Dict[str, Any]]]:
        """Extract entity edges using cursor-based pagination."""
        offset = 0
        total_processed = 0

        while True:
            where_clause = ''
            if since_timestamp:
                iso_timestamp = since_timestamp.isoformat()
                where_clause = f"WHERE r.updated_at > '{iso_timestamp}' OR r.created_at > '{iso_timestamp}' OR r.updated_at IS NULL OR r.created_at IS NULL"

            # Use SKIP/LIMIT for pagination to avoid unbounded ORDER BY
            # Use UUID for stable pagination instead of created_at to avoid NULL value issues
            page_limit = self._resolve_query_limit('entity_edges')
            query = f"""
            MATCH (source)-[r:RELATES_TO]->(target)
            {where_clause}
            RETURN r.uuid as uuid, source.uuid as source_uuid, target.uuid as target_uuid, properties(r) as props
            ORDER BY r.uuid
            SKIP {offset} LIMIT {page_limit}
            """

            try:
                result = await self.graph.query(query)
                if not result.result_set:
                    logger.info(
                        f'Entity edges extraction completed. Total processed: {total_processed}'
                    )
                    break

                batch = []
                for row in result.result_set:
                    uuid_val = row[0]
                    source_uuid = row[1]
                    target_uuid = row[2]
                    props = row[3] if row[3] else {}

                    edge_data = {
                        'uuid': uuid_val,
                        'source_node_uuid': source_uuid,
                        'target_node_uuid': target_uuid,
                        'relationship_type': 'RELATES_TO',
                        **props,
                    }

                    batch.append(self._convert_edge_result(edge_data))

                    if len(batch) >= self._resolve_batch_limit('entity_edges'):
                        yield batch
                        total_processed += len(batch)
                        batch = []

                # Yield remaining items in batch
                if batch:
                    yield batch
                    total_processed += len(batch)

                # Check if we got 0 results - indicates end of data
                # Note: Don't break just because we got fewer than max_query_limit results,
                # as this can happen with NULL values being filtered differently
                if len(result.result_set) == 0:
                    logger.info(
                        f'Entity edges extraction completed. Total processed: {total_processed}'
                    )
                    break

                # Move to next page
                offset += page_limit
                logger.debug(
                    f'Processed {total_processed} entity edges, continuing with offset {offset}'
                )

            except Exception as e:
                logger.error(f'Failed to extract entity edges at offset {offset}: {e}')
                raise

    async def _extract_entity_edges_single_query(
        self, since_timestamp: Optional[datetime] = None, limit: Optional[int] = None
    ) -> AsyncIterator[List[Dict[str, Any]]]:
        """Legacy single-query extraction method."""
        where_clause = ''
        if since_timestamp:
            iso_timestamp = since_timestamp.isoformat()
            where_clause = f"WHERE r.updated_at > '{iso_timestamp}' OR r.created_at > '{iso_timestamp}' OR r.updated_at IS NULL OR r.created_at IS NULL"

        query = f"""
        MATCH (source)-[r:RELATES_TO]->(target)
        {where_clause}
        RETURN r.uuid as uuid, source.uuid as source_uuid, target.uuid as target_uuid, properties(r) as props
        ORDER BY r.uuid
        """

        if limit:
            query += f' LIMIT {limit}'

        try:
            result = await self.graph.query(query)
            if not result.result_set:
                return

            batch = []
            for row in result.result_set:
                uuid_val = row[0]
                source_uuid = row[1]
                target_uuid = row[2]
                props = row[3] if row[3] else {}

                edge_data = {
                    'uuid': uuid_val,
                    'source_node_uuid': source_uuid,
                    'target_node_uuid': target_uuid,
                    'relationship_type': 'RELATES_TO',
                    **props,
                }

                batch.append(self._convert_edge_result(edge_data))

                if len(batch) >= self._resolve_batch_limit('entity_edges', limit):
                    yield batch
                    batch = []

            if batch:
                yield batch

        except Exception as e:
            logger.error(f'Failed to extract entity edges: {e}')
            raise

    async def extract_episodic_edges(
        self, since_timestamp: Optional[datetime] = None, limit: Optional[int] = None
    ) -> AsyncIterator[List[Dict[str, Any]]]:
        """Extract episodic edges (MENTIONS) in batches with pagination."""
        if not self.graph:
            raise RuntimeError('Not connected to FalkorDB')

        # Use pagination if enabled and no explicit limit is provided
        if self.enable_pagination and limit is None:
            async for batch in self._extract_episodic_edges_paginated(since_timestamp):
                yield batch
        else:
            # Legacy method for backward compatibility or explicit limits
            async for batch in self._extract_episodic_edges_single_query(since_timestamp, limit):
                yield batch

    async def _extract_episodic_edges_paginated(
        self, since_timestamp: Optional[datetime] = None
    ) -> AsyncIterator[List[Dict[str, Any]]]:
        """Extract episodic edges using cursor-based pagination."""
        offset = 0
        total_processed = 0

        while True:
            where_clause = ''
            if since_timestamp:
                iso_timestamp = since_timestamp.isoformat()
                where_clause = f"WHERE r.updated_at > '{iso_timestamp}' OR r.created_at > '{iso_timestamp}' OR r.updated_at IS NULL OR r.created_at IS NULL"

            # Use SKIP/LIMIT for pagination to avoid unbounded ORDER BY
            # Use UUID for stable pagination instead of created_at to avoid NULL value issues
            page_limit = self._resolve_query_limit('episodic_edges')
            query = f"""
            MATCH (episode:Episodic)-[r:MENTIONS]->(entity:Entity)
            {where_clause}
            RETURN r.uuid as uuid, episode.uuid as source_uuid, entity.uuid as target_uuid, properties(r) as props
            ORDER BY r.uuid
            SKIP {offset} LIMIT {page_limit}
            """

            try:
                result = await self.graph.query(query)
                if not result.result_set:
                    logger.info(
                        f'Episodic edges extraction completed. Total processed: {total_processed}'
                    )
                    break

                batch = []
                for row in result.result_set:
                    uuid_val = row[0]
                    source_uuid = row[1]
                    target_uuid = row[2]
                    props = row[3] if row[3] else {}

                    edge_data = {
                        'uuid': uuid_val,
                        'source_node_uuid': source_uuid,
                        'target_node_uuid': target_uuid,
                        'relationship_type': 'MENTIONS',
                        **props,
                    }

                    batch.append(self._convert_edge_result(edge_data))

                    if len(batch) >= self._resolve_batch_limit('episodic_edges'):
                        yield batch
                        total_processed += len(batch)
                        batch = []

                # Yield remaining items in batch
                if batch:
                    yield batch
                    total_processed += len(batch)

                # Check if we got 0 results - indicates end of data
                # Note: Don't break just because we got fewer than max_query_limit results,
                # as this can happen with NULL values being filtered differently
                if len(result.result_set) == 0:
                    logger.info(
                        f'Episodic edges extraction completed. Total processed: {total_processed}'
                    )
                    break

                # Move to next page
                offset += page_limit
                logger.debug(
                    f'Processed {total_processed} episodic edges, continuing with offset {offset}'
                )

            except Exception as e:
                logger.error(f'Failed to extract episodic edges at offset {offset}: {e}')
                raise

    async def _extract_episodic_edges_single_query(
        self, since_timestamp: Optional[datetime] = None, limit: Optional[int] = None
    ) -> AsyncIterator[List[Dict[str, Any]]]:
        """Legacy single-query extraction method."""
        where_clause = ''
        if since_timestamp:
            iso_timestamp = since_timestamp.isoformat()
            where_clause = f"WHERE r.updated_at > '{iso_timestamp}' OR r.created_at > '{iso_timestamp}' OR r.updated_at IS NULL OR r.created_at IS NULL"

        query = f"""
        MATCH (episode:Episodic)-[r:MENTIONS]->(entity:Entity)
        {where_clause}
        RETURN r.uuid as uuid, episode.uuid as source_uuid, entity.uuid as target_uuid, properties(r) as props
        ORDER BY r.uuid
        """

        if limit:
            query += f' LIMIT {limit}'

        try:
            result = await self.graph.query(query)
            if not result.result_set:
                return

            batch = []
            for row in result.result_set:
                uuid_val = row[0]
                source_uuid = row[1]
                target_uuid = row[2]
                props = row[3] if row[3] else {}

                edge_data = {
                    'uuid': uuid_val,
                    'source_node_uuid': source_uuid,
                    'target_node_uuid': target_uuid,
                    'relationship_type': 'MENTIONS',
                    **props,
                }

                batch.append(self._convert_edge_result(edge_data))

                if len(batch) >= self._resolve_batch_limit('episodic_edges', limit):
                    yield batch
                    batch = []

            if batch:
                yield batch

        except Exception as e:
            logger.error(f'Failed to extract episodic edges: {e}')
            raise

    async def extract_all_data(
        self, since_timestamp: Optional[datetime] = None
    ) -> Tuple[AsyncIterator[Tuple[str, List[Dict[str, Any]]]], ExtractionStats]:
        """
        Extract all data from FalkorDB.

        Returns:
            AsyncIterator yielding (data_type, batch) tuples and extraction statistics
        """
        stats = ExtractionStats()
        start_time = asyncio.get_event_loop().time()

        async def data_generator():
            # Extract entity nodes
            async for batch in self.extract_entity_nodes(since_timestamp):
                stats.entity_nodes += len(batch)
                yield ('entity_nodes', batch)

            # Extract episodic nodes
            async for batch in self.extract_episodic_nodes(since_timestamp):
                stats.episodic_nodes += len(batch)
                yield ('episodic_nodes', batch)

            # Extract community nodes
            async for batch in self.extract_community_nodes(since_timestamp):
                stats.community_nodes += len(batch)
                yield ('community_nodes', batch)

            # Extract entity edges
            async for batch in self.extract_entity_edges(since_timestamp):
                stats.entity_edges += len(batch)
                yield ('entity_edges', batch)

            # Extract episodic edges
            async for batch in self.extract_episodic_edges(since_timestamp):
                stats.episodic_edges += len(batch)
                yield ('episodic_edges', batch)

            # Calculate final stats
            end_time = asyncio.get_event_loop().time()
            stats.extraction_time_seconds = end_time - start_time

            logger.info(
                f'FalkorDB extraction completed: {stats.entity_nodes} entities, '
                f'{stats.episodic_nodes} episodes, {stats.community_nodes} communities, '
                f'{stats.entity_edges} entity edges, {stats.episodic_edges} episodic edges '
                f'in {stats.extraction_time_seconds:.2f}s'
            )

        return data_generator(), stats
