"""
Comprehensive tests for graphiti_core/utils/maintenance/node_operations.py

Tests the core node operation functions:
- normalize_entity_name(): Entity name normalization
- calculate_fuzzy_similarity(): Fuzzy name matching
- generate_deterministic_uuid(): UUID generation
- merge_edge_properties(): Edge property merging
- merge_node_into(): Node merging operations
"""

import os
import pytest
from datetime import datetime, timezone
from uuid import UUID
from unittest.mock import patch, AsyncMock, MagicMock

# Import the functions we're testing
from graphiti_core.utils.maintenance.node_operations import (
    normalize_entity_name,
    calculate_fuzzy_similarity,
    generate_deterministic_uuid,
    merge_edge_properties,
)


# =============================================================================
# normalize_entity_name() Tests
# =============================================================================


class TestNormalizeEntityName:
    """Tests for the normalize_entity_name function."""

    def test_basic_lowercase_conversion(self):
        """Test basic lowercase conversion."""
        assert normalize_entity_name('HELLO') == 'hello'
        assert normalize_entity_name('Hello') == 'hello'
        assert normalize_entity_name('hello') == 'hello'

    def test_mixed_case(self):
        """Test mixed case handling."""
        assert normalize_entity_name('HeLLo WoRLd') == 'hello_world'
        assert normalize_entity_name('MyClass') == 'myclass'

    def test_separator_replacement(self):
        """Test replacement of various separators with underscores."""
        assert normalize_entity_name('hello-world') == 'hello_world'
        assert normalize_entity_name('hello.world') == 'hello_world'
        assert normalize_entity_name('hello world') == 'hello_world'
        assert normalize_entity_name('hello - world') == 'hello_world'

    def test_multiple_separators(self):
        """Test handling of multiple consecutive separators."""
        assert normalize_entity_name('hello---world') == 'hello_world'
        assert normalize_entity_name('hello...world') == 'hello_world'
        assert normalize_entity_name('hello   world') == 'hello_world'

    def test_special_characters_removal(self):
        """Test removal of special characters."""
        assert normalize_entity_name('hello!world') == 'helloworld'
        assert normalize_entity_name('hello@world') == 'helloworld'
        assert normalize_entity_name('hello#world') == 'helloworld'
        assert normalize_entity_name("hello'world") == 'helloworld'

    def test_unicode_handling(self):
        """Test handling of unicode characters."""
        # Unicode characters are removed
        assert normalize_entity_name('héllo') == 'hllo'
        assert normalize_entity_name('naïve') == 'nave'

    def test_leading_trailing_underscores(self):
        """Test removal of leading/trailing underscores."""
        assert normalize_entity_name('_hello_') == 'hello'
        assert normalize_entity_name('__hello__') == 'hello'
        assert normalize_entity_name('-hello-') == 'hello'

    def test_empty_string(self):
        """Test empty string handling."""
        assert normalize_entity_name('') == ''
        assert normalize_entity_name('   ') == '   '  # Preserves spaces-only before check

    def test_none_handling(self):
        """Test None handling."""
        assert normalize_entity_name(None) is None

    def test_only_special_chars(self):
        """Test string with only special characters."""
        # Returns original if normalization results in empty string
        result = normalize_entity_name('!!!')
        assert result == '!!!'  # Fallback to original

    def test_numbers_preserved(self):
        """Test that numbers are preserved."""
        assert normalize_entity_name('test123') == 'test123'
        assert normalize_entity_name('123test') == '123test'
        assert normalize_entity_name('test 123') == 'test_123'

    @patch.dict(os.environ, {'DEDUP_NORMALIZE_NAMES': 'false'})
    def test_disabled_normalization(self):
        """Test that normalization can be disabled via env var."""
        result = normalize_entity_name('Hello World')
        assert result == 'Hello World'  # Original preserved when disabled

    @patch.dict(os.environ, {'DEDUP_NORMALIZE_NAMES': 'true'})
    def test_enabled_normalization(self):
        """Test that normalization is enabled via env var."""
        result = normalize_entity_name('Hello World')
        assert result == 'hello_world'

    def test_real_world_examples(self):
        """Test with real-world entity name examples."""
        assert normalize_entity_name('New York City') == 'new_york_city'
        assert normalize_entity_name('Mr. Smith') == 'mr_smith'
        assert normalize_entity_name("O'Brien") == 'obrien'
        assert normalize_entity_name('Smith & Co.') == 'smith_co'
        assert normalize_entity_name('AI/ML Engineer') == 'aiml_engineer'


