#!/usr/bin/env python3
"""
Test script for EpisodicNode and EntityEdge validators (GRAPH-372)
"""

import sys
import uuid
from datetime import datetime
from pydantic import ValidationError

sys.path.insert(0, '/opt/stacks/graphiti')

from graphiti_core.nodes import EpisodicNode, EpisodeType
from graphiti_core.edges import EntityEdge
from graphiti_core.utils.datetime_utils import utc_now

def test_valid_episodic_node():
    """Test creating a valid EpisodicNode"""
    print("Testing valid EpisodicNode creation...")
    try:
        node = EpisodicNode(
            uuid=str(uuid.uuid4()),
            name="Test Episode",
            group_id="test_group",
            source=EpisodeType.text,
            source_description="Test source",
            content="This is test episode content",
            valid_at=utc_now(),
            entity_edges=[str(uuid.uuid4()), str(uuid.uuid4())]
        )
        print(f"✅ Valid EpisodicNode created: {node.uuid}")
        return True
    except Exception as e:
        print(f"❌ Failed to create valid EpisodicNode: {e}")
        return False

def test_empty_source_description():
    """Test empty source description validation"""
    print("Testing empty source description validation...")
    try:
        node = EpisodicNode(
            uuid=str(uuid.uuid4()),
            name="Test Episode",
            group_id="test_group",
            source=EpisodeType.text,
            source_description="",
            content="This is test content",
            valid_at=utc_now()
        )
        print("❌ Should have failed with empty source description")
        return False
    except ValidationError as e:
        print(f"✅ Source description validation working: {e}")
        return True

def test_empty_content():
    """Test empty content validation"""
    print("Testing empty content validation...")
    try:
        node = EpisodicNode(
            uuid=str(uuid.uuid4()),
            name="Test Episode",
            group_id="test_group",
            source=EpisodeType.text,
            source_description="Test source",
            content="",
            valid_at=utc_now()
        )
        print("❌ Should have failed with empty content")
        return False
    except ValidationError as e:
        print(f"✅ Content validation working: {e}")
        return True

def test_long_content():
    """Test content length validation"""
    print("Testing content length validation...")
    try:
        long_content = "x" * 100001  # Exceed 100000 character limit
        node = EpisodicNode(
            uuid=str(uuid.uuid4()),
            name="Test Episode",
            group_id="test_group",
            source=EpisodeType.text,
            source_description="Test source",
            content=long_content,
            valid_at=utc_now()
        )
        print("❌ Should have failed with long content")
        return False
    except ValidationError as e:
        print(f"✅ Content length validation working: {e}")
        return True

def test_invalid_entity_edges():
    """Test invalid entity edge UUIDs validation"""
    print("Testing invalid entity edge UUIDs validation...")
    try:
        node = EpisodicNode(
            uuid=str(uuid.uuid4()),
            name="Test Episode",
            group_id="test_group",
            source=EpisodeType.text,
            source_description="Test source",
            content="Test content",
            valid_at=utc_now(),
            entity_edges=["invalid-uuid", "another-invalid"]
        )
        print("❌ Should have failed with invalid entity edge UUIDs")
        return False
    except ValidationError as e:
        print(f"✅ Entity edges validation working: {e}")
        return True

def test_valid_entity_edge():
    """Test creating a valid EntityEdge"""
    print("Testing valid EntityEdge creation...")
    try:
        edge = EntityEdge(
            uuid=str(uuid.uuid4()),
            group_id="test_group",
            source_node_uuid=str(uuid.uuid4()),
            target_node_uuid=str(uuid.uuid4()),
            created_at=utc_now(),
            name="RELATED_TO",
            fact="Alice is related to Bob",
            fact_embedding=[0.1, 0.2, 0.3, 0.4, 0.5],
            episodes=[str(uuid.uuid4())],
            valid_at=utc_now()
        )
        print(f"✅ Valid EntityEdge created: {edge.uuid}")
        return True
    except Exception as e:
        print(f"❌ Failed to create valid EntityEdge: {e}")
        return False

