"""
Tests for relevance scoring models.

Copyright 2024, Zep Software, Inc.
Licensed under the Apache License, Version 2.0.
"""

import math
from datetime import datetime, timedelta, timezone

import pytest

from graphiti_core.relevance.models import (
    BulkRecalculateRequest,
    MemoryFeedback,
    RelevanceFeedbackRequest,
    RelevanceScore,
    ScoringConfig,
)
from graphiti_core.utils.datetime_utils import utc_now


class TestRelevanceScore:
    """Tests for RelevanceScore model."""

    def test_basic_creation(self):
        score = RelevanceScore(
            memory_id='test-uuid-123',
            score=0.75,
        )
        assert score.memory_id == 'test-uuid-123'
        assert score.score == 0.75

    def test_score_bounds_valid(self):
        # Minimum score
        score_min = RelevanceScore(memory_id='test', score=0.0)
        assert score_min.score == 0.0

        # Maximum score
        score_max = RelevanceScore(memory_id='test', score=1.0)
        assert score_max.score == 1.0

    def test_score_bounds_invalid_low(self):
        with pytest.raises(ValueError):
            RelevanceScore(memory_id='test', score=-0.1)

    def test_score_bounds_invalid_high(self):
        with pytest.raises(ValueError):
            RelevanceScore(memory_id='test', score=1.1)

    def test_default_query_id(self):
        score = RelevanceScore(memory_id='test', score=0.5)
        assert score.query_id is None

    def test_custom_query_id(self):
        score = RelevanceScore(memory_id='test', score=0.5, query_id='query-123')
        assert score.query_id == 'query-123'

    def test_default_timestamp(self):
        before = utc_now()
        score = RelevanceScore(memory_id='test', score=0.5)
        after = utc_now()
        assert before <= score.timestamp <= after

    def test_default_scoring_method(self):
        score = RelevanceScore(memory_id='test', score=0.5)
        assert score.scoring_method == 'manual'

    def test_custom_scoring_method(self):
        score = RelevanceScore(memory_id='test', score=0.5, scoring_method='llm')
        assert score.scoring_method == 'llm'

    def test_default_metadata(self):
        score = RelevanceScore(memory_id='test', score=0.5)
        assert score.metadata == {}

    def test_custom_metadata(self):
        metadata = {'source': 'test', 'confidence': 0.9}
        score = RelevanceScore(memory_id='test', score=0.5, metadata=metadata)
        assert score.metadata == metadata


class TestMemoryFeedback:
    """Tests for MemoryFeedback model."""

    def test_basic_creation(self):
        feedback = MemoryFeedback(memory_id='test-uuid')
        assert feedback.memory_id == 'test-uuid'
        assert feedback.relevance_scores == []
        assert feedback.avg_relevance == 0.0
        assert feedback.usage_count == 0

    def test_default_values(self):
        feedback = MemoryFeedback(memory_id='test')
        assert feedback.successful_uses == 0
        assert feedback.last_accessed is None
        assert feedback.last_scored is None
        assert feedback.decay_factor == 1.0
        assert feedback.query_embeddings == []

    def test_add_score_first_score(self):
        feedback = MemoryFeedback(memory_id='test')
        score = RelevanceScore(memory_id='test', score=0.8)
        feedback.add_score(score)

        assert len(feedback.relevance_scores) == 1
        assert feedback.avg_relevance == 0.8
        assert feedback.last_scored == score.timestamp

    def test_add_score_exponential_moving_average(self):
        feedback = MemoryFeedback(memory_id='test')

        # Add first score
        score1 = RelevanceScore(memory_id='test', score=1.0)
        feedback.add_score(score1)
        assert feedback.avg_relevance == 1.0

        # Add second score - EMA with alpha=0.3
        score2 = RelevanceScore(memory_id='test', score=0.4)
        feedback.add_score(score2)
        # EMA: 0.3 * 0.4 + 0.7 * 1.0 = 0.12 + 0.7 = 0.82
        assert abs(feedback.avg_relevance - 0.82) < 0.001

    def test_add_score_without_update_avg(self):
        feedback = MemoryFeedback(memory_id='test')
        score = RelevanceScore(memory_id='test', score=0.9)
        feedback.add_score(score, update_avg=False)

        assert len(feedback.relevance_scores) == 1
        assert feedback.avg_relevance == 0.0  # Should remain at default

    def test_apply_decay_no_last_accessed(self):
        feedback = MemoryFeedback(memory_id='test')
        feedback.apply_decay(half_life_days=30.0)
        # Should not change decay_factor when last_accessed is None
        assert feedback.decay_factor == 1.0

    def test_apply_decay_with_last_accessed(self):
        feedback = MemoryFeedback(memory_id='test')
        # Set last_accessed to 30 days ago (one half-life)
        feedback.last_accessed = utc_now() - timedelta(days=30)
        feedback.apply_decay(half_life_days=30.0)

        # After one half-life, decay should be approximately 0.5
        assert abs(feedback.decay_factor - 0.5) < 0.05

    def test_apply_decay_recent_access(self):
        feedback = MemoryFeedback(memory_id='test')
        feedback.last_accessed = utc_now() - timedelta(hours=1)
        feedback.apply_decay(half_life_days=30.0)

        # Very recent access should have decay close to 1.0
        assert feedback.decay_factor > 0.99

    def test_get_effective_score(self):
        feedback = MemoryFeedback(memory_id='test')
        feedback.avg_relevance = 0.8
        feedback.decay_factor = 0.5

        effective = feedback.get_effective_score()
        assert effective == 0.4  # 0.8 * 0.5

    def test_get_effective_score_no_decay(self):
        feedback = MemoryFeedback(memory_id='test')
        feedback.avg_relevance = 0.8
        feedback.decay_factor = 1.0

        effective = feedback.get_effective_score()
        assert effective == 0.8


