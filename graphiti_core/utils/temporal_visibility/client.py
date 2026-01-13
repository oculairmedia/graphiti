from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass

from graphiti_core.utils.temporal_visibility.config import TemporalStageQueueConfig
from datetime import timedelta
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TemporalIngestionConfig:
    enabled: bool
    address: str
    namespace: str
    task_queue: str
    workflow_id_prefix: str
    workflow_timeout_hours: int

    @classmethod
    def from_env(cls) -> 'TemporalIngestionConfig':
        enabled = os.getenv('TEMPORAL_INGESTION_ENABLED', 'false').lower() == 'true'
        stage_queues = TemporalStageQueueConfig.from_env()
        return cls(
            enabled=enabled,
            address=os.getenv('TEMPORAL_VISIBILITY_ADDRESS', '192.168.50.90:7233'),
            namespace=os.getenv('TEMPORAL_VISIBILITY_NAMESPACE', 'graphiti'),
            task_queue=stage_queues.workflow_queue,
            workflow_id_prefix=os.getenv('TEMPORAL_INGESTION_WORKFLOW_PREFIX', 'ingest-episode-'),
            workflow_timeout_hours=int(os.getenv('TEMPORAL_INGESTION_WORKFLOW_TIMEOUT_HOURS', '8')),
        )


class TemporalIngestionClient:
    _instance: 'TemporalIngestionClient | None' = None

    def __init__(self, config: TemporalIngestionConfig):
        self._config = config
        self._client_lock = asyncio.Lock()
        self._client: Any | None = None

    @classmethod
    def get(cls) -> 'TemporalIngestionClient':
        if cls._instance is None:
            cls._instance = TemporalIngestionClient(TemporalIngestionConfig.from_env())
        return cls._instance

    def enabled(self) -> bool:
        return self._config.enabled

    def workflow_id(self, episode_uuid: str) -> str:
        return f'{self._config.workflow_id_prefix}{episode_uuid}'

    async def _get_client(self) -> Any:
        if self._client is not None:
            return self._client

        async with self._client_lock:
            if self._client is not None:
                return self._client

            import importlib

            temporalio_client = importlib.import_module('temporalio.client')
            Client = temporalio_client.Client

            self._client = await Client.connect(
                self._config.address, namespace=self._config.namespace
            )
            return self._client

    async def start_ingestion(
        self,
        episode_uuid: str,
        group_id: str,
        name: str,
        episode_body: str,
        source: str,
        source_description: str,
        reference_time: str,
        entity_types: dict[str, Any] | None = None,
        excluded_entity_types: list[str] | None = None,
        edge_types: dict[str, Any] | None = None,
        edge_type_map: dict[str, list[str]] | None = None,
        previous_episode_uuids: list[str] | None = None,
        store_raw_content: bool = True,
    ) -> str | None:
        if not self._config.enabled:
            return None

        try:
            from graphiti_core.utils.temporal_visibility.ingestion_workflow import (
                IngestEpisodeWorkflow,
                IngestEpisodeInput,
            )

            client = await self._get_client()
            wf_id = self.workflow_id(episode_uuid)

            input_data = IngestEpisodeInput(
                episode_uuid=episode_uuid,
                group_id=group_id,
                name=name,
                episode_body=episode_body,
                source=source,
                source_description=source_description,
                reference_time=reference_time,
                entity_types=entity_types,
                excluded_entity_types=excluded_entity_types,
                edge_types=edge_types,
                edge_type_map=edge_type_map,
                previous_episode_uuids=previous_episode_uuids,
                store_raw_content=store_raw_content,
            )

            handle = await client.start_workflow(
                IngestEpisodeWorkflow.run,
                args=[input_data],
                id=wf_id,
                task_queue=self._config.task_queue,
                execution_timeout=timedelta(hours=self._config.workflow_timeout_hours),
            )

            logger.info(f'Started Temporal ingestion workflow: {wf_id}')
            return wf_id

        except Exception as e:
            logger.warning(f'Failed to start Temporal ingestion workflow: {e}')
            return None


@dataclass(frozen=True)
class TemporalVisibilityConfig:
    enabled: bool
    address: str
    namespace: str
    task_queue: str
    workflow_id_prefix: str
    rpc_timeout_seconds: float

    @classmethod
    def from_env(cls) -> 'TemporalVisibilityConfig':
        enabled = os.getenv('TEMPORAL_VISIBILITY_ENABLED', 'false').lower() == 'true'
        return cls(
            enabled=enabled,
            address=os.getenv('TEMPORAL_VISIBILITY_ADDRESS', 'temporal:7233'),
            namespace=os.getenv('TEMPORAL_VISIBILITY_NAMESPACE', 'default'),
            task_queue=os.getenv('TEMPORAL_VISIBILITY_TASK_QUEUE', 'graphiti-visibility'),
            workflow_id_prefix=os.getenv('TEMPORAL_VISIBILITY_WORKFLOW_PREFIX', 'vis-episode-'),
            rpc_timeout_seconds=float(os.getenv('TEMPORAL_VISIBILITY_RPC_TIMEOUT_SECONDS', '0.5')),
        )