def test_empty_edge_name():
    """Test empty edge name validation"""
    print("Testing empty edge name validation...")
    try:
        edge = EntityEdge(
            uuid=str(uuid.uuid4()),
            group_id="test_group",
            source_node_uuid=str(uuid.uuid4()),
            target_node_uuid=str(uuid.uuid4()),
            created_at=utc_now(),
            name="",
            fact="Test fact"
        )
        print("❌ Should have failed with empty edge name")
        return False
    except ValidationError as e:
        print(f"✅ Edge name validation working: {e}")
        return True

def test_empty_fact():
    """Test empty fact validation"""
    print("Testing empty fact validation...")
    try:
        edge = EntityEdge(
            uuid=str(uuid.uuid4()),
            group_id="test_group",
            source_node_uuid=str(uuid.uuid4()),
            target_node_uuid=str(uuid.uuid4()),
            created_at=utc_now(),
            name="RELATED_TO",
            fact=""
        )
        print("❌ Should have failed with empty fact")
        return False
    except ValidationError as e:
        print(f"✅ Fact validation working: {e}")
        return True

def test_invalid_fact_embedding():
    """Test invalid fact embedding validation"""
    print("Testing invalid fact embedding validation...")
    try:
        edge = EntityEdge(
            uuid=str(uuid.uuid4()),
            group_id="test_group",
            source_node_uuid=str(uuid.uuid4()),
            target_node_uuid=str(uuid.uuid4()),
            created_at=utc_now(),
            name="RELATED_TO",
            fact="Test fact",
            fact_embedding=["not", "numeric", "values"]
        )
        print("❌ Should have failed with invalid fact embedding")
        return False
    except ValidationError as e:
        print(f"✅ Fact embedding validation working: {e}")
        return True

def test_invalid_episode_uuids():
    """Test invalid episode UUIDs validation"""
    print("Testing invalid episode UUIDs validation...")
    try:
        edge = EntityEdge(
            uuid=str(uuid.uuid4()),
            group_id="test_group",
            source_node_uuid=str(uuid.uuid4()),
            target_node_uuid=str(uuid.uuid4()),
            created_at=utc_now(),
            name="RELATED_TO",
            fact="Test fact",
            episodes=["invalid-uuid", "another-invalid"]
        )
        print("❌ Should have failed with invalid episode UUIDs")
        return False
    except ValidationError as e:
        print(f"✅ Episode UUIDs validation working: {e}")
        return True

def test_invalid_source_node_uuid():
    """Test invalid source node UUID validation"""
    print("Testing invalid source node UUID validation...")
    try:
        edge = EntityEdge(
            uuid=str(uuid.uuid4()),
            group_id="test_group",
            source_node_uuid="invalid-source-uuid",
            target_node_uuid=str(uuid.uuid4()),
            created_at=utc_now(),
            name="RELATED_TO",
            fact="Test fact"
        )
        print("❌ Should have failed with invalid source node UUID")
        return False
    except ValidationError as e:
        print(f"✅ Source node UUID validation working: {e}")
        return True

def main():
    """Run all validation tests"""
    print("🧪 Testing EpisodicNode and EntityEdge validators (GRAPH-372)")
    print("=" * 60)
    
    tests = [
        test_valid_episodic_node,
        test_empty_source_description,
        test_empty_content,
        test_long_content,
        test_invalid_entity_edges,
        test_valid_entity_edge,
        test_empty_edge_name,
        test_empty_fact,
        test_invalid_fact_embedding,
        test_invalid_episode_uuids,
        test_invalid_source_node_uuid
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
        print()
    
    print("=" * 60)
    print(f"Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All EpisodicNode and EntityEdge validator tests passed!")
        return True
    else:
        print("💥 Some tests failed!")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)