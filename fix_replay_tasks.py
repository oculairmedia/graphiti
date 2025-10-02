#!/usr/bin/env python3
"""
Fix replay task issues:
1. Backfill valid_at for episodes missing it
2. Clean up replay tasks for deleted episodes
"""

import asyncio
import redis
import httpx
from graphiti_core.driver.falkordb_driver import FalkorDriver


async def backfill_valid_at():
    """Set valid_at = created_at for episodes missing valid_at"""
    print("\n🔧 Backfilling valid_at for episodes...")

    driver = FalkorDriver(host='localhost', port=6379, database='graphiti_migration')

    # Count episodes without valid_at
    count_query = """
    MATCH (ep:Episodic)
    WHERE ep.valid_at IS NULL
    RETURN count(ep) as count
    """

    result, _, _ = await driver.execute_query(count_query)
    count = result[0]['count'] if result else 0
    print(f"   Found {count} episodes without valid_at")

    if count == 0:
        print("   ✅ No episodes need backfilling")
        return 0

    # Update episodes
    update_query = """
    MATCH (ep:Episodic)
    WHERE ep.valid_at IS NULL
    SET ep.valid_at = ep.created_at
    RETURN count(ep) as updated
    """

    result, _, _ = await driver.execute_query(update_query)
    updated = result[0]['updated'] if result else 0
    print(f"   ✅ Updated {updated} episodes")

    return updated


async def backfill_source():
    """Set source = 'message' for episodes missing source"""
    print("\n🔧 Backfilling source for episodes...")

    driver = FalkorDriver(host='localhost', port=6379, database='graphiti_migration')

    # Count episodes without source
    count_query = """
    MATCH (ep:Episodic)
    WHERE ep.source IS NULL
    RETURN count(ep) as count
    """

    result, _, _ = await driver.execute_query(count_query)
    count = result[0]['count'] if result else 0
    print(f"   Found {count} episodes without source")

    if count == 0:
        print("   ✅ No episodes need backfilling")
        return 0

    # Update episodes with default source type
    update_query = """
    MATCH (ep:Episodic)
    WHERE ep.source IS NULL
    SET ep.source = 'message'
    RETURN count(ep) as updated
    """

    result, _, _ = await driver.execute_query(update_query)
    updated = result[0]['updated'] if result else 0
    print(f"   ✅ Updated {updated} episodes with source='message'")

    return updated


async def backfill_source_description():
    """Set source_description = '' for episodes missing it"""
    print("\n🔧 Backfilling source_description for episodes...")

    driver = FalkorDriver(host='localhost', port=6379, database='graphiti_migration')

    # Count episodes without source_description
    count_query = """
    MATCH (ep:Episodic)
    WHERE ep.source_description IS NULL
    RETURN count(ep) as count
    """

    result, _, _ = await driver.execute_query(count_query)
    count = result[0]['count'] if result else 0
    print(f"   Found {count} episodes without source_description")

    if count == 0:
        print("   ✅ No episodes need backfilling")
        return 0

    # Update episodes with empty string
    update_query = """
    MATCH (ep:Episodic)
    WHERE ep.source_description IS NULL
    SET ep.source_description = ''
    RETURN count(ep) as updated
    """

    result, _, _ = await driver.execute_query(update_query)
    updated = result[0]['updated'] if result else 0
    print(f"   ✅ Updated {updated} episodes with source_description=''")

    return updated


async def backfill_entity_edges():
    """Set entity_edges = [] for episodes missing it"""
    print("\n🔧 Backfilling entity_edges for episodes...")

    driver = FalkorDriver(host='localhost', port=6379, database='graphiti_migration')

    # Count episodes without entity_edges
    count_query = """
    MATCH (ep:Episodic)
    WHERE ep.entity_edges IS NULL
    RETURN count(ep) as count
    """

    result, _, _ = await driver.execute_query(count_query)
    count = result[0]['count'] if result else 0
    print(f"   Found {count} episodes without entity_edges")

    if count == 0:
        print("   ✅ No episodes need backfilling")
        return 0

    # Update episodes with empty list
    update_query = """
    MATCH (ep:Episodic)
    WHERE ep.entity_edges IS NULL
    SET ep.entity_edges = []
    RETURN count(ep) as updated
    """

    result, _, _ = await driver.execute_query(update_query)
    updated = result[0]['updated'] if result else 0
    print(f"   ✅ Updated {updated} episodes with entity_edges=[]")

    return updated


