"""Replay execution helpers."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Mapping

from graphiti_core.driver.driver import GraphDriver
from graphiti_core.helpers import get_default_group_id, parse_db_date
from graphiti_core.nodes import EpisodeType, EpisodicNode
from graphiti_core.utils.datetime_utils import ensure_utc, utc_now

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ReplayContext:
    """Structured context describing why a replay was scheduled."""

    reason: str
    priority_score: float
    scheduled_at: datetime
    attempt_number: int
    group_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            'reason': self.reason,
            'priority_score': self.priority_score,
            'scheduled_at': self.scheduled_at.isoformat(),
            'attempt_number': self.attempt_number,
            'group_id': self.group_id,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "ReplayContext":
        if not data:
            now = utc_now()
            return cls(reason='unspecified', priority_score=0.0, scheduled_at=now, attempt_number=1)

        reason = str(data.get('reason') or 'unspecified')
        priority_raw = data.get('priority_score')
        try:
            priority_score = float(priority_raw)
        except (TypeError, ValueError):
            priority_score = 0.0

        scheduled_raw = data.get('scheduled_at')
        scheduled_at = parse_db_date(scheduled_raw) or utc_now()

        attempt_raw = data.get('attempt_number')
        try:
            attempt_number = int(attempt_raw)
        except (TypeError, ValueError):
            attempt_number = 1

        group_id = data.get('group_id')
        if group_id is not None:
            group_id = str(group_id)

        return cls(
            reason=reason,
            priority_score=priority_score,
            scheduled_at=scheduled_at,
            attempt_number=attempt_number,
            group_id=group_id,
        )

    def with_group_id(self, group_id: str) -> "ReplayContext":
        if self.group_id == group_id:
            return self
        return ReplayContext(
            reason=self.reason,
            priority_score=self.priority_score,
            scheduled_at=self.scheduled_at,
            attempt_number=self.attempt_number,
            group_id=group_id,
        )


class ReplayMetadataManager:
    """Persist replay metadata inside the graph store."""

    def __init__(self, driver: GraphDriver) -> None:
        self.driver = driver

    async def record_success(
        self,
        *,
        episode_uuid: str,
        group_id: str,
        context: ReplayContext,
        episode: EpisodicNode,
    ) -> None:
        now = utc_now()
        extraction_version = getattr(episode, 'extraction_version', None)
        confidence_score = getattr(episode, 'confidence_score', None)
        entity_count = getattr(episode, 'entity_count', None)
        edge_count = getattr(episode, 'edge_count', None)
        cross_group_connections = getattr(episode, 'cross_group_connections', None)

        query = """
        MATCH (ep:Episodic {uuid: $episode_uuid})
        SET ep.entity_count = $entity_count,
            ep.edge_count = $edge_count,
            ep.cross_group_connections = $cross_group_connections,
            ep.extraction_version = $extraction_version,
            ep.confidence_score = $confidence_score
        WITH ep
        MERGE (rm:ReplayMetadata {episode_uuid: ep.uuid})
        SET rm.group_id = $group_id,
            rm.last_replayed_at = $now,
            rm.replay_attempts = COALESCE(rm.replay_attempts, 0) + 1,
            rm.extraction_version = $extraction_version,
            rm.replay_reason = $reason,
            rm.priority_score = $priority_score,
            rm.confidence_score = $confidence_score,
            rm.updated_at = $now,
            rm.last_error = NULL,
            rm.last_failed_at = NULL
        """

        params = {
            'episode_uuid': episode_uuid,
            'group_id': group_id,
            'entity_count': entity_count,
            'edge_count': edge_count,
            'cross_group_connections': cross_group_connections,
            'extraction_version': extraction_version,
            'confidence_score': confidence_score,
            'reason': context.reason,
            'priority_score': context.priority_score,
            'now': now,
        }

        await self.driver.execute_query(query, **params)

    async def record_failure(
        self,
        *,
        episode_uuid: str,
        group_id: str,
        context: ReplayContext,
        error: BaseException,
    ) -> None:
        now = utc_now()
        query = """
        MERGE (rm:ReplayMetadata {episode_uuid: $episode_uuid})
        SET rm.group_id = $group_id,
            rm.replay_attempts = COALESCE(rm.replay_attempts, 0) + 1,
            rm.replay_reason = $reason,
            rm.priority_score = $priority_score,
            rm.last_failed_at = $now,
            rm.last_error = $error,
            rm.updated_at = $now
        """

        params = {
            'episode_uuid': episode_uuid,
            'group_id': group_id,
            'reason': context.reason,
            'priority_score': context.priority_score,
            'now': now,
            'error': str(error),
        }

        await self.driver.execute_query(query, **params)


class ReplayExecutorError(Exception):
    """Base replay execution error."""


class ReplayEpisodeNotFound(ReplayExecutorError):
    """Raised when the requested episode is missing from the graph."""

    def __init__(self, episode_uuid: str) -> None:
        super().__init__(f'Episode {episode_uuid} not found')
        self.episode_uuid = episode_uuid


class ReplayExecutor:
    """Execute replay tasks by delegating to the resilient ingestion pipeline."""

    def __init__(
        self,
        graphiti: "Graphiti",
        *,
        metadata_manager: ReplayMetadataManager | None = None,
    ) -> None:
        self.graphiti = graphiti
        self.metadata_manager = metadata_manager or ReplayMetadataManager(graphiti.driver)

    async def execute(self, episode_uuid: str, context: ReplayContext) -> Any:
        episode = await EpisodicNode.get_by_uuid(self.graphiti.driver, episode_uuid)
        if not episode:
            raise ReplayEpisodeNotFound(episode_uuid)

        group_id = episode.group_id or context.group_id or get_default_group_id(self.graphiti.driver.provider)
        context = context.with_group_id(group_id)

        reference_time = episode.valid_at or episode.created_at or utc_now()
        reference_time = ensure_utc(reference_time)

        source_description = getattr(episode, 'source_description', '') or ''
        source = getattr(episode, 'source', EpisodeType.message)

        if episode.content is None:
            logger.warning('Episode %s has no stored content; replay may be incomplete', episode_uuid)

        try:
            result = await self.graphiti.add_episode_resilient(
                name=episode.name,
                episode_body=episode.content or '',
                source_description=source_description,
                reference_time=reference_time,
                source=source,
                group_id=group_id,
                uuid=episode.uuid,
                replay_mode=True,
                replay_context=context,
            )
        except Exception as exc:  # pragma: no cover - exercised via failure tests
            await self.metadata_manager.record_failure(
                episode_uuid=episode_uuid,
                group_id=group_id,
                context=context,
                error=exc,
            )
            raise

        await self.metadata_manager.record_success(
            episode_uuid=episode_uuid,
            group_id=group_id,
            context=context,
            episode=result.episode,
        )

        return result


if TYPE_CHECKING:  # pragma: no cover - typing helpers only
    from graphiti_core.graphiti import Graphiti
