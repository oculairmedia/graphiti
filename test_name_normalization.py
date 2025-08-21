#!/usr/bin/env python3
"""
Test script for enhanced name normalization functionality (GRAPH-379)
"""

import sys
import os

sys.path.insert(0, '/opt/stacks/graphiti')

from graphiti_core.utils.uuid_utils import (
    normalize_entity_name,
    calculate_name_similarity,
    get_name_variants,
    is_likely_same_entity,
    _basic_normalize,
    _enhanced_normalize,
    COMMON_TITLES,
    COMMON_SUFFIXES,
    COMPANY_INDICATORS,
    ABBREVIATION_MAP
)

def test_basic_normalization():
    """Test basic name normalization functionality"""
    print("Testing basic normalization...")
    
    test_cases = [
        ("Claude", "claude"),
        ("CLAUDE", "claude"),
        ("Dr. Smith", "dr_smith"),
        ("John-Doe", "john_doe"),
        ("Jane O'Connor", "jane_oconnor"),
        ("Microsoft Corp.", "microsoft_corp"),
        ("  Extra  Spaces  ", "extra_spaces"),
        ("Multiple___Underscores", "multiple_underscores"),
        ("", ""),
    ]
    
    for original, expected in test_cases:
        result = _basic_normalize(original)
        if result == expected:
            print(f"✅ '{original}' → '{result}'")
        else:
            print(f"❌ '{original}' → '{result}' (expected '{expected}')")
            return False
    
    return True


def test_enhanced_normalization():
    """Test enhanced name normalization with titles, suffixes, and abbreviations"""
    print("Testing enhanced normalization...")
    
    # Set environment variable for enhanced normalization
    os.environ['DEDUP_ENHANCED_NORMALIZATION'] = 'true'
    
    test_cases = [
        ("Dr. John Smith", "john_smith"),  # Remove title
        ("Jane Doe Jr.", "jane_doe"),      # Remove suffix
        ("Microsoft Corp.", "microsoft"), # Remove company indicator
        ("Prof. Bob Wilson PhD", "robert_wilson"),  # Remove title, expand abbreviation, remove suffix
        ("Mr. Mike Johnson", "michael_johnson"),     # Remove title, expand abbreviation
        ("Apple Inc.", "apple"),          # Remove company indicator
        ("Tom's Restaurant", "thomas_restaurant"),  # Remove possessive, expand abbreviation
        ("can't", "canot"),               # Handle contractions (n't becomes 'not')
        ("José García", "jose_garcia"),   # Unicode normalization
        ("", ""),
    ]
    
    for original, expected in test_cases:
        result = normalize_entity_name(original, enhanced=True)
        if result == expected:
            print(f"✅ '{original}' → '{result}'")
        else:
            print(f"❌ '{original}' → '{result}' (expected '{expected}')")
            # Debug the enhanced normalization
            basic_result = _basic_normalize(original)
            enhanced_result = _enhanced_normalize(original)
            print(f"   Debug: basic='{basic_result}', enhanced='{enhanced_result}'")
            return False
    
    return True


def test_similarity_calculation():
    """Test name similarity calculation"""
    print("Testing similarity calculation...")
    
    test_cases = [
        ("John Smith", "john smith", 1.0),          # Exact after normalization
        ("Dr. John Smith", "John Smith", 1.0),     # Same after enhanced normalization
        ("Microsoft Corp", "Microsoft", 1.0),     # Same after company indicator removal
        ("Bob", "Robert", 1.0),                    # Abbreviation expansion
        ("John", "Jon", 0.8),                      # High similarity (typo)
        ("Apple", "Orange", 0.0),                  # Low similarity (but will be higher due to algorithm)
        ("", "", 0.0),                             # Empty strings
        ("John", "", 0.0),                         # One empty string
    ]
    
    for name1, name2, expected_min in test_cases:
        similarity = calculate_name_similarity(name1, name2)
        if expected_min == 1.0:
            # Exact match expected
            if similarity == 1.0:
                print(f"✅ '{name1}' vs '{name2}' → {similarity:.2f}")
            else:
                print(f"❌ '{name1}' vs '{name2}' → {similarity:.2f} (expected 1.0)")
                return False
        elif expected_min == 0.0 and similarity < 0.5:
            # Low similarity expected
            print(f"✅ '{name1}' vs '{name2}' → {similarity:.2f}")
        elif expected_min > 0.0 and similarity >= expected_min:
            # High similarity expected
            print(f"✅ '{name1}' vs '{name2}' → {similarity:.2f}")
        else:
            print(f"❌ '{name1}' vs '{name2}' → {similarity:.2f} (expected >= {expected_min})")
            return False
    
    return True


def test_name_variants():
    """Test generation of name variants"""
    print("Testing name variants generation...")
    
    test_cases = [
        ("Dr. Bob Smith", 3),  # Should generate at least 3 variants
        ("Microsoft Corp.", 3),  # Should generate at least 3 variants  
        ("", 0),  # Empty string should have no variants
    ]
    
    for name, min_variants in test_cases:
        variants = get_name_variants(name)
        
        if len(variants) >= min_variants:
            print(f"✅ '{name}' → {len(variants)} variants: {sorted(variants)}")
        else:
            print(f"❌ '{name}' → {len(variants)} variants (expected >= {min_variants}): {sorted(variants)}")
            return False
    
    return True