async def get_all_episode_uuids():
    """Get all valid episode UUIDs from the database"""
    driver = FalkorDriver(host='localhost', port=6379, database='graphiti_migration')
    
    query = """
    MATCH (ep:Episodic)
    RETURN ep.uuid as uuid
    """
    
    result, _, _ = await driver.execute_query(query)
    return {record['uuid'] for record in result}


async def clean_replay_queue():
    """Remove replay tasks for episodes that no longer exist"""
    print("\n🧹 Cleaning replay queue...")
    
    # Get all valid episode UUIDs
    valid_uuids = await get_all_episode_uuids()
    print(f"   Found {len(valid_uuids)} valid episodes in database")
    
    # Get all replay tasks from queue
    async with httpx.AsyncClient() as client:
        try:
            # Get queue stats
            response = await client.get('http://localhost:8093/queue/memory_replay/metrics')
            if response.status_code == 200:
                metrics = response.json()
                print(f"   Queue has {metrics.get('total_messages', 0)} messages")
            
            # Poll and check tasks
            deleted_count = 0
            checked_count = 0
            
            while checked_count < 1000:  # Safety limit
                # Poll a message
                poll_response = await client.post(
                    'http://localhost:8093/queue/memory_replay/messages/poll',
                    timeout=5.0
                )
                
                if poll_response.status_code != 200:
                    break
                
                task_data = poll_response.json()
                if not task_data:
                    break
                
                message_id = task_data.get('message_id')
                poll_tag = task_data.get('poll_tag')
                payload = task_data.get('payload', {})
                episode_uuid = payload.get('episode_uuid')
                
                checked_count += 1
                
                # Check if episode exists
                if episode_uuid and episode_uuid not in valid_uuids:
                    # Delete this task - episode no longer exists
                    delete_response = await client.delete(
                        f'http://localhost:8093/queue/memory_replay/messages/{message_id}',
                        params={'poll_tag': poll_tag}
                    )
                    if delete_response.status_code == 200:
                        deleted_count += 1
                        print(f"   🗑️  Deleted task for missing episode {episode_uuid[:8]}...")
                else:
                    # Re-queue the task (release it back)
                    await client.post(
                        f'http://localhost:8093/queue/memory_replay/messages/{message_id}/update',
                        json={'poll_tag': poll_tag, 'delay_seconds': 0}
                    )
            
            print(f"   ✅ Checked {checked_count} tasks, deleted {deleted_count} orphaned tasks")
            return deleted_count
            
        except Exception as e:
            print(f"   ⚠️  Error cleaning queue: {e}")
            return 0


async def verify_fix():
    """Verify that the fixes worked"""
    print("\n✅ Verifying fixes...")
    
    driver = FalkorDriver(host='localhost', port=6379, database='graphiti_migration')
    
    # Check for episodes without valid_at
    query = """
    MATCH (ep:Episodic)
    WHERE ep.valid_at IS NULL
    RETURN count(ep) as count
    """
    
    result, _, _ = await driver.execute_query(query)
    count = result[0]['count'] if result else 0
    
    if count == 0:
        print("   ✅ All episodes have valid_at")
    else:
        print(f"   ⚠️  {count} episodes still missing valid_at")
    
    return count == 0


async def main():
    print("=" * 60)
    print("REPLAY TASK FIXER")
    print("=" * 60)

    # Step 1: Backfill valid_at
    updated_valid_at = await backfill_valid_at()

    # Step 2: Backfill source
    updated_source = await backfill_source()

    # Step 3: Clean replay queue
    deleted = await clean_replay_queue()

    # Step 4: Verify
    success = await verify_fix()

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Episodes updated with valid_at: {updated_valid_at}")
    print(f"Episodes updated with source: {updated_source}")
    print(f"Orphaned replay tasks deleted: {deleted}")
    print(f"Verification: {'✅ PASSED' if success else '⚠️  FAILED'}")
    print("\n💡 Next step: Restart the worker to clear retry queue")
    print("   docker restart graphiti-graphiti-worker-1")
    print("=" * 60)


if __name__ == '__main__':
    asyncio.run(main())

