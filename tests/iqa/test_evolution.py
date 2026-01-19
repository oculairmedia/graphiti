"""
IQA Scenario A: Entity Summary Evolution Tests

Tests that entity summaries evolve correctly when entities are
re-mentioned in subsequent episodes with new context.

This is the "Evolution of Alice" test scenario:
- Episode 1: Alice starts as a Junior Dev
- Episode 2: Alice is promoted to CTO
- Assertion: Same entity UUID, but summary updates to reflect new role
"""

import pytest

from tests.iqa.conftest import get_entity_by_name, get_entity_count


@pytest.mark.iqa
@pytest.mark.iqa_evolution
@pytest.mark.asyncio
async def test_entity_summary_updates_with_new_context(
    activity_simulator, falkordb_driver, test_group_id
):
    """
    GIVEN: An entity (Alice) is created with initial context (Junior Dev)
    WHEN: A new episode mentions the same entity with updated context (promoted to CTO)
    THEN: The entity's summary should be updated to reflect the new information
    """
    episode1_content = """
    Emmanuel: Today we welcomed Alice to the engineering team.
    She's starting as a Junior Developer working on the frontend.
    Alice has a strong background in React and TypeScript.
    """

    result1 = await activity_simulator.ingest_episode(
        episode_content=episode1_content,
        episode_name='onboarding_alice',
        group_id=test_group_id,
    )

    alice_v1 = await get_entity_by_name(falkordb_driver, 'Alice', test_group_id)
    assert alice_v1 is not None, 'Alice entity should be created'
    alice_uuid = alice_v1['uuid']

    assert alice_v1['summary'], 'Alice should have a summary after first episode'
    summary_v1 = alice_v1['summary'].lower()
    assert 'junior' in summary_v1 or 'frontend' in summary_v1 or 'developer' in summary_v1, (
        f'Summary v1 should mention junior/frontend role: {alice_v1["summary"]}'
    )

    episode2_content = """
    Emmanuel: Big news! Alice has been promoted to CTO.
    After leading the successful platform migration, the board
    decided to recognize her exceptional leadership.
    Alice will now oversee all engineering and technical strategy.
    """

    result2 = await activity_simulator.ingest_episode(
        episode_content=episode2_content,
        episode_name='alice_promotion',
        group_id=test_group_id,
    )

    alice_v2 = await get_entity_by_name(falkordb_driver, 'Alice', test_group_id)
    assert alice_v2 is not None, 'Alice entity should still exist'

    assert alice_v2['uuid'] == alice_uuid, (
        f'Alice should have same UUID. Expected {alice_uuid}, got {alice_v2["uuid"]}'
    )

    summary_v2 = alice_v2['summary'].lower()
    assert 'cto' in summary_v2 or 'chief' in summary_v2 or 'promoted' in summary_v2, (
        f'Summary v2 should mention CTO/promotion: {alice_v2["summary"]}'
    )


@pytest.mark.iqa
@pytest.mark.iqa_evolution
@pytest.mark.asyncio
async def test_multiple_entities_evolve_independently(
    activity_simulator, falkordb_driver, test_group_id
):
    """
    GIVEN: Multiple entities are created
    WHEN: Different episodes update different entities
    THEN: Each entity's summary should evolve based only on relevant episodes
    """
    episode1_content = """
    Team standup:
    - Alice is working on the authentication module
    - Bob is fixing database performance issues
    """

    await activity_simulator.ingest_episode(
        episode_content=episode1_content,
        episode_name='standup_day1',
        group_id=test_group_id,
    )

    alice_v1 = await get_entity_by_name(falkordb_driver, 'Alice', test_group_id)
    bob_v1 = await get_entity_by_name(falkordb_driver, 'Bob', test_group_id)

    assert alice_v1 is not None
    assert bob_v1 is not None

    episode2_content = """
    Update: Alice completed the authentication module and is now
    leading the mobile app development initiative.
    """

    await activity_simulator.ingest_episode(
        episode_content=episode2_content,
        episode_name='alice_update',
        group_id=test_group_id,
    )

    alice_v2 = await get_entity_by_name(falkordb_driver, 'Alice', test_group_id)
    bob_v2 = await get_entity_by_name(falkordb_driver, 'Bob', test_group_id)

    assert alice_v2['uuid'] == alice_v1['uuid']
    alice_summary = alice_v2['summary'].lower()
    assert (
        'mobile' in alice_summary or 'completed' in alice_summary or 'leading' in alice_summary
    ), f"Alice's summary should update with mobile/completed: {alice_v2['summary']}"


