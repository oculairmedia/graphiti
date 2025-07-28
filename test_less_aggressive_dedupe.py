#!/usr/bin/env python3
"""
Test script to verify less aggressive deduplication behavior
"""

import asyncio
import sys
sys.path.append('/opt/stacks/graphiti')

from maintenance_dedupe_entities import EntityDeduplicator
from graphiti_core.nodes import EntityNode
from datetime import datetime

# Create mock entities for testing
def create_test_entities():
    """Create test entities to verify deduplication behavior"""
    return [
        # Test case 1: Exact duplicates (should merge)
        EntityNode(name="Claude", group_id="test", labels=["Entity"], summary="AI assistant"),
        EntityNode(name="claude", group_id="test", labels=["Entity"], summary="AI assistant"),
        EntityNode(name="CLAUDE", group_id="test", labels=["Entity"], summary="AI assistant"),
        
        # Test case 2: Compound names (should NOT merge)
        EntityNode(name="Claude Code", group_id="test", labels=["Entity"], summary="CLI tool"),
        EntityNode(name="claude_code", group_id="test", labels=["Entity"], summary="CLI tool"),
        
        # Test case 3: Similar but distinct (should NOT merge)
        EntityNode(name="GitHub", group_id="test", labels=["Entity"], summary="Version control"),
        EntityNode(name="GitHub Actions", group_id="test", labels=["Entity"], summary="CI/CD service"),
        
        # Test case 4: Variations with suffixes (should merge after normalization)
        EntityNode(name="User (system)", group_id="test", labels=["Entity"], summary="System user"),
        EntityNode(name="User", group_id="test", labels=["Entity"], summary="System user"),
        EntityNode(name="user", group_id="test", labels=["Entity"], summary="System user"),
    ]

async def test_deduplication():
    """Test the deduplication logic"""
    # Create a mock deduplicator
    class MockGraphiti:
        driver = None
        llm_client = None
        embedder = None
    
    graphiti = MockGraphiti()
    deduplicator = EntityDeduplicator(graphiti)
    
    entities = create_test_entities()
    
    print("Testing name similarity...")
    print("-" * 50)
    
    # Test pairs
    test_pairs = [
        ("Claude", "claude", True, "Case variations should match"),
        ("Claude", "Claude Code", False, "Compound names should NOT match"),
        ("GitHub", "GitHub Actions", False, "Extended names should NOT match"),
        ("User (system)", "User", True, "Suffixes should be removed and match"),
        ("claude_code", "Claude Code", True, "Underscore variations should match"),
    ]
    
    for name1, name2, expected, reason in test_pairs:
        result = deduplicator._are_names_similar(name1, name2, 0.95)
        status = "✓" if result == expected else "✗"
        print(f"{status} '{name1}' vs '{name2}': {result} (expected {expected}) - {reason}")
    
    print("\nTesting compound name detection...")
    print("-" * 50)
    
    compound_tests = [
        ("Claude", "Claude Code", True, "Should detect as compound"),
        ("GitHub", "GitHub Actions", True, "Should detect as compound"),
        ("User", "User (system)", False, "Suffix is not a compound"),
        ("Claude", "claude", False, "Case variation is not a compound"),
    ]
    
    for name1, name2, expected, reason in compound_tests:
        result = deduplicator._is_compound_name(name1, name2)
        status = "✓" if result == expected else "✗"
        print(f"{status} '{name1}' vs '{name2}': {result} (expected {expected}) - {reason}")
    
    print("\nTesting auto-merge logic...")
    print("-" * 50)
    
    # Test small group with exact matches
    exact_group = [
        EntityNode(name="Claude", group_id="test", labels=["Entity"], summary=""),
        EntityNode(name="claude", group_id="test", labels=["Entity"], summary=""),
        EntityNode(name="CLAUDE", group_id="test", labels=["Entity"], summary=""),
    ]
    
    should_merge = deduplicator._should_auto_merge(exact_group)
    print(f"Exact duplicates group: {should_merge} (expected True)")
    
    # Test group with compound name
    compound_group = [
        EntityNode(name="Claude", group_id="test", labels=["Entity"], summary=""),
        EntityNode(name="Claude Code", group_id="test", labels=["Entity"], summary=""),
    ]
    
    should_merge = deduplicator._should_auto_merge(compound_group)
    print(f"Compound name group: {should_merge} (expected False)")

if __name__ == "__main__":
    asyncio.run(test_deduplication())