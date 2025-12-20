"""
Tests for merge policies configuration and utilities.

Copyright 2024, Zep Software, Inc.
Licensed under the Apache License, Version 2.0.
"""

import os
from datetime import datetime
from unittest.mock import patch

import pytest

from graphiti_core.utils.merge_policies import (
    ConflictResolution,
    EntityMerger,
    FieldMergeMode,
    FieldMergeRule,
    MergePolicyConfig,
    MergeStrategy,
    create_merge_policy_from_strategy,
    get_entity_merger,
    merge_duplicate_entities,
)


class TestMergeStrategy:
    """Tests for MergeStrategy enum."""

    def test_preserve_oldest_value(self):
        assert MergeStrategy.PRESERVE_OLDEST.value == 'preserve_oldest'

    def test_preserve_newest_value(self):
        assert MergeStrategy.PRESERVE_NEWEST.value == 'preserve_newest'

    def test_preserve_most_complete_value(self):
        assert MergeStrategy.PRESERVE_MOST_COMPLETE.value == 'preserve_most_complete'

    def test_preserve_highest_centrality_value(self):
        assert MergeStrategy.PRESERVE_HIGHEST_CENTRALITY.value == 'preserve_highest_centrality'

    def test_aggregate_all_value(self):
        assert MergeStrategy.AGGREGATE_ALL.value == 'aggregate_all'

    def test_custom_value(self):
        assert MergeStrategy.CUSTOM.value == 'custom'


class TestConflictResolution:
    """Tests for ConflictResolution enum."""

    def test_first_wins_value(self):
        assert ConflictResolution.FIRST_WINS.value == 'first_wins'

    def test_last_wins_value(self):
        assert ConflictResolution.LAST_WINS.value == 'last_wins'

    def test_longest_wins_value(self):
        assert ConflictResolution.LONGEST_WINS.value == 'longest_wins'

    def test_numeric_max_value(self):
        assert ConflictResolution.NUMERIC_MAX.value == 'numeric_max'

    def test_numeric_min_value(self):
        assert ConflictResolution.NUMERIC_MIN.value == 'numeric_min'

    def test_numeric_average_value(self):
        assert ConflictResolution.NUMERIC_AVERAGE.value == 'numeric_average'

    def test_concatenate_value(self):
        assert ConflictResolution.CONCATENATE.value == 'concatenate'

    def test_list_union_value(self):
        assert ConflictResolution.LIST_UNION.value == 'list_union'

    def test_custom_value(self):
        assert ConflictResolution.CUSTOM.value == 'custom'


class TestFieldMergeMode:
    """Tests for FieldMergeMode enum."""

    def test_overwrite_value(self):
        assert FieldMergeMode.OVERWRITE.value == 'overwrite'

    def test_merge_value(self):
        assert FieldMergeMode.MERGE.value == 'merge'

    def test_preserve_value(self):
        assert FieldMergeMode.PRESERVE.value == 'preserve'

    def test_skip_value(self):
        assert FieldMergeMode.SKIP.value == 'skip'


class TestFieldMergeRule:
    """Tests for FieldMergeRule dataclass."""

    def test_basic_creation(self):
        rule = FieldMergeRule(
            field_name='name',
            mode=FieldMergeMode.MERGE,
            conflict_resolution=ConflictResolution.LONGEST_WINS,
        )
        assert rule.field_name == 'name'
        assert rule.mode == FieldMergeMode.MERGE
        assert rule.conflict_resolution == ConflictResolution.LONGEST_WINS

    def test_default_values(self):
        rule = FieldMergeRule(
            field_name='test',
            mode=FieldMergeMode.PRESERVE,
            conflict_resolution=ConflictResolution.FIRST_WINS,
        )
        assert rule.custom_function is None
        assert rule.priority_weight == 1.0
        assert rule.preserve_history is False

    def test_custom_function(self):
        def custom_merge(values):
            return values[0]

        rule = FieldMergeRule(
            field_name='test',
            mode=FieldMergeMode.MERGE,
            conflict_resolution=ConflictResolution.CUSTOM,
            custom_function=custom_merge,
        )
        assert rule.custom_function is not None
        assert rule.custom_function(['a', 'b']) == 'a'


