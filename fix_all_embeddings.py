#!/usr/bin/env python3
"""
Fix ALL embeddings by ensuring every single node and edge has an embedding.
This script will:
1. Find ALL nodes (not just those with missing embeddings)
2. Find ALL edges (not just those with missing embeddings)
3. Generate embeddings for everything with proper 2560 dimensions
"""

import asyncio
import os
import sys
import time
from typing import List, Dict, Any, Optional
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
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ANSI color codes
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def print_header(text: str):
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*80}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{text.center(80)}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*80}{Colors.ENDC}\n")

def print_section(text: str):
    print(f"\n{Colors.CYAN}{Colors.BOLD}{text}{Colors.ENDC}")
    print(f"{Colors.CYAN}{'-'*50}{Colors.ENDC}")

def print_success(text: str):
    print(f"{Colors.GREEN}✅ {text}{Colors.ENDC}")

def print_error(text: str):
    print(f"{Colors.RED}❌ {text}{Colors.ENDC}")

def print_info(text: str):
    print(f"{Colors.BLUE}ℹ️  {text}{Colors.ENDC}")

def print_warning(text: str):
    print(f"{Colors.YELLOW}⚠️  {text}{Colors.ENDC}")


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


async def fix_all_node_embeddings(driver, embedder, batch_size: int = 50):
    """Generate embeddings for ALL nodes."""
    
    print_section("FIXING ALL NODE EMBEDDINGS")
    
    # Count ALL nodes (not just those without embeddings)
    count_query = """
    MATCH (n:Entity)
    RETURN count(n) as total
    """
    results, _, _ = await driver.execute_query(count_query)
    total_nodes = results[0]['total'] if results else 0
    
    # Count nodes with existing embeddings
    with_embeddings_query = """
    MATCH (n:Entity)
    WHERE n.name_embedding IS NOT NULL
    RETURN count(n) as total
    """
    results, _, _ = await driver.execute_query(with_embeddings_query)
    nodes_with_embeddings = results[0]['total'] if results else 0
    
    print_info(f"Total nodes in database: {total_nodes}")
    print_info(f"Nodes with embeddings: {nodes_with_embeddings}")
    print_warning(f"Nodes missing embeddings: {total_nodes - nodes_with_embeddings}")
    
    if total_nodes == 0:
        print_warning("No nodes found in database")
        return 0, 0
    
    processed = 0
    updated = 0
    failed = 0
    start_time = time.time()
    
    # Process ALL nodes in batches
    while processed < total_nodes:
        # Get batch of ALL nodes (not filtering by missing embeddings)
        batch_query = """
        MATCH (n:Entity)
        RETURN 
            n.uuid as uuid,
            n.name as name,
            n.name_embedding IS NOT NULL as has_embedding
        ORDER BY n.created_at DESC
        SKIP $skip
        LIMIT $batch_size
        """
        
        results, _, _ = await driver.execute_query(
            batch_query, 
            skip=processed,
            batch_size=batch_size
        )
        
        if not results:
            break
        
        print(f"\nProcessing batch {processed // batch_size + 1} ({len(results)} nodes)...")
        
        # Filter for nodes that need embeddings or have empty names
        nodes_to_embed = []
        for r in results:
            if r.get('name') and r['name'].strip():  # Only process nodes with valid names
                nodes_to_embed.append(r)
        
        if nodes_to_embed:
            names = [r['name'] for r in nodes_to_embed]
            
            try:
                # Generate embeddings in batch
                embeddings = await embedder.create_batch(names)
                
                # Update each node with its embedding
                for i, node in enumerate(nodes_to_embed):
                    update_query = """
                    MATCH (n:Entity {uuid: $uuid})
                    SET n.name_embedding = vecf32($embedding)
                    RETURN n.uuid as uuid
                    """
                    
                    try:
                        _, _, _ = await driver.execute_query(
                            update_query,
                            uuid=node['uuid'],
                            embedding=embeddings[i]
                        )
                        updated += 1
                        
                        if updated % 100 == 0:
                            print(f"  Updated {updated} nodes...")
                            
                    except Exception as e:
                        logger.error(f"Failed to update node {node['uuid']}: {e}")
                        failed += 1
                
            except Exception as e:
                logger.error(f"Failed to generate embeddings for batch: {e}")
                failed += len(nodes_to_embed)
        
        processed += len(results)
        
        # Progress report
        elapsed = time.time() - start_time
        rate = processed / elapsed if elapsed > 0 else 0
        eta = (total_nodes - processed) / rate if rate > 0 else 0
        
        print(f"Progress: {processed}/{total_nodes} nodes processed")
        print(f"Updated: {updated}, Failed: {failed}")
        print(f"Rate: {rate:.1f} nodes/sec, ETA: {eta:.1f} seconds")
        
        # Small delay to avoid overwhelming the embedding service
        if processed < total_nodes:
            await asyncio.sleep(0.1)
    
    return updated, failed


