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

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from graphiti_core.utils.datetime_utils import utc_now


class RelevanceScore(BaseModel):
    """Individual relevance score for a memory/node."""
    
    memory_id: str = Field(description="UUID of the memory/node being scored")
    score: float = Field(ge=0.0, le=1.0, description="Relevance score between 0 and 1")
    query_id: Optional[str] = Field(default=None, description="ID of the query that generated this score")
    timestamp: datetime = Field(default_factory=utc_now, description="When the score was recorded")
    scoring_method: str = Field(default="manual", description="Method used to generate score (manual, llm, heuristic)")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional scoring metadata")


class MemoryFeedback(BaseModel):
    """Comprehensive feedback data for a memory/node."""
    
    memory_id: str = Field(description="UUID of the memory/node")
    relevance_scores: list[RelevanceScore] = Field(
        default_factory=list, 
        description="Historical relevance scores"
    )
    avg_relevance: float = Field(
        default=0.0, 
        ge=0.0, 
        le=1.0, 
        description="Average relevance score"
    )
    usage_count: int = Field(default=0, ge=0, description="Number of times this memory was retrieved")
    successful_uses: int = Field(default=0, ge=0, description="Number of times this memory contributed to successful responses")
    last_accessed: Optional[datetime] = Field(default=None, description="Last time this memory was accessed")
    last_scored: Optional[datetime] = Field(default=None, description="Last time this memory was scored")
    decay_factor: float = Field(default=1.0, ge=0.0, le=1.0, description="Current decay factor applied to score")
    query_embeddings: list[list[float]] = Field(
        default_factory=list, 
        description="Embeddings of queries that retrieved this memory"
    )
    
    def add_score(self, score: RelevanceScore, update_avg: bool = True):
        """Add a new relevance score and optionally update the average."""
        self.relevance_scores.append(score)
        self.last_scored = score.timestamp
        
        if update_avg and self.relevance_scores:
            # Calculate exponential moving average with more weight on recent scores
            alpha = 0.3  # Weight for new score
            if self.avg_relevance == 0.0:
                self.avg_relevance = score.score
            else:
                self.avg_relevance = alpha * score.score + (1 - alpha) * self.avg_relevance
    
    def apply_decay(self, half_life_days: float = 30.0):
        """Apply time-based decay to the relevance score."""
        if not self.last_accessed:
            return
            
        now = utc_now()
        time_delta = (now - self.last_accessed).total_seconds() / 86400  # Convert to days
        
        # Exponential decay formula
        import math
        self.decay_factor = math.exp(-0.693 * time_delta / half_life_days)  # 0.693 = ln(2)
        
    def get_effective_score(self) -> float:
        """Get the effective relevance score after applying decay."""
        return self.avg_relevance * self.decay_factor


class ScoringConfig(BaseModel):
    """Configuration for relevance scoring system."""
    
    # Scoring parameters
    enable_llm_scoring: bool = Field(default=True, description="Enable LLM-based automatic scoring")
    enable_heuristic_scoring: bool = Field(default=True, description="Enable heuristic-based scoring")
    
    # Decay parameters
    enable_decay: bool = Field(default=True, description="Enable time-based score decay")
    half_life_days: float = Field(default=30.0, gt=0, description="Half-life for score decay in days")
    
    # Thresholds
    min_relevance_threshold: float = Field(
        default=0.3, 
        ge=0.0, 
        le=1.0, 
        description="Minimum relevance score to return results"
    )
    high_relevance_threshold: float = Field(
        default=0.7, 
        ge=0.0, 
        le=1.0, 
        description="Threshold for high relevance classification"
    )
    
    # Caching
    cache_high_relevance: bool = Field(default=True, description="Cache memories with high relevance scores")
    cache_size: int = Field(default=1000, gt=0, description="Maximum number of cached memories")
    cache_ttl_seconds: int = Field(default=3600, gt=0, description="Cache TTL in seconds")
    
    # Batch processing
    batch_size: int = Field(default=10, gt=0, description="Batch size for score updates")
    async_scoring: bool = Field(default=True, description="Process scoring asynchronously")
    
    # RRF parameters
    rrf_k: int = Field(default=60, gt=0, description="K parameter for Reciprocal Rank Fusion")
    
    # Weights for different score sources
    semantic_weight: float = Field(default=0.4, ge=0.0, le=1.0, description="Weight for semantic similarity score")
    keyword_weight: float = Field(default=0.3, ge=0.0, le=1.0, description="Weight for keyword (BM25) score")
    graph_weight: float = Field(default=0.2, ge=0.0, le=1.0, description="Weight for graph traversal score")
    historical_weight: float = Field(default=0.1, ge=0.0, le=1.0, description="Weight for historical relevance score")


class RelevanceFeedbackRequest(BaseModel):
    """Request model for submitting relevance feedback."""
    
    query_id: str = Field(description="ID of the query")
    query_text: Optional[str] = Field(default=None, description="Original query text")
    memory_scores: dict[str, float] = Field(
        description="Map of memory IDs to relevance scores (0-1)"
    )
    response_text: Optional[str] = Field(default=None, description="Generated response text")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class BulkRecalculateRequest(BaseModel):
    """Request model for bulk score recalculation."""
    
    memory_ids: Optional[list[str]] = Field(default=None, description="Specific memory IDs to recalculate")
    group_id: Optional[str] = Field(default=None, description="Recalculate all memories in a group")
    recalculation_method: str = Field(
        default="hybrid", 
        pattern="^(llm|heuristic|hybrid)$",
        description="Method for recalculation"
    )
    force: bool = Field(default=False, description="Force recalculation even if recently scored")