class TestMergePolicyConfig:
    """Tests for MergePolicyConfig dataclass."""

    def test_default_values(self):
        config = MergePolicyConfig()
        assert config.strategy == MergeStrategy.PRESERVE_MOST_COMPLETE
        assert config.default_conflict_resolution == ConflictResolution.FIRST_WINS
        assert config.preserve_entity_with_most_edges is True
        assert config.preserve_entity_with_highest_degree is True
        assert config.preserve_entity_with_longest_summary is True
        assert config.merge_labels is True
        assert config.merge_attributes is True
        assert config.preserve_timestamps is True
        assert config.track_merge_history is True
        assert config.max_history_entries == 10
        assert config.validate_merged_entity is True
        assert config.require_manual_review is False

    def test_default_field_rules_created(self):
        config = MergePolicyConfig()
        assert config.field_rules is not None
        assert 'uuid' in config.field_rules
        assert 'name' in config.field_rules
        assert 'summary' in config.field_rules
        assert 'labels' in config.field_rules

    def test_default_centrality_weights(self):
        config = MergePolicyConfig()
        assert config.centrality_weights is not None
        assert 'centrality_degree' in config.centrality_weights
        assert 'centrality_pagerank' in config.centrality_weights
        assert 'centrality_betweenness' in config.centrality_weights
        assert 'centrality_eigenvector' in config.centrality_weights
        # Weights should sum to 1.0
        total = sum(config.centrality_weights.values())
        assert abs(total - 1.0) < 0.001

    def test_custom_strategy(self):
        config = MergePolicyConfig(strategy=MergeStrategy.PRESERVE_OLDEST)
        assert config.strategy == MergeStrategy.PRESERVE_OLDEST

    def test_from_environment_default(self):
        with patch.dict(os.environ, {}, clear=True):
            config = MergePolicyConfig.from_environment()
            assert config.strategy == MergeStrategy.PRESERVE_MOST_COMPLETE

    def test_from_environment_custom_strategy(self):
        with patch.dict(os.environ, {'MERGE_STRATEGY': 'preserve_oldest'}):
            config = MergePolicyConfig.from_environment()
            assert config.strategy == MergeStrategy.PRESERVE_OLDEST

    def test_from_environment_custom_bools(self):
        with patch.dict(
            os.environ,
            {
                'MERGE_LABELS': 'false',
                'MERGE_REQUIRE_MANUAL_REVIEW': 'true',
            },
        ):
            config = MergePolicyConfig.from_environment()
            assert config.merge_labels is False
            assert config.require_manual_review is True