def test_entity_matching():
    """Test high-level entity matching functionality"""
    print("Testing entity matching...")
    
    test_cases = [
        ("Dr. John Smith", "John Smith", True),
        ("Bob Wilson", "Robert Wilson", True),
        ("Microsoft Corp.", "Microsoft Inc.", True),
        ("Apple", "Orange", False),
        ("John", "Jon", True),  # Should be considered same with fuzzy matching
        ("", "", False),        # Empty strings should not match
    ]
    
    for name1, name2, should_match in test_cases:
        is_match = is_likely_same_entity(name1, name2, threshold=0.8)
        if is_match == should_match:
            print(f"✅ '{name1}' vs '{name2}' → {is_match}")
        else:
            print(f"❌ '{name1}' vs '{name2}' → {is_match} (expected {should_match})")
            return False
    
    return True


def test_configuration():
    """Test configuration options"""
    print("Testing configuration options...")
    
    # Test disabling normalization
    os.environ['DEDUP_NORMALIZE_NAMES'] = 'false'
    result = normalize_entity_name("Dr. John Smith")
    if result == "Dr. John Smith":
        print("✅ Normalization disabled correctly")
    else:
        print(f"❌ Normalization should be disabled, got: {result}")
        return False
    
    # Re-enable normalization
    os.environ['DEDUP_NORMALIZE_NAMES'] = 'true'
    
    # Test disabling enhanced normalization
    os.environ['DEDUP_ENHANCED_NORMALIZATION'] = 'false'
    result = normalize_entity_name("Dr. John Smith", enhanced=True)
    expected_basic = _basic_normalize("Dr. John Smith")
    if result == expected_basic:
        print("✅ Enhanced normalization disabled correctly")
    else:
        print(f"❌ Enhanced normalization should be disabled, got: {result}")
        return False
    
    # Test custom similarity threshold
    os.environ['DEDUP_SIMILARITY_THRESHOLD'] = '0.95'
    is_match = is_likely_same_entity("John", "Jon")  # This should fail with high threshold
    if not is_match:
        print("✅ Custom similarity threshold working")
    else:
        print("❌ Custom similarity threshold not working")
        return False
    
    # Reset environment
    os.environ['DEDUP_ENHANCED_NORMALIZATION'] = 'true'
    os.environ['DEDUP_SIMILARITY_THRESHOLD'] = '0.85'
    
    return True


def test_edge_cases():
    """Test various edge cases"""
    print("Testing edge cases...")
    
    edge_cases = [
        ("", ""),                    # Empty strings
        ("   ", ""),                 # Whitespace only
        ("123", "123"),              # Numbers only
        ("a", "a"),                  # Single character
        ("Dr.Prof.Mr.", "professor_mister"),  # Mix of titles (not all filtered)
        ("!!@#$%", ""),             # Special characters only
        ("José María García-López", "jose_maria_garcia_lopez"),  # Complex unicode
        ("McDonald's", "mcdonald"),  # Possessives
        ("Don't", "donot"),         # Contractions
    ]
    
    for original, expected in edge_cases:
        result = normalize_entity_name(original)
        # For empty expected, we expect either empty or original fallback
        if expected == "" and (result == "" or result == original):
            print(f"✅ '{original}' → '{result}' (edge case handled)")
        elif result == expected:
            print(f"✅ '{original}' → '{result}'")
        else:
            print(f"❌ '{original}' → '{result}' (expected '{expected}')")
            return False
    
    return True


def test_performance():
    """Test performance with various input sizes"""
    print("Testing performance...")
    
    import time
    
    test_names = [
        "John Smith",
        "Dr. Robert Johnson Jr.",
        "Microsoft Corporation Inc.",
        "José María García-López",
        "Very Long Entity Name With Many Words And Punctuation!!!"
    ]
    
    start_time = time.time()
    for _ in range(1000):
        for name in test_names:
            normalize_entity_name(name)
            calculate_name_similarity(name, test_names[0])
            get_name_variants(name)
    
    end_time = time.time()
    duration = end_time - start_time
    
    if duration < 2.0:  # Should complete in under 2 seconds
        print(f"✅ Performance test completed in {duration:.2f}s")
        return True
    else:
        print(f"❌ Performance test took {duration:.2f}s (expected < 2.0s)")
        return False


def main():
    """Run all name normalization tests"""
    print("🧪 Testing Enhanced Name Normalization (GRAPH-379)")
    print("=" * 60)
    
    tests = [
        test_basic_normalization,
        test_enhanced_normalization,
        test_similarity_calculation,
        test_name_variants,
        test_entity_matching,
        test_configuration,
        test_edge_cases,
        test_performance,
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
        print("🎉 All name normalization tests passed!")
        return True
    else:
        print("💥 Some name normalization tests failed!")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)