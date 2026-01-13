"""
DSPy LM Configuration for Graphiti.

Supports multi-model load balancing for maximum concurrent throughput:
- Reasoning models: GLM-4.6, GLM-4.7 (output to reasoning_content field)
- Standard models: GLM-4.5 (standard OpenAI-compatible output)
- Fast models: GLM-4.5-air (lighter, faster for simple tasks)

Model selection strategy:
- Complex tasks (entity extraction, dedup): Use standard or reasoning models
- Simple tasks (summaries, high-volume): Use fast models
- Reasoning tasks (complex analysis): Use reasoning models with chain-of-thought
"""

import os
import logging
import time
import warnings
import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Literal, Any, ClassVar

import dspy

# Suppress benign Pydantic serialization warnings from DSPy/LiteLLM
warnings.filterwarnings('ignore', category=UserWarning, module='pydantic.main')

logger = logging.getLogger(__name__)

# Z.AI GLM endpoints
ZAI_API_BASE = 'https://api.z.ai/api/coding/paas/v4'

# Models that use reasoning_content field instead of content
# These models do chain-of-thought reasoning before providing final answer
# Note: glm-4.5-air also outputs reasoning first, but GLM-4.5 outputs to both fields
REASONING_MODELS = {
    'glm-4.6',
    'glm-4.7',
    'GLM-4.6',
    'GLM-4.7',  # Pure reasoning models
    'glm-4.5-air',  # Fast model but uses reasoning output
}


class ZAITokenTracker:
    """
    Shared token usage tracker for Z.AI API calls.
    Used by both ChutesClient and DSPy to track hourly token budget.

    Configure via environment variables:
    - ZAI_TOKENS_PER_HOUR: Maximum tokens per hour (default: 500000)
    - ZAI_MIN_REQUEST_DELAY: Minimum seconds between requests (default: 1.0)
    """

    _token_usage_history: ClassVar[deque] = deque(maxlen=10000)
    _hourly_token_budget: ClassVar[int] = int(os.environ.get('ZAI_TOKENS_PER_HOUR', '500000'))
    _min_request_delay: ClassVar[float] = float(os.environ.get('ZAI_MIN_REQUEST_DELAY', '1.0'))
    _last_request_time: ClassVar[float] = 0.0
    _lock: ClassVar[threading.Lock] = threading.Lock()

    @classmethod
    def get_hourly_usage(cls) -> int:
        """Calculate total tokens used in the last hour."""
        now = time.time()
        one_hour_ago = now - 3600
        with cls._lock:
            total = sum(tokens for ts, tokens in cls._token_usage_history if ts >= one_hour_ago)
        return total

    @classmethod
    def record_usage(cls, tokens: int, source: str = 'unknown') -> None:
        """Record token usage with timestamp."""
        with cls._lock:
            cls._token_usage_history.append((time.time(), tokens))
            cls._last_request_time = time.time()

        hourly = cls.get_hourly_usage()
        pct = (hourly / cls._hourly_token_budget * 100) if cls._hourly_token_budget > 0 else 0
        logger.info(
            f'📊 Z.AI [{source}] tokens: {tokens:,} | '
            f'Hourly: {hourly:,}/{cls._hourly_token_budget:,} ({pct:.1f}%)'
        )

    @classmethod
    def wait_for_budget_sync(cls) -> None:
        """Synchronous wait for token budget (for DSPy calls)."""
        with cls._lock:
            now = time.time()
            time_since_last = now - cls._last_request_time
            if time_since_last < cls._min_request_delay:
                wait_time = cls._min_request_delay - time_since_last
                logger.debug(f'Z.AI rate limit: waiting {wait_time:.2f}s between requests')
                time.sleep(wait_time)

            one_hour_ago = now - 3600
            hourly_usage = sum(
                tokens for ts, tokens in cls._token_usage_history if ts >= one_hour_ago
            )
            if hourly_usage >= cls._hourly_token_budget:
                now = time.time()
                one_hour_ago = now - 3600
                oldest_in_window = None
                for ts, _ in cls._token_usage_history:
                    if ts >= one_hour_ago:
                        oldest_in_window = ts
                        break

                if oldest_in_window:
                    wait_time = oldest_in_window + 3600 - now + 1
                    logger.warning(
                        f'Z.AI token budget exceeded ({hourly_usage:,}/{cls._hourly_token_budget:,}). '
                        f'Waiting {wait_time:.0f}s...'
                    )
                    time.sleep(wait_time)

    @classmethod
    def get_status(cls) -> dict:
        """Get current budget status."""
        hourly = cls.get_hourly_usage()
        return {
            'hourly_usage': hourly,
            'hourly_budget': cls._hourly_token_budget,
            'usage_percent': (hourly / cls._hourly_token_budget * 100)
            if cls._hourly_token_budget > 0
            else 0,
            'remaining': max(0, cls._hourly_token_budget - hourly),
        }


