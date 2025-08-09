#!/usr/bin/env python3
"""
Performance comparison script between Python and Rust search implementations.
Tests both services and generates a comprehensive comparison report.
"""

import json
import time
import requests
import statistics
import numpy as np
from datetime import datetime
from typing import Dict, List, Tuple, Any
import concurrent.futures
from colorama import init, Fore, Style
from tabulate import tabulate

# Initialize colorama
init(autoreset=True)

# Configuration
PYTHON_BASE_URL = "http://localhost:8003"  # Python graph service (Docker)
RUST_BASE_URL = "http://localhost:3004"    # Rust search service
HEADERS = {"Content-Type": "application/json"}

# Test configurations
NUM_REQUESTS = 100
NUM_WORKERS = 10
WARMUP_REQUESTS = 10

def print_header(text: str):
    """Print formatted header"""
    print(f"\n{Fore.CYAN}{'='*80}")
    print(f"{Fore.YELLOW}{text:^80}")
    print(f"{Fore.CYAN}{'='*80}")

def print_section(text: str):
    """Print section header"""
    print(f"\n{Fore.GREEN}▶ {text}")
    print(f"{Fore.CYAN}{'-'*60}")

def measure_latency(func, *args, **kwargs) -> Tuple[float, bool, Any]:
    """Measure function execution time"""
    start = time.perf_counter()
    try:
        result = func(*args, **kwargs)
        elapsed = (time.perf_counter() - start) * 1000  # Convert to ms
        success = result.status_code == 200 if hasattr(result, 'status_code') else True
        return elapsed, success, result
    except Exception as e:
        elapsed = (time.perf_counter() - start) * 1000
        return elapsed, False, str(e)

def test_endpoint(base_url: str, endpoint: str, payload: Dict) -> Dict[str, Any]:
    """Test a single endpoint and collect metrics"""
    url = f"{base_url}{endpoint}"
    
    # Warmup
    for _ in range(WARMUP_REQUESTS):
        try:
            requests.post(url, headers=HEADERS, json=payload, timeout=5)
        except:
            pass
    
    # Actual test
    latencies = []
    successes = 0
    failures = 0
    errors = []
    
    def make_request():
        latency, success, result = measure_latency(
            requests.post, url, headers=HEADERS, json=payload, timeout=5
        )
        return latency, success, result
    
    # Sequential requests for accurate latency measurement
    for _ in range(NUM_REQUESTS):
        latency, success, result = make_request()
        if success:
            successes += 1
            latencies.append(latency)
        else:
            failures += 1
            if isinstance(result, str):
                errors.append(result[:50])
    
    # Concurrent requests for throughput measurement
    with concurrent.futures.ThreadPoolExecutor(max_workers=NUM_WORKERS) as executor:
        start_time = time.perf_counter()
        futures = [executor.submit(make_request) for _ in range(NUM_REQUESTS)]
        concurrent_results = [f.result() for f in concurrent.futures.as_completed(futures)]
        total_time = time.perf_counter() - start_time
    
    concurrent_successes = sum(1 for _, success, _ in concurrent_results if success)
    throughput = concurrent_successes / total_time if total_time > 0 else 0
    
    if latencies:
        return {
            "success_rate": (successes / NUM_REQUESTS) * 100,
            "avg_latency": statistics.mean(latencies),
            "median_latency": statistics.median(latencies),
            "min_latency": min(latencies),
            "max_latency": max(latencies),
            "p95_latency": np.percentile(latencies, 95),
            "p99_latency": np.percentile(latencies, 99),
            "std_dev": statistics.stdev(latencies) if len(latencies) > 1 else 0,
            "throughput": throughput,
            "errors": errors[:3]  # First 3 errors
        }
    else:
        return {
            "success_rate": 0,
            "avg_latency": 0,
            "median_latency": 0,
            "min_latency": 0,
            "max_latency": 0,
            "p95_latency": 0,
            "p99_latency": 0,
            "std_dev": 0,
            "throughput": 0,
            "errors": errors[:3]
        }

def test_python_service() -> Dict[str, Dict]:
    """Test Python implementation endpoints"""
    print_section("Testing Python Service")
    
    results = {}
    
    # Test health endpoint
    try:
        response = requests.get(f"{PYTHON_BASE_URL}/healthcheck", timeout=5)
        if response.status_code == 200:
            print(f"{Fore.GREEN}✓ Python service is healthy")
        else:
            print(f"{Fore.RED}✗ Python service health check failed")
            return results
    except Exception as e:
        print(f"{Fore.RED}✗ Python service is not running: {e}")
        return results
    
    # Test search endpoint (if available)
    test_cases = {
        "simple_search": {
            "endpoint": "/search",
            "payload": {
                "query": "Node",
                "limit": 10,
                "search_type": "hybrid"
            }
        },
        "node_search": {
            "endpoint": "/search/nodes", 
            "payload": {
                "query": "Node",
                "limit": 10
            }
        }
    }
    
    for test_name, test_config in test_cases.items():
        print(f"  Testing {test_name}...", end=" ")
        try:
            metrics = test_endpoint(
                PYTHON_BASE_URL,
                test_config["endpoint"],
                test_config["payload"]
            )
            results[test_name] = metrics
            print(f"{Fore.GREEN}✓")
        except Exception as e:
            print(f"{Fore.RED}✗ {str(e)[:50]}")
            results[test_name] = {"error": str(e)}
    
    return results

