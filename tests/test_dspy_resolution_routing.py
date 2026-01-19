"""
Tests for DSPy resolution routing in Graphiti.

Verifies that when use_dspy=True, node resolution routes through
the DSPy NodeResolver instead of the legacy resolve_extracted_nodes.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
from uuid import uuid4

from graphiti_core.graphiti import Graphiti
from graphiti_core.nodes import EntityNode, EpisodicNode, EpisodeType
from graphiti_core.utils.resilient_ingestion import ResilientIngestionState
from graphiti_core.dspy.signatures import NodeResolutions, NodeDuplicate


@pytest.fixture
def mock_driver():
    driver = MagicMock()
    driver.provider = 'mock'
    driver.execute_query = AsyncMock(return_value=([], None, None))
    return driver


@pytest.fixture
def mock_llm_client():
    client = MagicMock()
    client.generate_response = AsyncMock(return_value={})
    return client


@pytest.fixture
def mock_embedder():
    embedder = MagicMock()
    embedder.create = AsyncMock(return_value=[0.1] * 1024)
    return embedder


@pytest.fixture
def graphiti_instance(mock_driver, mock_llm_client, mock_embedder):
    graphiti = Graphiti.__new__(Graphiti)
    graphiti.driver = mock_driver
    graphiti.llm_client = mock_llm_client
    graphiti.embedder = mock_embedder
    graphiti.use_dspy = False
    graphiti.enable_cross_graph_deduplication = False
    graphiti.clients = MagicMock()
    graphiti.clients.driver = mock_driver
    graphiti.clients.llm_client = mock_llm_client
    graphiti.clients.embedder = mock_embedder
    return graphiti


@pytest.fixture
def sample_episode():
    return EpisodicNode(
        uuid=str(uuid4()),
        name='test-episode',
        group_id='test-group',
        source=EpisodeType.text,
        source_description='Test source',
        content='Emmanuel is working on the Graphiti project.',
        created_at=datetime.now(timezone.utc),
        valid_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def sample_extracted_nodes():
    now = datetime.now(timezone.utc)
    node1_uuid = str(uuid4())
    node2_uuid = str(uuid4())
    return [
        EntityNode(
            uuid=node1_uuid,
            name='Emmanuel',
            group_id='test-group',
            labels=['Person'],
            created_at=now,
            summary='',
        ),
        EntityNode(
            uuid=node2_uuid,
            name='Graphiti',
            group_id='test-group',
            labels=['Project'],
            created_at=now,
            summary='',
        ),
    ]


@pytest.fixture
def sample_state():
    return ResilientIngestionState(episode_id=str(uuid4()), group_id='test-group')


class TestDSPyResolutionRouting:
    @pytest.mark.asyncio
    async def test_resolve_nodes_uses_legacy_when_dspy_disabled(
        self, graphiti_instance, sample_extracted_nodes, sample_episode, sample_state
    ):
        graphiti_instance.use_dspy = False

        with patch(
            'graphiti_core.graphiti.resolve_extracted_nodes',
            new_callable=AsyncMock,
        ) as mock_legacy:
            mock_legacy.return_value = (sample_extracted_nodes, {}, [])

            result = await graphiti_instance._resolve_nodes_with_retry(
                sample_extracted_nodes,
                sample_episode,
                [],
                None,
                sample_state,
            )

            mock_legacy.assert_called_once()
            assert len(result[0]) == 2

    @pytest.mark.asyncio
    async def test_resolve_nodes_uses_dspy_when_enabled(
        self, graphiti_instance, sample_extracted_nodes, sample_episode, sample_state
    ):
        graphiti_instance.use_dspy = True

        uuid_map = {node.uuid: node.uuid for node in sample_extracted_nodes}

        with patch.object(
            graphiti_instance,
            '_resolve_nodes_dspy',
            new_callable=AsyncMock,
        ) as mock_dspy:
            mock_dspy.return_value = (
                sample_extracted_nodes,
                uuid_map,
                [],
            )

            result = await graphiti_instance._resolve_nodes_with_retry(
                sample_extracted_nodes,
                sample_episode,
                [],
                None,
                sample_state,
            )

            mock_dspy.assert_called_once()
            assert len(result[0]) == 2

    @pytest.mark.asyncio
    async def test_resolve_nodes_dspy_handles_no_existing_entities(
        self, graphiti_instance, sample_extracted_nodes, sample_episode
    ):
        graphiti_instance.use_dspy = True
        graphiti_instance.driver.execute_query = AsyncMock(return_value=([], None, None))

        with patch('graphiti_core.graphiti._get_dspy_pipeline') as mock_pipeline:
            mock_pipeline_instance = MagicMock()
            mock_pipeline.return_value = mock_pipeline_instance

            result = await graphiti_instance._resolve_nodes_dspy(
                sample_extracted_nodes,
                sample_episode,
                [],
            )

            resolved_nodes, uuid_map, duplicates = result
            assert len(resolved_nodes) == 2
            assert len(uuid_map) == 2
            assert len(duplicates) == 0
            for node in sample_extracted_nodes:
                assert uuid_map[node.uuid] == node.uuid

    @pytest.mark.asyncio
    async def test_resolve_nodes_dspy_detects_duplicates(
        self, graphiti_instance, sample_extracted_nodes, sample_episode
    ):
        graphiti_instance.use_dspy = True

        existing_uuid = str(uuid4())
        existing_entity = {
            'uuid': existing_uuid,
            'name': 'Emmanuel',
            'summary': 'A developer',
            'labels': ['Person'],
            'group_id': 'test-group',
        }
        graphiti_instance.driver.execute_query = AsyncMock(
            return_value=([existing_entity], None, None)
        )

        mock_resolution = NodeResolutions(
            entity_resolutions=[
                NodeDuplicate(id=0, duplicate_idx=0, name='Emmanuel', duplicates=[0]),
                NodeDuplicate(id=1, duplicate_idx=-1, name='Graphiti', duplicates=[]),
            ]
        )

        with patch('graphiti_core.graphiti._get_dspy_pipeline') as mock_pipeline:
            mock_pipeline_instance = MagicMock()
            mock_pipeline_instance.node_resolver = MagicMock(return_value=mock_resolution)
            mock_pipeline.return_value = mock_pipeline_instance

            result = await graphiti_instance._resolve_nodes_dspy(
                sample_extracted_nodes,
                sample_episode,
                [],
            )

            resolved_nodes, uuid_map, duplicates = result
            assert len(duplicates) == 1
            node1_uuid = sample_extracted_nodes[0].uuid
            node2_uuid = sample_extracted_nodes[1].uuid
            assert uuid_map[node1_uuid] == existing_uuid
            assert uuid_map[node2_uuid] == node2_uuid


class TestGetExistingEntitiesForResolution:
    @pytest.mark.asyncio
    async def test_returns_empty_for_no_extracted_nodes(self, graphiti_instance):
        result = await graphiti_instance._get_existing_entities_for_resolution('test-group', [])
        assert result == []

    @pytest.mark.asyncio
    async def test_queries_by_name_within_group(self, graphiti_instance, sample_extracted_nodes):
        graphiti_instance.enable_cross_graph_deduplication = False
        graphiti_instance.driver.execute_query = AsyncMock(return_value=([], None, None))

        await graphiti_instance._get_existing_entities_for_resolution(
            'test-group', sample_extracted_nodes
        )

        call_args = graphiti_instance.driver.execute_query.call_args
        assert 'n.group_id = $group_id' in call_args[0][0]
        assert call_args[1]['group_id'] == 'test-group'
        assert set(call_args[1]['names']) == {'Emmanuel', 'Graphiti'}

    @pytest.mark.asyncio
    async def test_queries_across_groups_when_cross_dedup_enabled(
        self, graphiti_instance, sample_extracted_nodes
    ):
        graphiti_instance.enable_cross_graph_deduplication = True
        graphiti_instance.driver.execute_query = AsyncMock(return_value=([], None, None))

        await graphiti_instance._get_existing_entities_for_resolution(
            'test-group', sample_extracted_nodes
        )

        call_args = graphiti_instance.driver.execute_query.call_args
        assert 'n.group_id = $group_id' not in call_args[0][0]
        assert 'group_id' not in call_args[1]

    @pytest.mark.asyncio
    async def test_returns_formatted_existing_entities(
        self, graphiti_instance, sample_extracted_nodes
    ):
        mock_records = [
            {
                'uuid': 'existing-1',
                'name': 'Emmanuel',
                'summary': 'A developer',
                'labels': ['Person'],
                'group_id': 'test-group',
            },
        ]
        graphiti_instance.driver.execute_query = AsyncMock(return_value=(mock_records, None, None))

        result = await graphiti_instance._get_existing_entities_for_resolution(
            'test-group', sample_extracted_nodes
        )

        assert len(result) == 1
        assert result[0]['idx'] == 0
        assert result[0]['uuid'] == 'existing-1'
        assert result[0]['name'] == 'Emmanuel'
        assert result[0]['entity_type'] == 'Person'


class TestResolutionStateTracking:
    @pytest.mark.asyncio
    async def test_increments_resolve_attempts(
        self, graphiti_instance, sample_extracted_nodes, sample_episode, sample_state
    ):
        graphiti_instance.use_dspy = False

        with patch(
            'graphiti_core.graphiti.resolve_extracted_nodes',
            new_callable=AsyncMock,
        ) as mock_legacy:
            mock_legacy.return_value = (sample_extracted_nodes, {}, [])

            assert sample_state.nodes_resolve_attempts == 0

            await graphiti_instance._resolve_nodes_with_retry(
                sample_extracted_nodes,
                sample_episode,
                [],
                None,
                sample_state,
            )

            assert sample_state.nodes_resolve_attempts == 1
