#!/usr/bin/env python3
"""
Example script to run OpenEvolve prompt evolution for Graphiti.

This script demonstrates how to:
1. Set up an evolution workspace
2. Run prompt evolution for entity extraction
3. Load and use evolved prompts

Prerequisites:
    pip install openevolve
    # Set your API key
    export OPENAI_API_KEY="your-gemini-api-key"  # Or OpenAI key

Usage:
    # Setup workspace
    python run_evolution.py --setup

    # Run evolution
    python run_evolution.py --task entity_extraction --iterations 50

    # Quick test (5 iterations)
    python run_evolution.py --task entity_extraction --iterations 5 --quick-test
"""

import argparse
import logging
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)


def check_prerequisites() -> bool:
    """Check if all prerequisites are met."""
    issues = []

    # Check OpenEvolve installation
    try:
        import openevolve  # noqa: F401
        logger.info("✓ OpenEvolve is installed")
    except ImportError:
        issues.append("OpenEvolve not installed. Run: pip install openevolve")

    # Check API key
    import os
    if not os.environ.get('OPENAI_API_KEY') and not os.environ.get('GOOGLE_API_KEY'):
        issues.append(
            "No API key found. Set OPENAI_API_KEY or GOOGLE_API_KEY environment variable"
        )
    else:
        logger.info("✓ API key configured")

    # Check training data
    training_data = Path(__file__).parent.parent.parent / 'training_data'
    if training_data.exists():
        logger.info(f"✓ Training data found at {training_data}")
    else:
        issues.append(
            f"Training data not found at {training_data}. "
            "Run the DSPy pipeline first to collect training data."
        )

    if issues:
        logger.error("Prerequisites not met:")
        for issue in issues:
            logger.error(f"  ✗ {issue}")
        return False

    return True


def setup_workspace(work_dir: Path) -> None:
    """Create evolution workspace with all necessary files."""
    from graphiti_core.dspy.openevolve.runner import create_evolution_workspace

    logger.info(f"Creating evolution workspace in {work_dir}")
    paths = create_evolution_workspace(work_dir)

    logger.info("\nWorkspace created with:")
    for name, path in paths.items():
        if isinstance(path, dict):
            for sub_name, sub_path in path.items():
                logger.info(f"  - {sub_name}: {sub_path}")
        else:
            logger.info(f"  - {name}: {path}")

    # Copy training data if available
    training_data = Path(__file__).parent.parent.parent / 'training_data'
    if training_data.exists():
        import shutil
        dest = work_dir / 'training_data'
        if not dest.exists():
            shutil.copytree(training_data, dest)
            logger.info(f"  - Copied training data to {dest}")


def run_evolution(
    task: str,
    iterations: int,
    work_dir: Path,
    config_path: Path | None = None,
) -> None:
    """Run OpenEvolve prompt evolution."""
    from graphiti_core.dspy.openevolve.runner import (
        OpenEvolveRunner,
        EvolutionConfig,
    )

    logger.info(f"\n{'='*60}")
    logger.info(f"Starting OpenEvolve prompt evolution")
    logger.info(f"  Task: {task}")
    logger.info(f"  Iterations: {iterations}")
    logger.info(f"  Work directory: {work_dir}")
    logger.info(f"{'='*60}\n")

    # Load or create config
    if config_path and config_path.exists():
        config = EvolutionConfig.from_yaml(config_path)
        logger.info(f"Loaded config from {config_path}")
    else:
        config = EvolutionConfig(max_iterations=iterations)
        logger.info("Using default configuration")

    # Run evolution
    runner = OpenEvolveRunner(config=config, work_dir=work_dir)
    result = runner.evolve(task, iterations=iterations)

    # Report results
    logger.info(f"\n{'='*60}")
    logger.info("Evolution Complete!")
    logger.info(f"{'='*60}")
    logger.info(f"  Task: {result.task_name}")
    logger.info(f"  Success: {result.success}")
    logger.info(f"  Iterations: {result.iterations_completed}")
    logger.info(f"  Best Score: {result.best_score:.4f}")

    if result.best_program_path:
        logger.info(f"  Best Program: {result.best_program_path}")

    if result.all_metrics:
        logger.info("\nMetrics:")
        for name, value in result.all_metrics.items():
            logger.info(f"    {name}: {value:.4f}")

    if result.error:
        logger.error(f"\nError: {result.error}")

    # Save results
    import json
    results_path = work_dir / f'{task}_results.json'
    with open(results_path, 'w') as f:
        json.dump(result.to_dict(), f, indent=2)
    logger.info(f"\nResults saved to {results_path}")