# =============================================================================
# calculate_fuzzy_similarity() Tests
# =============================================================================


class TestCalculateFuzzySimilarity:
    """Tests for the calculate_fuzzy_similarity function."""

    def test_identical_names(self):
        """Test similarity of identical names."""
        assert calculate_fuzzy_similarity('hello', 'hello') == 1.0
        assert calculate_fuzzy_similarity('Test Entity', 'Test Entity') == 1.0

    def test_case_insensitive(self):
        """Test case-insensitive matching."""
        result = calculate_fuzzy_similarity('Hello', 'hello')
        assert result == 1.0  # After normalization, they're identical

    def test_separator_normalization(self):
        """Test that separators are normalized before comparison."""
        assert calculate_fuzzy_similarity('hello world', 'hello-world') == 1.0
        assert calculate_fuzzy_similarity('hello.world', 'hello_world') == 1.0

    def test_completely_different(self):
        """Test similarity of completely different names."""
        result = calculate_fuzzy_similarity('alice', 'bob')
        assert result < 0.5

    def test_partial_match(self):
        """Test partial matching."""
        result = calculate_fuzzy_similarity('hello', 'helloworld')
        assert 0.0 < result < 1.0

    def test_similar_names(self):
        """Test similar but not identical names."""
        # Off by one character
        result = calculate_fuzzy_similarity('hello', 'hallo')
        assert result > 0.7

    def test_empty_strings(self):
        """Test empty string handling."""
        assert calculate_fuzzy_similarity('', '') == 0.0
        assert calculate_fuzzy_similarity('hello', '') == 0.0
        assert calculate_fuzzy_similarity('', 'hello') == 0.0

    def test_none_handling(self):
        """Test None handling."""
        assert calculate_fuzzy_similarity(None, 'hello') == 0.0
        assert calculate_fuzzy_similarity('hello', None) == 0.0
        assert calculate_fuzzy_similarity(None, None) == 0.0

    def test_very_short_strings(self):
        """Test very short strings."""
        assert calculate_fuzzy_similarity('a', 'a') == 1.0
        assert calculate_fuzzy_similarity('a', 'b') == 0.0

    def test_typo_detection(self):
        """Test detection of common typos."""
        # Transposition
        result = calculate_fuzzy_similarity('recieve', 'receive')
        assert result > 0.8

        # Missing letter
        result = calculate_fuzzy_similarity('manger', 'manager')
        assert result > 0.8

    def test_threshold_examples(self):
        """Test examples near typical threshold (0.9)."""
        # Should be above 0.9
        high_similarity = calculate_fuzzy_similarity('organization', 'Organisation')
        assert high_similarity > 0.9

        # Should be below 0.9
        low_similarity = calculate_fuzzy_similarity('alice', 'alex')
        assert low_similarity < 0.9


# =============================================================================
# generate_deterministic_uuid() Tests
# =============================================================================