def _get_cache_enabled_default() -> bool:
    """Get default DSPy cache enabled value from environment."""
    env_value = os.environ.get('DSPY_ENABLE_CACHE', 'true').lower()
    return env_value in ('true', '1', 'yes', 'on')


def is_reasoning_model(model_name: str) -> bool:
    """Check if a model uses reasoning_content output format."""
    return model_name in REASONING_MODELS


# Model pools with concurrency limits
# Complex models - for entity extraction, deduplication, complex reasoning
COMPLEX_MODELS = [
    ('GLM-4.5', 5),  # Standard model - reverting, glm-4-plus has quota issues
]

# Simple/fast models - for summaries, high-volume tasks
# Note: glm-4.5-air requires reasoning_content handling, so use GLM-4.5 for simplicity
SIMPLE_MODELS = [
    ('GLM-4.5', 8),  # Standard model - reverting, glm-4-plus has quota issues
]

# Reasoning models - for complex analysis requiring chain-of-thought
# These models output reasoning steps to reasoning_content field
REASONING_MODEL_POOL = [
    ('glm-4.6', 3),  # Reasoning model with CoT - good for complex analysis
    ('glm-4.7', 3),  # Latest reasoning model - best for complex tasks
]


@dataclass
class ModelInstance:
    """Tracks a model instance and its usage."""

    name: str
    concurrency_limit: int
    lm: dspy.LM
    is_reasoning: bool = False  # Whether this model uses reasoning_content
    in_flight: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)

    def available(self) -> bool:
        """Check if model has capacity."""
        return self.in_flight < self.concurrency_limit

    def acquire(self) -> bool:
        """Try to acquire a slot. Returns True if successful."""
        with self.lock:
            if self.in_flight < self.concurrency_limit:
                self.in_flight += 1
                return True
            return False

    def release(self):
        """Release a slot."""
        with self.lock:
            self.in_flight = max(0, self.in_flight - 1)


class TokenTrackingLM:
    """
    Wrapper that tracks token usage for any DSPy LM.
    Estimates tokens from request/response length and records to ZAITokenTracker.
    """

    def __init__(self, lm: dspy.LM, model_name: str):
        self._lm = lm
        self._model_name = model_name
        # Forward all attributes to wrapped LM
        self.__dict__.update({k: v for k, v in lm.__dict__.items() if not k.startswith('_')})

    def __call__(self, *args, **kwargs) -> Any:
        """Call the underlying LM with token tracking."""
        # Wait for budget before making request
        ZAITokenTracker.wait_for_budget_sync()

        # Estimate input tokens from args (rough: 4 chars per token)
        input_chars = sum(len(str(a)) for a in args) + sum(len(str(v)) for v in kwargs.values())
        input_tokens_est = input_chars // 4

        response = self._lm(*args, **kwargs)

        # Estimate output tokens from response
        output_chars = len(str(response)) if response else 0
        output_tokens_est = output_chars // 4

        total_tokens_est = input_tokens_est + output_tokens_est
        ZAITokenTracker.record_usage(total_tokens_est, source=f'DSPy:{self._model_name}')

        return response

    def __getattr__(self, name: str) -> Any:
        """Forward attribute access to wrapped LM."""
        return getattr(self._lm, name)


