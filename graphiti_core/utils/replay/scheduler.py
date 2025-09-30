"""Memory replay scheduling loop and queue publisher."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Callable, DefaultDict, Deque, Iterable, List

from graphiti_core.config.replay_config import ReplayConfig
from graphiti_core.ingestion.queue_client import IngestionTask, QueuedClient, TaskPriority, TaskType
from graphiti_core.utils.datetime_utils import utc_now
from graphiti_core.utils.replay.candidate_detector import ReplayCandidate, ReplayCandidateDetector

if TYPE_CHECKING:  # pragma: no cover - typing helpers only
    from graphiti_core.graphiti import Graphiti

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ReplaySchedulerStatus:
    """Lightweight snapshot of scheduler state."""

    enabled: bool
    running: bool
    queue_name: str
    last_run_at: datetime | None
    last_scheduled: int
    last_error: str | None
    batch_size: int
    min_priority: float

    def as_dict(self) -> dict[str, object]:
        return {
            'enabled': self.enabled,
            'running': self.running,
            'queue_name': self.queue_name,
            'last_run_at': self.last_run_at.isoformat() if self.last_run_at else None,
            'last_scheduled': self.last_scheduled,
            'last_error': self.last_error,
            'batch_size': self.batch_size,
            'min_priority': self.min_priority,
        }


class MemoryReplayScheduler:
    """Coordinate detection of replay candidates and queue publishing."""

    def __init__(
        self,
        *,
        queue_client: QueuedClient,
        config: ReplayConfig | None = None,
        candidate_detector: ReplayCandidateDetector | None = None,
        graphiti: "Graphiti" | None = None,
        now_provider: Callable[[], datetime] = utc_now,
    ) -> None:
        if candidate_detector is None:
            if graphiti is None:
                raise ValueError('graphiti or candidate_detector must be provided')
            candidate_detector = ReplayCandidateDetector(graphiti.driver)

        self.queue_client = queue_client
        self.config = config or ReplayConfig()
        self.candidate_detector = candidate_detector
        self._now = now_provider

        self._running = False
        self._task: asyncio.Task | None = None

        # Track recent scheduling activity per group to enforce rate limits.
        self._group_schedule_history: DefaultDict[str, Deque[datetime]] = defaultdict(deque)
        self._id_sequence = 0
        self._last_run_at: datetime | None = None
        self._last_scheduled: int = 0
        self._last_error: str | None = None

    async def start(self) -> None:
        """Start the continuous scheduler loop as a background task."""

        if not self.config.enabled:
            logger.info('Memory replay scheduler is disabled; start request ignored')
            return

        if self._task and not self._task.done():
            logger.debug('Memory replay scheduler already running')
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop(), name='memory-replay-scheduler')
        logger.info('Memory replay scheduler loop started')

    async def stop(self) -> None:
        """Stop the scheduler loop and await the background task."""

        self._running = False
        if self._task is None:
            return

        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:  # pragma: no cover - normal cancellation path
            pass
        finally:
            self._task = None
            logger.info('Memory replay scheduler loop stopped')

    async def run_cycle(self) -> int:
        """Execute a single scheduling cycle.

        Returns
        -------
        int
            Number of replay tasks published to the queue during the cycle.
        """

        if not self.config.enabled:
            logger.debug('Memory replay scheduler disabled; skipping cycle')
            self._last_run_at = self._now()
            self._last_scheduled = 0
            return 0

        now = self._now()
        candidate_limit = max(1, self.config.batch_size * self.config.candidate_scan_multiplier)

        candidates = await self.candidate_detector.identify_candidates(
            group_id=self.config.target_group_id,
            limit=candidate_limit,
            min_priority=self.config.min_priority,
        )

        if not candidates:
            logger.debug('Memory replay scheduler found no candidates')
            self._last_run_at = now
            self._last_scheduled = 0
            self._last_error = None
            return 0

        selected = self._select_candidates(candidates, now)
        if not selected:
            logger.debug('Memory replay scheduler selected no candidates after safety filters')
            self._last_run_at = now
            self._last_scheduled = 0
            self._last_error = None
            return 0

        tasks = [self._build_task(candidate, now) for candidate in selected]
        await self.queue_client.push(tasks, queue_name=self.config.queue_name)

        for candidate in selected:
            self._record_group_schedule(candidate.group_id, now)

        logger.info('Scheduled %s replay task(s)', len(selected))
        self._last_run_at = now
        self._last_scheduled = len(selected)
        self._last_error = None
        return len(selected)

    async def _run_loop(self) -> None:
        """Background loop that periodically executes scheduling cycles."""

        interval = max(1, self.config.interval_seconds)
        while self._running:
            try:
                await self.run_cycle()
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.exception('Memory replay scheduler cycle failed: %s', exc)
                self._last_error = str(exc)
                await asyncio.sleep(interval * 2)

    def _select_candidates(self, candidates: Iterable[ReplayCandidate], now: datetime) -> List[ReplayCandidate]:
        """Apply safety filters and batch size limits to the candidate stream."""

        selected: List[ReplayCandidate] = []
        per_cycle_counts: DefaultDict[str, int] = defaultdict(int)

        for candidate in candidates:
            if len(selected) >= self.config.batch_size:
                break

            if self._exceeds_attempt_limit(candidate):
                logger.debug('Skipping %s due to attempt limit', candidate.episode_uuid)
                continue

            if self._within_cooldown(candidate, now):
                logger.debug('Skipping %s due to cooldown window', candidate.episode_uuid)
                continue

            if not self._within_group_limit(candidate.group_id, now, per_cycle_counts[candidate.group_id]):
                logger.debug('Skipping %s due to group rate limit', candidate.episode_uuid)
                continue

            selected.append(candidate)
            per_cycle_counts[candidate.group_id] += 1

        return selected

    def _exceeds_attempt_limit(self, candidate: ReplayCandidate) -> bool:
        """Return True if the candidate exceeds the configured attempt budget."""

        if self.config.max_attempts <= 0:
            return False
        return candidate.replay_attempts >= self.config.max_attempts

    def _within_cooldown(self, candidate: ReplayCandidate, now: datetime) -> bool:
        """Return True if the candidate is still within the cooldown window."""

        if self.config.cooldown_seconds <= 0:
            return False
        last_replay = candidate.last_replayed_at
        if last_replay is None:
            return False
        cooldown_delta = timedelta(seconds=self.config.cooldown_seconds)
        return now - last_replay < cooldown_delta

    def _within_group_limit(self, group_id: str, now: datetime, scheduled_this_cycle: int) -> bool:
        """Check rate limiting for a group taking into account current cycle selections."""

        limit = self.config.max_per_group_per_hour
        if limit <= 0:
            return True

        history = self._group_schedule_history[group_id]
        window = timedelta(seconds=max(1, self.config.rate_limit_window_seconds))
        cutoff = now - window
        while history and history[0] < cutoff:
            history.popleft()

        return len(history) + scheduled_this_cycle < limit

    def _record_group_schedule(self, group_id: str, scheduled_at: datetime) -> None:
        """Record that a group has been scheduled at the given time."""

        self._group_schedule_history[group_id].append(scheduled_at)

    def _build_task(self, candidate: ReplayCandidate, now: datetime) -> IngestionTask:
        """Construct an ingestion task describing the replay operation."""

        self._id_sequence += 1
        task_id = f"replay-{candidate.episode_uuid}-{int(now.timestamp() * 1000)}-{self._id_sequence}"
        payload = {
            'episode_uuid': candidate.episode_uuid,
            'group_id': candidate.group_id,
            'replay_context': {
                'reason': candidate.replay_reason,
                'priority_score': candidate.replay_priority,
                'scheduled_at': now.isoformat(),
                'attempt_number': candidate.replay_attempts + 1,
            },
        }
        metadata = {
            'replay_reason': candidate.replay_reason,
            'priority_score': candidate.replay_priority,
        }

        return IngestionTask(
            id=task_id,
            type=TaskType.REPLAY,
            payload=payload,
            group_id=candidate.group_id,
            priority=TaskPriority.NORMAL,
            metadata=metadata,
        )

    def get_status(self) -> ReplaySchedulerStatus:
        """Expose scheduler state for monitoring."""

        return ReplaySchedulerStatus(
            enabled=self.config.enabled,
            running=bool(self._running and self._task and not self._task.done()),
            queue_name=self.config.queue_name,
            last_run_at=self._last_run_at,
            last_scheduled=self._last_scheduled,
            last_error=self._last_error,
            batch_size=self.config.batch_size,
            min_priority=self.config.min_priority,
        )


__all__ = ['MemoryReplayScheduler', 'ReplaySchedulerStatus']
