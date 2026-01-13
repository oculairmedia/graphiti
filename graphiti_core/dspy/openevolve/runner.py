"""
OpenEvolve runner for Graphiti DSPy pipeline optimization.

This module provides:
- Configuration for OpenEvolve evolution runs
- Runner class to orchestrate evolution
- Integration with existing DSPy pipeline
- Disk checkpointing after each iteration
- Complete evolved code storage
- Graceful shutdown with signal handling
- Multi-provider round-robin for diversity and reliability
"""

import json
import logging
import os
import random
import signal
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from itertools import cycle
from pathlib import Path
from typing import Any

import yaml

from .evaluators import (
    EntityExtractionEvaluator,
    EdgeExtractionEvaluator,
    ResolutionEvaluator,
)
from .prompts import (
    PromptTemplate,
    create_evolution_seeds,
    get_initial_templates,
    load_prompt_template,
)

logger = logging.getLogger(__name__)


@dataclass
class ProviderConfig:
    """Configuration for a single LLM provider endpoint."""

    name: str  # Provider name for logging (e.g., 'openai-proxy', 'z-ai-glm')
    api_base: str  # API endpoint URL
    api_key: str = ''  # API key (can be empty for proxy endpoints)
    models: list[dict[str, Any]] = field(default_factory=list)  # Available models
    weight: float = 1.0  # Selection weight for round-robin
    timeout: int = 120  # Request timeout in seconds
    max_retries: int = 3  # Max retry attempts

    def get_model_names(self) -> list[str]:
        """Get list of model names from this provider."""
        return [m.get('name', m) if isinstance(m, dict) else m for m in self.models]

    def sample_model(self) -> dict[str, Any]:
        """Sample a model from this provider based on weights."""
        if not self.models:
            raise ValueError(f'No models configured for provider {self.name}')

        # Calculate total weight
        weights = [m.get('weight', 1.0) if isinstance(m, dict) else 1.0 for m in self.models]
        total = sum(weights)

        # Weighted random selection
        r = random.random() * total
        cumulative = 0.0
        for model, weight in zip(self.models, weights):
            cumulative += weight
            if r <= cumulative:
                if isinstance(model, dict):
                    return {'api_base': self.api_base, 'api_key': self.api_key, **model}
                return {'api_base': self.api_base, 'api_key': self.api_key, 'name': model}

        # Fallback to last model
        model = self.models[-1]
        if isinstance(model, dict):
            return {'api_base': self.api_base, 'api_key': self.api_key, **model}
        return {'api_base': self.api_base, 'api_key': self.api_key, 'name': model}


class MultiProviderManager:
    """
    Manages multiple LLM providers with round-robin selection.

    Provides:
    - Weighted round-robin across providers
    - Fallback on provider errors
    - Model diversity for evolution
    - Load balancing across endpoints
    """

    def __init__(
        self,
        providers: list[ProviderConfig],
        mode: str = 'weighted',  # 'weighted', 'sequential', 'random'
    ):
        self.providers = providers
        self.mode = mode
        self._sequential_index = 0
        self._provider_cycle = cycle(range(len(providers))) if providers else None
        self._call_counts: dict[str, int] = {p.name: 0 for p in providers}
        self._error_counts: dict[str, int] = {p.name: 0 for p in providers}

    def select_provider(self) -> ProviderConfig:
        """Select a provider based on the current mode."""
        if not self.providers:
            raise ValueError('No providers configured')

        if len(self.providers) == 1:
            return self.providers[0]

        if self.mode == 'sequential':
            # Round-robin through providers
            provider = self.providers[self._sequential_index]
            self._sequential_index = (self._sequential_index + 1) % len(self.providers)
            return provider

        elif self.mode == 'random':
            return random.choice(self.providers)

        else:  # weighted (default)
            # Weighted selection based on provider weights and error rates
            weights = []
            for p in self.providers:
                # Reduce weight for providers with high error rates
                error_rate = self._error_counts[p.name] / max(1, self._call_counts[p.name])
                adjusted_weight = p.weight * (1.0 - error_rate * 0.5)
                weights.append(max(0.1, adjusted_weight))  # Minimum weight of 0.1

            total = sum(weights)
            r = random.random() * total
            cumulative = 0.0
            for provider, weight in zip(self.providers, weights):
                cumulative += weight
                if r <= cumulative:
                    return provider

            return self.providers[-1]  # Fallback

    def sample_model_config(self) -> dict[str, Any]:
        """Sample a model configuration from a selected provider."""
        provider = self.select_provider()
        model_config = provider.sample_model()
        self._call_counts[provider.name] += 1
        return model_config

    def report_success(self, provider_name: str) -> None:
        """Report a successful call to a provider."""
        # Success slightly reduces error impact over time
        if provider_name in self._error_counts:
            self._error_counts[provider_name] = max(0, self._error_counts[provider_name] - 0.1)

    def report_error(self, provider_name: str) -> None:
        """Report an error from a provider."""
        if provider_name in self._error_counts:
            self._error_counts[provider_name] += 1

    def get_stats(self) -> dict[str, Any]:
        """Get provider statistics."""
        return {
            'providers': [
                {
                    'name': p.name,
                    'calls': self._call_counts[p.name],
                    'errors': self._error_counts[p.name],
                    'models': p.get_model_names(),
                }
                for p in self.providers
            ],
            'mode': self.mode,
        }

    def to_openevolve_config(self) -> dict[str, Any]:
        """
        Convert to OpenEvolve-compatible LLM config.

        Since OpenEvolve doesn't natively support multi-provider,
        we flatten all models into a single list with provider info.
        """
        all_models = []
        for provider in self.providers:
            for model in provider.models:
                model_config = model.copy() if isinstance(model, dict) else {'name': model}
                model_config['_provider'] = provider.name
                model_config['_api_base'] = provider.api_base
                model_config['_api_key'] = provider.api_key
                # Adjust weight by provider weight
                model_config['weight'] = model_config.get('weight', 1.0) * provider.weight
                all_models.append(model_config)

        # Use first provider as default (OpenEvolve requires single api_base)
        # We'll handle multi-provider in a custom LLM wrapper
        first = self.providers[0] if self.providers else None
        return {
            'api_base': first.api_base if first else '',
            'api_key': first.api_key if first else '',
            'models': all_models,
            '_multi_provider': True,
            '_providers': [
                {
                    'name': p.name,
                    'api_base': p.api_base,
                    'models': [m.get('name', m) if isinstance(m, dict) else m for m in p.models],
                }
                for p in self.providers
            ],
        }


