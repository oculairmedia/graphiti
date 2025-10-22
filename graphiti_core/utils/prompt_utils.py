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

import logging
import os
import re
from typing import Any

logger = logging.getLogger(__name__)

# Configuration via environment variables
MAX_PROMPT_TOKENS = int(os.getenv("MAX_PROMPT_TOKENS", "24000"))  # Safe default below 27K
MAX_EPISODE_CONTENT_CHARS = int(os.getenv("MAX_EPISODE_CONTENT_CHARS", "2000"))
MAX_PREVIOUS_EPISODES = int(os.getenv("MAX_PREVIOUS_EPISODES", "3"))
STRIP_ANSI_CODES = os.getenv("STRIP_ANSI_CODES", "true").lower() == "true"


def estimate_tokens(text: str) -> int:
    """
    Estimate token count for a given text.
    Uses a simple heuristic: ~4 characters per token on average.

    Args:
        text: Input text

    Returns:
        Estimated token count
    """
    if not text:
        return 0
    return len(text) // 4


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
    return content[:max_chars] + "... [truncated]"


def clip_previous_episodes(
    episodes: list[Any],
    max_episodes: int = MAX_PREVIOUS_EPISODES,
    max_content_chars: int = MAX_EPISODE_CONTENT_CHARS
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
        # Convert to dict if it's an object
        if hasattr(ep, 'model_dump'):
            ep_dict = ep.model_dump()
        elif hasattr(ep, '__dict__'):
            ep_dict = ep.__dict__.copy()
        else:
            ep_dict = dict(ep)

        # Truncate content field
        if 'content' in ep_dict:
            ep_dict['content'] = truncate_episode_content(ep_dict['content'], max_content_chars)

        # Remove unnecessary fields to save tokens
        fields_to_remove = ['entity_edges', 'labels', 'uuid']
        for field in fields_to_remove:
            ep_dict.pop(field, None)

        clipped.append(ep_dict)

    return clipped


def enforce_max_prompt_tokens(
    context: dict[str, Any],
    max_tokens: int = MAX_PROMPT_TOKENS
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
    # Clone the context to avoid mutating the original
    context = dict(context)

    # Helper to estimate total tokens in context
    def estimate_context_tokens():
        total = 0
        for key, value in context.items():
            if isinstance(value, str):
                total += estimate_tokens(value)
            elif isinstance(value, list):
                import json
                total += estimate_tokens(json.dumps(value))
            elif isinstance(value, dict):
                import json
                total += estimate_tokens(json.dumps(value))
        return total

    current_tokens = estimate_context_tokens()

    if current_tokens <= max_tokens:
        # Already within limits
        return context

    logger.warning(
        f"Prompt exceeds max tokens: {current_tokens} > {max_tokens}. "
        f"Applying progressive clipping..."
    )

    # Step 1: Reduce previous_episodes
    if 'previous_episodes' in context and isinstance(context['previous_episodes'], list):
        episodes = context['previous_episodes']

        # Try progressively fewer episodes
        for n in [2, 1, 0]:
            context['previous_episodes'] = clip_previous_episodes(
                episodes,
                max_episodes=n,
                max_content_chars=MAX_EPISODE_CONTENT_CHARS
            )
            current_tokens = estimate_context_tokens()
            logger.info(f"After reducing to {n} episodes: {current_tokens} tokens")

            if current_tokens <= max_tokens:
                return context

    # Step 2: Truncate episode_content
    if 'episode_content' in context and isinstance(context['episode_content'], str):
        original_len = len(context['episode_content'])

        # Try progressively smaller limits
        for limit in [1500, 1000, 500]:
            context['episode_content'] = truncate_episode_content(
                context['episode_content'],
                max_chars=limit
            )
            current_tokens = estimate_context_tokens()
            logger.info(f"After truncating episode to {limit} chars: {current_tokens} tokens")

            if current_tokens <= max_tokens:
                logger.warning(
                    f"Truncated episode_content from {original_len} to {limit} chars"
                )
                return context

    # Step 3: Truncate existing_nodes_text
    if 'existing_nodes_text' in context and isinstance(context['existing_nodes_text'], str):
        original_len = len(context['existing_nodes_text'])

        for limit in [2000, 1000, 500]:
            context['existing_nodes_text'] = context['existing_nodes_text'][:limit] + "... [truncated]"
            current_tokens = estimate_context_tokens()
            logger.info(f"After truncating nodes to {limit} chars: {current_tokens} tokens")

            if current_tokens <= max_tokens:
                logger.warning(
                    f"Truncated existing_nodes_text from {original_len} to {limit} chars"
                )
                return context

    # Step 4: Last resort - remove previous_episodes entirely
    if 'previous_episodes' in context:
        logger.error("Removing previous_episodes entirely to meet token limit!")
        context['previous_episodes'] = []
        current_tokens = estimate_context_tokens()

    final_tokens = estimate_context_tokens()
    if final_tokens > max_tokens:
        logger.error(
            f"Could not reduce prompt below {max_tokens} tokens. "
            f"Final size: {final_tokens} tokens. Prompt may fail."
        )

    return context
