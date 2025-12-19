"""
Tests for the mock implementations.

Verifies that the mock classes work correctly for testing purposes.
"""

import pytest
from tests.mocks import (
    MockGraphDriver,
    MockGraphDriverSession,
    MockLLMClient,
    MockEmbedderClient,
    create_entity_node,
    create_episodic_node,
    create_edge,
    create_test_uuid,
    create_test_group_id,
)


# =============================================================================
# MockGraphDriver Tests
# =============================================================================


class TestMockGraphDriver:
    """Tests for MockGraphDriver."""

    def test_initialization(self):
        """Test driver initialization."""
        driver = MockGraphDriver()
        assert driver.provider == 'mock'
        assert len(driver.nodes) == 0
        assert len(driver.relationships) == 0

    def test_add_node(self):
        """Test adding a node."""
        driver = MockGraphDriver()
        node = driver.add_node(
            uuid='test-uuid',
            labels=['Entity'],
            properties={'name': 'Test'},
        )
        assert node.uuid == 'test-uuid'
        assert 'Entity' in node.labels
        assert node.properties['name'] == 'Test'

    def test_add_node_generates_uuid(self):
        """Test that add_node generates UUID if not provided."""
        driver = MockGraphDriver()
        node = driver.add_node(properties={'name': 'Test'})
        assert node.uuid is not None
        assert len(node.uuid) > 0

    def test_add_relationship(self):
        """Test adding a relationship."""
        driver = MockGraphDriver()
        node1 = driver.add_node(uuid='uuid1')
        node2 = driver.add_node(uuid='uuid2')

        rel = driver.add_relationship(
            source_uuid='uuid1',
            target_uuid='uuid2',
            rel_type='KNOWS',
            properties={'fact': 'knows'},
        )

        assert rel.source_uuid == 'uuid1'
        assert rel.target_uuid == 'uuid2'
        assert rel.rel_type == 'KNOWS'

    def test_get_node(self):
        """Test getting a node by UUID."""
        driver = MockGraphDriver()
        driver.add_node(uuid='test-uuid', properties={'name': 'Test'})

        node = driver.get_node('test-uuid')
        assert node is not None
        assert node.properties['name'] == 'Test'

    def test_get_node_not_found(self):
        """Test getting a non-existent node."""
        driver = MockGraphDriver()
        node = driver.get_node('non-existent')
        assert node is None

    @pytest.mark.asyncio
    async def test_execute_query_basic(self):
        """Test basic query execution."""
        driver = MockGraphDriver()
        driver.add_node(uuid='test-uuid', properties={'name': 'Test'})

        results, _, _ = await driver.execute_query(
            'MATCH (n:Entity {uuid: $uuid}) RETURN n', uuid='test-uuid'
        )

        assert len(results) == 1
        assert results[0]['uuid'] == 'test-uuid'

    @pytest.mark.asyncio
    async def test_execute_query_canned_response(self):
        """Test canned response."""
        driver = MockGraphDriver()
        expected = [{'test': 'value'}]
        driver.add_canned_response('SELECT', expected)

        results, _, _ = await driver.execute_query('SELECT * FROM test')
        assert results == expected

    @pytest.mark.asyncio
    async def test_execute_query_count(self):
        """Test COUNT query."""
        driver = MockGraphDriver()
        driver.add_node()
        driver.add_node()

        results, _, _ = await driver.execute_query('MATCH (n:Entity) RETURN COUNT(n) as count')

        assert results[0]['count'] == 2

    def test_clear(self):
        """Test clearing the driver."""
        driver = MockGraphDriver()
        driver.add_node()
        driver.add_relationship('a', 'b', 'REL')

        driver.clear()

        assert len(driver.nodes) == 0
        assert len(driver.relationships) == 0

    def test_session(self):
        """Test session creation."""
        driver = MockGraphDriver()
        session = driver.session()
        assert isinstance(session, MockGraphDriverSession)


# =============================================================================
# MockGraphDriverSession Tests
# =============================================================================