async def fix_all_edge_embeddings(driver, embedder, batch_size: int = 50):
    """Generate embeddings for ALL edges."""
    
    print_section("FIXING ALL EDGE EMBEDDINGS")
    
    # Count ALL edges
    count_query = """
    MATCH ()-[e:RELATES_TO]->()
    RETURN count(e) as total
    """
    results, _, _ = await driver.execute_query(count_query)
    total_edges = results[0]['total'] if results else 0
    
    # Count edges with existing embeddings
    with_embeddings_query = """
    MATCH ()-[e:RELATES_TO]->()
    WHERE e.fact_embedding IS NOT NULL
    RETURN count(e) as total
    """
    results, _, _ = await driver.execute_query(with_embeddings_query)
    edges_with_embeddings = results[0]['total'] if results else 0
    
    print_info(f"Total edges in database: {total_edges}")
    print_info(f"Edges with embeddings: {edges_with_embeddings}")
    print_warning(f"Edges missing embeddings: {total_edges - edges_with_embeddings}")
    
    if total_edges == 0:
        print_warning("No edges found in database")
        return 0, 0
    
    processed = 0
    updated = 0
    failed = 0
    start_time = time.time()
    
    # Process ALL edges in batches
    while processed < total_edges:
        # Get batch of ALL edges
        batch_query = """
        MATCH (s)-[e:RELATES_TO]->(t)
        RETURN 
            e.uuid as uuid,
            e.fact as fact,
            e.fact_embedding IS NOT NULL as has_embedding,
            s.name as source_name,
            t.name as target_name
        SKIP $skip
        LIMIT $batch_size
        """
        
        results, _, _ = await driver.execute_query(
            batch_query,
            skip=processed,
            batch_size=batch_size
        )
        
        if not results:
            break
        
        print(f"\nProcessing batch {processed // batch_size + 1} ({len(results)} edges)...")
        
        # Process all edges with valid facts
        edges_to_embed = []
        for r in results:
            if r.get('fact') and r['fact'].strip():  # Only process edges with valid facts
                edges_to_embed.append(r)
        
        if edges_to_embed:
            facts = [r['fact'] for r in edges_to_embed]
            
            try:
                # Generate embeddings in batch
                embeddings = await embedder.create_batch(facts)
                
                # Update each edge with its embedding
                for i, edge in enumerate(edges_to_embed):
                    update_query = """
                    MATCH ()-[e:RELATES_TO {uuid: $uuid}]->()
                    SET e.fact_embedding = vecf32($embedding)
                    RETURN e.uuid as uuid
                    """
                    
                    try:
                        _, _, _ = await driver.execute_query(
                            update_query,
                            uuid=edge['uuid'],
                            embedding=embeddings[i]
                        )
                        updated += 1
                        
                        if updated % 100 == 0:
                            print(f"  Updated {updated} edges...")
                            
                    except Exception as e:
                        logger.error(f"Failed to update edge {edge['uuid']}: {e}")
                        failed += 1
                
            except Exception as e:
                logger.error(f"Failed to generate embeddings for batch: {e}")
                failed += len(edges_to_embed)
        
        processed += len(results)
        
        # Progress report
        elapsed = time.time() - start_time
        rate = processed / elapsed if elapsed > 0 else 0
        eta = (total_edges - processed) / rate if rate > 0 else 0
        
        print(f"Progress: {processed}/{total_edges} edges processed")
        print(f"Updated: {updated}, Failed: {failed}")
        print(f"Rate: {rate:.1f} edges/sec, ETA: {eta:.1f} seconds")
        
        # Small delay to avoid overwhelming the embedding service
        if processed < total_edges:
            await asyncio.sleep(0.1)
    
    return updated, failed


