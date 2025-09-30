from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta, timezone

import pytest

from graphiti_core.config.replay_config import ReplayConfig
from graphiti_core.ingestion.queue_client import TaskPriority, TaskType
from graphiti_core.utils.replay.candidate_detector import ReplayCandidate
from graphiti_core.utils.replay.scheduler import MemoryReplayScheduler


class DummyDetector:
    def __init__(self, candidates):
        self._candidates = list(candidates)
        self.calls = []

    async def identify_candidates(self, **kwargs):
        self.calls.append(kwargs)
        return list(self._candidates)


class RecordingQueue:
    def __init__(self):
        self.calls = []

    async def push(self, tasks, queue_name: str = 'memory_replay'):
        self.calls.append((queue_name, list(tasks)))
        return list(range(len(tasks)))


def _candidate(
    episode_uuid: str,
    *,
    priority: float = 0.8,
    group_id: str = 'GRAPH',
    attempts: int = 0,
    last_replayed_at: datetime | None = None,
) -> ReplayCandidate:
    now = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return ReplayCandidate(
        episode_uuid=episode_uuid,
        group_id=group_id,
        entity_count=1,
        edge_count=1,
        cross_group_connections=0,
        extraction_version='1.0.0',
        confidence_score=0.1,
        valid_at=now,
        created_at=now - timedelta(days=1),
        last_replayed_at=last_replayed_at,
        replay_attempts=attempts,
        replay_reason='sparse_entities',
        replay_priority=priority,
    )


@pytest.mark.asyncio
async def test_scheduler_queues_candidates_respecting_batch_size():
    now = datetime(2025, 1, 1, tzinfo=timezone.utc)
    detector = DummyDetector([
        _candidate('ep-1', priority=0.9),
        _candidate('ep-2', priority=0.8),
        _candidate('ep-3', priority=0.7),
    ])
    queue = RecordingQueue()
    config = ReplayConfig(
        enabled=True,
        batch_size=2,
        cooldown_hours=0,
        max_per_group_per_hour=10,
        min_priority=0.1,
    )

    scheduler = MemoryReplayScheduler(
        queue_client=queue,
        config=config,
        candidate_detector=detector,
        now_provider=lambda: now,
    )

    scheduled = await scheduler.run_cycle()

    assert scheduled == 2
    assert len(queue.calls) == 1
    queue_name, tasks = queue.calls[0]
    assert queue_name == config.queue_name
    assert [task.payload['episode_uuid'] for task in tasks] == ['ep-1', 'ep-2']
    assert all(task.type == TaskType.REPLAY for task in tasks)
    assert all(task.priority == TaskPriority.NORMAL for task in tasks)

    status = scheduler.get_status().as_dict()
    assert status['last_scheduled'] == 2
    assert status['running'] is False
    assert status['queue_name'] == config.queue_name


@pytest.mark.asyncio
async def test_scheduler_skips_candidates_in_cooldown_or_over_attempt_limit():
    now = datetime(2025, 1, 1, tzinfo=timezone.utc)
    detector = DummyDetector([
        _candidate('ep-recent', last_replayed_at=now - timedelta(hours=1)),
        _candidate('ep-exhausted', attempts=5),
    ])
    queue = RecordingQueue()
    config = ReplayConfig(
        enabled=True,
        cooldown_hours=2,
        max_attempts=2,
        max_per_group_per_hour=10,
        min_priority=0.1,
    )

    scheduler = MemoryReplayScheduler(
        queue_client=queue,
        config=config,
        candidate_detector=detector,
        now_provider=lambda: now,
    )

    scheduled = await scheduler.run_cycle()

    assert scheduled == 0
    assert queue.calls == []

    status = scheduler.get_status().as_dict()
    assert status['last_scheduled'] == 0
    assert status['last_error'] is None


@pytest.mark.asyncio
async def test_scheduler_enforces_group_rate_limit_across_cycles():
    base_time = datetime(2025, 1, 1, tzinfo=timezone.utc)
    detector = DummyDetector([
        _candidate('ep-1', group_id='GRAPH'),
        _candidate('ep-2', group_id='GRAPH'),
    ])
    queue = RecordingQueue()
    config = ReplayConfig(
        enabled=True,
        batch_size=5,
        max_per_group_per_hour=1,
        rate_limit_window_seconds=3600,
        cooldown_hours=0,
    )
    times = deque([
        base_time,
        base_time + timedelta(minutes=10),
        base_time + timedelta(hours=2),
    ])

    scheduler = MemoryReplayScheduler(
        queue_client=queue,
        config=config,
        candidate_detector=detector,
        now_provider=lambda: times[0],
    )

    scheduled_first = await scheduler.run_cycle()
    assert scheduled_first == 1
    assert len(queue.calls) == 1

    times.rotate(-1)
    scheduled_second = await scheduler.run_cycle()
    assert scheduled_second == 0
    assert len(queue.calls) == 1

    times.rotate(-1)
    scheduled_third = await scheduler.run_cycle()
    assert scheduled_third == 1
    assert len(queue.calls) == 2

    history = list(scheduler._group_schedule_history['GRAPH'])
    assert len(history) == 1
    assert history[0] == times[0]

    status = scheduler.get_status().as_dict()
    assert status['last_scheduled'] == 1
