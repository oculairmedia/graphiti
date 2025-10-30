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

import json
import logging

import os
import re
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


def safe_json_dumps(obj: Any) -> str:
    """
    Safely serialize objects to JSON, handling datetime objects.

    Args:
        obj: Object to serialize

    Returns:
        JSON string
    """
    def datetime_handler(x):
        if isinstance(x, datetime):
            return x.isoformat()
        raise TypeError(f"Object of type {type(x).__name__} is not JSON serializable")

    return json.dumps(obj, ensure_ascii=False, default=datetime_handler)


# Configuration via environment variables
MAX_PROMPT_TOKENS = int(os.getenv('MAX_PROMPT_TOKENS', '24000'))  # Safe default below 27K
MAX_EPISODE_CONTENT_CHARS = int(os.getenv('MAX_EPISODE_CONTENT_CHARS', '2000'))
MAX_PREVIOUS_EPISODES = int(os.getenv('MAX_PREVIOUS_EPISODES', '3'))
STRIP_ANSI_CODES = os.getenv('STRIP_ANSI_CODES', 'true').lower() == 'true'


def estimate_tokens(text: str) -> int:
    """
    Estimate token count for a given text.
    Uses tiktoken for accurate counting when available, otherwise falls back to heuristic.

    Args:
        text: Input text

    Returns:
        Estimated token count
    """
    if not text:
        return 0

    # Try using tiktoken for accurate counting
    try:
        import tiktoken
        encoding = tiktoken.get_encoding("cl100k_base")
        return len(encoding.encode(text))
    except ImportError:
        # Fallback: More conservative heuristic (3 chars per token instead of 4)
        # This accounts for underestimation issues we've observed
        logger.debug("tiktoken not available, using conservative heuristic for token estimation")
        return len(text) // 3
    except Exception as e:
        # If tiktoken fails for any reason, use conservative heuristic
        logger.warning(f"tiktoken encoding failed: {e}, using conservative heuristic")
        return len(text) // 3


def strip_ansi_codes(text: str) -> str:
    """
    Remove ANSI color codes and escape sequences from text.

    Args:
        text: Text potentially containing ANSI codes

    Returns:
        Cleaned text without ANSI codes
    """
    if not text or not STRIP_ANSI_CODES:
        return text

    # ANSI escape sequences pattern
    ansi_pattern = re.compile(r'\x1b\[[0-9;]*[mGKHf]')
    return ansi_pattern.sub('', text)


def truncate_episode_content(content: str, max_chars: int = MAX_EPISODE_CONTENT_CHARS) -> str:
    """
    Truncate episode content to a maximum character limit.

    Args:
        content: Episode content
        max_chars: Maximum characters to keep

    Returns:
        Truncated content with ellipsis if truncated
    """
    if not content:
        return content

    # Strip ANSI codes first
    content = strip_ansi_codes(content)

    if len(content) <= max_chars:
        return content

    # Truncate and add ellipsis
    return content[:max_chars] + '... [truncated]'


