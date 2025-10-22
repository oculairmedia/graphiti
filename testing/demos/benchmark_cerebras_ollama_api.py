#!/usr/bin/env python3
"""
Benchmark Cerebras vs Ollama API Performance
No database connection required - pure API testing
"""

import asyncio
import time
import json
import os
from typing import Dict, Any, List
from dataclasses import dataclass
from datetime import datetime
from pydantic import BaseModel

# Import only the LLM clients
import sys
sys.path.append('/opt/stacks/graphiti')

from graphiti_core.llm_client.cerebras_client import CerebrasClient
from graphiti_core.llm_client.ollama_factory import OllamaClientFactory

@dataclass
class BenchmarkResult:
    model: str
    task: str
    response_time: float
    tokens_generated: int
    success: bool
    error: str = None

class TestResponse(BaseModel):
    entities: List[str]
    summary: str
    confidence: float

async def benchmark_simple_completion(client, model_name: str, prompt: str) -> BenchmarkResult:
    """Test simple text completion"""
    start = time.time()
    try:
        messages = [{"role": "user", "content": prompt}]
        response = await client.generate_response(messages)
        end = time.time()
        
        return BenchmarkResult(
            model=model_name,
            task="simple_completion",
            response_time=end - start,
            tokens_generated=len(response.split()) if response else 0,
            success=True
        )
    except Exception as e:
        return BenchmarkResult(
            model=model_name,
            task="simple_completion",
            response_time=time.time() - start,
            tokens_generated=0,
            success=False,
            error=str(e)
        )

async def benchmark_structured_output(client, model_name: str) -> BenchmarkResult:
    """Test structured JSON output"""
    start = time.time()
    try:
        messages = [{
            "role": "user", 
            "content": "Extract entities from: 'John works at OpenAI in San Francisco developing GPT models.'"
        }]
        response = await client.generate_response(messages, response_model=TestResponse)
        end = time.time()
        
        return BenchmarkResult(
            model=model_name,
            task="structured_output",
            response_time=end - start,
            tokens_generated=1,  # Structured response
            success=True
        )
    except Exception as e:
        return BenchmarkResult(
            model=model_name,
            task="structured_output",
            response_time=time.time() - start,
            tokens_generated=0,
            success=False,
            error=str(e)
        )

async def benchmark_batch_processing(client, model_name: str, batch_size: int = 3) -> BenchmarkResult:
    """Test batch processing capability"""
    prompts = [
        "What is machine learning?",
        "Explain quantum computing.",
        "Define artificial intelligence."
    ][:batch_size]
    
    start = time.time()
    try:
        tasks = []
        for prompt in prompts:
            messages = [{"role": "user", "content": prompt}]
            tasks.append(client.generate_response(messages))
        
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        end = time.time()
        
        successful = sum(1 for r in responses if not isinstance(r, Exception))
        
        return BenchmarkResult(
            model=model_name,
            task=f"batch_processing_{batch_size}",
            response_time=end - start,
            tokens_generated=successful,
            success=successful == batch_size,
            error=f"{batch_size - successful} failed" if successful < batch_size else None
        )
    except Exception as e:
        return BenchmarkResult(
            model=model_name,
            task=f"batch_processing_{batch_size}",
            response_time=time.time() - start,
            tokens_generated=0,
            success=False,
            error=str(e)
        )

