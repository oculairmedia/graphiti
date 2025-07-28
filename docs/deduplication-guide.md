# Entity Deduplication Guide

## Overview

The `maintenance_dedupe_entities.py` script provides intelligent deduplication of entities in the Graphiti knowledge graph. It identifies and merges duplicate entities while preserving distinct entities that may share similar names.

## Key Features

### 1. Smart Name Matching
- **Exact matching after normalization**: Handles case variations, underscores, and common suffixes
- **Compound name detection**: Preserves entities like "Claude" vs "Claude Code" as separate
- **No substring matching**: Prevents overly aggressive merging

### 2. Confidence-Based Merging
- **High thresholds**: 92% for embeddings, 95% for names
- **Auto-merge for high confidence**: Skips expensive LLM calls when confidence is very high
- **LLM fallback**: Uses AI for ambiguous cases

### 3. Performance Optimizations
- **Batch processing**: Handles large datasets efficiently
- **Progress tracking**: Shows estimated time remaining
- **Configurable model**: Can use different LLM models for speed/accuracy tradeoff

## Usage

### Basic Usage

```bash
cd /opt/stacks/graphiti
python3 maintenance_dedupe_entities.py
```

### Configuration

The script uses environment variables from `.env`:
- `OLLAMA_BASE_URL`: LLM server URL
- `OLLAMA_MODEL`: Model to use (default: qwen3:30b for performance)

### Parameters (in code)

```python
# In main() function:
deduplicator.run_deduplication(
    group_id="claude_conversations",  # Optional: filter by group
    dry_run=True,                     # Test mode first
    batch_size=10,                    # Process in batches
    max_groups=None                   # Limit groups for testing
)
```

## Deduplication Logic

### 1. Name Normalization
```python
def _normalize_name(self, name: str) -> str:
    # Convert to lowercase
    # Replace underscores with spaces
    # Remove suffixes: (system), (user), (bot), (ai)
    # Remove special characters
    # Normalize whitespace
```

### 2. Similarity Detection
```python
def _are_names_similar(self, name1: str, name2: str, threshold: float) -> bool:
    # Exact match after normalization → merge
    # Compound name detected → DON'T merge
    # Multi-word overlap >= 95% → merge
```

### 3. Compound Name Detection
```python
def _is_compound_name(self, name1: str, name2: str) -> bool:
    # "Claude" vs "Claude Code" → True (don't merge)
    # "GitHub" vs "GitHub Actions" → True (don't merge)
    # "User" vs "User (system)" → False (merge after normalization)
```

### 4. Auto-Merge Logic
- **Large groups (>50 entities)**: Need 95% exact matches
- **Small groups**: ALL must be exactly the same
- **Embedding check**: If available, requires high similarity

## Examples

### Will Merge
- `Claude`, `claude`, `CLAUDE` → Single "Claude" entity
- `User (system)`, `User`, `user` → Single "User" entity
- `claude_code`, `Claude Code` → Single "Claude Code" entity

### Won't Merge
- `Claude` and `Claude Code` → Kept as separate entities
- `GitHub` and `GitHub Actions` → Kept as separate entities
- `React` and `React Native` → Kept as separate entities

## Performance

### Optimization Tips
1. **Use smaller models**: qwen3:30b is ~52% faster than qwen3:32b
2. **Run in batches**: Default batch_size=10 works well
3. **Dry run first**: Always test with dry_run=True
4. **Filter by group**: Process specific groups if possible

### Typical Performance
- **Small dataset (<100 entities)**: ~10 seconds
- **Medium dataset (100-1000 entities)**: 1-5 minutes
- **Large dataset (1000+ entities)**: 5-15 minutes

## Safety Features

1. **Dry run mode**: Test without making changes
2. **Progress tracking**: Know how long it will take
3. **UUID mapping**: Track all merges for auditing
4. **Edge preservation**: Automatically updates relationships

## Troubleshooting

### Common Issues

1. **Ollama server overload**
   ```bash
   # Restart the container
   cd /opt/stacks/graphiti
   docker-compose restart graph
   ```

2. **Too aggressive merging**
   - Increase thresholds in `find_duplicate_candidates()`
   - Add more patterns to `_is_compound_name()`

3. **Not merging obvious duplicates**
   - Check normalization in `_normalize_name()`
   - Lower thresholds slightly (but be careful)

### Monitoring

Check the logs for:
- "Auto-merging N nodes: X% exactly match"
- "Not auto-merging N nodes: only X% exactly match"
- "Processing group X/Y"

## Future Enhancements

1. **Automated scheduling**: Run when entity count exceeds threshold
2. **Incremental deduplication**: Only process new entities
3. **Custom rules**: Entity-type specific deduplication logic
4. **Metrics dashboard**: Track duplicate rates over time