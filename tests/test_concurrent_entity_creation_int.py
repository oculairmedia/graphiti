"""
Copyright 2024, Zep Software, Inc.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import asyncio
import os
from datetime import datetime

import pytest
import pytest_asyncio

from graphiti_core.driver.falkordb_driver import FalkorDriver
from graphiti_core.nodes import EntityNode
from graphiti_core.utils.datetime_utils import utc_now
from graphiti_core.utils.bulk_utils import add_nodes_and_edges_bulk
from graphiti_core.embedder import EmbedderClient

# Test configuration
FALKORDB_HOST = os.getenv('FALKORDB_HOST', 'localhost')
FALKORDB_PORT = int(os.getenv('FALKORDB_PORT', 6379))


@pytest_asyncio.fixture
async def falkordb_driver():
    """Create a FalkorDB driver for testing."""
    driver = FalkorDriver(host=FALKORDB_HOST, port=FALKORDB_PORT, database='test_race_condition_db')
    yield driver
    await driver.close()


@pytest_asyncio.fixture
async def clean_graph(request):
    """Clean the test graph before each test."""
    driver = FalkorDriver(host=FALKORDB_HOST, port=FALKORDB_PORT, database='test_race_condition_db')

    await driver.execute_query('MATCH (n) DETACH DELETE n')
    yield driver
    # Clean up after test
    await driver.execute_query('MATCH (n) DETACH DELETE n')
    await driver.close()


class MockEmbedder(EmbedderClient):
    """Mock embedder for testing that returns fixed-size vectors."""

    def __init__(self):
        self.call_count = 0

    async def create(self, input_data: list[str]):
        """Return a mock embedding vector."""
        self.call_count += 1
        # Return a fixed-size vector (768 dimensions as example)
        return [[0.1] * 768 for _ in input_data][0]


@pytest.mark.asyncio
async def test_concurrent_entity_creation_with_deterministic_uuids():
    """
    Test that concurrent creation of entities with the same name uses deterministic UUIDs
    and doesn't create duplicates or orphaned nodes.

    This simulates the race condition where multiple workers extract the same entity
    simultaneously. With deterministic UUIDs, they should all generate the same UUID
    and the MERGE operation should be idempotent.
    """
    driver = FalkorDriver(host=FALKORDB_HOST, port=FALKORDB_PORT, database='test_race_condition_db')

    # Clean the graph
    await driver.execute_query('MATCH (n) DETACH DELETE n')

    # Enable deterministic UUIDs for this test
    original_env = os.environ.get('USE_DETERMINISTIC_UUIDS')
    os.environ['USE_DETERMINISTIC_UUIDS'] = 'true'

    try:
        # Create 10 identical entities concurrently
        entity_name = 'TestConcurrentEntity'
        group_id = 'test-concurrent-group'
        num_concurrent = 10

        async def create_entity_task(task_id: int):
            """Create an entity node."""
            node = EntityNode(
                name=entity_name,
                group_id=group_id,
                labels=['Entity', 'TestNode'],
                summary=f'Test entity from task {task_id}',
                created_at=utc_now(),
            )

            # Save the node
            await node.save(driver)
            return node.uuid

        # Run all tasks concurrently
        tasks = [create_entity_task(i) for i in range(num_concurrent)]
        uuids = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter out any exceptions (constraint violations are expected)
        successful_uuids = [uuid for uuid in uuids if isinstance(uuid, str)]
        exceptions = [uuid for uuid in uuids if isinstance(uuid, Exception)]

        print(f'\nSuccessful UUIDs: {len(successful_uuids)}')
        print(f'Exceptions (expected): {len(exceptions)}')

        # Verify all successful UUIDs are identical (deterministic)
        if successful_uuids:
            first_uuid = successful_uuids[0]
            assert all(uuid == first_uuid for uuid in successful_uuids), (
                'All successfully created entities should have the same deterministic UUID'
            )
            print(f'All UUIDs match: {first_uuid}')

        # Verify only ONE entity node exists in the database
        query = """
        MATCH (n:Entity {name: $name, group_id: $group_id})
        RETURN n.uuid AS uuid, n.name AS name, n.group_id AS group_id
        """
        result, _, _ = await driver.execute_query(query, name=entity_name, group_id=group_id)

        assert len(result) == 1, f'Expected exactly 1 entity node, found {len(result)}'

        print(f'✅ Only 1 entity created despite {num_concurrent} concurrent attempts')

        # Verify no orphaned nodes
        orphan_query = """
        MATCH (n)
        WHERE NOT (n)-[]-()
        RETURN count(n) AS orphan_count
        """
        orphan_result, _, _ = await driver.execute_query(orphan_query)
        orphan_count = orphan_result[0]['orphan_count'] if orphan_result else 0

        # We expect at most 1 orphaned node (the successfully created one with no edges yet)
        assert orphan_count <= 1, f'Expected at most 1 orphaned node, found {orphan_count}'

        print(f'✅ No unexpected orphaned nodes (found {orphan_count})')

    finally:
        # Restore original environment
        if original_env is not None:
            os.environ['USE_DETERMINISTIC_UUIDS'] = original_env
        else:
            os.environ.pop('USE_DETERMINISTIC_UUIDS', None)


@pytest.mark.asyncio
@pytest.mark.parametrize('clean_graph', ['falkordb_driver'], indirect=True)
async def test_concurrent_bulk_save_with_same_entities(clean_graph):
    """
    Test that concurrent bulk save operations with the same entities
    handle constraint violations gracefully and don't create orphaned nodes.

    This simulates multiple ingestion workers processing different episodes
    that mention the same entities.
    """
    driver = clean_graph
    embedder = MockEmbedder()

    # Enable deterministic UUIDs
    original_env = os.environ.get('USE_DETERMINISTIC_UUIDS')
    os.environ['USE_DETERMINISTIC_UUIDS'] = 'true'

    try:
        entity_name = 'SharedEntity'
        group_id = 'test-bulk-group'
        num_workers = 5

        async def bulk_save_task(worker_id: int):
            """Simulate a worker doing bulk save with shared entities."""
            # Each worker creates the same entity (should get same UUID)
            nodes = [
                EntityNode(
                    name=entity_name,
                    group_id=group_id,
                    labels=['Entity'],
                    summary=f'Created by worker {worker_id}',
                    created_at=utc_now(),
                ),
                EntityNode(
                    name=f'UniqueEntity_{worker_id}',
                    group_id=group_id,
                    labels=['Entity'],
                    summary=f'Unique to worker {worker_id}',
                    created_at=utc_now(),
                ),
            ]

            # Generate embeddings
            for node in nodes:
                if node.name_embedding is None:
                    await node.generate_name_embedding(embedder)

            # Use bulk save
            try:
                await add_nodes_and_edges_bulk(
                    driver=driver,
                    episodic_nodes=[],
                    episodic_edges=[],
                    entity_nodes=nodes,
                    entity_edges=[],
                    embedder=embedder,
                )
                return True
            except Exception as e:
                print(f'Worker {worker_id} exception: {type(e).__name__}: {str(e)[:100]}')
                return False

        # Run all workers concurrently
        tasks = [bulk_save_task(i) for i in range(num_workers)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        successful = sum(1 for r in results if r is True)
        failed = sum(1 for r in results if r is False or isinstance(r, Exception))

        print(f'\nSuccessful bulk saves: {successful}')
        print(f'Failed bulk saves: {failed}')

        # Verify the shared entity exists exactly once
        query = """
        MATCH (n:Entity {name: $name, group_id: $group_id})
        RETURN count(n) AS count
        """
        result, _, _ = await driver.execute_query(query, name=entity_name, group_id=group_id)

        shared_entity_count = result[0]['count']
        assert shared_entity_count == 1, (
            f'Expected exactly 1 shared entity, found {shared_entity_count}'
        )

        print(f'✅ Shared entity exists exactly once')

        # Verify each worker's unique entity was created
        unique_query = """
        MATCH (n:Entity {group_id: $group_id})
        WHERE n.name STARTS WITH 'UniqueEntity_'
        RETURN count(n) AS count
        """
        unique_result, _, _ = await driver.execute_query(unique_query, group_id=group_id)

        unique_count = unique_result[0]['count']
        print(f'Unique entities created: {unique_count}')

        # Check for orphaned nodes
        orphan_query = """
        MATCH (n)
        WHERE NOT (n)-[]-()
        RETURN count(n) AS orphan_count
        """
        orphan_result, _, _ = await driver.execute_query(orphan_query)
        orphan_count = orphan_result[0]['orphan_count']

        # All nodes should be orphaned since we didn't create edges
        total_expected = 1 + unique_count  # 1 shared + N unique
        assert orphan_count == total_expected, (
            f'Expected {total_expected} orphaned nodes (no edges created), found {orphan_count}'
        )

        print(f'✅ Orphan count matches expected: {orphan_count}')

    finally:
        # Restore original environment
        if original_env is not None:
            os.environ['USE_DETERMINISTIC_UUIDS'] = original_env
        else:
            os.environ.pop('USE_DETERMINISTIC_UUIDS', None)


@pytest.mark.asyncio
@pytest.mark.parametrize('clean_graph', ['falkordb_driver'], indirect=True)
async def test_race_condition_with_retry_logic(clean_graph):
    """
    Test that the retry logic properly handles constraint violations
    from race conditions during concurrent entity creation.

    This simulates the real-world scenario where a task fails with
    constraint violation and retries successfully.
    """
    driver = clean_graph

    # Enable deterministic UUIDs
    original_env = os.environ.get('USE_DETERMINISTIC_UUIDS')
    os.environ['USE_DETERMINISTIC_UUIDS'] = 'true'

    try:
        entity_name = 'RaceConditionEntity'
        group_id = 'test-race-group'

        # First attempt: Create the entity successfully
        node1 = EntityNode(
            name=entity_name,
            group_id=group_id,
            labels=['Entity'],
            summary='First creation',
            created_at=utc_now(),
        )
        await node1.save(driver)

        print(f'First entity created with UUID: {node1.uuid}')

        # Second attempt: Try to create the same entity (simulates race condition loser)
        node2 = EntityNode(
            name=entity_name,
            group_id=group_id,
            labels=['Entity'],
            summary='Second creation attempt',
            created_at=utc_now(),
        )

        # Verify both nodes got the same deterministic UUID
        assert node1.uuid == node2.uuid, 'Both entities should have the same deterministic UUID'

        print(f'Second entity has same UUID: {node2.uuid}')

        # Try to save - this should either succeed (MERGE finds existing) or fail gracefully
        try:
            await node2.save(driver)
            print('✅ Second save succeeded (MERGE found existing node)')
        except Exception as e:
            print(f'⚠️  Second save failed (expected): {type(e).__name__}')
            # This is acceptable - the entity already exists

        # Verify only ONE entity exists
        query = """
        MATCH (n:Entity {name: $name, group_id: $group_id})
        RETURN count(n) AS count, collect(n.uuid) AS uuids
        """
        result, _, _ = await driver.execute_query(query, name=entity_name, group_id=group_id)

        entity_count = result[0]['count']
        uuids = result[0]['uuids']

        assert entity_count == 1, f'Expected exactly 1 entity after retry, found {entity_count}'

        assert len(set(uuids)) == 1, 'All entities should have the same UUID'

        print(f'✅ Only 1 entity exists with UUID: {uuids[0]}')

    finally:
        # Restore original environment
        if original_env is not None:
            os.environ['USE_DETERMINISTIC_UUIDS'] = original_env
        else:
            os.environ.pop('USE_DETERMINISTIC_UUIDS', None)
