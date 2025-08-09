"""
High-performance multi-tier caching system for search operations.

This module provides a caching layer that significantly reduces latency
by avoiding repeated database queries and embedding generation.
"""

import hashlib
import json
import logging
import pickle
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple, TypeVar, Generic
import asyncio

try:
    import redis.asyncio as aioredis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    aioredis = None  # type: ignore

try:
    import msgpack
    MSGPACK_AVAILABLE = True
except ImportError:
    MSGPACK_AVAILABLE = False
    msgpack = None  # type: ignore

from pydantic import BaseModel

logger = logging.getLogger(__name__)

T = TypeVar('T')


class CacheMetrics:
    """Track cache performance metrics."""
    
    def __init__(self):
        self.hits = 0
        self.misses = 0
        self.l1_hits = 0
        self.l2_hits = 0
        self.evictions = 0
        self.errors = 0
        self.total_latency_ms = 0.0
        self.cached_latency_ms = 0.0
    
    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return (self.hits / total * 100) if total > 0 else 0.0
    
    @property
    def avg_latency_ms(self) -> float:
        total = self.hits + self.misses
        return (self.total_latency_ms / total) if total > 0 else 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": f"{self.hit_rate:.2f}%",
            "l1_hits": self.l1_hits,
            "l2_hits": self.l2_hits,
            "evictions": self.evictions,
            "errors": self.errors,
            "avg_latency_ms": f"{self.avg_latency_ms:.2f}",
            "cached_latency_ms": f"{self.cached_latency_ms:.2f}",
        }


class LRUCache(Generic[T]):
    """
    Thread-safe LRU cache implementation for L1 caching.
    """
    
    def __init__(self, max_size: int = 1000):
        self.cache: OrderedDict[str, Tuple[T, datetime]] = OrderedDict()
        self.max_size = max_size
        self.lock = asyncio.Lock()
        self.default_ttl = timedelta(minutes=5)
    
    async def get(self, key: str) -> Optional[T]:
        """Get value from cache if not expired."""
        async with self.lock:
            if key not in self.cache:
                return None
            
            value, expiry = self.cache[key]
            
            # Check expiry
            if datetime.now(timezone.utc) > expiry:
                del self.cache[key]
                return None
            
            # Move to end (most recently used)
            self.cache.move_to_end(key)
            return value
    
    async def set(self, key: str, value: T, ttl: Optional[timedelta] = None) -> None:
        """Set value in cache with TTL."""
        if ttl is None:
            ttl = self.default_ttl
        
        async with self.lock:
            # Remove oldest if at capacity
            if len(self.cache) >= self.max_size and key not in self.cache:
                self.cache.popitem(last=False)
            
            expiry = datetime.now(timezone.utc) + ttl
            self.cache[key] = (value, expiry)
            self.cache.move_to_end(key)
    
    async def clear(self) -> None:
        """Clear all cache entries."""
        async with self.lock:
            self.cache.clear()
    
    def size(self) -> int:
        """Get current cache size."""
        return len(self.cache)


