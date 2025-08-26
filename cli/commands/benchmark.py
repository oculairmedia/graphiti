#!/usr/bin/env python3
"""
CLI commands for dry-run benchmarking functionality.

Provides command-line interface for running benchmarks, hyperparameter tuning,
and performance analysis of the Graphiti ingestion pipeline.
"""

import asyncio
import click
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

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

logger = logging.getLogger(__name__)


async def create_graphiti_instance(
    database_type: str = "falkor",
    neo4j_uri: str = "bolt://192.168.50.90:7687",
    neo4j_user: str = "neo4j", 
    neo4j_password: str = "demodemo",
    neo4j_database: str = "neo4j",
    falkor_host: str = "192.168.50.90",
    falkor_port: int = 6379,
    falkor_database: str = "graphiti_migration"
) -> Graphiti:
    """Create a Graphiti instance based on configuration"""
    
    if database_type.lower() == "neo4j":
        driver = Neo4jDriver(
            uri=neo4j_uri,
            user=neo4j_user,
            password=neo4j_password,
            database=neo4j_database
        )
    elif database_type.lower() == "falkor":
        driver = FalkorDriver(
            host=falkor_host,
            port=falkor_port,
            database=falkor_database
        )
    else:
        raise ValueError(f"Unsupported database type: {database_type}")
    
    llm_client = OpenAIClient()
    embedder = OpenAIEmbedder()
    
    return Graphiti(
        driver=driver,
        llm_client=llm_client,
        embedder=embedder
    )


@click.group()
def benchmark():
    """Dry-run benchmarking commands for performance testing and hyperparameter tuning"""
    pass


@benchmark.command()
@click.option("--episodes-limit", type=int, default=50, help="Number of episodes to process")
@click.option("--batch-size", type=int, default=10, help="Batch size for processing episodes")
@click.option("--max-concurrent", type=int, default=3, help="Maximum concurrent episode processing")
@click.option("--database-type", type=click.Choice(["neo4j", "falkor"]), default="falkor", help="Database backend to use")
@click.option("--output-dir", type=click.Path(), default="./benchmark_results", help="Output directory for results")
@click.option("--run-id", type=str, help="Custom run ID for this benchmark")
@click.option("--enable-profiling/--disable-profiling", default=True, help="Enable performance profiling")
@click.option("--export-format", multiple=True, default=["json", "csv"], help="Export formats")
@click.option("--description", type=str, help="Description for this benchmark run")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
def run(
    episodes_limit: int,
    batch_size: int, 
    max_concurrent: int,
    database_type: str,
    output_dir: str,
    run_id: Optional[str],
    enable_profiling: bool,
    export_format: List[str],
    description: Optional[str],
    verbose: bool
):
    """Run a basic dry-run benchmark"""
    
    if verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)
    
    async def _run_benchmark():
        click.echo(f"Starting dry-run benchmark with {episodes_limit} episodes...")
        
        # Create Graphiti instance
        graphiti = await create_graphiti_instance(database_type=database_type)
        
        # Configure benchmark
        config = DryRunConfig(
            run_id=run_id or f"benchmark_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            description=description or f"Dry-run benchmark with {episodes_limit} episodes",
            episodes_limit=episodes_limit,
            batch_size=batch_size,
            max_concurrent_episodes=max_concurrent,
            output_dir=Path(output_dir),
            export_formats=list(export_format),
            enable_profiling=enable_profiling,
            collect_memory_stats=True,
        )
        
        # Run benchmark
        worker = DryRunWorker(graphiti, config)
        try:
            results = await worker.run_benchmark()
            
            # Display results
            summary = results.get_summary_stats()
            click.echo(f"\n{'='*50}")
            click.echo("BENCHMARK RESULTS")
            click.echo(f"{'='*50}")
            click.echo(f"Run ID: {results.run_id}")
            click.echo(f"Episodes processed: {results.total_episodes_processed}")
            click.echo(f"Success rate: {summary.get('success_rate', 0)*100:.1f}%")
            click.echo(f"Average duration: {summary.get('avg_episode_duration_ms', 0):.1f}ms")
            click.echo(f"Episodes per second: {summary.get('episodes_per_second', 0):.2f}")
            click.echo(f"Total entities created: {summary.get('total_entities_created', 0)}")
            click.echo(f"Total edges created: {summary.get('total_edges_created', 0)}")
            click.echo(f"Results saved to: {config.output_dir}")
            
            if results.failed_episodes > 0:
                click.echo(f"⚠️  {results.failed_episodes} episodes failed")
            
            click.echo("✅ Benchmark completed successfully!")
            
        except Exception as e:
            click.echo(f"❌ Benchmark failed: {e}")
            raise click.ClickException(str(e))
        finally:
            await worker.close()
            await graphiti.close()
    
    asyncio.run(_run_benchmark())


