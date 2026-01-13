"""
OpenEvolve evaluator for entity_extraction.
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
    evaluator_class = {
        'entity_extraction': EntityExtractionEvaluator,
        'edge_extraction': EdgeExtractionEvaluator,
        'resolution': ResolutionEvaluator,
    }['entity_extraction']

    evaluator = evaluator_class(
        test_data_path='training_data/entity_extraction.json',
    )

    result = evaluator.evaluate(code_path)

    # Return in OpenEvolve format
    return {
        'metrics': result.metrics,
        'artifacts': result.artifacts,
    }


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: python entity_extraction_evaluator.py <code_path>')
        sys.exit(1)

    result = evaluate(sys.argv[1])
    print(json.dumps(result, indent=2))
