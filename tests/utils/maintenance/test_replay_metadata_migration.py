import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from graphiti_core.utils.maintenance.replay_metadata_migration import (
    apply_replay_metadata_migration,
    rollback_replay_metadata_migration,
)


@pytest.mark.asyncio
async def test_apply_replay_metadata_migration_backfills_counts():
    created_calls = 0
    updated_calls = 0

    async def fake_execute_query(query, **kwargs):
        nonlocal created_calls, updated_calls
        if 'RETURN count(rm) AS created' in query:
            if created_calls == 0:
                created_calls += 1
                return ([{'created': 2}], None, None)
            return ([{'created': 0}], None, None)
        if 'RETURN count(e) AS updated' in query:
            if updated_calls == 0:
                updated_calls += 1
                return ([{'updated': 3}], None, None)
            return ([{'updated': 0}], None, None)
        return None

    driver = MagicMock()
    driver.provider = 'neo4j'
    driver.execute_query = AsyncMock(side_effect=fake_execute_query)

    stats = await apply_replay_metadata_migration(driver, batch_size=100)

    assert stats.created_metadata_nodes == 2
    assert stats.hydrated_episode_counts == 3
    assert stats.index_operations == 2

    create_calls = [
        call for call in driver.execute_query.call_args_list if 'RETURN count(rm) AS created' in call.args[0]
    ]
    assert create_calls, 'replay metadata creation query was not executed'
    assert any('now' in call.kwargs for call in create_calls)


@pytest.mark.asyncio
async def test_rollback_replay_metadata_migration_removes_nodes():
    delete_calls = 0
    clear_calls = 0

    async def fake_execute_query(query, **kwargs):
        nonlocal delete_calls, clear_calls
        if 'RETURN count(rm) AS deleted' in query:
            if delete_calls == 0:
                delete_calls += 1
                return ([{'deleted': 4}], None, None)
            return ([{'deleted': 0}], None, None)
        if 'RETURN count(e) AS cleared' in query:
            if clear_calls == 0:
                clear_calls += 1
                return ([{'cleared': 6}], None, None)
            return ([{'cleared': 0}], None, None)
        return None

    driver = MagicMock()
    driver.provider = 'falkordb'
    driver.execute_query = AsyncMock(side_effect=fake_execute_query)

    stats = await rollback_replay_metadata_migration(driver, batch_size=25)

    assert stats.created_metadata_nodes == 4
    assert stats.hydrated_episode_counts == 6
    assert stats.index_operations == 2

    delete_calls_args = [
        call for call in driver.execute_query.call_args_list if 'RETURN count(rm) AS deleted' in call.args[0]
    ]
    assert delete_calls_args, 'metadata deletion query was not executed'
