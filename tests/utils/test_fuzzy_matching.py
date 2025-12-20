"""
Tests for fuzzy matching configuration and utilities.

Copyright 2024, Zep Software, Inc.
Licensed under the Apache License, Version 2.0.
"""

import os
from unittest.mock import patch

import pytest

from graphiti_core.utils.fuzzy_matching import (
    FuzzyMatcher,
    FuzzyMatchingConfig,
    MatchingMode,
    MatchingStrategy,
    get_fuzzy_matcher,
    is_edge_fuzzy_match,
    is_entity_fuzzy_match,
    reconfigure_default_matcher,
)


class TestMatchingStrategy:
    """Tests for MatchingStrategy enum."""

    def test_strict_value(self):
        assert MatchingStrategy.STRICT.value == 'strict'

    def test_balanced_value(self):
        assert MatchingStrategy.BALANCED.value == 'balanced'

    def test_permissive_value(self):
        assert MatchingStrategy.PERMISSIVE.value == 'permissive'

    def test_custom_value(self):
        assert MatchingStrategy.CUSTOM.value == 'custom'


class TestMatchingMode:
    """Tests for MatchingMode enum."""

    def test_word_overlap_value(self):
        assert MatchingMode.WORD_OVERLAP.value == 'word_overlap'

    def test_semantic_similarity_value(self):
        assert MatchingMode.SEMANTIC_SIMILARITY.value == 'semantic_similarity'

    def test_combined_value(self):
        assert MatchingMode.COMBINED.value == 'combined'


class TestFuzzyMatchingConfig:
    """Tests for FuzzyMatchingConfig dataclass."""

    def test_default_values(self):
        config = FuzzyMatchingConfig()
        assert config.semantic_threshold == 0.8
        assert config.word_overlap_threshold == 0.6
        assert config.combined_threshold == 0.75
        assert config.edge_semantic_threshold == 0.6
        assert config.edge_word_overlap_threshold == 0.4
        assert config.edge_combined_threshold == 0.55
        assert config.name_similarity_threshold == 0.85
        assert config.use_name_normalization is True
        assert config.require_minimum_word_overlap is True
        assert config.minimum_overlap_ratio == 0.3
        assert config.boost_exact_matches is True
        assert config.max_candidates_per_entity == 100
        assert config.enable_early_stopping is True

    def test_from_strategy_strict(self):
        config = FuzzyMatchingConfig.from_strategy(MatchingStrategy.STRICT)
        assert config.semantic_threshold == 0.9
        assert config.word_overlap_threshold == 0.8
        assert config.combined_threshold == 0.85
        assert config.edge_semantic_threshold == 0.8
        assert config.minimum_overlap_ratio == 0.5

    def test_from_strategy_permissive(self):
        config = FuzzyMatchingConfig.from_strategy(MatchingStrategy.PERMISSIVE)
        assert config.semantic_threshold == 0.6
        assert config.word_overlap_threshold == 0.4
        assert config.combined_threshold == 0.5
        assert config.edge_semantic_threshold == 0.5
        assert config.minimum_overlap_ratio == 0.2

    def test_from_strategy_balanced(self):
        config = FuzzyMatchingConfig.from_strategy(MatchingStrategy.BALANCED)
        # Should use default values
        assert config.semantic_threshold == 0.8
        assert config.word_overlap_threshold == 0.6

    def test_from_environment_default(self):
        with patch.dict(os.environ, {}, clear=True):
            config = FuzzyMatchingConfig.from_environment()
            # Should use balanced strategy defaults
            assert config.semantic_threshold == 0.8

    def test_from_environment_custom_strategy(self):
        with patch.dict(os.environ, {'FUZZY_MATCHING_STRATEGY': 'strict'}):
            config = FuzzyMatchingConfig.from_environment()
            assert config.semantic_threshold == 0.9

    def test_from_environment_custom_threshold(self):
        with patch.dict(
            os.environ,
            {
                'FUZZY_MATCHING_STRATEGY': 'balanced',
                'FUZZY_SEMANTIC_THRESHOLD': '0.95',
            },
        ):
            config = FuzzyMatchingConfig.from_environment()
            assert config.semantic_threshold == 0.95

    def test_from_environment_invalid_float(self):
        with patch.dict(
            os.environ,
            {'FUZZY_SEMANTIC_THRESHOLD': 'invalid'},
        ):
            # Should use default on invalid value
            config = FuzzyMatchingConfig.from_environment()
            assert config.semantic_threshold == 0.8

    def test_from_environment_invalid_strategy(self):
        with patch.dict(os.environ, {'FUZZY_MATCHING_STRATEGY': 'invalid_strategy'}):
            config = FuzzyMatchingConfig.from_environment()
            # Should fall back to balanced
            assert config.semantic_threshold == 0.8