def test_rust_service() -> Dict[str, Dict]:
    """Test Rust implementation endpoints"""
    print_section("Testing Rust Service")
    
    results = {}
    
    # Test health endpoint
    try:
        response = requests.get(f"{RUST_BASE_URL}/health", timeout=5)
        if response.status_code == 200:
            print(f"{Fore.GREEN}✓ Rust service is healthy")
        else:
            print(f"{Fore.RED}✗ Rust service health check failed")
            return results
    except Exception as e:
        print(f"{Fore.RED}✗ Rust service is not running: {e}")
        return results
    
    # Test search endpoints
    test_cases = {
        "edge_search": {
            "endpoint": "/search/edges",
            "payload": {
                "query": "Node",
                "config": {
                    "search_methods": ["fulltext"],
                    "reranker": "rrf",
                    "bfs_max_depth": 2,
                    "sim_min_score": 0.5,
                    "mmr_lambda": 0.5
                },
                "filters": {}
            }
        },
        "node_search": {
            "endpoint": "/search/nodes",
            "payload": {
                "query": "Node",
                "config": {
                    "search_methods": ["fulltext"],
                    "reranker": "rrf",
                    "bfs_max_depth": 2,
                    "sim_min_score": 0.5,
                    "mmr_lambda": 0.5
                },
                "filters": {}
            }
        },
        "combined_search": {
            "endpoint": "/search",
            "payload": {
                "query": "Node",
                "config": {
                    "edge_config": {
                        "search_methods": ["fulltext"],
                        "reranker": "rrf",
                        "bfs_max_depth": 2,
                        "sim_min_score": 0.5,
                        "mmr_lambda": 0.5
                    },
                    "node_config": {
                        "search_methods": ["fulltext"],
                        "reranker": "rrf",
                        "bfs_max_depth": 2,
                        "sim_min_score": 0.5,
                        "mmr_lambda": 0.5
                    },
                    "limit": 10,
                    "reranker_min_score": 0.0
                },
                "filters": {}
            }
        }
    }
    
    for test_name, test_config in test_cases.items():
        print(f"  Testing {test_name}...", end=" ")
        try:
            metrics = test_endpoint(
                RUST_BASE_URL,
                test_config["endpoint"],
                test_config["payload"]
            )
            results[test_name] = metrics
            print(f"{Fore.GREEN}✓")
        except Exception as e:
            print(f"{Fore.RED}✗ {str(e)[:50]}")
            results[test_name] = {"error": str(e)}
    
    return results

def generate_comparison_table(python_results: Dict, rust_results: Dict) -> str:
    """Generate comparison table"""
    headers = ["Metric", "Python", "Rust", "Improvement"]
    rows = []
    
    # Find common test cases
    common_tests = set(python_results.keys()) & set(rust_results.keys())
    
    for test_name in common_tests:
        if "error" in python_results[test_name] or "error" in rust_results[test_name]:
            continue
            
        py_metrics = python_results[test_name]
        rs_metrics = rust_results[test_name]
        
        metrics_to_compare = [
            ("Success Rate (%)", "success_rate", False),
            ("Avg Latency (ms)", "avg_latency", True),
            ("Median Latency (ms)", "median_latency", True),
            ("P95 Latency (ms)", "p95_latency", True),
            ("P99 Latency (ms)", "p99_latency", True),
            ("Throughput (req/s)", "throughput", False)
        ]
        
        rows.append([f"{Fore.YELLOW}{test_name.upper()}", "", "", ""])
        
        for metric_name, metric_key, lower_is_better in metrics_to_compare:
            py_val = py_metrics.get(metric_key, 0)
            rs_val = rs_metrics.get(metric_key, 0)
            
            if py_val > 0 and rs_val > 0:
                if lower_is_better:
                    improvement = ((py_val - rs_val) / py_val) * 100
                    improvement_str = f"{improvement:.1f}% faster" if improvement > 0 else f"{abs(improvement):.1f}% slower"
                else:
                    improvement = ((rs_val - py_val) / py_val) * 100
                    improvement_str = f"{improvement:.1f}% better" if improvement > 0 else f"{abs(improvement):.1f}% worse"
                
                # Color code the improvement
                if improvement > 0:
                    improvement_str = f"{Fore.GREEN}{improvement_str}"
                else:
                    improvement_str = f"{Fore.RED}{improvement_str}"
            else:
                improvement_str = "N/A"
            
            rows.append([
                f"  {metric_name}",
                f"{py_val:.2f}" if py_val > 0 else "N/A",
                f"{rs_val:.2f}" if rs_val > 0 else "N/A",
                improvement_str
            ])
    
    return tabulate(rows, headers, tablefmt="grid")

