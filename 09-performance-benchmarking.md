# FalkorDB Persistence Performance Benchmarking

## Overview

This guide provides comprehensive benchmarking methodologies for evaluating FalkorDB persistence performance across different configurations, helping optimize settings for specific workloads and requirements.

> Graphiti context: Benchmark against Graphiti’s real workloads:
> - Ingestion (episodes/entities/relations) with backfill bursts
> - Query patterns from Graphiti API and search service
> - Recovery time after controlled restarts.
> Use these results to set RPO/RTO targets and to size FalkorDB resources in Graphiti.


## Benchmarking Framework

### 1. Test Environment Setup

#### Hardware Requirements
```bash
# Minimum recommended test environment
CPU: 8 cores (Intel Xeon or AMD EPYC)
Memory: 32GB RAM
Storage: NVMe SSD with 1000+ IOPS
Network: 1Gbps+ for distributed tests

# Optimal test environment
CPU: 16+ cores
Memory: 64GB+ RAM
Storage: High-performance NVMe SSD (3000+ IOPS)
Network: 10Gbps for cluster tests
```

#### Software Environment
```bash
# Install benchmarking tools
sudo apt-get update
sudo apt-get install -y redis-tools python3-pip htop iotop sysstat

# Install Python dependencies for custom benchmarks
pip3 install redis matplotlib numpy pandas

# Install FalkorDB
docker pull falkordb/falkordb:latest
```

### 2. Baseline Configuration

#### Standard Test Configuration
```redis
# baseline-redis.conf
loadmodule /FalkorDB/bin/src/falkordb.so THREAD_COUNT 8 CACHE_SIZE 100

# Network
bind 0.0.0.0
port 6379
tcp-backlog 511
tcp-keepalive 300

# Memory
maxmemory 16gb
maxmemory-policy allkeys-lru

# Persistence - Baseline (AOF only)
appendonly yes
appendfsync everysec
auto-aof-rewrite-percentage 100
auto-aof-rewrite-min-size 64mb

# Disable RDB for baseline
save ""

# Logging
loglevel notice
```

## Performance Test Scenarios

### 1. Write Performance Tests

#### Graph Creation Benchmark
```python
#!/usr/bin/env python3
# graph_write_benchmark.py

import redis
import time
import statistics
import argparse

def benchmark_graph_writes(host='localhost', port=6379, password=None,
                          num_nodes=10000, batch_size=100):
    """Benchmark graph write operations"""

    r = redis.Redis(host=host, port=port, password=password, decode_responses=True)

    # Test configurations
    configs = [
        {'name': 'AOF-everysec', 'appendfsync': 'everysec'},
        {'name': 'AOF-always', 'appendfsync': 'always'},
        {'name': 'AOF-no', 'appendfsync': 'no'},
        {'name': 'RDB-only', 'appendonly': 'no', 'save': '900 1 300 10 60 10000'},
        {'name': 'Hybrid', 'appendonly': 'yes', 'appendfsync': 'everysec', 'save': '900 1 300 10 60 10000'}
    ]

    results = {}

    for config in configs:
        print(f"\nTesting configuration: {config['name']}")

        # Apply configuration
        for key, value in config.items():
            if key != 'name':
                r.config_set(key, value)

        # Clear previous data
        r.flushall()

        # Warm up
        for i in range(100):
            r.execute_command('GRAPH.QUERY', 'benchmark',
                            f'CREATE (:Person {{id: {i}, name: "Person{i}"}})')

        # Benchmark
        start_time = time.time()
        latencies = []

        for batch in range(0, num_nodes, batch_size):
            batch_start = time.time()

            # Create batch of nodes
            query = "CREATE "
            for i in range(batch, min(batch + batch_size, num_nodes)):
                if i > batch:
                    query += ", "
                query += f"(:Person {{id: {i}, name: 'Person{i}', timestamp: timestamp()}})"

            r.execute_command('GRAPH.QUERY', 'benchmark', query)

            batch_latency = time.time() - batch_start
            latencies.append(batch_latency)

        total_time = time.time() - start_time

        results[config['name']] = {
            'total_time': total_time,
            'ops_per_sec': num_nodes / total_time,
            'avg_latency': statistics.mean(latencies),
            'p95_latency': statistics.quantiles(latencies, n=20)[18],  # 95th percentile
            'p99_latency': statistics.quantiles(latencies, n=100)[98]  # 99th percentile
        }

        print(f"  Total time: {total_time:.2f}s")
        print(f"  Ops/sec: {results[config['name']]['ops_per_sec']:.2f}")
        print(f"  Avg latency: {results[config['name']]['avg_latency']:.4f}s")

    return results

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='FalkorDB Write Performance Benchmark')
    parser.add_argument('--host', default='localhost', help='Redis host')
    parser.add_argument('--port', type=int, default=6379, help='Redis port')
    parser.add_argument('--password', help='Redis password')
    parser.add_argument('--nodes', type=int, default=10000, help='Number of nodes to create')
    parser.add_argument('--batch-size', type=int, default=100, help='Batch size for operations')

    args = parser.parse_args()

    results = benchmark_graph_writes(
        host=args.host,
        port=args.port,
        password=args.password,
        num_nodes=args.nodes,
        batch_size=args.batch_size
    )

    # Print summary
    print("\n=== BENCHMARK RESULTS ===")
    print(f"{'Configuration':<15} {'Ops/sec':<10} {'Avg Latency':<12} {'P95 Latency':<12} {'P99 Latency':<12}")
    print("-" * 70)

    for config, metrics in results.items():
        print(f"{config:<15} {metrics['ops_per_sec']:<10.2f} {metrics['avg_latency']:<12.4f} "
              f"{metrics['p95_latency']:<12.4f} {metrics['p99_latency']:<12.4f}")
```

