"""
Mock implementations of GraphDriver and GraphDriverSession.

Provides in-memory storage for testing database-dependent code without
actual Neo4j/FalkorDB connections.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4


@dataclass
class MockNode:
    """In-memory representation of a graph node."""

    uuid: str
    labels: list[str]
    properties: dict[str, Any]


@dataclass
class MockRelationship:
    """In-memory representation of a graph relationship."""

    uuid: str
    source_uuid: str
    target_uuid: str
    rel_type: str
    properties: dict[str, Any]


class MockGraphDriverSession:
    """
    Mock implementation of GraphDriverSession for testing.

    Provides async context manager support and basic query execution.
    """

    def __init__(self, driver: 'MockGraphDriver', database: str | None = None):
        self.driver = driver
        self.database = database
        self._closed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.close()

    async def run(self, query: str, **kwargs: Any) -> list[dict[str, Any]]:
        """Execute a query and return results."""
        if self._closed:
            raise RuntimeError('Session is closed')
        results, _, _ = await self.driver.execute_query(query, **kwargs)
        return results

    async def close(self):
        """Close the session."""
        self._closed = False

    async def execute_write(self, func, *args, **kwargs):
        """Execute a write transaction."""
        return await func(self, *args, **kwargs)


class MockGraphDriver:
    """
    Mock implementation of GraphDriver for testing.

    Provides in-memory node and relationship storage with basic
    Cypher query pattern matching.

    Attributes:
        provider: The database provider name (default: 'mock')
        fulltext_syntax: Fulltext query syntax prefix (default: '')
        nodes: Dictionary of nodes by UUID
        relationships: Dictionary of relationships by UUID
        query_log: List of executed queries (for debugging)
        canned_responses: Pre-configured responses for specific queries
    """

    provider: str = 'mock'
    fulltext_syntax: str = ''

    def __init__(self):
        self.nodes: dict[str, MockNode] = {}
        self.relationships: dict[str, MockRelationship] = {}
        self.query_log: list[tuple[str, dict]] = []
        self.canned_responses: dict[str, list[dict[str, Any]]] = {}
        self._closed = False

    def add_canned_response(self, query_pattern: str, response: list[dict[str, Any]]):
        """
        Add a canned response for queries matching a pattern.

        Args:
            query_pattern: Regex pattern or exact query string
            response: List of result records to return
        """
        self.canned_responses[query_pattern] = response

    def add_node(
        self,
        uuid: str | None = None,
        labels: list[str] | None = None,
        properties: dict[str, Any] | None = None,
    ) -> MockNode:
        """
        Add a node to the mock database.

        Args:
            uuid: Node UUID (generated if not provided)
            labels: Node labels (default: ['Entity'])
            properties: Node properties (default: {})

        Returns:
            The created MockNode
        """
        uuid = uuid or str(uuid4())
        labels = labels or ['Entity']
        properties = properties or {}
        properties['uuid'] = uuid

        node = MockNode(uuid=uuid, labels=labels, properties=properties)
        self.nodes[uuid] = node
        return node

    def add_relationship(
        self,
        source_uuid: str,
        target_uuid: str,
        rel_type: str,
        uuid: str | None = None,
        properties: dict[str, Any] | None = None,
    ) -> MockRelationship:
        """
        Add a relationship to the mock database.

        Args:
            source_uuid: Source node UUID
            target_uuid: Target node UUID
            rel_type: Relationship type
            uuid: Relationship UUID (generated if not provided)
            properties: Relationship properties (default: {})

        Returns:
            The created MockRelationship
        """
        uuid = uuid or str(uuid4())
        properties = properties or {}
        properties['uuid'] = uuid

        rel = MockRelationship(
            uuid=uuid,
            source_uuid=source_uuid,
            target_uuid=target_uuid,
            rel_type=rel_type,
            properties=properties,
        )
        self.relationships[uuid] = rel
        return rel

    def get_node(self, uuid: str) -> MockNode | None:
        """Get a node by UUID."""
        return self.nodes.get(uuid)

    def get_relationships_for_node(
        self, uuid: str, direction: str = 'both'
    ) -> list[MockRelationship]:
        """
        Get relationships connected to a node.

        Args:
            uuid: Node UUID
            direction: 'incoming', 'outgoing', or 'both'

        Returns:
            List of relationships
        """
        results = []
        for rel in self.relationships.values():
            if direction in ('incoming', 'both') and rel.target_uuid == uuid:
                results.append(rel)
            if direction in ('outgoing', 'both') and rel.source_uuid == uuid:
                results.append(rel)
        return results

    def clear(self):
        """Clear all nodes and relationships."""
        self.nodes.clear()
        self.relationships.clear()
        self.query_log.clear()

    async def execute_query(
        self, cypher_query_: str, **kwargs: Any
    ) -> tuple[list[dict[str, Any]], Any, Any]:
        """
        Execute a Cypher query and return results.

        This mock implementation supports:
        - Canned responses for specific query patterns
        - Basic MATCH (n:Label {uuid: $uuid}) patterns
        - COUNT queries
        - Basic relationship patterns

        Args:
            cypher_query_: The Cypher query string
            **kwargs: Query parameters

        Returns:
            Tuple of (results, None, None) - mimics Neo4j driver return format
        """
        self.query_log.append((cypher_query_, kwargs))

        # Check for canned responses
        for pattern, response in self.canned_responses.items():
            if pattern in cypher_query_ or re.search(pattern, cypher_query_):
                return (response, None, None)

        # Parse basic patterns
        results = self._execute_basic_query(cypher_query_, kwargs)
        return (results, None, None)

    def _execute_basic_query(self, query: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Execute basic query patterns.

        Supports:
        - MATCH (n:Entity {uuid: $uuid})
        - MATCH (n:Entity) WHERE n.name = $name
        - COUNT queries
        - MATCH (n)-[r]->(m) relationship patterns
        """
        query_lower = query.lower()

        # Handle COUNT queries
        if 'count(' in query_lower:
            if 'match (n:entity' in query_lower or 'match (n)' in query_lower:
                return [{'count': len(self.nodes)}]
            if 'match ()-[r]->' in query_lower or 'match (n)-[r]' in query_lower:
                return [{'count': len(self.relationships)}]
            return [{'count': 0}]

        # Handle UUID-based lookups
        uuid = params.get('uuid') or params.get('canonical_uuid') or params.get('duplicate_uuid')
        if uuid and 'match' in query_lower:
            node = self.nodes.get(uuid)
            if node:
                # Create a mock record object
                record = {
                    'n': type('MockRecord', (), {'properties': node.properties})(),
                    'uuid': node.uuid,
                    'name': node.properties.get('name'),
                    'group_id': node.properties.get('group_id'),
                    'labels': node.labels,
                    'summary': node.properties.get('summary', ''),
                    'name_embedding': node.properties.get('name_embedding'),
                    'created_at': node.properties.get('created_at'),
                }
                return [record]
            return []

        # Handle name-based lookups
        name = params.get('name')
        group_id = params.get('group_id')
        if name and 'where n.name' in query_lower:
            for node in self.nodes.values():
                if node.properties.get('name') == name:
                    if group_id and node.properties.get('group_id') != group_id:
                        continue
                    record = {
                        'n': type('MockRecord', (), {'properties': node.properties})(),
                        'uuid': node.uuid,
                        'name': node.properties.get('name'),
                        'group_id': node.properties.get('group_id'),
                        'labels': node.labels,
                    }
                    return [record]
            return []

        # Handle relationship queries
        if '-[r]->' in query_lower or '-[r]-' in query_lower:
            results = []
            for rel in self.relationships.values():
                source = self.nodes.get(rel.source_uuid)
                target = self.nodes.get(rel.target_uuid)
                if source and target:
                    results.append(
                        {
                            'source_uuid': rel.source_uuid,
                            'target_uuid': rel.target_uuid,
                            'rel_type': rel.rel_type,
                            'props': rel.properties,
                        }
                    )
            return results

        # Default: return empty results
        return []

    def session(self, database: str | None = None) -> MockGraphDriverSession:
        """Create a new session."""
        return MockGraphDriverSession(self, database)

    def close(self):
        """Close the driver."""
        self._closed = True

    async def delete_all_indexes(self, database_: str | None = None):
        """Delete all indexes (no-op for mock)."""
        pass