def generate_report(python_results: Dict, rust_results: Dict):
    """Generate comprehensive performance report"""
    print_header("PERFORMANCE COMPARISON REPORT")
    print(f"{Fore.BLUE}Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{Fore.BLUE}Test Configuration: {NUM_REQUESTS} requests, {NUM_WORKERS} concurrent workers")
    
    # Summary statistics
    print_section("Executive Summary")
    
    # Calculate average improvements
    improvements = []
    for test_name in set(python_results.keys()) & set(rust_results.keys()):
        if "error" not in python_results[test_name] and "error" not in rust_results[test_name]:
            py_lat = python_results[test_name].get("median_latency", 0)
            rs_lat = rust_results[test_name].get("median_latency", 0)
            if py_lat > 0 and rs_lat > 0:
                improvements.append((py_lat - rs_lat) / py_lat * 100)
    
    if improvements:
        avg_improvement = statistics.mean(improvements)
        print(f"  {Fore.GREEN}Average Latency Improvement: {avg_improvement:.1f}%")
    
    # Rust-specific advantages
    rust_advantages = []
    python_advantages = []
    
    for test_name in set(rust_results.keys()):
        if test_name in python_results:
            if "error" not in rust_results[test_name] and "error" not in python_results[test_name]:
                rs_throughput = rust_results[test_name].get("throughput", 0)
                py_throughput = python_results[test_name].get("throughput", 0)
                if rs_throughput > py_throughput and py_throughput > 0:
                    improvement = (rs_throughput / py_throughput)
                    rust_advantages.append(f"{test_name}: {improvement:.1f}x higher throughput")
                elif py_throughput > rs_throughput and rs_throughput > 0:
                    improvement = (py_throughput / rs_throughput)
                    python_advantages.append(f"{test_name}: {improvement:.1f}x higher throughput")
    
    if rust_advantages:
        print(f"\n  {Fore.GREEN}Rust Advantages:")
        for advantage in rust_advantages:
            print(f"    • {advantage}")
    
    if python_advantages:
        print(f"\n  {Fore.YELLOW}Python Advantages:")
        for advantage in python_advantages:
            print(f"    • {advantage}")
    
    # Detailed comparison table
    print_section("Detailed Performance Metrics")
    
    if python_results and rust_results:
        table = generate_comparison_table(python_results, rust_results)
        print(table)
    elif rust_results:
        print(f"{Fore.YELLOW}Only Rust service results available:")
        for test_name, metrics in rust_results.items():
            if "error" not in metrics:
                print(f"\n  {test_name}:")
                print(f"    • Median Latency: {metrics.get('median_latency', 0):.2f} ms")
                print(f"    • Throughput: {metrics.get('throughput', 0):.2f} req/s")
                print(f"    • Success Rate: {metrics.get('success_rate', 0):.1f}%")
    else:
        print(f"{Fore.RED}No test results available")
    
    # Recommendations
    print_section("Recommendations")
    
    if improvements and avg_improvement > 0:
        print(f"  {Fore.GREEN}✓ Rust implementation shows {avg_improvement:.1f}% average latency improvement")
        print(f"  {Fore.GREEN}✓ Recommended for production use for performance-critical operations")
    
    # Save results to JSON
    results = {
        "timestamp": datetime.now().isoformat(),
        "config": {
            "num_requests": NUM_REQUESTS,
            "num_workers": NUM_WORKERS,
            "warmup_requests": WARMUP_REQUESTS
        },
        "python_results": python_results,
        "rust_results": rust_results
    }
    
    with open("performance_comparison_results.json", "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"\n{Fore.BLUE}Results saved to performance_comparison_results.json")

def main():
    """Main execution"""
    print_header("GRAPHITI SEARCH SERVICE PERFORMANCE COMPARISON")
    print(f"{Fore.CYAN}Comparing Python and Rust implementations")
    
    # Test both services
    python_results = test_python_service()
    rust_results = test_rust_service()
    
    # Generate report
    generate_report(python_results, rust_results)
    
    print(f"\n{Fore.GREEN}{'='*80}")
    print(f"{Fore.GREEN}Testing complete!")
    print(f"{Fore.GREEN}{'='*80}")

if __name__ == "__main__":
    # Install required packages if needed
    try:
        from tabulate import tabulate
    except ImportError:
        print("Installing required package: tabulate")
        import subprocess
        subprocess.check_call(["pip", "install", "tabulate"])
        from tabulate import tabulate
    
    main()