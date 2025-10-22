#!/usr/bin/env python3
"""
Generate embeddings for ALL missing nodes and edges regardless of type.
This script will find nodes/edges without embeddings and generate 2560-dimension embeddings for them.
"""

import asyncio
import os
import sys
import time
from typing import List, Dict, Any
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


async def fix_missing_node_embeddings(driver, embedder, batch_size: int = 50):
    """Generate embeddings for ALL nodes missing embeddings regardless of type."""
    
    print_section("FIXING MISSING NODE EMBEDDINGS (ALL TYPES)")
    
    # Find ALL nodes without embeddings regardless of type or embedding field
    missing_query = """
    MATCH (n)
    WHERE (n.name_embedding IS NULL OR NOT EXISTS(n.name_embedding))
      AND n.name IS NOT NULL 
      AND n.name <> ''
    RETURN 
        n.uuid as uuid,
        n.name as name,
        labels(n) as node_types
    ORDER BY n.created_at DESC
    """
    
    results, _, _ = await driver.execute_query(missing_query)
    total_missing = len(results)
    
    print_info(f"Found {total_missing} nodes missing embeddings (all types)")
    
    if total_missing == 0:
        print_success("All nodes already have embeddings!")
        return 0, 0
    
    # Show node type breakdown
    type_counts = {}
    for result in results:
        node_types = result.get('node_types', ['Unknown'])
        for node_type in node_types:
            type_counts[node_type] = type_counts.get(node_type, 0) + 1
    
    print_info("Node types missing embeddings:")
    for node_type, count in type_counts.items():
        print(f"  • {node_type}: {count} nodes")
    
    processed = 0
    updated = 0
    failed = 0
    start_time = time.time()
    
    # Process nodes in batches
    for i in range(0, total_missing, batch_size):
        batch = results[i:i + batch_size]
        
        print(f"\nProcessing batch {i // batch_size + 1} ({len(batch)} nodes)...")
        
        # Filter for nodes with valid names
        nodes_to_embed = []
        for node in batch:
            if node.get('name') and node['name'].strip():
                nodes_to_embed.append(node)
        
        if nodes_to_embed:
            names = [node['name'] for node in nodes_to_embed]
            
            try:
                # Generate embeddings in batch
                embeddings = await embedder.create_batch(names)
                
                # Update each node with its embedding
                for j, node in enumerate(nodes_to_embed):
                    update_query = """
                    MATCH (n {uuid: $uuid})
                    SET n.name_embedding = vecf32($embedding)
                    RETURN n.uuid as uuid
                    """
                    
                    try:
                        _, _, _ = await driver.execute_query(
                            update_query,
                            uuid=node['uuid'],
                            embedding=embeddings[j]
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
        
        processed += len(batch)
        
        # Progress report
        elapsed = time.time() - start_time
        rate = processed / elapsed if elapsed > 0 else 0
        eta = (total_missing - processed) / rate if rate > 0 else 0
        
        print(f"Progress: {processed}/{total_missing} nodes processed")
        print(f"Updated: {updated}, Failed: {failed}")
        print(f"Rate: {rate:.1f} nodes/sec, ETA: {eta:.1f} seconds")
        
        # Small delay to avoid overwhelming the embedding service
        if processed < total_missing:
            await asyncio.sleep(0.1)
    
    return updated, failed


async def fix_missing_edge_embeddings(driver, embedder, batch_size: int = 50):
    """Generate embeddings for ALL edges missing embeddings regardless of type."""
    
    print_section("FIXING MISSING EDGE EMBEDDINGS (ALL TYPES)")
    
    # Find ALL edges without embeddings regardless of type
    missing_query = """
    MATCH ()-[e]->()
    WHERE (e.fact_embedding IS NULL OR NOT EXISTS(e.fact_embedding))
      AND e.fact IS NOT NULL 
      AND e.fact <> ''
    RETURN 
        e.uuid as uuid,
        e.fact as fact,
        type(e) as edge_type
    """
    
    results, _, _ = await driver.execute_query(missing_query)
    total_missing = len(results)
    
    print_info(f"Found {total_missing} edges missing embeddings (all types)")
    
    if total_missing == 0:
        print_success("All edges already have embeddings!")
        return 0, 0
    
    # Show edge type breakdown
    type_counts = {}
    for result in results:
        edge_type = result.get('edge_type', 'Unknown')
        type_counts[edge_type] = type_counts.get(edge_type, 0) + 1
    
    print_info("Edge types missing embeddings:")
    for edge_type, count in type_counts.items():
        print(f"  • {edge_type}: {count} edges")
    
    processed = 0
    updated = 0
    failed = 0
    start_time = time.time()
    
    # Process edges in batches
    for i in range(0, total_missing, batch_size):
        batch = results[i:i + batch_size]
        
        print(f"\nProcessing batch {i // batch_size + 1} ({len(batch)} edges)...")
        
        # Filter for edges with valid facts
        edges_to_embed = []
        for edge in batch:
            if edge.get('fact') and edge['fact'].strip():
                edges_to_embed.append(edge)
        
        if edges_to_embed:
            facts = [edge['fact'] for edge in edges_to_embed]
            
            try:
                # Generate embeddings in batch
                embeddings = await embedder.create_batch(facts)
                
                # Update each edge with its embedding
                for j, edge in enumerate(edges_to_embed):
                    update_query = """
                    MATCH ()-[e {uuid: $uuid}]->()
                    SET e.fact_embedding = vecf32($embedding)
                    RETURN e.uuid as uuid
                    """
                    
                    try:
                        _, _, _ = await driver.execute_query(
                            update_query,
                            uuid=edge['uuid'],
                            embedding=embeddings[j]
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
        
        processed += len(batch)
        
        # Progress report
        elapsed = time.time() - start_time
        rate = processed / elapsed if elapsed > 0 else 0
        eta = (total_missing - processed) / rate if rate > 0 else 0
        
        print(f"Progress: {processed}/{total_missing} edges processed")
        print(f"Updated: {updated}, Failed: {failed}")
        print(f"Rate: {rate:.1f} edges/sec, ETA: {eta:.1f} seconds")
        
        # Small delay to avoid overwhelming the embedding service
        if processed < total_missing:
            await asyncio.sleep(0.1)
    
    return updated, failed


async def main():
    """Main function to fix missing embeddings."""
    
    print_header("FIX MISSING EMBEDDINGS FOR ALL NODE/EDGE TYPES")
    print_info(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
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
    
    # Fix missing node embeddings
    try:
        nodes_updated, nodes_failed = await fix_missing_node_embeddings(driver, embedder)
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
    
    # Fix missing edge embeddings
    try:
        edges_updated, edges_failed = await fix_missing_edge_embeddings(driver, embedder)
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
    
    # Final verification
    print_header("FINAL VERIFICATION")
    
    # Check counts
    verify_queries = [
        ("Total nodes", "MATCH (n) RETURN count(n) as count"),
        ("Nodes with embeddings", """
            MATCH (n)
            WHERE n.name_embedding IS NOT NULL
            RETURN count(n) as count
        """),
        ("Total edges", "MATCH ()-[e]->() RETURN count(e) as count"),
        ("Edges with embeddings", """
            MATCH ()-[e]->()
            WHERE e.fact_embedding IS NOT NULL
            RETURN count(e) as count
        """)
    ]
    
    for description, query in verify_queries:
        results_data, _, _ = await driver.execute_query(query)
        count = results_data[0]['count'] if results_data else 0
        print_info(f"{description}: {count}")
    
    await driver.close()
    
    # Calculate total time
    total_duration = time.time() - total_start
    
    # Print summary
    print_header("MISSING EMBEDDINGS FIX SUMMARY")
    
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
    
    if total_failed == 0 and total_updated > 0:
        print_success("\n🎉 All missing embeddings successfully generated!")
        print_info("The dimension mismatch error should now be resolved.")
    elif total_updated == 0:
        print_info("\n✅ No missing embeddings found - all nodes and edges already have embeddings.")
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