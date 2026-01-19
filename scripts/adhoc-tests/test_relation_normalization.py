#!/usr/bin/env python3
"""
Test script for relation type normalization.
Verifies that all Unicode/punctuation/whitespace variations are properly canonicalized.
"""

import sys
sys.path.insert(0, '.')

from graphiti_core.utils.maintenance.edge_operations import normalize_relation_type


def test_normalization():
    """Test cases from the hardening plan."""
    test_cases = [
        # (input, expected_output, description)
        ("WORKS_WITH", "WORKS_WITH", "Already normalized"),
        ("Works With", "WORKS_WITH", "Case and space variation"),
        ("works-with", "WORKS_WITH", "Dash separator"),
        ("works/with", "WORKS_WITH", "Slash separator"),
        ("works.with", "WORKS_WITH", "Dot separator"),
        ("works:with", "WORKS_WITH", "Colon separator"),
        ("works\twith", "WORKS_WITH", "Tab whitespace"),
        ("works\u00a0with", "WORKS_WITH", "Non-breaking space"),
        ("WÖRKS WITH", "WORKS_WITH", "Diacritics (umlaut)"),
        ("  works__with  ", "WORKS_WITH", "Leading/trailing space + multiple underscores"),
        ("works—with", "WORKS_WITH", "Em-dash"),
        ("works–with", "WORKS_WITH", "En-dash"),
        ("café-owner", "CAFE_OWNER", "Accented character"),
        ("Works   With", "WORKS_WITH", "Multiple spaces"),
        ("works_with", "WORKS_WITH", "Already has underscores"),
        ("", "", "Empty string"),
        ("   ", "", "Whitespace only"),
    ]

    print("=" * 80)
    print("Relation Type Normalization Test Suite")
    print("=" * 80)
    print()

    passed = 0
    failed = 0

    for input_str, expected, description in test_cases:
        result = normalize_relation_type(input_str)
        status = "✅ PASS" if result == expected else "❌ FAIL"

        if result == expected:
            passed += 1
        else:
            failed += 1

        print(f"{status} | {description}")
        print(f"  Input:    {repr(input_str)}")
        print(f"  Expected: {repr(expected)}")
        print(f"  Got:      {repr(result)}")
        print()

    print("=" * 80)
    print(f"Results: {passed} passed, {failed} failed out of {len(test_cases)} tests")
    print("=" * 80)

    return failed == 0


if __name__ == '__main__':
    success = test_normalization()
    sys.exit(0 if success else 1)