@benchmark.command()
@click.option("--episodes-limit", type=int, default=30, help="Number of episodes per hyperparameter combination")
@click.option("--temperature", multiple=True, type=float, help="Temperature values to test")
@click.option("--max-tokens", multiple=True, type=int, help="Max tokens values to test") 
@click.option("--search-limit", multiple=True, type=int, help="Search limit values to test")
@click.option("--entity-similarity", multiple=True, type=float, help="Entity similarity thresholds to test")
@click.option("--output-dir", type=click.Path(), default="./hyperparameter_results", help="Output directory")
@click.option("--database-type", type=click.Choice(["neo4j", "falkor"]), default="falkor", help="Database backend")
@click.option("--max-combinations", type=int, help="Limit number of parameter combinations to test")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
def tune(
    episodes_limit: int,
    temperature: tuple,
    max_tokens: tuple,
    search_limit: tuple,
    entity_similarity: tuple,
    output_dir: str,
    database_type: str,
    max_combinations: Optional[int],
    verbose: bool
):
    """Run hyperparameter tuning across parameter combinations"""
    
    if verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)
    
    async def _run_tuning():
        # Build hyperparameter space
        param_space = HyperparameterSpace()
        
        if temperature:
            param_space.temperature = list(temperature)
        if max_tokens:
            param_space.max_tokens = list(max_tokens)
        if search_limit:
            param_space.search_limit = list(search_limit)
        if entity_similarity:
            param_space.entity_similarity_threshold = list(entity_similarity)
        
        combinations = param_space.get_parameter_combinations()
        
        if max_combinations and len(combinations) > max_combinations:
            combinations = combinations[:max_combinations]
            click.echo(f"Limited to {max_combinations} combinations")
        
        click.echo(f"Testing {len(combinations)} hyperparameter combinations...")
        click.echo(f"Episodes per combination: {episodes_limit}")
        
        results = []
        
        for i, hyperparams in enumerate(combinations):
            click.echo(f"\nRunning combination {i+1}/{len(combinations)}: {hyperparams}")
            
            # Create fresh Graphiti instance
            graphiti = await create_graphiti_instance(database_type=database_type)
            
            config = DryRunConfig(
                run_id=f"tune_{i+1}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                description=f"Hyperparameter tuning {i+1}/{len(combinations)}",
                episodes_limit=episodes_limit,
                batch_size=5,
                max_concurrent_episodes=1,  # Sequential for fair comparison
                output_dir=Path(output_dir) / f"combination_{i+1}",
                export_formats=["json"],
                hyperparameters=hyperparams,
                enable_profiling=False,
                collect_memory_stats=True,
            )
            
            worker = DryRunWorker(graphiti, config)
            try:
                result = await worker.run_benchmark()
                summary = result.get_summary_stats()
                
                results.append({
                    'combination': i + 1,
                    'hyperparameters': hyperparams,
                    'summary': summary,
                    'run_id': result.run_id
                })
                
                click.echo(f"  ✅ Success rate: {summary.get('success_rate', 0)*100:.1f}%")
                click.echo(f"  ⚡ Avg duration: {summary.get('avg_episode_duration_ms', 0):.1f}ms")
                
            except Exception as e:
                click.echo(f"  ❌ Failed: {e}")
                results.append({
                    'combination': i + 1,
                    'hyperparameters': hyperparams,
                    'error': str(e)
                })
            finally:
                await worker.close()
                await graphiti.close()
        
        # Analyze and save results
        await _analyze_tuning_results(results, Path(output_dir))
        
        click.echo(f"\n✅ Hyperparameter tuning completed!")
        click.echo(f"Results saved to: {output_dir}")
    
    asyncio.run(_run_tuning())


