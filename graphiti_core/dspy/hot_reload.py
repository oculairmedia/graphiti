"""
Hot-Reload Mechanism for Optimized DSPy Modules.

This module provides runtime reloading of MIPROv2-optimized modules
without requiring pipeline restart.

Features:
- File watcher for reload_ready.json marker
- Thread-safe module replacement
- Version tracking and rollback support
- Gradual rollout via percentage-based activation

Usage:
    from graphiti_core.dspy.hot_reload import HotReloader, get_hot_reloader

    # Initialize with pipeline
    reloader = HotReloader(
        pipeline=my_pipeline,
        optimized_dir='optimized_modules',
    )

    # Start background watcher
    reloader.start_watching()

    # Manual reload check
    reloader.check_and_reload()

    # Stop watcher
    reloader.stop_watching()
"""

import json
import logging
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .pipeline import DSPyIngestionPipeline

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration
# =============================================================================

@dataclass
class HotReloadConfig:
    """Configuration for hot-reload behavior."""

    # Directory containing optimized modules
    optimized_dir: str = 'optimized_modules'

    # Watch interval in seconds
    watch_interval: float = 60.0

    # Whether to enable gradual rollout
    gradual_rollout: bool = False

    # Percentage of requests to use optimized modules (0-100)
    rollout_percentage: int = 100

    # Keep backup of previous modules for rollback
    keep_backup: bool = True

    # Maximum number of backup versions to keep
    max_backups: int = 3

    @classmethod
    def from_env(cls) -> 'HotReloadConfig':
        """Create config from environment variables."""
        return cls(
            optimized_dir=os.environ.get('DSPY_OPTIMIZED_DIR', 'optimized_modules'),
            watch_interval=float(os.environ.get('DSPY_RELOAD_INTERVAL', '60')),
            gradual_rollout=os.environ.get('DSPY_GRADUAL_ROLLOUT', 'false').lower() == 'true',
            rollout_percentage=int(os.environ.get('DSPY_ROLLOUT_PERCENT', '100')),
            keep_backup=os.environ.get('DSPY_KEEP_BACKUP', 'true').lower() == 'true',
            max_backups=int(os.environ.get('DSPY_MAX_BACKUPS', '3')),
        )


# =============================================================================
# Module Version Tracking
# =============================================================================

@dataclass
class ModuleVersion:
    """Tracks a specific version of a module."""
    stage: str  # 'extraction', 'edge_extraction', 'resolution', 'summary'
    version: str  # Timestamp or version identifier
    path: str  # Path to the optimized module file
    loaded_at: str  # When it was loaded
    active: bool = True
    metrics: dict[str, float] = field(default_factory=dict)


@dataclass
class ReloadHistory:
    """Tracks reload history for debugging and rollback."""
    reloads: list[dict[str, Any]] = field(default_factory=list)
    max_entries: int = 100

    def add(self, stage: str, version: str, success: bool, error: str | None = None):
        """Record a reload attempt."""
        entry = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'stage': stage,
            'version': version,
            'success': success,
            'error': error,
        }
        self.reloads.append(entry)

        # Trim old entries
        if len(self.reloads) > self.max_entries:
            self.reloads = self.reloads[-self.max_entries:]

    def get_recent(self, count: int = 10) -> list[dict[str, Any]]:
        """Get recent reload entries."""
        return self.reloads[-count:]

    def to_dict(self) -> dict:
        """Convert to dict."""
        return {'reloads': self.reloads}


# =============================================================================
# Hot Reloader
# =============================================================================