#### Relationship Creation Benchmark
```python
#!/usr/bin/env python3
# relationship_benchmark.py

import redis
import time
import random

def benchmark_relationships(host='localhost', port=6379, password=None,
                          num_nodes=1000, num_relationships=5000):
    """Benchmark relationship creation performance"""

    r = redis.Redis(host=host, port=port, password=password, decode_responses=True)

    # Create nodes first
    print("Creating nodes...")
    for i in range(num_nodes):
        r.execute_command('GRAPH.QUERY', 'reltest',
                        f'CREATE (:Person {{id: {i}, name: "Person{i}"}})')

    # Benchmark relationship creation
    print("Benchmarking relationship creation...")
    start_time = time.time()

    for i in range(num_relationships):
        src = random.randint(0, num_nodes - 1)
        dst = random.randint(0, num_nodes - 1)
        if src != dst:
            r.execute_command('GRAPH.QUERY', 'reltest',
                            f'MATCH (a:Person {{id: {src}}}), (b:Person {{id: {dst}}}) '
                            f'CREATE (a)-[:KNOWS {{since: timestamp()}}]->(b)')

    total_time = time.time() - start_time

    print(f"Created {num_relationships} relationships in {total_time:.2f}s")
    print(f"Relationships/sec: {num_relationships / total_time:.2f}")

    return num_relationships / total_time
```

### 2. Read Performance Tests

#### Query Performance Benchmark
```python
#!/usr/bin/env python3
# query_benchmark.py

import redis
import time
import statistics

def benchmark_queries(host='localhost', port=6379, password=None):
    """Benchmark various query patterns"""

    r = redis.Redis(host=host, port=port, password=password, decode_responses=True)

    queries = [
        {
            'name': 'Simple Node Match',
            'query': 'MATCH (n:Person) RETURN count(n)',
            'iterations': 1000
        },
        {
            'name': 'Property Filter',
            'query': 'MATCH (n:Person) WHERE n.id > 500 RETURN count(n)',
            'iterations': 500
        },
        {
            'name': 'Relationship Traversal',
            'query': 'MATCH (a:Person)-[:KNOWS]->(b:Person) RETURN count(*)',
            'iterations': 100
        },
        {
            'name': 'Path Query',
            'query': 'MATCH path = (a:Person)-[:KNOWS*1..2]->(b:Person) RETURN count(path) LIMIT 1000',
            'iterations': 50
        }
    ]

    results = {}

    for query_test in queries:
        print(f"\nTesting: {query_test['name']}")
        latencies = []

        for i in range(query_test['iterations']):
            start_time = time.time()
            r.execute_command('GRAPH.QUERY', 'benchmark', query_test['query'])
            latency = time.time() - start_time
            latencies.append(latency)

        results[query_test['name']] = {
            'avg_latency': statistics.mean(latencies),
            'p95_latency': statistics.quantiles(latencies, n=20)[18],
            'p99_latency': statistics.quantiles(latencies, n=100)[98],
            'ops_per_sec': 1 / statistics.mean(latencies)
        }

        print(f"  Avg latency: {results[query_test['name']]['avg_latency']:.4f}s")
        print(f"  Ops/sec: {results[query_test['name']]['ops_per_sec']:.2f}")

    return results
```

