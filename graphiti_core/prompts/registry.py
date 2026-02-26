"""
PromptRegistry: Versioned prompt management for DSPy optimization.

Provides a caching layer over FalkorDB's graphiti_prompts graph,
enabling hot-swapping of optimized prompts without restart.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from falkordb.asyncio import FalkorDB

logger = logging.getLogger(__name__)

PROMPT_DATABASE = 'graphiti_prompts'


class PromptStatus(str, Enum):
    LIVE = 'live'
    CANDIDATE = 'candidate'
    ARCHIVED = 'archived'
    FAILED = 'failed'


class PromptTask(str, Enum):
    ENTITY_EXTRACTION = 'entity_extraction'
    EDGE_EXTRACTION = 'edge_extraction'
    NODE_RESOLUTION = 'node_resolution'
    SUMMARY_GENERATION = 'summary_generation'


@dataclass
class PromptVersion:
    id: str
    task: PromptTask
    version: int
    status: PromptStatus
    docstring: str
    demos: list[dict[str, Any]]

    accuracy: float | None = None
    latency_ms: float | None = None
    token_count: int | None = None

    created_at: datetime | None = None
    promoted_at: datetime | None = None
    archived_at: datetime | None = None

    parent_version: int | None = None
    training_examples: int = 0

    @classmethod
    def from_db_record(cls, record: dict[str, Any]) -> PromptVersion:
        demos_raw = record.get('demos', '[]')
        demos = json.loads(demos_raw) if isinstance(demos_raw, str) else demos_raw or []

        return cls(
            id=record['id'],
            task=PromptTask(record['task']),
            version=record['version'],
            status=PromptStatus(record['status']),
            docstring=record.get('docstring', ''),
            demos=demos,
            accuracy=record.get('accuracy'),
            latency_ms=record.get('latency_ms'),
            token_count=record.get('token_count'),
            created_at=_parse_datetime(record.get('created_at')),
            promoted_at=_parse_datetime(record.get('promoted_at')),
            archived_at=_parse_datetime(record.get('archived_at')),
            parent_version=record.get('parent_version'),
            training_examples=record.get('training_examples', 0),
        )


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace('Z', '+00:00'))
    return None


@dataclass
class PromptCache:
    prompts: dict[PromptTask, PromptVersion] = field(default_factory=dict)
    last_refresh: datetime | None = None
    ttl_seconds: int = 60

    def is_stale(self) -> bool:
        if self.last_refresh is None:
            return True
        age = (datetime.now(timezone.utc) - self.last_refresh).total_seconds()
        return age > self.ttl_seconds

    def get(self, task: PromptTask) -> PromptVersion | None:
        return self.prompts.get(task)

    def set(self, task: PromptTask, prompt: PromptVersion) -> None:
        self.prompts[task] = prompt

    def refresh_timestamp(self) -> None:
        self.last_refresh = datetime.now(timezone.utc)

    def invalidate(self) -> None:
        self.prompts.clear()
        self.last_refresh = None


class PromptRegistry:
    """
    Manages versioned prompts stored in FalkorDB's graphiti_prompts graph.

    Features:
    - In-memory caching with configurable TTL
    - Automatic refresh of live prompts
    - Support for candidate testing and promotion
    - Thread-safe operations via asyncio locks
    """

    def __init__(
        self,
        client: FalkorDB | None = None,
        host: str | None = None,
        port: int | None = None,
        cache_ttl_seconds: int = 60,
    ):
        self._client = client
        self._host = host or os.getenv('FALKORDB_HOST', 'localhost')
        self._port = port or int(os.getenv('FALKORDB_PORT', '6379'))
        self._cache = PromptCache(ttl_seconds=cache_ttl_seconds)
        self._lock = asyncio.Lock()
        self._initialized = False

    async def _get_client(self) -> FalkorDB:
        if self._client is not None:
            return self._client

        from falkordb.asyncio import FalkorDB

        self._client = FalkorDB(host=self._host, port=self._port)
        return self._client

    async def _get_graph(self):
        client = await self._get_client()
        return client.select_graph(PROMPT_DATABASE)

    async def get_live_prompt(
        self, task: PromptTask, force_refresh: bool = False
    ) -> PromptVersion | None:
        async with self._lock:
            if not force_refresh and not self._cache.is_stale():
                cached = self._cache.get(task)
                if cached is not None:
                    return cached

            prompt = await self._fetch_live_prompt(task)
            if prompt:
                self._cache.set(task, prompt)
                self._cache.refresh_timestamp()

            return prompt

    async def _fetch_live_prompt(self, task: PromptTask) -> PromptVersion | None:
        graph = await self._get_graph()

        query = """
        MATCH (p:PromptVersion {task: $task, status: 'live'})
        RETURN p.id as id, p.task as task, p.version as version, p.status as status,
               p.docstring as docstring, p.demos as demos, p.accuracy as accuracy,
               p.latency_ms as latency_ms, p.token_count as token_count,
               p.created_at as created_at, p.promoted_at as promoted_at,
               p.archived_at as archived_at, p.parent_version as parent_version,
               p.training_examples as training_examples
        ORDER BY p.version DESC
        LIMIT 1
        """

        try:
            result = await graph.query(query, {'task': task.value})
            if not result.result_set:
                return None

            header = [h[1] for h in result.header]
            row = result.result_set[0]
            record = dict(zip(header, row))
            return PromptVersion.from_db_record(record)
        except Exception as e:
            logger.error(f'Failed to fetch live prompt for {task}: {e}')
            return None

    async def get_all_live_prompts(
        self, force_refresh: bool = False
    ) -> dict[PromptTask, PromptVersion]:
        async with self._lock:
            if not force_refresh and not self._cache.is_stale():
                if all(self._cache.get(task) is not None for task in PromptTask):
                    cached_prompts: dict[PromptTask, PromptVersion] = {}
                    for task in PromptTask:
                        cached_prompt = self._cache.get(task)
                        if cached_prompt is not None:
                            cached_prompts[task] = cached_prompt
                    return cached_prompts

            prompts = await self._fetch_all_live_prompts()
            for task, prompt in prompts.items():
                self._cache.set(task, prompt)
            self._cache.refresh_timestamp()

            return prompts

    async def _fetch_all_live_prompts(self) -> dict[PromptTask, PromptVersion]:
        graph = await self._get_graph()

        query = """
        MATCH (p:PromptVersion {status: 'live'})
        RETURN p.id as id, p.task as task, p.version as version, p.status as status,
               p.docstring as docstring, p.demos as demos, p.accuracy as accuracy,
               p.latency_ms as latency_ms, p.token_count as token_count,
               p.created_at as created_at, p.promoted_at as promoted_at,
               p.archived_at as archived_at, p.parent_version as parent_version,
               p.training_examples as training_examples
        """

        prompts: dict[PromptTask, PromptVersion] = {}
        try:
            result = await graph.query(query)
            if not result.result_set:
                return prompts

            header = [h[1] for h in result.header]
            for row in result.result_set:
                record = dict(zip(header, row))
                prompt = PromptVersion.from_db_record(record)
                prompts[prompt.task] = prompt
        except Exception as e:
            logger.error(f'Failed to fetch all live prompts: {e}')

        return prompts

    async def get_prompt_history(self, task: PromptTask, limit: int = 10) -> list[PromptVersion]:
        graph = await self._get_graph()

        query = """
        MATCH (p:PromptVersion {task: $task})
        RETURN p.id as id, p.task as task, p.version as version, p.status as status,
               p.docstring as docstring, p.demos as demos, p.accuracy as accuracy,
               p.latency_ms as latency_ms, p.token_count as token_count,
               p.created_at as created_at, p.promoted_at as promoted_at,
               p.archived_at as archived_at, p.parent_version as parent_version,
               p.training_examples as training_examples
        ORDER BY p.version DESC
        LIMIT $limit
        """

        prompts: list[PromptVersion] = []
        try:
            result = await graph.query(query, {'task': task.value, 'limit': limit})
            if not result.result_set:
                return prompts

            header = [h[1] for h in result.header]
            for row in result.result_set:
                record = dict(zip(header, row))
                prompts.append(PromptVersion.from_db_record(record))
        except Exception as e:
            logger.error(f'Failed to fetch prompt history for {task}: {e}')

        return prompts

    async def create_candidate(
        self,
        task: PromptTask,
        docstring: str,
        demos: list[dict[str, Any]] | None = None,
        parent_version: int | None = None,
        training_examples: int = 0,
    ) -> PromptVersion:
        graph = await self._get_graph()

        next_version = await self._get_next_version(task)
        prompt_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        demos_json = json.dumps(demos or [])

        query = """
        CREATE (p:PromptVersion {
            id: $id,
            task: $task,
            version: $version,
            status: 'candidate',
            docstring: $docstring,
            demos: $demos,
            accuracy: null,
            latency_ms: null,
            token_count: null,
            created_at: $created_at,
            promoted_at: null,
            archived_at: null,
            parent_version: $parent_version,
            training_examples: $training_examples
        })
        RETURN p.id as id, p.task as task, p.version as version, p.status as status,
               p.docstring as docstring, p.demos as demos, p.created_at as created_at,
               p.parent_version as parent_version, p.training_examples as training_examples
        """

        result = await graph.query(
            query,
            {
                'id': prompt_id,
                'task': task.value,
                'version': next_version,
                'docstring': docstring,
                'demos': demos_json,
                'created_at': now,
                'parent_version': parent_version,
                'training_examples': training_examples,
            },
        )

        header = [h[1] for h in result.header]
        row = result.result_set[0]
        record = dict(zip(header, row))

        logger.info(f'Created candidate {task.value} v{next_version} (id={prompt_id[:8]}...)')
        return PromptVersion.from_db_record(record)

    async def _get_next_version(self, task: PromptTask) -> int:
        graph = await self._get_graph()

        query = """
        MATCH (p:PromptVersion {task: $task})
        RETURN max(p.version) as max_version
        """

        result = await graph.query(query, {'task': task.value})
        if not result.result_set or result.result_set[0][0] is None:
            return 1
        return result.result_set[0][0] + 1

    async def update_metrics(
        self,
        prompt_id: str,
        accuracy: float | None = None,
        latency_ms: float | None = None,
        token_count: int | None = None,
    ) -> None:
        graph = await self._get_graph()

        set_clauses = []
        params: dict[str, Any] = {'id': prompt_id}

        if accuracy is not None:
            set_clauses.append('p.accuracy = $accuracy')
            params['accuracy'] = accuracy
        if latency_ms is not None:
            set_clauses.append('p.latency_ms = $latency_ms')
            params['latency_ms'] = latency_ms
        if token_count is not None:
            set_clauses.append('p.token_count = $token_count')
            params['token_count'] = token_count

        if not set_clauses:
            return

        query = f"""
        MATCH (p:PromptVersion {{id: $id}})
        SET {', '.join(set_clauses)}
        """

        await graph.query(query, params)
        logger.debug(f'Updated metrics for prompt {prompt_id[:8]}...')

    async def promote_candidate(self, prompt_id: str) -> PromptVersion:
        graph = await self._get_graph()
        now = datetime.now(timezone.utc).isoformat()

        get_task_query = """
        MATCH (p:PromptVersion {id: $id})
        RETURN p.task as task
        """
        result = await graph.query(get_task_query, {'id': prompt_id})
        if not result.result_set:
            raise ValueError(f'Prompt {prompt_id} not found')
        task = result.result_set[0][0]

        archive_query = """
        MATCH (p:PromptVersion {task: $task, status: 'live'})
        SET p.status = 'archived', p.archived_at = $archived_at
        """
        await graph.query(archive_query, {'task': task, 'archived_at': now})

        promote_query = """
        MATCH (p:PromptVersion {id: $id})
        SET p.status = 'live', p.promoted_at = $promoted_at
        RETURN p.id as id, p.task as task, p.version as version, p.status as status,
               p.docstring as docstring, p.demos as demos, p.accuracy as accuracy,
               p.latency_ms as latency_ms, p.token_count as token_count,
               p.created_at as created_at, p.promoted_at as promoted_at,
               p.archived_at as archived_at, p.parent_version as parent_version,
               p.training_examples as training_examples
        """

        result = await graph.query(promote_query, {'id': prompt_id, 'promoted_at': now})
        header = [h[1] for h in result.header]
        row = result.result_set[0]
        record = dict(zip(header, row))

        prompt = PromptVersion.from_db_record(record)

        async with self._lock:
            self._cache.set(prompt.task, prompt)

        logger.info(f'Promoted {prompt.task.value} v{prompt.version} to live')
        return prompt

    async def mark_failed(self, prompt_id: str) -> None:
        graph = await self._get_graph()

        query = """
        MATCH (p:PromptVersion {id: $id})
        SET p.status = 'failed'
        """

        await graph.query(query, {'id': prompt_id})
        logger.info(f'Marked prompt {prompt_id[:8]}... as failed')

    def invalidate_cache(self) -> None:
        self._cache.invalidate()
        logger.debug('Prompt cache invalidated')


_default_registry: PromptRegistry | None = None


def get_prompt_registry() -> PromptRegistry:
    global _default_registry
    if _default_registry is None:
        _default_registry = PromptRegistry()
    return _default_registry


def configure_prompt_registry(registry: PromptRegistry) -> None:
    global _default_registry
    _default_registry = registry
