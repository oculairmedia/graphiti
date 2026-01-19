from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import importlib

activity = importlib.import_module('temporalio.activity')

logger = logging.getLogger(__name__)


@dataclass
class GraphHealthCheckOutput:
    timestamp: str
    isolated_episodic_count: int
    total_episodic_count: int
    total_entity_count: int
    total_edges: int
    relates_to_count: int
    mentions_count: int
    edge_ratio: float
    recent_episodes_count: int
    recent_edges_count: int
    recent_isolated_count: int
    status: str
    alerts: list[str]


@dataclass
class MonitoringInput:
    check_interval_minutes: int = 5
    alert_on_isolated: bool = True
    min_edge_ratio: float = 3.0


class MonitoringActivities:
    def __init__(self):
        self._redis = None

    def _get_redis(self):
        if self._redis is None:
            import redis

            host = os.getenv('FALKORDB_HOST', 'falkordb')
            port = int(os.getenv('FALKORDB_PORT', '6379'))
            self._redis = redis.Redis(host=host, port=port)
        return self._redis

    def _query(self, cypher: str) -> list[dict[str, Any]]:
        r = self._get_redis()
        database = os.getenv('FALKORDB_DATABASE', 'graphiti_migration')
        result = r.execute_command('GRAPH.QUERY', database, cypher)
        if not result or len(result) < 2:
            return []
        headers = [h.decode() if isinstance(h, bytes) else h for h in result[0]]
        rows = []
        for row in result[1]:
            rows.append({headers[i]: row[i] for i in range(len(headers))})
        return rows

    @activity.defn(name='check_graph_health')
    async def check_graph_health(self, input: MonitoringInput) -> GraphHealthCheckOutput:
        now = datetime.now(timezone.utc)
        one_hour_ago = (now - timedelta(hours=1)).isoformat()

        alerts = []

        isolated_result = self._query('MATCH (e:Episodic) WHERE NOT (e)-[]-() RETURN count(e) as c')
        isolated_count = isolated_result[0]['c'] if isolated_result else 0

        episodic_result = self._query('MATCH (e:Episodic) RETURN count(e) as c')
        episodic_count = episodic_result[0]['c'] if episodic_result else 0

        entity_result = self._query('MATCH (n:Entity) RETURN count(n) as c')
        entity_count = entity_result[0]['c'] if entity_result else 0

        relates_to_result = self._query('MATCH ()-[r:RELATES_TO]->() RETURN count(r) as c')
        relates_to_count = relates_to_result[0]['c'] if relates_to_result else 0

        mentions_result = self._query('MATCH ()-[r:MENTIONS]->() RETURN count(r) as c')
        mentions_count = mentions_result[0]['c'] if mentions_result else 0

        total_edges = relates_to_count + mentions_count
        edge_ratio = total_edges / episodic_count if episodic_count > 0 else 0

        recent_ep_result = self._query(
            f"MATCH (e:Episodic) WHERE e.created_at > '{one_hour_ago}' RETURN count(e) as c"
        )
        recent_episodes = recent_ep_result[0]['c'] if recent_ep_result else 0

        recent_edge_result = self._query(
            f"MATCH ()-[r]->() WHERE r.created_at > '{one_hour_ago}' RETURN count(r) as c"
        )
        recent_edges = recent_edge_result[0]['c'] if recent_edge_result else 0

        recent_iso_result = self._query(
            f"MATCH (e:Episodic) WHERE e.created_at > '{one_hour_ago}' AND NOT (e)-[]-() RETURN count(e) as c"
        )
        recent_isolated = recent_iso_result[0]['c'] if recent_iso_result else 0

        status = 'OK'

        if isolated_count > 0 and input.alert_on_isolated:
            status = 'WARN'
            alerts.append(f'DETACHED:{isolated_count}')

        if edge_ratio < input.min_edge_ratio:
            status = 'WARN'
            alerts.append(f'LOW_RATIO:{edge_ratio:.2f}')

        if recent_episodes > 0 and recent_isolated > 0:
            status = 'ALERT'
            alerts.append(f'NEW_EPS_NO_EDGES:{recent_isolated}')

        logger.info(
            'Graph health check: status=%s isolated=%d ratio=%.2f alerts=%s',
            status,
            isolated_count,
            edge_ratio,
            alerts,
        )

        return GraphHealthCheckOutput(
            timestamp=now.isoformat(),
            isolated_episodic_count=isolated_count,
            total_episodic_count=episodic_count,
            total_entity_count=entity_count,
            total_edges=total_edges,
            relates_to_count=relates_to_count,
            mentions_count=mentions_count,
            edge_ratio=edge_ratio,
            recent_episodes_count=recent_episodes,
            recent_edges_count=recent_edges,
            recent_isolated_count=recent_isolated,
            status=status,
            alerts=alerts,
        )
