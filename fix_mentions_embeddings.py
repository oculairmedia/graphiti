#!/usr/bin/env python3
"""
Generate embeddings for MENTIONS edges that are missing embeddings.
"""

import asyncio
import os
import sys
import time
from typing import List
import logging
from datetime import datetime
from openai import AsyncOpenAI

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from graphiti_core.driver.falkordb_driver import FalkorDriver
from graphiti_core.embedder.client import EmbedderClient
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO)
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


async def fix_mentions_embeddings():
    """Generate embeddings for MENTIONS edges missing embeddings."""
    
    print("\n🔧 FIXING MENTIONS EDGE EMBEDDINGS")
    print("=" * 50)
    
    # Initialize driver
    driver = FalkorDriver(
        host='localhost',
        port=6379,
        database='graphiti_migration'
    )
    
    # Initialize embedder
    ollama_base_url = os.getenv('OLLAMA_EMBEDDING_BASE_URL', 'http://100.81.139.20:11434/v1')
    ollama_model = os.getenv('OLLAMA_EMBEDDING_MODEL', 'dengcao/Qwen3-Embedding-4B:Q4_K_M')
    embedder = OllamaEmbedder(base_url=ollama_base_url, model=ollama_model)
    
    # Get MENTIONS edges without embeddings
    query = """
    MATCH ()-[e:MENTIONS]->()
    WHERE e.fact_embedding IS NULL AND e.fact IS NOT NULL AND e.fact <> ''
    RETURN e.uuid as uuid, e.fact as fact
    """
    
    results, _, _ = await driver.execute_query(query)
    total_edges = len(results)
    
    print(f"Found {total_edges} MENTIONS edges missing embeddings")
    
    if total_edges == 0:
        print("✅ All MENTIONS edges already have embeddings!")
        await driver.close()
        return
    
    # Process in batches
    batch_size = 50
    updated = 0
    failed = 0
    start_time = time.time()
    
    for i in range(0, total_edges, batch_size):
        batch = results[i:i + batch_size]
        facts = [edge['fact'] for edge in batch]
        
        print(f"Processing batch {i // batch_size + 1} ({len(batch)} edges)...")
        
        try:
            # Generate embeddings
            embeddings = await embedder.create_batch(facts)
            
            # Update each edge
            for j, edge in enumerate(batch):
                update_query = """
                MATCH ()-[e:MENTIONS {uuid: $uuid}]->()
                SET e.fact_embedding = vecf32($embedding)
                RETURN e.uuid as uuid
                """
                
                try:
                    await driver.execute_query(
                        update_query,
                        uuid=edge['uuid'],
                        embedding=embeddings[j]
                    )
                    updated += 1
                except Exception as e:
                    logger.error(f"Failed to update edge {edge['uuid']}: {e}")
                    failed += 1
            
            if updated % 100 == 0:
                print(f"  ✅ Updated {updated} edges...")
        
        except Exception as e:
            logger.error(f"Failed to generate embeddings for batch: {e}")
            failed += len(batch)
        
        # Progress report
        processed = min(i + batch_size, total_edges)
        elapsed = time.time() - start_time
        rate = processed / elapsed if elapsed > 0 else 0
        eta = (total_edges - processed) / rate if rate > 0 else 0
        
        print(f"Progress: {processed}/{total_edges} | Rate: {rate:.1f}/sec | ETA: {eta:.0f}s")
        
        await asyncio.sleep(0.1)  # Small delay
    
    await driver.close()
    
    duration = time.time() - start_time
    print(f"\n📊 FINAL RESULTS:")
    print(f"  Updated: {updated}")
    print(f"  Failed: {failed}")
    print(f"  Time: {duration:.1f} seconds")
    
    if failed == 0:
        print("🎉 All MENTIONS embeddings successfully generated!")
    else:
        print(f"⚠️  {failed} embeddings failed")


if __name__ == "__main__":
    try:
        asyncio.run(fix_mentions_embeddings())
    except KeyboardInterrupt:
        print("\nInterrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)