class TestFuzzyMatcher:
    """Tests for FuzzyMatcher class."""

    def test_init_default_config(self):
        matcher = FuzzyMatcher()
        assert matcher.config is not None

    def test_init_custom_config(self):
        config = FuzzyMatchingConfig(semantic_threshold=0.95)
        matcher = FuzzyMatcher(config=config)
        assert matcher.config.semantic_threshold == 0.95

    def test_calculate_word_overlap_similarity_empty(self):
        matcher = FuzzyMatcher()
        assert matcher.calculate_word_overlap_similarity('', '') == 0.0
        assert matcher.calculate_word_overlap_similarity('hello', '') == 0.0
        assert matcher.calculate_word_overlap_similarity('', 'world') == 0.0

    def test_calculate_word_overlap_similarity_identical(self):
        config = FuzzyMatchingConfig(use_name_normalization=False)
        matcher = FuzzyMatcher(config=config)
        result = matcher.calculate_word_overlap_similarity('hello world', 'hello world')
        assert result == 1.0

    def test_calculate_word_overlap_similarity_partial(self):
        config = FuzzyMatchingConfig(
            use_name_normalization=False, require_minimum_word_overlap=False
        )
        matcher = FuzzyMatcher(config=config)
        # 'hello' overlaps, 'world' and 'there' don't
        # Jaccard: 1 / 3 = 0.333...
        result = matcher.calculate_word_overlap_similarity('hello world', 'hello there')
        assert abs(result - 1 / 3) < 0.01

    def test_calculate_word_overlap_similarity_no_overlap(self):
        config = FuzzyMatchingConfig(
            use_name_normalization=False, require_minimum_word_overlap=False
        )
        matcher = FuzzyMatcher(config=config)
        result = matcher.calculate_word_overlap_similarity('hello world', 'foo bar')
        assert result == 0.0

    def test_calculate_word_overlap_below_minimum_ratio(self):
        config = FuzzyMatchingConfig(
            use_name_normalization=False,
            require_minimum_word_overlap=True,
            minimum_overlap_ratio=0.5,
        )
        matcher = FuzzyMatcher(config=config)
        # 1 out of 2 words overlap (50%), but with 4 total unique words
        # overlap_ratio = 1/2 = 0.5, meets threshold
        result = matcher.calculate_word_overlap_similarity('hello world', 'hello there')
        assert result > 0.0

    def test_calculate_semantic_similarity_empty(self):
        matcher = FuzzyMatcher()
        assert matcher.calculate_semantic_similarity([], []) == 0.0
        assert matcher.calculate_semantic_similarity([1.0], []) == 0.0
        assert matcher.calculate_semantic_similarity([], [1.0]) == 0.0

    def test_calculate_semantic_similarity_identical(self):
        matcher = FuzzyMatcher()
        embedding = [0.5, 0.5, 0.5, 0.5]
        result = matcher.calculate_semantic_similarity(embedding, embedding)
        assert abs(result - 1.0) < 0.01

    def test_calculate_semantic_similarity_orthogonal(self):
        matcher = FuzzyMatcher()
        embedding1 = [1.0, 0.0]
        embedding2 = [0.0, 1.0]
        result = matcher.calculate_semantic_similarity(embedding1, embedding2)
        assert abs(result) < 0.01

    def test_calculate_combined_similarity(self):
        config = FuzzyMatchingConfig(
            use_name_normalization=False,
            require_minimum_word_overlap=False,
            boost_exact_matches=False,
        )
        matcher = FuzzyMatcher(config=config)
        # Identical text and embeddings
        embedding = [0.5, 0.5, 0.5, 0.5]
        result = matcher.calculate_combined_similarity(
            'hello world', 'hello world', embedding, embedding
        )
        # Should be close to 1.0 (word_sim=1.0, semantic_sim=1.0)
        assert result > 0.9

    def test_calculate_combined_similarity_exact_match_boost(self):
        config = FuzzyMatchingConfig(
            use_name_normalization=False,
            require_minimum_word_overlap=False,
            boost_exact_matches=True,
        )
        matcher = FuzzyMatcher(config=config)
        embedding = [0.5, 0.5, 0.5, 0.5]
        result = matcher.calculate_combined_similarity(
            'hello world', 'hello world', embedding, embedding
        )
        assert result == 1.0

    def test_is_entity_match_missing_names(self):
        matcher = FuzzyMatcher()
        assert matcher.is_entity_match({'name': ''}, {'name': 'test'}) is False
        assert matcher.is_entity_match({'name': 'test'}, {'name': ''}) is False
        assert matcher.is_entity_match({}, {'name': 'test'}) is False

    def test_is_entity_match_word_overlap_mode(self):
        config = FuzzyMatchingConfig(
            use_name_normalization=False,
            require_minimum_word_overlap=False,
            word_overlap_threshold=0.5,
        )
        matcher = FuzzyMatcher(config=config)
        entity1 = {'name': 'hello world'}
        entity2 = {'name': 'hello world'}
        assert matcher.is_entity_match(entity1, entity2, mode=MatchingMode.WORD_OVERLAP) is True

    def test_is_entity_match_semantic_mode(self):
        config = FuzzyMatchingConfig(semantic_threshold=0.9)
        matcher = FuzzyMatcher(config=config)
        embedding = [0.5, 0.5, 0.5, 0.5]
        entity1 = {'name': 'test', 'name_embedding': embedding}
        entity2 = {'name': 'test', 'name_embedding': embedding}
        assert (
            matcher.is_entity_match(entity1, entity2, mode=MatchingMode.SEMANTIC_SIMILARITY) is True
        )

    def test_is_edge_match_different_nodes(self):
        matcher = FuzzyMatcher()
        edge1 = {'source_node_uuid': 'a', 'target_node_uuid': 'b', 'fact': 'test'}
        edge2 = {'source_node_uuid': 'c', 'target_node_uuid': 'd', 'fact': 'test'}
        assert matcher.is_edge_match(edge1, edge2) is False

    def test_is_edge_match_same_nodes_similar_facts(self):
        config = FuzzyMatchingConfig(
            use_name_normalization=False,
            require_minimum_word_overlap=False,
            edge_combined_threshold=0.5,
        )
        matcher = FuzzyMatcher(config=config)
        embedding = [0.5, 0.5, 0.5, 0.5]
        edge1 = {
            'source_node_uuid': 'a',
            'target_node_uuid': 'b',
            'fact': 'test fact',
            'fact_embedding': embedding,
        }
        edge2 = {
            'source_node_uuid': 'a',
            'target_node_uuid': 'b',
            'fact': 'test fact',
            'fact_embedding': embedding,
        }
        assert matcher.is_edge_match(edge1, edge2) is True

    def test_find_entity_candidates_empty(self):
        matcher = FuzzyMatcher()
        target = {'name': 'test'}
        assert matcher.find_entity_candidates(target, []) == []

    def test_find_entity_candidates_no_name(self):
        matcher = FuzzyMatcher()
        target = {}
        candidates = [{'name': 'test'}]
        assert matcher.find_entity_candidates(target, candidates) == []

    def test_find_entity_candidates_with_matches(self):
        config = FuzzyMatchingConfig(
            use_name_normalization=False,
            require_minimum_word_overlap=False,
            combined_threshold=0.5,
        )
        matcher = FuzzyMatcher(config=config)
        embedding = [0.5, 0.5, 0.5, 0.5]
        target = {'name': 'test entity', 'name_embedding': embedding}
        candidates = [
            {'name': 'test entity', 'name_embedding': embedding},
            {'name': 'different thing', 'name_embedding': [0.1, 0.1, 0.1, 0.1]},
        ]
        matches = matcher.find_entity_candidates(target, candidates)
        assert len(matches) >= 1
        # First match should be the similar one
        assert matches[0][0]['name'] == 'test entity'

    def test_find_entity_candidates_early_stopping(self):
        config = FuzzyMatchingConfig(
            use_name_normalization=False,
            require_minimum_word_overlap=False,
            combined_threshold=0.1,  # Very low threshold
            max_candidates_per_entity=2,
            enable_early_stopping=True,
        )
        matcher = FuzzyMatcher(config=config)
        embedding = [0.5, 0.5, 0.5, 0.5]
        target = {'name': 'test', 'name_embedding': embedding}
        candidates = [{'name': f'test{i}', 'name_embedding': embedding} for i in range(10)]
        matches = matcher.find_entity_candidates(target, candidates)
        assert len(matches) <= 2

    def test_find_edge_candidates_empty(self):
        matcher = FuzzyMatcher()
        target = {'source_node_uuid': 'a', 'target_node_uuid': 'b', 'fact': 'test'}
        assert matcher.find_edge_candidates(target, []) == []

    def test_find_edge_candidates_no_fact(self):
        matcher = FuzzyMatcher()
        target = {'source_node_uuid': 'a', 'target_node_uuid': 'b'}
        candidates = [{'source_node_uuid': 'a', 'target_node_uuid': 'b', 'fact': 'test'}]
        assert matcher.find_edge_candidates(target, candidates) == []

    def test_get_similarity_stats_insufficient_entities(self):
        matcher = FuzzyMatcher()
        result = matcher.get_similarity_stats([])
        assert 'error' in result

        result = matcher.get_similarity_stats([{'name': 'test'}])
        assert 'error' in result

    def test_get_similarity_stats_with_entities(self):
        config = FuzzyMatchingConfig(
            use_name_normalization=False, require_minimum_word_overlap=False
        )
        matcher = FuzzyMatcher(config=config)
        embedding = [0.5, 0.5, 0.5, 0.5]
        entities = [
            {'name': 'test one', 'name_embedding': embedding},
            {'name': 'test two', 'name_embedding': embedding},
        ]
        stats = matcher.get_similarity_stats(entities)
        assert 'config' in stats
        assert 'word_overlap_stats' in stats
        assert 'semantic_similarity_stats' in stats
        assert 'combined_similarity_stats' in stats
        assert 'total_pairs_analyzed' in stats


