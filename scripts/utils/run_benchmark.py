#!/usr/bin/env python3
"""
Simple wrapper for running dry-run benchmarks with proper environment setup.
"""

import os
import asyncio
from pathlib import Path
from graphiti_core.graphiti import Graphiti
from graphiti_core.driver.falkordb_driver import FalkorDriver
from graphiti_core.llm_client.openai_client import OpenAIClient
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
from graphiti_core.benchmarking import DryRunConfig, DryRunWorker

async def main():
    # Set up Chutes API configuration
    chutes_api_key = 'cpk_f62b08fa4c2b4ae0b195b944fd47d6fc.bb20b5a1d58c50c9bc051e74b2a39d7c.roXSCXsJnWAk8mcZ26umGcrPjkCaqXlh'
    
    print("🚀 Starting dry-run benchmark test with Chutes AI...")
    
    try:
        # Create FalkorDB driver
        print("📊 Connecting to FalkorDB...")
        driver = FalkorDriver(
            host='192.168.50.90',
            port=6379,
            database='graphiti_migration'
        )
        
        # Create LLM client configured for Chutes AI
        print("🧠 Configuring Chutes AI client...")
        chutes_config = LLMConfig(
            api_key=chutes_api_key,
            base_url='https://llm.chutes.ai/v1',
            model='zai-org/GLM-4.5-FP8',
            temperature=0.7,
            max_tokens=1024
        )
        llm_client = OpenAIClient(config=chutes_config)
        
        # Create embedder using our Ollama server
        print("📊 Configuring Ollama embedder...")
        ollama_embedder_config = OpenAIEmbedderConfig(
            api_key='ollama',  # Ollama doesn't need a real API key
            base_url='http://192.168.50.80:11434/v1',  # Our Ollama server
            embedding_model='mxbai-embed-large'  # A good embedding model
        )
        embedder = OpenAIEmbedder(config=ollama_embedder_config)
        
        # Create Graphiti instance
        graphiti = Graphiti(
            graph_driver=driver,
            llm_client=llm_client,
            embedder=embedder
        )
        
        print("⚙️  Configuring dry-run benchmark...")
        
        # Configure benchmark
        config = DryRunConfig(
            run_id="chutes_ai_test_2025",
            description="Test of Chutes AI with dry-run benchmarking system",
            episodes_limit=3,  # Small test
            batch_size=1,
            max_concurrent_episodes=1,
            output_dir=Path("./test_benchmark_results"),
            export_formats=["json"],
            enable_profiling=False,  # Disable for simplicity
            collect_memory_stats=False
        )
        
        print("🔧 Creating dry-run worker...")
        
        # Create and run benchmark
        worker = DryRunWorker(graphiti, config)
        
        try:
            print("🏃 Running benchmark...")
            results = await worker.run_benchmark()
            
            print("\n" + "="*50)
            print("📈 BENCHMARK RESULTS")
            print("="*50)
            print(f"Run ID: {results.run_id}")
            print(f"Episodes processed: {results.total_episodes_processed}")
            print(f"Successful: {results.successful_episodes}")
            print(f"Failed: {results.failed_episodes}")
            
            if results.total_episodes_processed > 0:
                success_rate = results.successful_episodes / results.total_episodes_processed * 100
                print(f"Success rate: {success_rate:.1f}%")
                
                summary = results.get_summary_stats()
                if 'avg_episode_duration_ms' in summary:
                    print(f"Avg duration: {summary['avg_episode_duration_ms']:.1f}ms")
            
            print(f"Results saved to: {config.output_dir}")
            print("✅ Benchmark completed successfully!")
            
        finally:
            await worker.close()
            await graphiti.close()
            
    except Exception as e:
        print(f"❌ Benchmark failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)