class TestEntityMerger:
    """Tests for EntityMerger class."""

    def test_init_default_config(self):
        merger = EntityMerger()
        assert merger.config is not None

    def test_init_custom_config(self):
        config = MergePolicyConfig(strategy=MergeStrategy.PRESERVE_OLDEST)
        merger = EntityMerger(config=config)
        assert merger.config.strategy == MergeStrategy.PRESERVE_OLDEST

    def test_merge_empty_list(self):
        merger = EntityMerger()
        with pytest.raises(ValueError, match='Cannot merge empty entity list'):
            merger.merge_entities([])

    def test_merge_single_entity(self):
        merger = EntityMerger()
        entity = {'uuid': 'test-1', 'name': 'Test Entity'}
        result = merger.merge_entities([entity])
        assert result == entity

    def test_merge_two_entities(self):
        config = MergePolicyConfig(
            strategy=MergeStrategy.PRESERVE_MOST_COMPLETE,
            validate_merged_entity=False,
        )
        merger = EntityMerger(config=config)

        entity1 = {
            'uuid': 'test-1',
            'name': 'Test Entity',
            'summary': 'Short summary',
        }
        entity2 = {
            'uuid': 'test-2',
            'name': 'Test Entity Extended',
            'summary': 'This is a much longer summary with more details',
        }

        result = merger.merge_entities([entity1, entity2])
        # Should preserve the entity with most complete data
        assert result['uuid'] is not None
        assert result['name'] is not None

    def test_calculate_completeness_score_empty(self):
        merger = EntityMerger()
        score = merger._calculate_completeness_score({})
        assert score == 0.0

    def test_calculate_completeness_score_with_name(self):
        merger = EntityMerger()
        score = merger._calculate_completeness_score({'name': 'Test'})
        assert score >= 1.0

    def test_calculate_completeness_score_with_summary(self):
        merger = EntityMerger()
        score_short = merger._calculate_completeness_score({'name': 'Test', 'summary': 'Short'})
        score_long = merger._calculate_completeness_score({'name': 'Test', 'summary': 'A' * 200})
        assert score_long > score_short

    def test_calculate_completeness_score_with_centrality(self):
        merger = EntityMerger()
        score_without = merger._calculate_completeness_score({'name': 'Test'})
        score_with = merger._calculate_completeness_score(
            {'name': 'Test', 'centrality_degree': 0.5, 'centrality_pagerank': 0.3}
        )
        assert score_with > score_without

    def test_calculate_centrality_score(self):
        # Use centrality_weights keys that match the config
        config = MergePolicyConfig()
        merger = EntityMerger(config=config)
        # The weights use different naming from default config
        # Use the actual weight keys from the config
        entity = {k: 0.5 for k in merger.config.centrality_weights.keys()}
        score = merger._calculate_centrality_score(entity)
        assert score > 0

    def test_calculate_centrality_score_empty(self):
        merger = EntityMerger()
        score = merger._calculate_centrality_score({})
        assert score == 0.0

    def test_resolve_field_conflict_empty(self):
        merger = EntityMerger()
        result = merger._resolve_field_conflict([], ConflictResolution.FIRST_WINS)
        assert result is None

    def test_resolve_field_conflict_single_value(self):
        merger = EntityMerger()
        result = merger._resolve_field_conflict(['value'], ConflictResolution.FIRST_WINS)
        assert result == 'value'

    def test_resolve_field_conflict_first_wins(self):
        merger = EntityMerger()
        result = merger._resolve_field_conflict(['first', 'second'], ConflictResolution.FIRST_WINS)
        assert result == 'first'

    def test_resolve_field_conflict_last_wins(self):
        merger = EntityMerger()
        result = merger._resolve_field_conflict(['first', 'second'], ConflictResolution.LAST_WINS)
        assert result == 'second'

    def test_resolve_field_conflict_longest_wins(self):
        merger = EntityMerger()
        result = merger._resolve_field_conflict(
            ['short', 'much longer value'], ConflictResolution.LONGEST_WINS
        )
        assert result == 'much longer value'

    def test_resolve_field_conflict_numeric_max(self):
        merger = EntityMerger()
        result = merger._resolve_field_conflict([1, 5, 3], ConflictResolution.NUMERIC_MAX)
        assert result == 5

    def test_resolve_field_conflict_numeric_min(self):
        merger = EntityMerger()
        result = merger._resolve_field_conflict([1, 5, 3], ConflictResolution.NUMERIC_MIN)
        assert result == 1

    def test_resolve_field_conflict_numeric_average(self):
        merger = EntityMerger()
        result = merger._resolve_field_conflict([2, 4, 6], ConflictResolution.NUMERIC_AVERAGE)
        assert result == 4.0

    def test_resolve_field_conflict_concatenate(self):
        merger = EntityMerger()
        result = merger._resolve_field_conflict(['a', 'b', 'c'], ConflictResolution.CONCATENATE)
        assert result == 'a | b | c'

    def test_resolve_field_conflict_list_union(self):
        merger = EntityMerger()
        result = merger._resolve_field_conflict(
            [['a', 'b'], ['b', 'c']], ConflictResolution.LIST_UNION
        )
        assert set(result) == {'a', 'b', 'c'}

    def test_resolve_field_conflict_custom(self):
        merger = EntityMerger()

        def custom_fn(values):
            return sum(len(str(v)) for v in values)

        result = merger._resolve_field_conflict(
            ['a', 'bb', 'ccc'], ConflictResolution.CUSTOM, custom_fn
        )
        assert result == 6  # 1 + 2 + 3

    def test_add_merge_history(self):
        config = MergePolicyConfig(track_merge_history=True, max_history_entries=5)
        merger = EntityMerger(config=config)

        merged_entity = {'uuid': 'merged-1', 'name': 'Merged'}
        source_entities = [
            {'uuid': 'source-1', 'name': 'Source 1'},
            {'uuid': 'source-2', 'name': 'Source 2'},
        ]

        result = merger._add_merge_history(merged_entity, source_entities)
        assert 'merge_history' in result
        assert len(result['merge_history']) == 1
        assert result['merge_history'][0]['entity_count'] == 2

    def test_add_merge_history_limits_entries(self):
        config = MergePolicyConfig(track_merge_history=True, max_history_entries=2)
        merger = EntityMerger(config=config)

        # Pre-existing history
        merged_entity = {
            'uuid': 'merged-1',
            'name': 'Merged',
            'merge_history': [
                {'timestamp': '2024-01-01', 'entity_count': 2},
                {'timestamp': '2024-01-02', 'entity_count': 3},
            ],
        }
        source_entities = [{'uuid': 'source-1'}, {'uuid': 'source-2'}]

        result = merger._add_merge_history(merged_entity, source_entities)
        assert len(result['merge_history']) == 2  # Limited to max

    def test_can_auto_merge_single(self):
        merger = EntityMerger()
        assert merger.can_auto_merge([{'uuid': '1', 'name': 'Test'}]) is True

    def test_can_auto_merge_too_many(self):
        config = MergePolicyConfig(require_manual_review=False)
        merger = EntityMerger(config=config)
        entities = [{'uuid': f'{i}', 'name': f'Test {i}'} for i in range(10)]
        assert merger.can_auto_merge(entities) is False

    def test_can_auto_merge_requires_manual_review(self):
        config = MergePolicyConfig(require_manual_review=True)
        merger = EntityMerger(config=config)
        entities = [{'uuid': '1', 'name': 'Test'}]
        assert merger.can_auto_merge(entities) is False

    def test_merge_with_conflict_report(self):
        config = MergePolicyConfig(validate_merged_entity=False)
        merger = EntityMerger(config=config)

        entities = [
            {'uuid': '1', 'name': 'Name A', 'summary': 'Summary 1'},
            {'uuid': '2', 'name': 'Name B', 'summary': 'Summary 2'},
        ]

        merged, conflicts = merger.merge_with_conflict_report(entities)
        assert merged is not None
        assert isinstance(conflicts, dict)
        # Should detect conflicts in name and summary
        assert 'name' in conflicts or 'summary' in conflicts

    def test_get_merge_preview(self):
        config = MergePolicyConfig(validate_merged_entity=False)
        merger = EntityMerger(config=config)

        entities = [
            {'uuid': '1', 'name': 'Test 1', 'summary': 'Short'},
            {'uuid': '2', 'name': 'Test 2', 'summary': 'Much longer summary'},
        ]

        preview = merger.get_merge_preview(entities)
        assert 'primary_entity_uuid' in preview
        assert 'total_entities' in preview
        assert preview['total_entities'] == 2
        assert 'completeness_scores' in preview
        assert 'centrality_scores' in preview
        assert 'can_auto_merge' in preview
        assert 'estimated_conflicts' in preview

    def test_estimate_conflicts(self):
        merger = EntityMerger()
        entities = [
            {'uuid': '1', 'name': 'Same Name'},
            {'uuid': '2', 'name': 'Same Name'},
        ]
        # Same name should not be a conflict
        conflicts = merger._estimate_conflicts(entities)
        assert conflicts >= 1  # At least uuid is different


