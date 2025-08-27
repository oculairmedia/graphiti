#!/usr/bin/env python3
"""
Test script to verify the migration service integration.
"""

import asyncio
import logging
from datetime import datetime

import sys
sys.path.append('sync_service')

from orchestrator.sync_orchestrator import SyncOrchestrator
from migration.migration_service import MigrationConfig

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_migration_integration():
    """Test the integrated migration service."""
    print("=== Testing Migration Service Integration ===")
    
    # Configuration
    neo4j_config = {
        'uri': 'bolt://localhost:7687',
        'user': 'neo4j',
        'password': 'demodemo',
        'database': 'neo4j'
    }
    
    falkordb_config = {
        'host': 'localhost',
        'port': 6379,
        'database': 'graphiti_migration'
    }
    
    # Create migration config
    migration_config = MigrationConfig(
        max_query_length=10000,
        retry_attempts=3,
        batch_progress_interval=25,  # More frequent progress for testing
        clear_target_on_start=True,
        embedding_properties=['name_embedding', 'summary_embedding']
    )
    
    # Create orchestrator with migration service
    orchestrator = SyncOrchestrator(
        neo4j_config=neo4j_config,
        falkordb_config=falkordb_config,
        batch_size=500,
        sync_interval_seconds=300,
        max_retries=3,
        retry_delay_seconds=5,
        migration_config=migration_config
    )
    
    def progress_callback(progress):
        """Progress callback for testing."""
        print(f"Migration Progress: {progress.current_phase} - "
              f"Nodes: {progress.migrated_nodes}/{progress.total_nodes} "
              f"({progress.node_success_rate:.1f}%), "
              f"Relationships: {progress.migrated_relationships}/{progress.total_relationships} "
              f"({progress.relationship_success_rate:.1f}%)")
    
    try:
        # Test migration
        print("Starting migration test...")
        operation_stats = await orchestrator.sync_migration_full(progress_callback=progress_callback)
        
        print(f"\nMigration completed!")
        print(f"Status: {operation_stats.status.value}")
        print(f"Mode: {operation_stats.mode.value}")
        print(f"Duration: {operation_stats.duration_seconds:.2f}s")
        print(f"Items processed: {operation_stats.total_items_processed}")
        print(f"Items failed: {operation_stats.total_items_failed}")
        print(f"Success rate: {operation_stats.success_rate:.1%}")
        
        if operation_stats.errors:
            print(f"Errors: {operation_stats.errors}")
        
        # Test progress access
        current_progress = orchestrator.get_migration_progress()
        if current_progress:
            print(f"\nFinal migration progress:")
            print(f"  Status: {current_progress.status.value}")
            print(f"  Duration: {current_progress.duration_seconds:.2f}s")
        
        return operation_stats.status.value == "completed"
        
    except Exception as e:
        print(f"Migration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Main test function."""
    success = await test_migration_integration()
    if success:
        print("\n✅ Migration service integration test PASSED!")
    else:
        print("\n❌ Migration service integration test FAILED!")
    
    return 0 if success else 1


if __name__ == '__main__':
    exit_code = asyncio.run(main())
    exit(exit_code)