async def rerank_and_budget_episodes(
    query: str,
    episodes: list[Any],
    reranker: Any,
    max_tokens: int = 4000,
    enable_rerank: bool = True,
    min_episodes: int = 1,
) -> list[dict[str, Any]]:
    """
    Rerank episodes by relevance to query and select top-K within token budget.

    This implements PRD #01 (Reranker Context Gating) to intelligently select
    the most relevant previous episodes instead of using simple FIFO.

    Args:
        query: Current episode content (search query)
        episodes: Previous episodes to filter and rank
        reranker: Reranker client instance (OllamaRerankerClient, OpenAIRerankerClient, etc.)
        max_tokens: Target token budget for selected episodes
        enable_rerank: Feature flag (fallback to FIFO if False)
        min_episodes: Minimum number of episodes to keep even if over budget

    Returns:
        List of selected and sanitized episode dicts with content, score, timestamp
    """
    if not enable_rerank or not episodes:
        logger.info('Reranker disabled or no episodes, using FIFO clipping')
        return clip_previous_episodes(episodes, max_episodes=3)

    logger.info(f'Reranking {len(episodes)} episodes (budget: {max_tokens} tokens)')

    # Extract episode content and build metadata
    passages = []
    episode_metadata = []

    for ep in episodes:
        if hasattr(ep, 'content'):
            content = strip_ansi_codes(ep.content)
        elif isinstance(ep, dict):
            content = strip_ansi_codes(ep.get('content', str(ep)))
        else:
            content = strip_ansi_codes(str(ep))

        passages.append(content)
        episode_metadata.append(
            {
                'uuid': getattr(ep, 'uuid', None) if hasattr(ep, 'uuid') else ep.get('uuid'),
                'timestamp': getattr(ep, 'valid_at', None)
                if hasattr(ep, 'valid_at')
                else ep.get('valid_at'),
                'content': content,
            }
        )

    # Rerank using the provided reranker
    try:
        ranked_passages = await reranker.rank(query, passages)
        top_score = ranked_passages[0][1] if ranked_passages else 0.0
        logger.info(
            f'Reranker returned {len(ranked_passages)} results, '
            f'top score: {top_score:.3f}'
        )
    except Exception as e:
        logger.warning(f'Reranker failed: {e}. Falling back to FIFO.')
        return clip_previous_episodes(episodes, max_episodes=3)

    # Budget allocation: accumulate top-scored episodes until token limit
    selected_episodes = []
    current_tokens = 0
    skipped_count = 0

    for passage, score in ranked_passages:
        # Find corresponding episode metadata
        try:
            idx = passages.index(passage)
        except ValueError:
            logger.warning(f'Could not find passage in original list, skipping')
            continue

        metadata = episode_metadata[idx]

        # Estimate tokens for this episode
        episode_tokens = estimate_tokens(passage)

        # Check budget (but always keep min_episodes)
        if len(selected_episodes) >= min_episodes and current_tokens + episode_tokens > max_tokens:
            skipped_count += 1
            logger.debug(
                f'Skipping episode (score {score:.3f}, {episode_tokens} tokens) - '
                f'would exceed budget ({current_tokens + episode_tokens} > {max_tokens})'
            )
            continue

        # Add episode to selection
        selected_episodes.append(
            {
                'content': truncate_episode_content(passage),
                'score': score,
                'timestamp': metadata['timestamp'],
                'uuid': metadata['uuid'],
            }
        )
        current_tokens += episode_tokens

    logger.info(
        f'Reranker selected {len(selected_episodes)}/{len(episodes)} episodes '
        f'({current_tokens}/{max_tokens} tokens, skipped {skipped_count})'
    )

    # If we got zero episodes due to budget, force include at least min_episodes
    if not selected_episodes and ranked_passages:
        logger.warning(f'No episodes fit budget, forcing {min_episodes} highest-scored')
        for i in range(min(min_episodes, len(ranked_passages))):
            passage, score = ranked_passages[i]
            idx = passages.index(passage)
            metadata = episode_metadata[idx]
            selected_episodes.append(
                {
                    'content': truncate_episode_content(passage, max_chars=500),
                    'score': score,
                    'timestamp': metadata['timestamp'],
                    'uuid': metadata['uuid'],
                }
            )

    return selected_episodes


def clip_previous_episodes(
    episodes: list[Any],
    max_episodes: int = MAX_PREVIOUS_EPISODES,
    max_content_chars: int = MAX_EPISODE_CONTENT_CHARS,
) -> list[dict[str, Any]]:
    """
    Clip and sanitize previous episodes for prompt inclusion.

    Args:
        episodes: List of episode objects or dicts
        max_episodes: Maximum number of episodes to include
        max_content_chars: Maximum characters per episode content

    Returns:
        List of sanitized episode dicts
    """
    if not episodes:
        return []

    # Take only the most recent N episodes
    recent_episodes = episodes[-max_episodes:] if len(episodes) > max_episodes else episodes

    clipped = []
    for ep in recent_episodes:
        if isinstance(ep, str):
            ep_dict = {'content': ep}
        elif hasattr(ep, 'model_dump'):
            ep_dict = ep.model_dump()
        elif hasattr(ep, '__dict__'):
            ep_dict = ep.__dict__.copy()
        else:
            ep_dict = dict(ep)

        if 'content' in ep_dict:
            ep_dict['content'] = truncate_episode_content(ep_dict['content'], max_content_chars)

        fields_to_remove = ['entity_edges', 'labels', 'uuid']
        for field in fields_to_remove:
            ep_dict.pop(field, None)

        clipped.append(ep_dict)

    return clipped


