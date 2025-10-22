#!/usr/bin/env python3
"""
Script to delete unconnected nodes from the graph.
Removes episodic nodes with no MENTIONS relationships and entity nodes with no incoming MENTIONS relationships.
"""

import asyncio
import logging
from typing import Dict

from graphiti_core.driver.falkordb_driver import FalkorDriver

# Configure logging
logging.basicConfig(
    level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class UnconnectedNodeCleaner:
    """Delete unconnected nodes from the graph"""

    def __init__(self, driver: FalkorDriver):
        self.driver = driver

    async def count_unconnected_nodes(self) -> Dict[str, int]:
        """Count unconnected nodes by type"""
        # Count disconnected episodes
        episode_query = """
        MATCH (ep:Episodic)
        WHERE NOT (ep)-[:MENTIONS]->()
        RETURN count(ep) as count
        """
        
        # Count disconnected entities
        entity_query = """
        MATCH (ent:Entity)
        WHERE NOT ()-[:MENTIONS]->(ent)
        RETURN count(ent) as count
        """
        
        episode_result, _, _ = await self.driver.execute_query(episode_query)
        entity_result, _, _ = await self.driver.execute_query(entity_query)
        
        return {
            'episodes': episode_result[0]['count'] if episode_result else 0,
            'entities': entity_result[0]['count'] if entity_result else 0,
        }

    async def delete_unconnected_episodes(self, group_id: str = None, dry_run: bool = False) -> int:
        """Delete episodic nodes with no MENTIONS relationships"""
        if group_id:
            query = """
            MATCH (ep:Episodic)
            WHERE ep.group_id = $group_id AND NOT (ep)-[:MENTIONS]->()
            """
            count_query = query + " RETURN count(ep) as count"
            delete_query = query + " DELETE ep"
            params = {'group_id': group_id}
        else:
            count_query = """
            MATCH (ep:Episodic)
            WHERE NOT (ep)-[:MENTIONS]->()
            RETURN count(ep) as count
            """
            delete_query = """
            MATCH (ep:Episodic)
            WHERE NOT (ep)-[:MENTIONS]->()
            DELETE ep
            """
            params = {}

        # Get count first
        result, _, _ = await self.driver.execute_query(count_query, **params)
        count = result[0]['count'] if result else 0
        
        if dry_run:
            logger.info(f'Would delete {count} unconnected episodic nodes')
            return count
        
        if count == 0:
            logger.info('No unconnected episodic nodes to delete')
            return 0
        
        # Delete nodes
        await self.driver.execute_query(delete_query, **params)
        logger.info(f'Deleted {count} unconnected episodic nodes')
        return count

    async def delete_unconnected_entities(self, group_id: str = None, dry_run: bool = False) -> int:
        """Delete entity nodes with no incoming MENTIONS relationships"""
        if group_id:
            query = """
            MATCH (ent:Entity)
            WHERE ent.group_id = $group_id AND NOT ()-[:MENTIONS]->(ent)
            """
            count_query = query + " RETURN count(ent) as count"
            delete_query = query + " DELETE ent"
            params = {'group_id': group_id}
        else:
            count_query = """
            MATCH (ent:Entity)
            WHERE NOT ()-[:MENTIONS]->(ent)
            RETURN count(ent) as count
            """
            delete_query = """
            MATCH (ent:Entity)
            WHERE NOT ()-[:MENTIONS]->(ent)
            DELETE ent
            """
            params = {}

        # Get count first
        result, _, _ = await self.driver.execute_query(count_query, **params)
        count = result[0]['count'] if result else 0
        
        if dry_run:
            logger.info(f'Would delete {count} unconnected entity nodes')
            return count
        
        if count == 0:
            logger.info('No unconnected entity nodes to delete')
            return 0
        
        # Delete nodes
        await self.driver.execute_query(delete_query, **params)
        logger.info(f'Deleted {count} unconnected entity nodes')
        return count

    async def clean_all_unconnected(self, group_id: str = None, dry_run: bool = False) -> Dict[str, int]:
        """Delete all unconnected nodes"""
        logger.info('Starting cleanup of unconnected nodes...')
        
        if dry_run:
            logger.info('DRY RUN MODE - No nodes will be deleted')
        
        # Show initial counts
        initial_counts = await self.count_unconnected_nodes()
        logger.info(f'Found {initial_counts["episodes"]} unconnected episodes and {initial_counts["entities"]} unconnected entities')
        
        if initial_counts['episodes'] == 0 and initial_counts['entities'] == 0:
            logger.info('No unconnected nodes found')
            return {'episodes_deleted': 0, 'entities_deleted': 0}
        
        # Delete unconnected nodes
        episodes_deleted = await self.delete_unconnected_episodes(group_id, dry_run)
        entities_deleted = await self.delete_unconnected_entities(group_id, dry_run)
        
        if not dry_run:
            # Verify cleanup
            final_counts = await self.count_unconnected_nodes()
            logger.info(f'After cleanup: {final_counts["episodes"]} unconnected episodes and {final_counts["entities"]} unconnected entities remain')
        
        return {
            'episodes_deleted': episodes_deleted,
            'entities_deleted': entities_deleted,
            'initial_counts': initial_counts
        }


async def main():
    """Main function to delete unconnected nodes"""
    import sys
    
    # Parse command line arguments
    dry_run = '--dry-run' in sys.argv
    group_id = None
    
    # Check for group_id argument
    for i, arg in enumerate(sys.argv):
        if arg.startswith('--group-id='):
            group_id = arg.split('=', 1)[1]
        elif arg == '--group-id' and i + 1 < len(sys.argv):
            group_id = sys.argv[i + 1]
    
    # Create FalkorDB driver
    driver = FalkorDriver(host='localhost', port=6379, database='graphiti_migration')
    
    cleaner = UnconnectedNodeCleaner(driver)
    
    if not dry_run:
        # Run dry run first to show what would be deleted
        logger.info('Running dry run to show what would be deleted...')
        dry_result = await cleaner.clean_all_unconnected(group_id, dry_run=True)
        
        if dry_result['episodes_deleted'] == 0 and dry_result['entities_deleted'] == 0:
            logger.info('No unconnected nodes found. Exiting.')
            return
        
        confirmation = input(f'\nDelete {dry_result["episodes_deleted"]} episodes and {dry_result["entities_deleted"]} entities? (yes/no): ')
        if confirmation.lower() not in ['yes', 'y']:
            logger.info('Operation cancelled.')
            return
    
    # Perform the actual cleanup
    result = await cleaner.clean_all_unconnected(group_id, dry_run)
    
    print('\n' + '=' * 50)
    print('CLEANUP SUMMARY')
    print('=' * 50)
    if dry_run:
        print(f'Would delete {result["episodes_deleted"]} episodic nodes')
        print(f'Would delete {result["entities_deleted"]} entity nodes')
    else:
        print(f'Deleted {result["episodes_deleted"]} episodic nodes')
        print(f'Deleted {result["entities_deleted"]} entity nodes')
        print(f'Total nodes removed: {result["episodes_deleted"] + result["entities_deleted"]}')


if __name__ == '__main__':
    asyncio.run(main())