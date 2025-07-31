#!/usr/bin/env python3
"""
Calculate centrality values for all nodes using Python implementation
"""

import asyncio
import logging
import os
from datetime import datetime

# Enable Rust centrality service
os.environ["USE_RUST_CENTRALITY"] = "true"
os.environ["RUST_CENTRALITY_URL"] = "http://localhost:3003"

from graphiti_core.driver.falkordb_driver import FalkorDriver
from graphiti_core.utils.maintenance.centrality_operations import calculate_all_centralities

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def check_centrality_status(driver):
    """Check how many nodes have centrality values"""
    query = """
    MATCH (n)
    WHERE n.centrality_pagerank IS NOT NULL 
    RETURN count(n) as with_centrality
    """
    
    records, _, _ = await driver.execute_query(query)
    with_centrality = records[0]['with_centrality'] if records else 0
    
    # Get total count
    total_query = "MATCH (n) RETURN count(n) as total"
    total_records, _, _ = await driver.execute_query(total_query)
    total = total_records[0]['total'] if total_records else 0
    
    return with_centrality, total

async def main():
    """Main function to calculate centrality values"""
    print("="*60)
    print("CENTRALITY CALCULATION (Rust Service)")
    print("="*60)
    
    # Connect to FalkorDB
    driver = FalkorDriver(
        host="localhost",
        port=6389,
        database="graphiti_migration"
    )
    
    # Check current status
    with_centrality, total = await check_centrality_status(driver)
    print(f"\nCurrent status:")
    print(f"  Total nodes: {total}")
    print(f"  Nodes with centrality values: {with_centrality}")
    print(f"  Nodes needing calculation: {total - with_centrality}")
    
    print(f"\nCalculating centrality values for all {total} nodes...")
    print("This will use the Rust centrality service at http://localhost:3003")
    
    start_time = datetime.now()
    
    try:
        # Calculate and store all centrality metrics
        results = await calculate_all_centralities(
            driver=driver,
            group_id=None,  # Process all nodes
            store_results=True  # Store in database
        )
        
        elapsed = (datetime.now() - start_time).total_seconds()
        
        print(f"\nCentrality calculation complete!")
        print(f"  Time taken: {elapsed:.2f} seconds")
        print(f"  Nodes processed: {len(results)}")
        
        # Show sample results
        print("\nSample centrality scores (first 5 nodes):")
        for i, (node_id, scores) in enumerate(list(results.items())[:5]):
            print(f"\n  Node {node_id[:8]}...")
            print(f"    PageRank: {scores['pagerank']:.6f}")
            print(f"    Degree: {scores['degree']}")
            print(f"    Betweenness: {scores['betweenness']:.6f}")
            print(f"    Importance: {scores['importance']:.4f}")
        
        # Verify update
        with_centrality_after, _ = await check_centrality_status(driver)
        print(f"\nVerification:")
        print(f"  Nodes with centrality values: {with_centrality_after}")
        
        # Find most important nodes
        print("\nTop 10 most important nodes:")
        sorted_nodes = sorted(results.items(), key=lambda x: x[1]['importance'], reverse=True)[:10]
        
        for i, (node_id, scores) in enumerate(sorted_nodes, 1):
            # Get node name
            query = "MATCH (n {uuid: $uuid}) RETURN n.name as name, labels(n) as labels"
            records, _, _ = await driver.execute_query(query, uuid=node_id)
            if records:
                name = records[0]['name']
                labels = records[0]['labels']
                print(f"{i:2d}. {name} ({labels[0]}) - Importance: {scores['importance']:.4f}")
                
    except Exception as e:
        logger.error(f"Error calculating centrality values: {e}")
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())