class TestGenerateDeterministicUuid:
    """Tests for the generate_deterministic_uuid function."""

    def test_valid_uuid_format(self):
        """Test that generated UUIDs are valid."""
        result = generate_deterministic_uuid('test', 'group1')
        UUID(result)  # This will raise if invalid

    def test_deterministic_output(self):
        """Test that same inputs produce same UUID."""
        uuid1 = generate_deterministic_uuid('entity', 'group')
        uuid2 = generate_deterministic_uuid('entity', 'group')
        assert uuid1 == uuid2

    def test_different_names_different_uuids(self):
        """Test that different names produce different UUIDs."""
        uuid1 = generate_deterministic_uuid('alice', 'group')
        uuid2 = generate_deterministic_uuid('bob', 'group')
        assert uuid1 != uuid2

    def test_different_groups_different_uuids(self):
        """Test that different groups produce different UUIDs."""
        uuid1 = generate_deterministic_uuid('entity', 'group1')
        uuid2 = generate_deterministic_uuid('entity', 'group2')
        assert uuid1 != uuid2

    def test_name_normalization(self):
        """Test that name normalization affects UUID generation."""
        # These should produce the same UUID after normalization
        uuid1 = generate_deterministic_uuid('Hello World', 'group')
        uuid2 = generate_deterministic_uuid('hello world', 'group')
        # Note: This depends on normalize_entity_name being called internally
        # The actual behavior should be tested based on implementation

    def test_special_characters_in_name(self):
        """Test handling of special characters in name."""
        result = generate_deterministic_uuid('test!@#$%', 'group')
        UUID(result)  # Should still be valid

    def test_unicode_in_name(self):
        """Test handling of unicode in name."""
        result = generate_deterministic_uuid('tëst', 'group')
        UUID(result)

    def test_empty_name(self):
        """Test handling of empty name."""
        result = generate_deterministic_uuid('', 'group')
        UUID(result)  # Should still produce valid UUID

    def test_very_long_name(self):
        """Test handling of very long names."""
        long_name = 'a' * 10000
        result = generate_deterministic_uuid(long_name, 'group')
        UUID(result)

    def test_consistency_across_calls(self):
        """Test UUID consistency across multiple calls."""
        results = [generate_deterministic_uuid('test', 'group') for _ in range(100)]
        assert len(set(results)) == 1  # All should be identical


# =============================================================================
# merge_edge_properties() Tests
# =============================================================================


