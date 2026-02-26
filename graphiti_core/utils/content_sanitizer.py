import logging
import re

logger = logging.getLogger(__name__)

# Regex patterns for common credential formats
CREDENTIAL_PATTERNS = [
    # API Keys with actual values (not variable references like ${VAR})
    (
        r'(?i)(OPENAI_API_KEY|ANTHROPIC_API_KEY|COMPOSIO_API_KEY|CEREBRAS_API_KEY|GITHUB_TOKEN|LETTA_API_KEY|LETTA_PASSWORD|LETTA_SERVER_PASSWORD|LETTA_API_TOKEN)=["\']?([A-Za-z0-9_\-\.]{20,})["\']?',
        r'\1=[REDACTED]',
    ),
    # OpenAI sk-proj keys
    (r'sk-proj-[A-Za-z0-9_\-]{20,}', '[REDACTED_OPENAI_KEY]'),
    # OpenAI sk- keys
    (r'sk-[A-Za-z0-9]{20,}', '[REDACTED_OPENAI_KEY]'),
    # GitHub PATs
    (r'github_pat_[A-Za-z0-9_]{20,}', '[REDACTED_GITHUB_PAT]'),
    # GitHub tokens (ghp_, gho_, ghs_, ghr_)
    (r'gh[posru]_[A-Za-z0-9]{20,}', '[REDACTED_GITHUB_TOKEN]'),
    # Bearer tokens with actual values (not variables)
    (r'Bearer\s+([A-Za-z0-9_\-\.]{20,})', 'Bearer [REDACTED_TOKEN]'),
    # Authorization headers with actual values
    (
        r'Authorization:\s*Bearer\s+([A-Za-z0-9_\-\.]{20,})',
        'Authorization: Bearer [REDACTED_TOKEN]',
    ),
    # Generic long API key patterns in env var assignments
    (
        r'(?i)(api[_-]?key|secret|password|token)\s*[=:]\s*["\']?([A-Za-z0-9_\-\.]{20,})["\']?',
        r'\1=[REDACTED]',
    ),
]


def sanitize_content(text: str) -> str:
    """Redact credentials and secrets from episode content before LLM processing."""
    if not text:
        return text

    sanitized = text
    redaction_count = 0

    for pattern, replacement in CREDENTIAL_PATTERNS:
        new_text = re.sub(pattern, replacement, sanitized)
        if new_text != sanitized:
            redaction_count += 1
            sanitized = new_text

    if redaction_count > 0:
        logger.warning(f'Sanitized {redaction_count} credential pattern(s) from episode content')

    return sanitized