### 3. Recovery Performance Tests

#### Startup Time Benchmark
```bash
#!/bin/bash
# startup_benchmark.sh

REDIS_PASSWORD="your_password"
DATA_SIZES=("1GB" "5GB" "10GB" "20GB")
PERSISTENCE_TYPES=("RDB" "AOF" "HYBRID")

echo "=== FalkorDB Startup Performance Benchmark ==="

for size in "${DATA_SIZES[@]}"; do
    for persistence in "${PERSISTENCE_TYPES[@]}"; do
        echo "Testing $persistence with $size dataset..."

        # Configure persistence type
        case $persistence in
            "RDB")
                redis-cli -a $REDIS_PASSWORD CONFIG SET appendonly no
                redis-cli -a $REDIS_PASSWORD CONFIG SET save "900 1 300 10 60 10000"
                ;;
            "AOF")
                redis-cli -a $REDIS_PASSWORD CONFIG SET appendonly yes
                redis-cli -a $REDIS_PASSWORD CONFIG SET save ""
                ;;
            "HYBRID")
                redis-cli -a $REDIS_PASSWORD CONFIG SET appendonly yes
                redis-cli -a $REDIS_PASSWORD CONFIG SET save "900 1 300 10 60 10000"
                ;;
        esac

        # Generate test data (implement data generation script)
        python3 generate_test_data.py --size $size

        # Force persistence
        redis-cli -a $REDIS_PASSWORD BGSAVE
        redis-cli -a $REDIS_PASSWORD BGREWRITEAOF

        # Wait for operations to complete
        while [ "$(redis-cli -a $REDIS_PASSWORD INFO persistence | grep -E 'rdb_bgsave_in_progress:1|aof_rewrite_in_progress:1')" ]; do
            sleep 1
        done

        # Restart and measure startup time
        sudo systemctl stop falkordb

        START_TIME=$(date +%s.%N)
        sudo systemctl start falkordb

        # Wait for Redis to be ready
        while ! redis-cli -a $REDIS_PASSWORD ping > /dev/null 2>&1; do
            sleep 0.1
        done

        END_TIME=$(date +%s.%N)
        STARTUP_TIME=$(echo "$END_TIME - $START_TIME" | bc)

        echo "  Startup time: ${STARTUP_TIME}s"

        # Verify data integrity
        RECORD_COUNT=$(redis-cli -a $REDIS_PASSWORD DBSIZE)
        echo "  Records loaded: $RECORD_COUNT"

        echo "  ---"
    done
done
```

## System Resource Monitoring

### 1. Resource Monitoring Script

```bash
#!/bin/bash
# monitor_resources.sh

DURATION=${1:-300}  # Default 5 minutes
INTERVAL=${2:-5}    # Default 5 seconds
OUTPUT_DIR="/tmp/falkordb_benchmark_$(date +%Y%m%d_%H%M%S)"

mkdir -p "$OUTPUT_DIR"

echo "Monitoring system resources for ${DURATION} seconds..."

# CPU monitoring
sar -u $INTERVAL $((DURATION / INTERVAL)) > "$OUTPUT_DIR/cpu.log" &

# Memory monitoring
sar -r $INTERVAL $((DURATION / INTERVAL)) > "$OUTPUT_DIR/memory.log" &

# I/O monitoring
sar -d $INTERVAL $((DURATION / INTERVAL)) > "$OUTPUT_DIR/io.log" &

# Network monitoring
sar -n DEV $INTERVAL $((DURATION / INTERVAL)) > "$OUTPUT_DIR/network.log" &

# Redis-specific monitoring
while [ $DURATION -gt 0 ]; do
    echo "$(date +%s),$(redis-cli -a your_password INFO stats | grep instantaneous_ops_per_sec | cut -d: -f2 | tr -d '\r')" >> "$OUTPUT_DIR/redis_ops.log"
    echo "$(date +%s),$(redis-cli -a your_password INFO memory | grep used_memory | head -1 | cut -d: -f2 | tr -d '\r')" >> "$OUTPUT_DIR/redis_memory.log"
    sleep $INTERVAL
    DURATION=$((DURATION - INTERVAL))
done

echo "Monitoring complete. Results in: $OUTPUT_DIR"
```

