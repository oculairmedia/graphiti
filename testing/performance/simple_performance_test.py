#!/usr/bin/env python3
"""
Simple performance comparison between Python and Rust search implementations.
"""

import time
import requests
import statistics
from colorama import init, Fore

init(autoreset=True)

def test_service(name, url, payload, num_requests=50):
    """Test a service endpoint"""
    print(f"\n{Fore.CYAN}Testing {name}...")
    
    latencies = []
    successes = 0
    
    # Warmup
    for _ in range(5):
        try:
            requests.post(url, json=payload, timeout=5)
        except:
            pass
    
    # Test requests
    for i in range(num_requests):
        try:
            start = time.perf_counter()
            response = requests.post(url, json=payload, timeout=5)
            latency = (time.perf_counter() - start) * 1000
            
            if response.status_code == 200:
                successes += 1
                latencies.append(latency)
                
            if (i + 1) % 10 == 0:
                print(f"  Progress: {i+1}/{num_requests}")
                
        except Exception as e:
            print(f"  Error: {e}")
    
    if latencies:
        return {
            "success_rate": (successes / num_requests) * 100,
            "median_latency": statistics.median(latencies),
            "avg_latency": statistics.mean(latencies),
            "min_latency": min(latencies),
            "max_latency": max(latencies),
            "throughput": 1000 / statistics.median(latencies)  # Requests per second
        }
    return None

def main():
    print(f"{Fore.YELLOW}=== Performance Comparison: Python vs Rust Search ===")
    
    # Test Python service
    python_url = "http://localhost:8003/search"
    python_payload = {
        "query": "Node",
        "limit": 10,
        "search_type": "hybrid"
    }
    
    python_results = test_service("Python Service", python_url, python_payload)
    
    # Test Rust service (edge search)
    rust_url = "http://localhost:3004/search/edges"
    rust_payload = {
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
    
    rust_results = test_service("Rust Service", rust_url, rust_payload)
    
    # Print comparison
    print(f"\n{Fore.GREEN}=== Results ===")
    
    if python_results:
        print(f"\n{Fore.BLUE}Python Service:")
        print(f"  Success Rate: {python_results['success_rate']:.1f}%")
        print(f"  Median Latency: {python_results['median_latency']:.2f} ms")
        print(f"  Avg Latency: {python_results['avg_latency']:.2f} ms")
        print(f"  Min/Max: {python_results['min_latency']:.2f} / {python_results['max_latency']:.2f} ms")
        print(f"  Throughput: {python_results['throughput']:.1f} req/s")
    
    if rust_results:
        print(f"\n{Fore.MAGENTA}Rust Service:")
        print(f"  Success Rate: {rust_results['success_rate']:.1f}%")
        print(f"  Median Latency: {rust_results['median_latency']:.2f} ms")
        print(f"  Avg Latency: {rust_results['avg_latency']:.2f} ms")
        print(f"  Min/Max: {rust_results['min_latency']:.2f} / {rust_results['max_latency']:.2f} ms")
        print(f"  Throughput: {rust_results['throughput']:.1f} req/s")
    
    if python_results and rust_results:
        print(f"\n{Fore.YELLOW}=== Comparison ===")
        
        # Latency improvement
        latency_improvement = ((python_results['median_latency'] - rust_results['median_latency']) / 
                              python_results['median_latency']) * 100
        
        # Throughput improvement
        throughput_improvement = ((rust_results['throughput'] - python_results['throughput']) / 
                                 python_results['throughput']) * 100
        
        if latency_improvement > 0:
            print(f"  {Fore.GREEN}Rust is {latency_improvement:.1f}% faster (lower latency)")
        else:
            print(f"  {Fore.RED}Python is {abs(latency_improvement):.1f}% faster (lower latency)")
            
        if throughput_improvement > 0:
            print(f"  {Fore.GREEN}Rust has {throughput_improvement:.1f}% higher throughput")
        else:
            print(f"  {Fore.RED}Python has {abs(throughput_improvement):.1f}% higher throughput")
        
        # Summary
        speedup = python_results['median_latency'] / rust_results['median_latency']
        if speedup > 1:
            print(f"\n  {Fore.GREEN}Overall: Rust is {speedup:.1f}x faster than Python")
        else:
            print(f"\n  {Fore.RED}Overall: Python is {1/speedup:.1f}x faster than Rust")

if __name__ == "__main__":
    main()