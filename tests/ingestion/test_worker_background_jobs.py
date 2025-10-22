import asyncio
from types import SimpleNamespace

import pytest

from graphiti_core.ingestion.queue_client import IngestionTask, TaskPriority, TaskType
from graphiti_core.ingestion.worker import IngestionWorker
from graphiti_core.nodes import EpisodeType
from graphiti_core.utils.datetime_utils import utc_now


class DummyQueueClient:
    async def poll(self, *args, **kwargs):
        return []

    async def delete(self, *args, **kwargs):
        return None

    async def update(self, *args, **kwargs):
        return None


class DummyGraphiti:
    def __init__(self, result):
        self._result = result
        self.llm_client = SimpleNamespace()
        self.driver = SimpleNamespace(provider="neo4j")

    async def add_episode_resilient(
        self,
        group_id,
        name,
        episode_body,
        reference_time,
        source,
        source_description=None,
    ):
        assert source is EpisodeType.message
        return self._result


class DummyEpisodeResult:
    def __init__(self):
        self.nodes = [SimpleNamespace(uuid="node-1")]
        self.episode = SimpleNamespace(uuid="episode-1")
        self.edges = []


@pytest.mark.asyncio
async def test_process_episode_defers_background_tasks(monkeypatch):
    dummy_result = DummyEpisodeResult()
    worker = IngestionWorker(
        worker_id="worker-test",
        queue_client=DummyQueueClient(),
        graphiti=DummyGraphiti(dummy_result),
        batch_size=1,
    )

    centrality_calls = []

    async def fake_update(nodes):
        centrality_calls.append(list(nodes))

    worker.centrality_client.update_nodes_centrality = fake_update

    async def no_delay_update(node_ids):
        await fake_update(node_ids)

    worker._update_centrality_async = no_delay_update

    def fail_create_task(_):
        raise AssertionError("Background create_task should not be used in gated flow")

    monkeypatch.setattr(asyncio, "create_task", fail_create_task)

    task = IngestionTask(
        id="task-1",
        type=TaskType.EPISODE,
        payload={
            "uuid": "episode-1",
            "content": "Example content",
            "name": "Episode",
            "group_id": "group-1",
            "source_description": "desc",
            "timestamp": utc_now().isoformat(),
        },
        group_id="group-1",
        priority=TaskPriority.NORMAL,
    )

    await worker._process_task(task)

    assert (
        centrality_calls
    ), "Centrality updates should still run even when background scheduling is gated"
