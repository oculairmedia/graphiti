# Prompt Analysis Infrastructure

Comprehensive testing and optimization framework for Graphiti ingestion prompts.

## Overview

This toolkit captures real LLM prompts during ingestion, replays them with different configurations, and provides detailed analysis to inform prompt optimization decisions.

## Components

### 1. `capture_prompts.py` - Prompt Capture Tool

Monkey patches LLM client to intercept and log all prompts with metadata.

**Usage:**
```bash
# Capture prompts from 10 episodes
python capture_prompts.py --samples 10 --output-dir ./prompt_captures

# Capture with custom configuration
FALKORDB_HOST=localhost FALKORDB_PORT=6379 \
python capture_prompts.py --samples 50
```

**Output:**
- `prompts_{timestamp}.jsonl` - Captured prompts with metadata
- `summary_{timestamp}.json` - Summary statistics

**Captured data:**
- Prompt type (extract_nodes, extract_edges, dedupe_nodes, etc.)
- Full message content
- Token count (estimated)
- Latency
- Timestamp

### 2. `replay_prompts.py` - Prompt Replay Harness

Replays captured prompts with different configurations to test optimizations.

**Usage:**
```bash
# Replay with multiple configurations
python replay_prompts.py \
  --input ./prompt_captures/prompts_20250123.jsonl \
  --max-samples 10 \
  --output-dir ./replay_results
```

**Configurations tested:**
- **baseline**: Original prompts unmodified
- **trim_prev_episodes_5**: Limit previous episodes to last 5
- **trim_prev_episodes_3**: Limit previous episodes to last 3  
- **trim_existing_nodes_20**: Limit dedupe candidates to 20

**Output:**
- `replay_results_{timestamp}.jsonl` - Individual replay results
- `comparison_report_{timestamp}.json` - Configuration comparison

### 3. `analyze_results.py` - Results Analysis Tool

Generates comprehensive analysis of captured and replayed prompts.

**Usage:**
```bash
# Analyze captures
python analyze_results.py \
  --captures ./prompt_captures/prompts_20250123.jsonl \
  --output-dir ./analysis_output
```

**Output:**
- Console report with statistics by prompt type
- `analysis_report.json` - Detailed breakdown

## Workflow

### Step 1: Capture Real Prompts

```bash
cd /opt/stacks/graphiti/scripts/prompt_analysis

# Capture from live database
python capture_prompts.py --samples 20
```

### Step 2: Analyze Baseline

```bash
# View current prompt characteristics
python analyze_results.py \
  --captures ./prompt_captures/prompts_*.jsonl
```

### Step 3: Replay with Optimizations

```bash
# Test different configurations
python replay_prompts.py \
  --input ./prompt_captures/prompts_*.jsonl \
  --max-samples 10
```

### Step 4: Compare Results

Review the comparison report to identify:
- Token savings per configuration
- Latency impact
- Success rates
- Best configuration by prompt type

## Example Output

```
PROMPT CAPTURE SUMMARY
============================================================
Total captures: 45
Total tokens: 125,430
Total latency: 15,230ms

By prompt type:
------------------------------------------------------------

extract_nodes:
  Count: 20
  Avg tokens: 3,245
  Token range: 1,200-8,500
  Avg latency: 450ms

dedupe_nodes:
  Count: 15
  Avg tokens: 5,120
  Token range: 2,800-12,000
  Avg latency: 650ms

extract_edges:
  Count: 10
  Avg tokens: 2,890
  Token range: 1,500-6,200
  Avg latency: 420ms
============================================================
```

## Integration with Development

### Add to CI/CD

```bash
# Run prompt capture in CI
python scripts/prompt_analysis/capture_prompts.py \
  --samples 5 \
  --output-dir test_results/prompts

# Analyze for regressions
python scripts/prompt_analysis/analyze_results.py \
  --captures test_results/prompts/prompts_*.jsonl
```

### Performance Monitoring

Schedule periodic captures to track prompt growth over time:

```bash
# Daily capture
0 2 * * * cd /opt/stacks/graphiti && \
  python scripts/prompt_analysis/capture_prompts.py --samples 50
```

## Customization

### Adding New Configurations

Edit `replay_prompts.py` to add custom configurations:

```python
configs = [
    ReplayConfig(
        name="aggressive_trim",
        description="Minimal context for testing",
        previous_episodes_limit=1,
        existing_nodes_limit=10
    ),
    # Add more...
]
```

### Capturing from Different Sources

Modify `capture_prompts.py` to sample from:
- Specific group_ids
- Specific time ranges
- Specific episode types

## Troubleshooting

**No captures generated:**
- Check FalkorDB connection (FALKORDB_HOST, FALKORDB_PORT)
- Ensure episodes exist in database
- Verify LLM client is configured

**Type errors during replay:**
- Message objects must have `.role` and `.content` attributes
- Ensure LLM client supports the response_model parameter

**High memory usage:**
- Reduce `--samples` parameter
- Process captures in smaller batches

## Next Steps

1. **Implement Recommendations**: Apply optimal configurations to production code
2. **Add Compression**: Integrate prompt compression library
3. **Monitor Production**: Set up continuous prompt monitoring
4. **Expand Coverage**: Add edge-specific optimizations

## See Also

- `docs/DRY_RUN_BENCHMARKING_GUIDE.md` - Performance testing
- `graphiti_core/prompts/` - Prompt templates
- `graphiti_core/utils/prompt_compression.py` - Compression utilities