class TestModuleFunctions:
    """Tests for module-level convenience functions."""

    def test_get_entity_merger_default(self):
        merger = get_entity_merger()
        assert isinstance(merger, EntityMerger)

    def test_get_entity_merger_custom_config(self):
        config = MergePolicyConfig(strategy=MergeStrategy.PRESERVE_NEWEST)
        merger = get_entity_merger(config)
        assert merger.config.strategy == MergeStrategy.PRESERVE_NEWEST

    def test_merge_duplicate_entities_basic(self):
        entities = [
            {'uuid': '1', 'name': 'Test Entity'},
        ]
        result = merge_duplicate_entities(entities)
        assert result['name'] == 'Test Entity'

    def test_create_merge_policy_from_strategy_valid(self):
        config = create_merge_policy_from_strategy('preserve_oldest')
        assert config.strategy == MergeStrategy.PRESERVE_OLDEST
        assert config.preserve_timestamps is True

    def test_create_merge_policy_from_strategy_newest(self):
        config = create_merge_policy_from_strategy('preserve_newest')
        assert config.strategy == MergeStrategy.PRESERVE_NEWEST
        assert config.default_conflict_resolution == ConflictResolution.LAST_WINS

    def test_create_merge_policy_from_strategy_aggregate(self):
        config = create_merge_policy_from_strategy('aggregate_all')
        assert config.strategy == MergeStrategy.AGGREGATE_ALL
        assert config.merge_labels is True
        assert config.default_conflict_resolution == ConflictResolution.CONCATENATE

    def test_create_merge_policy_from_strategy_invalid(self):
        config = create_merge_policy_from_strategy('invalid_strategy')
        # Should fall back to default
        assert config.strategy == MergeStrategy.PRESERVE_MOST_COMPLETE