class TemporalVisibilityClient:
    """Best-effort Temporal client for ingestion visibility.

    This client is safe to call from ingestion hot paths:
    - gated by env var
    - never raises to callers
    - bounded RPC timeout
    """

    _instance: 'TemporalVisibilityClient | None' = None

    def __init__(self, config: TemporalVisibilityConfig):
        self._config = config
        self._client_lock = asyncio.Lock()
        self._client: Any | None = None

    @classmethod
    def get(cls) -> 'TemporalVisibilityClient':
        if cls._instance is None:
            cls._instance = TemporalVisibilityClient(TemporalVisibilityConfig.from_env())
        return cls._instance

    def enabled(self) -> bool:
        return self._config.enabled

    def workflow_id(self, episode_uuid: str) -> str:
        return f'{self._config.workflow_id_prefix}{episode_uuid}'

    async def _with_timeout(self, coro: Any) -> Any:
        return await asyncio.wait_for(coro, timeout=self._config.rpc_timeout_seconds)

    async def _get_client(self) -> Any:
        if self._client is not None:
            return self._client

        async with self._client_lock:
            if self._client is not None:
                return self._client

            import importlib

            temporalio_client = importlib.import_module('temporalio.client')
            Client = temporalio_client.Client

            self._client = await self._with_timeout(
                Client.connect(self._config.address, namespace=self._config.namespace)
            )
            return self._client

    async def ensure_workflow_started(self, episode_uuid: str, group_id: str) -> None:
        if not self._config.enabled:
            return

        try:
            from graphiti_core.utils.temporal_visibility.workflow import (
                EpisodeIngestionVisibilityWorkflow,
            )

            client = await self._get_client()
            wf_id = self.workflow_id(episode_uuid)

            await self._with_timeout(
                client.start_workflow(
                    EpisodeIngestionVisibilityWorkflow.run,
                    args=[episode_uuid, group_id],
                    id=wf_id,
                    task_queue=self._config.task_queue,
                    execution_timeout=timedelta(hours=1),
                )
            )

        except Exception as e:
            if e.__class__.__name__ == 'WorkflowAlreadyStartedError':
                return
            logger.debug('Temporal visibility ensure_workflow_started failed: %s', e)

    async def stage_started(
        self, episode_uuid: str, group_id: str, stage: str, metadata: dict[str, Any] | None = None
    ) -> None:
        await self._signal(episode_uuid, group_id, 'stage_started', stage, metadata)

    async def stage_completed(
        self,
        episode_uuid: str,
        group_id: str,
        stage: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        await self._signal(episode_uuid, group_id, 'stage_completed', stage, metadata)

    async def ingestion_failed(
        self,
        episode_uuid: str,
        group_id: str,
        stage: str,
        error_message: str,
        error_type: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if not self._config.enabled:
            return

        try:
            from graphiti_core.utils.temporal_visibility.workflow import (
                EpisodeIngestionVisibilityWorkflow,
            )

            client = await self._get_client()
            wf_id = self.workflow_id(episode_uuid)
            await self.ensure_workflow_started(episode_uuid, group_id)

            handle = client.get_workflow_handle(wf_id)
            await self._with_timeout(
                handle.signal(
                    EpisodeIngestionVisibilityWorkflow.ingestion_failed,
                    stage,
                    error_message,
                    error_type,
                    metadata,
                )
            )
        except Exception as e:
            logger.debug('Temporal visibility ingestion_failed failed: %s', e)

    async def ingestion_completed(
        self,
        episode_uuid: str,
        group_id: str,
        summary: dict[str, Any] | None = None,
    ) -> None:
        if not self._config.enabled:
            return

        try:
            from graphiti_core.utils.temporal_visibility.workflow import (
                EpisodeIngestionVisibilityWorkflow,
            )

            client = await self._get_client()
            wf_id = self.workflow_id(episode_uuid)
            await self.ensure_workflow_started(episode_uuid, group_id)

            handle = client.get_workflow_handle(wf_id)
            await self._with_timeout(
                handle.signal(EpisodeIngestionVisibilityWorkflow.ingestion_completed, summary)
            )
        except Exception as e:
            logger.debug('Temporal visibility ingestion_completed failed: %s', e)

    async def _signal(
        self,
        episode_uuid: str,
        group_id: str,
        signal_name: str,
        stage: str,
        metadata: dict[str, Any] | None,
    ) -> None:
        if not self._config.enabled:
            return

        try:
            from graphiti_core.utils.temporal_visibility.workflow import (
                EpisodeIngestionVisibilityWorkflow,
            )

            client = await self._get_client()
            wf_id = self.workflow_id(episode_uuid)
            await self.ensure_workflow_started(episode_uuid, group_id)
            handle = client.get_workflow_handle(wf_id)

            if signal_name == 'stage_started':
                signal = EpisodeIngestionVisibilityWorkflow.stage_started
            elif signal_name == 'stage_completed':
                signal = EpisodeIngestionVisibilityWorkflow.stage_completed
            else:
                raise ValueError(f'Unknown signal: {signal_name}')

            await self._with_timeout(handle.signal(signal, stage, metadata))
        except Exception as e:
            logger.debug('Temporal visibility %s failed: %s', signal_name, e)
