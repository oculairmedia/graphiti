from __future__ import annotations

from typing import Any

import importlib

workflow = importlib.import_module('temporalio.workflow')


@workflow.defn(name='EpisodeIngestionVisibilityWorkflow', sandboxed=False)
class EpisodeIngestionVisibilityWorkflow:
    """A minimal workflow that only records ingestion stage events.

    The actual ingestion continues to run in the existing worker. This workflow exists
    purely to surface a per-episode timeline in Temporal Web UI.
    """

    def __init__(self) -> None:
        self._episode_uuid: str | None = None
        self._group_id: str | None = None
        self._status: str = 'running'
        self._events: list[dict[str, Any]] = []
        self._error: dict[str, Any] | None = None
        self._summary: dict[str, Any] | None = None

    @workflow.run
    async def run(self, episode_uuid: str, group_id: str) -> dict[str, Any]:
        self._episode_uuid = episode_uuid
        self._group_id = group_id
        self._events.append(
            {
                'ts': workflow.now().isoformat(),
                'type': 'workflow_started',
                'episode_uuid': episode_uuid,
                'group_id': group_id,
            }
        )

        await workflow.wait_condition(lambda: self._status in ('completed', 'failed'))

        return {
            'episode_uuid': self._episode_uuid,
            'group_id': self._group_id,
            'status': self._status,
            'events': self._events,
            'error': self._error,
            'summary': self._summary,
        }

    @workflow.signal
    async def stage_started(self, stage: str, metadata: dict[str, Any] | None = None) -> None:
        self._events.append(
            {
                'ts': workflow.now().isoformat(),
                'type': 'stage_started',
                'stage': stage,
                'metadata': metadata or {},
            }
        )

    @workflow.signal
    async def stage_completed(self, stage: str, metadata: dict[str, Any] | None = None) -> None:
        self._events.append(
            {
                'ts': workflow.now().isoformat(),
                'type': 'stage_completed',
                'stage': stage,
                'metadata': metadata or {},
            }
        )

    @workflow.signal
    async def ingestion_failed(
        self,
        stage: str,
        error_message: str,
        error_type: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._status = 'failed'
        self._error = {
            'ts': workflow.now().isoformat(),
            'stage': stage,
            'message': error_message,
            'error_type': error_type,
            'metadata': metadata or {},
        }
        self._events.append(
            {'ts': workflow.now().isoformat(), 'type': 'ingestion_failed', **self._error}
        )

    @workflow.signal
    async def ingestion_completed(self, summary: dict[str, Any] | None = None) -> None:
        self._status = 'completed'
        self._summary = summary or {}
        self._events.append(
            {
                'ts': workflow.now().isoformat(),
                'type': 'ingestion_completed',
                'summary': self._summary,
            }
        )

    @workflow.query
    def status(self) -> dict[str, Any]:
        return {
            'episode_uuid': self._episode_uuid,
            'group_id': self._group_id,
            'status': self._status,
            'error': self._error,
            'last_event': self._events[-1] if self._events else None,
            'event_count': len(self._events),
        }
