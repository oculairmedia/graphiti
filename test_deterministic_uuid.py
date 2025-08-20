#!/usr/bin/env python3
"""
Test script for deterministic UUID generation enforcement (GRAPH-371)
"""

import sys
import uuid
import os
from datetime import datetime
from pydantic import ValidationError

sys.path.insert(0, '/opt/stacks/graphiti')

from graphiti_core.nodes import EntityNode, EpisodicNode, EpisodeType
from graphiti_core.edges import EntityEdge
from graphiti_core.utils.datetime_utils import utc_now
from graphiti_core.utils.uuid_utils import generate_deterministic_uuid, generate_deterministic_edge_uuid

def test_deterministic_node_uuid_generation():
    """Test that nodes with same name+group_id get same UUID when deterministic mode enabled"""
    print("Testing deterministic node UUID generation...")
    
    # Set environment variable to enable deterministic UUIDs
    os.environ['USE_DETERMINISTIC_UUIDS'] = 'true'
    
    try:
        # Create two nodes with same name and group_id
        node1 = EntityNode(
            name="Alice",
            group_id="test_group",
            summary="First Alice entity"
        )
        
        node2 = EntityNode(
            name="Alice", 
            group_id="test_group",
            summary="Second Alice entity"
        )
        
        if node1.uuid == node2.uuid:
            print(f"✅ Deterministic UUIDs match: {node1.uuid}")
            return True
        else:
            print(f"❌ UUIDs should match but got: {node1.uuid} vs {node2.uuid}")
            return False
            
    except Exception as e:
        print(f"❌ Failed to create deterministic nodes: {e}")
        return False
    finally:
        # Clean up
        os.environ.pop('USE_DETERMINISTIC_UUIDS', None)

def test_different_names_different_uuids():
    """Test that nodes with different names get different UUIDs"""
    print("Testing different names get different UUIDs...")
    
    # Set environment variable to enable deterministic UUIDs
    os.environ['USE_DETERMINISTIC_UUIDS'] = 'true'
    
    try:
        node1 = EntityNode(
            name="Alice",
            group_id="test_group"
        )
        
        node2 = EntityNode(
            name="Bob",
            group_id="test_group"
        )
        
        if node1.uuid != node2.uuid:
            print(f"✅ Different names get different UUIDs: {node1.name}={node1.uuid[:8]}... vs {node2.name}={node2.uuid[:8]}...")
            return True
        else:
            print(f"❌ Different names should get different UUIDs but both got: {node1.uuid}")
            return False
            
    except Exception as e:
        print(f"❌ Failed to create nodes with different names: {e}")
        return False
    finally:
        # Clean up
        os.environ.pop('USE_DETERMINISTIC_UUIDS', None)

def test_different_groups_different_uuids():
    """Test that same name in different groups gets different UUIDs"""
    print("Testing same name in different groups gets different UUIDs...")
    
    # Set environment variable to enable deterministic UUIDs
    os.environ['USE_DETERMINISTIC_UUIDS'] = 'true'
    
    try:
        node1 = EntityNode(
            name="Alice",
            group_id="group1"
        )
        
        node2 = EntityNode(
            name="Alice",
            group_id="group2"
        )
        
        if node1.uuid != node2.uuid:
            print(f"✅ Same name in different groups get different UUIDs: group1={node1.uuid[:8]}... vs group2={node2.uuid[:8]}...")
            return True
        else:
            print(f"❌ Same name in different groups should get different UUIDs but both got: {node1.uuid}")
            return False
            
    except Exception as e:
        print(f"❌ Failed to create nodes in different groups: {e}")
        return False
    finally:
        # Clean up
        os.environ.pop('USE_DETERMINISTIC_UUIDS', None)

def test_deterministic_edge_uuid_generation():
    """Test that edges with same parameters get same UUID when deterministic mode enabled"""
    print("Testing deterministic edge UUID generation...")
    
    # Set environment variable to enable deterministic UUIDs
    os.environ['USE_DETERMINISTIC_UUIDS'] = 'true'
    
    try:
        # Create consistent source and target UUIDs
        source_uuid = str(uuid.uuid4())
        target_uuid = str(uuid.uuid4())
        
        # Create two edges with same parameters
        edge1 = EntityEdge(
            source_node_uuid=source_uuid,
            target_node_uuid=target_uuid,
            group_id="test_group",
            name="RELATES_TO",
            fact="Alice relates to Bob",
            created_at=utc_now()
        )
        
        edge2 = EntityEdge(
            source_node_uuid=source_uuid,
            target_node_uuid=target_uuid, 
            group_id="test_group",
            name="RELATES_TO",
            fact="Alice relates to Bob differently",
            created_at=utc_now()
        )
        
        if edge1.uuid == edge2.uuid:
            print(f"✅ Deterministic edge UUIDs match: {edge1.uuid}")
            return True
        else:
            print(f"❌ Edge UUIDs should match but got: {edge1.uuid} vs {edge2.uuid}")
            return False
            
    except Exception as e:
        print(f"❌ Failed to create deterministic edges: {e}")
        return False
    finally:
        # Clean up
        os.environ.pop('USE_DETERMINISTIC_UUIDS', None)

