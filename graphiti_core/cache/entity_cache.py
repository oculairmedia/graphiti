"""
Entity Summary Cache for Graphiti.

Provides caching of entity summaries to avoid regenerating summaries for
entities that have already been processed. This can reduce LLM calls by
30-50% for repeat entities across episodes.

Usage:
    from graphiti_core.cache import get_entity_cache

    cache = get_entity_cache()

    # Check for cached summary
    cached = cache.get_cached_summary('John Doe', 'group-123')
    if cached:
        node.summary = cached
    else:
        # Generate summary via LLM
        summary = await generate_summary(node)
        cache.cache_summary('John Doe', 'group-123', summary)
"""

import hashlib
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from diskcache import Cache

logger = logging.getLogger(__name__)

# Default configuration
DEFAULT_CACHE_DIR = './entity_summary_cache'
DEFAULT_TTL_SECONDS = 86400 * 7  # 7 days
DEFAULT_MAX_SIZE_MB = 500  # 500MB


def _get_cache_enabled_default() -> bool:
    """Get default cache enabled value from environment."""
    env_value = os.environ.get('GRAPHITI_ENTITY_CACHE_ENABLED', 'true').lower()
    return env_value in ('true', '1', 'yes', 'on')


@dataclass
class EntityCacheConfig:
    """Configuration for entity summary cache."""

    # Whether caching is enabled
    enabled: bool = True

    # Cache directory
    cache_dir: str = DEFAULT_CACHE_DIR

    # Time-to-live for cache entries in seconds
    ttl_seconds: int = DEFAULT_TTL_SECONDS

    # Maximum cache size in MB
    max_size_mb: int = DEFAULT_MAX_SIZE_MB

    # Minimum summary length to cache (avoid caching empty/short summaries)
    min_summary_length: int = 10

    @classmethod
    def from_env(cls) -> 'EntityCacheConfig':
        """Create config from environment variables."""
        return cls(
            enabled=_get_cache_enabled_default(),
            cache_dir=os.environ.get('GRAPHITI_ENTITY_CACHE_DIR', DEFAULT_CACHE_DIR),
            ttl_seconds=int(os.environ.get('GRAPHITI_ENTITY_CACHE_TTL', str(DEFAULT_TTL_SECONDS))),
            max_size_mb=int(os.environ.get('GRAPHITI_ENTITY_CACHE_SIZE_MB', str(DEFAULT_MAX_SIZE_MB))),
            min_summary_length=int(os.environ.get('GRAPHITI_ENTITY_CACHE_MIN_LENGTH', '10')),
        )


@dataclass
class CacheStats:
    """Statistics for cache performance monitoring."""

    hits: int = 0
    misses: int = 0
    stores: int = 0
    evictions: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)

    def record_hit(self):
        with self.lock:
            self.hits += 1

    def record_miss(self):
        with self.lock:
            self.misses += 1

    def record_store(self):
        with self.lock:
            self.stores += 1

    def record_eviction(self):
        with self.lock:
            self.evictions += 1

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            'hits': self.hits,
            'misses': self.misses,
            'stores': self.stores,
            'evictions': self.evictions,
            'hit_rate': f'{self.hit_rate:.2%}',
        }


