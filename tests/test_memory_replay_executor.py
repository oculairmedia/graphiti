from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from graphiti_core.graphiti import AddEpisodeResults
from graphiti_core.ingestion.queue_client import IngestionTask, TaskPriority, TaskType
from graphiti_core.nodes import EpisodeType, EpisodicNode
from graphiti_core.utils.replay.executor import (
    ReplayContext,
    ReplayEpisodeNotFound,
    ReplayExecutor,
)
from graphiti_core.ingestion.worker import IngestionWorker, PermanentError
from graphiti_core.driver.driver import GraphDriver, GraphDriverSession


class DummyDriver(GraphDriver):
    provider = 'neo4j'

    def __init__(self):
        super().__init__()
        self.queries: list[dict] = []

    async def execute_query(self, query: str, **kwargs):
        self.queries.append({'query': query, 'params': kwargs})
        return [], None, None

    def session(self, database: str | None = None) -> GraphDriverSession:  # pragma: no cover - unused
        raise NotImplementedError

    async def close(self):  # pragma: no cover - unused
        return None

    async def delete_all_indexes(self, database_: str | None = None):  # pragma: no cover - unused
        return None


class DummyGraphiti:
    def __init__(self, driver: DummyDriver, result: AddEpisodeResults, *, raises: Exception | None = None):
        self.driver = driver
        self._result = result
        self._raises = raises
        self.calls: list[dict] = []

    async def add_episode_resilient(self, **kwargs):
        self.calls.append(kwargs)
        if self._raises:
            raise self._raises
        return self._result


@pytest.mark.asyncio
async def test_replay_executor_updates_metadata(monkeypatch):
    now = datetime(2025, 1, 1, tzinfo=timezone.utc)
    episode = EpisodicNode(
        uuid=str(uuid4()),
        name='Episode',
        group_id='GRAPH',
        source_description='source',
        content='hello world',
        valid_at=now,
        source=EpisodeType.message,
        entity_edges=[],
        entity_count=2,
        edge_count=3,
        cross_group_connections=1,
        extraction_version='1.2.3',
        confidence_score=0.8,
    )

    async def fake_get_by_uuid(driver, uuid):
        assert uuid == 'ep-1'
        return episode

    monkeypatch.setattr(EpisodicNode, 'get_by_uuid', staticmethod(fake_get_by_uuid))

    result = AddEpisodeResults(episode=episode, nodes=[], edges=[])
    driver = DummyDriver()
    graphiti = DummyGraphiti(driver, result)
    executor = ReplayExecutor(graphiti)

    context = ReplayContext(
        reason='low_confidence',
        priority_score=0.9,
        scheduled_at=now,
        attempt_number=1,
        group_id='GRAPH',
    )

    await executor.execute('ep-1', context)

    assert graphiti.calls, 'replay should invoke resilient ingestion'
    call = graphiti.calls[0]
    assert call['replay_mode'] is True
    assert call['replay_context'].reason == 'low_confidence'

    assert driver.queries, 'metadata update should be persisted'
    params = driver.queries[0]['params']
    assert params['episode_uuid'] == 'ep-1'
    assert params['group_id'] == 'GRAPH'
    assert params['reason'] == 'low_confidence'
    assert params['entity_count'] == 2
    assert params['edge_count'] == 3


@pytest.mark.asyncio
async def test_replay_executor_records_failure(monkeypatch):
    now = datetime(2025, 1, 1, tzinfo=timezone.utc)
    episode = EpisodicNode(
        uuid=str(uuid4()),
        name='Episode',
        group_id='GRAPH',
        source_description='source',
        content='content',
        valid_at=now,
        source=EpisodeType.message,
        entity_edges=[],
    )

    async def fake_get_by_uuid(driver, uuid):
        return episode

    monkeypatch.setattr(EpisodicNode, 'get_by_uuid', staticmethod(fake_get_by_uuid))

    driver = DummyDriver()
    graphiti = DummyGraphiti(driver, result=None, raises=RuntimeError('boom'))
    executor = ReplayExecutor(graphiti)

    context = ReplayContext(reason='test', priority_score=0.5, scheduled_at=now, attempt_number=2, group_id='GRAPH')

    with pytest.raises(RuntimeError):
        await executor.execute('ep-2', context)

    assert driver.queries, 'failure should still persist metadata'
    params = driver.queries[0]['params']
    assert params['episode_uuid'] == 'ep-2'
    assert params['reason'] == 'test'
    assert 'error' in params and params['error'] == 'boom'


