# Node Deduplication Model Evaluation Report

## Executive Summary

We evaluated 5 different LLM models on the node deduplication task, a critical component of Graphiti's knowledge graph construction pipeline. The current model (qwen3-30b-a3b:iq4_nl) achieves 79.2% accuracy, but we found that gemma3:12b performs significantly better at 87.5% accuracy.

## Task Description

The node deduplication task requires the LLM to:
1. Compare newly extracted entities with existing entities in the database
2. Identify which new entities are duplicates of existing ones
3. Return correct array indices for matches (or -1 for new entities)
4. Handle name variations, abbreviations, and entity type constraints

## Model Performance Results

| Model | Accuracy (JSON Mode) | Bounds Errors | Key Strengths | Key Weaknesses |
|-------|---------------------|---------------|---------------|----------------|
| **gemma3:12b** | **87.5%** ✅ | 0 | Excellent at name variations, reliable JSON output | Missed one edge case |
| qwen3-30b-a3b:iq4_nl | 79.2% | 0 | Decent overall performance, current model | Inconsistent with complex name variations |
| mistral:7b | 58.3% | 0 | Good JSON compliance | Poor at recognizing name variations |
| granite3.3:8b | 54.2% | 0 | Follows format correctly | Too conservative, misses obvious matches |
| phi4-mini-reasoning | 25.0% | 0 | Only succeeded at obvious non-matches | Failed basic entity matching |

## Detailed Test Case Performance

### Test 1: Basic Name Variations
- Tests: "Bob Smith" = "Bob S.", "NYC" = "New York City"
- Best: gemma3, mistral (100%)
- Worst: phi4-mini (0%)

### Test 2: Overlapping Duplicates  
- Tests: Multiple variations of same name (Robert/Bob/R. Smith)
- Best: gemma3 (100%)
- Worst: granite, mistral, phi4-mini (0-33%)

### Test 3: No Duplicates
- Tests: Correctly identifying truly new entities
- All models: 100% (easiest test case)

### Test 4: Edge Cases
- Tests: Generic names, type constraints
- All models struggled (0-50% accuracy)

## Key Findings

1. **gemma3:12b is the clear winner** with 87.5% accuracy, an 8.3% improvement over the current model
2. **JSON mode is essential** - it provides better reliability than regular prompting
3. **Bounds checking is necessary** - Even though no models produced out-of-bounds errors in JSON mode, the protection is still valuable
4. **Model size doesn't guarantee performance** - phi4-mini-reasoning performed worst despite being a "reasoning" model
5. **Name variation recognition is the key differentiator** - Models that understood "Bob" = "Robert" performed best

## Recommendations

1. **Switch to gemma3:12b for the deduplication task** - 87.5% accuracy is a significant improvement
2. **Always use JSON mode** (`format: "json"`) for structured output tasks
3. **Keep the bounds checking code** as a safety measure
4. **Consider fine-tuning** a model specifically for entity matching to achieve >95% accuracy

## Cost-Benefit Analysis

- gemma3:12b (12B parameters) vs qwen3-30b-a3b (30B quantized)
- Likely faster inference with smaller model
- Better accuracy (87.5% vs 79.2%)
- More reliable entity matching reduces downstream errors in the knowledge graph

## Future Improvements

1. Create a larger test dataset with more edge cases
2. Test more models (Claude, GPT-4, specialized NER models)
3. Consider ensemble approaches for critical deduplication decisions
4. Implement confidence scoring to flag uncertain matches for human review