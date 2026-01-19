#!/usr/bin/env python3
"""
Test worker fixes in isolation before applying to production.
Run this script to verify each fix works correctly.
"""

import sys
import json
from typing import Any
from pydantic import BaseModel, Field


# Mock the ExtractedEntity class structure
class ExtractedEntity(BaseModel):
    """Mock of the real ExtractedEntity for testing"""
    name: str
    entity_type_id: int = 0
    summary: str = ""


def test_entity_extraction_robustness():
    """
    Test Fix #1: Entity extraction should handle dict, object, and garbage payloads
    """
    print("\n" + "="*60)
    print("TEST 1: Entity Extraction Robustness")
    print("="*60)

    # Simulate different response formats from LLM
    test_cases = [
        {
            "name": "Valid dict payload",
            "llm_response": {
                "extracted_entities": [
                    {"name": "Alice", "entity_type_id": 0, "summary": "A person"},
                    {"name": "Bob", "entity_type_id": 0, "summary": "Another person"}
                ]
            },
            "expected_count": 2
        },
        {
            "name": "Already constructed objects",
            "llm_response": {
                "extracted_entities": [
                    ExtractedEntity(name="Charlie", entity_type_id=0),
                    ExtractedEntity(name="Diana", entity_type_id=0)
                ]
            },
            "expected_count": 2
        },
        {
            "name": "Mixed dict and object",
            "llm_response": {
                "extracted_entities": [
                    {"name": "Eve", "entity_type_id": 0},
                    ExtractedEntity(name="Frank", entity_type_id=0)
                ]
            },
            "expected_count": 2
        },
        {
            "name": "Garbage string payload",
            "llm_response": {
                "extracted_entities": ["invalid", "data"]
            },
            "expected_count": 0
        },
        {
            "name": "Single character garbage",
            "llm_response": {
                "extracted_entities": ["a"]
            },
            "expected_count": 0
        },
        {
            "name": "Empty list",
            "llm_response": {
                "extracted_entities": []
            },
            "expected_count": 0
        },
        {
            "name": "Missing extracted_entities key",
            "llm_response": {},
            "expected_count": 0
        }
    ]

    # ORIGINAL (BROKEN) CODE
    def original_extraction(llm_response: dict) -> list[ExtractedEntity]:
        """This is the current broken code"""
        try:
            extracted_entities: list[ExtractedEntity] = [
                ExtractedEntity(**entity_data)
                for entity_data in llm_response.get('extracted_entities', [])
            ]
            return extracted_entities
        except Exception as e:
            raise e

    # FIXED CODE
    def fixed_extraction(llm_response: dict) -> list[ExtractedEntity]:
        """This is the hardened version"""
        extracted_entities: list[ExtractedEntity] = []
        entities_data = llm_response.get('extracted_entities', [])

        dropped_payloads = 0

        for entity_data in entities_data:
            try:
                if isinstance(entity_data, ExtractedEntity):
                    # Already constructed - use directly
                    extracted_entities.append(entity_data)
                elif isinstance(entity_data, dict):
                    # Raw dict - construct from dict
                    extracted_entities.append(ExtractedEntity(**entity_data))
                else:
                    # Garbage - log and skip
                    print(f"  ⚠️  Dropped invalid payload: type={type(entity_data)}, value={entity_data}")
                    dropped_payloads += 1
            except Exception as e:
                print(f"  ⚠️  Failed to construct entity from {entity_data}: {e}")
                dropped_payloads += 1

        if dropped_payloads > 0:
            print(f"  📊 Dropped {dropped_payloads} invalid payloads")

        return extracted_entities

    # Run tests
    passed = 0
    failed = 0

    for test_case in test_cases:
        print(f"\n  Test: {test_case['name']}")

        # Test original (should fail on some)
        print("    Original code: ", end="")
        try:
            result_original = original_extraction(test_case['llm_response'])
            if len(result_original) == test_case['expected_count']:
                print(f"✓ (got {len(result_original)} entities)")
            else:
                print(f"✗ Expected {test_case['expected_count']}, got {len(result_original)}")
        except Exception as e:
            print(f"💥 CRASHED: {type(e).__name__}: {e}")

        # Test fixed (should always work)
        print("    Fixed code:    ", end="")
        try:
            result_fixed = fixed_extraction(test_case['llm_response'])
            if len(result_fixed) == test_case['expected_count']:
                print(f"✓ (got {len(result_fixed)} entities)")
                passed += 1
            else:
                print(f"✗ Expected {test_case['expected_count']}, got {len(result_fixed)}")
                failed += 1
        except Exception as e:
            print(f"💥 CRASHED: {type(e).__name__}: {e}")
            failed += 1

    print(f"\n  Summary: {passed}/{len(test_cases)} tests passed")
    return failed == 0


