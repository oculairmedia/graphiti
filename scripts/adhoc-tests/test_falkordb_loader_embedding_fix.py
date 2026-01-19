#!/usr/bin/env python3
"""
Test to verify FalkorDBLoader embedding preservation fix.
This demonstrates that the loader now properly handles embeddings with vecf32() wrapping.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sync_service.loaders.falkordb_loader import FalkorDBLoader


def test_embedding_detection():
    """Test that embedding properties are detected correctly."""
    
    loader = FalkorDBLoader()
    
    # Test embedding property detection
    embedding_props = [
        'name_embedding', 'summary_embedding', 'fact_embedding',
        'content_embedding', 'embedding', 'embeddings',
        'NAME_EMBEDDING', 'Fact_Embedding'  # Test case insensitivity
    ]
    
    non_embedding_props = [
        'name', 'uuid', 'created_at', 'episodes', 'fact', 'summary'
    ]
    
    print("🧪 Testing Embedding Property Detection")
    print("=" * 50)
    
    for prop in embedding_props:
        is_embedding = loader._is_embedding_property(prop)
        status = "✅" if is_embedding else "❌"
        print(f"   {status} {prop}: {is_embedding}")
        assert is_embedding, f"Should detect {prop} as embedding"
    
    for prop in non_embedding_props:
        is_embedding = loader._is_embedding_property(prop)
        status = "✅" if not is_embedding else "❌"
        print(f"   {status} {prop}: {is_embedding}")
        assert not is_embedding, f"Should NOT detect {prop} as embedding"
    
    print(f"\n✅ All embedding detection tests passed!")


def test_vector_value_formatting():
    """Test that vector values are formatted correctly with vecf32()."""
    
    loader = FalkorDBLoader()
    
    print("\n🧪 Testing Vector Value Formatting")
    print("=" * 50)
    
    # Test embedding property with vector value
    test_embedding = [0.1, 0.2, -0.3, 1.5, -2.1]
    
    # Test with embedding property name
    result = loader._safe_value_for_query(test_embedding, 'fact_embedding')
    expected = 'vecf32([0.1, 0.2, -0.3, 1.5, -2.1])'
    print(f"   Input:    {test_embedding}")
    print(f"   Property: 'fact_embedding'")
    print(f"   Output:   {result}")
    print(f"   Expected: {expected}")
    assert result == expected, f"Expected {expected}, got {result}"
    
    # Test with non-embedding property name
    result = loader._safe_value_for_query(test_embedding, 'episodes')
    expected = '[0.1, 0.2, -0.3, 1.5, -2.1]'
    print(f"\n   Input:    {test_embedding}")
    print(f"   Property: 'episodes'")
    print(f"   Output:   {result}")
    print(f"   Expected: {expected}")
    assert result == expected, f"Expected {expected}, got {result}"
    
    # Test with no property name (default to non-embedding)
    result = loader._safe_value_for_query(test_embedding)
    expected = '[0.1, 0.2, -0.3, 1.5, -2.1]'
    print(f"\n   Input:    {test_embedding}")
    print(f"   Property: (none)")
    print(f"   Output:   {result}")
    print(f"   Expected: {expected}")
    assert result == expected, f"Expected {expected}, got {result}"
    
    print(f"\n✅ All vector formatting tests passed!")


def test_string_array_formatting():
    """Test that string arrays in embeddings are properly escaped."""
    
    loader = FalkorDBLoader()
    
    print("\n🧪 Testing String Array Formatting") 
    print("=" * 50)
    
    # Test string array with embedding property
    test_strings = ['word1', 'word "with" quotes', 'word\\with\\backslashes']
    
    result = loader._safe_value_for_query(test_strings, 'content_embedding')
    expected = 'vecf32(["word1", "word \\"with\\" quotes", "word\\\\with\\\\backslashes"])'
    print(f"   Input:    {test_strings}")
    print(f"   Property: 'content_embedding'") 
    print(f"   Output:   {result}")
    print(f"   Expected: {expected}")
    assert result == expected, f"Expected {expected}, got {result}"
    
    print(f"\n✅ String array formatting test passed!")


def test_non_vector_values():
    """Test that non-vector values are handled correctly."""
    
    loader = FalkorDBLoader()
    
    print("\n🧪 Testing Non-Vector Value Formatting")
    print("=" * 50)
    
    test_cases = [
        (None, 'fact_embedding', 'NULL'),
        ('text value', 'fact_embedding', '"text value"'),
        (42, 'fact_embedding', '42'),
        (3.14, 'fact_embedding', '3.14'),
        (True, 'fact_embedding', 'true'),
        (False, 'fact_embedding', 'false'),
    ]
    
    for value, prop, expected in test_cases:
        result = loader._safe_value_for_query(value, prop)
        status = "✅" if result == expected else "❌"
        print(f"   {status} {repr(value)} ({prop}): {result}")
        assert result == expected, f"Expected {expected}, got {result}"
    
    print(f"\n✅ All non-vector value tests passed!")


def main():
    """Run all embedding preservation tests."""
    
    print("🔧 FalkorDBLoader Embedding Preservation Tests")
    print("Testing the fix for Neo4j → FalkorDB sync embedding preservation")
    print("=" * 80)
    
    try:
        test_embedding_detection()
        test_vector_value_formatting()
        test_string_array_formatting()
        test_non_vector_values()
        
        print("\n" + "=" * 80)
        print("🎉 ALL TESTS PASSED!")
        print("✅ FalkorDBLoader embedding fix is working correctly")
        print("✅ Neo4j → FalkorDB sync will now preserve embeddings")
        print("✅ fact_embedding properties will be properly wrapped with vecf32()")
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()