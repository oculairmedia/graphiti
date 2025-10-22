#!/usr/bin/env python3
"""
Regenerate embeddings for all Episodic nodes using Ollama.
This script will regenerate embeddings for Episodic nodes which represent events/episodes.
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


async def regenerate_episodic_embeddings(
    dry_run: bool = False, 
    batch_size: int = 50, 
    limit: Optional[int] = None,
    force_regenerate: bool = False
):
    """
    Regenerate embeddings for Episodic nodes.
    
    Args:
        dry_run: If True, only show what would be done without updating
        batch_size: Number of nodes to process in each batch
        limit: Maximum number of nodes to process (None for all)
        force_regenerate: If True, regenerate ALL nodes. If False, only missing ones.
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
    print("EPISODIC NODE EMBEDDING REGENERATION WITH OLLAMA")
    print("="*80 + "\n")
    print(f"Ollama URL: {ollama_base_url}")
    print(f"Embedding Model: {ollama_model}")
    print(f"Force Regenerate: {force_regenerate}")
    print(f"Dry Run: {dry_run}")
    
    # Step 1: Count nodes to process
    print("\nStep 1: Counting Episodic nodes to process...")
    print("-" * 50)
    
    if force_regenerate:
        count_query = """
        MATCH (n:Episodic)
        WHERE n.content IS NOT NULL AND n.content <> ''
        RETURN count(n) as total
        """
        description = "Episodic nodes with content (will regenerate ALL)"
    else:
        count_query = """
        MATCH (n:Episodic)
        WHERE n.content_embedding IS NULL AND n.content IS NOT NULL AND n.content <> ''
        RETURN count(n) as total
        """
        description = "Episodic nodes with content but no embeddings"
    
    results, _, _ = await driver.execute_query(count_query)
    total_nodes = results[0]['total'] if results else 0
    
    print(f"Found {total_nodes} {description}\n")
    
    if total_nodes == 0:
        print("No Episodic nodes need processing!")
        await driver.close()
        return 0, 0, 0
    
    # Apply limit if specified
    nodes_to_process = min(total_nodes, limit) if limit else total_nodes
    
    if dry_run:
        print(f"DRY RUN MODE - Would process {nodes_to_process} nodes")
    else:
        print(f"Will process {nodes_to_process} nodes in batches of {batch_size}")
    
    # Step 2: Process nodes in batches
    print("\nStep 2: Processing Episodic nodes in batches...")
    print("-" * 50)
    
    processed = 0
    updated = 0
    failed = 0
    start_time = time.time()
    
    while processed < nodes_to_process:
        # Get batch of nodes to process
        if force_regenerate:
            batch_query = """
            MATCH (n:Episodic)
            WHERE n.content IS NOT NULL AND n.content <> ''
            RETURN 
                n.uuid as uuid,
                n.content as content,
                n.group_id as group_id,
                n.content_embedding IS NOT NULL as has_embedding
            ORDER BY n.created_at DESC
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
            MATCH (n:Episodic)
            WHERE n.content_embedding IS NULL AND n.content IS NOT NULL AND n.content <> ''
            RETURN 
                n.uuid as uuid,
                n.content as content,
                n.group_id as group_id,
                false as has_embedding
            ORDER BY n.created_at DESC
            LIMIT $batch_size
            """
            results, _, _ = await driver.execute_query(batch_query, batch_size=batch_size)
        
        if not results:
            print("No more Episodic nodes to process")
            break
        
        print(f"\nProcessing batch {processed // batch_size + 1} ({len(results)} nodes)...")
        
        if force_regenerate and not dry_run:
            existing_count = sum(1 for r in results if r.get('has_embedding', False))
            if existing_count > 0:
                print(f"  Note: {existing_count} nodes already have embeddings (will regenerate)")
        
        # Generate embeddings for this batch
        contents = [r['content'] for r in results]
        
        if not dry_run:
            try:
                # Generate embeddings in batch
                embeddings = await embedder.create_batch(contents)
                
                # Update each node with its embedding
                for i, result in enumerate(results):
                    update_query = """
                    MATCH (n:Episodic {uuid: $uuid})
                    SET n.content_embedding = vecf32($embedding)
                    RETURN n.uuid as uuid
                    """
                    
                    try:
                        _, _, _ = await driver.execute_query(
                            update_query,
                            uuid=result['uuid'],
                            embedding=embeddings[i]
                        )
                        updated += 1
                        
                        if updated % 10 == 0:
                            print(f"  Updated {updated} nodes...")
                            
                    except Exception as e:
                        logger.error(f"Failed to update node {result['uuid']}: {e}")
                        failed += 1
                
            except Exception as e:
                logger.error(f"Failed to generate embeddings for batch: {e}")
                failed += len(results)
        else:
            # Dry run - just show what would be done
            for result in results:
                content_preview = result['content'][:80] if len(result['content']) > 80 else result['content']
                print(f"  Would generate embedding for node {result['uuid'][:8]}...")
                print(f"    Content: {content_preview}...")
        
        processed += len(results)
        
        # Progress report
        elapsed = time.time() - start_time
        rate = processed / elapsed if elapsed > 0 else 0
        eta = (nodes_to_process - processed) / rate if rate > 0 else 0
        
        print(f"\nProgress: {processed}/{nodes_to_process} nodes processed")
        if not dry_run:
            print(f"Updated: {updated}, Failed: {failed}")
        print(f"Rate: {rate:.1f} nodes/sec, ETA: {eta:.1f} seconds")
        
        # Small delay to avoid overwhelming the embedding service
        if not dry_run and processed < nodes_to_process:
            await asyncio.sleep(0.1)
    
    # Step 3: Verify results
    print("\n\nStep 3: Verification...")
    print("-" * 50)
    
    # Count remaining nodes without embeddings
    verify_query = """
    MATCH (n:Episodic)
    WHERE n.content_embedding IS NULL AND n.content IS NOT NULL AND n.content <> ''
    RETURN count(n) as remaining
    """
    
    results, _, _ = await driver.execute_query(verify_query)
    remaining = results[0]['remaining'] if results else 0
    
    # Count nodes with embeddings
    with_embeddings_query = """
    MATCH (n:Episodic)
    WHERE n.content_embedding IS NOT NULL
    RETURN count(n) as total
    """
    
    results, _, _ = await driver.execute_query(with_embeddings_query)
    total_with_embeddings = results[0]['total'] if results else 0
    
    # Get sample embedded node to verify dimensions
    sample_query = """
    MATCH (n:Episodic)
    WHERE n.content_embedding IS NOT NULL
    RETURN n.content, size(n.content_embedding) as embedding_dim
    LIMIT 1
    """
    
    results, _, _ = await driver.execute_query(sample_query)
    if results and not dry_run:
        sample = results[0]
        print(f"\nSample embedded Episodic node:")
        content_preview = sample['content'][:100] if len(sample['content']) > 100 else sample['content']
        print(f"  Content: {content_preview}...")
        print(f"  Embedding dimensions: {sample['embedding_dim']}")
    
    await driver.close()
    
    # Final report
    print("\n" + "="*80)
    print("EPISODIC NODE EMBEDDING REGENERATION COMPLETE")
    print("="*80 + "\n")
    
    if not dry_run:
        print(f"Results:")
        print(f"  Processed: {processed} nodes")
        print(f"  Successfully updated: {updated} nodes")
        print(f"  Failed: {failed} nodes")
        print(f"  Remaining without embeddings: {remaining} nodes")
        print(f"  Total Episodic nodes with embeddings: {total_with_embeddings}")
        print(f"  Time taken: {time.time() - start_time:.2f} seconds")
    else:
        print(f"DRY RUN - Would have processed {processed} nodes")
        print(f"Currently {total_nodes} nodes need processing")
        print(f"Currently {total_with_embeddings} nodes have embeddings")
    
    return updated, failed, remaining


async def main():
    """Main entry point with command line arguments"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Regenerate Episodic node embeddings using Ollama')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done without updating')
    parser.add_argument('--batch-size', type=int, default=50, help='Number of nodes to process in each batch')
    parser.add_argument('--limit', type=int, help='Maximum number of nodes to process')
    parser.add_argument('--force-regenerate', action='store_true', 
                       help='Regenerate ALL nodes, not just missing ones')
    
    args = parser.parse_args()
    
    try:
        print(f"Configuration:")
        print(f"  Ollama Embeddings: {os.getenv('USE_OLLAMA_EMBEDDINGS', 'false')}")
        print(f"  Ollama Base URL: {os.getenv('OLLAMA_BASE_URL', 'not set')}")
        print(f"  Embedding URL: {os.getenv('OLLAMA_EMBEDDING_BASE_URL', 'not set')}")
        print(f"  Embedding Model: {os.getenv('OLLAMA_EMBEDDING_MODEL', 'not set')}")
        print(f"  FalkorDB Host: localhost")
        print(f"  Database: graphiti_migration")
        print()
        
        updated, failed, remaining = await regenerate_episodic_embeddings(
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
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())