class SearchCache:
    """
    Multi-tier caching system for search operations.
    
    Features:
    - L1: In-memory LRU cache (fastest, ~1ms)
    - L2: Redis/FalkorDB cache (fast, ~10ms)
    - Automatic serialization/deserialization
    - TTL-based expiration
    - Cache key versioning
    - Metrics tracking
    """
    
    def __init__(
        self,
        redis_url: Optional[str] = None,
        l1_max_size: int = 1000,
        default_ttl_seconds: int = 300,
        cache_prefix: str = "graphiti:cache:",
        cache_version: int = 1,
    ):
        """
        Initialize the search cache.
        
        Args:
            redis_url: Redis connection URL
            l1_max_size: Maximum size of L1 cache
            default_ttl_seconds: Default TTL in seconds
            cache_prefix: Prefix for cache keys
            cache_version: Cache version for invalidation
        """
        self.l1_cache: LRUCache[Any] = LRUCache(max_size=l1_max_size)
        self.redis_client: Optional[aioredis.Redis] = None
        self.redis_url = redis_url or "redis://localhost:6379/1"  # Use DB 1 for cache
        self.default_ttl = default_ttl_seconds
        self.cache_prefix = cache_prefix
        self.cache_version = cache_version
        self.metrics = CacheMetrics()
        self._initialized = False
    
    async def initialize(self) -> None:
        """Initialize Redis connection."""
        if self._initialized:
            return
        
        if REDIS_AVAILABLE and self.redis_url:
            try:
                self.redis_client = await aioredis.from_url(
                    self.redis_url,
                    encoding="utf-8",
                    decode_responses=False,
                    max_connections=20,
                )
                # Test connection
                await self.redis_client.ping()
                self._initialized = True
                logger.info(f"Redis cache initialized at {self.redis_url}")
            except Exception as e:
                logger.warning(f"Failed to connect to Redis cache: {e}")
                self.redis_client = None
        else:
            logger.info("Redis not available, using L1 cache only")
    
    async def close(self) -> None:
        """Close Redis connection."""
        if self.redis_client:
            await self.redis_client.close()
            self._initialized = False
    
    def _generate_cache_key(self, 
                           query: str, 
                           group_ids: Optional[List[str]] = None,
                           additional_params: Optional[Dict[str, Any]] = None) -> str:
        """Generate a deterministic cache key."""
        key_parts = [
            f"v{self.cache_version}",
            query,
            json.dumps(sorted(group_ids) if group_ids else [], sort_keys=True),
            json.dumps(additional_params or {}, sort_keys=True),
        ]
        
        key_string = "|".join(key_parts)
        key_hash = hashlib.sha256(key_string.encode()).hexdigest()[:16]
        
        return f"{self.cache_prefix}{key_hash}"
    
    def _serialize(self, data: Any) -> bytes:
        """Serialize data for storage."""
        if MSGPACK_AVAILABLE:
            try:
                return msgpack.packb(data, use_bin_type=True)
            except:
                pass
        
        # Fallback to pickle
        return pickle.dumps(data, protocol=pickle.HIGHEST_PROTOCOL)
    
    def _deserialize(self, data: bytes) -> Any:
        """Deserialize data from storage."""
        if MSGPACK_AVAILABLE:
            try:
                return msgpack.unpackb(data, raw=False)
            except:
                pass
        
        # Fallback to pickle
        return pickle.loads(data)
    
    async def get_search_results(
        self,
        query: str,
        group_ids: Optional[List[str]] = None,
        additional_params: Optional[Dict[str, Any]] = None,
    ) -> Optional[Any]:
        """
        Get cached search results.
        
        Returns None if not found in cache.
        """
        import time
        start_time = time.time()
        
        cache_key = self._generate_cache_key(query, group_ids, additional_params)
        
        # L1 cache check
        result = await self.l1_cache.get(cache_key)
        if result is not None:
            self.metrics.hits += 1
            self.metrics.l1_hits += 1
            elapsed_ms = (time.time() - start_time) * 1000
            self.metrics.cached_latency_ms += elapsed_ms
            logger.debug(f"L1 cache hit for key {cache_key[:8]}... ({elapsed_ms:.2f}ms)")
            return result
        
        # L2 cache check (Redis)
        if self.redis_client:
            try:
                cached_data = await self.redis_client.get(cache_key)
                if cached_data:
                    result = self._deserialize(cached_data)
                    
                    # Populate L1 cache
                    await self.l1_cache.set(cache_key, result)
                    
                    self.metrics.hits += 1
                    self.metrics.l2_hits += 1
                    elapsed_ms = (time.time() - start_time) * 1000
                    self.metrics.cached_latency_ms += elapsed_ms
                    logger.debug(f"L2 cache hit for key {cache_key[:8]}... ({elapsed_ms:.2f}ms)")
                    return result
            except Exception as e:
                self.metrics.errors += 1
                logger.error(f"Redis cache get error: {e}")
        
        # Cache miss
        self.metrics.misses += 1
        elapsed_ms = (time.time() - start_time) * 1000
        self.metrics.total_latency_ms += elapsed_ms
        return None
    
    async def set_search_results(
        self,
        query: str,
        results: Any,
        group_ids: Optional[List[str]] = None,
        additional_params: Optional[Dict[str, Any]] = None,
        ttl_seconds: Optional[int] = None,
    ) -> None:
        """
        Cache search results.
        """
        if ttl_seconds is None:
            ttl_seconds = self.default_ttl
        
        cache_key = self._generate_cache_key(query, group_ids, additional_params)
        
        # Set in L1 cache
        await self.l1_cache.set(
            cache_key, 
            results, 
            ttl=timedelta(seconds=ttl_seconds)
        )
        
        # Set in L2 cache (Redis)
        if self.redis_client:
            try:
                serialized = self._serialize(results)
                await self.redis_client.setex(
                    cache_key,
                    ttl_seconds,
                    serialized
                )
                logger.debug(f"Cached results for key {cache_key[:8]}... (TTL: {ttl_seconds}s)")
            except Exception as e:
                self.metrics.errors += 1
                logger.error(f"Redis cache set error: {e}")
    
    async def invalidate_pattern(self, pattern: str) -> int:
        """
        Invalidate cache entries matching a pattern.
        
        Returns number of entries invalidated.
        """
        count = 0
        
        # Clear L1 cache (simple approach - clear all)
        await self.l1_cache.clear()
        
        # Clear L2 cache by pattern
        if self.redis_client:
            try:
                cursor = 0
                pattern_with_prefix = f"{self.cache_prefix}{pattern}"
                
                while True:
                    cursor, keys = await self.redis_client.scan(
                        cursor, 
                        match=pattern_with_prefix,
                        count=100
                    )
                    
                    if keys:
                        await self.redis_client.delete(*keys)
                        count += len(keys)
                    
                    if cursor == 0:
                        break
                
                logger.info(f"Invalidated {count} cache entries matching {pattern}")
            except Exception as e:
                logger.error(f"Cache invalidation error: {e}")
        
        return count
    
    async def invalidate_group(self, group_id: str) -> None:
        """Invalidate all cache entries for a specific group."""
        # Since group_ids are in the cache key, we need to scan
        # This is why we might want to maintain a separate index
        await self.invalidate_pattern(f"*{group_id}*")
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get cache metrics."""
        return {
            **self.metrics.to_dict(),
            "l1_size": self.l1_cache.size(),
            "l1_max_size": self.l1_cache.max_size,
            "redis_connected": self.redis_client is not None,
        }


class EmbeddingCache:
    """
    Specialized cache for embedding vectors.
    
    Embeddings are expensive to compute but deterministic,
    making them ideal for aggressive caching.
    """
    
    def __init__(self, max_size: int = 10000):
        self.cache: LRUCache[List[float]] = LRUCache(max_size=max_size)
        self.metrics = CacheMetrics()
    
    async def get_or_compute(
        self,
        text: str,
        embedder_func: Any,  # Callable that returns embedding
    ) -> List[float]:
        """
        Get embedding from cache or compute it.
        
        Args:
            text: Text to embed
            embedder_func: Async function to compute embedding
            
        Returns:
            Embedding vector
        """
        import time
        start_time = time.time()
        
        # Normalize text for caching
        cache_key = hashlib.sha256(text.encode()).hexdigest()
        
        # Check cache
        embedding = await self.cache.get(cache_key)
        if embedding is not None:
            self.metrics.hits += 1
            elapsed_ms = (time.time() - start_time) * 1000
            self.metrics.cached_latency_ms += elapsed_ms
            return embedding
        
        # Compute embedding
        self.metrics.misses += 1
        embedding = await embedder_func(text)
        
        # Cache for 1 hour (embeddings don't change)
        await self.cache.set(cache_key, embedding, ttl=timedelta(hours=1))
        
        elapsed_ms = (time.time() - start_time) * 1000
        self.metrics.total_latency_ms += elapsed_ms
        
        return embedding
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get cache metrics."""
        return {
            **self.metrics.to_dict(),
            "cache_size": self.cache.size(),
            "max_size": self.cache.max_size,
        }


# Global cache instances
search_cache = SearchCache()
embedding_cache = EmbeddingCache()


async def initialize_caches(redis_url: Optional[str] = None) -> None:
    """Initialize all cache systems."""
    if redis_url:
        search_cache.redis_url = redis_url
    await search_cache.initialize()
    logger.info("Cache systems initialized")


async def close_caches() -> None:
    """Close all cache connections."""
    await search_cache.close()
    logger.info("Cache systems closed")