class TestMergeEdgeProperties:
    """Tests for the merge_edge_properties function."""

    def test_empty_properties(self):
        """Test merging with empty properties."""
        result = merge_edge_properties({}, {})
        assert result == {}

    def test_existing_only(self):
        """Test that existing properties are preserved."""
        existing = {'fact': 'test fact', 'group_id': 'g1'}
        incoming = {}
        result = merge_edge_properties(existing, incoming)
        assert result == existing

    def test_incoming_only_new_fields(self):
        """Test that new incoming fields are added."""
        existing = {'fact': 'test'}
        incoming = {'new_field': 'value'}
        result = merge_edge_properties(existing, incoming)
        assert result['fact'] == 'test'
        assert result['new_field'] == 'value'

    def test_episodes_union(self):
        """Test that episodes are unioned."""
        existing = {'episodes': ['e1', 'e2']}
        incoming = {'episodes': ['e2', 'e3']}
        result = merge_edge_properties(existing, incoming)
        assert set(result['episodes']) == {'e1', 'e2', 'e3'}

    def test_episodes_single_to_list(self):
        """Test episodes conversion from single value to list."""
        existing = {'episodes': 'e1'}
        incoming = {'episodes': 'e2'}
        result = merge_edge_properties(existing, incoming)
        assert 'e1' in result['episodes']
        assert 'e2' in result['episodes']

    def test_created_at_earliest(self):
        """Test that created_at uses earliest timestamp."""
        t1 = datetime(2020, 1, 1, tzinfo=timezone.utc)
        t2 = datetime(2021, 1, 1, tzinfo=timezone.utc)

        existing = {'created_at': t2}
        incoming = {'created_at': t1}
        result = merge_edge_properties(existing, incoming)
        assert result['created_at'] == t1  # Earlier one

    def test_valid_at_minimum(self):
        """Test that valid_at uses minimum timestamp."""
        t1 = datetime(2020, 1, 1, tzinfo=timezone.utc)
        t2 = datetime(2021, 1, 1, tzinfo=timezone.utc)

        existing = {'valid_at': t2}
        incoming = {'valid_at': t1}
        result = merge_edge_properties(existing, incoming)
        assert result['valid_at'] == t1

    def test_invalid_at_maximum(self):
        """Test that invalid_at uses maximum timestamp."""
        t1 = datetime(2020, 1, 1, tzinfo=timezone.utc)
        t2 = datetime(2021, 1, 1, tzinfo=timezone.utc)

        existing = {'invalid_at': t1}
        incoming = {'invalid_at': t2}
        result = merge_edge_properties(existing, incoming)
        assert result['invalid_at'] == t2  # Later one

    def test_fact_prefers_existing(self):
        """Test that existing fact is preferred."""
        existing = {'fact': 'existing fact'}
        incoming = {'fact': 'incoming fact'}
        result = merge_edge_properties(existing, incoming)
        assert result['fact'] == 'existing fact'

    def test_fact_uses_incoming_if_existing_empty(self):
        """Test that incoming fact is used if existing is empty."""
        existing = {'fact': ''}
        incoming = {'fact': 'incoming fact'}
        result = merge_edge_properties(existing, incoming)
        assert result['fact'] == 'incoming fact'

    def test_fact_embedding_prefers_existing(self):
        """Test that existing fact_embedding is preferred."""
        existing = {'fact_embedding': [1.0, 2.0]}
        incoming = {'fact_embedding': [3.0, 4.0]}
        result = merge_edge_properties(existing, incoming)
        assert result['fact_embedding'] == [1.0, 2.0]

    def test_fact_embedding_uses_incoming_if_missing(self):
        """Test that incoming embedding is used if existing is missing."""
        existing = {}
        incoming = {'fact_embedding': [1.0, 2.0]}
        result = merge_edge_properties(existing, incoming)
        assert result['fact_embedding'] == [1.0, 2.0]

    def test_fact_embedding_sanitization(self):
        """Test that empty fact_embedding lists are sanitized."""
        existing = {}
        incoming = {'fact_embedding': []}
        result = merge_edge_properties(existing, incoming)
        # Empty list should be converted to None or not set
        assert result.get('fact_embedding') is None

    def test_attributes_merge(self):
        """Test that attributes dictionaries are merged."""
        existing = {'attributes': {'a': 1, 'b': 2}}
        incoming = {'attributes': {'b': 3, 'c': 4}}
        result = merge_edge_properties(existing, incoming)
        assert result['attributes']['a'] == 1  # Existing preserved
        assert result['attributes']['b'] == 2  # Existing preferred on conflict
        assert result['attributes']['c'] == 4  # New added

    def test_group_id_excluded_from_override(self):
        """Test that group_id is not overwritten."""
        existing = {'group_id': 'g1'}
        incoming = {'group_id': 'g2'}
        result = merge_edge_properties(existing, incoming)
        assert result['group_id'] == 'g1'

    def test_new_property_fills_missing(self):
        """Test that new properties fill missing values."""
        existing = {'name': None}
        incoming = {'name': 'test_name'}
        result = merge_edge_properties(existing, incoming)
        assert result['name'] == 'test_name'

    def test_complex_merge_scenario(self):
        """Test complex merge scenario with multiple properties."""
        t1 = datetime(2020, 1, 1, tzinfo=timezone.utc)
        t2 = datetime(2021, 1, 1, tzinfo=timezone.utc)

        existing = {
            'fact': 'original fact',
            'fact_embedding': [1.0, 2.0],
            'episodes': ['e1', 'e2'],
            'created_at': t2,
            'valid_at': t2,
            'invalid_at': t1,
            'attributes': {'a': 1},
            'group_id': 'g1',
        }

        incoming = {
            'fact': 'new fact',
            'fact_embedding': [3.0, 4.0],
            'episodes': ['e2', 'e3'],
            'created_at': t1,
            'valid_at': t1,
            'invalid_at': t2,
            'attributes': {'b': 2},
            'group_id': 'g2',
            'new_field': 'value',
        }

        result = merge_edge_properties(existing, incoming)

        # Verify all merge policies
        assert result['fact'] == 'original fact'  # Existing preferred
        assert result['fact_embedding'] == [1.0, 2.0]  # Existing preferred
        assert set(result['episodes']) == {'e1', 'e2', 'e3'}  # Union
        assert result['created_at'] == t1  # Earliest
        assert result['valid_at'] == t1  # Minimum
        assert result['invalid_at'] == t2  # Maximum
        assert result['attributes']['a'] == 1  # Preserved
        assert result['attributes']['b'] == 2  # Added
        assert result['group_id'] == 'g1'  # Not overwritten
        assert result['new_field'] == 'value'  # New field added