class TestScoringConfig:
    """Tests for ScoringConfig model."""

    def test_default_values(self):
        config = ScoringConfig()
        assert config.enable_llm_scoring is True
        assert config.enable_heuristic_scoring is True
        assert config.enable_decay is True
        assert config.half_life_days == 30.0
        assert config.min_relevance_threshold == 0.3
        assert config.high_relevance_threshold == 0.7
        assert config.cache_high_relevance is True
        assert config.cache_size == 1000
        assert config.cache_ttl_seconds == 3600
        assert config.batch_size == 10
        assert config.async_scoring is True
        assert config.rrf_k == 60

    def test_weight_defaults(self):
        config = ScoringConfig()
        assert config.semantic_weight == 0.4
        assert config.keyword_weight == 0.3
        assert config.graph_weight == 0.2
        assert config.historical_weight == 0.1
        # Total should be approximately 1.0 (floating point comparison)
        total = (
            config.semantic_weight
            + config.keyword_weight
            + config.graph_weight
            + config.historical_weight
        )
        assert abs(total - 1.0) < 0.0001

    def test_custom_thresholds(self):
        config = ScoringConfig(
            min_relevance_threshold=0.5,
            high_relevance_threshold=0.9,
        )
        assert config.min_relevance_threshold == 0.5
        assert config.high_relevance_threshold == 0.9

    def test_threshold_bounds(self):
        # Valid bounds
        config = ScoringConfig(min_relevance_threshold=0.0, high_relevance_threshold=1.0)
        assert config.min_relevance_threshold == 0.0
        assert config.high_relevance_threshold == 1.0

    def test_half_life_positive(self):
        config = ScoringConfig(half_life_days=1.0)
        assert config.half_life_days == 1.0

    def test_half_life_invalid(self):
        with pytest.raises(ValueError):
            ScoringConfig(half_life_days=0.0)

    def test_cache_size_positive(self):
        config = ScoringConfig(cache_size=100)
        assert config.cache_size == 100

    def test_cache_size_invalid(self):
        with pytest.raises(ValueError):
            ScoringConfig(cache_size=0)

    def test_disable_scoring_methods(self):
        config = ScoringConfig(
            enable_llm_scoring=False,
            enable_heuristic_scoring=False,
        )
        assert config.enable_llm_scoring is False
        assert config.enable_heuristic_scoring is False


class TestRelevanceFeedbackRequest:
    """Tests for RelevanceFeedbackRequest model."""

    def test_basic_creation(self):
        request = RelevanceFeedbackRequest(
            query_id='query-123',
            memory_scores={'mem-1': 0.8, 'mem-2': 0.3},
        )
        assert request.query_id == 'query-123'
        assert request.memory_scores == {'mem-1': 0.8, 'mem-2': 0.3}

    def test_optional_fields(self):
        request = RelevanceFeedbackRequest(
            query_id='query-123',
            memory_scores={},
        )
        assert request.query_text is None
        assert request.response_text is None
        assert request.metadata == {}

    def test_with_all_fields(self):
        request = RelevanceFeedbackRequest(
            query_id='query-123',
            query_text='What is the weather?',
            memory_scores={'mem-1': 0.9},
            response_text='The weather is sunny.',
            metadata={'session_id': 'sess-456'},
        )
        assert request.query_text == 'What is the weather?'
        assert request.response_text == 'The weather is sunny.'
        assert request.metadata['session_id'] == 'sess-456'


class TestBulkRecalculateRequest:
    """Tests for BulkRecalculateRequest model."""

    def test_default_values(self):
        request = BulkRecalculateRequest()
        assert request.memory_ids is None
        assert request.group_id is None
        assert request.recalculation_method == 'hybrid'
        assert request.force is False

    def test_with_memory_ids(self):
        request = BulkRecalculateRequest(
            memory_ids=['mem-1', 'mem-2', 'mem-3'],
        )
        assert request.memory_ids == ['mem-1', 'mem-2', 'mem-3']

    def test_with_group_id(self):
        request = BulkRecalculateRequest(group_id='group-123')
        assert request.group_id == 'group-123'

    def test_valid_recalculation_methods(self):
        for method in ['llm', 'heuristic', 'hybrid']:
            request = BulkRecalculateRequest(recalculation_method=method)
            assert request.recalculation_method == method

    def test_invalid_recalculation_method(self):
        with pytest.raises(ValueError):
            BulkRecalculateRequest(recalculation_method='invalid')

    def test_force_flag(self):
        request = BulkRecalculateRequest(force=True)
        assert request.force is True
