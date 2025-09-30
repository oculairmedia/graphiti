"""Runtime configuration for memory replay scheduling."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping, MutableMapping


def _parse_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {'1', 'true', 't', 'yes', 'y', 'on'}:
        return True
    if normalized in {'0', 'false', 'f', 'no', 'n', 'off'}:
        return False
    return default


def _parse_int(value: str | None, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _parse_float(value: str | None, default: float) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


@dataclass(slots=True)
class ReplayConfig:
    """Configuration parameters controlling the replay scheduler."""

    enabled: bool = False
    interval_seconds: int = 300
    batch_size: int = 10
    max_attempts: int = 3
    cooldown_hours: float = 24.0
    min_priority: float = 0.2
    max_per_group_per_hour: int = 100
    rate_limit_window_seconds: int = 3600
    circuit_breaker_threshold: int = 10
    circuit_breaker_reset_seconds: int = 900
    queue_name: str = 'memory_replay'
    candidate_scan_multiplier: int = 4
    target_group_id: str | None = None

    @classmethod
    def from_env(cls, env: Mapping[str, str] | MutableMapping[str, str] | None = None) -> "ReplayConfig":
        """Instantiate configuration from environment variables."""

        environ = env if env is not None else os.environ
        return cls(
            enabled=_parse_bool(environ.get('REPLAY_ENABLED'), cls.enabled),
            interval_seconds=_parse_int(environ.get('REPLAY_INTERVAL_SECONDS'), cls.interval_seconds),
            batch_size=_parse_int(environ.get('REPLAY_BATCH_SIZE'), cls.batch_size),
            max_attempts=_parse_int(environ.get('REPLAY_MAX_ATTEMPTS'), cls.max_attempts),
            cooldown_hours=_parse_float(environ.get('REPLAY_COOLDOWN_HOURS'), cls.cooldown_hours),
            min_priority=_parse_float(environ.get('REPLAY_MIN_PRIORITY'), cls.min_priority),
            max_per_group_per_hour=_parse_int(
                environ.get('REPLAY_MAX_PER_GROUP_PER_HOUR'),
                cls.max_per_group_per_hour,
            ),
            rate_limit_window_seconds=_parse_int(
                environ.get('REPLAY_RATE_LIMIT_WINDOW_SECONDS'),
                cls.rate_limit_window_seconds,
            ),
            circuit_breaker_threshold=_parse_int(
                environ.get('REPLAY_CIRCUIT_BREAKER_THRESHOLD'),
                cls.circuit_breaker_threshold,
            ),
            circuit_breaker_reset_seconds=_parse_int(
                environ.get('REPLAY_CIRCUIT_BREAKER_RESET_SECONDS'),
                cls.circuit_breaker_reset_seconds,
            ),
            queue_name=environ.get('REPLAY_QUEUE_NAME', cls.queue_name),
            candidate_scan_multiplier=max(
                1,
                _parse_int(environ.get('REPLAY_SCAN_MULTIPLIER'), cls.candidate_scan_multiplier),
            ),
            target_group_id=environ.get('REPLAY_TARGET_GROUP_ID'),
        )

    @property
    def cooldown_seconds(self) -> float:
        """Return the replay cooldown duration expressed in seconds."""

        return max(0.0, self.cooldown_hours * 3600.0)


__all__ = ['ReplayConfig']