def create_default_providers() -> list[ProviderConfig]:
    """
    Create default multi-provider configuration.

    Uses:
    - Local proxy for OpenAI models (gpt5, gpt51, codexmini) on port 8082
    - Local proxy for Gemini models on port 8083
    - Z.AI for GLM models (GLM-4.5, glm-4.6, glm-4.7)
    """
    providers = []

    # OpenAI Proxy (local) - Port 8082
    proxy_key = os.environ.get('OPENAI_API_KEY', 'dummy')
    providers.append(ProviderConfig(
        name='openai-proxy',
        api_base='http://192.168.50.90:8082/v1',
        api_key=proxy_key,
        weight=1.0,
        models=[
            {'name': 'gpt5', 'weight': 1.0},
            {'name': 'gpt51', 'weight': 0.9},
            {'name': 'codexmini', 'weight': 0.7},
            {'name': 'gpt5-reasoning-medium', 'weight': 0.5, 'reasoning': True},
        ],
    ))

    # Gemini Proxy (local) - Port 8083
    gemini_key = os.environ.get('GOOGLE_API_KEY', '')
    if gemini_key:
        providers.append(ProviderConfig(
            name='gemini-proxy',
            api_base='http://192.168.50.90:8083/v1',
            api_key=gemini_key,
            weight=1.0,
            models=[
                {'name': 'gemini-2.5-flash', 'weight': 1.0},
                {'name': 'gemini-2.5-pro', 'weight': 0.8},
                {'name': 'gemini-2.0-flash', 'weight': 0.7},
                {'name': 'gemini-2.0-flash-exp', 'weight': 0.5},
            ],
        ))

    # Z.AI GLM
    zai_key = os.environ.get('CHUTES_API_KEY', '')
    if zai_key:
        providers.append(ProviderConfig(
            name='z-ai-glm',
            api_base='https://api.z.ai/api/coding/paas/v4',
            api_key=zai_key,
            weight=0.6,  # Lower due to timeout issues
            timeout=180,  # Longer timeout for Z.AI
            models=[
                {'name': 'GLM-4.5', 'weight': 1.0},
                {'name': 'glm-4.6', 'weight': 0.8, 'reasoning': True},
                {'name': 'glm-4.7', 'weight': 0.6, 'reasoning': True},
            ],
        ))

    return providers