class EntitySummaryCache:
    """
    Cache for entity summaries to reduce redundant LLM calls.

    Uses disk-based caching with TTL support. Summaries are keyed by
    entity name and group_id to ensure proper isolation.
    """

    _instance: 'EntitySummaryCache | None' = None
    _lock = threading.Lock()

    def __init__(self, config: EntityCacheConfig | None = None):
        self.config = config or EntityCacheConfig.from_env()
        self.stats = CacheStats()
        self._cache: Cache | None = None

        if self.config.enabled:
            self._initialize_cache()

    def _initialize_cache(self):
        """Initialize the disk cache."""
        try:
            # Convert MB to bytes for size limit
            size_limit = self.config.max_size_mb * 1024 * 1024
            self._cache = Cache(
                self.config.cache_dir,
                size_limit=size_limit,
                eviction_policy='least-recently-used',
            )
            logger.info(
                f'Entity summary cache initialized '
                f'(dir={self.config.cache_dir}, '
                f'ttl={self.config.ttl_seconds}s, '
                f'max_size={self.config.max_size_mb}MB)'
            )
        except Exception as e:
            logger.error(f'Failed to initialize entity cache: {e}')
            self._cache = None

    @classmethod
    def get_instance(cls, config: EntityCacheConfig | None = None) -> 'EntitySummaryCache':
        """Get or create singleton instance."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(config)
            return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton (for testing)."""
        with cls._lock:
            if cls._instance is not None and cls._instance._cache is not None:
                cls._instance._cache.close()
            cls._instance = None

    def _make_key(self, entity_name: str, group_id: str) -> str:
        """Create a cache key from entity name and group_id."""
        # Normalize the entity name (case-insensitive, stripped)
        normalized_name = entity_name.strip().lower()
        normalized_group = group_id.strip() if group_id else 'default'

        # Create a deterministic key
        key_str = f'{normalized_group}:{normalized_name}'
        return hashlib.sha256(key_str.encode()).hexdigest()[:32]

    def get_cached_summary(self, entity_name: str, group_id: str) -> str | None:
        """
        Get a cached summary for an entity.

        Args:
            entity_name: Name of the entity
            group_id: Group ID for isolation

        Returns:
            Cached summary string, or None if not found
        """
        if not self.config.enabled or self._cache is None:
            return None

        key = self._make_key(entity_name, group_id)

        try:
            entry = self._cache.get(key)
            if entry is not None and isinstance(entry, tuple) and len(entry) == 2:
                # Check TTL - diskcache returns tuple of (timestamp, summary)
                stored_time = float(entry[0])  # type: ignore[arg-type]
                summary = str(entry[1])  # type: ignore[arg-type]
                if time.time() - stored_time < self.config.ttl_seconds:
                    self.stats.record_hit()
                    logger.debug(f'Cache hit for entity "{entity_name}" in group "{group_id}"')
                    return summary
                else:
                    # Expired - delete and return None
                    self._cache.delete(key)
                    self.stats.record_eviction()

            self.stats.record_miss()
            return None

        except Exception as e:
            logger.warning(f'Cache read error for "{entity_name}": {e}')
            self.stats.record_miss()
            return None

    def cache_summary(self, entity_name: str, group_id: str, summary: str) -> bool:
        """
        Cache a summary for an entity.

        Args:
            entity_name: Name of the entity
            group_id: Group ID for isolation
            summary: Summary text to cache

        Returns:
            True if cached successfully
        """
        if not self.config.enabled or self._cache is None:
            return False

        # Don't cache empty or very short summaries
        if not summary or len(summary) < self.config.min_summary_length:
            logger.debug(f'Skipping cache for "{entity_name}" - summary too short')
            return False

        key = self._make_key(entity_name, group_id)

        try:
            # Store with timestamp for TTL checking
            entry = (time.time(), summary)
            self._cache.set(key, entry)
            self.stats.record_store()
            logger.debug(
                f'Cached summary for entity "{entity_name}" in group "{group_id}" '
                f'({len(summary)} chars)'
            )
            return True

        except Exception as e:
            logger.warning(f'Cache write error for "{entity_name}": {e}')
            return False

    def invalidate(self, entity_name: str, group_id: str) -> bool:
        """
        Invalidate a cached summary for an entity.

        Args:
            entity_name: Name of the entity
            group_id: Group ID for isolation

        Returns:
            True if entry was found and deleted
        """
        if not self.config.enabled or self._cache is None:
            return False

        key = self._make_key(entity_name, group_id)

        try:
            deleted = self._cache.delete(key)
            if deleted:
                logger.debug(f'Invalidated cache for entity "{entity_name}" in group "{group_id}"')
            return deleted
        except Exception as e:
            logger.warning(f'Cache invalidation error for "{entity_name}": {e}')
            return False

    def clear(self) -> int:
        """
        Clear all cached entries.

        Returns:
            Number of entries cleared
        """
        if not self.config.enabled or self._cache is None:
            return 0

        try:
            count: int = self._cache.__len__()  # type: ignore[assignment]
            self._cache.clear()
            logger.info(f'Cleared {count} entries from entity summary cache')
            return count
        except Exception as e:
            logger.warning(f'Cache clear error: {e}')
            return 0

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        stats = self.stats.to_dict()
        stats['enabled'] = self.config.enabled

        if self._cache is not None:
            stats['size'] = self._cache.__len__()  # type: ignore[assignment]
            stats['volume_bytes'] = self._cache.volume()

        return stats

    def close(self):
        """Close the cache."""
        if self._cache is not None:
            self._cache.close()
            self._cache = None


# =============================================================================
# Global Helper Functions
# =============================================================================

def get_entity_cache(config: EntityCacheConfig | None = None) -> EntitySummaryCache:
    """Get or create global entity cache instance."""
    return EntitySummaryCache.get_instance(config)


def configure_entity_cache(
    enabled: bool | None = None,
    cache_dir: str | None = None,
    ttl_seconds: int | None = None,
    max_size_mb: int | None = None,
    **kwargs,
) -> EntitySummaryCache:
    """
    Configure and return the global entity cache.

    Args:
        enabled: Whether caching is enabled
        cache_dir: Directory for cache storage
        ttl_seconds: Time-to-live for cache entries
        max_size_mb: Maximum cache size
        **kwargs: Additional config options

    Returns:
        Configured EntitySummaryCache instance.
    """
    config = EntityCacheConfig.from_env()

    if enabled is not None:
        config.enabled = enabled
    if cache_dir is not None:
        config.cache_dir = cache_dir
    if ttl_seconds is not None:
        config.ttl_seconds = ttl_seconds
    if max_size_mb is not None:
        config.max_size_mb = max_size_mb

    for key, value in kwargs.items():
        if hasattr(config, key):
            setattr(config, key, value)

    EntitySummaryCache.reset_instance()
    return EntitySummaryCache.get_instance(config)
