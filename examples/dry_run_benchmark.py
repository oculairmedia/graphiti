#!/usr/bin/env python3
"""
Example script demonstrating how to use the dry-run benchmarking system.

This script shows how to:
1. Configure a dry-run benchmark
2. Run benchmarks with different hyperparameters
3. Collect and analyze performance metrics
4. Export results for analysis

Usage:
    python examples/dry_run_benchmark.py --episodes-limit 100 --hyperparameter-tuning
"""

import asyncio
import argparse
import logging
from pathlib import Path
from datetime import datetime, timedelta

from graphiti_core.graphiti import Graphiti
from graphiti_core.driver.neo4j_driver import Neo4jDriver
from graphiti_core.driver.falkordb_driver import FalkorDriver
from graphiti_core.llm_client.openai_client import OpenAIClient
from graphiti_core.embedder.openai import OpenAIEmbedder
from graphiti_core.benchmarking import (
    DryRunConfig, 
    DryRunWorker, 
    SafetyConfig, 
    HyperparameterSpace
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def create_graphiti_instance(use_falkor: bool = False) -> Graphiti:
    """Create a Graphiti instance for benchmarking"""
    
    if use_falkor:
        driver = FalkorDriver(
            host='localhost',
            port=6389,
            database='graphiti_migration'
        )
    else:
        driver = Neo4jDriver(
            uri='bolt://localhost:7687',
            user='neo4j',
            password='demodemo',
            database='neo4j'
        )
    
    llm_client = OpenAIClient()
    embedder = OpenAIEmbedder()
    
    return Graphiti(
        driver=driver,
        llm_client=llm_client,
        embedder=embedder
    )


async def run_simple_benchmark():
    """Run a simple benchmark with default configuration"""
    logger.info("Running simple dry-run benchmark...")
    
    # Create Graphiti instance
    graphiti = await create_graphiti_instance(use_falkor=True)
    
    # Configure dry-run
    config = DryRunConfig(
        run_id=f"simple_benchmark_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        description="Simple dry-run benchmark to test basic functionality",
        episodes_limit=10,
        batch_size=5,
        max_concurrent_episodes=2,
        output_dir=Path("./benchmark_results"),
        export_formats=["json", "csv"],
        enable_profiling=True,
        collect_memory_stats=True,
    )
    
    # Run benchmark
    worker = DryRunWorker(graphiti, config)
    try:
        results = await worker.run_benchmark()
        logger.info(f"Benchmark complete! Run ID: {results.run_id}")
        logger.info(f"Episodes processed: {results.total_episodes_processed}")
        logger.info(f"Success rate: {results.successful_episodes / results.total_episodes_processed * 100:.1f}%")
        logger.info(f"Avg duration: {results.get_summary_stats().get('avg_episode_duration_ms', 0):.1f}ms")
        
        return results
    finally:
        await worker.close()
        await graphiti.close()


async def run_hyperparameter_tuning():
    """Run systematic hyperparameter tuning"""
    logger.info("Running hyperparameter tuning benchmark...")
    
    # Define hyperparameter space
    param_space = HyperparameterSpace(
        temperature=[0.0, 0.3, 0.7],
        max_tokens=[1000, 2000],
        entity_similarity_threshold=[0.8, 0.9],
        search_limit=[10, 20]
    )
    
    combinations = param_space.get_parameter_combinations()
    logger.info(f"Testing {len(combinations)} hyperparameter combinations")
    
    results = []
    
    for i, hyperparams in enumerate(combinations):
        logger.info(f"Running combination {i+1}/{len(combinations)}: {hyperparams}")
        
        # Create fresh Graphiti instance for each run
        graphiti = await create_graphiti_instance(use_falkor=True)
        
        # Configure dry-run with current hyperparameters
        config = DryRunConfig(
            run_id=f"hyperparam_tune_{i+1}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            description=f"Hyperparameter tuning run {i+1}: {hyperparams}",
            episodes_limit=20,
            batch_size=5,
            max_concurrent_episodes=1,  # Sequential for consistent comparison
            output_dir=Path("./benchmark_results/hyperparameter_tuning"),
            export_formats=["json"],
            hyperparameters=hyperparams,
            enable_profiling=False,  # Disable profiling for faster runs
            collect_memory_stats=True,
        )
        
        # Run benchmark
        worker = DryRunWorker(graphiti, config)
        try:
            result = await worker.run_benchmark()
            results.append({
                'hyperparameters': hyperparams,
                'metrics': result,
                'summary': result.get_summary_stats()
            })
            
            logger.info(f"Run {i+1} complete - Success rate: {result.successful_episodes / result.total_episodes_processed * 100:.1f}%")
            
        except Exception as e:
            logger.error(f"Run {i+1} failed: {e}")
            results.append({
                'hyperparameters': hyperparams,
                'error': str(e)
            })
        finally:
            await worker.close()
            await graphiti.close()
    
    # Analyze results
    await analyze_hyperparameter_results(results)
    return results


async def analyze_hyperparameter_results(results):
    """Analyze and report hyperparameter tuning results"""
    import json
    
    valid_results = [r for r in results if 'error' not in r]
    
    if not valid_results:
        logger.error("No valid results to analyze")
        return
    
    logger.info(f"\n{'='*60}")
    logger.info("HYPERPARAMETER TUNING RESULTS")
    logger.info(f"{'='*60}")
    
    # Sort by success rate and average duration
    valid_results.sort(key=lambda x: (
        -x['summary'].get('success_rate', 0),
        x['summary'].get('avg_episode_duration_ms', float('inf'))
    ))
    
    logger.info("\nTop 3 configurations:")
    for i, result in enumerate(valid_results[:3]):
        logger.info(f"\n{i+1}. {result['hyperparameters']}")
        summary = result['summary']
        logger.info(f"   Success Rate: {summary.get('success_rate', 0)*100:.1f}%")
        logger.info(f"   Avg Duration: {summary.get('avg_episode_duration_ms', 0):.1f}ms")
        logger.info(f"   Episodes/sec: {summary.get('episodes_per_second', 0):.2f}")
    
    # Save detailed analysis
    analysis_file = Path("./benchmark_results/hyperparameter_analysis.json")
    analysis_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(analysis_file, 'w') as f:
        json.dump({
            'timestamp': datetime.now().isoformat(),
            'total_combinations': len(results),
            'successful_runs': len(valid_results),
            'failed_runs': len(results) - len(valid_results),
            'results': results
        }, f, indent=2, default=str)
    
    logger.info(f"\nDetailed analysis saved to {analysis_file}")


async def run_performance_comparison():
    """Compare performance between different database backends"""
    logger.info("Running performance comparison between Neo4j and FalkorDB...")
    
    backends = [
        ("Neo4j", False),
        ("FalkorDB", True)
    ]
    
    results = {}
    
    for backend_name, use_falkor in backends:
        logger.info(f"Testing {backend_name}...")
        
        graphiti = await create_graphiti_instance(use_falkor=use_falkor)
        
        config = DryRunConfig(
            run_id=f"backend_comparison_{backend_name.lower()}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            description=f"Performance comparison using {backend_name}",
            episodes_limit=50,
            batch_size=10,
            max_concurrent_episodes=3,
            output_dir=Path(f"./benchmark_results/backend_comparison/{backend_name.lower()}"),
            export_formats=["json", "csv"],
            enable_profiling=True,
            collect_memory_stats=True,
        )
        
        worker = DryRunWorker(graphiti, config)
        try:
            result = await worker.run_benchmark()
            results[backend_name] = result.get_summary_stats()
            logger.info(f"{backend_name} benchmark complete")
        finally:
            await worker.close()
            await graphiti.close()
    
    # Compare results
    logger.info(f"\n{'='*50}")
    logger.info("BACKEND PERFORMANCE COMPARISON")
    logger.info(f"{'='*50}")
    
    for backend, stats in results.items():
        logger.info(f"\n{backend}:")
        logger.info(f"  Episodes/second: {stats.get('episodes_per_second', 0):.2f}")
        logger.info(f"  Avg duration: {stats.get('avg_episode_duration_ms', 0):.1f}ms")
        logger.info(f"  Success rate: {stats.get('success_rate', 0)*100:.1f}%")


async def main():
    parser = argparse.ArgumentParser(description="Dry-run benchmark examples")
    parser.add_argument("--simple", action="store_true", help="Run simple benchmark")
    parser.add_argument("--hyperparameter-tuning", action="store_true", help="Run hyperparameter tuning")
    parser.add_argument("--backend-comparison", action="store_true", help="Compare database backends")
    parser.add_argument("--episodes-limit", type=int, default=50, help="Number of episodes to process")
    
    args = parser.parse_args()
    
    if not any([args.simple, args.hyperparameter_tuning, args.backend_comparison]):
        # Default to simple benchmark
        args.simple = True
    
    try:
        if args.simple:
            await run_simple_benchmark()
        
        if args.hyperparameter_tuning:
            await run_hyperparameter_tuning()
        
        if args.backend_comparison:
            await run_performance_comparison()
        
        logger.info("All benchmarks complete!")
        
    except KeyboardInterrupt:
        logger.info("Benchmarks interrupted by user")
    except Exception as e:
        logger.error(f"Benchmark failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())