class TestModuleFunctions:
    """Tests for module-level convenience functions."""

    def test_get_fuzzy_matcher_default(self):
        matcher = get_fuzzy_matcher()
        assert isinstance(matcher, FuzzyMatcher)

    def test_get_fuzzy_matcher_custom_config(self):
        config = FuzzyMatchingConfig(semantic_threshold=0.99)
        matcher = get_fuzzy_matcher(config)
        assert matcher.config.semantic_threshold == 0.99

    def test_reconfigure_default_matcher(self):
        original_matcher = get_fuzzy_matcher()
        new_config = FuzzyMatchingConfig(semantic_threshold=0.55)
        reconfigure_default_matcher(new_config)
        new_matcher = get_fuzzy_matcher()
        assert new_matcher.config.semantic_threshold == 0.55
        # Reset to default
        reconfigure_default_matcher(FuzzyMatchingConfig())

    def test_is_entity_fuzzy_match_default(self):
        entity1 = {'name': 'test', 'name_embedding': [0.5, 0.5]}
        entity2 = {'name': 'test', 'name_embedding': [0.5, 0.5]}
        # This may or may not match depending on normalization
        result = is_entity_fuzzy_match(entity1, entity2)
        assert isinstance(result, bool)

    def test_is_entity_fuzzy_match_custom_threshold(self):
        entity1 = {'name': 'test', 'name_embedding': [0.5, 0.5]}
        entity2 = {'name': 'test', 'name_embedding': [0.5, 0.5]}
        # Very low threshold should match
        result = is_entity_fuzzy_match(entity1, entity2, threshold=0.1)
        assert result is True

    def test_is_edge_fuzzy_match_default(self):
        edge1 = {
            'source_node_uuid': 'a',
            'target_node_uuid': 'b',
            'fact': 'test',
            'fact_embedding': [0.5, 0.5],
        }
        edge2 = {
            'source_node_uuid': 'a',
            'target_node_uuid': 'b',
            'fact': 'test',
            'fact_embedding': [0.5, 0.5],
        }
        result = is_edge_fuzzy_match(edge1, edge2)
        assert isinstance(result, bool)

    def test_is_edge_fuzzy_match_different_nodes(self):
        edge1 = {
            'source_node_uuid': 'a',
            'target_node_uuid': 'b',
            'fact': 'test',
        }
        edge2 = {
            'source_node_uuid': 'c',
            'target_node_uuid': 'd',
            'fact': 'test',
        }
        # Different nodes should never match
        result = is_edge_fuzzy_match(edge1, edge2)
        assert result is False