@pytest.mark.asyncio
async def test_replay_executor_missing_episode(monkeypatch):
    async def fake_get_by_uuid(driver, uuid):
        return None

    monkeypatch.setattr(EpisodicNode, 'get_by_uuid', staticmethod(fake_get_by_uuid))

    driver = DummyDriver()
    graphiti = DummyGraphiti(driver, result=None)
    executor = ReplayExecutor(graphiti)

    context = ReplayContext(reason='missing', priority_score=0.1, scheduled_at=datetime.now(timezone.utc), attempt_number=1)

    with pytest.raises(ReplayEpisodeNotFound):
        await executor.execute('missing-ep', context)

    assert driver.queries == []


class DummyQueue:
    async def poll(self, *args, **kwargs):  # pragma: no cover - not used in tests
        return []

    async def delete(self, *args, **kwargs):  # pragma: no cover - not used
        return True


class StubCentralityClient:
    async def close(self):
        return None


class StubGraphiti:
    def __init__(self):
        self.driver = type('D', (), {'provider': 'neo4j'})()
        self.add_episode_resilient = None  # pragma: no cover - not used in worker test


@pytest.mark.asyncio
async def test_worker_routes_replay_tasks(monkeypatch):
    monkeypatch.setattr('graphiti_core.ingestion.worker.CentralityClient', lambda *args, **kwargs: StubCentralityClient())
    sample_episode = EpisodicNode(
        uuid=str(uuid4()),
        name='Episode',
        group_id='GRAPH',
        source_description='desc',
        content='text',
        valid_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        source=EpisodeType.message,
        entity_edges=[],
    )

    class _StubReplayExecutor:
        def __init__(self, graphiti):
            self.calls = []

        async def execute(self, episode_uuid, context):
            self.calls.append((episode_uuid, context))
            return AddEpisodeResults(episode=sample_episode, nodes=[], edges=[])

    monkeypatch.setattr('graphiti_core.ingestion.worker.ReplayExecutor', _StubReplayExecutor)

    worker = IngestionWorker(
        worker_id='worker-1',
        queue_client=DummyQueue(),
        graphiti=StubGraphiti(),
        batch_size=1,
    )

    task = IngestionTask(
        id='task-1',
        type=TaskType.REPLAY,
        payload={'episode_uuid': 'ep-123', 'replay_context': {'reason': 'test', 'priority_score': 0.7}},
        group_id='GRAPH',
        priority=TaskPriority.NORMAL,
    )

    await worker._process_task(task)

    assert worker.replay_executor.calls
    episode_uuid, context = worker.replay_executor.calls[0]
    assert episode_uuid == 'ep-123'
    assert context.group_id == 'GRAPH'
    assert context.reason == 'test'


@pytest.mark.asyncio
async def test_worker_replay_validates_payload(monkeypatch):
    monkeypatch.setattr('graphiti_core.ingestion.worker.CentralityClient', lambda *args, **kwargs: StubCentralityClient())
    class _StubReplayExecutor:
        def __init__(self, graphiti):
            self.calls = []

        async def execute(self, episode_uuid, context):
            self.calls.append((episode_uuid, context))
            return AddEpisodeResults(
                episode=EpisodicNode(
                    uuid=str(uuid4()),
                    name='n',
                    group_id='GRAPH',
                    source_description='d',
                    content='c',
                    valid_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
                    source=EpisodeType.message,
                    entity_edges=[],
                ),
                nodes=[],
                edges=[],
            )

    monkeypatch.setattr('graphiti_core.ingestion.worker.ReplayExecutor', _StubReplayExecutor)

    worker = IngestionWorker(
        worker_id='worker-2',
        queue_client=DummyQueue(),
        graphiti=StubGraphiti(),
        batch_size=1,
    )

    task = IngestionTask(
        id='task-missing',
        type=TaskType.REPLAY,
        payload={},
        group_id='GRAPH',
    )

    with pytest.raises(PermanentError):
        await worker._process_task(task)
