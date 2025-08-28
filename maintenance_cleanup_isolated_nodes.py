#!/usr/bin/env python3
"""
Maintenance script to remove isolated nodes (nodes with no edges) from FalkorDB.
This cleans up orphaned episodic nodes and entities that serve no purpose in the knowledge graph.
"""
import asyncio
import logging
import os
from typing import List, Optional

from graphiti_core.driver.falkordb_driver import FalkorDriver

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class IsolatedNodeCleaner:
    """Utility class to find and remove isolated nodes from the knowledge graph."""
    
    def __init__(self, driver: FalkorDriver):
        self.driver = driver
        
    async def get_isolated_count(self) -> int:
        """Get count of nodes with no edges"""
        query = """
        MATCH (n)
        WHERE NOT (n)-[]-()
        RETURN count(n) as count
        """
        
        result, _, _ = await self.driver.execute_query(query)
        return result[0]['count'] if result else 0
    
    async def get_isolated_nodes_sample(self, limit: int = 20) -> List[dict]:
        """Get sample of isolated nodes for inspection"""
        query = """
        MATCH (n)
        WHERE NOT (n)-[]-()
        RETURN n.uuid as uuid, labels(n) as labels, n.name as name, n.created_at as created_at
        LIMIT $limit
        """
        
        result, _, _ = await self.driver.execute_query(query, limit=limit)
        return [
            {
                'uuid': record['uuid'],
                'labels': record['labels'],
                'name': record['name'],
                'created_at': record['created_at']
            }
            for record in result
        ]
    
    async def delete_isolated_nodes_batch(self, batch_size: int = 100) -> int:
        """Delete a batch of isolated nodes and return count deleted"""
        query = """
        MATCH (n)
        WHERE NOT (n)-[]-()
        WITH n LIMIT $batch_size
        DELETE n
        RETURN count(n) as deleted_count
        """
        
        result, _, _ = await self.driver.execute_query(query, batch_size=batch_size)
        return result[0]['deleted_count'] if result else 0
    
    async def get_isolated_by_type(self) -> List[dict]:
        """Get counts of isolated nodes by type"""
        query = """
        MATCH (n)
        WHERE NOT (n)-[]-()
        RETURN labels(n) as labels, count(n) as count
        ORDER BY count DESC
        """
        
        result, _, _ = await self.driver.execute_query(query)
        return [
            {
                'labels': record['labels'],
                'count': record['count']
            }
            for record in result
        ]


async def main():
    """Main cleanup process"""
    # Set up FalkorDB connection
    os.environ['FALKORDB_HOST'] = 'localhost'
    os.environ['FALKORDB_PORT'] = '6389'
    os.environ['FALKORDB_DATABASE'] = 'graphiti_migration'
    
    driver = FalkorDriver()
    cleaner = IsolatedNodeCleaner(driver)
    
    # Get initial count and analysis
    total_isolated = await cleaner.get_isolated_count()
    print(f'Found {total_isolated} isolated nodes (nodes with no edges)')
    
    if total_isolated == 0:
        print('No isolated nodes found. Database is clean!')
        return
    
    # Show breakdown by type
    print('\nBreakdown by node type:')
    types = await cleaner.get_isolated_by_type()
    for node_type in types:
        print(f'  {node_type["labels"]}: {node_type["count"]} nodes')
    
    # Show sample nodes
    print('\nSample isolated nodes:')
    samples = await cleaner.get_isolated_nodes_sample(10)
    for i, node in enumerate(samples, 1):
        print(f'  {i}. {node["labels"]} - {node["name"]} ({node["uuid"][:8]}...)')
    
    # Confirm deletion
    confirmation = input(f'\nDo you want to delete all {total_isolated} isolated nodes? (yes/no): ')
    if confirmation.lower() not in ['yes', 'y']:
        print('Operation cancelled.')
        return
    
    # Delete in batches
    print('\nDeleting isolated nodes in batches...')
    total_deleted = 0
    batch_size = 100
    batch_num = 1
    
    while True:
        deleted_count = await cleaner.delete_isolated_nodes_batch(batch_size)
        if deleted_count == 0:
            break
            
        total_deleted += deleted_count
        print(f'  Batch {batch_num}: Deleted {deleted_count} nodes (total: {total_deleted})')
        batch_num += 1
        
        # Check remaining count
        remaining = await cleaner.get_isolated_count()
        if remaining == 0:
            break
    
    print(f'\nCleanup completed! Deleted {total_deleted} isolated nodes.')
    
    # Final verification
    final_count = await cleaner.get_isolated_count()
    if final_count == 0:
        print('✅ Database is now clean - no isolated nodes remaining.')
    else:
        print(f'⚠️  Warning: {final_count} isolated nodes still remain.')


if __name__ == '__main__':
    asyncio.run(main())