"""
UUID utility functions for deterministic UUID generation.

This module provides utilities for generating deterministic UUIDs to prevent
entity duplication and race conditions in concurrent environments.
"""

from uuid import uuid5, NAMESPACE_DNS
import os
import re


def normalize_entity_name(name: str) -> str:
    """
    Normalize entity name for consistent deduplication.
    
    This ensures variations like "Claude", "claude", "CLAUDE" all map to the same entity.
    Also handles common separators and typos.
    
    Args:
        name: Original entity name
        
    Returns:
        Normalized entity name
    """
    if not os.getenv('DEDUP_NORMALIZE_NAMES', 'true').lower() == 'true':
        return name
    
    if not name or not name.strip():
        return name
    
    # Convert to lowercase
    normalized = name.lower()
    # Replace common separators with underscore
    normalized = re.sub(r'[-.\s]+', '_', normalized)
    # Remove special characters except underscores and alphanumeric
    normalized = re.sub(r'[^a-z0-9_]', '', normalized)
    # Remove multiple consecutive underscores
    normalized = re.sub(r'_+', '_', normalized)
    # Remove leading/trailing underscores
    normalized = normalized.strip('_')
    
    return normalized or name  # Fallback to original if normalization results in empty string


def generate_deterministic_uuid(name: str, group_id: str) -> str:
    """
    Generate a deterministic UUID based on entity name and group_id.
    
    This prevents race conditions where multiple workers create different UUIDs
    for the same entity name. Uses UUID5 with a namespace derived from the 
    name+group_id combination, ensuring consistent UUIDs across workers.
    
    Args:
        name: Entity name
        group_id: Entity group ID
        
    Returns:
        Deterministic UUID string
    """
    # Create a deterministic namespace based on group_id
    # This adds some pseudo-randomness while keeping it deterministic
    group_namespace = uuid5(NAMESPACE_DNS, f"graphiti.entity.{group_id}")
    
    # Normalize the name for consistent UUID generation
    normalized_name = normalize_entity_name(name)
    
    # Generate deterministic UUID based on the normalized name within this namespace
    entity_uuid = uuid5(group_namespace, normalized_name)
    
    return str(entity_uuid)


def generate_deterministic_edge_uuid(source_uuid: str, target_uuid: str, name: str, group_id: str) -> str:
    """
    Generate a deterministic UUID for an edge based on source, target, name and group_id.
    
    This ensures the same edge is not created multiple times between the same nodes.
    
    Args:
        source_uuid: Source node UUID
        target_uuid: Target node UUID  
        name: Edge name/type
        group_id: Edge group ID
        
    Returns:
        Deterministic UUID string
    """
    # Create a deterministic namespace based on group_id
    group_namespace = uuid5(NAMESPACE_DNS, f"graphiti.edge.{group_id}")
    
    # Create deterministic string combining source, target, and edge name
    edge_key = f"{source_uuid}|{target_uuid}|{name}"
    
    # Generate deterministic UUID
    edge_uuid = uuid5(group_namespace, edge_key)
    
    return str(edge_uuid)