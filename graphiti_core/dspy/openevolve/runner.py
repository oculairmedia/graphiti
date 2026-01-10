"""
OpenEvolve runner for Graphiti DSPy pipeline optimization.

This module provides:
- Configuration for OpenEvolve evolution runs
- Runner class to orchestrate evolution
- Integration with existing DSPy pipeline
"""

import json
import logging
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
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
class EvolutionConfig:
    """Configuration for OpenEvolve evolution run."""

    # Evolution parameters
    max_iterations: int = 100
    random_seed: int = 42
    population_size: int = 50
    num_islands: int = 3
    migration_interval: int = 20

    # LLM configuration - using Z.AI GLM models
    # Model selection strategy:
    # - GLM-4.5: Standard model for reliable structured output
    # - glm-4.6/4.7: Reasoning models for complex analysis (output to reasoning_content)
    # Note: glm-4.5-air also outputs to reasoning_content, so we use GLM-4.5 for simplicity
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

    # Output
    output_dir: str = 'openevolve_output'

    def to_yaml(self) -> str:
        """Convert to YAML config file format."""
        config = {
            'max_iterations': self.max_iterations,
            'random_seed': self.random_seed,
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
            'all_metrics': self.all_metrics,
            'evolution_history': self.evolution_history,
            'started_at': self.started_at,
            'completed_at': self.completed_at,
            'success': self.success,
            'error': self.error,
        }


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

            # Create config
            config_path = task_dir / 'config.yaml'
            config = EvolutionConfig(
                max_iterations=iterations or self.config.max_iterations,
                random_seed=self.config.random_seed,
                llm_api_base=self.config.llm_api_base,
                llm_model=self.config.llm_model,
                llm_temperature=self.config.llm_temperature,
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
                result.best_score = self._evaluate_program(task_name, best_program)
                result.iterations_completed = self.config.max_iterations

        except subprocess.TimeoutExpired:
            result.success = False
            result.error = 'Evolution timed out after 1 hour'

        return result

    def _run_api_evolution(
        self,
        task_name: str,
        initial_program_path: Path,
        evaluator_path: Path,
        config_path: Path,
        result: EvolutionResult,
    ) -> EvolutionResult:
        """Run evolution using OpenEvolve Python API."""
        try:
            from openevolve import run_evolution
        except ImportError:
            result.success = False
            result.error = 'OpenEvolve not installed. Run: pip install openevolve'
            return result

        # Create evaluator function
        evaluator_class = self._evaluators[task_name]
        evaluator = evaluator_class()

        def evaluate_fn(code_path: str) -> dict:
            eval_result = evaluator.evaluate(code_path)
            return eval_result.to_dict()

        try:
            evolution_result = run_evolution(
                initial_program=initial_program_path.read_text(),
                evaluator=evaluate_fn,
                iterations=self.config.max_iterations,
                config=str(config_path),
            )

            # Extract results from OpenEvolve's EvolutionResult
            if evolution_result.output_dir:
                result.best_program_path = str(Path(evolution_result.output_dir) / 'best' / 'best_program.py')
            else:
                result.best_program_path = ''
            result.best_score = evolution_result.best_score or 0.0
            result.iterations_completed = self.config.max_iterations
            result.all_metrics = evolution_result.metrics or {}
            result.success = True

        except Exception as e:
            result.success = False
            result.error = str(e)

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
