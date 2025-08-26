# Dry-Run Benchmarking Guide

This guide covers the comprehensive dry-run benchmarking system for Graphiti, enabling safe performance testing and hyperparameter tuning without affecting production data.

## Overview

The dry-run benchmarking system creates a shadow of the ingestion pipeline that queries the real database but intercepts all write operations, allowing you to:

- Benchmark endpoint performance with real data
- Tune hyperparameters systematically
- Compare database backends (Neo4j vs FalkorDB)
- Profile memory usage and processing bottlenecks
- Export detailed metrics for analysis

## Quick Start

### Basic Benchmark

Run a simple benchmark with 50 episodes using FalkorDB:

```bash
python3 cli/benchmark.py run --episodes-limit 50 --database-type falkor
```

### Hyperparameter Tuning

Test different temperature and token limit combinations:

```bash
python3 cli/benchmark.py tune \
  --temperature 0.0 --temperature 0.3 --temperature 0.7 \
  --max-tokens 1000 --max-tokens 2000 \
  --episodes-limit 20
```

### Backend Comparison

Compare Neo4j vs FalkorDB performance:

```bash
python3 cli/benchmark.py compare --episodes-limit 100
```

## Architecture

### Core Components

1. **DryRunDriver**: Wraps existing database drivers to intercept write operations
2. **DryRunWorker**: Orchestrates episode processing and metrics collection
3. **MetricsCollector**: Real-time collection of performance metrics
4. **BenchmarkMetrics**: Aggregated results and statistics
5. **CLI Interface**: Command-line tools for running benchmarks

### Safety Features

- **Write Interception**: All CREATE, MERGE, SET, DELETE operations are blocked
- **Read-Only Access**: Full access to production data for realistic benchmarking
- **Runtime Limits**: Configurable episode and time limits prevent runaway processes
- **Validation**: Configuration validation ensures safe execution

## Configuration

### DryRunConfig

```python
from graphiti_core.benchmarking import DryRunConfig, SafetyConfig

config = DryRunConfig(
    run_id="my_benchmark",
    description="Testing new hyperparameters",
    episodes_limit=100,
    batch_size=10,
    max_concurrent_episodes=3,
    output_dir=Path("./results"),
    export_formats=["json", "csv"],
    enable_profiling=True,
    collect_memory_stats=True,
    hyperparameters={
        'temperature': 0.3,
        'max_tokens': 2000,
        'search_limit': 20
    }
)
```

### Safety Configuration

```python
safety = SafetyConfig(
    require_explicit_dry_run=True,
    max_episodes_per_run=1000,
    max_runtime_minutes=60,
    allowed_databases=['neo4j', 'default_db'],
    forbidden_query_patterns=[
        r'DROP\\s+DATABASE',
        r'DELETE\\s+.*\\s+WHERE\\s+.*\\s+IS\\s+NOT\\s+NULL'
    ]
)
```

## Programming Interface

### Python API

```python
import asyncio
from graphiti_core.graphiti import Graphiti
from graphiti_core.driver.falkordb_driver import FalkorDriver
from graphiti_core.benchmarking import DryRunConfig, DryRunWorker

async def run_benchmark():
    # Create Graphiti instance
    driver = FalkorDriver(host='localhost', port=6389)
    graphiti = Graphiti(driver=driver, llm_client=llm_client, embedder=embedder)
    
    # Configure benchmark
    config = DryRunConfig(
        episodes_limit=50,
        batch_size=5,
        enable_profiling=True
    )
    
    # Run benchmark
    worker = DryRunWorker(graphiti, config)
    try:
        results = await worker.run_benchmark()
        
        # Access results
        summary = results.get_summary_stats()
        print(f"Success rate: {summary['success_rate']*100:.1f}%")
        print(f"Avg duration: {summary['avg_episode_duration_ms']:.1f}ms")
        
    finally:
        await worker.close()
        await graphiti.close()

asyncio.run(run_benchmark())
```

### Example Scripts

The repository includes comprehensive examples:

- `examples/dry_run_benchmark.py`: Complete examples for all benchmark types
- `cli/benchmark.py`: Command-line interface for all operations
- `cli/commands/benchmark.py`: Implementation of CLI commands

## Hyperparameter Tuning

### Supported Parameters

The system supports tuning various hyperparameters:

```python
from graphiti_core.benchmarking import HyperparameterSpace

param_space = HyperparameterSpace(
    # LLM parameters
    temperature=[0.0, 0.3, 0.7],
    max_tokens=[1000, 2000, 4000],
    
    # Entity extraction
    max_entities_per_episode=[10, 20, 50],
    entity_similarity_threshold=[0.7, 0.8, 0.9],
    
    # Search parameters
    search_limit=[10, 20, 50],
    embedding_similarity_threshold=[0.6, 0.7, 0.8],
    
    # Deduplication
    dedup_similarity_threshold=[0.85, 0.9, 0.95]
)

# Generate all combinations
combinations = param_space.get_parameter_combinations()
print(f"Testing {len(combinations)} combinations")
```

### Tuning Workflow