def demonstrate_evolved_prompt(work_dir: Path, task: str) -> None:
    """Demonstrate using an evolved prompt."""
    from graphiti_core.dspy.openevolve.runner import OpenEvolveRunner

    runner = OpenEvolveRunner(work_dir=work_dir)
    evolved_prompt = runner.load_evolved_prompt(task)

    if not evolved_prompt:
        logger.warning(f"No evolved prompt found for {task}")
        return

    logger.info(f"\n{'='*60}")
    logger.info(f"Evolved Prompt for {task}")
    logger.info(f"{'='*60}")
    logger.info(f"\nInstruction ({len(evolved_prompt.instruction)} chars):\n")
    logger.info(evolved_prompt.instruction[:500] + "..." if len(evolved_prompt.instruction) > 500 else evolved_prompt.instruction)

    if evolved_prompt.examples:
        logger.info(f"\nExamples: {len(evolved_prompt.examples)}")

    # Show how to use in DSPy pipeline
    logger.info("\n" + "="*60)
    logger.info("Usage in DSPy Pipeline:")
    logger.info("="*60)
    logger.info("""
from graphiti_core.dspy.openevolve import inject_evolved_prompt
from graphiti_core.dspy.modules import NodeExtractor

# Load evolved prompt
extractor = NodeExtractor()
inject_evolved_prompt(extractor, evolved_prompt.instruction)

# Now use the extractor with optimized prompts
result = extractor(
    current_message="Your text here...",
    entity_types=[...],
)
""")


def main():
    parser = argparse.ArgumentParser(
        description='Run OpenEvolve prompt evolution for Graphiti',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Setup workspace
  python run_evolution.py --setup

  # Run full evolution
  python run_evolution.py --task entity_extraction --iterations 100

  # Quick test run
  python run_evolution.py --task entity_extraction --iterations 5 --quick-test

  # Show evolved prompt
  python run_evolution.py --task entity_extraction --show-evolved
        """,
    )

    parser.add_argument(
        '--task',
        default='entity_extraction',
        choices=['entity_extraction', 'edge_extraction', 'resolution'],
        help='Task to evolve (default: entity_extraction)',
    )
    parser.add_argument(
        '--iterations',
        type=int,
        default=50,
        help='Number of evolution iterations (default: 50)',
    )
    parser.add_argument(
        '--work-dir',
        type=Path,
        default=Path(__file__).parent / 'openevolve_workspace',
        help='Working directory for evolution files',
    )
    parser.add_argument(
        '--config',
        type=Path,
        help='Path to custom config.yaml',
    )
    parser.add_argument(
        '--setup',
        action='store_true',
        help='Create evolution workspace and exit',
    )
    parser.add_argument(
        '--quick-test',
        action='store_true',
        help='Quick test mode (skips some checks)',
    )
    parser.add_argument(
        '--show-evolved',
        action='store_true',
        help='Show the evolved prompt for the task',
    )
    parser.add_argument(
        '--skip-prereq-check',
        action='store_true',
        help='Skip prerequisite checks',
    )

    args = parser.parse_args()

    # Handle setup
    if args.setup:
        setup_workspace(args.work_dir)
        logger.info("\n✓ Workspace ready! Next steps:")
        logger.info("  1. Set your API key: export OPENAI_API_KEY=...")
        logger.info("  2. Run evolution: python run_evolution.py --task entity_extraction")
        return

    # Handle show evolved
    if args.show_evolved:
        demonstrate_evolved_prompt(args.work_dir, args.task)
        return

    # Check prerequisites
    if not args.skip_prereq_check and not args.quick_test:
        if not check_prerequisites():
            logger.error("\nFix the above issues and try again.")
            logger.info("Or use --skip-prereq-check to bypass (not recommended).")
            sys.exit(1)

    # Run evolution
    run_evolution(
        task=args.task,
        iterations=args.iterations,
        work_dir=args.work_dir,
        config_path=args.config or (args.work_dir / 'config.yaml'),
    )


if __name__ == '__main__':
    main()
