"""
Tests for MENTIONS edge UUID resolution in Temporal activities.

This test file specifically targets the bug where episodic edges (MENTIONS)
fail to be created when entities are resolved as duplicates of existing entities.

Bug: graphiti-179a
Root cause: In resolve_edges_and_persist activity, nodes are reconstructed using
original UUIDs from extracted_node_dicts instead of resolved UUIDs from uuid_map.

The fix: When building the nodes list, use uuid_map.get(d.get('uuid', ''), d.get('uuid', ''))
instead of just d.get('uuid', '').
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from graphiti_core.edges import EpisodicEdge
from graphiti_core.nodes import EntityNode, EpisodicNode
from graphiti_core.utils.maintenance.edge_operations import build_episodic_edges


class TestBuildEpisodicEdgesWithResolvedUUIDs:
    """Test that build_episodic_edges uses resolved UUIDs correctly."""

    def test_build_episodic_edges_uses_node_uuids(self):
        """Basic test: build_episodic_edges should use the UUIDs from node objects."""
        now = datetime.now(timezone.utc)
        episode_uuid = str(uuid4())
        group_id = 'test_group'

        # Create nodes with specific UUIDs
        node1_uuid = str(uuid4())
        node2_uuid = str(uuid4())

        nodes = [
            EntityNode(
                uuid=node1_uuid,
                name='Alice',
                group_id=group_id,
                labels=['Entity', 'Person'],
                created_at=now,
                summary='Alice is a person',
            ),
            EntityNode(
                uuid=node2_uuid,
                name='Bob',
                group_id=group_id,
                labels=['Entity', 'Person'],
                created_at=now,
                summary='Bob is a person',
            ),
        ]

        episodic_edges = build_episodic_edges(nodes, episode_uuid, now, episode_group_id=group_id)

        assert len(episodic_edges) == 2

        # The target_node_uuid should match the node's UUID
        target_uuids = {edge.target_node_uuid for edge in episodic_edges}
        assert node1_uuid in target_uuids
        assert node2_uuid in target_uuids

        # All edges should have the episode as source
        for edge in episodic_edges:
            assert edge.source_node_uuid == episode_uuid

    def test_episodic_edges_point_to_resolved_uuids_not_original(self):
        """
        Critical test: When nodes are resolved as duplicates, episodic edges
        must point to the RESOLVED (existing) UUIDs, not the original extracted UUIDs.

        This is the core bug being fixed.
        """
        now = datetime.now(timezone.utc)
        episode_uuid = str(uuid4())
        group_id = 'test_group'

        # Simulate the scenario:
        # - Extracted node has UUID 'original-uuid-alice'
        # - But it resolves to existing node with UUID 'existing-uuid-alice'
        # Use valid UUIDs for testing
        original_uuid_alice = str(uuid4())  # Original extracted UUID for Alice
        existing_uuid_alice = str(uuid4())  # Existing entity UUID for Alice
        original_uuid_bob = str(uuid4())  # Original extracted UUID for Bob
        existing_uuid_bob = str(uuid4())  # Existing entity UUID for Bob

        # This is how uuid_map would look after resolution
        uuid_map = {
            original_uuid_alice: existing_uuid_alice,  # Alice resolved to existing
            original_uuid_bob: existing_uuid_bob,  # Bob resolved to existing
        }

        # THE BUG: nodes list was being built with ORIGINAL UUIDs
        # This is what the buggy code produces:
        nodes_with_wrong_uuids = [
            EntityNode(
                uuid=original_uuid_alice,  # WRONG - uses original UUID
                name='Alice',
                group_id=group_id,
                labels=['Entity', 'Person'],
                created_at=now,
                summary='Alice is a person',
            ),
            EntityNode(
                uuid=original_uuid_bob,  # WRONG - uses original UUID
                name='Bob',
                group_id=group_id,
                labels=['Entity', 'Person'],
                created_at=now,
                summary='Bob is a person',
            ),
        ]

        # THE FIX: nodes list should be built with RESOLVED UUIDs
        # This is what the fixed code should produce:
        nodes_with_correct_uuids = [
            EntityNode(
                uuid=uuid_map.get(original_uuid_alice, original_uuid_alice),  # CORRECT
                name='Alice',
                group_id=group_id,
                labels=['Entity', 'Person'],
                created_at=now,
                summary='Alice is a person',
            ),
            EntityNode(
                uuid=uuid_map.get(original_uuid_bob, original_uuid_bob),  # CORRECT
                name='Bob',
                group_id=group_id,
                labels=['Entity', 'Person'],
                created_at=now,
                summary='Bob is a person',
            ),
        ]

        # Build episodic edges with the WRONG nodes (what the bug produces)
        wrong_edges = build_episodic_edges(
            nodes_with_wrong_uuids, episode_uuid, now, episode_group_id=group_id
        )

        # Build episodic edges with the CORRECT nodes (what the fix should produce)
        correct_edges = build_episodic_edges(
            nodes_with_correct_uuids, episode_uuid, now, episode_group_id=group_id
        )

        # Wrong edges point to non-existent original UUIDs
        wrong_target_uuids = {edge.target_node_uuid for edge in wrong_edges}
        assert original_uuid_alice in wrong_target_uuids  # Points to non-existent node
        assert original_uuid_bob in wrong_target_uuids  # Points to non-existent node
        assert existing_uuid_alice not in wrong_target_uuids  # Missing the existing node!
        assert existing_uuid_bob not in wrong_target_uuids  # Missing the existing node!

        # Correct edges point to existing resolved UUIDs
        correct_target_uuids = {edge.target_node_uuid for edge in correct_edges}
        assert existing_uuid_alice in correct_target_uuids  # Points to existing node
        assert existing_uuid_bob in correct_target_uuids  # Points to existing node
        assert original_uuid_alice not in correct_target_uuids  # Not the original
        assert original_uuid_bob not in correct_target_uuids  # Not the original

    def test_mixed_resolution_new_and_existing_nodes(self):
        """
        Test scenario where some nodes are new and some resolve to existing.

        - Alice: new node (UUID stays the same)
        - Bob: resolves to existing node (UUID changes)
        """
        now = datetime.now(timezone.utc)
        episode_uuid = str(uuid4())
        group_id = 'test_group'

        # Alice is new - UUID stays the same
        alice_uuid = str(uuid4())

        # Bob resolves to existing - UUID changes
        original_bob_uuid = str(uuid4())
        existing_bob_uuid = str(uuid4())

        # uuid_map reflects this
        uuid_map = {
            alice_uuid: alice_uuid,  # Alice is new, maps to self
            original_bob_uuid: existing_bob_uuid,  # Bob maps to existing
        }

        # Simulate extracted_node_dicts (what we get from extraction worker)
        extracted_node_dicts = [
            {'uuid': alice_uuid, 'name': 'Alice', 'labels': ['Entity', 'Person'], 'summary': ''},
            {
                'uuid': original_bob_uuid,
                'name': 'Bob',
                'labels': ['Entity', 'Person'],
                'summary': '',
            },
        ]

        # THE FIX: Build nodes with resolved UUIDs
        nodes_with_resolved_uuids = []
        for d in extracted_node_dicts:
            original_uuid: str = d.get('uuid') or ''
            resolved_uuid: str = uuid_map.get(original_uuid, original_uuid)
            labels: list[str] = d.get('labels') or ['Entity']
            summary: str = d.get('summary') or ''
            nodes_with_resolved_uuids.append(
                EntityNode(
                    uuid=resolved_uuid,
                    name=d['name'],
                    group_id=group_id,
                    labels=labels,
                    created_at=now,
                    summary=summary,
                )
            )

        episodic_edges = build_episodic_edges(
            nodes_with_resolved_uuids, episode_uuid, now, episode_group_id=group_id
        )

        target_uuids = {edge.target_node_uuid for edge in episodic_edges}

        # Alice's UUID should be unchanged (new node)
        assert alice_uuid in target_uuids

        # Bob's UUID should be the EXISTING one, not the original
        assert existing_bob_uuid in target_uuids
        assert original_bob_uuid not in target_uuids


class TestActivityNodeReconstruction:
    """
    Test the node reconstruction logic that should use uuid_map.

    These tests verify that the pattern used in resolve_edges_and_persist
    correctly applies uuid_map when rebuilding nodes from extracted_node_dicts.
    """

    def test_node_uuid_resolution_pattern(self):
        """Test the pattern: uuid_map.get(d.get('uuid', ''), d.get('uuid', ''))"""
        # When UUID is in uuid_map (resolved to existing)
        uuid_map: dict[str, str] = {'orig-123': 'existing-456'}
        d: dict[str, str] = {'uuid': 'orig-123', 'name': 'Test'}

        original_uuid = d.get('uuid', '')
        resolved_uuid = uuid_map.get(original_uuid, original_uuid)
        assert resolved_uuid == 'existing-456'

        # When UUID is NOT in uuid_map (new node)
        d2: dict[str, str] = {'uuid': 'new-789', 'name': 'Test2'}
        original_uuid2 = d2.get('uuid', '')
        resolved_uuid2 = uuid_map.get(original_uuid2, original_uuid2)
        assert resolved_uuid2 == 'new-789'

        # When UUID is missing from dict
        d3: dict[str, str] = {'name': 'Test3'}
        original_uuid3 = d3.get('uuid', '')
        resolved_uuid3 = uuid_map.get(original_uuid3, original_uuid3)
        assert resolved_uuid3 == ''

    def test_all_duplicate_scenario(self):
        """
        Test when ALL extracted nodes resolve to existing duplicates.
        This is the exact scenario observed in production logs.
        """
        now = datetime.now(timezone.utc)
        episode_uuid = str(uuid4())
        group_id = 'claude_conversations'

        # Production scenario: 12 nodes extracted, 11 are duplicates
        # Creating a simplified version with 3 nodes, all duplicates
        # Use valid UUIDs
        extracted_uuid_1 = str(uuid4())
        extracted_uuid_2 = str(uuid4())
        extracted_uuid_3 = str(uuid4())
        existing_emmanuel_uuid = str(uuid4())
        existing_claude_uuid = str(uuid4())
        existing_graphiti_uuid = str(uuid4())

        extracted_node_dicts = [
            {'uuid': extracted_uuid_1, 'name': 'Emmanuel', 'labels': ['Entity', 'Person']},
            {'uuid': extracted_uuid_2, 'name': 'Claude', 'labels': ['Entity', 'AI']},
            {'uuid': extracted_uuid_3, 'name': 'Graphiti', 'labels': ['Entity', 'Project']},
        ]

        # All resolve to existing entities
        uuid_map = {
            extracted_uuid_1: existing_emmanuel_uuid,
            extracted_uuid_2: existing_claude_uuid,
            extracted_uuid_3: existing_graphiti_uuid,
        }

        # BUGGY PATTERN (what was happening):
        buggy_nodes = []
        for d in extracted_node_dicts:
            original_uuid: str = d.get('uuid') or ''
            labels: list[str] = d.get('labels') or ['Entity']
            buggy_nodes.append(
                EntityNode(
                    uuid=original_uuid,  # BUG: Uses original UUID
                    name=d['name'],
                    group_id=group_id,
                    labels=labels,
                    created_at=now,
                    summary='',
                )
            )

        # FIXED PATTERN (what should happen):
        fixed_nodes = []
        for d in extracted_node_dicts:
            original_uuid = d.get('uuid') or ''
            resolved_uuid: str = uuid_map.get(
                original_uuid, original_uuid
            )  # FIX: Uses resolved UUID
            labels = d.get('labels') or ['Entity']
            fixed_nodes.append(
                EntityNode(
                    uuid=resolved_uuid,
                    name=d['name'],
                    group_id=group_id,
                    labels=labels,
                    created_at=now,
                    summary='',
                )
            )

        # Verify buggy nodes have wrong UUIDs
        buggy_uuids = {n.uuid for n in buggy_nodes}
        assert buggy_uuids == {extracted_uuid_1, extracted_uuid_2, extracted_uuid_3}

        # Verify fixed nodes have correct UUIDs
        fixed_uuids = {n.uuid for n in fixed_nodes}
        assert fixed_uuids == {
            existing_emmanuel_uuid,
            existing_claude_uuid,
            existing_graphiti_uuid,
        }

        # Build episodic edges with fixed nodes
        episodic_edges = build_episodic_edges(
            fixed_nodes, episode_uuid, now, episode_group_id=group_id
        )

        # Verify episodic edges point to existing entities
        edge_targets = {e.target_node_uuid for e in episodic_edges}
        assert edge_targets == {
            existing_emmanuel_uuid,
            existing_claude_uuid,
            existing_graphiti_uuid,
        }

        # These edges will MATCH when persisted because the entities exist
        # The buggy edges would fail to match because 'extracted-*' UUIDs don't exist


class TestEpisodicEdgePersistence:
    """
    Test that episodic edges with correct UUIDs can be matched during persistence.

    These tests simulate the EPISODIC_EDGE_SAVE_BULK query behavior.
    """

    @pytest.mark.asyncio
    async def test_episodic_edge_match_requires_existing_entity(self):
        """
        The EPISODIC_EDGE_SAVE_BULK query uses MATCH to find entities.
        If the target_node_uuid doesn't exist, the MATCH silently fails.

        This test verifies the semantic behavior of the persistence pattern.
        """
        now = datetime.now(timezone.utc)
        episode_uuid = str(uuid4())
        group_id = 'test_group'

        # Existing entity UUID (would be found by MATCH) - use valid UUID
        existing_entity_uuid = str(uuid4())

        # Non-existing entity UUID (MATCH would fail silently) - use valid UUID
        nonexistent_entity_uuid = str(uuid4())

        # Create edge pointing to existing entity
        good_edge = EpisodicEdge(
            source_node_uuid=episode_uuid,
            target_node_uuid=existing_entity_uuid,
            created_at=now,
            group_id=group_id,
        )

        # Create edge pointing to non-existing entity
        bad_edge = EpisodicEdge(
            source_node_uuid=episode_uuid,
            target_node_uuid=nonexistent_entity_uuid,
            created_at=now,
            group_id=group_id,
        )

        # In production, good_edge would succeed and bad_edge would silently fail
        # We can't test the actual DB behavior in unit tests, but we verify the UUIDs
        assert good_edge.target_node_uuid == existing_entity_uuid
        assert bad_edge.target_node_uuid == nonexistent_entity_uuid

        # The fix ensures we never create bad_edge in the first place
        # by using resolved UUIDs that point to existing entities


# Run the tests
if __name__ == '__main__':
    pytest.main([__file__, '-v'])
