"""
UUID utility functions for deterministic UUID generation.

This module provides utilities for generating deterministic UUIDs to prevent
entity duplication and race conditions in concurrent environments.
"""

from uuid import uuid5, NAMESPACE_DNS
import os
import re
import string
import unicodedata
from difflib import SequenceMatcher
from typing import Dict, List, Set


# Common entity name variations for normalization
COMMON_TITLES = {'mr', 'mrs', 'ms', 'dr', 'prof', 'sir', 'madam'}
COMMON_SUFFIXES = {'jr', 'sr', 'ii', 'iii', 'iv', 'phd', 'md', 'esq'}
COMPANY_INDICATORS = {'inc', 'corp', 'ltd', 'llc', 'co', 'company', 'corporation', 'limited'}

# Common abbreviation mappings
ABBREVIATION_MAP = {
    # Personal titles
    'dr': 'doctor',
    'prof': 'professor',
    'mr': 'mister',
    'mrs': 'missus',
    'ms': 'miss',
    # Common name abbreviations
    'alex': 'alexander',
    'bob': 'robert', 
    'bill': 'william',
    'dick': 'richard',
    'jim': 'james',
    'joe': 'joseph',
    'mike': 'michael',
    'nick': 'nicholas',
    'pat': 'patricia',
    'sam': 'samuel',
    'tom': 'thomas',
    'tony': 'anthony',
    # Organization types
    'corp': 'corporation',
    'inc': 'incorporated',
    'ltd': 'limited',
    'co': 'company'
}


def normalize_entity_name(name: str, enhanced: bool = True) -> str:
    """
    Enhanced entity name normalization for consistent deduplication.
    
    Handles case variations, unicode normalization, common abbreviations,
    titles/suffixes, and various formatting inconsistencies.
    
    Args:
        name: Original entity name
        enhanced: Whether to use enhanced normalization features
        
    Returns:
        Normalized entity name
    """
    if not os.getenv('DEDUP_NORMALIZE_NAMES', 'true').lower() == 'true':
        return name
    
    if not name or not name.strip():
        return name
    
    original_name = name
    
    if enhanced and os.getenv('DEDUP_ENHANCED_NORMALIZATION', 'true').lower() == 'true':
        # Use enhanced normalization
        normalized = _enhanced_normalize(name)
    else:
        # Use basic normalization
        normalized = _basic_normalize(name)
    
    return normalized or original_name  # Fallback to original if normalization results in empty string


def _basic_normalize(name: str) -> str:
    """Basic name normalization (original functionality)"""
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
    
    return normalized


def _enhanced_normalize(name: str) -> str:
    """Enhanced name normalization with additional features"""
    if not name:
        return name
    
    # Step 1: Unicode normalization to handle accented characters
    normalized = unicodedata.normalize('NFKD', name)
    normalized = ''.join(c for c in normalized if not unicodedata.combining(c))
    
    # Step 2: Convert to lowercase
    normalized = normalized.lower()
    
    # Step 3: Handle contractions and possessives
    normalized = re.sub(r"'s\b", '', normalized)  # Remove possessive 's
    normalized = re.sub(r"n't\b", 'not', normalized)  # Convert contractions (no underscore yet)
    
    # Step 4: Split into tokens for processing
    tokens = re.findall(r'\w+', normalized)
    
    if not tokens:
        return name
    
    # Step 5: Process tokens
    processed_tokens = []
    for i, token in enumerate(tokens):
        # Skip common titles at the beginning
        if token in COMMON_TITLES and i == 0:
            continue
        
        # Skip common suffixes at the end  
        if token in COMMON_SUFFIXES and i == len(tokens) - 1:
            continue
            
        # Skip company indicators for organizations
        if token in COMPANY_INDICATORS:
            continue
        
        # Expand abbreviations
        expanded_token = ABBREVIATION_MAP.get(token, token)
        processed_tokens.append(expanded_token)
    
    # Step 6: Join with underscores
    if not processed_tokens:
        # If all tokens were filtered out, return empty string (will trigger fallback)
        return ""
    
    normalized = '_'.join(processed_tokens)
    
    # Step 7: Final cleanup
    # Remove any remaining non-alphanumeric characters except underscores
    normalized = re.sub(r'[^a-z0-9_]', '', normalized)
    # Remove multiple consecutive underscores
    normalized = re.sub(r'_+', '_', normalized)
    # Remove leading/trailing underscores
    normalized = normalized.strip('_')
    
    return normalized