class ReasoningLMWrapper:
    """
    Wrapper for reasoning models that extracts content from reasoning_content field.

    Reasoning models (GLM-4.6, GLM-4.7) output their chain-of-thought to
    `reasoning_content` and final answer to `content`. This wrapper ensures
    compatibility with code expecting standard OpenAI format.
    """

    def __init__(self, lm: dspy.LM, model_name: str):
        self._lm = lm
        self._model_name = model_name
        # Forward all attributes to wrapped LM
        self.__dict__.update({k: v for k, v in lm.__dict__.items() if not k.startswith('_')})

    def __call__(self, *args, **kwargs) -> Any:
        """Call the underlying LM and handle reasoning_content."""
        response = self._lm(*args, **kwargs)
        return self._process_response(response)

    def _process_response(self, response: Any) -> Any:
        """Process response to extract content from reasoning models."""
        if response is None:
            return response

        # Handle list of responses
        if isinstance(response, list):
            return [self._process_single(r) for r in response]

        return self._process_single(response)

    def _process_single(self, item: Any) -> Any:
        """Process a single response item."""
        # If it's a dict-like object with choices
        if hasattr(item, 'choices') or (isinstance(item, dict) and 'choices' in item):
            choices = item.choices if hasattr(item, 'choices') else item['choices']
            for choice in choices:
                message = (
                    choice.message if hasattr(choice, 'message') else choice.get('message', {})
                )

                # Check if content is empty and reasoning_content exists
                content = getattr(message, 'content', None) or message.get('content', '')
                reasoning = getattr(message, 'reasoning_content', None) or message.get(
                    'reasoning_content', ''
                )

                if not content and reasoning:
                    # Use reasoning content as main content
                    if hasattr(message, 'content'):
                        message.content = reasoning
                    else:
                        message['content'] = reasoning
                    logger.debug(
                        f'Extracted {len(reasoning)} chars from reasoning_content for {self._model_name}'
                    )

        return item

    def __getattr__(self, name: str) -> Any:
        """Forward attribute access to wrapped LM."""
        return getattr(self._lm, name)


@dataclass
class LMConfig:
    """Language model configuration."""

    api_base: str
    api_key: str
    max_tokens: int = 20000
    temperature: float = 0.1


class ModelPool:
    """Round-robin model pool with concurrency tracking."""

    def __init__(self, models: list[ModelInstance]):
        self.models = models
        self._index = 0
        self._lock = threading.Lock()

    def get_next(self) -> ModelInstance:
        """Get next available model using round-robin."""
        with self._lock:
            # Try each model in round-robin order
            for _ in range(len(self.models)):
                model = self.models[self._index]
                self._index = (self._index + 1) % len(self.models)
                if model.acquire():
                    return model

            # All models at capacity, return least loaded
            least_loaded = min(self.models, key=lambda m: m.in_flight / m.concurrency_limit)
            least_loaded.acquire()
            return least_loaded

    def total_capacity(self) -> int:
        """Total concurrent capacity across all models."""
        return sum(m.concurrency_limit for m in self.models)

    def current_load(self) -> int:
        """Current total in-flight requests."""
        return sum(m.in_flight for m in self.models)

    def status(self) -> str:
        """Get pool status string."""
        lines = []
        for m in self.models:
            lines.append(f'  {m.name}: {m.in_flight}/{m.concurrency_limit}')
        return '\n'.join(lines)


_config: LMConfig | None = None
_complex_pool: ModelPool | None = None
_simple_pool: ModelPool | None = None
_reasoning_pool: ModelPool | None = None


def get_lm_config() -> LMConfig:
    """Get current LM configuration."""
    global _config
    if _config is None:
        raise RuntimeError('LM not configured. Call configure_lm() first.')
    return _config


_dspy_default_configured = False