def enforce_max_prompt_tokens(
    context: dict[str, Any], max_tokens: int = MAX_PROMPT_TOKENS
) -> dict[str, Any]:
    """
    Enforce maximum token limit on prompt context by progressively reducing content.

    Strategy:
    1. Estimate total tokens
    2. If over limit, clip previous_episodes to fewer entries
    3. If still over, truncate episode_content
    4. If still over, truncate existing_nodes_text

    Args:
        context: Prompt context dictionary
        max_tokens: Maximum allowed tokens

    Returns:
        Clipped context dictionary
    """
    context = dict(context)
    debug = {'initial_tokens': 0, 'adjustments': [], 'final_tokens': 0}
    context['__prompt_debug__'] = debug

    def estimate_context_tokens() -> int:
        total = 0
        for key, value in context.items():
            if key == '__prompt_debug__':
                continue
            if isinstance(value, str):
                total += estimate_tokens(value)
            elif isinstance(value, list):
                total += estimate_tokens(safe_json_dumps(value))
            elif isinstance(value, dict):
                total += estimate_tokens(safe_json_dumps(value))
        return total

    def record_adjustment(kind: str, detail: Any, tokens: int) -> None:
        debug['adjustments'].append({'type': kind, 'detail': detail, 'tokens': tokens})

    current_tokens = estimate_context_tokens()
    debug['initial_tokens'] = current_tokens

    if current_tokens <= max_tokens:
        debug['final_tokens'] = current_tokens
        debug['status'] = 'unchanged'
        return context

    logger.warning(
        f'Prompt exceeds max tokens: {current_tokens} > {max_tokens}. '
        f'Applying progressive clipping...'
    )

    if 'previous_episodes' in context and isinstance(context['previous_episodes'], list):
        episodes = context['previous_episodes']
        for n in [2, 1, 0]:
            context['previous_episodes'] = clip_previous_episodes(
                episodes, max_episodes=n, max_content_chars=MAX_EPISODE_CONTENT_CHARS
            )
            current_tokens = estimate_context_tokens()
            record_adjustment('previous_episodes', n, current_tokens)
            logger.info(f'After reducing to {n} episodes: {current_tokens} tokens')

            if current_tokens <= max_tokens:
                debug['final_tokens'] = current_tokens
                debug['status'] = 'clipped_episodes'
                return context

    if 'episode_content' in context and isinstance(context['episode_content'], str):
        original_len = len(context['episode_content'])
        for limit in [1500, 1000, 500]:
            context['episode_content'] = truncate_episode_content(
                context['episode_content'], max_chars=limit
            )
            current_tokens = estimate_context_tokens()
            record_adjustment('episode_content', limit, current_tokens)
            logger.info(f'After truncating episode to {limit} chars: {current_tokens} tokens')

            if current_tokens <= max_tokens:
                logger.warning(f'Truncated episode_content from {original_len} to {limit} chars')
                debug['final_tokens'] = current_tokens
                debug['status'] = 'truncated_episode'
                return context

    if 'existing_nodes_text' in context and isinstance(context['existing_nodes_text'], str):
        original_len = len(context['existing_nodes_text'])
        for limit in [2000, 1000, 500]:
            context['existing_nodes_text'] = (
                context['existing_nodes_text'][:limit] + '... [truncated]'
            )
            current_tokens = estimate_context_tokens()
            record_adjustment('existing_nodes_text', limit, current_tokens)
            logger.info(f'After truncating nodes to {limit} chars: {current_tokens} tokens')

            if current_tokens <= max_tokens:
                logger.warning(
                    f'Truncated existing_nodes_text from {original_len} to {limit} chars'
                )
                debug['final_tokens'] = current_tokens
                debug['status'] = 'truncated_nodes'
                return context

    if 'previous_episodes' in context:
        logger.error('Removing previous_episodes entirely to meet token limit!')
        context['previous_episodes'] = []
        current_tokens = estimate_context_tokens()
        record_adjustment('previous_episodes_removed', 0, current_tokens)

    final_tokens = estimate_context_tokens()
    debug['final_tokens'] = final_tokens
    debug['status'] = 'over_limit' if final_tokens > max_tokens else 'reduced'
    if final_tokens > max_tokens:
        logger.error(
            f'Could not reduce prompt below {max_tokens} tokens. '
            f'Final size: {final_tokens} tokens. Prompt may fail.'
        )

    return context
