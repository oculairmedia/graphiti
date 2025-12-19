"""
Factory functions for creating test objects.

Provides convenient functions for creating EntityNodes, EpisodicNodes,
and other Graphiti objects with sensible defaults for testing.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def create_test_uuid(seed: str | None = None) -> str:
    """
    Create a test UUID.

    Args:
        seed: Optional seed for deterministic UUID (uses uuid5)
              If None, generates a random uuid4
    """
    if seed:
        from uuid import uuid5, NAMESPACE_DNS

        return str(uuid5(NAMESPACE_DNS, seed))
    return str(uuid4())


def create_test_group_id(name: str = 'test') -> str:
    """
    Create a test group ID.

    Args:
        name: Base name for the group ID
    """
    return f'{name}_group_{uuid4().hex[:8]}'


def create_entity_node(
    name: str = 'Test Entity',
    uuid: str | None = None,
    group_id: str | None = None,
    labels: list[str] | None = None,
    summary: str = '',
    name_embedding: list[float] | None = None,
    attributes: dict[str, Any] | None = None,
    created_at: datetime | None = None,
) -> dict[str, Any]:
    """
    Create an EntityNode-compatible dictionary for testing.

    This returns a dict that can be used to construct an EntityNode
    or passed to functions expecting EntityNode-like data.

    Args:
        name: Entity name
        uuid: Entity UUID (generated if not provided)
        group_id: Group ID (generated if not provided)
        labels: Entity labels (default: ['Entity'])
        summary: Entity summary
        name_embedding: Name embedding vector
        attributes: Additional attributes
        created_at: Creation timestamp (default: now)

    Returns:
        Dict with EntityNode fields
    """
    return {
        'uuid': uuid or create_test_uuid(),
        'name': name,
        'group_id': group_id or create_test_group_id(),
        'labels': labels or ['Entity'],
        'summary': summary,
        'name_embedding': name_embedding,
        'attributes': attributes or {},
        'created_at': created_at or datetime.now(timezone.utc),
    }


def create_episodic_node(
    name: str = 'Test Episode',
    content: str = 'Test episode content',
    uuid: str | None = None,
    group_id: str | None = None,
    source: str = 'text',
    source_description: str = 'Test source',
    valid_at: datetime | None = None,
    created_at: datetime | None = None,
    entity_edges: list[str] | None = None,
) -> dict[str, Any]:
    """
    Create an EpisodicNode-compatible dictionary for testing.

    Args:
        name: Episode name
        content: Episode content
        uuid: Episode UUID (generated if not provided)
        group_id: Group ID (generated if not provided)
        source: Source type ('text', 'message', 'json')
        source_description: Description of the source
        valid_at: Validity timestamp (default: now)
        created_at: Creation timestamp (default: now)
        entity_edges: List of entity edge UUIDs

    Returns:
        Dict with EpisodicNode fields
    """
    now = datetime.now(timezone.utc)
    return {
        'uuid': uuid or create_test_uuid(),
        'name': name,
        'group_id': group_id or create_test_group_id(),
        'labels': ['Episodic'],
        'source': source,
        'source_description': source_description,
        'content': content,
        'valid_at': valid_at or now,
        'created_at': created_at or now,
        'entity_edges': entity_edges or [],
    }


def create_edge(
    source_uuid: str | None = None,
    target_uuid: str | None = None,
    uuid: str | None = None,
    group_id: str | None = None,
    fact: str = 'relates to',
    rel_type: str = 'RELATES_TO',
    fact_embedding: list[float] | None = None,
    episodes: list[str] | None = None,
    created_at: datetime | None = None,
    valid_at: datetime | None = None,
    invalid_at: datetime | None = None,
    attributes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Create an EntityEdge-compatible dictionary for testing.

    Args:
        source_uuid: Source entity UUID
        target_uuid: Target entity UUID
        uuid: Edge UUID (generated if not provided)
        group_id: Group ID (generated if not provided)
        fact: Edge fact/description
        rel_type: Relationship type
        fact_embedding: Fact embedding vector
        episodes: List of episode UUIDs
        created_at: Creation timestamp
        valid_at: Valid from timestamp
        invalid_at: Valid until timestamp (None for valid)
        attributes: Additional attributes

    Returns:
        Dict with EntityEdge fields
    """
    now = datetime.now(timezone.utc)
    return {
        'uuid': uuid or create_test_uuid(),
        'source_uuid': source_uuid or create_test_uuid(),
        'target_uuid': target_uuid or create_test_uuid(),
        'group_id': group_id or create_test_group_id(),
        'fact': fact,
        'name': rel_type,
        'fact_embedding': fact_embedding,
        'episodes': episodes or [],
        'created_at': created_at or now,
        'valid_at': valid_at or now,
        'invalid_at': invalid_at,
        'attributes': attributes or {},
    }


def create_community_node(
    name: str = 'Test Community',
    uuid: str | None = None,
    group_id: str | None = None,
    summary: str = '',
    name_embedding: list[float] | None = None,
    created_at: datetime | None = None,
) -> dict[str, Any]:
    """
    Create a CommunityNode-compatible dictionary for testing.

    Args:
        name: Community name
        uuid: Community UUID (generated if not provided)
        group_id: Group ID (generated if not provided)
        summary: Community summary
        name_embedding: Name embedding vector
        created_at: Creation timestamp

    Returns:
        Dict with CommunityNode fields
    """
    return {
        'uuid': uuid or create_test_uuid(),
        'name': name,
        'group_id': group_id or create_test_group_id(),
        'labels': ['Community'],
        'summary': summary,
        'name_embedding': name_embedding,
        'created_at': created_at or datetime.now(timezone.utc),
    }


def create_search_result(
    nodes: list[dict] | None = None,
    edges: list[dict] | None = None,
    communities: list[dict] | None = None,
) -> dict[str, Any]:
    """
    Create a SearchResults-compatible dictionary for testing.

    Args:
        nodes: List of node dicts
        edges: List of edge dicts
        communities: List of community dicts

    Returns:
        Dict with SearchResults fields
    """
    return {
        'nodes': nodes or [],
        'edges': edges or [],
        'communities': communities or [],
    }


# Pre-built test data for common scenarios

TEST_ENTITIES = [
    create_entity_node(name='Alice', summary='A person named Alice'),
    create_entity_node(name='Bob', summary='A person named Bob'),
    create_entity_node(name='Acme Corp', labels=['Entity', 'Organization'], summary='A company'),
]

TEST_EPISODES = [
    create_episodic_node(
        name='episode_1',
        content='Alice met Bob at the coffee shop.',
        source='text',
    ),
    create_episodic_node(
        name='episode_2',
        content='Bob works at Acme Corp.',
        source='text',
    ),
]


def get_test_entities(count: int = 3) -> list[dict[str, Any]]:
    """Get a list of test entity dicts."""
    entities = []
    names = ['Alice', 'Bob', 'Charlie', 'David', 'Eve', 'Frank', 'Grace', 'Henry', 'Ivy', 'Jack']
    for i in range(min(count, len(names))):
        entities.append(create_entity_node(name=names[i]))
    return entities


def get_test_episodes(count: int = 3) -> list[dict[str, Any]]:
    """Get a list of test episode dicts."""
    contents = [
        'User discussed project plans.',
        'Team meeting about quarterly goals.',
        'Code review session completed.',
        'Documentation update finished.',
        'Bug fix deployed to production.',
    ]
    episodes = []
    for i in range(min(count, len(contents))):
        episodes.append(
            create_episodic_node(
                name=f'episode_{i}',
                content=contents[i],
            )
        )
    return episodes
