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

import json
import logging
from typing import Any, Optional

import numpy as np
from pydantic import BaseModel, Field

from graphiti_core.driver.driver import GraphDriver
from graphiti_core.llm_client.client import LLMClient
from graphiti_core.relevance.models import (
    MemoryFeedback,
    RelevanceScore,
    ScoringConfig,
)
from graphiti_core.utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)


class ScoringContext(BaseModel):
    """Context for scoring a memory's relevance."""
    
    original_query: str = Field(description="Original user query")
    decomposed_query: Optional[str] = Field(default=None, description="Decomposed query sent to Graphiti")
    memory_content: str = Field(description="Content of the memory being scored")
    memory_id: str = Field(description="ID of the memory")
    agent_response: Optional[str] = Field(default=None, description="Agent's response to the user")
    additional_context: dict[str, Any] = Field(default_factory=dict)


class RelevanceScorer:
    """Handles relevance scoring for memories in Graphiti."""
    
    def __init__(
        self,
        driver: GraphDriver,
        llm_client: Optional[LLMClient] = None,
        config: Optional[ScoringConfig] = None
    ):
        self.driver = driver
        self.llm_client = llm_client
        self.config = config or ScoringConfig()
        
    async def score_memory_llm(self, context: ScoringContext) -> float:
        """Score a memory's relevance using LLM evaluation."""
        if not self.llm_client:
            raise ValueError("LLM client required for LLM-based scoring")
            
        prompt = self._build_scoring_prompt(context)
        
        try:
            # Use structured output if available
            response = await self.llm_client.generate_response(
                messages=[
                    {
                        "role": "system",
                        "content": "You are a relevance scoring system. Score how relevant a memory is to a query on a scale of 0 to 1."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                response_model={
                    "type": "object",
                    "properties": {
                        "relevance_score": {
                            "type": "number",
                            "minimum": 0,
                            "maximum": 1,
                            "description": "Relevance score between 0 and 1"
                        },
                        "reasoning": {
                            "type": "string",
                            "description": "Brief explanation of the score"
                        }
                    },
                    "required": ["relevance_score"]
                }
            )
            
            # Parse response
            if isinstance(response, str):
                result = json.loads(response)
            else:
                result = response
                
            score = float(result.get("relevance_score", 0.5))
            logger.debug(f"LLM scored memory {context.memory_id}: {score} - {result.get('reasoning', '')}")
            
            return score
            
        except Exception as e:
            logger.error(f"Error in LLM scoring: {e}")
            # Fallback to neutral score on error
            return 0.5
    
    def _build_scoring_prompt(self, context: ScoringContext) -> str:
        """Build the prompt for LLM-based scoring."""
        prompt_parts = [
            f"Original Query: {context.original_query}",
            f"\nMemory Content: {context.memory_content}",
        ]
        
        if context.decomposed_query:
            prompt_parts.append(f"\nDecomposed Query: {context.decomposed_query}")
            
        if context.agent_response:
            prompt_parts.append(f"\nAgent Response: {context.agent_response}")
            
        prompt_parts.append(
            "\n\nBased on the above information, rate how relevant this memory is to answering the original query."
            "\nConsider:"
            "\n- Direct relevance to the query topic"
            "\n- Usefulness of the information provided"
            "\n- Whether the memory was likely used in the response"
            "\n\nReturn a relevance score between 0 (completely irrelevant) and 1 (highly relevant)."
        )
        
        return "\n".join(prompt_parts)
    
    async def score_memory_heuristic(self, context: ScoringContext) -> float:
        """Score a memory's relevance using heuristic methods."""
        score = 0.5  # Start with neutral score
        
        # Simple keyword matching
        query_words = set(context.original_query.lower().split())
        memory_words = set(context.memory_content.lower().split())
        
        # Calculate Jaccard similarity
        intersection = query_words.intersection(memory_words)
        union = query_words.union(memory_words)
        
        if union:
            keyword_score = len(intersection) / len(union)
            score = 0.3 + (0.4 * keyword_score)  # Scale to 0.3-0.7 range
            
        # Boost score if memory appears in response
        if context.agent_response and context.memory_content[:50] in context.agent_response:
            score = min(1.0, score + 0.2)
            
        logger.debug(f"Heuristic scored memory {context.memory_id}: {score}")
        return score
    
    async def score_memory(
        self, 
        context: ScoringContext,
        method: str = "hybrid"
    ) -> RelevanceScore:
        """Score a memory using the specified method."""
        score_value = 0.5
        
        if method == "llm" and self.config.enable_llm_scoring:
            score_value = await self.score_memory_llm(context)
        elif method == "heuristic" and self.config.enable_heuristic_scoring:
            score_value = await self.score_memory_heuristic(context)
        elif method == "hybrid":
            scores = []
            if self.config.enable_llm_scoring and self.llm_client:
                scores.append(await self.score_memory_llm(context))
            if self.config.enable_heuristic_scoring:
                scores.append(await self.score_memory_heuristic(context))
            
            if scores:
                score_value = np.mean(scores)
        
        return RelevanceScore(
            memory_id=context.memory_id,
            score=score_value,
            query_id=context.additional_context.get("query_id"),
            scoring_method=method,
            metadata={
                "original_query": context.original_query,
                "has_response": context.agent_response is not None
            }
        )
    
    async def apply_reciprocal_rank_fusion(
        self,
        rankings: dict[str, list[str]],
        k: Optional[int] = None
    ) -> list[tuple[str, float]]:
        """
        Apply Reciprocal Rank Fusion to combine multiple rankings.
        
        Args:
            rankings: Dict mapping ranking source to ordered list of IDs
            k: RRF parameter (default from config)
            
        Returns:
            List of (memory_id, fused_score) tuples ordered by score
        """
        k = k or self.config.rrf_k
        rrf_scores = {}
        
        for source, ranked_ids in rankings.items():
            for rank, memory_id in enumerate(ranked_ids, 1):
                if memory_id not in rrf_scores:
                    rrf_scores[memory_id] = 0.0
                rrf_scores[memory_id] += 1.0 / (k + rank)
        
        # Sort by RRF score
        sorted_results = sorted(
            rrf_scores.items(),
            key=lambda x: x[1],
            reverse=True
        )
        
        return sorted_results
    
    async def combine_scores(
        self,
        memory_id: str,
        semantic_score: Optional[float] = None,
        keyword_score: Optional[float] = None,
        graph_score: Optional[float] = None,
        historical_score: Optional[float] = None
    ) -> float:
        """
        Combine multiple score sources using weighted average.
        
        Args:
            memory_id: ID of the memory
            semantic_score: Score from embedding similarity
            keyword_score: Score from BM25/keyword search
            graph_score: Score from graph traversal
            historical_score: Historical relevance score
            
        Returns:
            Combined score between 0 and 1
        """
        scores = []
        weights = []
        
        if semantic_score is not None:
            scores.append(semantic_score)
            weights.append(self.config.semantic_weight)
            
        if keyword_score is not None:
            scores.append(keyword_score)
            weights.append(self.config.keyword_weight)
            
        if graph_score is not None:
            scores.append(graph_score)
            weights.append(self.config.graph_weight)
            
        if historical_score is not None:
            scores.append(historical_score)
            weights.append(self.config.historical_weight)
        
        if not scores:
            return 0.5  # Neutral score if no inputs
        
        # Normalize weights
        total_weight = sum(weights)
        if total_weight > 0:
            weights = [w / total_weight for w in weights]
        else:
            weights = [1.0 / len(scores)] * len(scores)
        
        # Calculate weighted average
        combined = sum(s * w for s, w in zip(scores, weights))
        
        return min(1.0, max(0.0, combined))
    
    async def update_memory_feedback(
        self,
        memory_id: str,
        score: RelevanceScore
    ) -> MemoryFeedback:
        """Update or create feedback for a memory in the database."""
        # Load existing feedback or create new
        feedback = await self._load_feedback(memory_id)
        if not feedback:
            feedback = MemoryFeedback(memory_id=memory_id)
        
        # Add new score
        feedback.add_score(score)
        feedback.last_accessed = utc_now()
        feedback.usage_count += 1
        
        # Apply decay if enabled
        if self.config.enable_decay:
            feedback.apply_decay(self.config.half_life_days)
        
        # Save to database
        await self._save_feedback(feedback)
        
        return feedback
    
    async def _load_feedback(self, memory_id: str) -> Optional[MemoryFeedback]:
        """Load feedback data from the database."""
        query = """
        MATCH (n {uuid: $memory_id})
        RETURN 
            n.relevance_scores AS relevance_scores,
            n.avg_relevance AS avg_relevance,
            n.usage_count AS usage_count,
            n.successful_uses AS successful_uses,
            n.last_accessed AS last_accessed,
            n.last_scored AS last_scored,
            n.decay_factor AS decay_factor,
            n.query_embeddings AS query_embeddings
        """
        
        records, _, _ = await self.driver.execute_query(
            query,
            memory_id=memory_id,
            routing_='r'
        )
        
        if not records or not records[0].get("avg_relevance"):
            return None
        
        record = records[0]
        
        # Deserialize relevance scores
        scores_data = record.get("relevance_scores", [])
        if isinstance(scores_data, str):
            scores_data = json.loads(scores_data)
        
        relevance_scores = [RelevanceScore(**score) for score in scores_data]
        
        return MemoryFeedback(
            memory_id=memory_id,
            relevance_scores=relevance_scores,
            avg_relevance=record.get("avg_relevance", 0.0),
            usage_count=record.get("usage_count", 0),
            successful_uses=record.get("successful_uses", 0),
            last_accessed=record.get("last_accessed"),
            last_scored=record.get("last_scored"),
            decay_factor=record.get("decay_factor", 1.0),
            query_embeddings=record.get("query_embeddings", [])
        )
    
    async def _save_feedback(self, feedback: MemoryFeedback):
        """Save feedback data to the database."""
        # Serialize relevance scores
        scores_data = [score.model_dump(mode='json') for score in feedback.relevance_scores[-100:]]  # Keep last 100 scores
        
        query = """
        MATCH (n {uuid: $memory_id})
        SET 
            n.relevance_scores = $relevance_scores,
            n.avg_relevance = $avg_relevance,
            n.usage_count = $usage_count,
            n.successful_uses = $successful_uses,
            n.last_accessed = $last_accessed,
            n.last_scored = $last_scored,
            n.decay_factor = $decay_factor,
            n.query_embeddings = $query_embeddings
        """
        
        await self.driver.execute_query(
            query,
            memory_id=feedback.memory_id,
            relevance_scores=json.dumps(scores_data),
            avg_relevance=feedback.avg_relevance,
            usage_count=feedback.usage_count,
            successful_uses=feedback.successful_uses,
            last_accessed=feedback.last_accessed,
            last_scored=feedback.last_scored,
            decay_factor=feedback.decay_factor,
            query_embeddings=feedback.query_embeddings[-50:]  # Keep last 50 query embeddings
        )