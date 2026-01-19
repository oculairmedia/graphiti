#!/usr/bin/env python3
"""
Update centrality values for nodes that are missing them
"""

import asyncio
import logging
import os
from datetime import datetime

# Enable Rust centrality service
os.environ['USE_RUST_CENTRALITY'] = 'true'

from graphiti_core.driver.falkordb_driver import FalkorDriver
from graphiti_core.utils.maintenance.centrality_operations import calculate_all_centralities

# Configure logging
logging.basicConfig(
    level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def check_centrality_status(driver):
    """Check how many nodes are missing centrality values"""
    query = """
    MATCH (n)
    WHERE n.pagerank IS NULL OR n.degree_centrality IS NULL OR n.betweenness_centrality IS NULL
    RETURN count(n) as missing_count
    """

    records, _, _ = await driver.execute_query(query)
    missing = records[0]['missing_count'] if records else 0

    # Get total count
    total_query = 'MATCH (n) RETURN count(n) as total'
    total_records, _, _ = await driver.execute_query(total_query)
    total = total_records[0]['total'] if total_records else 0

    return missing, total


async def main():
    """Main function to update centrality values"""
    print('=' * 60)
    print('CENTRALITY VALUE UPDATE')
    print('=' * 60)

    # Connect to FalkorDB
    driver = FalkorDriver(host='localhost', port=6389, database='graphiti_migration')

    # Check current status
    missing, total = await check_centrality_status(driver)
    print(f'\nCurrent status:')
    print(f'  Total nodes: {total}')
    print(f'  Nodes missing centrality values: {missing}')

    if missing == 0:
        print('\nAll nodes already have centrality values!')
        return

    print(f'\nUpdating centrality values for {missing} nodes...')
    print('This will use the Rust centrality server at port 3003')

    start_time = datetime.now()

    try:
        # Calculate and store all centrality metrics
        results = await calculate_all_centralities(
            driver=driver,
            group_id=None,  # Process all nodes
            store_results=True,  # Store in database
        )

        elapsed = (datetime.now() - start_time).total_seconds()

        print(f'\nCentrality calculation complete!')
        print(f'  Time taken: {elapsed:.2f} seconds')
        print(f'  Nodes processed: {len(results)}')

        # Verify update
        missing_after, _ = await check_centrality_status(driver)
        print(f'\nVerification:')
        print(f'  Nodes still missing centrality values: {missing_after}')

        if missing_after > 0:
            print('\nSome nodes still missing values. Checking details...')

            # Get sample of nodes still missing values
            sample_query = """
            MATCH (n)
            WHERE n.pagerank IS NULL OR n.degree_centrality IS NULL OR n.betweenness_centrality IS NULL
            RETURN n.uuid as uuid, labels(n) as labels
            LIMIT 5
            """
            samples, _, _ = await driver.execute_query(sample_query)

            print('\nSample nodes still missing values:')
            for sample in samples:
                print(f'  UUID: {sample["uuid"]}, Labels: {sample["labels"]}')

    except Exception as e:
        logger.error(f'Error updating centrality values: {e}')
        print(f'\nError: {e}')
        print('\nTroubleshooting:')
        print(
            '1. Check if Rust centrality server is running: docker-compose ps graphiti-centrality-rs'
        )
        print('2. Check server logs: docker-compose logs graphiti-centrality-rs')
        print('3. Verify server is accessible: curl http://localhost:3003/health')


if __name__ == '__main__':
    asyncio.run(main())
