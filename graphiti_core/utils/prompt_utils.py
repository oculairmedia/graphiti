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

import os

# Episode content truncation for prompt optimization
MAX_EPISODE_CONTENT_CHARS = int(os.getenv('MAX_EPISODE_CONTENT_CHARS', '6000'))


def truncate_episode_content(content: str, max_chars: int = MAX_EPISODE_CONTENT_CHARS) -> str:
    """
    Truncate episode content to max_chars, preserving start and end for context.
    
    This function is used to reduce prompt sizes for LLM requests while maintaining
    important context from both the beginning and end of episodes.
    
    Args:
        content: The episode content to truncate
        max_chars: Maximum characters to keep (default from MAX_EPISODE_CONTENT_CHARS env var)
    
    Returns:
        Truncated content with start and end preserved, or original content if under limit
    
    Example:
        >>> content = "A" * 10000
        >>> truncated = truncate_episode_content(content, max_chars=1000)
        >>> len(truncated) <= 1000 + 50  # Allow for truncation marker
        True
    """
    if len(content) <= max_chars:
        return content
    
    # Keep first 70% and last 30% to preserve context
    # This ensures we get the beginning (context setup) and end (recent activity)
    keep_start = int(max_chars * 0.7)
    keep_end = max_chars - keep_start
    
    truncated_chars = len(content) - max_chars
    truncation_marker = f"\n\n... [truncated {truncated_chars:,} chars] ...\n\n"
    
    return content[:keep_start] + truncation_marker + content[-keep_end:]

