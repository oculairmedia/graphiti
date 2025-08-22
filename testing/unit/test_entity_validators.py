#!/usr/bin/env python3
"""
Test script for EntityNode validators (GRAPH-370)
"""

import sys
import uuid
from datetime import datetime
from pydantic import ValidationError

sys.path.insert(0, '/opt/stacks/graphiti')

from graphiti_core.nodes import EntityNode
from graphiti_core.utils.datetime_utils import utc_now

def test_valid_entity_node():
    """Test creating a valid EntityNode"""
    print("Testing valid EntityNode creation...")
    try:
        node = EntityNode(
            uuid=str(uuid.uuid4()),
            name="Test Entity",
            group_id="test_group",
            summary="A test entity for validation",
            attributes={
                "pagerank_centrality": 0.5,
                "eigenvector_centrality": 0.3,
                "importance_score": 0.8
            }
        )
        print(f"✅ Valid EntityNode created: {node.uuid}")
        return True
    except Exception as e:
        print(f"❌ Failed to create valid EntityNode: {e}")
        return False

def test_invalid_uuid():
    """Test invalid UUID validation"""
    print("Testing invalid UUID validation...")
    try:
        node = EntityNode(
            uuid="invalid-uuid-format",
            name="Test Entity",
            group_id="test_group"
        )
        print("❌ Should have failed with invalid UUID")
        return False
    except ValidationError as e:
        print(f"✅ UUID validation working: {e}")
        return True

def test_empty_name():
    """Test empty name validation"""
    print("Testing empty name validation...")
    try:
        node = EntityNode(
            uuid=str(uuid.uuid4()),
            name="",
            group_id="test_group"
        )
        print("❌ Should have failed with empty name")
        return False
    except ValidationError as e:
        print(f"✅ Name validation working: {e}")
        return True

def test_invalid_group_id():
    """Test invalid group ID validation"""
    print("Testing invalid group ID validation...")
    try:
        node = EntityNode(
            uuid=str(uuid.uuid4()),
            name="Test Entity",
            group_id="invalid@group#id!"
        )
        print("❌ Should have failed with invalid group ID")
        return False
    except ValidationError as e:
        print(f"✅ Group ID validation working: {e}")
        return True

def test_invalid_centrality_scores():
    """Test centrality score validation"""
    print("Testing centrality score validation...")
    try:
        node = EntityNode(
            uuid=str(uuid.uuid4()),
            name="Test Entity",
            group_id="test_group",
            attributes={
                "pagerank_centrality": 1.5,  # Invalid: > 1.0
                "eigenvector_centrality": -0.1  # Invalid: < 0.0
            }
        )
        print("❌ Should have failed with invalid centrality scores")
        return False
    except ValidationError as e:
        print(f"✅ Centrality validation working: {e}")
        return True

def test_invalid_embedding():
    """Test name embedding validation"""
    print("Testing name embedding validation...")
    try:
        node = EntityNode(
            uuid=str(uuid.uuid4()),
            name="Test Entity",
            group_id="test_group",
            name_embedding=["not", "a", "number"]
        )
        print("❌ Should have failed with invalid embedding")
        return False
    except ValidationError as e:
        print(f"✅ Embedding validation working: {e}")
        return True

def test_long_summary():
    """Test summary length validation"""
    print("Testing summary length validation...")
    try:
        long_summary = "x" * 10001  # Exceed 10000 character limit
        node = EntityNode(
            uuid=str(uuid.uuid4()),
            name="Test Entity",
            group_id="test_group",
            summary=long_summary
        )
        print("❌ Should have failed with long summary")
        return False
    except ValidationError as e:
        print(f"✅ Summary validation working: {e}")
        return True

def main():
    """Run all validation tests"""
    print("🧪 Testing EntityNode validators (GRAPH-370)")
    print("=" * 50)
    
    tests = [
        test_valid_entity_node,
        test_invalid_uuid,
        test_empty_name,
        test_invalid_group_id,
        test_invalid_centrality_scores,
        test_invalid_embedding,
        test_long_summary
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
        print()
    
    print("=" * 50)
    print(f"Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All EntityNode validator tests passed!")
        return True
    else:
        print("💥 Some tests failed!")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)