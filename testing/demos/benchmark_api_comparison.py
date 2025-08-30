#!/usr/bin/env python3
"""
Simple API-only benchmark comparison: Cerebras vs Ollama
No database required - pure API performance testing
"""

import asyncio
import time
import json
import os
from datetime import datetime
from typing import Dict, Any
from openai import AsyncOpenAI

async def test_cerebras_api(prompt: str) -> Dict[str, Any]:
    """Test Cerebras API response time and quality."""
    client = AsyncOpenAI(
        base_url="https://api.together.xyz/v1",
        api_key=os.environ.get("CEREBRAS_API_KEY"),
    )
    
    start = time.time()
    try:
        response = await client.chat.completions.create(
            model="meta-llama/Llama-3.2-90B-Vision-Instruct-Turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=500
        )
        end = time.time()
        
        return {
            "success": True,
            "response_time": end - start,
            "content": response.choices[0].message.content,
            "tokens": response.usage.total_tokens if hasattr(response, 'usage') else None
        }
    except Exception as e:
        return {
            "success": False,
            "response_time": time.time() - start,
            "error": str(e)
        }

async def test_ollama_api(prompt: str) -> Dict[str, Any]:
    """Test Ollama API response time and quality."""
    client = AsyncOpenAI(
        base_url="http://100.81.139.20:11434/v1",
        api_key="ollama"
    )
    
    start = time.time()
    try:
        response = await client.chat.completions.create(
            model="gemma3:12b",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=500
        )
        end = time.time()
        
        return {
            "success": True,
            "response_time": end - start,
            "content": response.choices[0].message.content,
            "tokens": response.usage.total_tokens if hasattr(response, 'usage') else None
        }
    except Exception as e:
        return {
            "success": False,
            "response_time": time.time() - start,
            "error": str(e)
        }

async def main():
    """Run benchmark comparison."""
    print("=" * 60)
    print("🔬 CEREBRAS vs OLLAMA API BENCHMARK")
    print("=" * 60)
    print(f"Start: {datetime.now().isoformat()}\n")
    
    # Test prompts - variety of tasks
    test_prompts = [
        "Write a Python function to calculate the nth Fibonacci number using dynamic programming.",
        "Extract entities from: 'Alice joined Microsoft in Seattle in 2022 to work on Azure cloud services.'",
        "Summarize in one sentence: Machine learning models learn patterns from data to make predictions.",
        "What are the key differences between async and sync programming in Python?",
        "Generate a JSON object with fields: name (string), age (number), skills (array of strings)."
    ]
    
    cerebras_results = []
    ollama_results = []
    
    print("🧠 Testing Cerebras (qwen-3-coder-480b)...")
    for i, prompt in enumerate(test_prompts, 1):
        print(f"  Test {i}/5: ", end="", flush=True)
        result = await test_cerebras_api(prompt)
        cerebras_results.append(result)
        if result["success"]:
            print(f"✓ {result['response_time']:.2f}s")
        else:
            print(f"✗ {result['error']}")
    
    print("\n🦙 Testing Ollama (gemma3:12b)...")  
    for i, prompt in enumerate(test_prompts, 1):
        print(f"  Test {i}/5: ", end="", flush=True)
        result = await test_ollama_api(prompt)
        ollama_results.append(result)
        if result["success"]:
            print(f"✓ {result['response_time']:.2f}s")
        else:
            print(f"✗ {result['error']}")
    
    # Analysis
    print("\n" + "=" * 60)
    print("📊 RESULTS ANALYSIS")
    print("=" * 60)
    
    # Calculate averages
    cerebras_times = [r["response_time"] for r in cerebras_results if r["success"]]
    ollama_times = [r["response_time"] for r in ollama_results if r["success"]]
    
    cerebras_avg = sum(cerebras_times) / len(cerebras_times) if cerebras_times else 0
    ollama_avg = sum(ollama_times) / len(ollama_times) if ollama_times else 0
    
    cerebras_success = sum(1 for r in cerebras_results if r["success"])
    ollama_success = sum(1 for r in ollama_results if r["success"])
    
    print(f"\n🧠 Cerebras Performance:")
    print(f"  • Success rate: {cerebras_success}/{len(cerebras_results)}")
    print(f"  • Average time: {cerebras_avg:.2f}s")
    print(f"  • Min/Max time: {min(cerebras_times):.2f}s / {max(cerebras_times):.2f}s" if cerebras_times else "N/A")
    
    print(f"\n🦙 Ollama Performance:")
    print(f"  • Success rate: {ollama_success}/{len(ollama_results)}")
    print(f"  • Average time: {ollama_avg:.2f}s")
    print(f"  • Min/Max time: {min(ollama_times):.2f}s / {max(ollama_times):.2f}s" if ollama_times else "N/A")
    
    print(f"\n🏆 Speed Comparison:")
    if cerebras_avg > 0 and ollama_avg > 0:
        if cerebras_avg < ollama_avg:
            speedup = ollama_avg / cerebras_avg
            print(f"  Cerebras is {speedup:.2f}x faster")
        else:
            speedup = cerebras_avg / ollama_avg
            print(f"  Ollama is {speedup:.2f}x faster")
    
    # Quality comparison (first prompt response)
    print(f"\n📝 Response Quality Sample (Fibonacci function):")
    if cerebras_results[0]["success"]:
        print(f"\nCerebras response length: {len(cerebras_results[0]['content'])} chars")
    if ollama_results[0]["success"]:
        print(f"Ollama response length: {len(ollama_results[0]['content'])} chars")
    
    # Save results
    results = {
        "timestamp": datetime.now().isoformat(),
        "cerebras": {
            "model": "qwen-3-coder-480b",
            "success_rate": f"{cerebras_success}/{len(cerebras_results)}",
            "avg_time": cerebras_avg,
            "results": cerebras_results
        },
        "ollama": {
            "model": "gemma3:12b",
            "success_rate": f"{ollama_success}/{len(ollama_results)}",
            "avg_time": ollama_avg,
            "results": ollama_results
        }
    }
    
    with open("api_benchmark_results.json", "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"\n💾 Full results saved to api_benchmark_results.json")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())