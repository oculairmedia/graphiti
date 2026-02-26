"""
Copyright 2024, Zep Software, Inc.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import asyncio
import logging
import os
import time
from functools import wraps
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Optional, TypeVar

from pydantic import BaseModel

from graphiti_core.llm_client.errors import RateLimitError, RefusalError, EmptyResponseError

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from graphiti_core.edges import EntityEdge
    from graphiti_core.nodes import EntityNode

T = TypeVar('T')


class ResilientIngestionState(BaseModel):
    """Tracks partial progress during resilient ingestion to avoid losing work on failures."""

    episode_id: str
    group_id: str

    # Stage completion flags
    nodes_extracted: bool = False
    nodes_resolved: bool = False
    edges_extracted: bool = False
    episode_created: bool = False

    # Cached results from completed stages
    extracted_nodes: Optional[list['EntityNode']] = None
    resolved_nodes: Optional[list['EntityNode']] = None
    extracted_edges: Optional[list['EntityEdge']] = None

    # Additional cached data from node resolution
    uuid_map: Optional[dict[str, str]] = None
    node_duplicates: Optional[list[tuple['EntityNode', 'EntityNode']]] = None

    # Retry tracking
    nodes_extract_attempts: int = 0
    nodes_resolve_attempts: int = 0
    edges_extract_attempts: int = 0

    # Timestamps for monitoring
    started_at: float = 0
    nodes_extracted_at: Optional[float] = None
    nodes_resolved_at: Optional[float] = None
    edges_extracted_at: Optional[float] = None
    completed_at: Optional[float] = None

    def __init__(self, **data):
        super().__init__(**data)
        if not self.started_at:
            self.started_at = time.time()

    def mark_nodes_extracted(self, nodes: list['EntityNode']):
        """Mark node extraction as complete and cache results."""
        self.nodes_extracted = True
        self.extracted_nodes = nodes
        self.nodes_extracted_at = time.time()
        logger.info(f'Episode {self.episode_id}: Nodes extracted ({len(nodes)} nodes)')

    def mark_nodes_resolved(self, nodes: list['EntityNode']):
        """Mark node resolution as complete and cache results."""
        self.nodes_resolved = True
        self.resolved_nodes = nodes
        self.nodes_resolved_at = time.time()
        logger.info(f'Episode {self.episode_id}: Nodes resolved ({len(nodes)} nodes)')

    def mark_edges_extracted(self, edges: list['EntityEdge']):
        """Mark edge extraction as complete and cache results."""
        self.edges_extracted = True
        self.extracted_edges = edges
        self.edges_extracted_at = time.time()
        logger.info(f'Episode {self.episode_id}: Edges extracted ({len(edges)} edges)')

    def mark_completed(self):
        """Mark entire ingestion as complete."""
        self.episode_created = True
        self.completed_at = time.time()
        duration = self.completed_at - self.started_at
        logger.info(f'Episode {self.episode_id}: Ingestion completed in {duration:.2f}s')

    def get_progress_summary(self) -> str:
        """Get human-readable progress summary."""
        stages = []
        if self.nodes_extracted:
            stages.append('nodes_extracted')
        if self.nodes_resolved:
            stages.append('nodes_resolved')
        if self.edges_extracted:
            stages.append('edges_extracted')
        if self.episode_created:
            stages.append('completed')

        return f'Episode {self.episode_id}: [{"/".join(stages) if stages else "starting"}]'


def retry_with_backoff(
    max_retries: int | None = None,
    base_delay: float | None = None,
    max_delay: float | None = None,
    exponential_base: float | None = None,
    jitter: bool = True,
    retryable_exceptions: tuple = (
        RateLimitError,
        ConnectionError,
        TimeoutError,
        asyncio.TimeoutError,
    ),
):
    """
    Decorator that implements exponential backoff retry logic for LLM operations.

    Args:
        max_retries: Maximum number of retry attempts (uses env RESILIENT_RETRY_MAX_ATTEMPTS if None)
        base_delay: Initial delay between retries in seconds (uses env RESILIENT_RETRY_BASE_DELAY if None)
        max_delay: Maximum delay between retries in seconds (uses env RESILIENT_RETRY_MAX_DELAY if None)
        exponential_base: Base for exponential backoff calculation (uses env RESILIENT_RETRY_EXPONENTIAL_BASE if None)
        jitter: Whether to add random jitter to delays
        retryable_exceptions: Tuple of exceptions that should trigger retries
    """

    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            # Load configuration from environment variables
            effective_max_retries = (
                max_retries
                if max_retries is not None
                else int(os.getenv('RESILIENT_RETRY_MAX_ATTEMPTS', '3'))
            )
            effective_base_delay = (
                base_delay
                if base_delay is not None
                else float(os.getenv('RESILIENT_RETRY_BASE_DELAY', '2.0'))
            )
            effective_max_delay = (
                max_delay
                if max_delay is not None
                else float(os.getenv('RESILIENT_RETRY_MAX_DELAY', '60.0'))
            )
            effective_exponential_base = (
                exponential_base
                if exponential_base is not None
                else float(os.getenv('RESILIENT_RETRY_EXPONENTIAL_BASE', '2.0'))
            )

            last_exception = None

            for attempt in range(effective_max_retries + 1):
                try:
                    result = await func(*args, **kwargs)
                    if attempt > 0:
                        logger.info(f'{func.__name__} succeeded on attempt {attempt + 1}')
                    return result

                except retryable_exceptions as e:
                    last_exception = e

                    if attempt == effective_max_retries:
                        logger.error(
                            f'{func.__name__} failed after {effective_max_retries + 1} attempts: {e}'
                        )
                        raise e

                    # Calculate delay with exponential backoff
                    delay = min(
                        effective_base_delay * (effective_exponential_base**attempt),
                        effective_max_delay,
                    )

                    # Add jitter to prevent thundering herd
                    if jitter:
                        import random

                        delay += random.uniform(0, delay * 0.1)

                    logger.warning(
                        f'{func.__name__} failed on attempt {attempt + 1}/{effective_max_retries + 1}: {e}. '
                        f'Retrying in {delay:.2f}s...'
                    )

                    await asyncio.sleep(delay)

                except (RefusalError, EmptyResponseError) as e:
                    # Don't retry on refusal or empty response - these are likely permanent failures
                    logger.error(f'{func.__name__} failed with non-retryable error: {e}')
                    raise e

                except Exception as e:
                    # Log unexpected errors but don't retry
                    logger.error(f'{func.__name__} failed with unexpected error: {e}')
                    raise e

            # Should never reach here, but just in case
            if last_exception:
                raise last_exception
            else:
                raise RuntimeError(f'{func.__name__} failed for unknown reason')

        return wrapper

    return decorator


class IngestionProgressCache:
    """In-memory cache for tracking ingestion progress across retries."""

    def __init__(self):
        self._cache: dict[str, ResilientIngestionState] = {}

    def get_or_create_state(self, episode_id: str, group_id: str) -> ResilientIngestionState:
        """Get existing state or create new one for episode."""
        if episode_id not in self._cache:
            self._cache[episode_id] = ResilientIngestionState(
                episode_id=episode_id, group_id=group_id
            )
        return self._cache[episode_id]

    def get_state(self, episode_id: str) -> Optional[ResilientIngestionState]:
        """Get existing state for episode, or None if not found."""
        return self._cache.get(episode_id)

    def remove_state(self, episode_id: str):
        """Remove completed state from cache to free memory."""
        self._cache.pop(episode_id, None)

    def clear_old_states(self, max_age_seconds: float | None = None):
        """Remove states older than max_age_seconds to prevent memory leaks."""
        effective_max_age = (
            max_age_seconds
            if max_age_seconds is not None
            else float(os.getenv('RESILIENT_CACHE_MAX_AGE_SECONDS', '3600'))
        )

        current_time = time.time()
        expired_keys = [
            key
            for key, state in self._cache.items()
            if current_time - state.started_at > effective_max_age
        ]

        for key in expired_keys:
            self._cache.pop(key, None)

        if expired_keys:
            logger.info(f'Cleared {len(expired_keys)} expired ingestion states from cache')

    def get_cache_stats(self) -> dict[str, Any]:
        """Get cache statistics for monitoring."""
        total_states = len(self._cache)
        completed_states = sum(1 for state in self._cache.values() if state.episode_created)
        in_progress_states = total_states - completed_states

        return {
            'total_states': total_states,
            'completed_states': completed_states,
            'in_progress_states': in_progress_states,
            'cache_size_mb': sum(len(str(state)) for state in self._cache.values()) / (1024 * 1024),
        }


# Global cache instance
ingestion_cache = IngestionProgressCache()
