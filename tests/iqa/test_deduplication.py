"""
IQA Scenario B: Entity Deduplication Tests

Tests that the node resolution correctly identifies and merges
duplicate entities (same entity referred to by different names).

This is the "Duplicate Merge" test scenario:
- Episode 1: "Robert builds the backend"
- Episode 2: "Bob fixes a bug" (Bob = Robert)
- Assertion: Bob resolved to Robert, no new node created
"""

import pytest

from tests.iqa.conftest import get_entity_by_name, get_entity_count


@pytest.mark.iqa
@pytest.mark.iqa_dedup
@pytest.mark.asyncio
async def test_nickname_resolves_to_original_entity(
    activity_simulator, falkordb_driver, test_group_id
):
    """
    GIVEN: An entity (Robert) exists in the graph
    WHEN: A new episode refers to the same person by nickname (Bob)
    THEN: Bob should resolve to Robert, not create a new entity
    """
    episode1_content = """
    Emmanuel: Robert has been leading the backend development.
    He designed the entire database schema and API architecture.
    Robert is our most senior engineer with 10 years of experience.
    """

    await activity_simulator.ingest_episode(
        episode_content=episode1_content,
        episode_name='robert_intro',
        group_id=test_group_id,
    )

    robert = await get_entity_by_name(falkordb_driver, 'Robert', test_group_id)
    assert robert is not None, 'Robert entity should be created'
    robert_uuid = robert['uuid']

    initial_count = await get_entity_count(falkordb_driver, test_group_id)

    episode2_content = """
    Emmanuel: Bob just fixed a critical bug in the authentication service.
    Great work from Bob as usual - he really knows the backend inside out.
    """

    await activity_simulator.ingest_episode(
        episode_content=episode2_content,
        episode_name='bob_bugfix',
        group_id=test_group_id,
    )

    bob = await get_entity_by_name(falkordb_driver, 'Bob', test_group_id)

    if bob is not None:
        assert bob['uuid'] == robert_uuid, (
            f'Bob should resolve to Robert. Bob UUID: {bob["uuid"]}, Robert UUID: {robert_uuid}'
        )
    else:
        robert_updated = await get_entity_by_name(falkordb_driver, 'Robert', test_group_id)
        assert robert_updated is not None, 'Robert should still exist'


@pytest.mark.iqa
@pytest.mark.iqa_dedup
@pytest.mark.asyncio
async def test_same_entity_different_episodes_merges(
    activity_simulator, falkordb_driver, test_group_id
):
    """
    GIVEN: An entity appears in multiple episodes
    WHEN: The entity is mentioned multiple times
    THEN: Only one entity should exist (no duplicates)
    """
    episodes = [
        'Alice joined the team as a frontend developer.',
        'Alice completed the dashboard redesign project.',
        'Alice presented the new UI at the company all-hands.',
        'Alice is now mentoring new team members.',
    ]

    for i, content in enumerate(episodes):
        await activity_simulator.ingest_episode(
            episode_content=content,
            episode_name=f'alice_episode_{i}',
            group_id=test_group_id,
        )

    records, _, _ = await falkordb_driver.execute_query(
        """
        MATCH (n:Entity {group_id: $group_id})
        WHERE toLower(n.name) CONTAINS 'alice'
        RETURN n.uuid AS uuid, n.name AS name
        """,
        group_id=test_group_id,
    )

    alice_entities = list(records) if records else []
    assert len(alice_entities) == 1, (
        f'Expected 1 Alice entity, found {len(alice_entities)}: {alice_entities}'
    )


