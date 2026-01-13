from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class TemporalStageQueueConfig:
    workflow_queue: str
    extract_queue: str
    resolve_queue: str
    edge_queue: str
    persist_queue: str
    legacy_queue: str
    staged_enabled: bool

    @classmethod
    def from_env(cls) -> 'TemporalStageQueueConfig':
        legacy_queue = os.getenv('TEMPORAL_INGESTION_TASK_QUEUE', 'graphiti-ingestion')
        staged_env_vars = (
            os.getenv('TEMPORAL_INGESTION_WORKFLOW_TASK_QUEUE'),
            os.getenv('TEMPORAL_INGESTION_EXTRACT_TASK_QUEUE'),
            os.getenv('TEMPORAL_INGESTION_RESOLVE_TASK_QUEUE'),
            os.getenv('TEMPORAL_INGESTION_EDGE_TASK_QUEUE'),
            os.getenv('TEMPORAL_INGESTION_PERSIST_TASK_QUEUE'),
        )
        staged_enabled = any(value for value in staged_env_vars)

        if not staged_enabled:
            return cls(
                workflow_queue=legacy_queue,
                extract_queue=legacy_queue,
                resolve_queue=legacy_queue,
                edge_queue=legacy_queue,
                persist_queue=legacy_queue,
                legacy_queue=legacy_queue,
                staged_enabled=False,
            )

        return cls(
            workflow_queue=os.getenv(
                'TEMPORAL_INGESTION_WORKFLOW_TASK_QUEUE', 'graphiti-ingestion-workflow'
            ),
            extract_queue=os.getenv(
                'TEMPORAL_INGESTION_EXTRACT_TASK_QUEUE', 'graphiti-ingestion-extract'
            ),
            resolve_queue=os.getenv(
                'TEMPORAL_INGESTION_RESOLVE_TASK_QUEUE', 'graphiti-ingestion-resolve'
            ),
            edge_queue=os.getenv('TEMPORAL_INGESTION_EDGE_TASK_QUEUE', 'graphiti-ingestion-edge'),
            persist_queue=os.getenv(
                'TEMPORAL_INGESTION_PERSIST_TASK_QUEUE', 'graphiti-ingestion-persist'
            ),
            legacy_queue=legacy_queue,
            staged_enabled=True,
        )


@dataclass(frozen=True)
class TemporalStageConcurrencyConfig:
    extract_max_activities: int
    resolve_max_activities: int
    edge_max_activities: int
    persist_max_activities: int
    legacy_max_activities: int

    @classmethod
    def from_env(cls) -> 'TemporalStageConcurrencyConfig':
        legacy_max = int(os.getenv('TEMPORAL_MAX_CONCURRENT_ACTIVITIES', '5'))
        staged_env_vars = (
            os.getenv('TEMPORAL_EXTRACT_MAX_CONCURRENT_ACTIVITIES'),
            os.getenv('TEMPORAL_RESOLVE_MAX_CONCURRENT_ACTIVITIES'),
            os.getenv('TEMPORAL_EDGE_MAX_CONCURRENT_ACTIVITIES'),
            os.getenv('TEMPORAL_PERSIST_MAX_CONCURRENT_ACTIVITIES'),
        )
        staged_enabled = any(value for value in staged_env_vars)

        if not staged_enabled:
            return cls(
                extract_max_activities=legacy_max,
                resolve_max_activities=legacy_max,
                edge_max_activities=legacy_max,
                persist_max_activities=legacy_max,
                legacy_max_activities=legacy_max,
            )

        return cls(
            extract_max_activities=int(
                os.getenv('TEMPORAL_EXTRACT_MAX_CONCURRENT_ACTIVITIES', '3')
            ),
            resolve_max_activities=int(
                os.getenv('TEMPORAL_RESOLVE_MAX_CONCURRENT_ACTIVITIES', '3')
            ),
            edge_max_activities=int(os.getenv('TEMPORAL_EDGE_MAX_CONCURRENT_ACTIVITIES', '2')),
            persist_max_activities=int(
                os.getenv('TEMPORAL_PERSIST_MAX_CONCURRENT_ACTIVITIES', '5')
            ),
            legacy_max_activities=legacy_max,
        )
