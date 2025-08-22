# Graphiti LLM Prompts - Complete Reference

This document contains all the prompts used to drive Graphiti's knowledge graph construction and maintenance.

## Prompt Library Structure

**File:** `graphiti_core/prompts/lib.py`

The prompt library is organized into these main categories:
- `extract_nodes` - Entity extraction from different content types
- `extract_edges` - Relationship/fact extraction 
- `dedupe_nodes` - Entity deduplication
- `dedupe_edges` - Relationship deduplication
- `summarize_nodes` - Entity summarization
- `invalidate_edges` - Temporal relationship invalidation
- `extract_edge_dates` - Temporal information extraction
- `eval` - Evaluation and testing prompts

## Key Prompt Patterns

### 1. Context Structure
Most prompts follow this pattern:
```
<PREVIOUS MESSAGES>
{previous_episodes}
</PREVIOUS MESSAGES>
<CURRENT MESSAGE>
{episode_content}
</CURRENT MESSAGE>
<ENTITIES/FACTS/etc>
{relevant_data}
</ENTITIES/FACTS/etc>
```

### 2. Guidelines Pattern
Prompts typically include:
- Clear task definition
- Specific extraction rules
- Format requirements
- What NOT to extract
- Output structure specifications

### 3. JSON Schema Integration
Many prompts use Pydantic models for structured output:
- `ExtractedEntities` - For entity extraction
- `ExtractedEdges` - For relationship extraction
- `NodeResolutions` - For deduplication
- `Summary` - For summarization

## Critical Prompts for Token Length Issues

### Most Verbose Prompts:
1. **`extract_attributes`** (nodes) - Includes ALL previous episodes + current episode + entity context
2. **`extract_message`** - Includes previous episodes + current message + entity types
3. **`edge`** (extract_edges) - Includes previous episodes + current message + entities + fact types
4. **`summarize_context`** - Includes previous episodes + current episode + entity context + attributes

### Token-Heavy Elements:
- `{previous_episodes}` - Can be massive for long conversations
- `json.dumps(..., indent=2)` - Verbose JSON formatting
- Complex entity type definitions
- Detailed extraction guidelines
- JSON schema specifications

## Prompt Modifications for Token Efficiency

### Immediate Optimizations:
1. **Limit previous episodes**: Only include last N episodes instead of all
2. **Compact JSON**: Remove `indent=2` from `json.dumps()`
3. **Shorter guidelines**: Condense instruction text
4. **Context windowing**: Implement sliding window for episode history

### Content Truncation:
1. **Episode content limits**: Truncate very long episodes
2. **Summary-based context**: Use summaries instead of full episode content for older episodes
3. **Selective context**: Only include relevant previous episodes based on entity mentions

## Model-Specific Considerations

### For Ollama/Local Models:
- Tend to be more verbose than API models
- May need explicit length constraints in prompts
- Consider adding "Be concise" instructions
- May benefit from examples of desired output length

### For API Models (OpenAI/Anthropic):
- Generally more concise
- Better at following token limits
- Can handle more complex structured output
- More reliable JSON generation

## Prompt Enhancement Strategies

### 1. Progressive Context:
Instead of including all previous episodes, use:
- Recent episodes (last 3-5)
- Relevant episodes (containing mentioned entities)
- Summarized older context

### 2. Chunked Processing:
For large conversations:
- Process in smaller chunks
- Maintain entity/relationship state
- Merge results from chunks

### 3. Adaptive Prompting:
- Adjust prompt complexity based on content size
- Use simpler prompts for large contexts
- Fall back to basic extraction when hitting limits

## Monitoring and Debugging

### Token Usage Tracking:
- Log prompt tokens vs completion tokens
- Track which prompts exceed limits
- Monitor model-specific behavior

### Prompt Performance:
- Measure extraction quality vs prompt length
- A/B test different prompt versions
- Track success rates by prompt type

This comprehensive reference should help understand how Graphiti's prompts work and where optimizations can be made to handle token limits more effectively.
