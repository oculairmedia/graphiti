"""
Stateful Learning Wrapper for Graphiti

A minimal implementation that provides stateful extraction context
using the Letta agent memory system, compatible with letta-client 1.7.x.

This replaces the agentic-learning SDK which requires an older letta-client version.
"""

import logging
import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from contextlib import contextmanager
from functools import wraps
from typing import Any, Callable, Generator, TypeVar

from letta_client import Letta

logger = logging.getLogger(__name__)

LETTA_TIMEOUT_SECONDS = float(os.getenv('LETTA_TIMEOUT_SECONDS', '5.0'))

T = TypeVar('T')


def with_timeout(timeout_seconds: float = LETTA_TIMEOUT_SECONDS) -> Callable:
    """Decorator to add timeout to synchronous functions."""

    def decorator(func: Callable[..., T]) -> Callable[..., T | None]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T | None:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(func, *args, **kwargs)
                try:
                    return future.result(timeout=timeout_seconds)
                except FuturesTimeoutError:
                    logger.warning(f'{func.__name__} timed out after {timeout_seconds}s')
                    return None
                except Exception as e:
                    logger.warning(f'{func.__name__} failed: {e}')
                    return None

        return wrapper

    return decorator


class StatefulLearningClient:
    """
    Client for stateful learning using Letta agents.

    Provides memory context injection for LLM calls, enabling
    the extraction pipeline to "remember" previous extractions.
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float | None = None,
    ):
        self.base_url = base_url or os.getenv('LETTA_BASE_URL', 'http://localhost:8283')
        self.api_key = api_key or os.getenv('LETTA_API_KEY')
        self.timeout = timeout or LETTA_TIMEOUT_SECONDS
        self._healthy = False

        self._client = Letta(
            base_url=self.base_url,
            api_key=self.api_key,
        )
        self._check_health()

    def _check_health(self) -> bool:
        """Check if Letta is reachable."""
        try:
            self._client.agents.list()
            self._healthy = True
            logger.info(f'Letta connection healthy: {self.base_url}')
            return True
        except Exception as e:
            self._healthy = False
            logger.warning(f'Letta unreachable at {self.base_url}: {e}')
            return False

    @property
    def is_healthy(self) -> bool:
        return self._healthy

    def get_agent_by_name(self, name: str) -> Any | None:
        """Find an agent by name."""
        try:
            agents = self._client.agents.list()
            for agent in agents:
                if agent.name == name:
                    return agent
            return None
        except Exception as e:
            logger.warning(f'Failed to list agents: {e}')
            return None

    def get_agent_by_id(self, agent_id: str) -> Any | None:
        """Get an agent by ID."""
        try:
            return self._client.agents.retrieve(agent_id)
        except Exception as e:
            logger.warning(f'Failed to retrieve agent {agent_id}: {e}')
            return None

    def get_memory_context(self, agent_id: str, query: str, limit: int = 5) -> list[str]:
        """
        Search agent's memory for relevant context.

        Args:
            agent_id: The agent's ID
            query: Search query for relevant memories
            limit: Maximum number of memories to return

        Returns:
            List of relevant memory strings
        """
        try:
            # Search passages (archival memory) - uses top_k not limit
            results = self._client.agents.passages.search(
                agent_id=agent_id,
                query=query,
                top_k=limit,
            )

            memories = []
            # Results can have 'results' (with 'content') or 'passages' (with 'text')
            if hasattr(results, 'results'):
                for result in results.results:
                    if hasattr(result, 'content'):
                        memories.append(result.content)
                    elif hasattr(result, 'text'):
                        memories.append(result.text)
            elif hasattr(results, 'passages'):
                for passage in results.passages:
                    if hasattr(passage, 'text'):
                        memories.append(passage.text)

            return memories
        except Exception as e:
            logger.warning(f'Failed to search memory for agent {agent_id}: {e}')
            return []

    def store_extraction_memory(
        self,
        agent_id: str,
        episode_content: str,
        extracted_entities: list[dict],
        extracted_edges: list[dict] | None = None,
    ) -> bool:
        """
        Store extraction results in agent's archival memory.

        This allows the agent to "remember" what was extracted from each episode,
        improving consistency in future extractions.

        Args:
            agent_id: The agent's ID
            episode_content: The original episode text
            extracted_entities: List of extracted entity dicts
            extracted_edges: Optional list of extracted edge dicts

        Returns:
            True if stored successfully
        """
        try:
            # Format the extraction summary
            entity_names = [e.get('name', 'unknown') for e in extracted_entities]

            memory_text = f"""Extraction from episode:
Content: {episode_content[:500]}{'...' if len(episode_content) > 500 else ''}
Entities extracted: {', '.join(entity_names)}
Entity count: {len(extracted_entities)}
"""
            if extracted_edges:
                edge_count = len(extracted_edges)
                memory_text += f'Edges extracted: {edge_count}\n'

            # Store as passage in agent's memory
            self._client.agents.passages.create(
                agent_id=agent_id,
                text=memory_text,
            )

            return True
        except Exception as e:
            logger.warning(f'Failed to store extraction memory: {e}')
            return False

    def get_extraction_hints(self, agent_id: str, episode_content: str) -> str:
        """
        Get hints for extraction based on previous extractions.

        Searches the agent's memory for similar episodes and returns
        a summary of what entities were previously extracted.

        Args:
            agent_id: The agent's ID
            episode_content: The episode to extract from

        Returns:
            String with extraction hints to include in prompt
        """
        try:
            # Get recent extraction memories
            memories = self.get_memory_context(agent_id, episode_content[:200], limit=3)

            if not memories:
                return ''

            hints = 'Previous extraction context:\n'
            for i, memory in enumerate(memories, 1):
                hints += f'{i}. {memory[:300]}...\n' if len(memory) > 300 else f'{i}. {memory}\n'

            return hints
        except Exception as e:
            logger.warning(f'Failed to get extraction hints: {e}')
            return ''

    def store_resolution_memory(
        self,
        agent_id: str,
        entity_name: str,
        resolved_to: str,
        is_duplicate: bool,
        context: str = '',
    ) -> bool:
        """
        Store a resolution decision in agent's archival memory.

        This allows the agent to "remember" deduplication decisions,
        improving consistency in future resolutions.

        Args:
            agent_id: The agent's ID
            entity_name: The entity being resolved
            resolved_to: The entity it was resolved to (or itself if not duplicate)
            is_duplicate: Whether it was marked as a duplicate
            context: Optional context about why the decision was made

        Returns:
            True if stored successfully
        """
        try:
            if is_duplicate:
                memory_text = f"""Resolution decision:
Entity "{entity_name}" was identified as DUPLICATE of "{resolved_to}".
{f'Context: {context}' if context else ''}
These entities refer to the same real-world object/concept.
"""
            else:
                memory_text = f"""Resolution decision:
Entity "{entity_name}" was identified as DISTINCT (not a duplicate).
{f'Context: {context}' if context else ''}
This is a unique entity in the knowledge graph.
"""

            # Store as passage in agent's memory
            self._client.agents.passages.create(
                agent_id=agent_id,
                text=memory_text,
            )

            return True
        except Exception as e:
            logger.warning(f'Failed to store resolution memory: {e}')
            return False

    def get_resolution_hints(
        self,
        agent_id: str,
        entity_names: list[str],
    ) -> str:
        """
        Get hints for resolution based on previous deduplication decisions.

        Searches the agent's memory for past decisions involving
        the given entity names.

        Args:
            agent_id: The agent's ID
            entity_names: Names of entities being resolved

        Returns:
            String with resolution hints to include in prompt
        """
        try:
            if not entity_names:
                return ''

            # Search for resolution decisions involving these entities
            query = f'Resolution decision entity {" ".join(entity_names[:5])}'
            memories = self.get_memory_context(agent_id, query, limit=5)

            if not memories:
                return ''

            # Filter to only resolution-related memories
            resolution_memories = [
                m
                for m in memories
                if 'resolution decision' in m.lower() or 'duplicate' in m.lower()
            ]

            if not resolution_memories:
                return ''

            hints = 'Previous resolution decisions:\n'
            for i, memory in enumerate(resolution_memories, 1):
                hints += f'{i}. {memory[:200]}...\n' if len(memory) > 200 else f'{i}. {memory}\n'

            return hints
        except Exception as e:
            logger.warning(f'Failed to get resolution hints: {e}')
            return ''


@contextmanager
def stateful_extraction(
    agent_id: str,
    client: StatefulLearningClient | None = None,
) -> Generator[dict[str, Any], None, None]:
    """
    Context manager for stateful extraction.

    Provides extraction hints from the agent's memory and
    stores extraction results after completion.

    Usage:
        client = StatefulLearningClient()

        with stateful_extraction("agent-xxx", client) as context:
            # context['hints'] contains extraction hints from memory
            entities = await extract_nodes(episode, context['hints'])

            # Store results for future reference
            context['store'](episode.content, entities)

    Args:
        agent_id: The Letta agent ID to use for memory
        client: Optional StatefulLearningClient instance

    Yields:
        Dict with 'hints' (str) and 'store' (callable) keys
    """
    if client is None:
        client = StatefulLearningClient()

    # Storage for extraction results
    stored_extractions: list[tuple[str, list[dict], list[dict] | None]] = []

    def store_fn(
        episode_content: str,
        entities: list[dict],
        edges: list[dict] | None = None,
    ):
        stored_extractions.append((episode_content, entities, edges))

    # Get hints before extraction
    hints = ''
    try:
        # We'd need the episode content here, but we don't have it yet
        # So we provide a store function and defer hint retrieval
        pass
    except Exception as e:
        logger.warning(f'Failed to get extraction hints: {e}')

    context = {
        'hints': hints,
        'store': store_fn,
        'get_hints': lambda content: client.get_extraction_hints(agent_id, content),
    }

    try:
        yield context
    finally:
        # Store all extractions after the context exits
        for episode_content, entities, edges in stored_extractions:
            client.store_extraction_memory(agent_id, episode_content, entities, edges)


# Convenience function to get a pre-configured client
_default_client: StatefulLearningClient | None = None


def get_learning_client() -> StatefulLearningClient:
    """Get or create the default StatefulLearningClient."""
    global _default_client
    if _default_client is None:
        _default_client = StatefulLearningClient()
    return _default_client
