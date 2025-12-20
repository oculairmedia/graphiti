"""
Pytest configuration and shared fixtures for Graphiti tests.

This module provides:
- Mock fixtures for database, LLM, and embedder
- Test data factories
- Common test utilities
"""

import os
import sys
from datetime import datetime, timezone

import pytest

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from tests.mocks import (
    MockGraphDriver,
    MockGraphDriverSession,
    MockLLMClient,
    MockEmbedderClient,
    create_entity_node,
    create_episodic_node,
    create_edge,
    create_test_group_id,
    create_test_uuid,
)


# =============================================================================
# Mock Fixtures
# =============================================================================


@pytest.fixture
def mock_driver():
    """
    Provide a MockGraphDriver for testing database operations.

    The driver is cleared between tests.

    Usage:
        def test_something(mock_driver):
            mock_driver.add_node(uuid='123', properties={'name': 'Test'})
            # Test code that uses driver...
    """
    driver = MockGraphDriver()
    yield driver
    driver.clear()


@pytest.fixture
def mock_session(mock_driver):
    """
    Provide a MockGraphDriverSession for testing session operations.

    Usage:
        async def test_session(mock_session):
            async with mock_session as session:
                results = await session.run("MATCH (n) RETURN n")
    """
    return mock_driver.session()


@pytest.fixture
def mock_llm_client():
    """
    Provide a MockLLMClient for testing LLM-dependent code.

    Usage:
        def test_with_llm(mock_llm_client):
            mock_llm_client.add_response({'summary': 'Test summary'})
            # Test code that uses LLM...
    """
    client = MockLLMClient()
    yield client
    client.clear()


@pytest.fixture
def mock_embedder():
    """
    Provide a MockEmbedderClient for testing embedding-dependent code.

    Usage:
        async def test_with_embedder(mock_embedder):
            embedding = await mock_embedder.create("test text")
            assert len(embedding) == mock_embedder.embedding_dim
    """
    embedder = MockEmbedderClient()
    yield embedder
    embedder.clear()


# =============================================================================
# Test Data Fixtures
# =============================================================================


@pytest.fixture
def test_group_id():
    """Provide a consistent test group ID."""
    return 'test_group_001'


@pytest.fixture
def test_uuid():
    """Provide a consistent test UUID."""
    return create_test_uuid(seed='test_entity')


@pytest.fixture
def sample_entity(test_group_id):
    """Provide a sample entity node dict."""
    return create_entity_node(
        name='Test Entity',
        group_id=test_group_id,
        summary='A test entity for unit testing',
    )


@pytest.fixture
def sample_entities(test_group_id):
    """Provide a list of sample entity node dicts."""
    return [
        create_entity_node(name='Alice', group_id=test_group_id),
        create_entity_node(name='Bob', group_id=test_group_id),
        create_entity_node(name='Charlie', group_id=test_group_id),
    ]


@pytest.fixture
def sample_episode(test_group_id):
    """Provide a sample episodic node dict."""
    return create_episodic_node(
        name='Test Episode',
        content='Alice met Bob at the coffee shop. They discussed work.',
        group_id=test_group_id,
    )


@pytest.fixture
def sample_episodes(test_group_id):
    """Provide a list of sample episodic node dicts."""
    return [
        create_episodic_node(
            name='episode_1',
            content='User discussed project plans with team.',
            group_id=test_group_id,
        ),
        create_episodic_node(
            name='episode_2',
            content='Team meeting about quarterly goals completed.',
            group_id=test_group_id,
        ),
        create_episodic_node(
            name='episode_3',
            content='Code review session for new features.',
            group_id=test_group_id,
        ),
    ]


@pytest.fixture
def sample_edge(test_group_id):
    """Provide a sample edge dict."""
    source = create_entity_node(name='Alice', group_id=test_group_id)
    target = create_entity_node(name='Bob', group_id=test_group_id)
    return create_edge(
        source_uuid=source['uuid'],
        target_uuid=target['uuid'],
        group_id=test_group_id,
        fact='Alice knows Bob',
    )


# =============================================================================
# Pre-populated Mock Fixtures
# =============================================================================


