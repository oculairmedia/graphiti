#!/usr/bin/env python3
"""
Simple test of the migration service integration.
"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'sync_service'))

from migration.migration_service import MigrationService, MigrationConfig


async def test_migration():
    """Test migration service directly."""
    print("=== Testing Migration Service ===")
    
    neo4j_config = {
        'uri': 'bolt://localhost:7687',
        'user': 'neo4j', 
        'password': 'demodemo'
    }
    
    falkordb_config = {
        'host': 'localhost',
        'port': 6379,
        'database': 'graphiti_migration'
    }
    
    migration_config = MigrationConfig()
    
    def progress_callback(progress):
        if progress.current_phase != getattr(progress_callback, '_last_phase', None):
            print(f"Phase: {progress.current_phase}")
            progress_callback._last_phase = progress.current_phase
        
        if progress.migrated_nodes > 0 or progress.migrated_relationships > 0:
            print(f"  Progress: {progress.migrated_nodes}/{progress.total_nodes} nodes, "
                  f"{progress.migrated_relationships}/{progress.total_relationships} relationships")
    
    try:
        async with MigrationService(
            neo4j_config=neo4j_config,
            falkordb_config=falkordb_config,
            migration_config=migration_config,
            progress_callback=progress_callback
        ) as service:
            
            print("Starting migration...")
            result = await service.migrate_full()
            
            print(f"\nMigration completed!")
            print(f"Status: {result.status.value}")
            print(f"Duration: {result.duration_seconds:.2f}s")
            print(f"Nodes: {result.migrated_nodes}/{result.total_nodes} ({result.node_success_rate:.1f}%)")
            print(f"Relationships: {result.migrated_relationships}/{result.total_relationships} ({result.relationship_success_rate:.1f}%)")
            
            return result.status.value == "completed"
            
    except Exception as e:
        print(f"Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    success = asyncio.run(test_migration())
    if success:
        print("\n✅ Migration service test PASSED!")
    else:
        print("\n❌ Migration service test FAILED!")
    exit(0 if success else 1)