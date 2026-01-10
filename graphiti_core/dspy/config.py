"""
DSPy LM Configuration for Graphiti.

Supports multi-model load balancing for maximum concurrent throughput:
- Complex models: GLM-4.5, GLM-4-32B-0414-128K, GLM-4.7
- Simple models: GLM-4-Plus, GLM-4.5-Air, GLM-4.5-AirX
"""

import os
import logging
import warnings
import threading
from dataclasses import dataclass, field
from typing import Literal

import dspy

# Suppress benign Pydantic serialization warnings from DSPy/LiteLLM
warnings.filterwarnings('ignore', category=UserWarning, module='pydantic.main')

logger = logging.getLogger(__name__)

# Z.AI GLM endpoints
ZAI_API_BASE = 'https://api.z.ai/api/coding/paas/v4'


def _get_cache_enabled_default() -> bool:
    """Get default DSPy cache enabled value from environment."""
    env_value = os.environ.get('DSPY_ENABLE_CACHE', 'true').lower()
    return env_value in ('true', '1', 'yes', 'on')

# Model pools with concurrency limits
# Using single model to avoid rate limiting
COMPLEX_MODELS = [
    ('GLM-4.5', 5),  # Reduced concurrency
]

# Simple models - for summaries, high-volume tasks
SIMPLE_MODELS = [
    ('GLM-4.5', 5),  # Same model, reduced concurrency
]


@dataclass
class ModelInstance:
    """Tracks a model instance and its usage."""
    name: str
    concurrency_limit: int
    lm: dspy.LM
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


def get_lm_config() -> LMConfig:
    """Get current LM configuration."""
    global _config
    if _config is None:
        raise RuntimeError('LM not configured. Call configure_lm() first.')
    return _config


def configure_lm(
    api_key: str | None = None,
    api_base: str | None = None,
    temperature: float = 0.1,
    max_tokens: int = 20000,
    use_multi_model: bool = True,
    cache: bool | None = None,
) -> None:
    """
    Configure DSPy language models for Graphiti.

    Args:
        api_key: API key for LLM provider. Defaults to CHUTES_API_KEY env var.
        api_base: Base URL for API. Defaults to Z.AI endpoint.
        temperature: Sampling temperature.
        max_tokens: Maximum tokens per response.
        use_multi_model: Enable multi-model load balancing (default True).
        cache: Enable response caching. Defaults to DSPY_ENABLE_CACHE env var (true).
    """
    global _config, _complex_pool, _simple_pool

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
    def create_lm(model_name: str) -> dspy.LM:
        return dspy.LM(
            model=f'openai/{model_name}',
            api_base=resolved_api_base,
            api_key=resolved_api_key,
            temperature=temperature,
            max_tokens=max_tokens,
            cache=cache,  # Enable/disable response caching
        )

    if use_multi_model:
        # Multi-model pools
        complex_instances = [
            ModelInstance(name=name, concurrency_limit=limit, lm=create_lm(name))
            for name, limit in COMPLEX_MODELS
        ]
        simple_instances = [
            ModelInstance(name=name, concurrency_limit=limit, lm=create_lm(name))
            for name, limit in SIMPLE_MODELS
        ]
    else:
        # Single model per pool (backwards compatible)
        env_complex = os.environ.get('CHUTES_MODEL', 'GLM-4.5')
        env_simple = os.environ.get('CHUTES_SMALL_MODEL', 'GLM-4-Plus')
        complex_instances = [ModelInstance(name=env_complex, concurrency_limit=10, lm=create_lm(env_complex))]
        simple_instances = [ModelInstance(name=env_simple, concurrency_limit=20, lm=create_lm(env_simple))]

    _complex_pool = ModelPool(complex_instances)
    _simple_pool = ModelPool(simple_instances)

    # Set first complex model as default
    dspy.configure(lm=_complex_pool.models[0].lm)

    logger.info('DSPy configured with model pools:')
    logger.info(f'  Response caching: {"ENABLED" if cache else "DISABLED"}')
    logger.info(f'  Complex pool (capacity {_complex_pool.total_capacity()}):')
    for m in _complex_pool.models:
        logger.info(f'    - {m.name} (limit: {m.concurrency_limit})')
    logger.info(f'  Simple pool (capacity {_simple_pool.total_capacity()}):')
    for m in _simple_pool.models:
        logger.info(f'    - {m.name} (limit: {m.concurrency_limit})')


def get_lm(task_type: Literal['complex', 'simple'] = 'complex') -> dspy.LM:
    """
    Get an LM from the appropriate pool.

    Args:
        task_type: 'complex' for extraction/dedup, 'simple' for summaries.

    Returns:
        DSPy LM instance from the least loaded model.
    """
    global _complex_pool, _simple_pool

    if _complex_pool is None or _simple_pool is None:
        raise RuntimeError('LM not configured. Call configure_lm() first.')

    pool = _complex_pool if task_type == 'complex' else _simple_pool
    return pool.get_next().lm


def get_model_with_tracking(task_type: Literal['complex', 'simple'] = 'complex') -> ModelInstance:
    """
    Get a model instance with concurrency tracking.

    Use this when you need to manually release the model slot after completion.

    Args:
        task_type: 'complex' or 'simple'

    Returns:
        ModelInstance with acquired slot. Call model.release() when done.
    """
    global _complex_pool, _simple_pool

    if _complex_pool is None or _simple_pool is None:
        raise RuntimeError('LM not configured. Call configure_lm() first.')

    pool = _complex_pool if task_type == 'complex' else _simple_pool
    return pool.get_next()


class tracked_lm:
    """
    Context manager for tracked LM usage.

    Usage:
        with tracked_lm('complex') as lm:
            result = dspy.Predict(sig)(...)
    """

    def __init__(self, task_type: Literal['complex', 'simple'] = 'complex'):
        self.task_type = task_type
        self.model: ModelInstance | None = None

    def __enter__(self) -> dspy.LM:
        self.model = get_model_with_tracking(self.task_type)
        return self.model.lm

    def __exit__(self, exc_type, exc_val, exc_tb):  # noqa: ANN001
        if self.model:
            self.model.release()
        return False


def with_lm(task_type: Literal['complex', 'simple'] = 'complex'):
    """
    Context manager to temporarily use a specific LM type.

    Usage:
        with with_lm('simple'):
            result = summary_module(...)
    """
    return dspy.context(lm=get_lm(task_type))


def get_pool_status() -> str:
    """Get current status of all model pools."""
    global _complex_pool, _simple_pool

    if _complex_pool is None or _simple_pool is None:
        return 'Not configured'

    return (
        f'Complex pool ({_complex_pool.current_load()}/{_complex_pool.total_capacity()}):\n'
        f'{_complex_pool.status()}\n'
        f'Simple pool ({_simple_pool.current_load()}/{_simple_pool.total_capacity()}):\n'
        f'{_simple_pool.status()}'
    )