@dataclass
class EvolutionConfig:
    """Configuration for OpenEvolve evolution run."""

    # Evolution parameters
    max_iterations: int = 100
    random_seed: int = 42
    population_size: int = 50
    num_islands: int = 3
    migration_interval: int = 20

    # Multi-provider configuration (preferred over single provider)
    # Enables round-robin across multiple LLM endpoints for diversity and reliability
    providers: list[ProviderConfig] = field(default_factory=list)
    provider_mode: str = 'weighted'  # 'weighted', 'sequential', 'random'
    use_multi_provider: bool = False  # Enable multi-provider mode

    # Legacy single-provider configuration (fallback if providers list is empty)
    # LLM configuration - using Z.AI GLM models
    # Model selection strategy:
    # - GLM-4.5: Standard model for reliable structured output
    # - glm-4.6/4.7: Reasoning models for complex analysis (output to reasoning_content)
    llm_api_base: str = 'https://api.z.ai/api/coding/paas/v4'
    llm_model: str = 'GLM-4.5'  # Standard model - reliable output format
    llm_temperature: float = 0.7
    llm_models: list[dict[str, Any]] = field(default_factory=lambda: [
        {'name': 'GLM-4.5', 'weight': 1.0},  # Standard model - reliable for structured output
    ])

    # Feature dimensions for MAP-Elites (use built-in OpenEvolve features)
    feature_dimensions: list[str] = field(default_factory=lambda: [
        'score',
        'complexity',
        'diversity',
    ])

    # API key for Z.AI (read from env)
    llm_api_key: str = field(default_factory=lambda: __import__('os').environ.get('CHUTES_API_KEY', ''))

    # Evaluation settings
    enable_artifacts: bool = True
    cascade_evaluation: bool = False  # Disabled - we use direct evaluation
    use_llm_feedback: bool = True

    # Prompt configuration
    num_top_programs: int = 3
    num_diverse_programs: int = 2

    # Checkpointing configuration
    checkpoint_interval: int = 1  # Save after every iteration by default
    checkpoint_dir: str = 'checkpoints'  # Directory for checkpoint files
    save_all_programs: bool = True  # Save complete code for all evolved programs
    max_checkpoints: int = 10  # Keep only the last N checkpoints

    # Output
    output_dir: str = 'openevolve_output'

    def to_yaml(self) -> str:
        """Convert to YAML config file format."""
        config = {
            'max_iterations': self.max_iterations,
            'random_seed': self.random_seed,
            'checkpoint_interval': self.checkpoint_interval,  # Enable checkpointing
            'llm': {
                'api_base': self.llm_api_base,
                'api_key': self.llm_api_key,
                'model': self.llm_model,
                'temperature': self.llm_temperature,
                'models': self.llm_models,
            },
            'database': {
                'population_size': self.population_size,
                'num_islands': self.num_islands,
                'migration_interval': self.migration_interval,
                'feature_dimensions': self.feature_dimensions,
                'db_path': str(Path(self.output_dir) / 'database'),  # Persist database
            },
            'evaluator': {
                'enable_artifacts': self.enable_artifacts,
                'cascade_evaluation': self.cascade_evaluation,
                'use_llm_feedback': self.use_llm_feedback,
            },
            'prompt': {
                'num_top_programs': self.num_top_programs,
                'num_diverse_programs': self.num_diverse_programs,
            },
        }
        return yaml.dump(config, default_flow_style=False)

    def save(self, path: str | Path) -> None:
        """Save configuration to YAML file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_yaml())
        logger.info(f'Saved evolution config to {path}')

    @classmethod
    def from_yaml(cls, path: str | Path) -> 'EvolutionConfig':
        """Load configuration from YAML file."""
        with open(path) as f:
            data = yaml.safe_load(f)

        return cls(
            max_iterations=data.get('max_iterations', 100),
            random_seed=data.get('random_seed', 42),
            llm_api_base=data.get('llm', {}).get('api_base', ''),
            llm_model=data.get('llm', {}).get('model', 'gemini-2.5-flash'),
            llm_temperature=data.get('llm', {}).get('temperature', 0.7),
            llm_models=data.get('llm', {}).get('models', []),
            population_size=data.get('database', {}).get('population_size', 50),
            num_islands=data.get('database', {}).get('num_islands', 3),
            migration_interval=data.get('database', {}).get('migration_interval', 20),
            feature_dimensions=data.get('database', {}).get('feature_dimensions', []),
            enable_artifacts=data.get('evaluator', {}).get('enable_artifacts', True),
            cascade_evaluation=data.get('evaluator', {}).get('cascade_evaluation', True),
            use_llm_feedback=data.get('evaluator', {}).get('use_llm_feedback', True),
            num_top_programs=data.get('prompt', {}).get('num_top_programs', 3),
            num_diverse_programs=data.get('prompt', {}).get('num_diverse_programs', 2),
            output_dir=data.get('output_dir', 'openevolve_output'),
        )


@dataclass
class EvolutionResult:
    """Result from an OpenEvolve evolution run."""

    task_name: str
    iterations_completed: int
    best_score: float
    best_program_path: str
    best_program_code: str = ''  # Complete code of the best evolved program
    all_metrics: dict[str, float] = field(default_factory=dict)
    evolution_history: list[dict[str, Any]] = field(default_factory=list)
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: str = ''
    success: bool = True
    error: str = ''

    def to_dict(self) -> dict[str, Any]:
        return {
            'task_name': self.task_name,
            'iterations_completed': self.iterations_completed,
            'best_score': self.best_score,
            'best_program_path': self.best_program_path,
            'best_program_code': self.best_program_code,
            'all_metrics': self.all_metrics,
            'evolution_history': self.evolution_history,
            'started_at': self.started_at,
            'completed_at': self.completed_at,
            'success': self.success,
            'error': self.error,
        }

    def save(self, path: str | Path) -> None:
        """Save result to JSON file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)
        logger.info(f'Saved evolution result to {path}')

    @classmethod
    def load(cls, path: str | Path) -> 'EvolutionResult':
        """Load result from JSON file."""
        with open(path) as f:
            data = json.load(f)
        return cls(**data)


