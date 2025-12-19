"""
Mock implementations for Graphiti testing.

This module provides comprehensive mock implementations of key Graphiti interfaces:
- MockGraphDriver: Simulates database operations (Neo4j/FalkorDB)
- MockGraphDriverSession: Simulates database sessions
- MockLLMClient: Simulates LLM responses
- MockEmbedderClient: Returns fake embeddings

These mocks enable unit testing of database-dependent code without actual database connections.
"""

from .driver import MockGraphDriver, MockGraphDriverSession
from .llm_client import MockLLMClient
from .embedder import MockEmbedderClient
from .factories import (
    create_entity_node,
    create_episodic_node,
    create_edge,
    create_test_group_id,
    create_test_uuid,
)

__all__ = [
    'MockGraphDriver',
    'MockGraphDriverSession',
    'MockLLMClient',
    'MockEmbedderClient',
    'create_entity_node',
    'create_episodic_node',
    'create_edge',
    'create_test_group_id',
    'create_test_uuid',
]