async def _analyze_tuning_results(results: List[Dict[str, Any]], output_dir: Path):
    """Analyze hyperparameter tuning results and generate report"""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Filter successful results
    successful_results = [r for r in results if 'error' not in r]
    
    if not successful_results:
        click.echo("❌ No successful results to analyze")
        return
    
    # Sort by performance (success rate, then speed)
    successful_results.sort(key=lambda x: (
        -x['summary'].get('success_rate', 0),
        x['summary'].get('avg_episode_duration_ms', float('inf'))
    ))
    
    # Generate analysis report
    analysis = {
        'timestamp': datetime.now().isoformat(),
        'total_combinations': len(results),
        'successful_combinations': len(successful_results),
        'failed_combinations': len(results) - len(successful_results),
        'top_performing': successful_results[:5],
        'all_results': results
    }
    
    # Save detailed results
    with open(output_dir / "analysis.json", 'w') as f:
        json.dump(analysis, f, indent=2, default=str)
    
    # Display top results
    click.echo(f"\n{'='*60}")
    click.echo("HYPERPARAMETER TUNING ANALYSIS")
    click.echo(f"{'='*60}")
    click.echo(f"Total combinations tested: {len(results)}")
    click.echo(f"Successful runs: {len(successful_results)}")
    click.echo(f"Failed runs: {len(results) - len(successful_results)}")
    
    click.echo(f"\n🏆 TOP 3 PERFORMING CONFIGURATIONS:")
    for i, result in enumerate(successful_results[:3]):
        click.echo(f"\n{i+1}. {result['hyperparameters']}")
        summary = result['summary']
        click.echo(f"   Success Rate: {summary.get('success_rate', 0)*100:.1f}%")
        click.echo(f"   Avg Duration: {summary.get('avg_episode_duration_ms', 0):.1f}ms")
        click.echo(f"   Episodes/sec: {summary.get('episodes_per_second', 0):.2f}")


@benchmark.command()
@click.option("--episodes-limit", type=int, default=100, help="Number of episodes to test with each backend")
@click.option("--output-dir", type=click.Path(), default="./backend_comparison", help="Output directory")
@click.option("--include-neo4j/--skip-neo4j", default=True, help="Include Neo4j in comparison")
@click.option("--include-falkor/--skip-falkor", default=True, help="Include FalkorDB in comparison")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
def compare(
    episodes_limit: int,
    output_dir: str,
    include_neo4j: bool,
    include_falkor: bool,
    verbose: bool
):
    """Compare performance between different database backends"""
    
    if verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)
    
    if not include_neo4j and not include_falkor:
        raise click.ClickException("Must include at least one database backend")
    
    async def _run_comparison():
        backends = []
        if include_neo4j:
            backends.append(("Neo4j", "neo4j"))
        if include_falkor:
            backends.append(("FalkorDB", "falkor"))
        
        click.echo(f"Comparing database backends: {', '.join(b[0] for b in backends)}")
        click.echo(f"Episodes per backend: {episodes_limit}")
        
        results = {}
        
        for backend_name, db_type in backends:
            click.echo(f"\n🔍 Testing {backend_name}...")
            
            graphiti = await create_graphiti_instance(database_type=db_type)
            
            config = DryRunConfig(
                run_id=f"compare_{db_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                description=f"Backend comparison: {backend_name}",
                episodes_limit=episodes_limit,
                batch_size=10,
                max_concurrent_episodes=3,
                output_dir=Path(output_dir) / db_type,
                export_formats=["json", "csv"],
                enable_profiling=True,
                collect_memory_stats=True,
            )
            
            worker = DryRunWorker(graphiti, config)
            try:
                result = await worker.run_benchmark()
                summary = result.get_summary_stats()
                results[backend_name] = summary
                
                click.echo(f"  ✅ {backend_name} completed")
                click.echo(f"     Episodes/sec: {summary.get('episodes_per_second', 0):.2f}")
                click.echo(f"     Success rate: {summary.get('success_rate', 0)*100:.1f}%")
                
            except Exception as e:
                click.echo(f"  ❌ {backend_name} failed: {e}")
                results[backend_name] = {"error": str(e)}
            finally:
                await worker.close()
                await graphiti.close()
        
        # Display comparison
        click.echo(f"\n{'='*60}")
        click.echo("BACKEND PERFORMANCE COMPARISON")
        click.echo(f"{'='*60}")
        
        for backend, stats in results.items():
            if "error" in stats:
                click.echo(f"\n❌ {backend}: {stats['error']}")
            else:
                click.echo(f"\n📊 {backend}:")
                click.echo(f"   Episodes/second: {stats.get('episodes_per_second', 0):.2f}")
                click.echo(f"   Avg duration: {stats.get('avg_episode_duration_ms', 0):.1f}ms")
                click.echo(f"   Success rate: {stats.get('success_rate', 0)*100:.1f}%")
                click.echo(f"   Total entities: {stats.get('total_entities_created', 0)}")
                click.echo(f"   Total edges: {stats.get('total_edges_created', 0)}")
        
        # Save comparison results
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        comparison_data = {
            'timestamp': datetime.now().isoformat(),
            'episodes_per_backend': episodes_limit,
            'backends_tested': list(results.keys()),
            'results': results
        }
        
        with open(output_path / "comparison.json", 'w') as f:
            json.dump(comparison_data, f, indent=2, default=str)
        
        click.echo(f"\n✅ Comparison completed! Results saved to: {output_dir}")
    
    asyncio.run(_run_comparison())


if __name__ == "__main__":
    benchmark()