class CheckpointManager:
    """
    Manages checkpoints for OpenEvolve evolution runs.

    Provides:
    - Automatic checkpointing after each iteration
    - Complete evolved code storage
    - Checkpoint rotation (keeps only last N checkpoints)
    - Graceful shutdown support
    """

    def __init__(
        self,
        checkpoint_dir: Path,
        max_checkpoints: int = 10,
        save_all_programs: bool = True,
    ):
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self.max_checkpoints = max_checkpoints
        self.save_all_programs = save_all_programs
        self._best_program_code: str = ''
        self._best_score: float = 0.0
        self._iteration: int = 0
        self._shutdown_requested: bool = False

    def save_checkpoint(
        self,
        iteration: int,
        database: Any,
        best_program_id: str | None = None,
    ) -> Path:
        """Save a checkpoint after an iteration."""
        self._iteration = iteration
        checkpoint_path = self.checkpoint_dir / f'checkpoint_{iteration:05d}'
        checkpoint_path.mkdir(parents=True, exist_ok=True)

        # Save database state
        if hasattr(database, 'save'):
            db_path = checkpoint_path / 'database'
            database.save(str(db_path), iteration=iteration)

        # Save best program code if available
        if best_program_id and hasattr(database, 'get'):
            program = database.get(best_program_id)
            if program and hasattr(program, 'code'):
                self._best_program_code = program.code
                best_program_path = checkpoint_path / 'best_program.py'
                best_program_path.write_text(program.code)

                # Also update the latest best program link
                latest_best = self.checkpoint_dir / 'latest_best_program.py'
                latest_best.write_text(program.code)

                # Save metrics alongside
                if hasattr(program, 'metrics'):
                    metrics_path = checkpoint_path / 'best_metrics.json'
                    with open(metrics_path, 'w') as f:
                        json.dump(program.metrics, f, indent=2)
                    self._best_score = program.metrics.get('score', 0.0)

        # Save checkpoint metadata
        metadata = {
            'iteration': iteration,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'best_program_id': best_program_id,
            'best_score': self._best_score,
        }
        metadata_path = checkpoint_path / 'metadata.json'
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)

        logger.info(f'Saved checkpoint at iteration {iteration} to {checkpoint_path}')

        # Rotate old checkpoints
        self._rotate_checkpoints()

        return checkpoint_path

    def _rotate_checkpoints(self) -> None:
        """Remove old checkpoints, keeping only the last N."""
        checkpoints = sorted(self.checkpoint_dir.glob('checkpoint_*'))
        if len(checkpoints) > self.max_checkpoints:
            for old_checkpoint in checkpoints[:-self.max_checkpoints]:
                import shutil
                shutil.rmtree(old_checkpoint)
                logger.debug(f'Removed old checkpoint: {old_checkpoint}')

    def load_latest_checkpoint(self) -> dict[str, Any] | None:
        """Load the most recent checkpoint."""
        checkpoints = sorted(self.checkpoint_dir.glob('checkpoint_*'))
        if not checkpoints:
            return None

        latest = checkpoints[-1]
        metadata_path = latest / 'metadata.json'
        if not metadata_path.exists():
            return None

        with open(metadata_path) as f:
            metadata = json.load(f)

        # Load best program code if available
        best_program_path = latest / 'best_program.py'
        if best_program_path.exists():
            metadata['best_program_code'] = best_program_path.read_text()

        logger.info(f'Loaded checkpoint from iteration {metadata.get("iteration", "unknown")}')
        return metadata

    def get_best_program_code(self) -> str:
        """Get the best program code seen so far."""
        # First check if we have it in memory
        if self._best_program_code:
            return self._best_program_code

        # Otherwise try to load from latest checkpoint
        latest_best = self.checkpoint_dir / 'latest_best_program.py'
        if latest_best.exists():
            return latest_best.read_text()

        return ''

    def request_shutdown(self) -> None:
        """Request graceful shutdown."""
        self._shutdown_requested = True
        logger.info('Graceful shutdown requested - will save checkpoint and exit')

    @property
    def shutdown_requested(self) -> bool:
        """Check if shutdown was requested."""
        return self._shutdown_requested


