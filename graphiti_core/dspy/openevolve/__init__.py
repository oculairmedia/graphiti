"""
OpenEvolve integration for Graphiti DSPy pipeline.

This module provides evolutionary optimization of:
- DSPy signature prompts/instructions
- Extraction heuristics
- Evaluation metrics
- Search scoring functions

Uses OpenEvolve's MAP-Elites quality-diversity evolution to discover
novel solutions that MIPROv2 prompt optimization alone wouldn't find.
"""

from graphiti_core.dspy.openevolve.evaluators import (
    EntityExtractionEvaluator,
    EdgeExtractionEvaluator,
    ResolutionEvaluator,
    create_evaluation_result,
)
from graphiti_core.dspy.openevolve.prompts import (
    PromptTemplate,
    load_prompt_template,
    save_prompt_template,
    inject_evolved_prompt,
)
from graphiti_core.dspy.openevolve.runner import (
    OpenEvolveRunner,
    EvolutionConfig,
    run_prompt_evolution,
)

__all__ = [
    # Evaluators
    'EntityExtractionEvaluator',
    'EdgeExtractionEvaluator',
    'ResolutionEvaluator',
    'create_evaluation_result',
    # Prompts
    'PromptTemplate',
    'load_prompt_template',
    'save_prompt_template',
    'inject_evolved_prompt',
    # Runner
    'OpenEvolveRunner',
    'EvolutionConfig',
    'run_prompt_evolution',
]