### 2. Performance Analysis Script

```python
#!/usr/bin/env python3
# analyze_performance.py

import pandas as pd
import matplotlib.pyplot as plt
import sys
import os

def analyze_benchmark_results(results_dir):
    """Analyze and visualize benchmark results"""

    # Read CPU data
    cpu_data = pd.read_csv(f"{results_dir}/cpu.log", sep='\s+', skiprows=3)

    # Read memory data
    memory_data = pd.read_csv(f"{results_dir}/memory.log", sep='\s+', skiprows=3)

    # Read Redis operations data
    redis_ops = pd.read_csv(f"{results_dir}/redis_ops.log", names=['timestamp', 'ops_per_sec'])

    # Create visualizations
    fig, axes = plt.subplots(2, 2, figsize=(15, 10))

    # CPU utilization
    axes[0, 0].plot(cpu_data['%user'] + cpu_data['%system'])
    axes[0, 0].set_title('CPU Utilization (%)')
    axes[0, 0].set_ylabel('CPU %')

    # Memory usage
    axes[0, 1].plot(memory_data['%memused'])
    axes[0, 1].set_title('Memory Utilization (%)')
    axes[0, 1].set_ylabel('Memory %')

    # Redis operations per second
    axes[1, 0].plot(redis_ops['ops_per_sec'])
    axes[1, 0].set_title('Redis Operations per Second')
    axes[1, 0].set_ylabel('Ops/sec')

    # I/O wait
    axes[1, 1].plot(cpu_data['%iowait'])
    axes[1, 1].set_title('I/O Wait (%)')
    axes[1, 1].set_ylabel('I/O Wait %')

    plt.tight_layout()
    plt.savefig(f"{results_dir}/performance_analysis.png")
    plt.show()

    # Generate summary statistics
    summary = {
        'avg_cpu_usage': (cpu_data['%user'] + cpu_data['%system']).mean(),
        'max_cpu_usage': (cpu_data['%user'] + cpu_data['%system']).max(),
        'avg_memory_usage': memory_data['%memused'].mean(),
        'max_memory_usage': memory_data['%memused'].max(),
        'avg_ops_per_sec': redis_ops['ops_per_sec'].mean(),
        'max_ops_per_sec': redis_ops['ops_per_sec'].max(),
        'avg_iowait': cpu_data['%iowait'].mean(),
        'max_iowait': cpu_data['%iowait'].max()
    }

    print("=== Performance Summary ===")
    for metric, value in summary.items():
        print(f"{metric}: {value:.2f}")

    return summary

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 analyze_performance.py <results_directory>")
        sys.exit(1)

    results_dir = sys.argv[1]
    if not os.path.exists(results_dir):
        print(f"Directory {results_dir} does not exist")
        sys.exit(1)

    analyze_benchmark_results(results_dir)
```

## Benchmark Execution Framework

### Complete Benchmark Suite