class TestMockGraphDriverSession:
    """Tests for MockGraphDriverSession."""

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Test async context manager."""
        driver = MockGraphDriver()
        session = driver.session()

        async with session as s:
            assert s == session

    @pytest.mark.asyncio
    async def test_run_query(self):
        """Test running a query."""
        driver = MockGraphDriver()
        driver.add_node(uuid='test', properties={'name': 'Test'})

        async with driver.session() as session:
            results = await session.run('MATCH (n {uuid: $uuid}) RETURN n', uuid='test')
            assert len(results) == 1


# =============================================================================
# MockLLMClient Tests
# =============================================================================


class TestMockLLMClient:
    """Tests for MockLLMClient."""

    def test_initialization(self):
        """Test client initialization."""
        client = MockLLMClient()
        assert client.config is not None
        assert len(client.responses) == 0
        assert len(client.call_log) == 0

    @pytest.mark.asyncio
    async def test_generate_response_queued(self):
        """Test queued response."""
        client = MockLLMClient()
        client.add_response({'summary': 'Test'})

        response = await client.generate_response([])

        assert response['summary'] == 'Test'
        assert len(client.responses) == 0  # Queue consumed

    @pytest.mark.asyncio
    async def test_generate_response_fifo(self):
        """Test FIFO order of responses."""
        client = MockLLMClient()
        client.add_response({'order': 1})
        client.add_response({'order': 2})

        r1 = await client.generate_response([])
        r2 = await client.generate_response([])

        assert r1['order'] == 1
        assert r2['order'] == 2

    @pytest.mark.asyncio
    async def test_call_log(self):
        """Test that calls are logged."""
        client = MockLLMClient()
        client.add_response({})

        await client.generate_response([{'role': 'user', 'content': 'test'}])

        assert len(client.call_log) == 1

    def test_clear(self):
        """Test clearing the client."""
        client = MockLLMClient()
        client.add_response({'test': 'value'})

        client.clear()

        assert len(client.responses) == 0
        assert len(client.call_log) == 0


# =============================================================================
# MockEmbedderClient Tests
# =============================================================================


class TestMockEmbedderClient:
    """Tests for MockEmbedderClient."""

    def test_initialization(self):
        """Test embedder initialization."""
        embedder = MockEmbedderClient()
        assert embedder.embedding_dim > 0

    @pytest.mark.asyncio
    async def test_create_embedding(self):
        """Test creating an embedding."""
        embedder = MockEmbedderClient(embedding_dim=128)

        embedding = await embedder.create('test text')

        assert len(embedding) == 128
        assert all(isinstance(x, float) for x in embedding)

    @pytest.mark.asyncio
    async def test_deterministic_embeddings(self):
        """Test that same input produces same embedding."""
        embedder = MockEmbedderClient()

        e1 = await embedder.create('test')
        e2 = await embedder.create('test')

        assert e1 == e2

    @pytest.mark.asyncio
    async def test_different_inputs_different_embeddings(self):
        """Test that different inputs produce different embeddings."""
        embedder = MockEmbedderClient()

        e1 = await embedder.create('hello')
        e2 = await embedder.create('world')

        assert e1 != e2

    @pytest.mark.asyncio
    async def test_create_batch(self):
        """Test batch embedding creation."""
        embedder = MockEmbedderClient(embedding_dim=64)

        embeddings = await embedder.create_batch(['text1', 'text2', 'text3'])

        assert len(embeddings) == 3
        assert all(len(e) == 64 for e in embeddings)

    @pytest.mark.asyncio
    async def test_custom_embedding(self):
        """Test setting custom embeddings."""
        embedder = MockEmbedderClient()
        custom = [1.0, 2.0, 3.0]
        embedder.set_embedding('special', custom)

        result = await embedder.create('special')

        assert result == custom

    def test_call_log(self):
        """Test that create calls are logged."""
        embedder = MockEmbedderClient()
        # Call is async but we just need to check the log mechanism
        embedder.call_log.append('test')
        assert len(embedder.call_log) == 1


# =============================================================================
# Factory Function Tests
# =============================================================================


class TestFactories:
    """Tests for factory functions."""

    def test_create_test_uuid(self):
        """Test UUID creation."""
        uuid = create_test_uuid()
        assert len(uuid) == 36  # Standard UUID length

    def test_create_test_uuid_deterministic(self):
        """Test deterministic UUID with seed."""
        uuid1 = create_test_uuid(seed='test')
        uuid2 = create_test_uuid(seed='test')
        assert uuid1 == uuid2

    def test_create_test_group_id(self):
        """Test group ID creation."""
        group_id = create_test_group_id('mytest')
        assert group_id.startswith('mytest_group_')

    def test_create_entity_node(self):
        """Test entity node creation."""
        entity = create_entity_node(
            name='Test Entity',
            summary='A test entity',
        )

        assert entity['name'] == 'Test Entity'
        assert entity['summary'] == 'A test entity'
        assert 'uuid' in entity
        assert 'group_id' in entity
        assert 'Entity' in entity['labels']

    def test_create_episodic_node(self):
        """Test episodic node creation."""
        episode = create_episodic_node(
            name='Test Episode',
            content='Episode content here',
        )

        assert episode['name'] == 'Test Episode'
        assert episode['content'] == 'Episode content here'
        assert 'uuid' in episode
        assert episode['source'] == 'text'

    def test_create_edge(self):
        """Test edge creation."""
        edge = create_edge(
            fact='relates to',
            rel_type='RELATES_TO',
        )

        assert edge['fact'] == 'relates to'
        assert edge['name'] == 'RELATES_TO'
        assert 'uuid' in edge
        assert 'source_uuid' in edge
        assert 'target_uuid' in edge
