from datetime import datetime, timedelta, timezone

import pytest

from graphiti_core.driver.driver import GraphDriver, GraphDriverSession
from graphiti_core.utils.replay.candidate_detector import ReplayCandidateDetector


class _DummySession(GraphDriverSession):
    async def __aexit__(self, exc_type, exc, tb):  # pragma: no cover - not used
        return None

    async def run(self, query: str, **kwargs):  # pragma: no cover - not used
        raise NotImplementedError

    async def close(self):  # pragma: no cover - not used
        return None

    async def execute_write(self, func, *args, **kwargs):  # pragma: no cover - not used
        raise NotImplementedError


class DummyDriver(GraphDriver):
    provider: str = 'neo4j'

    def __init__(self, responses):
        super().__init__()
        self._responses = responses
        self._queries = []

    async def execute_query(self, cypher_query_: str, **kwargs):
        self._queries.append({'query': cypher_query_, 'params': kwargs})
        if callable(self._responses):
            return self._responses()
        return self._responses

    def session(self, database: str | None = None) -> GraphDriverSession:  # pragma: no cover - not used
        return _DummySession()

    async def close(self):  # pragma: no cover - not used
        return None

    async def delete_all_indexes(self, database_: str | None = None):  # pragma: no cover - not used
        return None


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()


@pytest.mark.asyncio
async def test_identify_candidates_prioritises_sparse_isolated_records():
    now = datetime(2025, 9, 30, tzinfo=timezone.utc)

    rows = [
        {
            'episode_uuid': 'ep-critical',
            'group_id': 'GRAPH',
            'entity_count': 1,
            'edge_count': 1,
            'cross_group_connections': 0,
            'extraction_version': '1.2.0',
            'confidence_score': 0.4,
            'valid_at': _iso(now - timedelta(days=2)),
            'created_at': _iso(now - timedelta(days=10)),
            'last_replayed_at': None,
            'replay_attempts': 0,
        },
        {
            'episode_uuid': 'ep-ok',
            'group_id': 'GRAPH',
            'entity_count': 5,
            'edge_count': 5,
            'cross_group_connections': 3,
            'extraction_version': '1.2.0',
            'confidence_score': 0.9,
            'valid_at': _iso(now - timedelta(days=40)),
            'created_at': _iso(now - timedelta(days=60)),
            'last_replayed_at': _iso(now - timedelta(days=1)),
            'replay_attempts': 1,
        },
    ]

    driver = DummyDriver(rows)
    detector = ReplayCandidateDetector(
        driver,
        current_extraction_version='1.3.0',
        now_provider=lambda: now,
    )

    candidates = await detector.identify_candidates(limit=5)

    assert [c.episode_uuid for c in candidates] == ['ep-critical', 'ep-ok']
    assert candidates[0].replay_priority > 0.5
    assert 'sparse_entities' in candidates[0].replay_reason
    assert 'stale_extraction' in candidates[0].replay_reason
    assert 'no_cross_group_links' in candidates[0].replay_reason

    assert candidates[1].replay_priority < 0.25


@pytest.mark.asyncio
async def test_identify_candidates_accepts_falkor_response_tuple():
    now = datetime(2025, 9, 30, tzinfo=timezone.utc)

    tuple_response = ([
        {
            'episode_uuid': 'ep-falkor',
            'group_id': 'GRAPH',
            'entity_count': 0,
            'edge_count': 0,
            'cross_group_connections': 0,
            'extraction_version': None,
            'confidence_score': None,
            'valid_at': _iso(now - timedelta(days=1)),
            'created_at': _iso(now - timedelta(days=5)),
            'last_replayed_at': None,
            'replay_attempts': None,
        }
    ], ['episode_uuid'], None)

    driver = DummyDriver(tuple_response)
    detector = ReplayCandidateDetector(driver, now_provider=lambda: now)

    [candidate] = await detector.identify_candidates(limit=1)
    assert candidate.episode_uuid == 'ep-falkor'
    assert candidate.replay_priority == pytest.approx(1.0, rel=1e-2)
    assert 'never_replayed' in candidate.replay_reason


@pytest.mark.asyncio
async def test_min_priority_filters_low_value_candidates():
    now = datetime(2025, 9, 30, tzinfo=timezone.utc)

    rows = [
        {
            'episode_uuid': 'ep-low',
            'group_id': 'GRAPH',
            'entity_count': 3,
            'edge_count': 3,
            'cross_group_connections': 1,
            'extraction_version': '1.3.0',
            'confidence_score': 0.64,
            'valid_at': _iso(now - timedelta(days=30)),
            'created_at': _iso(now - timedelta(days=30)),
            'last_replayed_at': _iso(now - timedelta(days=2)),
            'replay_attempts': 0,
        }
    ]

    driver = DummyDriver(rows)
    detector = ReplayCandidateDetector(driver, now_provider=lambda: now)

    candidates = await detector.identify_candidates(limit=5, min_priority=0.5)
    assert candidates == []