def test_random_mode_still_works():
    """Test that random UUID generation still works when deterministic mode is disabled"""
    print("Testing random UUID mode still works...")
    
    # Ensure deterministic mode is disabled
    os.environ.pop('USE_DETERMINISTIC_UUIDS', None)
    
    try:
        # Create two nodes with same name and group_id
        node1 = EntityNode(
            name="Alice",
            group_id="test_group"
        )
        
        node2 = EntityNode(
            name="Alice",
            group_id="test_group"
        )
        
        if node1.uuid != node2.uuid:
            print(f"✅ Random UUIDs are different: {node1.uuid[:8]}... vs {node2.uuid[:8]}...")
            return True
        else:
            print(f"❌ Random UUIDs should be different but both got: {node1.uuid}")
            return False
            
    except Exception as e:
        print(f"❌ Failed to create random nodes: {e}")
        return False

def test_explicit_uuid_override():
    """Test that explicitly provided UUIDs override deterministic generation"""
    print("Testing explicit UUID override...")
    
    # Set environment variable to enable deterministic UUIDs
    os.environ['USE_DETERMINISTIC_UUIDS'] = 'true'
    
    try:
        explicit_uuid = str(uuid.uuid4())
        
        node = EntityNode(
            uuid=explicit_uuid,
            name="Alice",
            group_id="test_group"
        )
        
        if node.uuid == explicit_uuid:
            print(f"✅ Explicit UUID override works: {explicit_uuid}")
            return True
        else:
            print(f"❌ Explicit UUID should be preserved but got: {node.uuid}")
            return False
            
    except Exception as e:
        print(f"❌ Failed to create node with explicit UUID: {e}")
        return False
    finally:
        # Clean up
        os.environ.pop('USE_DETERMINISTIC_UUIDS', None)

def test_name_normalization_consistency():
    """Test that name normalization produces consistent UUIDs for similar names"""
    print("Testing name normalization consistency...")
    
    # Set environment variable to enable deterministic UUIDs and name normalization
    os.environ['USE_DETERMINISTIC_UUIDS'] = 'true'
    os.environ['DEDUP_NORMALIZE_NAMES'] = 'true'
    
    try:
        # Create nodes with variations of the same name
        node1 = EntityNode(
            name="Claude AI",
            group_id="test_group"
        )
        
        node2 = EntityNode(
            name="claude_ai", 
            group_id="test_group"
        )
        
        node3 = EntityNode(
            name="CLAUDE.AI",
            group_id="test_group" 
        )
        
        if node1.uuid == node2.uuid == node3.uuid:
            print(f"✅ Name normalization produces consistent UUIDs: {node1.uuid}")
            return True
        else:
            print(f"❌ Normalized names should get same UUID but got:")
            print(f"   'Claude AI': {node1.uuid}")
            print(f"   'claude_ai': {node2.uuid}")  
            print(f"   'CLAUDE.AI': {node3.uuid}")
            return False
            
    except Exception as e:
        print(f"❌ Failed to create nodes with name variants: {e}")
        return False
    finally:
        # Clean up
        os.environ.pop('USE_DETERMINISTIC_UUIDS', None)
        os.environ.pop('DEDUP_NORMALIZE_NAMES', None)

def main():
    """Run all deterministic UUID tests"""
    print("🧪 Testing Deterministic UUID Generation (GRAPH-371)")
    print("=" * 60)
    
    tests = [
        test_deterministic_node_uuid_generation,
        test_different_names_different_uuids,
        test_different_groups_different_uuids,
        test_deterministic_edge_uuid_generation,
        test_random_mode_still_works,
        test_explicit_uuid_override,
        test_name_normalization_consistency
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
        print("🎉 All deterministic UUID tests passed!")
        return True
    else:
        print("💥 Some tests failed!")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)