def _configure_default_lm_safe() -> None:
    """
    Set default LM via dspy.configure() only once, and only from the main async context.
    In Temporal activities or other async contexts, use dspy.context() instead.
    """
    global _dspy_default_configured, _complex_pool
    if _dspy_default_configured:
        return
    if _complex_pool is None:
        return
    try:
        dspy.configure(lm=_complex_pool.models[0].lm)
        _dspy_default_configured = True
    except RuntimeError as e:
        if 'same async task' in str(e):
            logger.debug('Skipping dspy.configure() - running in different async context')
        else:
            raise


def configure_lm(
    api_key: str | None = None,
    api_base: str | None = None,
    temperature: float = 0.1,
    max_tokens: int = 20000,
    use_multi_model: bool = True,
    cache: bool | None = None,
    enable_reasoning_models: bool = True,
) -> None:
    global _config, _complex_pool, _simple_pool, _reasoning_pool

    if _complex_pool is not None:
        return

    # Resolve configuration
    resolved_api_key = api_key or os.environ.get('CHUTES_API_KEY')
    if not resolved_api_key:
        raise ValueError('API key required. Set CHUTES_API_KEY or pass api_key.')

    resolved_api_base = api_base or os.environ.get('CHUTES_BASE_URL', ZAI_API_BASE)

    _config = LMConfig(
        api_base=resolved_api_base,
        api_key=resolved_api_key,
        max_tokens=max_tokens,
        temperature=temperature,
    )

    # Resolve cache setting
    if cache is None:
        cache = _get_cache_enabled_default()

    # Create model pools
    def create_lm(model_name: str, wrap_reasoning: bool = False) -> dspy.LM:
        """Create a DSPy LM, optionally wrapped for reasoning models and token tracking."""
        lm = dspy.LM(
            model=f'openai/{model_name}',
            api_base=resolved_api_base,
            api_key=resolved_api_key,
            temperature=temperature,
            max_tokens=max_tokens,
            cache=cache,  # Enable/disable response caching
        )

        # Wrap reasoning models to handle reasoning_content field
        if wrap_reasoning and is_reasoning_model(model_name):
            return ReasoningLMWrapper(lm, model_name)  # type: ignore

        # Note: Token tracking is handled by ZAITokenTracker in ChutesClient
        # DSPy LM tracking would require subclassing dspy.BaseLM
        return lm

    if use_multi_model:
        # Multi-model pools
        complex_instances = [
            ModelInstance(
                name=name,
                concurrency_limit=limit,
                lm=create_lm(name),
                is_reasoning=is_reasoning_model(name),
            )
            for name, limit in COMPLEX_MODELS
        ]
        simple_instances = [
            ModelInstance(
                name=name,
                concurrency_limit=limit,
                lm=create_lm(name),
                is_reasoning=is_reasoning_model(name),
            )
            for name, limit in SIMPLE_MODELS
        ]

        # Create reasoning model pool if enabled
        if enable_reasoning_models:
            reasoning_instances = [
                ModelInstance(
                    name=name,
                    concurrency_limit=limit,
                    lm=create_lm(name, wrap_reasoning=True),
                    is_reasoning=True,
                )
                for name, limit in REASONING_MODEL_POOL
            ]
            _reasoning_pool = ModelPool(reasoning_instances)
        else:
            _reasoning_pool = None
    else:
        # Single model per pool (backwards compatible)
        env_complex = os.environ.get('CHUTES_MODEL', 'GLM-4.5')
        env_simple = os.environ.get('CHUTES_SMALL_MODEL', 'glm-4.5-air')
        complex_instances = [
            ModelInstance(name=env_complex, concurrency_limit=10, lm=create_lm(env_complex))
        ]
        simple_instances = [
            ModelInstance(name=env_simple, concurrency_limit=20, lm=create_lm(env_simple))
        ]
        _reasoning_pool = None

    _complex_pool = ModelPool(complex_instances)
    _simple_pool = ModelPool(simple_instances)

    _configure_default_lm_safe()

    logger.info('DSPy configured with model pools:')
    logger.info(f'  Response caching: {"ENABLED" if cache else "DISABLED"}')
    logger.info(f'  Complex pool (capacity {_complex_pool.total_capacity()}):')
    for m in _complex_pool.models:
        logger.info(f'    - {m.name} (limit: {m.concurrency_limit})')
    logger.info(f'  Simple pool (capacity {_simple_pool.total_capacity()}):')
    for m in _simple_pool.models:
        logger.info(f'    - {m.name} (limit: {m.concurrency_limit})')
    if _reasoning_pool:
        logger.info(f'  Reasoning pool (capacity {_reasoning_pool.total_capacity()}):')
        for m in _reasoning_pool.models:
            logger.info(f'    - {m.name} (limit: {m.concurrency_limit}, reasoning=True)')


