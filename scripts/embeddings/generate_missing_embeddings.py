#!/usr/bin/env python3
"""
Generate embeddings for edges that are missing them.
This script will process all edges with NULL fact_embedding and generate embeddings using the configured embedder.
"""

import asyncio
import os
import sys
from typing import List, Dict, Any
import logging
from datetime import datetime
import time

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from graphiti_core.driver.falkordb_driver import FalkorDriver
from graphiti_core.embedder import EmbedderClient
from graphiti_core.llm_client import LLMClient
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def generate_missing_embeddings(dry_run: bool = False, batch_size: int = 50, limit: int = None):
    """
    Generate embeddings for edges that don't have them.
    
    Args:
        dry_run: If True, only show what would be done without updating
        batch_size: Number of edges to process in each batch
        limit: Maximum number of edges to process (None for all)
    """
    
    # Initialize driver
    driver = FalkorDriver(
        host='localhost',
        port=6379,
        database='graphiti_migration'
    )
    
    # Initialize embedder - using the same configuration as the main system
    use_ollama = os.getenv('USE_OLLAMA', 'false').lower() == 'true'
    
    if use_ollama:
        logger.info("Using Ollama embedder")
        embedder = EmbedderClient(
            base_url=os.getenv('OLLAMA_EMBEDDING_URL', 'http://192.168.50.90:11435'),
            embedder_type='ollama'
        )
    else:
        logger.info("Using OpenAI embedder")
        embedder = EmbedderClient(
            api_key=os.getenv('OPENAI_API_KEY'),
            embedder_type='openai'
        )
    
    print("\n" + "="*80)
    print("EMBEDDING GENERATION FOR EDGES WITHOUT EMBEDDINGS")
    print("="*80 + "\n")
    
    # Step 1: Count edges without embeddings
    print("Step 1: Counting edges without embeddings...")
    print("-" * 50)
    
    count_query = """
    MATCH ()-[e:RELATES_TO]->()
    WHERE e.fact_embedding IS NULL AND e.fact IS NOT NULL AND e.fact <> ''
    RETURN count(e) as total
    """
    
    results, _, _ = await driver.execute_query(count_query)
    total_edges = results[0]['total'] if results else 0
    
    print(f"Found {total_edges} edges with facts but no embeddings\n")
    
    if total_edges == 0:
        print("No edges need embedding generation!")
        await driver.close()
        return
    
    # Apply limit if specified
    edges_to_process = min(total_edges, limit) if limit else total_edges
    
    if dry_run:
        print(f"DRY RUN MODE - Would process {edges_to_process} edges")
    else:
        print(f"Will process {edges_to_process} edges in batches of {batch_size}")
    
    # Step 2: Process edges in batches
    print("\nStep 2: Processing edges in batches...")
    print("-" * 50)
    
    processed = 0
    updated = 0
    failed = 0
    start_time = time.time()
    
    while processed < edges_to_process:
        # Get batch of edges without embeddings
        batch_query = """
        MATCH ()-[e:RELATES_TO]->()
        WHERE e.fact_embedding IS NULL AND e.fact IS NOT NULL AND e.fact <> ''
        RETURN 
            e.uuid as uuid,
            e.fact as fact,
            e.name as name,
            e.group_id as group_id
        LIMIT $batch_size
        """
        
        results, _, _ = await driver.execute_query(batch_query, batch_size=batch_size)
        
        if not results:
            print("No more edges to process")
            break
        
        print(f"\nProcessing batch {processed // batch_size + 1} ({len(results)} edges)...")
        
        # Generate embeddings for this batch
        facts = [r['fact'] for r in results]
        
        if not dry_run:
            try:
                # Generate embeddings in batch
                embeddings = await embedder.embed(facts)
                
                # Update each edge with its embedding
                for i, result in enumerate(results):
                    update_query = """
                    MATCH ()-[e:RELATES_TO {uuid: $uuid}]->()
                    SET e.fact_embedding = vecf32($embedding)
                    RETURN e.uuid as uuid
                    """
                    
                    try:
                        _, _, _ = await driver.execute_query(
                            update_query,
                            uuid=result['uuid'],
                            embedding=embeddings[i]
                        )
                        updated += 1
                        
                        if updated % 10 == 0:
                            print(f"  Updated {updated} edges...")
                            
                    except Exception as e:
                        logger.error(f"Failed to update edge {result['uuid']}: {e}")
                        failed += 1
                
            except Exception as e:
                logger.error(f"Failed to generate embeddings for batch: {e}")
                failed += len(results)
        else:
            # Dry run - just show what would be done
            for result in results:
                print(f"  Would generate embedding for edge {result['uuid'][:8]}... ({result['name']})")
                print(f"    Fact: {result['fact'][:100]}...")
        
        processed += len(results)
        
        # Progress report
        elapsed = time.time() - start_time
        rate = processed / elapsed if elapsed > 0 else 0
        eta = (edges_to_process - processed) / rate if rate > 0 else 0
        
        print(f"\nProgress: {processed}/{edges_to_process} edges processed")
        print(f"Updated: {updated}, Failed: {failed}")
        print(f"Rate: {rate:.1f} edges/sec, ETA: {eta:.1f} seconds")
        
        # Small delay to avoid overwhelming the embedding service
        if not dry_run and processed < edges_to_process:
            await asyncio.sleep(0.1)
    
    # Step 3: Verify results
    print("\n\nStep 3: Verification...")
    print("-" * 50)
    
    # Count remaining edges without embeddings
    verify_query = """
    MATCH ()-[e:RELATES_TO]->()
    WHERE e.fact_embedding IS NULL AND e.fact IS NOT NULL AND e.fact <> ''
    RETURN count(e) as remaining
    """
    
    results, _, _ = await driver.execute_query(verify_query)
    remaining = results[0]['remaining'] if results else 0
    
    # Count edges with embeddings
    with_embeddings_query = """
    MATCH ()-[e:RELATES_TO]->()
    WHERE e.fact_embedding IS NOT NULL
    RETURN count(e) as total
    """
    
    results, _, _ = await driver.execute_query(with_embeddings_query)
    total_with_embeddings = results[0]['total'] if results else 0
    
    await driver.close()
    
    # Final report
    print("\n" + "="*80)
    print("EMBEDDING GENERATION COMPLETE")
    print("="*80 + "\n")
    
    if not dry_run:
        print(f"Results:")
        print(f"  Processed: {processed} edges")
        print(f"  Successfully updated: {updated} edges")
        print(f"  Failed: {failed} edges")
        print(f"  Remaining without embeddings: {remaining} edges")
        print(f"  Total edges with embeddings: {total_with_embeddings}")
        print(f"  Time taken: {time.time() - start_time:.2f} seconds")
    else:
        print(f"DRY RUN - Would have processed {processed} edges")
        print(f"Currently {total_edges} edges need embeddings")
        print(f"Currently {total_with_embeddings} edges have embeddings")
    
    return updated, failed, remaining


async def main():
    """Main entry point with command line arguments"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Generate embeddings for edges that are missing them')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done without updating')
    parser.add_argument('--batch-size', type=int, default=50, help='Number of edges to process in each batch')
    parser.add_argument('--limit', type=int, help='Maximum number of edges to process')
    
    args = parser.parse_args()
    
    try:
        updated, failed, remaining = await generate_missing_embeddings(
            dry_run=args.dry_run,
            batch_size=args.batch_size,
            limit=args.limit
        )
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Failed to generate embeddings: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())