class HotReloader:
    """
    Hot-reload manager for DSPy pipeline modules.

    Watches for optimized modules and reloads them at runtime
    without requiring pipeline restart.
    """

    _instance: 'HotReloader | None' = None
    _lock = threading.Lock()

    def __init__(
        self,
        pipeline: 'DSPyIngestionPipeline | None' = None,
        config: HotReloadConfig | None = None,
    ):
        self.config = config or HotReloadConfig.from_env()
        self.pipeline = pipeline

        # Module versions
        self.current_versions: dict[str, ModuleVersion] = {}
        self.backup_modules: dict[str, list[Any]] = {
            'extraction': [],
            'edge_extraction': [],
            'resolution': [],
            'summary': [],
        }

        # History tracking
        self.history = ReloadHistory()

        # Last processed marker timestamp
        self._last_marker_time: str | None = None

        # Watcher thread
        self._watcher_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._module_lock = threading.RLock()

    @classmethod
    def get_instance(
        cls,
        pipeline: 'DSPyIngestionPipeline | None' = None,
        config: HotReloadConfig | None = None,
    ) -> 'HotReloader':
        """Get or create singleton instance."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(pipeline, config)
            elif pipeline is not None and cls._instance.pipeline is None:
                cls._instance.pipeline = pipeline
            return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton (for testing)."""
        with cls._lock:
            if cls._instance is not None:
                cls._instance.stop_watching()
            cls._instance = None

    def set_pipeline(self, pipeline: 'DSPyIngestionPipeline') -> None:
        """Set the pipeline to reload modules into."""
        with self._module_lock:
            self.pipeline = pipeline

    # =========================================================================
    # Module Loading
    # =========================================================================

    def _get_marker_path(self) -> Path:
        """Get path to reload marker file."""
        return Path(self.config.optimized_dir) / 'reload_ready.json'

    def _read_marker(self) -> dict | None:
        """Read the reload marker file."""
        marker_path = self._get_marker_path()
        if not marker_path.exists():
            return None

        try:
            with open(marker_path) as f:
                return json.load(f)
        except Exception as e:
            logger.error(f'Failed to read reload marker: {e}')
            return None

    def _backup_current_module(self, stage: str, module: Any) -> None:
        """Backup current module before replacement."""
        if not self.config.keep_backup:
            return

        backups = self.backup_modules[stage]
        backups.append(module)

        # Trim to max backups
        if len(backups) > self.config.max_backups:
            self.backup_modules[stage] = backups[-self.config.max_backups:]

    def _load_optimized_module(self, stage: str, path: str) -> Any:
        """Load an optimized module from file."""
        from .modules import NodeExtractor, EdgeExtractor, NodeResolver, SummaryGenerator

        module_path = Path(path)
        if not module_path.exists():
            raise FileNotFoundError(f'Optimized module not found: {path}')

        # Create fresh module instance
        if stage == 'extraction':
            module = NodeExtractor()
        elif stage == 'edge_extraction':
            module = EdgeExtractor()
        elif stage == 'resolution':
            module = NodeResolver()
        elif stage == 'summary':
            module = SummaryGenerator()
        else:
            raise ValueError(f'Unknown stage: {stage}')

        # Load optimized state
        module.load(str(module_path))

        logger.info(f'Loaded optimized {stage} module from {path}')
        return module

    def _apply_module_to_pipeline(self, stage: str, module: Any) -> bool:
        """Apply loaded module to the pipeline."""
        if self.pipeline is None:
            logger.warning('No pipeline set - cannot apply module')
            return False

        with self._module_lock:
            try:
                if stage == 'extraction':
                    self._backup_current_module(stage, self.pipeline.node_extractor)
                    self.pipeline.node_extractor = module
                elif stage == 'edge_extraction':
                    self._backup_current_module(stage, self.pipeline.edge_extractor)
                    self.pipeline.edge_extractor = module
                elif stage == 'resolution':
                    self._backup_current_module(stage, self.pipeline.node_resolver)
                    self.pipeline.node_resolver = module
                elif stage == 'summary':
                    self._backup_current_module(stage, self.pipeline.summary_generator)
                    self.pipeline.summary_generator = module
                else:
                    return False

                return True
            except Exception as e:
                logger.error(f'Failed to apply {stage} module: {e}')
                return False

    def reload_stage(self, stage: str, path: str, version: str) -> bool:
        """
        Reload a specific stage's module.

        Args:
            stage: Stage name (extraction, edge_extraction, resolution, summary)
            path: Path to optimized module file
            version: Version identifier for tracking

        Returns:
            True if reload succeeded.
        """
        try:
            module = self._load_optimized_module(stage, path)

            if self._apply_module_to_pipeline(stage, module):
                self.current_versions[stage] = ModuleVersion(
                    stage=stage,
                    version=version,
                    path=path,
                    loaded_at=datetime.now(timezone.utc).isoformat(),
                    active=True,
                )
                self.history.add(stage, version, success=True)
                logger.info(f'Successfully reloaded {stage} module (version: {version})')
                return True
            else:
                self.history.add(stage, version, success=False, error='Failed to apply to pipeline')
                return False

        except Exception as e:
            error_msg = str(e)
            logger.error(f'Reload failed for {stage}: {error_msg}')
            self.history.add(stage, version, success=False, error=error_msg)
            return False

    def check_and_reload(self) -> dict[str, bool]:
        """
        Check for new optimized modules and reload if available.

        Returns:
            Dict mapping stage names to reload success status.
        """
        marker = self._read_marker()
        if not marker:
            return {}

        marker_time = marker.get('timestamp')
        if marker_time == self._last_marker_time:
            # Already processed this marker
            return {}

        stages = marker.get('stages', {})
        if not stages:
            return {}

        logger.info(f'Found reload marker with {len(stages)} stages')

        results = {}
        for stage, info in stages.items():
            if info.get('status') != 'success':
                continue

            path = info.get('output_path')
            if not path:
                continue

            # Map stage names
            stage_key = stage
            if stage == 'entity_extraction':
                stage_key = 'extraction'

            results[stage_key] = self.reload_stage(
                stage=stage_key,
                path=path,
                version=marker_time or 'unknown',
            )

        self._last_marker_time = marker_time
        return results

    # =========================================================================
    # Rollback
    # =========================================================================

    def rollback(self, stage: str) -> bool:
        """
        Rollback to previous module version.

        Args:
            stage: Stage to rollback.

        Returns:
            True if rollback succeeded.
        """
        backups = self.backup_modules.get(stage, [])
        if not backups:
            logger.warning(f'No backup available for {stage}')
            return False

        previous_module = backups.pop()

        if self._apply_module_to_pipeline(stage, previous_module):
            # Update version tracking
            if stage in self.current_versions:
                del self.current_versions[stage]
            self.history.add(stage, 'rollback', success=True)
            logger.info(f'Rolled back {stage} to previous version')
            return True
        else:
            self.history.add(stage, 'rollback', success=False, error='Failed to apply backup')
            return False

    # =========================================================================
    # Background Watcher
    # =========================================================================

    def _watcher_loop(self) -> None:
        """Background watcher thread loop."""
        logger.info(f'Hot-reload watcher started (interval: {self.config.watch_interval}s)')

        while not self._stop_event.is_set():
            try:
                results = self.check_and_reload()
                if results:
                    logger.info(f'Reload results: {results}')
            except Exception as e:
                logger.error(f'Watcher error: {e}')

            self._stop_event.wait(self.config.watch_interval)

        logger.info('Hot-reload watcher stopped')

    def start_watching(self) -> None:
        """Start background watcher thread."""
        if self._watcher_thread is not None and self._watcher_thread.is_alive():
            logger.warning('Watcher already running')
            return

        self._stop_event.clear()
        self._watcher_thread = threading.Thread(
            target=self._watcher_loop,
            name='dspy-hot-reload-watcher',
            daemon=True,
        )
        self._watcher_thread.start()

    def stop_watching(self) -> None:
        """Stop background watcher thread."""
        if self._watcher_thread is None:
            return

        self._stop_event.set()
        self._watcher_thread.join(timeout=5.0)
        self._watcher_thread = None

    def is_watching(self) -> bool:
        """Check if watcher is running."""
        return self._watcher_thread is not None and self._watcher_thread.is_alive()

    # =========================================================================
    # Status & Metrics
    # =========================================================================

    def get_status(self) -> dict[str, Any]:
        """Get current hot-reload status."""
        return {
            'watching': self.is_watching(),
            'pipeline_connected': self.pipeline is not None,
            'watch_interval': self.config.watch_interval,
            'gradual_rollout': self.config.gradual_rollout,
            'rollout_percentage': self.config.rollout_percentage,
            'current_versions': {
                stage: {
                    'version': v.version,
                    'path': v.path,
                    'loaded_at': v.loaded_at,
                    'active': v.active,
                }
                for stage, v in self.current_versions.items()
            },
            'backup_counts': {
                stage: len(backups)
                for stage, backups in self.backup_modules.items()
            },
            'recent_history': self.history.get_recent(5),
        }

    def should_use_optimized(self) -> bool:
        """
        Check if optimized modules should be used for this request.

        For gradual rollout support - returns True based on rollout_percentage.
        """
        if not self.config.gradual_rollout:
            return True

        import random
        return random.randint(1, 100) <= self.config.rollout_percentage


