#!/usr/bin/env python3
"""
Regenerate embeddings for all edges using Ollama.
This script will regenerate embeddings for ALL edges, not just missing ones.
Useful for when you want to switch embedding models or regenerate with updated models.
"""

import asyncio
import os
import sys
from typing import List, Dict, Any, Optional
import logging
from datetime import datetime
import time
from openai import AsyncOpenAI

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from graphiti_core.driver.falkordb_driver import FalkorDriver
from graphiti_core.embedder.client import EmbedderClient
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class OllamaEmbedder(EmbedderClient):
    """Custom embedder that uses Ollama for embeddings."""

    def __init__(self, base_url: str, model: str = 'dengcao/Qwen3-Embedding-4B:Q4_K_M'):
        self.base_url = base_url
        self.model = model
        self.client = AsyncOpenAI(base_url=base_url, api_key='ollama')
        logger.info(f'✓ Initialized OllamaEmbedder with model: {model} at {base_url}')

    async def create(self, input_data: str | list[str]) -> list[float]:
        """Create embeddings using Ollama for single input."""
        try:
            if isinstance(input_data, str):
                input_data = [input_data]
            
            response = await self.client.embeddings.create(model=self.model, input=input_data)
            return response.data[0].embedding
        except Exception as e:
            logger.error(f'❌ Error creating embedding: {e}')
            raise

    async def create_batch(self, input_data_list: list[str]) -> list[list[float]]:
        """Create embeddings using Ollama for batch input."""
        try:
            response = await self.client.embeddings.create(model=self.model, input=input_data_list)
            return [item.embedding for item in response.data]
        except Exception as e:
            logger.error(f'❌ Error creating batch embeddings: {e}')
            raise


async def regenerate_edge_embeddings(
    dry_run: bool = False, 
    batch_size: int = 50, 
    limit: Optional[int] = None,
    force_regenerate: bool = False
):
    """
    Regenerate embeddings for edges.
    
    Args:
        dry_run: If True, only show what would be done without updating
        batch_size: Number of edges to process in each batch
        limit: Maximum number of edges to process (None for all)
        force_regenerate: If True, regenerate ALL edges. If False, only missing ones.
    """
    
    # Initialize driver
    driver = FalkorDriver(
        host='localhost',  # Use localhost directly
        port=6379,
        database='graphiti_migration'  # Use the actual database name
    )

    # Initialize Ollama embedder - use dedicated embedding endpoint if available
    use_dedicated = os.getenv('USE_DEDICATED_EMBEDDING_ENDPOINT', 'true').lower() == 'true'
    if use_dedicated:
        ollama_base_url = os.getenv('OLLAMA_EMBEDDING_BASE_URL', 'http://100.81.139.20:11434/v1')
    else:
        ollama_base_url = os.getenv('OLLAMA_BASE_URL', 'http://100.81.139.20:11434/v1')

    ollama_model = os.getenv('OLLAMA_EMBEDDING_MODEL', 'dengcao/Qwen3-Embedding-4B:Q4_K_M')
    
    embedder = OllamaEmbedder(
        base_url=ollama_base_url,
        model=ollama_model
    )
    
    print("\n" + "="*80)
    print("EDGE EMBEDDING REGENERATION WITH OLLAMA")
    print("="*80 + "\n")
    print(f"Ollama URL: {ollama_base_url}")
    print(f"Embedding Model: {ollama_model}")
    print(f"Force Regenerate: {force_regenerate}")
    print(f"Dry Run: {dry_run}")
    
    # Step 1: Count edges to process
    print("\nStep 1: Counting edges to process...")
    print("-" * 50)
    
    if force_regenerate:
        count_query = """
        MATCH ()-[e:RELATES_TO]->()
        WHERE e.fact IS NOT NULL AND e.fact <> ''
        RETURN count(e) as total
        """
        description = "edges with facts (will regenerate ALL)"
    else:
        count_query = """
        MATCH ()-[e:RELATES_TO]->()
        WHERE e.fact_embedding IS NULL AND e.fact IS NOT NULL AND e.fact <> ''
        RETURN count(e) as total
        """
        description = "edges with facts but no embeddings"
    
    results, _, _ = await driver.execute_query(count_query)
    total_edges = results[0]['total'] if results else 0
    
    print(f"Found {total_edges} {description}\n")
    
    if total_edges == 0:
        print("No edges need processing!")
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
        # Get batch of edges to process
        if force_regenerate:
            batch_query = """
            MATCH ()-[e:RELATES_TO]->()
            WHERE e.fact IS NOT NULL AND e.fact <> ''
            RETURN 
                e.uuid as uuid,
                e.fact as fact,
                e.name as name,
                e.group_id as group_id,
                e.fact_embedding IS NOT NULL as has_embedding
            ORDER BY e.created_at DESC
            SKIP $skip
            LIMIT $batch_size
            """
            results, _, _ = await driver.execute_query(
                batch_query, 
                skip=processed,
                batch_size=batch_size
            )
        else:
            batch_query = """
            MATCH ()-[e:RELATES_TO]->()
            WHERE e.fact_embedding IS NULL AND e.fact IS NOT NULL AND e.fact <> ''
            RETURN 
                e.uuid as uuid,
                e.fact as fact,
                e.name as name,
                e.group_id as group_id,
                false as has_embedding
            ORDER BY e.created_at DESC
            LIMIT $batch_size
            """
            results, _, _ = await driver.execute_query(batch_query, batch_size=batch_size)
        
        if not results:
            print("No more edges to process")
            break
        
        print(f"\nProcessing batch {processed // batch_size + 1} ({len(results)} edges)...")
        
        if force_regenerate and not dry_run:
            existing_count = sum(1 for r in results if r.get('has_embedding', False))
            if existing_count > 0:
                print(f"  Note: {existing_count} edges already have embeddings (will regenerate)")
        
        # Generate embeddings for this batch
        facts = [r['fact'] for r in results]
        
        if not dry_run:
            try:
                # Generate embeddings in batch
                embeddings = await embedder.create_batch(facts)
                
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
    print("EDGE EMBEDDING REGENERATION COMPLETE")
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
        print(f"Currently {total_edges} edges need processing")
        print(f"Currently {total_with_embeddings} edges have embeddings")
    
    return updated, failed, remaining


async def main():
    """Main entry point with command line arguments"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Regenerate edge embeddings using Ollama')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done without updating')
    parser.add_argument('--batch-size', type=int, default=50, help='Number of edges to process in each batch')
    parser.add_argument('--limit', type=int, help='Maximum number of edges to process')
    parser.add_argument('--force-regenerate', action='store_true', 
                       help='Regenerate ALL edges, not just missing ones')
    
    args = parser.parse_args()
    
    try:
        updated, failed, remaining = await regenerate_edge_embeddings(
            dry_run=args.dry_run,
            batch_size=args.batch_size,
            limit=args.limit,
            force_regenerate=args.force_regenerate
        )
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Failed to regenerate embeddings: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