def test_embedding_type_conversion():
    """
    Test Fix #4: Embedding conversion for FalkorDB
    """
    print("\n" + "="*60)
    print("TEST 2: Embedding Type Conversion")
    print("="*60)

    test_cases = [
        {
            "name": "Python list embedding",
            "input": {"fact_embedding": [0.1, 0.2, 0.3]},
            "should_convert": True
        },
        {
            "name": "None embedding",
            "input": {"fact_embedding": None},
            "should_drop": True
        },
        {
            "name": "Empty list embedding",
            "input": {"fact_embedding": []},
            "should_drop": True
        },
        {
            "name": "Already VectorF32 (mock)",
            "input": {"fact_embedding": "VectorF32([0.1, 0.2])"}, # Mock string representation
            "should_preserve": True
        },
        {
            "name": "Mixed properties",
            "input": {
                "fact": "Some fact",
                "fact_embedding": [0.5, 0.6, 0.7],
                "created_at": "2024-01-01",
                "episodes": ["ep1", "ep2"]
            },
            "should_convert": True
        }
    ]

    def normalize_embeddings_for_falkor(props: dict) -> dict:
        """
        Fixed version: Normalize embeddings for FalkorDB compatibility
        """
        result = dict(props)

        # Handle fact_embedding
        if 'fact_embedding' in result:
            embedding = result['fact_embedding']

            if embedding is None or (isinstance(embedding, list) and len(embedding) == 0):
                # Drop null/empty embeddings
                del result['fact_embedding']
                print(f"    Dropped null/empty embedding")
            elif isinstance(embedding, list):
                # Convert Python list to FalkorDB VectorF32
                # In real code, this would call FalkorDB's vector constructor
                result['fact_embedding'] = f"VectorF32({embedding})"
                print(f"    Converted list to VectorF32: {len(embedding)} dims")
            else:
                # Already in correct format or unknown - preserve
                print(f"    Preserved embedding as-is: {type(embedding)}")

        # Handle name_embedding similarly
        if 'name_embedding' in result:
            embedding = result['name_embedding']

            if embedding is None or (isinstance(embedding, list) and len(embedding) == 0):
                del result['name_embedding']
            elif isinstance(embedding, list):
                result['name_embedding'] = f"VectorF32({embedding})"

        return result

    passed = 0
    failed = 0

    for test_case in test_cases:
        print(f"\n  Test: {test_case['name']}")
        print(f"    Input: {test_case['input']}")

        try:
            result = normalize_embeddings_for_falkor(test_case['input'])
            print(f"    Output: {result}")

            # Verify expectations
            if test_case.get('should_drop'):
                if 'fact_embedding' not in result:
                    print("    ✓ Embedding correctly dropped")
                    passed += 1
                else:
                    print("    ✗ Embedding should have been dropped")
                    failed += 1
            elif test_case.get('should_convert'):
                if 'fact_embedding' in result and 'VectorF32' in str(result['fact_embedding']):
                    print("    ✓ Embedding correctly converted")
                    passed += 1
                else:
                    print("    ✗ Embedding should have been converted")
                    failed += 1
            elif test_case.get('should_preserve'):
                if 'fact_embedding' in result:
                    print("    ✓ Embedding preserved")
                    passed += 1
                else:
                    print("    ✗ Embedding should have been preserved")
                    failed += 1
            else:
                passed += 1

        except Exception as e:
            print(f"    💥 CRASHED: {type(e).__name__}: {e}")
            failed += 1

    print(f"\n  Summary: {passed}/{len(test_cases)} tests passed")
    return failed == 0


def test_merge_feature_flag():
    """
    Test Fix #2: Feature flag for auto-merge
    """
    print("\n" + "="*60)
    print("TEST 3: Auto-Merge Feature Flag")
    print("="*60)

    import os

    def should_execute_merge() -> bool:
        """Check if auto-merge is enabled"""
        return os.getenv('GRAPHITI_ENABLE_AUTO_MERGE', 'false').lower() == 'true'

    # Test with flag disabled (default)
    os.environ.pop('GRAPHITI_ENABLE_AUTO_MERGE', None)
    result_disabled = should_execute_merge()
    print(f"  Flag not set: should_execute_merge() = {result_disabled}")
    if not result_disabled:
        print("  ✓ Auto-merge correctly disabled by default")
        test1_pass = True
    else:
        print("  ✗ Auto-merge should be disabled by default")
        test1_pass = False

    # Test with flag explicitly disabled
    os.environ['GRAPHITI_ENABLE_AUTO_MERGE'] = 'false'
    result_explicit_false = should_execute_merge()
    print(f"  Flag = 'false': should_execute_merge() = {result_explicit_false}")
    if not result_explicit_false:
        print("  ✓ Auto-merge correctly disabled")
        test2_pass = True
    else:
        print("  ✗ Auto-merge should be disabled")
        test2_pass = False

    # Test with flag enabled
    os.environ['GRAPHITI_ENABLE_AUTO_MERGE'] = 'true'
    result_enabled = should_execute_merge()
    print(f"  Flag = 'true': should_execute_merge() = {result_enabled}")
    if result_enabled:
        print("  ✓ Auto-merge correctly enabled")
        test3_pass = True
    else:
        print("  ✗ Auto-merge should be enabled")
        test3_pass = False

    # Cleanup
    os.environ.pop('GRAPHITI_ENABLE_AUTO_MERGE', None)

    all_pass = test1_pass and test2_pass and test3_pass
    print(f"\n  Summary: {'All tests passed' if all_pass else 'Some tests failed'}")
    return all_pass


def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("WORKER FIX VALIDATION - ISOLATED TESTING")
    print("="*60)
    print("\nTesting proposed fixes before applying to production...")

    results = {
        "Entity Extraction": test_entity_extraction_robustness(),
        "Embedding Conversion": test_embedding_type_conversion(),
        "Merge Feature Flag": test_merge_feature_flag()
    }

    print("\n" + "="*60)
    print("FINAL RESULTS")
    print("="*60)
    for test_name, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status}: {test_name}")

    all_passed = all(results.values())
    print("\n" + "="*60)
    if all_passed:
        print("✓ ALL TESTS PASSED - Fixes are safe to apply")
        return 0
    else:
        print("✗ SOME TESTS FAILED - Review fixes before applying")
        return 1


if __name__ == "__main__":
    sys.exit(main())