class SignalHandler:
    """Handles OS signals for graceful shutdown."""

    def __init__(self, checkpoint_manager: CheckpointManager):
        self.checkpoint_manager = checkpoint_manager
        self._original_sigint = None
        self._original_sigterm = None

    def install(self) -> None:
        """Install signal handlers."""
        self._original_sigint = signal.signal(signal.SIGINT, self._handle_signal)
        self._original_sigterm = signal.signal(signal.SIGTERM, self._handle_signal)
        logger.info('Installed signal handlers for graceful shutdown')

    def uninstall(self) -> None:
        """Restore original signal handlers."""
        if self._original_sigint:
            signal.signal(signal.SIGINT, self._original_sigint)
        if self._original_sigterm:
            signal.signal(signal.SIGTERM, self._original_sigterm)

    def _handle_signal(self, signum: int, frame: Any) -> None:
        """Handle interrupt signals."""
        sig_name = signal.Signals(signum).name
        logger.warning(f'Received {sig_name} - requesting graceful shutdown')
        self.checkpoint_manager.request_shutdown()


class OpenEvolveRunner:
    """
    Runner for OpenEvolve prompt evolution.

    Orchestrates the evolution of DSPy prompts using OpenEvolve's
    MAP-Elites quality-diversity algorithm.
    """

    def __init__(
        self,
        config: EvolutionConfig | None = None,
        work_dir: str | Path = 'openevolve_work',
    ):
        self.config = config or EvolutionConfig()
        self.work_dir = Path(work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)

        # Checkpoint management
        self._checkpoint_manager: CheckpointManager | None = None
        self._signal_handler: SignalHandler | None = None

        # Evaluators
        self._evaluators = {
            'entity_extraction': EntityExtractionEvaluator,
            'edge_extraction': EdgeExtractionEvaluator,
            'resolution': ResolutionEvaluator,
        }

    def _check_openevolve_installed(self) -> bool:
        """Check if OpenEvolve is installed."""
        try:
            import openevolve  # noqa: F401
            return True
        except ImportError:
            return False

    def _create_evaluator_script(self, task_name: str) -> Path:
        """Create a standalone evaluator script for OpenEvolve CLI."""
        evaluator_path = self.work_dir / f'{task_name}_evaluator.py'

        # Get the test data path
        test_data_path = Path('training_data') / f'{task_name}.json'

        script = f'''"""
OpenEvolve evaluator for {task_name}.
Auto-generated - do not edit directly.
"""

import sys
import json
from pathlib import Path

# Add graphiti to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from graphiti_core.dspy.openevolve.evaluators import (
    EntityExtractionEvaluator,
    EdgeExtractionEvaluator,
    ResolutionEvaluator,
    EvaluationResult,
)


def evaluate(code_path: str) -> dict:
    """Evaluate evolved code and return OpenEvolve-compatible result."""
    evaluator_class = {{
        'entity_extraction': EntityExtractionEvaluator,
        'edge_extraction': EdgeExtractionEvaluator,
        'resolution': ResolutionEvaluator,
    }}['{task_name}']

    evaluator = evaluator_class(
        test_data_path='{test_data_path}',
    )

    result = evaluator.evaluate(code_path)

    # Return in OpenEvolve format
    return {{
        'metrics': result.metrics,
        'artifacts': result.artifacts,
    }}


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: python {task_name}_evaluator.py <code_path>')
        sys.exit(1)

    result = evaluate(sys.argv[1])
    print(json.dumps(result, indent=2))
'''
        evaluator_path.write_text(script)
        return evaluator_path

    def _create_system_message(self, task_name: str) -> str:
        """Create system message for LLM during evolution."""
        templates = get_initial_templates()
        template = templates.get(task_name)

        if not template:
            return f'You are optimizing a {task_name} prompt for a knowledge graph system.'

        return f'''You are an expert prompt engineer optimizing a {task_name} prompt for Graphiti, a temporal knowledge graph framework.

TARGET: Improve {template.metadata.get('target_metric', 'extraction quality')} by 10-20%

OPTIMIZATION OPPORTUNITIES:
- More precise entity/relationship extraction instructions
- Better handling of ambiguous cases
- Improved few-shot examples
- Clearer constraint specification
- Better temporal reasoning instructions

CONSTRAINTS:
- Do not change the output format (must return valid JSON)
- Maintain compatibility with DSPy signatures
- Keep instructions under 500 words
- Preserve core extraction logic

CURRENT CONSTRAINTS TO PRESERVE:
{json.dumps(template.constraints, indent=2)}

Focus on clarity, precision, and robustness to edge cases.'''

    def evolve(
        self,
        task_name: str,
        iterations: int | None = None,
        use_cli: bool = True,
    ) -> EvolutionResult:
        """
        Run OpenEvolve evolution for a specific task.

        Args:
            task_name: One of 'entity_extraction', 'edge_extraction', 'resolution'
            iterations: Override max iterations from config
            use_cli: Use OpenEvolve CLI (True) or Python API (False)

        Returns:
            EvolutionResult with best evolved program and metrics
        """
        if task_name not in self._evaluators:
            raise ValueError(f'Unknown task: {task_name}. Choose from {list(self._evaluators.keys())}')

        result = EvolutionResult(
            task_name=task_name,
            iterations_completed=0,
            best_score=0.0,
            best_program_path='',
        )

        try:
            # Create evolution directory
            task_dir = self.work_dir / task_name
            task_dir.mkdir(parents=True, exist_ok=True)

            # Create initial program (seed)
            templates = get_initial_templates()
            initial_program_path = task_dir / 'initial_program.py'
            templates[task_name].save(initial_program_path)

            # Create evaluator script
            evaluator_path = self._create_evaluator_script(task_name)

            # Create config (copy all LLM settings from self.config)
            config_path = task_dir / 'config.yaml'
            config = EvolutionConfig(
                max_iterations=iterations or self.config.max_iterations,
                random_seed=self.config.random_seed,
                llm_api_base=self.config.llm_api_base,
                llm_api_key=self.config.llm_api_key,
                llm_model=self.config.llm_model,
                llm_temperature=self.config.llm_temperature,
                llm_models=self.config.llm_models,  # Use configured models
                output_dir=str(task_dir / 'output'),
            )

            # Add system message
            config_data = yaml.safe_load(config.to_yaml())
            config_data['prompt'] = config_data.get('prompt', {})
            config_data['prompt']['system_message'] = self._create_system_message(task_name)

            with open(config_path, 'w') as f:
                yaml.dump(config_data, f, default_flow_style=False)

            if use_cli:
                result = self._run_cli_evolution(
                    task_name=task_name,
                    initial_program_path=initial_program_path,
                    evaluator_path=evaluator_path,
                    config_path=config_path,
                    result=result,
                )
            else:
                result = self._run_api_evolution(
                    task_name=task_name,
                    initial_program_path=initial_program_path,
                    evaluator_path=evaluator_path,
                    config_path=config_path,
                    result=result,
                )

        except Exception as e:
            logger.error(f'Evolution error: {e}')
            result.success = False
            result.error = str(e)

        result.completed_at = datetime.now(timezone.utc).isoformat()
        return result

    def _run_cli_evolution(
        self,
        task_name: str,
        initial_program_path: Path,
        evaluator_path: Path,
        config_path: Path,
        result: EvolutionResult,
    ) -> EvolutionResult:
        """Run evolution using OpenEvolve CLI."""
        if not self._check_openevolve_installed():
            result.success = False
            result.error = 'OpenEvolve not installed. Run: pip install openevolve'
            return result

        cmd = [
            sys.executable, '-m', 'openevolve',
            str(initial_program_path),
            str(evaluator_path),
            '--config', str(config_path),
            '--iterations', str(self.config.max_iterations),
        ]

        logger.info(f'Running OpenEvolve: {" ".join(cmd)}')

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=3600,  # 1 hour timeout
                cwd=str(self.work_dir),
            )

            if proc.returncode != 0:
                result.success = False
                result.error = f'OpenEvolve failed: {proc.stderr}'
                return result

            # Parse output to find best program
            output_dir = self.work_dir / task_name / 'output'
            best_program = self._find_best_program(output_dir)

            if best_program:
                result.best_program_path = str(best_program)
                result.best_program_code = best_program.read_text()  # Store complete code
                result.best_score = self._evaluate_program(task_name, best_program)
                result.iterations_completed = self.config.max_iterations

        except subprocess.TimeoutExpired:
            result.success = False
            result.error = 'Evolution timed out after 1 hour'

            # Try to recover best program from checkpoints
            checkpoint_dir = self.work_dir / task_name / self.config.checkpoint_dir
            latest_best = checkpoint_dir / 'latest_best_program.py'
            if latest_best.exists():
                result.best_program_code = latest_best.read_text()
                result.best_program_path = str(latest_best)

        return result

    def _run_api_evolution(
        self,
        task_name: str,
        initial_program_path: Path,
        evaluator_path: Path,
        config_path: Path,
        result: EvolutionResult,
    ) -> EvolutionResult:
        """
        Run evolution using OpenEvolve Python API with enhanced checkpointing.

        Features:
        - Saves checkpoint after each iteration
        - Stores complete evolved code (not truncated)
        - Supports graceful shutdown with signal handling
        - Can resume from checkpoints
        """
        try:
            from openevolve.controller import OpenEvolve
            from openevolve.config import load_config
        except ImportError:
            result.success = False
            result.error = 'OpenEvolve not installed. Run: pip install openevolve'
            return result

        # Set up checkpoint directory
        task_dir = self.work_dir / task_name
        checkpoint_dir = task_dir / self.config.checkpoint_dir
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        output_dir = task_dir / 'output'
        output_dir.mkdir(parents=True, exist_ok=True)

        # Initialize checkpoint manager
        self._checkpoint_manager = CheckpointManager(
            checkpoint_dir=checkpoint_dir,
            max_checkpoints=self.config.max_checkpoints,
            save_all_programs=self.config.save_all_programs,
        )

        # Set up signal handler for graceful shutdown
        self._signal_handler = SignalHandler(self._checkpoint_manager)
        self._signal_handler.install()

        try:
            # Load OpenEvolve config
            config = load_config(str(config_path))

            # Ensure checkpoint_interval is 1 for per-iteration checkpoints
            config.checkpoint_interval = self.config.checkpoint_interval

            # Set database path for persistence
            db_path = str(checkpoint_dir / 'database')
            config.database.db_path = db_path

            # Check for existing checkpoint to resume from
            existing_checkpoint = self._checkpoint_manager.load_latest_checkpoint()
            start_iteration = 0
            if existing_checkpoint:
                start_iteration = existing_checkpoint.get('iteration', 0) + 1
                logger.info(f'Resuming evolution from iteration {start_iteration}')
                if existing_checkpoint.get('best_program_code'):
                    result.best_program_code = existing_checkpoint['best_program_code']

            # Create OpenEvolve controller
            controller = OpenEvolve(
                initial_program_path=str(initial_program_path),
                evaluation_file=str(evaluator_path),
                config=config,
                output_dir=str(output_dir),
            )

            # Run evolution
            import asyncio

            async def run_with_checkpointing() -> None:
                """Run evolution with manual checkpointing after database is modified."""
                # Run the evolution
                best_program = await controller.run(
                    iterations=self.config.max_iterations - start_iteration,
                    target_score=None,
                    checkpoint_path=db_path,
                )

                # Save final best program
                if best_program:
                    result.best_program_code = best_program.code
                    result.best_score = best_program.metrics.get('score', 0.0)
                    result.all_metrics = best_program.metrics

                    # Save to file
                    best_path = output_dir / 'best_program.py'
                    best_path.write_text(best_program.code)
                    result.best_program_path = str(best_path)

                    # Also save to checkpoint dir
                    latest_best = checkpoint_dir / 'latest_best_program.py'
                    latest_best.write_text(best_program.code)

                    # Save metrics
                    metrics_path = output_dir / 'best_metrics.json'
                    with open(metrics_path, 'w') as f:
                        json.dump(best_program.metrics, f, indent=2)

                # Save iteration count
                result.iterations_completed = controller.database.last_iteration

            # Run the async evolution
            asyncio.run(run_with_checkpointing())
            result.success = True

            # Save final result
            result_path = output_dir / 'evolution_result.json'
            result.save(result_path)

            logger.info(f'Evolution complete. Best program saved to {result.best_program_path}')

        except Exception as e:
            logger.error(f'Evolution failed: {e}')
            result.success = False
            result.error = str(e)

            # Try to save partial result if we have any checkpoint
            if self._checkpoint_manager:
                best_code = self._checkpoint_manager.get_best_program_code()
                if best_code:
                    result.best_program_code = best_code
                    result.best_program_path = str(checkpoint_dir / 'latest_best_program.py')
                    logger.info(f'Partial result saved from checkpoint: {result.best_program_path}')

        finally:
            # Restore signal handlers
            if self._signal_handler:
                self._signal_handler.uninstall()

        return result

    def _find_best_program(self, output_dir: Path) -> Path | None:
        """Find the best evolved program in output directory."""
        if not output_dir.exists():
            return None

        # Look for checkpoint directories
        checkpoints = sorted(output_dir.glob('checkpoints/checkpoint_*'))
        if not checkpoints:
            return None

        # Get latest checkpoint
        latest = checkpoints[-1]

        # Look for best program file
        for pattern in ['best_program.py', 'best.py', '*.py']:
            matches = list(latest.glob(pattern))
            if matches:
                return matches[0]

        return None

    def _evaluate_program(self, task_name: str, program_path: Path) -> float:
        """Evaluate a program and return its score."""
        evaluator_class = self._evaluators[task_name]
        evaluator = evaluator_class()
        result = evaluator.evaluate(str(program_path))
        return result.metrics.get('score', 0.0)

    def evolve_all(
        self,
        iterations: int | None = None,
    ) -> dict[str, EvolutionResult]:
        """Run evolution for all tasks."""
        results = {}
        for task_name in self._evaluators:
            logger.info(f'Starting evolution for {task_name}')
            results[task_name] = self.evolve(task_name, iterations)
        return results

    def load_evolved_prompt(self, task_name: str) -> PromptTemplate | None:
        """Load the best evolved prompt for a task."""
        task_dir = self.work_dir / task_name / 'output'
        best_program = self._find_best_program(task_dir)

        if not best_program:
            logger.warning(f'No evolved prompt found for {task_name}')
            return None

        return load_prompt_template(best_program)