def calculate_name_similarity(name1: str, name2: str) -> float:
    """
    Calculate similarity score between two entity names.
    
    Uses multiple similarity measures and normalization to handle
    various name variations and typos.
    
    Args:
        name1: First entity name
        name2: Second entity name
        
    Returns:
        Similarity score between 0.0 and 1.0
    """
    if not name1 or not name2:
        return 0.0
    
    # Exact match after normalization
    norm1 = normalize_entity_name(name1)
    norm2 = normalize_entity_name(name2)
    
    if norm1 == norm2:
        return 1.0
    
    # Use SequenceMatcher for fuzzy matching
    similarity = SequenceMatcher(None, norm1, norm2).ratio()
    
    # Boost similarity for token overlap
    tokens1 = set(norm1.split('_'))
    tokens2 = set(norm2.split('_'))
    
    if tokens1 and tokens2:
        token_overlap = len(tokens1.intersection(tokens2))
        total_tokens = len(tokens1.union(tokens2))
        token_similarity = token_overlap / total_tokens if total_tokens > 0 else 0.0
        
        # Combine sequence and token similarities
        similarity = max(similarity, token_similarity * 0.8)  # Token overlap gets slight penalty
    
    return similarity


def get_name_variants(name: str) -> Set[str]:
    """
    Generate common variants of an entity name for fuzzy matching.
    
    Args:
        name: Original entity name
        
    Returns:
        Set of name variants to check during deduplication
    """
    if not name:
        return set()
    
    variants = {name}  # Include original
    
    # Add normalized version
    normalized = normalize_entity_name(name)
    variants.add(normalized)
    
    # Add basic normalized version
    basic_normalized = _basic_normalize(name)
    variants.add(basic_normalized)
    
    # Add variants with common abbreviations expanded/contracted
    tokens = normalized.split('_')
    
    # Try expanding abbreviations
    expanded_tokens = [ABBREVIATION_MAP.get(token, token) for token in tokens]
    if expanded_tokens != tokens:
        variants.add('_'.join(expanded_tokens))
    
    # Try contracting to abbreviations
    reverse_abbrev_map = {v: k for k, v in ABBREVIATION_MAP.items()}
    contracted_tokens = [reverse_abbrev_map.get(token, token) for token in tokens]
    if contracted_tokens != tokens:
        variants.add('_'.join(contracted_tokens))
    
    # Remove empty variants
    variants = {v for v in variants if v and v.strip()}
    
    return variants


def is_likely_same_entity(name1: str, name2: str, threshold: float = 0.85) -> bool:
    """
    Determine if two names likely represent the same entity.
    
    Uses enhanced similarity calculation with configurable threshold.
    
    Args:
        name1: First entity name
        name2: Second entity name
        threshold: Similarity threshold for considering names the same
        
    Returns:
        True if names likely represent the same entity
    """
    if not name1 or not name2:
        return False
    
    # Allow threshold configuration via environment
    env_threshold = os.getenv('DEDUP_SIMILARITY_THRESHOLD', str(threshold))
    try:
        threshold = float(env_threshold)
    except ValueError:
        pass  # Use default threshold
    
    similarity = calculate_name_similarity(name1, name2)
    return similarity >= threshold


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
    
    # Normalize edge name to prevent UUID collisions from empty/inconsistent names
    normalized_name = name.strip().upper() if name and name.strip() else 'RELATES_TO'
    
    # Create deterministic string combining source, target, and normalized edge name
    edge_key = f"{source_uuid}|{target_uuid}|{normalized_name}"
    
    # Generate deterministic UUID
    edge_uuid = uuid5(group_namespace, edge_key)
    
    return str(edge_uuid)