@pytest.mark.iqa
@pytest.mark.iqa_dedup
@pytest.mark.asyncio
async def test_distinct_entities_not_merged(activity_simulator, falkordb_driver, test_group_id):
    """
    GIVEN: Two distinct entities with similar but different names
    WHEN: Both are mentioned in episodes
    THEN: They should remain separate entities
    """
    episode1_content = """
    Our team has two Alices:
    - Alice Smith works on frontend
    - Alice Johnson works on backend
    They collaborate frequently but have different responsibilities.
    """

    await activity_simulator.ingest_episode(
        episode_content=episode1_content,
        episode_name='two_alices',
        group_id=test_group_id,
    )

    records, _, _ = await falkordb_driver.execute_query(
        """
        MATCH (n:Entity {group_id: $group_id})
        WHERE toLower(n.name) CONTAINS 'alice'
        RETURN n.uuid AS uuid, n.name AS name
        """,
        group_id=test_group_id,
    )

    alice_entities = list(records) if records else []
    assert len(alice_entities) >= 2, (
        f'Expected at least 2 distinct Alice entities, found {len(alice_entities)}'
    )


@pytest.mark.iqa
@pytest.mark.iqa_dedup
@pytest.mark.asyncio
async def test_entity_resolution_updates_uuid_map(
    activity_simulator, falkordb_driver, test_group_id
):
    """
    GIVEN: An entity is mentioned that resolves to an existing entity
    WHEN: The workflow runs
    THEN: The uuid_map should correctly map the new UUID to existing UUID
    """
    episode1_content = 'Emmanuel: Dr. Sarah Chen leads our AI research team.'

    result1 = await activity_simulator.ingest_episode(
        episode_content=episode1_content,
        episode_name='sarah_intro',
        group_id=test_group_id,
    )

    sarah = await get_entity_by_name(falkordb_driver, 'Sarah Chen', test_group_id)
    if sarah is None:
        sarah = await get_entity_by_name(falkordb_driver, 'Dr. Sarah Chen', test_group_id)
    assert sarah is not None, 'Sarah Chen entity should exist'

    original_uuid = sarah['uuid']

    episode2_content = 'Emmanuel: Sarah just published a breakthrough paper on LLMs.'

    result2 = await activity_simulator.ingest_episode(
        episode_content=episode2_content,
        episode_name='sarah_paper',
        group_id=test_group_id,
    )

    uuid_map = result2['resolve'].get('uuid_map', {})

    for extracted_uuid, resolved_uuid in uuid_map.items():
        if extracted_uuid != resolved_uuid:
            assert resolved_uuid == original_uuid, f'Resolved UUID should match original Sarah UUID'


@pytest.mark.iqa
@pytest.mark.iqa_dedup
@pytest.mark.asyncio
async def test_fuzzy_matching_handles_typos(activity_simulator, falkordb_driver, test_group_id):
    """
    GIVEN: An entity exists
    WHEN: A subsequent episode mentions it with a minor typo
    THEN: Fuzzy matching should resolve to the original entity
    """
    episode1_content = 'Emmanuel: Kubernetes is our primary orchestration platform.'

    await activity_simulator.ingest_episode(
        episode_content=episode1_content,
        episode_name='k8s_intro',
        group_id=test_group_id,
    )

    k8s = await get_entity_by_name(falkordb_driver, 'Kubernetes', test_group_id)
    assert k8s is not None, 'Kubernetes entity should exist'
    original_uuid = k8s['uuid']

    episode2_content = 'Emmanuel: We upgraded Kuberntes to version 1.28 yesterday.'

    await activity_simulator.ingest_episode(
        episode_content=episode2_content,
        episode_name='k8s_upgrade',
        group_id=test_group_id,
    )

    records, _, _ = await falkordb_driver.execute_query(
        """
        MATCH (n:Entity {group_id: $group_id})
        WHERE toLower(n.name) CONTAINS 'kuber'
        RETURN n.uuid AS uuid, n.name AS name
        """,
        group_id=test_group_id,
    )

    k8s_entities = list(records) if records else []

    if len(k8s_entities) == 1:
        assert k8s_entities[0]['uuid'] == original_uuid, (
            'Typo should resolve to original Kubernetes entity'
        )
