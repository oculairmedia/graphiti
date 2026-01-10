# OpenEvolve Integration for Graphiti

This directory contains the OpenEvolve integration for evolving Graphiti's DSPy prompts using MAP-Elites quality-diversity evolution.

## Overview

OpenEvolve uses LLMs to autonomously discover and optimize prompts through evolutionary processes. This integration allows you to:

1. **Evolve Entity Extraction Prompts** - Improve F1 scores for entity recognition
2. **Evolve Edge Extraction Prompts** - Better relationship extraction
3. **Evolve Resolution Prompts** - More accurate entity deduplication

## Why OpenEvolve + DSPy?

| Approach | Strengths |
|----------|-----------|
| **DSPy MIPROv2** | Optimizes few-shot examples, local search |
| **OpenEvolve** | Discovers novel prompt structures, quality-diversity |
| **Combined** | Best of both - MIPROv2 for refinement, OpenEvolve for exploration |

## Quick Start

### 1. Install Dependencies

```bash
# Install OpenEvolve
pip install openevolve

# Set your API key (Gemini recommended for cost/quality balance)
export OPENAI_API_KEY="your-api-key"
```

### 2. Setup Workspace

```bash
python run_evolution.py --setup
```

This creates:
- `openevolve_workspace/seeds/` - Initial prompt templates
- `openevolve_workspace/config.yaml` - Evolution configuration
- `openevolve_workspace/training_data/` - Test data for evaluation

### 3. Collect Training Data

Before running evolution, collect training data from successful DSPy pipeline runs:

```python
from graphiti_core.dspy import DSPyIngestionPipeline, TrainingDataCollector

# Create pipeline with data collection
pipeline = DSPyIngestionPipeline(enable_response_logging=True)

# Run some episodes to collect examples
for episode in episodes:
    result = pipeline.ingest_episode(episode['content'])

# Data is automatically saved to training_data/
```

### 4. Run Evolution

```bash
# Quick test (5 iterations)
python run_evolution.py --task entity_extraction --iterations 5 --quick-test

# Full evolution
python run_evolution.py --task entity_extraction --iterations 100

# All tasks
python run_evolution.py --task entity_extraction --iterations 50
python run_evolution.py --task edge_extraction --iterations 50
python run_evolution.py --task resolution --iterations 50
```

### 5. Use Evolved Prompts

```python
from graphiti_core.dspy.openevolve import (
    OpenEvolveRunner,
    inject_evolved_prompt,
)
from graphiti_core.dspy.modules import NodeExtractor

# Load evolved prompt
runner = OpenEvolveRunner(work_dir='openevolve_workspace')
evolved_prompt = runner.load_evolved_prompt('entity_extraction')

# Inject into DSPy module
extractor = NodeExtractor()
inject_evolved_prompt(extractor, evolved_prompt.instruction)

# Use with optimized prompts!
result = extractor(
    current_message="Alice from Anthropic met Bob at the AI conference.",
    entity_types=[...],
)
```

## Configuration

Edit `config.yaml` to customize evolution:

```yaml
max_iterations: 100
random_seed: 42

llm:
  # Gemini (recommended)
  api_base: "https://generativelanguage.googleapis.com/v1beta/openai/"
  model: "gemini-2.5-flash"

  # Or local Ollama
  # api_base: "http://localhost:11434/v1"
  # model: "codellama:7b"

database:
  population_size: 100    # More diverse solutions
  num_islands: 3          # Parallel populations
  migration_interval: 25  # Exchange solutions

evaluator:
  enable_artifacts: true  # Learn from errors
  cascade_evaluation: true
```

## How It Works

### Evolution Pipeline

```
┌─────────────────────────────────────────────────────────┐
│                    OpenEvolve                            │
│                                                          │
│  1. Initialize population with seed prompts             │
│  2. LLM generates prompt variations                      │
│  3. Evaluate using Graphiti metrics (F1, accuracy)      │
│  4. MAP-Elites maintains quality-diversity              │
│  5. Islands evolve independently, exchange solutions    │
│  6. Best prompt saved after N iterations                │
└─────────────────────────────────────────────────────────┘
            │
            ▼
┌─────────────────────────────────────────────────────────┐
│                    DSPy Pipeline                         │
│                                                          │
│  NodeExtractor ─► EdgeExtractor ─► NodeResolver         │
│       │                │                │                │
│  (evolved prompt) (evolved prompt) (evolved prompt)     │
└─────────────────────────────────────────────────────────┘
```

