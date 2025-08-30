#!/usr/bin/env python3

"""
Test Chutes AI batch processing with parallel API calls.

This test runs all batch sizes simultaneously to test concurrency
and get faster results while measuring quota efficiency.
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import List

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent.parent))

# Import our robust parser from the previous test
from test_chutes_batch_robust_parsing import ChutesClientRobust, BatchExtractionResult

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_batch_size(client: ChutesClientRobust, episodes: List[str], batch_size: int, test_id: str) -> dict:
    """Test a specific batch size and return results."""
    batch = episodes[:batch_size]
    
    logger.info(f"[{test_id}] Starting batch of {batch_size} episodes...")
    
    start_time = datetime.now()
    result = await client.extract_batch(batch)
    duration = (datetime.now() - start_time).total_seconds()
    
    # Calculate efficiency metrics
    expected_min_entities = batch_size * 2  # At least 2 entities per episode
    extraction_rate = (result.total_entities / expected_min_entities) * 100 if expected_min_entities > 0 else 0
    entities_per_second = result.total_entities / duration if duration > 0 else 0
    api_efficiency = batch_size / 1.0  # 1 API call for N episodes
    
    logger.info(f"[{test_id}] Completed in {duration:.2f}s")
    logger.info(f"[{test_id}] Strategy: {result.parsing_metadata.get('strategy', 'unknown')}")
    logger.info(f"[{test_id}] Entities: {result.total_entities}, Relationships: {result.total_relationships}")
    logger.info(f"[{test_id}] Extraction rate: {extraction_rate:.1f}%")
    logger.info(f"[{test_id}] API efficiency: {api_efficiency:.1f}x (1 call for {batch_size} episodes)")
    
    return {
        'test_id': test_id,
        'batch_size': batch_size,
        'duration': duration,
        'total_entities': result.total_entities,
        'total_relationships': result.total_relationships,
        'extraction_rate': extraction_rate,
        'entities_per_second': entities_per_second,
        'api_efficiency': api_efficiency,
        'parsing_strategy': result.parsing_metadata.get('strategy', 'unknown'),
        'success': result.parsing_metadata.get('api_call', 'unknown') == 'success',
        'episodes': [
            {
                'index': ep.episode_index,
                'entities': len(ep.entities),
                'relationships': len(ep.relationships)
            }
            for ep in result.episodes
        ]
    }


async def run_parallel_batch_tests():
    """Run all batch tests in parallel."""
    
    # Test episodes with varying complexity
    test_episodes = [
        "Alice from TechCorp met with Bob from DataSystems to discuss the new AI platform. They plan to integrate machine learning capabilities by Q2.",
        "The quantum computing research at MIT is led by Dr. Sarah Chen. Her team collaborates with IBM Research on developing new quantum algorithms.",
        "Microsoft announced Azure OpenAI Service expansion. The service now supports GPT-4 and DALL-E 3 models for enterprise customers.",
        "Emma Thompson, CEO of StartupXYZ, secured $10M funding from Venture Partners. The company focuses on blockchain solutions for supply chain.",
        "The conference in San Francisco featured talks by Google researchers on transformer architectures and Meta's work on computer vision.",
        "Netflix is investing $2B in original content production. The company signed deals with major studios for exclusive streaming rights.",
        "Tesla's new Gigafactory in Austin will produce the Cybertruck. Elon Musk expects production to begin in late 2024.",
        "OpenAI released GPT-4 Turbo with improved performance and lower costs. Developers can access the API through Azure OpenAI Service."
    ]
    
    # Get API key
    api_key = os.getenv('CHUTES_API_KEY')
    if not api_key:
        logger.error("CHUTES_API_KEY not set")
        return
    
    client = ChutesClientRobust(api_key)
    
    logger.info("=" * 80)
    logger.info("Parallel Batch Processing Test with Chutes AI")
    logger.info("=" * 80)
    
    # Test different batch sizes in parallel
    batch_sizes = [1, 2, 3, 4, 5, 6, 7, 8]  # Including single episodes for comparison
    
    # Create tasks for parallel execution
    tasks = []
    for batch_size in batch_sizes:
        if batch_size <= len(test_episodes):
            test_id = f"BATCH-{batch_size}"
            task = test_batch_size(client, test_episodes, batch_size, test_id)
            tasks.append(task)
    
    logger.info(f"Launching {len(tasks)} parallel API calls...")
    start_time = datetime.now()
    
    # Run all tests in parallel
    try:
        results = await asyncio.gather(*tasks, return_exceptions=True)
    except Exception as e:
        logger.error(f"Parallel execution failed: {e}")
        return
    
    total_duration = (datetime.now() - start_time).total_seconds()
    
    logger.info("=" * 80)
    logger.info(f"All Tests Completed in {total_duration:.2f}s")
    logger.info("=" * 80)
    
    # Process results
    successful_results = []
    failed_results = []
    
    for result in results:
        if isinstance(result, Exception):
            logger.error(f"Task failed with exception: {result}")
            failed_results.append(result)
        elif isinstance(result, dict):
            successful_results.append(result)
        else:
            logger.warning(f"Unexpected result type: {type(result)}")
    
    if not successful_results:
        logger.error("No successful results to analyze")
        return
    
    # Sort results by batch size
    successful_results.sort(key=lambda x: x['batch_size'])
    
    # Analysis and comparison
    logger.info("\nDetailed Results:")
    logger.info("-" * 80)
    
    total_api_calls = len(successful_results)
    total_episodes_processed = sum(r['batch_size'] for r in successful_results)
    total_entities_found = sum(r['total_entities'] for r in successful_results)
    total_relationships_found = sum(r['total_relationships'] for r in successful_results)
    
    for result in successful_results:
        logger.info(f"Batch Size {result['batch_size']:2d}: "
                   f"{result['total_entities']:2d} entities, "
                   f"{result['total_relationships']:2d} relationships | "
                   f"{result['extraction_rate']:5.1f}% rate | "
                   f"{result['duration']:5.1f}s | "
                   f"Strategy: {result['parsing_strategy']}")
    
    # Calculate efficiency metrics
    logger.info("\n" + "=" * 80)
    logger.info("Efficiency Analysis")
    logger.info("=" * 80)
    
    # Compare against individual processing
    single_episode_results = [r for r in successful_results if r['batch_size'] == 1]
    if single_episode_results:
        single_avg_entities = single_episode_results[0]['total_entities']
        single_avg_duration = single_episode_results[0]['duration']
        
        logger.info(f"Single Episode Baseline:")
        logger.info(f"  Entities per episode: {single_avg_entities}")
        logger.info(f"  Duration per episode: {single_avg_duration:.2f}s")
        logger.info(f"  Projected for 8 episodes: {8 * single_avg_duration:.2f}s, {8} API calls")
    
    # Best batch performance
    best_efficiency = max(successful_results, key=lambda x: x['api_efficiency'])
    best_extraction = max(successful_results, key=lambda x: x['extraction_rate'])
    
    logger.info(f"\nBest API Efficiency:")
    logger.info(f"  Batch size {best_efficiency['batch_size']}: {best_efficiency['api_efficiency']:.1f}x efficiency")
    logger.info(f"  {best_efficiency['total_entities']} entities in {best_efficiency['duration']:.2f}s")
    
    logger.info(f"\nBest Extraction Rate:")
    logger.info(f"  Batch size {best_extraction['batch_size']}: {best_extraction['extraction_rate']:.1f}% rate")
    logger.info(f"  {best_extraction['total_entities']} entities, {best_extraction['total_relationships']} relationships")
    
    # Overall statistics
    avg_entities_per_episode = total_entities_found / total_episodes_processed if total_episodes_processed > 0 else 0
    quota_savings = ((total_episodes_processed - total_api_calls) / total_episodes_processed) * 100 if total_episodes_processed > 0 else 0
    
    logger.info(f"\nOverall Performance:")
    logger.info(f"  Total episodes processed: {total_episodes_processed}")
    logger.info(f"  Total API calls made: {total_api_calls}")
    logger.info(f"  Quota savings: {quota_savings:.1f}%")
    logger.info(f"  Average entities per episode: {avg_entities_per_episode:.1f}")
    logger.info(f"  Total extraction time: {total_duration:.2f}s (parallel)")
    
    # Parsing strategy analysis
    strategy_counts = {}
    for result in successful_results:
        strategy = result['parsing_strategy']
        strategy_counts[strategy] = strategy_counts.get(strategy, 0) + 1
    
    logger.info(f"\nParsing Strategy Distribution:")
    for strategy, count in strategy_counts.items():
        percentage = (count / len(successful_results)) * 100
        logger.info(f"  {strategy}: {count}/{len(successful_results)} ({percentage:.1f}%)")
    
    if failed_results:
        logger.info(f"\nFailed Tests: {len(failed_results)}")
        for i, error in enumerate(failed_results):
            logger.info(f"  {i+1}: {error}")
    
    # Test error recovery with sample responses
    logger.info("\n" + "=" * 80)
    logger.info("Error Recovery Test")
    logger.info("=" * 80)
    
    # Test our robust parser with various response formats
    from test_chutes_batch_robust_parsing import RobustJSONParser
    
    parser = RobustJSONParser()
    test_responses = [
        ('Perfect JSON', '{"episodes": [{"entities": [{"name": "Alice", "type": "person"}], "relationships": []}]}'),
        ('Markdown Wrapped', '```json\n{"episodes": [{"entities": [{"name": "Bob", "type": "person"}]}]}\n```'),
        ('Partial Response', '{"episodes": [{"entities": [{"name": "Charlie", "type": "pers'),
        ('Text Format', 'Episode 0:\nEntity: David (person)\nRelationship: David -> Company (WORKS_FOR)'),
    ]
    
    for name, response in test_responses:
        result = parser.parse(response, expected_episodes=1)
        logger.info(f"{name:15s}: {result.total_entities} entities, strategy: {result.parsing_metadata.get('strategy', 'unknown')}")


if __name__ == "__main__":
    asyncio.run(run_parallel_batch_tests())