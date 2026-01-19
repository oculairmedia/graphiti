from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import importlib

workflow = importlib.import_module('temporalio.workflow')


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


@workflow.defn(name='GraphHealthMonitorWorkflow')
class GraphHealthMonitorWorkflow:
    @workflow.run
    async def run(self, input: MonitoringInput) -> GraphHealthCheckOutput:
        result = await workflow.execute_activity(
            'check_graph_health',
            input,
            task_queue='graphiti-monitoring',
            start_to_close_timeout=timedelta(minutes=2),
        )
        return result
