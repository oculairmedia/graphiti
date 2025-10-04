"""Replay candidate detection heuristics."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Optional
from textwrap import dedent

from graphiti_core.driver.driver import GraphDriver
from graphiti_core.helpers import parse_db_date
from graphiti_core.utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)


def _normalise_records(result: Any) -> list[dict[str, Any]]:
    """Return a list of dictionaries from Neo4j or Falkor responses."""

    if result is None:
        return []

    if isinstance(result, tuple):
        maybe_records = result[0]
        if isinstance(maybe_records, list):
            return [dict(record) if not isinstance(record, dict) else record for record in maybe_records]

    records_attr = getattr(result, 'records', None)
    if records_attr is not None:
        return [dict(record) for record in records_attr]

    if isinstance(result, list):
        return [dict(record) if not isinstance(record, dict) else record for record in result]

    return []


def _version_key(version: str | None) -> tuple[int, ...]:
    if not version:
        return tuple()

    parts = re.findall(r'\d+', version)
    if not parts:
        return tuple()

    return tuple(int(part) for part in parts)


def _coerce_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _cypher_quote(value: str | None) -> str:
    """Return a Cypher string literal or NULL."""

    if value is None:
        return 'NULL'

    if not isinstance(value, str):
        value = str(value)

    escaped = value.replace("\\", r"\\").replace("'", "''")
    return f"'{escaped}'"


def _build_extraction_version_clause(current_version: str | None) -> str:
    """Construct the extraction version mismatch condition."""

    if current_version is None:
        return 'ep.extraction_version IS NULL'

    version_literal = _cypher_quote(current_version)
    return f"(ep.extraction_version IS NULL OR ep.extraction_version <> {version_literal})"


@dataclass(slots=True)
class ReplayCandidate:
    """Replay candidate enriched with heuristic scoring."""

    episode_uuid: str
    group_id: str
    entity_count: int
    edge_count: int
    cross_group_connections: int
    extraction_version: Optional[str]
    confidence_score: Optional[float]
    valid_at: Optional[datetime]
    created_at: Optional[datetime]
    last_replayed_at: Optional[datetime]
    replay_attempts: int
    replay_reason: str
    replay_priority: float


class ReplayCandidateDetector:
    """Detect episodes that would benefit from replay."""

    ENTITY_THRESHOLD = 3
    CONFIDENCE_THRESHOLD = 0.65
    RECENCY_WINDOW_DAYS = 14
    STALE_REPLAY_WINDOW_DAYS = 14
    MIN_PRIORITY = 0.2
    SCAN_MULTIPLIER = 4

    WEIGHTS = {
        'sparsity': 0.30,
        'isolation': 0.20,
        'staleness': 0.20,
        'confidence': 0.15,
        'recent_activity': 0.10,
        'stale_replay': 0.05,
    }

    def __init__(
        self,
        driver: GraphDriver,
        *,
        current_extraction_version: str | None = None,
        now_provider: Callable[[], datetime] = utc_now,
    ) -> None:
        self.driver = driver
        self.current_extraction_version = (
            current_extraction_version
            or os.getenv('GRAPHITI_REPLAY_EXTRACTION_VERSION')
            or os.getenv('GRAPHITI_EXTRACTION_VERSION')
        )
        self._now = now_provider

    async def identify_candidates(
        self,
        group_id: str | None = None,
        limit: int = 100,
        *,
        current_extraction_version: str | None = None,
        min_priority: float | None = None,
    ) -> list[ReplayCandidate]:
        """Return replay candidates sorted by priority."""

        min_priority = self.MIN_PRIORITY if min_priority is None else min_priority
        limit = max(limit, 0)
        scan_limit = max(limit * self.SCAN_MULTIPLIER, limit or 1)

        version_to_compare = current_extraction_version or self.current_extraction_version

        records = await self._fetch_candidate_rows(
            group_id=group_id,
            max_candidates=scan_limit,
            entity_threshold=self.ENTITY_THRESHOLD,
            confidence_threshold=self.CONFIDENCE_THRESHOLD,
            current_extraction_version=version_to_compare,
        )

        candidates: list[ReplayCandidate] = []
        for record in records:
            candidate = self._build_candidate(record, version_to_compare)
            if candidate and candidate.replay_priority >= min_priority:
                candidates.append(candidate)

        candidates.sort(key=lambda cand: cand.replay_priority, reverse=True)
        if limit:
            return candidates[:limit]
        return candidates

    async def _fetch_candidate_rows(
        self,
        *,
        group_id: str | None,
        max_candidates: int,
        entity_threshold: int,
        confidence_threshold: float,
        current_extraction_version: str | None,
    ) -> list[dict[str, Any]]:
        # Get stale days threshold from environment and compute cutoff timestamp
        stale_days = float(os.getenv('REPLAY_STALE_DAYS', '90'))
        now = self._now()
        from datetime import timedelta
        cutoff_time = now - timedelta(days=stale_days)
        cutoff_iso = cutoff_time.isoformat()
        cutoff_literal = _cypher_quote(cutoff_iso)

        group_filter = f"ep.group_id = {_cypher_quote(group_id)}" if group_id else "true"
        confidence_literal = f"{confidence_threshold:.6f}"
        version_clause = _build_extraction_version_clause(current_extraction_version)

        query = dedent(
            f"""
            MATCH (ep:Episodic)
            OPTIONAL MATCH (rm:ReplayMetadata {{episode_uuid: ep.uuid}})
            WITH ep, rm,
                 coalesce(ep.entity_count, size(coalesce(ep.entity_edges, []))) AS entity_count,
                 coalesce(ep.edge_count, size(coalesce(ep.entity_edges, []))) AS edge_count,
                 coalesce(ep.cross_group_connections, 0) AS cross_group_connections,
                 coalesce(ep.confidence_score, 0.0) AS confidence_score
            WHERE {group_filter}
              AND ep.created_at IS NOT NULL
              AND ep.created_at < {cutoff_literal}
              AND (
                    entity_count < {entity_threshold}
                 OR cross_group_connections = 0
                 OR confidence_score < {confidence_literal}
                 OR {version_clause}
              )
            RETURN ep.uuid AS episode_uuid,
                   ep.group_id AS group_id,
                   entity_count,
                   edge_count,
                   cross_group_connections,
                   ep.extraction_version AS extraction_version,
                   confidence_score,
                   ep.valid_at AS valid_at,
                   ep.created_at AS created_at,
                   rm.last_replayed_at AS last_replayed_at,
                   coalesce(rm.replay_attempts, 0) AS replay_attempts
            ORDER BY ep.valid_at DESC
            LIMIT {max_candidates}
            """
        ).strip()

        logger.info('ReplayCandidateDetector query params: stale_days=%.6f, cutoff=%s, entity_threshold=%d, confidence_threshold=%.2f',
                    stale_days, cutoff_iso, entity_threshold, confidence_threshold)
        logger.info('ReplayCandidateDetector query: %s', query[:500])  # Log first 500 chars

        result = await self.driver.execute_query(query)
        rows = _normalise_records(result)
        logger.info('ReplayCandidateDetector fetched %d raw rows', len(rows))
        return rows

    def _build_candidate(
        self,
        record: dict[str, Any],
        current_version: str | None,
    ) -> ReplayCandidate | None:
        now = self._now()

        entity_count = _coerce_int(record.get('entity_count'))
        edge_count = _coerce_int(record.get('edge_count'))
        cross_group_connections = _coerce_int(record.get('cross_group_connections'))
        confidence_score = _coerce_float(record.get('confidence_score'))

        valid_at = parse_db_date(record.get('valid_at'))
        created_at = parse_db_date(record.get('created_at'))
        last_replayed_at = parse_db_date(record.get('last_replayed_at'))

        score, reasons = self._calculate_priority(
            entity_count=entity_count,
            edge_count=edge_count,
            cross_group_connections=cross_group_connections,
            confidence_score=confidence_score,
            extraction_version=record.get('extraction_version'),
            current_version=current_version,
            valid_at=valid_at,
            created_at=created_at,
            last_replayed_at=last_replayed_at,
            now=now,
        )

        if score <= 0:
            return None

        attempt_count = _coerce_int(record.get('replay_attempts'))
        reason = ','.join(sorted(reasons)) if reasons else 'unspecified'

        return ReplayCandidate(
            episode_uuid=str(record.get('episode_uuid')),
            group_id=str(record.get('group_id')),
            entity_count=entity_count,
            edge_count=edge_count,
            cross_group_connections=cross_group_connections,
            extraction_version=record.get('extraction_version'),
            confidence_score=confidence_score,
            valid_at=valid_at,
            created_at=created_at,
            last_replayed_at=last_replayed_at,
            replay_attempts=attempt_count,
            replay_reason=reason,
            replay_priority=min(score, 1.0),
        )

    def _calculate_priority(
        self,
        *,
        entity_count: int,
        edge_count: int,
        cross_group_connections: int,
        confidence_score: Optional[float],
        extraction_version: Any,
        current_version: Optional[str],
        valid_at: Optional[datetime],
        created_at: Optional[datetime],
        last_replayed_at: Optional[datetime],
        now: datetime,
    ) -> tuple[float, set[str]]:
        score = 0.0
        reasons: set[str] = set()

        # Sparsity (few entities/edges)
        if entity_count < self.ENTITY_THRESHOLD:
            deficit = self.ENTITY_THRESHOLD - entity_count
            normalized = min(deficit / self.ENTITY_THRESHOLD, 1.0)
            score += normalized * self.WEIGHTS['sparsity']
            reasons.add('sparse_entities')
        elif edge_count < self.ENTITY_THRESHOLD:
            deficit = self.ENTITY_THRESHOLD - edge_count
            normalized = min(max(deficit, 0) / self.ENTITY_THRESHOLD, 1.0)
            score += normalized * self.WEIGHTS['sparsity'] * 0.5
            if normalized > 0:
                reasons.add('low_edge_count')

        # Cross-group isolation
        if cross_group_connections <= 0:
            score += self.WEIGHTS['isolation']
            reasons.add('no_cross_group_links')
        elif cross_group_connections < 2:
            normalized = (2 - cross_group_connections) / 2
            score += normalized * self.WEIGHTS['isolation']
            reasons.add('weak_cross_group_links')

        # Extraction version staleness
        if current_version:
            if _version_key(extraction_version) < _version_key(current_version):
                score += self.WEIGHTS['staleness']
                reasons.add('stale_extraction')
        elif extraction_version is None:
            score += self.WEIGHTS['staleness']
            reasons.add('unknown_extraction_version')

        # Confidence score heuristics
        confidence_value = confidence_score if confidence_score is not None else 0.0
        if confidence_value < self.CONFIDENCE_THRESHOLD:
            gap = self.CONFIDENCE_THRESHOLD - confidence_value
            normalized = min(gap / max(self.CONFIDENCE_THRESHOLD, 1e-6), 1.0)
            score += normalized * self.WEIGHTS['confidence']
            reasons.add('low_confidence')

        # Recent activity boost based on valid_at/created_at
        reference_time = valid_at or created_at
        if reference_time is not None:
            days_since_reference = (now - reference_time).total_seconds() / 86400
            normalized = max(0.0, 1.0 - min(days_since_reference, self.RECENCY_WINDOW_DAYS) / self.RECENCY_WINDOW_DAYS)
            if normalized > 0:
                score += normalized * self.WEIGHTS['recent_activity']
                reasons.add('recent_activity')

        # Stale replay bonus (never replayed or replayed long ago)
        if last_replayed_at is None:
            score += self.WEIGHTS['stale_replay']
            reasons.add('never_replayed')
        else:
            days_since_replay = (now - last_replayed_at).total_seconds() / 86400
            normalized = min(days_since_replay / self.STALE_REPLAY_WINDOW_DAYS, 1.0)
            if normalized > 0:
                score += normalized * self.WEIGHTS['stale_replay']
                reasons.add('stale_replay')

        return score, reasons
