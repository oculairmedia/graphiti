"""
Utility endpoints for Graphiti API.

Provides helper functions for external integrations like VibeSync.
"""

from fastapi import APIRouter, Query

from graphiti_core.utils.uuid_utils import (
    generate_deterministic_uuid,
    generate_deterministic_edge_uuid,
)

router = APIRouter(prefix='/utils', tags=['utils'])


@router.get('/uuid')
async def get_deterministic_uuid(
    name: str = Query(..., description='Entity name to generate UUID for'),
    group_id: str = Query(..., description='Group ID for namespace isolation'),
) -> dict[str, str]:
    """
    Generate a deterministic UUID for an entity.

    This endpoint allows external services (like VibeSync) to calculate
    the exact UUID that Graphiti would assign to an entity, without
    querying the graph first.

    The UUID is generated using:
    - UUID5 with NAMESPACE_DNS
    - Group-specific namespace: `graphiti.entity.{group_id}`
    - Normalized entity name

    Same name + group_id always produces the same UUID.

    Args:
        name: Entity name (will be normalized)
        group_id: Group ID for namespace isolation

    Returns:
        {"uuid": "<deterministic-uuid>", "normalized_name": "<normalized>"}
    """
    from graphiti_core.utils.uuid_utils import normalize_entity_name

    normalized = normalize_entity_name(name)
    uuid = generate_deterministic_uuid(name, group_id)

    return {
        'uuid': uuid,
        'name': name,
        'normalized_name': normalized,
        'group_id': group_id,
    }


@router.get('/edge-uuid')
async def get_deterministic_edge_uuid(
    source_uuid: str = Query(..., description='Source node UUID'),
    target_uuid: str = Query(..., description='Target node UUID'),
    name: str = Query(..., description='Edge name/type'),
    group_id: str = Query(..., description='Edge group ID'),
    source_group_id: str | None = Query(
        None, description='Source node group ID (for cross-group edges)'
    ),
    target_group_id: str | None = Query(
        None, description='Target node group ID (for cross-group edges)'
    ),
) -> dict[str, str | None]:
    """
    Generate a deterministic UUID for an edge.

    This endpoint allows external services to calculate the exact UUID
    that Graphiti would assign to an edge between two nodes.

    Includes optional source/target group IDs to prevent UUID collisions
    for edges connecting nodes across different groups.

    Args:
        source_uuid: Source node UUID
        target_uuid: Target node UUID
        name: Edge name/type (will be normalized to uppercase)
        group_id: Edge group ID
        source_group_id: Optional source node's group ID
        target_group_id: Optional target node's group ID

    Returns:
        {"uuid": "<deterministic-uuid>", "normalized_name": "<UPPERCASE_NAME>"}
    """
    normalized_name = name.strip().upper() if name and name.strip() else 'RELATES_TO'
    uuid = generate_deterministic_edge_uuid(
        source_uuid=source_uuid,
        target_uuid=target_uuid,
        name=name,
        group_id=group_id,
        source_group_id=source_group_id,
        target_group_id=target_group_id,
    )

    return {
        'uuid': uuid,
        'source_uuid': source_uuid,
        'target_uuid': target_uuid,
        'name': name,
        'normalized_name': normalized_name,
        'group_id': group_id,
    }