@pytest.fixture
def populated_driver(mock_driver, sample_entities):
    """
    Provide a MockGraphDriver pre-populated with sample entities.

    Contains Alice, Bob, and Charlie entities.
    """
    for entity in sample_entities:
        mock_driver.add_node(
            uuid=entity['uuid'],
            labels=entity['labels'],
            properties=entity,
        )
    return mock_driver


@pytest.fixture
def populated_driver_with_relationships(populated_driver, test_group_id):
    """
    Provide a MockGraphDriver with entities and relationships.

    Contains:
    - Alice, Bob, Charlie entities
    - Alice -> Bob (KNOWS)
    - Bob -> Charlie (WORKS_WITH)
    """
    nodes = list(populated_driver.nodes.values())
    if len(nodes) >= 2:
        populated_driver.add_relationship(
            source_uuid=nodes[0].uuid,
            target_uuid=nodes[1].uuid,
            rel_type='KNOWS',
            properties={
                'fact': 'Alice knows Bob',
                'group_id': test_group_id,
            },
        )
    if len(nodes) >= 3:
        populated_driver.add_relationship(
            source_uuid=nodes[1].uuid,
            target_uuid=nodes[2].uuid,
            rel_type='WORKS_WITH',
            properties={
                'fact': 'Bob works with Charlie',
                'group_id': test_group_id,
            },
        )
    return populated_driver


# =============================================================================
# Integration Test Fixtures
# =============================================================================


@pytest.fixture
def neo4j_config():
    """
    Provide Neo4j connection configuration for integration tests.

    Uses environment variables or defaults suitable for local development.
    Integration tests using this fixture should be marked with @pytest.mark.integration.

    Environment variables:
        - NEO4J_URI: Neo4j connection URI (default: bolt://localhost:7687)
        - NEO4J_USER: Neo4j username (default: neo4j)
        - NEO4J_PASSWORD: Neo4j password (default: graphiti123)

    Usage:
        @pytest.mark.integration
        async def test_with_neo4j(neo4j_config):
            graphiti = Graphiti(
                neo4j_uri=neo4j_config['uri'],
                neo4j_user=neo4j_config['user'],
                neo4j_password=neo4j_config['password'],
            )
    """
    return {
        'uri': os.environ.get('NEO4J_URI', 'bolt://localhost:7687'),
        'user': os.environ.get('NEO4J_USER', 'neo4j'),
        'password': os.environ.get('NEO4J_PASSWORD', 'graphiti123'),
    }


# =============================================================================
# Environment Fixtures
# =============================================================================


@pytest.fixture
def clean_environment():
    """
    Provide a clean environment with test-specific env vars.

    Restores original environment after test.
    """
    original_env = os.environ.copy()

    # Set test-specific environment
    os.environ['DEDUP_NORMALIZE_NAMES'] = 'true'
    os.environ['ENABLE_AGGRESSIVE_DEDUP'] = 'true'
    os.environ['DEDUP_FUZZY_THRESHOLD'] = '0.9'
    os.environ['EMBEDDING_DIMENSION'] = '2560'

    yield

    # Restore original environment
    os.environ.clear()
    os.environ.update(original_env)


@pytest.fixture
def disable_normalization():
    """
    Temporarily disable name normalization.

    Useful for testing raw name behavior.
    """
    original = os.environ.get('DEDUP_NORMALIZE_NAMES')
    os.environ['DEDUP_NORMALIZE_NAMES'] = 'false'

    yield

    if original is not None:
        os.environ['DEDUP_NORMALIZE_NAMES'] = original
    else:
        os.environ.pop('DEDUP_NORMALIZE_NAMES', None)


# =============================================================================
# Utility Fixtures
# =============================================================================


@pytest.fixture
def now():
    """Provide current UTC datetime."""
    return datetime.now(timezone.utc)


@pytest.fixture
def event_loop_policy():
    """Configure event loop policy for async tests."""
    import asyncio

    return asyncio.DefaultEventLoopPolicy()


# =============================================================================
# Markers Configuration
# =============================================================================


def pytest_configure(config):
    """Configure pytest markers."""
    config.addinivalue_line('markers', 'integration: marks tests as integration tests')
    config.addinivalue_line('markers', 'slow: marks tests as slow running')
    config.addinivalue_line('markers', 'requires_db: marks tests that require database connection')
    config.addinivalue_line('markers', 'requires_llm: marks tests that require LLM connection')