1. **Define Parameter Space**: Specify ranges for each hyperparameter
2. **Run Grid Search**: Test all parameter combinations
3. **Analyze Results**: Compare performance metrics
4. **Select Optimal**: Choose best performing configuration
5. **Apply to Production**: Update production settings

## Metrics and Analysis

### Episode-Level Metrics

Each episode generates detailed metrics:

```python
class EpisodeMetrics:
    episode_id: str
    total_duration_ms: float
    entity_extraction_time_ms: float
    edge_extraction_time_ms: float
    deduplication_time_ms: float
    entities_created: int
    edges_created: int
    llm_calls: int
    embedding_calls: int
    memory_used_mb: float
    errors: List[str]
```

### Aggregated Statistics

Benchmark runs provide summary statistics:

```python
summary = results.get_summary_stats()
# Returns:
{
    'total_episodes': 100,
    'success_rate': 0.98,
    'avg_episode_duration_ms': 1234.5,
    'min_episode_duration_ms': 567.2,
    'max_episode_duration_ms': 3456.7,
    'episodes_per_second': 2.34,
    'total_entities_created': 456,
    'total_edges_created': 789
}
```

### Export Formats

Results are exported in multiple formats:

- **JSON**: Complete metrics and configuration
- **CSV**: Episode-level data for spreadsheet analysis
- **HTML**: Performance profiles when profiling is enabled

## Performance Profiling

### CPU Profiling

Enable detailed CPU profiling with pyinstrument:

```python
config = DryRunConfig(
    enable_profiling=True,
    # ... other options
)
```

This generates interactive HTML reports showing:
- Function call hierarchy
- Time spent in each function
- Bottleneck identification
- Memory allocation patterns

### Memory Monitoring

Track memory usage throughout processing:

```python
config = DryRunConfig(
    collect_memory_stats=True,
    # ... other options
)
```

Provides:
- Peak memory usage per episode
- Memory growth patterns
- Garbage collection impact

## Database Backend Comparison

Compare performance between Neo4j and FalkorDB:

### Automatic Comparison

```bash
python3 cli/benchmark.py compare \
  --episodes-limit 100 \
  --include-neo4j \
  --include-falkor
```

### Manual Configuration

```python
# Test Neo4j
neo4j_driver = Neo4jDriver(uri='bolt://localhost:7687')
neo4j_graphiti = Graphiti(driver=neo4j_driver, ...)

# Test FalkorDB
falkor_driver = FalkorDriver(host='localhost', port=6389)
falkor_graphiti = Graphiti(driver=falkor_driver, ...)

# Run identical benchmarks on both
```

## Best Practices

### Configuration

1. **Start Small**: Begin with small episode limits (10-50) for initial testing
2. **Gradual Scaling**: Increase episode counts as you validate functionality
3. **Batch Sizing**: Use appropriate batch sizes based on available memory
4. **Concurrent Limits**: Balance parallelism with system resources

### Hyperparameter Tuning

1. **Focused Search**: Start with key parameters that most impact your use case
2. **Iterative Refinement**: Use coarse-grained search first, then fine-tune
3. **Statistical Significance**: Run multiple iterations for statistical confidence
4. **Domain-Specific**: Choose parameter ranges relevant to your data domain

### Safety

1. **Verify Dry-Run**: Always confirm no writes reach production database
2. **Monitor Resources**: Watch CPU, memory, and disk usage during runs
3. **Time Limits**: Set reasonable runtime limits to prevent runaway processes
4. **Backup Database**: Ensure backups are current before running benchmarks

## Troubleshooting

### Common Issues

**Import Errors**
```bash
# Missing optional dependencies
pip install psutil pyinstrument
```

**Connection Failures**
```bash
# Verify database connectivity
python3 -c "from graphiti_core.driver.falkordb_driver import FalkorDriver; d = FalkorDriver(); print('OK')"
```

**Memory Issues**
- Reduce batch_size and max_concurrent_episodes
- Enable garbage collection monitoring
- Check available system memory

**Performance Issues**
- Use smaller episode limits for testing
- Profile with smaller datasets first
- Consider database query optimization

### Debugging

Enable verbose logging for detailed information:

```bash
python3 cli/benchmark.py run -v --episodes-limit 10
```

Check configuration validation:

```python
config = DryRunConfig(...)
errors = config.validate()
if errors:
    print("Configuration errors:", errors)
```

## Future Enhancements

Planned improvements include:

1. **Distributed Benchmarking**: Multi-node parallel execution
2. **ML-Guided Tuning**: Bayesian optimization for hyperparameter search
3. **Real-time Monitoring**: Live dashboard for long-running benchmarks
4. **Custom Metrics**: User-defined performance indicators
5. **A/B Testing**: Statistical comparison of configuration variants

## Contributing

The benchmarking system is designed to be extensible:

- Add new hyperparameters in `HyperparameterSpace`
- Extend metrics collection in `MetricsCollector`
- Create custom export formats in `DryRunWorker`
- Add new CLI commands in `cli/commands/benchmark.py`

See the main project contributing guidelines for development setup and submission process.