### Feature Dimensions (MAP-Elites)

OpenEvolve maintains diverse solutions across:

1. **extraction_quality** - F1 score (precision × recall)
2. **token_efficiency** - Entities extracted per token
3. **latency** - Inference time

This means you get not just the "best" prompt, but a population of specialized prompts:
- High F1, higher cost (for critical extraction)
- Medium F1, very fast (for bulk processing)
- High recall, lower precision (for broad coverage)

## Cost Estimation

| Model | Cost per Iteration | 100 Iterations |
|-------|-------------------|----------------|
| gemini-2.5-flash | ~$0.01-0.05 | ~$1-5 |
| gemini-2.5-pro | ~$0.08-0.30 | ~$8-30 |
| gpt-4o-mini | ~$0.02-0.08 | ~$2-8 |
| Local (Ollama) | ~$0 | ~$0 |

## File Structure

```
examples/openevolve/
├── README.md              # This file
├── config.yaml            # Default configuration
├── run_evolution.py       # Main runner script
└── openevolve_workspace/  # Generated workspace
    ├── seeds/             # Initial prompt templates
    ├── config.yaml        # Active config
    ├── training_data/     # Test data
    └── <task>/            # Evolution output per task
        └── output/
            └── checkpoints/

graphiti_core/dspy/openevolve/
├── __init__.py            # Module exports
├── evaluators.py          # Evaluation functions
├── prompts.py             # Prompt templates
└── runner.py              # Evolution runner
```

## Troubleshooting

### "OpenEvolve not installed"
```bash
pip install openevolve
```

### "No training data found"
Run the DSPy pipeline first to collect examples:
```python
from graphiti_core.dspy import DSPyIngestionPipeline
pipeline = DSPyIngestionPipeline()
# Ingest some episodes...
```

### "API key not set"
```bash
# For Gemini
export OPENAI_API_KEY="your-gemini-key"

# Or Google-specific
export GOOGLE_API_KEY="your-key"
```

### Evolution is slow
- Reduce `population_size` in config
- Use `gemini-2.5-flash` instead of `pro`
- Reduce `num_islands` to 1-2
- Enable `cascade_evaluation` for faster initial filtering

## Advanced Usage

### Programmatic API

```python
from graphiti_core.dspy.openevolve import (
    OpenEvolveRunner,
    EvolutionConfig,
    run_prompt_evolution,
)

# Custom configuration
config = EvolutionConfig(
    max_iterations=200,
    population_size=200,
    num_islands=5,
    llm_model='gemini-2.5-pro',  # Use best model
)

# Run evolution
runner = OpenEvolveRunner(config=config)
result = runner.evolve('entity_extraction', iterations=200)

# Check results
print(f"Best F1: {result.best_score}")
print(f"Best prompt: {result.best_program_path}")
```

### Combine with MIPROv2

Use OpenEvolve to find novel prompt structures, then MIPROv2 to optimize:

```python
from graphiti_core.dspy.openevolve import OpenEvolveRunner
from graphiti_core.dspy.optimization import DSPyOptimizer

# Step 1: Evolve prompt structure
runner = OpenEvolveRunner()
evolved = runner.evolve('entity_extraction', iterations=100)

# Step 2: Fine-tune with MIPROv2
optimizer = DSPyOptimizer()
optimized = optimizer.optimize_entity_extraction(min_examples=50)

# Result: Novel structure + optimized examples
```

## References

- [OpenEvolve GitHub](https://github.com/algorithmicsuperintelligence/openevolve)
- [DSPy Documentation](https://dspy-docs.vercel.app/)
- [Graphiti Documentation](https://github.com/getzep/graphiti)
- [MAP-Elites Paper](https://arxiv.org/abs/1504.04909)
