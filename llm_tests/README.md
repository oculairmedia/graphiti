# LLM Test Scripts for Node Deduplication

This directory contains test scripts to evaluate different LLMs on the node deduplication task used in Graphiti's knowledge graph construction.

## The Deduplication Task

When Graphiti extracts entities from text, it needs to determine if newly extracted entities are duplicates of existing ones in the database. The LLM receives:

1. **Extracted nodes**: New entities found in the text (with indices 0, 1, 2...)
2. **Existing nodes**: Entities already in the database (with indices 0, 1, 2...)

The LLM must return a mapping that says which extracted nodes match which existing nodes, using -1 for new entities.

### Example:
- Extracted: [0: "Bob Smith", 1: "NYC"]  
- Existing: [0: "Bob S.", 1: "New York City", 2: "Alice"]
- Expected: Entity 0 → 0 (Bob Smith matches Bob S.), Entity 1 → 1 (NYC matches New York City)

## Test Scripts

### 1. `test_node_deduplication.py`
Tests models using regular prompt-based approach. The model returns JSON in markdown code blocks.

```bash
TEST_MODEL="qwen3-30b-a3b:iq4_nl" python3 test_node_deduplication.py
```

### 2. `test_dedup_structured_output.py`
Tests models using Ollama's structured output format with Pydantic schemas.

```bash
TEST_MODEL="llama3.2:3b" python3 test_dedup_structured_output.py
```

### 3. `test_dedup_json_mode.py`
Tests models using Ollama's JSON mode (`format: "json"`). More reliable than markdown but less strict than structured output.

```bash
TEST_MODEL="mistral:7b" python3 test_dedup_json_mode.py
```

### 4. `compare_models_dedup.py`
Compares multiple models across different formats.

```bash
python3 compare_models_dedup.py
```

## Key Metrics

- **Accuracy**: Percentage of correct entity mappings
- **Bounds Errors**: When the model returns invalid indices (e.g., index 5 when only 3 nodes exist)

## Current Results

The `qwen3-30b-a3b:iq4_nl` model achieves:
- Regular format: 75% accuracy (some JSON parsing issues)
- JSON mode: 79.2% accuracy (no bounds errors)
- Structured output: Not all models support this

## Common Issues

1. **Bounds Errors**: Models sometimes return indices outside valid ranges
2. **JSON Parsing**: Models may wrap JSON in markdown code blocks
3. **Consistency**: Some models struggle with the "Robert Smith" = "Bob S." type matches

## Recommendations

1. Use JSON mode (`format: "json"`) for better reliability
2. Add bounds checking in production code (as done in `node_operations.py`)
3. Consider fine-tuning a model specifically for this task
4. Test new models before switching to ensure they handle the task correctly

## Model Requirements

A good deduplication model should:
- Follow index constraints strictly (no out-of-bounds errors)
- Recognize name variations and abbreviations
- Consider entity types when matching
- Return valid JSON consistently
- Handle edge cases (no matches, all matches, etc.)