def run_prompt_evolution(
    task: str = 'entity_extraction',
    iterations: int = 50,
    work_dir: str = 'openevolve_work',
    config: EvolutionConfig | None = None,
) -> EvolutionResult:
    """
    Convenience function to run prompt evolution.

    Args:
        task: Task to evolve ('entity_extraction', 'edge_extraction', 'resolution')
        iterations: Number of evolution iterations
        work_dir: Working directory for evolution files
        config: Optional evolution configuration

    Returns:
        EvolutionResult with best program and metrics
    """
    runner = OpenEvolveRunner(config=config, work_dir=work_dir)
    return runner.evolve(task, iterations=iterations)


def create_evolution_workspace(
    output_dir: str | Path = 'openevolve_workspace',
) -> dict[str, Path]:
    """
    Create a complete evolution workspace with all necessary files.

    Args:
        output_dir: Directory to create workspace in

    Returns:
        Dict mapping file type to path
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    paths = {}

    # Create seed prompts
    seeds_dir = output_dir / 'seeds'
    seed_paths = create_evolution_seeds(seeds_dir)
    paths['seeds'] = seed_paths

    # Create default config
    config = EvolutionConfig()
    config_path = output_dir / 'config.yaml'
    config.save(config_path)
    paths['config'] = config_path

    # Create README
    readme_path = output_dir / 'README.md'
    readme_path.write_text('''# Graphiti OpenEvolve Workspace

This directory contains files for evolving Graphiti DSPy prompts using OpenEvolve.

## Structure

- `seeds/`: Initial prompt templates to evolve
- `config.yaml`: Evolution configuration
- `training_data/`: Test data for evaluation (copy from main training_data/)

## Usage

```bash
# Install OpenEvolve
pip install openevolve

# Run evolution for entity extraction
python -m graphiti_core.dspy.openevolve.runner \\
    --task entity_extraction \\
    --iterations 100 \\
    --work-dir ./openevolve_work

# Or use the Python API
from graphiti_core.dspy.openevolve import run_prompt_evolution

result = run_prompt_evolution(
    task='entity_extraction',
    iterations=100,
)
print(f"Best score: {result.best_score}")
```

## Configuration

Edit `config.yaml` to customize:
- LLM provider and model
- Population size and islands
- Feature dimensions for MAP-Elites
- Evaluation parameters

## Results

Evolved prompts are saved to `openevolve_work/<task>/output/`.
''')
    paths['readme'] = readme_path

    logger.info(f'Created evolution workspace in {output_dir}')
    return paths


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Run OpenEvolve prompt evolution')
    parser.add_argument('--task', default='entity_extraction',
                       choices=['entity_extraction', 'edge_extraction', 'resolution'],
                       help='Task to evolve')
    parser.add_argument('--iterations', type=int, default=50,
                       help='Number of evolution iterations')
    parser.add_argument('--work-dir', default='openevolve_work',
                       help='Working directory')
    parser.add_argument('--setup', action='store_true',
                       help='Create evolution workspace and exit')

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    if args.setup:
        create_evolution_workspace(args.work_dir)
        print(f'Created workspace in {args.work_dir}')
    else:
        result = run_prompt_evolution(
            task=args.task,
            iterations=args.iterations,
            work_dir=args.work_dir,
        )

        print(f'\nEvolution Result:')
        print(f'  Task: {result.task_name}')
        print(f'  Success: {result.success}')
        print(f'  Best Score: {result.best_score:.4f}')
        print(f'  Best Program: {result.best_program_path}')

        if result.error:
            print(f'  Error: {result.error}')
