"""
Copyright 2024, Zep Software, Inc.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import asyncio
import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from graphiti_core.relevance import (
    MemoryFeedback,
    RelevanceScore,
    RelevanceScorer,
    ScoringConfig,
)
from graphiti_core.relevance.scorer import ScoringContext
from graphiti_core.utils.datetime_utils import utc_now


class TestRelevanceModels:
    """Test relevance scoring data models."""
    
    def test_relevance_score_creation(self):
        """Test creating a RelevanceScore object."""
        score = RelevanceScore(
            memory_id="test-123",
            score=0.8,
            query_id="query-456",
            scoring_method="llm"
        )
        
        assert score.memory_id == "test-123"
        assert score.score == 0.8
        assert score.query_id == "query-456"
        assert score.scoring_method == "llm"
        assert isinstance(score.timestamp, datetime)
    
    def test_relevance_score_validation(self):
        """Test score validation (0-1 range)."""
        # Valid scores
        RelevanceScore(memory_id="test", score=0.0)
        RelevanceScore(memory_id="test", score=1.0)
        RelevanceScore(memory_id="test", score=0.5)
        
        # Invalid scores should raise validation error
        with pytest.raises(ValueError):
            RelevanceScore(memory_id="test", score=-0.1)
        
        with pytest.raises(ValueError):
            RelevanceScore(memory_id="test", score=1.1)
    
    def test_memory_feedback_add_score(self):
        """Test adding scores to memory feedback."""
        feedback = MemoryFeedback(memory_id="test-123")
        
        # Initial state
        assert feedback.avg_relevance == 0.0
        assert len(feedback.relevance_scores) == 0
        
        # Add first score
        score1 = RelevanceScore(memory_id="test-123", score=0.8)
        feedback.add_score(score1)
        
        assert len(feedback.relevance_scores) == 1
        assert feedback.avg_relevance == 0.8
        assert feedback.last_scored == score1.timestamp
        
        # Add second score (test exponential moving average)
        score2 = RelevanceScore(memory_id="test-123", score=0.6)
        feedback.add_score(score2)
        
        assert len(feedback.relevance_scores) == 2
        # EMA with alpha=0.3: 0.3 * 0.6 + 0.7 * 0.8 = 0.74
        assert abs(feedback.avg_relevance - 0.74) < 0.01
    
    def test_memory_feedback_decay(self):
        """Test time-based decay of relevance scores."""
        feedback = MemoryFeedback(
            memory_id="test-123",
            avg_relevance=0.8,
            last_accessed=utc_now() - timedelta(days=30)
        )
        
        # Apply decay with 30-day half-life
        feedback.apply_decay(half_life_days=30)
        
        # After one half-life, score should be ~0.5 of original
        assert abs(feedback.decay_factor - 0.5) < 0.01
        assert abs(feedback.get_effective_score() - 0.4) < 0.01
    
    def test_scoring_config_defaults(self):
        """Test default scoring configuration."""
        config = ScoringConfig()
        
        assert config.enable_llm_scoring is True
        assert config.enable_heuristic_scoring is True
        assert config.enable_decay is True
        assert config.half_life_days == 30.0
        assert config.min_relevance_threshold == 0.3
        assert config.high_relevance_threshold == 0.7
        assert config.rrf_k == 60


class TestRelevanceScorer:
    """Test RelevanceScorer functionality."""
    
    @pytest.fixture
    def mock_driver(self):
        """Create a mock graph driver."""
        driver = AsyncMock()
        driver.execute_query = AsyncMock()
        return driver
    
    @pytest.fixture
    def mock_llm_client(self):
        """Create a mock LLM client."""
        client = AsyncMock()
        client.generate_response = AsyncMock()
        return client
    
    @pytest.fixture
    def scorer(self, mock_driver, mock_llm_client):
        """Create a RelevanceScorer instance."""
        config = ScoringConfig()
        return RelevanceScorer(mock_driver, mock_llm_client, config)
    
    @pytest.mark.asyncio
    async def test_score_memory_heuristic(self, scorer):
        """Test heuristic scoring method."""
        context = ScoringContext(
            original_query="What is machine learning?",
            memory_content="Machine learning is a subset of artificial intelligence.",
            memory_id="test-123",
            agent_response="Machine learning is a field of AI that enables computers to learn from data."
        )
        
        score = await scorer.score_memory_heuristic(context)
        
        # Should have moderate score due to keyword overlap
        assert 0.3 <= score <= 0.7
    
    @pytest.mark.asyncio
    async def test_score_memory_llm(self, scorer, mock_llm_client):
        """Test LLM-based scoring method."""
        # Mock LLM response
        mock_llm_client.generate_response.return_value = json.dumps({
            "relevance_score": 0.85,
            "reasoning": "Highly relevant to the query"
        })
        
        context = ScoringContext(
            original_query="What is machine learning?",
            memory_content="Machine learning is a subset of artificial intelligence.",
            memory_id="test-123"
        )
        
        score = await scorer.score_memory_llm(context)
        
        assert score == 0.85
        mock_llm_client.generate_response.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_score_memory_hybrid(self, scorer, mock_llm_client):
        """Test hybrid scoring (LLM + heuristic)."""
        # Mock LLM response
        mock_llm_client.generate_response.return_value = json.dumps({
            "relevance_score": 0.8,
            "reasoning": "Relevant"
        })
        
        context = ScoringContext(
            original_query="What is machine learning?",
            memory_content="Machine learning is a subset of artificial intelligence.",
            memory_id="test-123"
        )
        
        result = await scorer.score_memory(context, method="hybrid")
        
        assert isinstance(result, RelevanceScore)
        assert result.memory_id == "test-123"
        assert 0.0 <= result.score <= 1.0
        assert result.scoring_method == "hybrid"
    
    @pytest.mark.asyncio
    async def test_reciprocal_rank_fusion(self, scorer):
        """Test RRF combination of rankings."""
        rankings = {
            "semantic": ["mem1", "mem2", "mem3"],
            "keyword": ["mem2", "mem1", "mem4"],
            "graph": ["mem3", "mem4", "mem1"]
        }
        
        results = await scorer.apply_reciprocal_rank_fusion(rankings, k=60)
        
        # Check results structure
        assert len(results) == 4
        assert all(isinstance(r, tuple) for r in results)
        assert all(len(r) == 2 for r in results)
        
        # Check that mem1 (appears in all 3) has high score
        mem_scores = dict(results)
        assert "mem1" in mem_scores
        assert mem_scores["mem1"] > 0
    
    @pytest.mark.asyncio
    async def test_combine_scores(self, scorer):
        """Test weighted combination of multiple scores."""
        combined = await scorer.combine_scores(
            memory_id="test-123",
            semantic_score=0.8,
            keyword_score=0.6,
            graph_score=0.7,
            historical_score=0.9
        )
        
        # Check combined score is in valid range
        assert 0.0 <= combined <= 1.0
        
        # Check it's a weighted average
        # Default weights: 0.4, 0.3, 0.2, 0.1
        expected = (0.8 * 0.4 + 0.6 * 0.3 + 0.7 * 0.2 + 0.9 * 0.1)
        assert abs(combined - expected) < 0.01
    
    @pytest.mark.asyncio
    async def test_update_memory_feedback(self, scorer, mock_driver):
        """Test updating memory feedback in database."""
        # Mock database responses
        mock_driver.execute_query.return_value = ([], None, None)
        
        score = RelevanceScore(
            memory_id="test-123",
            score=0.75,
            scoring_method="manual"
        )
        
        feedback = await scorer.update_memory_feedback("test-123", score)
        
        assert feedback.memory_id == "test-123"
        assert len(feedback.relevance_scores) == 1
        assert feedback.avg_relevance == 0.75
        assert feedback.usage_count == 1
        
        # Check database was called
        assert mock_driver.execute_query.call_count >= 1
    
    @pytest.mark.asyncio
    async def test_load_feedback_existing(self, scorer, mock_driver):
        """Test loading existing feedback from database."""
        # Mock database response with existing feedback
        mock_driver.execute_query.return_value = (
            [{
                "relevance_scores": json.dumps([
                    {"memory_id": "test-123", "score": 0.7, "timestamp": "2024-01-01T00:00:00"}
                ]),
                "avg_relevance": 0.7,
                "usage_count": 5,
                "successful_uses": 3,
                "last_accessed": datetime(2024, 1, 1),
                "last_scored": datetime(2024, 1, 1),
                "decay_factor": 0.9,
                "query_embeddings": []
            }],
            None,
            None
        )
        
        feedback = await scorer._load_feedback("test-123")
        
        assert feedback is not None
        assert feedback.memory_id == "test-123"
        assert feedback.avg_relevance == 0.7
        assert feedback.usage_count == 5
        assert feedback.successful_uses == 3
    
    @pytest.mark.asyncio
    async def test_load_feedback_not_found(self, scorer, mock_driver):
        """Test loading feedback when none exists."""
        # Mock empty database response
        mock_driver.execute_query.return_value = ([], None, None)
        
        feedback = await scorer._load_feedback("test-123")
        
        assert feedback is None


class TestScoringIntegration:
    """Integration tests for the scoring system."""
    
    @pytest.mark.asyncio
    async def test_end_to_end_scoring_workflow(self):
        """Test complete scoring workflow."""
        # Create mock components
        mock_driver = AsyncMock()
        mock_driver.execute_query = AsyncMock(return_value=([], None, None))
        
        mock_llm = AsyncMock()
        mock_llm.generate_response = AsyncMock(return_value=json.dumps({
            "relevance_score": 0.75,
            "reasoning": "Relevant content"
        }))
        
        # Create scorer
        config = ScoringConfig(
            enable_llm_scoring=True,
            enable_heuristic_scoring=True,
            enable_decay=True,
            half_life_days=30
        )
        scorer = RelevanceScorer(mock_driver, mock_llm, config)
        
        # Create scoring context
        context = ScoringContext(
            original_query="Tell me about Python programming",
            memory_content="Python is a high-level programming language known for its simplicity.",
            memory_id="mem-789",
            agent_response="Python is a versatile programming language used for web development, data science, and more."
        )
        
        # Score the memory
        score = await scorer.score_memory(context, method="hybrid")
        
        # Update feedback
        feedback = await scorer.update_memory_feedback("mem-789", score)
        
        # Verify results
        assert feedback.memory_id == "mem-789"
        assert len(feedback.relevance_scores) == 1
        assert 0.0 <= feedback.avg_relevance <= 1.0
        assert feedback.usage_count == 1
        
        # Apply decay after 15 days
        feedback.last_accessed = utc_now() - timedelta(days=15)
        feedback.apply_decay(half_life_days=30)
        
        # Check decay was applied
        assert feedback.decay_factor < 1.0
        assert feedback.get_effective_score() < feedback.avg_relevance


@pytest.mark.asyncio
async def test_bulk_operations():
    """Test bulk scoring operations."""
    mock_driver = AsyncMock()
    mock_driver.execute_query = AsyncMock()
    
    config = ScoringConfig(batch_size=5)
    scorer = RelevanceScorer(mock_driver, None, config)
    
    # Test RRF with many memories
    rankings = {
        "semantic": [f"mem{i}" for i in range(100)],
        "keyword": [f"mem{i}" for i in range(99, -1, -1)],
    }
    
    results = await scorer.apply_reciprocal_rank_fusion(rankings)
    
    assert len(results) == 100
    assert all(isinstance(r[1], float) for r in results)