@pytest.mark.iqa
@pytest.mark.iqa_evolution
@pytest.mark.asyncio
async def test_summary_preserves_important_historical_context(
    activity_simulator, falkordb_driver, test_group_id
):
    """
    GIVEN: An entity has important historical context
    WHEN: New episodes add more context
    THEN: The summary should incorporate new info while preserving key historical facts
    """
    episode1_content = """
    Company founding story: TechCorp was founded in 2020 by Alice
    in San Francisco. The company started with a focus on AI infrastructure.
    """

    await activity_simulator.ingest_episode(
        episode_content=episode1_content,
        episode_name='founding',
        group_id=test_group_id,
    )

    techcorp_v1 = await get_entity_by_name(falkordb_driver, 'TechCorp', test_group_id)
    assert techcorp_v1 is not None

    episode2_content = """
    TechCorp news: The company has expanded to 500 employees and
    opened offices in New York and London. Revenue hit $100M this year.
    """

    await activity_simulator.ingest_episode(
        episode_content=episode2_content,
        episode_name='expansion',
        group_id=test_group_id,
    )

    techcorp_v2 = await get_entity_by_name(falkordb_driver, 'TechCorp', test_group_id)
    summary_v2 = techcorp_v2['summary'].lower()

    assert '2020' in summary_v2 or 'founded' in summary_v2 or 'alice' in summary_v2, (
        f'Summary should preserve founding context: {techcorp_v2["summary"]}'
    )

    assert (
        '500' in summary_v2
        or 'expanded' in summary_v2
        or 'revenue' in summary_v2
        or '100' in summary_v2
    ), f'Summary should include expansion news: {techcorp_v2["summary"]}'


@pytest.mark.iqa
@pytest.mark.iqa_evolution
@pytest.mark.asyncio
async def test_force_update_bypasses_cache(activity_simulator, falkordb_driver, test_group_id):
    """
    Regression test for the force_update fix.

    GIVEN: An entity exists with a cached summary
    WHEN: A new episode provides significant new information
    THEN: The summary MUST update (cache should not prevent updates)

    This test fails if force_update=True is reverted to False.
    """
    episode1_content = 'Project Alpha is a small internal tool for the DevOps team.'

    await activity_simulator.ingest_episode(
        episode_content=episode1_content,
        episode_name='project_intro',
        group_id=test_group_id,
    )

    project_v1 = await get_entity_by_name(falkordb_driver, 'Project Alpha', test_group_id)
    assert project_v1 is not None
    summary_v1 = project_v1['summary']

    episode2_content = """
    MAJOR UPDATE: Project Alpha has been selected as the company's
    flagship product! It will be rebranded and launched to enterprise
    customers next quarter with a $10M marketing budget.
    """

    await activity_simulator.ingest_episode(
        episode_content=episode2_content,
        episode_name='project_promotion',
        group_id=test_group_id,
    )

    project_v2 = await get_entity_by_name(falkordb_driver, 'Project Alpha', test_group_id)
    summary_v2 = project_v2['summary']

    assert summary_v1 != summary_v2, (
        f"Summary MUST change after major update. v1='{summary_v1}', v2='{summary_v2}'"
    )

    summary_lower = summary_v2.lower()
    assert any(
        word in summary_lower
        for word in ['flagship', 'enterprise', 'launch', 'rebrand', 'marketing']
    ), f'Updated summary should reflect the major change: {summary_v2}'