async def run_benchmarks():
    """Run all benchmarks for both models"""
    results = []
    
    # Initialize clients
    cerebras_client = CerebrasClient(
        api_key=os.environ.get("CEREBRAS_API_KEY"),
        model="qwen-3-coder-480b"
    )
    
    ollama_client = OllamaClientFactory.create_client(
        base_url="http://100.81.139.20:11434/v1",
        model="gemma3:12b"
    )
    
    print("=" * 60)
    print("🔬 CEREBRAS vs OLLAMA PERFORMANCE BENCHMARK")
    print("=" * 60)
    print(f"Start time: {datetime.now().isoformat()}\n")
    
    # Test prompts
    test_prompts = [
        "Write a Python function to calculate fibonacci numbers.",
        "Explain the concept of recursion in programming.",
        "What are the benefits of asynchronous programming?"
    ]
    
    # Benchmark Cerebras
    print("🧠 Testing Cerebras (qwen-3-coder-480b)...")
    for i, prompt in enumerate(test_prompts, 1):
        print(f"  Test {i}/3: Simple completion...", end=" ")
        result = await benchmark_simple_completion(cerebras_client, "Cerebras", prompt)
        results.append(result)
        print(f"✓ {result.response_time:.2f}s" if result.success else f"✗ {result.error}")
    
    print(f"  Test 4: Structured output...", end=" ")
    result = await benchmark_structured_output(cerebras_client, "Cerebras")
    results.append(result)
    print(f"✓ {result.response_time:.2f}s" if result.success else f"✗ {result.error}")
    
    print(f"  Test 5: Batch processing...", end=" ")
    result = await benchmark_batch_processing(cerebras_client, "Cerebras", 3)
    results.append(result)
    print(f"✓ {result.response_time:.2f}s" if result.success else f"✗ {result.error}")
    
    # Benchmark Ollama
    print("\n🦙 Testing Ollama (gemma3:12b)...")
    for i, prompt in enumerate(test_prompts, 1):
        print(f"  Test {i}/3: Simple completion...", end=" ")
        result = await benchmark_simple_completion(ollama_client, "Ollama", prompt)
        results.append(result)
        print(f"✓ {result.response_time:.2f}s" if result.success else f"✗ {result.error}")
    
    print(f"  Test 4: Structured output...", end=" ")
    result = await benchmark_structured_output(ollama_client, "Ollama")
    results.append(result)
    print(f"✓ {result.response_time:.2f}s" if result.success else f"✗ {result.error}")
    
    print(f"  Test 5: Batch processing...", end=" ")
    result = await benchmark_batch_processing(ollama_client, "Ollama", 3)
    results.append(result)
    print(f"✓ {result.response_time:.2f}s" if result.success else f"✗ {result.error}")
    
    # Analyze results
    print("\n" + "=" * 60)
    print("📊 PERFORMANCE COMPARISON")
    print("=" * 60)
    
    cerebras_results = [r for r in results if r.model == "Cerebras"]
    ollama_results = [r for r in results if r.model == "Ollama"]
    
    cerebras_avg = sum(r.response_time for r in cerebras_results if r.success) / max(1, sum(1 for r in cerebras_results if r.success))
    ollama_avg = sum(r.response_time for r in ollama_results if r.success) / max(1, sum(1 for r in ollama_results if r.success))
    
    print(f"\n🧠 Cerebras Performance:")
    print(f"  • Average response time: {cerebras_avg:.2f}s")
    print(f"  • Success rate: {sum(1 for r in cerebras_results if r.success)}/{len(cerebras_results)}")
    print(f"  • Total time: {sum(r.response_time for r in cerebras_results):.2f}s")
    
    print(f"\n🦙 Ollama Performance:")
    print(f"  • Average response time: {ollama_avg:.2f}s")
    print(f"  • Success rate: {sum(1 for r in ollama_results if r.success)}/{len(ollama_results)}")
    print(f"  • Total time: {sum(r.response_time for r in ollama_results):.2f}s")
    
    print(f"\n🏆 Winner: ", end="")
    if cerebras_avg < ollama_avg:
        speedup = ollama_avg / cerebras_avg
        print(f"Cerebras ({speedup:.2f}x faster)")
    else:
        speedup = cerebras_avg / ollama_avg
        print(f"Ollama ({speedup:.2f}x faster)")
    
    # Save results
    results_dict = {
        "timestamp": datetime.now().isoformat(),
        "cerebras": {
            "model": "qwen-3-coder-480b",
            "avg_response_time": cerebras_avg,
            "success_rate": f"{sum(1 for r in cerebras_results if r.success)}/{len(cerebras_results)}",
            "results": [vars(r) for r in cerebras_results]
        },
        "ollama": {
            "model": "gemma3:12b",
            "avg_response_time": ollama_avg,
            "success_rate": f"{sum(1 for r in ollama_results if r.success)}/{len(ollama_results)}",
            "results": [vars(r) for r in ollama_results]
        }
    }
    
    with open("benchmark_results.json", "w") as f:
        json.dump(results_dict, f, indent=2, default=str)
    
    print(f"\n💾 Results saved to benchmark_results.json")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(run_benchmarks())