TaskType = Literal['complex', 'simple', 'reasoning']


def get_lm(task_type: TaskType = 'complex') -> dspy.LM:
    """
    Get an LM from the appropriate pool.

    Args:
        task_type: 'complex' for extraction/dedup, 'simple' for summaries,
                   'reasoning' for chain-of-thought tasks.

    Returns:
        DSPy LM instance from the least loaded model.
    """
    global _complex_pool, _simple_pool, _reasoning_pool

    if _complex_pool is None or _simple_pool is None:
        raise RuntimeError('LM not configured. Call configure_lm() first.')

    if task_type == 'reasoning':
        if _reasoning_pool is None:
            logger.warning('Reasoning pool not configured, falling back to complex pool')
            pool = _complex_pool
        else:
            pool = _reasoning_pool
    elif task_type == 'simple':
        pool = _simple_pool
    else:
        pool = _complex_pool

    return pool.get_next().lm


def get_model_with_tracking(task_type: TaskType = 'complex') -> ModelInstance:
    """
    Get a model instance with concurrency tracking.

    Use this when you need to manually release the model slot after completion.

    Args:
        task_type: 'complex', 'simple', or 'reasoning'

    Returns:
        ModelInstance with acquired slot. Call model.release() when done.
    """
    global _complex_pool, _simple_pool, _reasoning_pool

    if _complex_pool is None or _simple_pool is None:
        raise RuntimeError('LM not configured. Call configure_lm() first.')

    if task_type == 'reasoning':
        if _reasoning_pool is None:
            logger.warning('Reasoning pool not configured, falling back to complex pool')
            pool = _complex_pool
        else:
            pool = _reasoning_pool
    elif task_type == 'simple':
        pool = _simple_pool
    else:
        pool = _complex_pool

    return pool.get_next()


class tracked_lm:
    """
    Context manager for tracked LM usage.

    Usage:
        with tracked_lm('complex') as lm:
            result = dspy.Predict(sig)(...)

        with tracked_lm('reasoning') as lm:
            result = complex_analysis(...)
    """

    def __init__(self, task_type: TaskType = 'complex'):
        self.task_type: TaskType = task_type
        self.model: ModelInstance | None = None

    def __enter__(self) -> dspy.LM:
        self.model = get_model_with_tracking(self.task_type)
        return self.model.lm

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        if self.model:
            self.model.release()
        return False


def with_lm(task_type: TaskType = 'complex'):
    """
    Context manager to temporarily use a specific LM type.

    Usage:
        with with_lm('simple'):
            result = summary_module(...)

        with with_lm('reasoning'):
            result = complex_reasoning(...)
    """
    return dspy.context(lm=get_lm(task_type))


def get_pool_status() -> str:
    """Get current status of all model pools."""
    global _complex_pool, _simple_pool, _reasoning_pool

    if _complex_pool is None or _simple_pool is None:
        return 'Not configured'

    status = (
        f'Complex pool ({_complex_pool.current_load()}/{_complex_pool.total_capacity()}):\n'
        f'{_complex_pool.status()}\n'
        f'Simple pool ({_simple_pool.current_load()}/{_simple_pool.total_capacity()}):\n'
        f'{_simple_pool.status()}'
    )

    if _reasoning_pool:
        status += (
            f'\nReasoning pool ({_reasoning_pool.current_load()}/{_reasoning_pool.total_capacity()}):\n'
            f'{_reasoning_pool.status()}'
        )

    return status