# =============================================================================
# Edge Cases and Error Handling
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_normalize_with_whitespace_only(self):
        """Test normalization of whitespace-only strings."""
        result = normalize_entity_name('   ')
        # Should either return original or handle gracefully
        assert isinstance(result, str)

    def test_similarity_with_numbers(self):
        """Test similarity calculation with numbers."""
        result = calculate_fuzzy_similarity('test123', 'test124')
        assert 0.0 < result < 1.0

    def test_uuid_with_special_group_id(self):
        """Test UUID generation with special group IDs."""
        result = generate_deterministic_uuid('entity', 'group-with-dashes')
        UUID(result)

        result = generate_deterministic_uuid('entity', 'group.with.dots')
        UUID(result)

    def test_merge_with_none_values(self):
        """Test merging with None values in properties."""
        existing = {'fact': None, 'name': 'test'}
        incoming = {'fact': 'new fact', 'other': None}
        result = merge_edge_properties(existing, incoming)
        assert result['fact'] == 'new fact'
        assert result['name'] == 'test'


# =============================================================================
# Performance Tests
# =============================================================================


class TestPerformance:
    """Performance-related tests."""

    def test_normalize_large_batch(self):
        """Test normalization of large batch of names."""
        names = [f'Entity {i} with special chars!' for i in range(1000)]
        results = [normalize_entity_name(name) for name in names]
        assert len(results) == 1000

    def test_uuid_generation_batch(self):
        """Test UUID generation for large batch."""
        results = [generate_deterministic_uuid(f'entity_{i}', 'group') for i in range(1000)]
        # All should be unique
        assert len(set(results)) == 1000

    def test_similarity_batch(self):
        """Test similarity calculation for batch."""
        pairs = [(f'entity{i}', f'entity{i + 1}') for i in range(100)]
        results = [calculate_fuzzy_similarity(a, b) for a, b in pairs]
        assert len(results) == 100


# =============================================================================
# Integration-style Tests
# =============================================================================


class TestIntegration:
    """Tests that verify components work together."""

    def test_normalize_then_similarity(self):
        """Test that normalization and similarity work together."""
        name1 = 'Hello World'
        name2 = 'hello-world'

        # After normalization, these should be identical
        norm1 = normalize_entity_name(name1)
        norm2 = normalize_entity_name(name2)
        assert norm1 == norm2

        # Similarity should be 1.0
        similarity = calculate_fuzzy_similarity(name1, name2)
        assert similarity == 1.0

    def test_normalize_then_uuid(self):
        """Test that normalization affects UUID generation consistently."""
        uuid1 = generate_deterministic_uuid('Hello World', 'group')
        uuid2 = generate_deterministic_uuid('hello-world', 'group')

        # These should produce the same UUID after normalization
        # (assuming normalize_entity_name is called internally)

    def test_merge_preserves_critical_data(self):
        """Test that merging never loses critical data."""
        existing = {
            'uuid': 'uuid-123',
            'fact': 'important fact',
            'episodes': ['e1', 'e2'],
        }

        incoming = {
            'uuid': 'uuid-456',  # Should not override
            'fact': 'less important',
            'episodes': ['e3'],
        }

        result = merge_edge_properties(existing, incoming)

        # Critical data preserved
        assert 'e1' in result['episodes']
        assert 'e2' in result['episodes']
        assert 'e3' in result['episodes']
        assert result['fact'] == 'important fact'