# =============================================================================
# Global Helper Functions
# =============================================================================

def get_hot_reloader(
    pipeline: 'DSPyIngestionPipeline | None' = None,
    config: HotReloadConfig | None = None,
) -> HotReloader:
    """Get or create global hot-reloader instance."""
    return HotReloader.get_instance(pipeline, config)


def configure_hot_reload(
    pipeline: 'DSPyIngestionPipeline | None' = None,
    optimized_dir: str | None = None,
    watch_interval: float | None = None,
    start_watching: bool = False,
    **kwargs,
) -> HotReloader:
    """
    Configure and optionally start the global hot-reloader.

    Args:
        pipeline: Pipeline to reload modules into
        optimized_dir: Directory with optimized modules
        watch_interval: Check interval in seconds
        start_watching: Start background watcher
        **kwargs: Additional config options

    Returns:
        Configured HotReloader instance.
    """
    config = HotReloadConfig.from_env()

    if optimized_dir is not None:
        config.optimized_dir = optimized_dir
    if watch_interval is not None:
        config.watch_interval = watch_interval

    for key, value in kwargs.items():
        if hasattr(config, key):
            setattr(config, key, value)

    HotReloader.reset_instance()
    reloader = HotReloader.get_instance(pipeline, config)

    if start_watching:
        reloader.start_watching()

    return reloader