async def fix_all_episodic_embeddings(driver, embedder, batch_size: int = 50):
    """Generate embeddings for ALL episodic nodes."""
    
    print_section("FIXING ALL EPISODIC NODE EMBEDDINGS")
    
    # Count ALL episodic nodes
    count_query = """
    MATCH (n:Episodic)
    RETURN count(n) as total
    """
    results, _, _ = await driver.execute_query(count_query)
    total_nodes = results[0]['total'] if results else 0
    
    # Count episodic nodes with existing embeddings
    with_embeddings_query = """
    MATCH (n:Episodic)
    WHERE n.content_embedding IS NOT NULL
    RETURN count(n) as total
    """
    results, _, _ = await driver.execute_query(with_embeddings_query)
    nodes_with_embeddings = results[0]['total'] if results else 0
    
    print_info(f"Total episodic nodes in database: {total_nodes}")
    print_info(f"Episodic nodes with embeddings: {nodes_with_embeddings}")
    print_warning(f"Episodic nodes missing embeddings: {total_nodes - nodes_with_embeddings}")
    
    if total_nodes == 0:
        print_warning("No episodic nodes found in database")
        return 0, 0
    
    processed = 0
    updated = 0
    failed = 0
    start_time = time.time()
    
    # Process ALL episodic nodes in batches
    while processed < total_nodes:
        # Get batch of ALL episodic nodes
        batch_query = """
        MATCH (n:Episodic)
        RETURN 
            n.uuid as uuid,
            n.content as content,
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
        
        if not results:
            break
        
        print(f"\nProcessing batch {processed // batch_size + 1} ({len(results)} episodic nodes)...")
        
        # Process all nodes with valid content
        nodes_to_embed = []
        for r in results:
            if r.get('content') and r['content'].strip():  # Only process nodes with valid content
                nodes_to_embed.append(r)
        
        if nodes_to_embed:
            contents = [r['content'] for r in nodes_to_embed]
            
            try:
                # Generate embeddings in batch
                embeddings = await embedder.create_batch(contents)
                
                # Update each node with its embedding
                for i, node in enumerate(nodes_to_embed):
                    update_query = """
                    MATCH (n:Episodic {uuid: $uuid})
                    SET n.content_embedding = vecf32($embedding)
                    RETURN n.uuid as uuid
                    """
                    
                    try:
                        _, _, _ = await driver.execute_query(
                            update_query,
                            uuid=node['uuid'],
                            embedding=embeddings[i]
                        )
                        updated += 1
                        
                        if updated % 100 == 0:
                            print(f"  Updated {updated} episodic nodes...")
                            
                    except Exception as e:
                        logger.error(f"Failed to update episodic node {node['uuid']}: {e}")
                        failed += 1
                
            except Exception as e:
                logger.error(f"Failed to generate embeddings for batch: {e}")
                failed += len(nodes_to_embed)
        
        processed += len(results)
        
        # Progress report
        elapsed = time.time() - start_time
        rate = processed / elapsed if elapsed > 0 else 0
        eta = (total_nodes - processed) / rate if rate > 0 else 0
        
        print(f"Progress: {processed}/{total_nodes} episodic nodes processed")
        print(f"Updated: {updated}, Failed: {failed}")
        print(f"Rate: {rate:.1f} nodes/sec, ETA: {eta:.1f} seconds")
        
        # Small delay to avoid overwhelming the embedding service
        if processed < total_nodes:
            await asyncio.sleep(0.1)
    
    return updated, failed


async def main():
    """Main function to fix all embeddings."""
    
    print_header("COMPLETE EMBEDDING FIX")
    print_info(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print_info("This will ensure ALL nodes and edges have proper 2560-dimension embeddings")
    
    # Initialize driver
    driver = FalkorDriver(
        host='localhost',
        port=6379,
        database='graphiti_migration'
    )
    
    # Initialize Ollama embedder
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
    
    print_info(f"Ollama URL: {ollama_base_url}")
    print_info(f"Embedding Model: {ollama_model}")
    print_info("Expected dimension: 2560")
    
    # Track overall statistics
    total_start = time.time()
    results = []
    
    # Fix all node embeddings
    try:
        nodes_updated, nodes_failed = await fix_all_node_embeddings(driver, embedder)
        results.append({
            'type': 'Nodes',
            'updated': nodes_updated,
            'failed': nodes_failed
        })
    except Exception as e:
        print_error(f"Failed to fix node embeddings: {e}")
        results.append({
            'type': 'Nodes',
            'updated': 0,
            'failed': -1
        })
    
    # Fix all edge embeddings
    try:
        edges_updated, edges_failed = await fix_all_edge_embeddings(driver, embedder)
        results.append({
            'type': 'Edges',
            'updated': edges_updated,
            'failed': edges_failed
        })
    except Exception as e:
        print_error(f"Failed to fix edge embeddings: {e}")
        results.append({
            'type': 'Edges',
            'updated': 0,
            'failed': -1
        })
    
    # Fix all episodic embeddings
    try:
        episodic_updated, episodic_failed = await fix_all_episodic_embeddings(driver, embedder)
        results.append({
            'type': 'Episodic Nodes',
            'updated': episodic_updated,
            'failed': episodic_failed
        })
    except Exception as e:
        print_error(f"Failed to fix episodic embeddings: {e}")
        results.append({
            'type': 'Episodic Nodes',
            'updated': 0,
            'failed': -1
        })
    
    # Final verification
    print_header("FINAL VERIFICATION")
    
    # Check for any remaining nodes without embeddings
    verify_queries = [
        ("Nodes without embeddings", """
            MATCH (n:Entity)
            WHERE n.name_embedding IS NULL AND n.name IS NOT NULL AND n.name <> ''
            RETURN count(n) as count
        """),
        ("Edges without embeddings", """
            MATCH ()-[e:RELATES_TO]->()
            WHERE e.fact_embedding IS NULL AND e.fact IS NOT NULL AND e.fact <> ''
            RETURN count(e) as count
        """),
        ("Episodic nodes without embeddings", """
            MATCH (n:Episodic)
            WHERE n.content_embedding IS NULL AND n.content IS NOT NULL AND n.content <> ''
            RETURN count(n) as count
        """)
    ]
    
    for description, query in verify_queries:
        results_data, _, _ = await driver.execute_query(query)
        count = results_data[0]['count'] if results_data else 0
        if count == 0:
            print_success(f"{description}: {count} ✅")
        else:
            print_warning(f"{description}: {count} ⚠️")
    
    await driver.close()
    
    # Calculate total time
    total_duration = time.time() - total_start
    
    # Print summary
    print_header("EMBEDDING FIX SUMMARY")
    
    print_section("Results by Type")
    total_updated = 0
    total_failed = 0
    for result in results:
        total_updated += result['updated']
        total_failed += result['failed'] if result['failed'] != -1 else 0
        
        if result['failed'] == -1:
            status = "❌ ERROR"
        elif result['failed'] == 0:
            status = "✅ SUCCESS"
        else:
            status = "⚠️  PARTIAL"
        
        print(f"  {status}: {result['type']}")
        print(f"    Updated: {result['updated']}")
        if result['failed'] != -1:
            print(f"    Failed: {result['failed']}")
    
    print_section("Overall Statistics")
    print(f"  Total updated: {total_updated}")
    print(f"  Total failed: {total_failed}")
    print(f"  Total time: {total_duration:.2f} seconds ({total_duration/60:.1f} minutes)")
    
    if total_failed == 0:
        print_success("\n🎉 All embeddings successfully fixed!")
        print_info("The dimension mismatch error should now be resolved.")
    else:
        print_warning(f"\n⚠️  Some embeddings failed. Check the output above for details.")
    
    print_info(f"\nEnd time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    return 0 if total_failed == 0 else 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print_warning("\n\nInterrupted by user")
        sys.exit(130)
    except Exception as e:
        print_error(f"\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)