```bash
#!/bin/bash
# run_complete_benchmark.sh

REDIS_PASSWORD="your_password"
BENCHMARK_DIR="/tmp/falkordb_benchmark_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BENCHMARK_DIR"

echo "=== FalkorDB Complete Performance Benchmark ===" | tee "$BENCHMARK_DIR/benchmark.log"
echo "Start time: $(date)" | tee -a "$BENCHMARK_DIR/benchmark.log"

# Test configurations
CONFIGS=(
    "AOF_EVERYSEC:appendonly=yes,appendfsync=everysec,save="
    "AOF_ALWAYS:appendonly=yes,appendfsync=always,save="
    "RDB_ONLY:appendonly=no,save=900 1 300 10 60 10000"
    "HYBRID:appendonly=yes,appendfsync=everysec,save=900 1 300 10 60 10000"
)

for config in "${CONFIGS[@]}"; do
    CONFIG_NAME=$(echo $config | cut -d: -f1)
    CONFIG_PARAMS=$(echo $config | cut -d: -f2)

    echo "Testing configuration: $CONFIG_NAME" | tee -a "$BENCHMARK_DIR/benchmark.log"

    # Apply configuration
    IFS=',' read -ra PARAMS <<< "$CONFIG_PARAMS"
    for param in "${PARAMS[@]}"; do
        if [ -n "$param" ]; then
            KEY=$(echo $param | cut -d= -f1)
            VALUE=$(echo $param | cut -d= -f2-)
            redis-cli -a $REDIS_PASSWORD CONFIG SET $KEY "$VALUE"
        fi
    done

    # Clear data
    redis-cli -a $REDIS_PASSWORD FLUSHALL

    # Start resource monitoring
    ./monitor_resources.sh 300 5 &
    MONITOR_PID=$!

    # Run write benchmark
    echo "  Running write benchmark..." | tee -a "$BENCHMARK_DIR/benchmark.log"
    python3 graph_write_benchmark.py --password $REDIS_PASSWORD --nodes 10000 > "$BENCHMARK_DIR/${CONFIG_NAME}_write.log"

    # Run read benchmark
    echo "  Running read benchmark..." | tee -a "$BENCHMARK_DIR/benchmark.log"
    python3 query_benchmark.py --password $REDIS_PASSWORD > "$BENCHMARK_DIR/${CONFIG_NAME}_read.log"

    # Stop monitoring
    kill $MONITOR_PID 2>/dev/null

    # Force persistence and measure
    echo "  Testing persistence performance..." | tee -a "$BENCHMARK_DIR/benchmark.log"
    START_TIME=$(date +%s.%N)
    redis-cli -a $REDIS_PASSWORD BGSAVE
    redis-cli -a $REDIS_PASSWORD BGREWRITEAOF

    # Wait for completion
    while [ "$(redis-cli -a $REDIS_PASSWORD INFO persistence | grep -E 'rdb_bgsave_in_progress:1|aof_rewrite_in_progress:1')" ]; do
        sleep 1
    done

    END_TIME=$(date +%s.%N)
    PERSISTENCE_TIME=$(echo "$END_TIME - $START_TIME" | bc)
    echo "  Persistence time: ${PERSISTENCE_TIME}s" | tee -a "$BENCHMARK_DIR/benchmark.log"

    echo "  Configuration $CONFIG_NAME completed" | tee -a "$BENCHMARK_DIR/benchmark.log"
    echo "  ---" | tee -a "$BENCHMARK_DIR/benchmark.log"
done

echo "Benchmark completed. Results in: $BENCHMARK_DIR" | tee -a "$BENCHMARK_DIR/benchmark.log"
echo "End time: $(date)" | tee -a "$BENCHMARK_DIR/benchmark.log"

# Generate summary report
python3 generate_benchmark_report.py "$BENCHMARK_DIR"
```

## Performance Optimization Guidelines

### Configuration Recommendations by Workload

#### High-Write Workloads
```redis
# Optimized for write-heavy workloads
appendonly yes
appendfsync everysec
no-appendfsync-on-rewrite yes
auto-aof-rewrite-percentage 200
auto-aof-rewrite-min-size 128mb

# Less frequent RDB snapshots
save 1800 1
save 600 100

# FalkorDB optimization
THREAD_COUNT 8
CACHE_SIZE 50  # Smaller cache for write workloads
```

#### High-Read Workloads
```redis
# Optimized for read-heavy workloads
appendonly yes
appendfsync everysec
auto-aof-rewrite-percentage 100
auto-aof-rewrite-min-size 64mb

# More frequent RDB snapshots for faster recovery
save 900 1
save 300 10
save 60 1000

# FalkorDB optimization
THREAD_COUNT 8
CACHE_SIZE 500  # Larger cache for read workloads
TIMEOUT_DEFAULT 30000
```

#### Balanced Workloads
```redis
# Balanced configuration (recommended default)
appendonly yes
appendfsync everysec
auto-aof-rewrite-percentage 100
auto-aof-rewrite-min-size 64mb

save 900 1
save 300 10
save 60 10000

# FalkorDB optimization
THREAD_COUNT 8
CACHE_SIZE 200
TIMEOUT_DEFAULT 30000
QUERY_MEM_CAPACITY 1073741824  # 1GB per query
```

---

**Next**: See [10-production-deployment.md](10-production-deployment.md) for production deployment considerations.
