"""
Production Response Logger for DSPy Pipeline.

This module provides continuous logging of DSPy module inputs/outputs
for training data collection and prompt optimization.

Features:
- JSONL format for append-only, streaming writes
- Per-stage logging (extraction, resolution, edges, summary)
- Automatic integration with pipeline execution
- Quality scoring for filtering training examples
- Export to TrainingDataset format for MIPROv2 optimization
"""

import json
import logging
import os
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import dspy

from .signatures import (
    ExtractedEntities,
    ExtractedEdges,
    NodeResolutions,
    Summary,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration
# =============================================================================

@dataclass
class ResponseLoggerConfig:
    """Configuration for the response logger."""

    # Enable/disable logging
    enabled: bool = True

    # Storage path (directory for JSONL files)
    log_dir: str = 'dspy_logs'

    # File rotation settings
    max_file_size_mb: int = 100  # Rotate when file exceeds this size
    max_files: int = 10  # Keep this many rotated files

    # What to log
    log_inputs: bool = True
    log_outputs: bool = True
    log_errors: bool = True
    log_timing: bool = True
    log_tokens: bool = True

    # Truncation for large inputs
    max_message_length: int = 10000  # Truncate messages longer than this

    # Quality threshold for training data export
    min_quality_score: float = 0.5

    @classmethod
    def from_env(cls) -> 'ResponseLoggerConfig':
        """Create config from environment variables."""
        return cls(
            enabled=os.environ.get('DSPY_LOG_ENABLED', 'true').lower() == 'true',
            log_dir=os.environ.get('DSPY_LOG_DIR', 'dspy_logs'),
            max_file_size_mb=int(os.environ.get('DSPY_LOG_MAX_SIZE_MB', '100')),
            max_files=int(os.environ.get('DSPY_LOG_MAX_FILES', '10')),
            min_quality_score=float(os.environ.get('DSPY_LOG_MIN_QUALITY', '0.5')),
        )


# =============================================================================
# Log Entry Types
# =============================================================================

@dataclass
class StageLogEntry:
    """A single log entry for a pipeline stage."""

    # Identifiers
    timestamp: str
    episode_id: str
    group_id: str
    stage: str  # 'extraction', 'resolution', 'edges', 'summary'

    # Inputs (what was sent to the LLM)
    inputs: dict[str, Any] = field(default_factory=dict)

    # Outputs (what the LLM returned)
    outputs: dict[str, Any] = field(default_factory=dict)

    # Metrics
    duration_ms: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0

    # Status
    success: bool = True
    error: str | None = None

    # Quality (for training data filtering)
    quality_score: float = 1.0
    quality_notes: list[str] = field(default_factory=list)

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(asdict(self), default=str, ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> 'StageLogEntry':
        """Deserialize from JSON string."""
        data = json.loads(json_str)
        return cls(**data)


@dataclass
class EpisodeLogEntry:
    """Complete log entry for an entire episode ingestion."""

    # Identifiers
    timestamp: str
    episode_id: str
    group_id: str

    # Content (potentially truncated)
    content: str
    content_length: int

    # Stage results
    extraction: StageLogEntry | None = None
    resolution: StageLogEntry | None = None
    edges: StageLogEntry | None = None
    summaries: list[StageLogEntry] = field(default_factory=list)

    # Aggregate metrics
    total_duration_ms: float = 0.0
    total_tokens: int = 0

    # Final results
    entity_count: int = 0
    edge_count: int = 0
    new_entity_count: int = 0

    # Status
    success: bool = True
    errors: list[str] = field(default_factory=list)

    def to_json(self) -> str:
        """Serialize to JSON string."""
        data = asdict(self)
        return json.dumps(data, default=str, ensure_ascii=False)


# =============================================================================
# Response Logger
# =============================================================================

class ResponseLogger:
    """
    Production response logger for DSPy pipeline.

    Captures all inputs/outputs from pipeline stages for:
    - Debugging and monitoring
    - Training data collection for MIPROv2 optimization
    - Quality analysis and improvement

    Usage:
        # Global singleton (recommended)
        logger = ResponseLogger.get_instance()

        # Or create with custom config
        logger = ResponseLogger(config=ResponseLoggerConfig(log_dir='/custom/path'))

        # Log a stage
        logger.log_extraction(
            episode_id='ep_123',
            group_id='default',
            inputs={...},
            outputs=extracted_entities,
            duration_ms=150.0,
        )

        # Log complete episode
        logger.log_episode(pipeline_result)
    """

    _instance: 'ResponseLogger | None' = None
    _lock = threading.Lock()

    def __init__(self, config: ResponseLoggerConfig | None = None):
        self.config = config or ResponseLoggerConfig.from_env()
        self._setup_log_dir()
        self._file_handles: dict[str, Any] = {}
        self._file_lock = threading.Lock()

    @classmethod
    def get_instance(cls, config: ResponseLoggerConfig | None = None) -> 'ResponseLogger':
        """Get or create the singleton instance."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(config)
            return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton (for testing)."""
        with cls._lock:
            if cls._instance is not None:
                cls._instance.close()
            cls._instance = None

    def _setup_log_dir(self) -> None:
        """Create log directory if needed."""
        Path(self.config.log_dir).mkdir(parents=True, exist_ok=True)

    def _get_log_file(self, stage: str) -> Path:
        """Get the current log file for a stage."""
        return Path(self.config.log_dir) / f'{stage}.jsonl'

    def _check_rotation(self, filepath: Path) -> None:
        """Check if file needs rotation and rotate if necessary."""
        if not filepath.exists():
            return

        size_mb = filepath.stat().st_size / (1024 * 1024)
        if size_mb < self.config.max_file_size_mb:
            return

        # Rotate files
        for i in range(self.config.max_files - 1, 0, -1):
            old_path = filepath.with_suffix(f'.{i}.jsonl')
            new_path = filepath.with_suffix(f'.{i + 1}.jsonl')
            if old_path.exists():
                if i + 1 >= self.config.max_files:
                    old_path.unlink()  # Delete oldest
                else:
                    old_path.rename(new_path)

        # Rotate current file
        filepath.rename(filepath.with_suffix('.1.jsonl'))

    def _write_entry(self, stage: str, entry: StageLogEntry) -> None:
        """Write a log entry to the appropriate file."""
        if not self.config.enabled:
            return

        filepath = self._get_log_file(stage)

        with self._file_lock:
            self._check_rotation(filepath)
            try:
                with open(filepath, 'a', encoding='utf-8') as f:
                    f.write(entry.to_json() + '\n')
            except Exception as e:
                logger.error(f'Failed to write log entry: {e}')

    def _truncate_message(self, message: str) -> str:
        """Truncate message if too long."""
        if len(message) <= self.config.max_message_length:
            return message
        return message[:self.config.max_message_length] + f'... [truncated, total {len(message)} chars]'

    def _compute_quality_score(
        self,
        stage: str,
        inputs: dict,
        outputs: dict,
        success: bool,
    ) -> tuple[float, list[str]]:
        """
        Compute quality score for training data filtering.

        Returns (score, notes) where score is 0.0-1.0.
        """
        if not success:
            return 0.0, ['Stage failed']

        score = 1.0
        notes = []

        if stage == 'extraction':
            entities = outputs.get('extracted_entities', [])
            if not entities:
                score = 0.3
                notes.append('No entities extracted')
            elif len(entities) > 20:
                score = 0.7
                notes.append('High entity count - may be over-extraction')

        elif stage == 'resolution':
            resolutions = outputs.get('entity_resolutions', [])
            if not resolutions:
                score = 0.5
                notes.append('No resolutions produced')

        elif stage == 'edges':
            edges = outputs.get('edges', [])
            if not edges:
                score = 0.5
                notes.append('No edges extracted')
            # Check for self-referential edges
            for edge in edges:
                if edge.get('source_entity_id') == edge.get('target_entity_id'):
                    score = min(score, 0.6)
                    notes.append('Self-referential edge detected')
                    break

        elif stage == 'summary':
            summary = outputs.get('summary', '')
            if not summary or len(summary) < 20:
                score = 0.3
                notes.append('Summary too short')
            elif len(summary.split()) > 300:
                score = 0.7
                notes.append('Summary exceeds word limit')

        return score, notes

    # =========================================================================
    # Public Logging Methods
    # =========================================================================

    def _extract_from_prediction(self, prediction: Any, field_name: str) -> Any:
        """Extract a field from a DSPy Prediction object."""
        if isinstance(prediction, dspy.Prediction):
            return getattr(prediction, field_name, None)
        return prediction

    def log_extraction(
        self,
        episode_id: str,
        group_id: str,
        inputs: dict[str, Any],
        outputs: ExtractedEntities | dspy.Prediction | dict | None,
        duration_ms: float = 0.0,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        success: bool = True,
        error: str | None = None,
    ) -> StageLogEntry:
        """Log an entity extraction stage."""

        # Handle DSPy Prediction wrapper
        if isinstance(outputs, dspy.Prediction):
            outputs = self._extract_from_prediction(outputs, 'extracted_entities')

        # Normalize outputs to dict
        output_dict: dict[str, Any]
        if isinstance(outputs, ExtractedEntities):
            output_dict = {
                'extracted_entities': [
                    {'name': e.name, 'entity_type_id': e.entity_type_id}
                    for e in outputs.extracted_entities
                ]
            }
        elif isinstance(outputs, dict):
            output_dict = outputs
        else:
            output_dict = {'extracted_entities': []}

        # Truncate large inputs
        processed_inputs = {
            'current_message': self._truncate_message(inputs.get('current_message', '')),
            'entity_types': inputs.get('entity_types', []),
            'previous_message_count': len(inputs.get('previous_messages', [])),
            'has_custom_instructions': bool(inputs.get('custom_instructions')),
        }

        quality_score, quality_notes = self._compute_quality_score(
            'extraction', processed_inputs, output_dict, success
        )

        entry = StageLogEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            episode_id=episode_id,
            group_id=group_id,
            stage='extraction',
            inputs=processed_inputs if self.config.log_inputs else {},
            outputs=output_dict if self.config.log_outputs else {},
            duration_ms=duration_ms if self.config.log_timing else 0.0,
            prompt_tokens=prompt_tokens if self.config.log_tokens else 0,
            completion_tokens=completion_tokens if self.config.log_tokens else 0,
            success=success,
            error=error if self.config.log_errors else None,
            quality_score=quality_score,
            quality_notes=quality_notes,
        )

        self._write_entry('extraction', entry)
        return entry

    def log_resolution(
        self,
        episode_id: str,
        group_id: str,
        inputs: dict[str, Any],
        outputs: NodeResolutions | dspy.Prediction | dict | None,
        duration_ms: float = 0.0,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        success: bool = True,
        error: str | None = None,
    ) -> StageLogEntry:
        """Log a node resolution/deduplication stage."""

        # Handle DSPy Prediction wrapper
        if isinstance(outputs, dspy.Prediction):
            outputs = self._extract_from_prediction(outputs, 'entity_resolutions')

        # Normalize outputs to dict
        output_dict: dict[str, Any]
        if isinstance(outputs, NodeResolutions):
            output_dict = {
                'entity_resolutions': [
                    {
                        'id': r.id,
                        'name': r.name,
                        'duplicate_idx': r.duplicate_idx,
                        'duplicates': r.duplicates,
                    }
                    for r in outputs.entity_resolutions
                ]
            }
        elif isinstance(outputs, dict):
            output_dict = outputs
        else:
            output_dict = {'entity_resolutions': []}

        # Summarize inputs
        processed_inputs = {
            'current_message': self._truncate_message(inputs.get('current_message', '')),
            'extracted_entity_count': len(inputs.get('extracted_entities', [])),
            'existing_entity_count': len(inputs.get('existing_entities', [])),
            'previous_message_count': len(inputs.get('previous_messages', [])),
        }

        quality_score, quality_notes = self._compute_quality_score(
            'resolution', processed_inputs, output_dict, success
        )

        entry = StageLogEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            episode_id=episode_id,
            group_id=group_id,
            stage='resolution',
            inputs=processed_inputs if self.config.log_inputs else {},
            outputs=output_dict if self.config.log_outputs else {},
            duration_ms=duration_ms if self.config.log_timing else 0.0,
            prompt_tokens=prompt_tokens if self.config.log_tokens else 0,
            completion_tokens=completion_tokens if self.config.log_tokens else 0,
            success=success,
            error=error if self.config.log_errors else None,
            quality_score=quality_score,
            quality_notes=quality_notes,
        )

        self._write_entry('resolution', entry)
        return entry

    def log_edges(
        self,
        episode_id: str,
        group_id: str,
        inputs: dict[str, Any],
        outputs: ExtractedEdges | dspy.Prediction | dict | None,
        duration_ms: float = 0.0,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        success: bool = True,
        error: str | None = None,
    ) -> StageLogEntry:
        """Log an edge extraction stage."""

        # Handle DSPy Prediction wrapper
        if isinstance(outputs, dspy.Prediction):
            outputs = self._extract_from_prediction(outputs, 'extracted_edges')

        # Normalize outputs to dict
        output_dict: dict[str, Any]
        if isinstance(outputs, ExtractedEdges):
            output_dict = {
                'edges': [
                    {
                        'relation_type': e.relation_type,
                        'source_entity_id': e.source_entity_id,
                        'target_entity_id': e.target_entity_id,
                        'fact': e.fact,
                        'valid_at': e.valid_at,
                        'invalid_at': e.invalid_at,
                    }
                    for e in outputs.edges
                ]
            }
        elif isinstance(outputs, dict):
            output_dict = outputs
        else:
            output_dict = {'edges': []}

        # Summarize inputs
        processed_inputs = {
            'current_message': self._truncate_message(inputs.get('current_message', '')),
            'entity_count': len(inputs.get('entities', [])),
            'reference_time': inputs.get('reference_time', ''),
            'edge_type_count': len(inputs.get('edge_types', [])),
            'previous_message_count': len(inputs.get('previous_messages', [])),
        }

        quality_score, quality_notes = self._compute_quality_score(
            'edges', processed_inputs, output_dict, success
        )

        entry = StageLogEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            episode_id=episode_id,
            group_id=group_id,
            stage='edges',
            inputs=processed_inputs if self.config.log_inputs else {},
            outputs=output_dict if self.config.log_outputs else {},
            duration_ms=duration_ms if self.config.log_timing else 0.0,
            prompt_tokens=prompt_tokens if self.config.log_tokens else 0,
            completion_tokens=completion_tokens if self.config.log_tokens else 0,
            success=success,
            error=error if self.config.log_errors else None,
            quality_score=quality_score,
            quality_notes=quality_notes,
        )

        self._write_entry('edges', entry)
        return entry

    def log_summary(
        self,
        episode_id: str,
        group_id: str,
        entity_name: str,
        inputs: dict[str, Any],
        outputs: Summary | dspy.Prediction | dict | str | None,
        duration_ms: float = 0.0,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        success: bool = True,
        error: str | None = None,
    ) -> StageLogEntry:
        """Log a summary generation stage."""

        # Handle DSPy Prediction wrapper
        if isinstance(outputs, dspy.Prediction):
            outputs = self._extract_from_prediction(outputs, 'summary')

        # Normalize outputs to dict
        output_dict: dict[str, Any]
        if isinstance(outputs, Summary):
            output_dict = {'summary': outputs.summary}
        elif isinstance(outputs, str):
            output_dict = {'summary': outputs}
        elif isinstance(outputs, dict):
            output_dict = outputs
        else:
            output_dict = {'summary': ''}

        # Summarize inputs
        processed_inputs = {
            'entity_name': entity_name,
            'current_message': self._truncate_message(inputs.get('current_message', '')),
            'has_existing_summary': bool(inputs.get('existing_summary')),
            'previous_message_count': len(inputs.get('previous_messages', [])),
        }

        quality_score, quality_notes = self._compute_quality_score(
            'summary', processed_inputs, output_dict, success
        )

        entry = StageLogEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            episode_id=episode_id,
            group_id=group_id,
            stage='summary',
            inputs=processed_inputs if self.config.log_inputs else {},
            outputs=output_dict if self.config.log_outputs else {},
            duration_ms=duration_ms if self.config.log_timing else 0.0,
            prompt_tokens=prompt_tokens if self.config.log_tokens else 0,
            completion_tokens=completion_tokens if self.config.log_tokens else 0,
            success=success,
            error=error if self.config.log_errors else None,
            quality_score=quality_score,
            quality_notes=quality_notes,
        )

        self._write_entry('summary', entry)
        return entry

    def log_episode_complete(
        self,
        episode_id: str,
        group_id: str,
        content: str,
        total_duration_ms: float,
        total_tokens: int,
        entity_count: int,
        edge_count: int,
        new_entity_count: int,
        success: bool,
        errors: list[str],
    ) -> None:
        """Log episode completion summary."""
        entry = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'episode_id': episode_id,
            'group_id': group_id,
            'content_length': len(content),
            'content_preview': self._truncate_message(content[:500]),
            'total_duration_ms': total_duration_ms,
            'total_tokens': total_tokens,
            'entity_count': entity_count,
            'edge_count': edge_count,
            'new_entity_count': new_entity_count,
            'success': success,
            'errors': errors,
        }

        filepath = self._get_log_file('episodes')
        with self._file_lock:
            self._check_rotation(filepath)
            try:
                with open(filepath, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(entry, default=str, ensure_ascii=False) + '\n')
            except Exception as e:
                logger.error(f'Failed to write episode log: {e}')

    # =========================================================================
    # Export & Analysis
    # =========================================================================

    def read_logs(
        self,
        stage: str,
        min_quality: float | None = None,
        limit: int | None = None,
    ) -> list[StageLogEntry]:
        """
        Read log entries for a stage.

        Args:
            stage: Stage name ('extraction', 'resolution', 'edges', 'summary')
            min_quality: Minimum quality score filter
            limit: Maximum entries to return

        Returns:
            List of StageLogEntry objects.
        """
        filepath = self._get_log_file(stage)
        if not filepath.exists():
            return []

        entries = []
        min_q = min_quality if min_quality is not None else self.config.min_quality_score

        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = StageLogEntry.from_json(line)
                    if entry.quality_score >= min_q:
                        entries.append(entry)
                        if limit and len(entries) >= limit:
                            break
                except Exception as e:
                    logger.warning(f'Failed to parse log entry: {e}')

        return entries

    def export_to_training_data(
        self,
        stage: str,
        output_path: str | Path,
        min_quality: float | None = None,
    ) -> int:
        """
        Export logs to TrainingDataset format for MIPROv2.

        Args:
            stage: Stage to export
            output_path: Path for output JSON file
            min_quality: Minimum quality score

        Returns:
            Number of examples exported.
        """
        from .optimization import TrainingDataset

        entries = self.read_logs(stage, min_quality=min_quality)

        dataset = TrainingDataset(task_name=stage)

        for entry in entries:
            if not entry.success:
                continue

            dataset.add_example(
                inputs=entry.inputs,
                expected_output=entry.outputs,
                metadata={
                    'episode_id': entry.episode_id,
                    'group_id': entry.group_id,
                    'timestamp': entry.timestamp,
                    'quality_score': entry.quality_score,
                },
            )

        dataset.save(output_path)
        logger.info(f'Exported {len(dataset.examples)} examples to {output_path}')

        return len(dataset.examples)

    def get_stats(self) -> dict[str, Any]:
        """Get logging statistics."""
        stats = {}

        for stage in ['extraction', 'resolution', 'edges', 'summary', 'episodes']:
            filepath = self._get_log_file(stage)
            if filepath.exists():
                line_count = sum(1 for _ in open(filepath, 'r', encoding='utf-8'))
                size_mb = filepath.stat().st_size / (1024 * 1024)
                stats[stage] = {
                    'entries': line_count,
                    'size_mb': round(size_mb, 2),
                }
            else:
                stats[stage] = {'entries': 0, 'size_mb': 0}

        return stats

    def close(self) -> None:
        """Close any open file handles."""
        with self._file_lock:
            for handle in self._file_handles.values():
                try:
                    handle.close()
                except Exception:
                    pass
            self._file_handles.clear()


# =============================================================================
# Global Helper Functions
# =============================================================================

def get_response_logger() -> ResponseLogger:
    """Get the global response logger instance."""
    return ResponseLogger.get_instance()


def configure_response_logger(
    enabled: bool | None = None,
    log_dir: str | None = None,
    **kwargs,
) -> ResponseLogger:
    """
    Configure the global response logger.

    Args:
        enabled: Enable/disable logging
        log_dir: Directory for log files
        **kwargs: Additional config options

    Returns:
        Configured ResponseLogger instance.
    """
    config = ResponseLoggerConfig.from_env()

    if enabled is not None:
        config.enabled = enabled
    if log_dir is not None:
        config.log_dir = log_dir

    for key, value in kwargs.items():
        if hasattr(config, key):
            setattr(config, key, value)

    ResponseLogger.reset_instance()
    return ResponseLogger.get_instance(config)