class TestMergeStrategies:
    """Tests for different merge strategies."""

    def test_preserve_oldest_strategy(self):
        config = MergePolicyConfig(
            strategy=MergeStrategy.PRESERVE_OLDEST,
            validate_merged_entity=False,
        )
        merger = EntityMerger(config=config)

        entities = [
            {'uuid': '1', 'name': 'Old Entity', 'created_at': datetime(2020, 1, 1)},
            {'uuid': '2', 'name': 'New Entity', 'created_at': datetime(2024, 1, 1)},
        ]

        result = merger.merge_entities(entities)
        # Should preserve oldest entity's uuid
        assert result['uuid'] == '1'

    def test_preserve_newest_strategy(self):
        config = MergePolicyConfig(
            strategy=MergeStrategy.PRESERVE_NEWEST,
            validate_merged_entity=False,
        )
        merger = EntityMerger(config=config)

        entities = [
            {'uuid': '1', 'name': 'Old Entity', 'created_at': datetime(2020, 1, 1)},
            {'uuid': '2', 'name': 'New Entity', 'created_at': datetime(2024, 1, 1)},
        ]

        result = merger.merge_entities(entities)
        # Should preserve newest entity's uuid
        assert result['uuid'] == '2'

    def test_preserve_highest_centrality_strategy(self):
        config = MergePolicyConfig(
            strategy=MergeStrategy.PRESERVE_HIGHEST_CENTRALITY,
            validate_merged_entity=False,
        )
        merger = EntityMerger(config=config)

        entities = [
            {'uuid': '1', 'name': 'Low Centrality', 'centrality_degree': 0.1},
            {'uuid': '2', 'name': 'High Centrality', 'centrality_degree': 0.9},
        ]

        result = merger.merge_entities(entities)
        # Should preserve entity with highest centrality
        assert result['uuid'] == '2'
