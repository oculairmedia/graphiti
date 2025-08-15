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

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from graph_service.dto.common import SuccessResponse
from graph_service.factories import create_llm_client
from graph_service.zep_graphiti import ZepGraphitiDep
from graphiti_core.driver.driver import GraphDriver
from graphiti_core.llm_client.client import LLMClient
from graphiti_core.relevance import (
    MemoryFeedback,
    RelevanceScore,
    RelevanceScorer,
    ScoringConfig,
)
from graphiti_core.relevance.models import (
    BulkRecalculateRequest,
    RelevanceFeedbackRequest,
)
from graphiti_core.relevance.scorer import ScoringContext

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/feedback", tags=["relevance"])


class RelevanceFeedbackResponse(BaseModel):
    """Response for relevance feedback submission."""
    
    status: str = Field(default="success")
    processed_count: int = Field(description="Number of memories processed")
    feedbacks: list[MemoryFeedback] = Field(description="Updated feedback data")


class MemoryWithScoreResponse(BaseModel):
    """Response for memory retrieval with scores."""
    
    memory_id: str
    content: str
    relevance_score: float
    usage_count: int
    last_accessed: Optional[str]
    metadata: dict[str, Any] = Field(default_factory=dict)


class BulkRecalculateResponse(BaseModel):
    """Response for bulk recalculation."""
    
    status: str = Field(default="success")
    processed_count: int
    failed_count: int = 0
    results: list[dict[str, Any]] = Field(default_factory=list)


# Global scorer instance (initialized on first use)
_scorer: Optional[RelevanceScorer] = None


async def get_scorer(
    graphiti: ZepGraphitiDep,
    llm_client: Optional[LLMClient] = Depends(create_llm_client)
) -> RelevanceScorer:
    """Get or create the relevance scorer instance."""
    global _scorer
    if _scorer is None:
        driver = graphiti.driver
        config = ScoringConfig()  # Load from environment or config file
        _scorer = RelevanceScorer(driver, llm_client, config)
    return _scorer


@router.post("/relevance", response_model=RelevanceFeedbackResponse)
async def submit_relevance_feedback(
    request: RelevanceFeedbackRequest,
    scorer: RelevanceScorer = Depends(get_scorer)
) -> RelevanceFeedbackResponse:
    """
    Submit relevance feedback for memories retrieved during a query.
    
    This endpoint allows submitting manual or automated relevance scores
    for memories that were retrieved during a search operation.
    """
    try:
        feedbacks = []
        
        for memory_id, score_value in request.memory_scores.items():
            # Create relevance score
            score = RelevanceScore(
                memory_id=memory_id,
                score=score_value,
                query_id=request.query_id,
                scoring_method="manual",
                metadata={
                    "query_text": request.query_text,
                    "has_response": request.response_text is not None
                }
            )
            
            # Update feedback in database
            feedback = await scorer.update_memory_feedback(memory_id, score)
            feedbacks.append(feedback)
        
        return RelevanceFeedbackResponse(
            status="success",
            processed_count=len(feedbacks),
            feedbacks=feedbacks
        )
        
    except Exception as e:
        logger.error(f"Error submitting relevance feedback: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/relevance/auto-score", response_model=RelevanceFeedbackResponse)
async def auto_score_memories(
    query_id: str,
    original_query: str,
    memory_contents: dict[str, str],  # memory_id -> content
    agent_response: Optional[str] = None,
    decomposed_query: Optional[str] = None,
    scorer: RelevanceScorer = Depends(get_scorer)
) -> RelevanceFeedbackResponse:
    """
    Automatically score memories using LLM and heuristic methods.
    
    This endpoint triggers automatic scoring of memories based on
    the query context and agent response.
    """
    try:
        feedbacks = []
        
        for memory_id, memory_content in memory_contents.items():
            # Create scoring context
            context = ScoringContext(
                original_query=original_query,
                decomposed_query=decomposed_query,
                memory_content=memory_content,
                memory_id=memory_id,
                agent_response=agent_response,
                additional_context={"query_id": query_id}
            )
            
            # Score using hybrid method
            score = await scorer.score_memory(context, method="hybrid")
            
            # Update feedback
            feedback = await scorer.update_memory_feedback(memory_id, score)
            feedbacks.append(feedback)
        
        return RelevanceFeedbackResponse(
            status="success",
            processed_count=len(feedbacks),
            feedbacks=feedbacks
        )
        
    except Exception as e:
        logger.error(f"Error in auto-scoring: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/memories", response_model=list[MemoryWithScoreResponse])
async def get_memories_with_scores(
    group_id: str,
    graphiti: ZepGraphitiDep,
    include_scores: bool = Query(default=True),
    min_relevance: Optional[float] = Query(default=None, ge=0.0, le=1.0),
    limit: Optional[int] = Query(default=50, ge=1, le=1000)
) -> list[MemoryWithScoreResponse]:
    """
    Retrieve memories with their relevance scores.
    
    This endpoint returns memories along with their relevance scoring metadata,
    allowing filtering by minimum relevance threshold.
    """
    try:
        driver = graphiti.driver
        
        # Build query based on parameters
        query_parts = ["MATCH (n:Entity {group_id: $group_id})"]
        
        if include_scores and min_relevance is not None:
            query_parts.append("WHERE n.avg_relevance >= $min_relevance")
        
        query_parts.extend([
            "RETURN n.uuid AS memory_id,",
            "n.name AS content,",
            "n.avg_relevance AS relevance_score,",
            "n.usage_count AS usage_count,",
            "n.last_accessed AS last_accessed,",
            "properties(n) AS metadata",
            "ORDER BY n.avg_relevance DESC" if include_scores else "ORDER BY n.created_at DESC",
            "LIMIT $limit"
        ])
        
        query = "\n".join(query_parts)
        
        records, _, _ = await driver.execute_query(
            query,
            group_id=group_id,
            min_relevance=min_relevance,
            limit=limit,
            routing_='r'
        )
        
        # Format response
        memories = []
        for record in records:
            memories.append(MemoryWithScoreResponse(
                memory_id=record["memory_id"],
                content=record["content"],
                relevance_score=record.get("relevance_score", 0.0),
                usage_count=record.get("usage_count", 0),
                last_accessed=str(record.get("last_accessed")) if record.get("last_accessed") else None,
                metadata=record.get("metadata", {})
            ))
        
        return memories
        
    except Exception as e:
        logger.error(f"Error retrieving memories with scores: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/recalculate", response_model=BulkRecalculateResponse)
async def bulk_recalculate_scores(
    request: BulkRecalculateRequest,
    graphiti: ZepGraphitiDep,
    scorer: RelevanceScorer = Depends(get_scorer)
) -> BulkRecalculateResponse:
    """
    Bulk recalculate relevance scores for multiple memories.
    
    This endpoint allows recalculating scores for a set of memories
    using specified methods (LLM, heuristic, or hybrid).
    """
    try:
        driver = graphiti.driver
        results = []
        failed_count = 0
        
        # Get memory IDs to process
        memory_ids = request.memory_ids
        if not memory_ids and request.group_id:
            # Get all memory IDs from the group
            query = """
            MATCH (n:Entity {group_id: $group_id})
            RETURN n.uuid AS memory_id
            """
            records, _, _ = await driver.execute_query(
                query,
                group_id=request.group_id,
                routing_='r'
            )
            memory_ids = [r["memory_id"] for r in records]
        
        if not memory_ids:
            return BulkRecalculateResponse(
                status="no_memories",
                processed_count=0,
                failed_count=0,
                results=[]
            )
        
        # Process each memory
        for memory_id in memory_ids:
            try:
                # Load existing feedback
                feedback = await scorer._load_feedback(memory_id)
                
                if not feedback:
                    feedback = MemoryFeedback(memory_id=memory_id)
                
                # Check if force recalculation or needs update
                if request.force or not feedback.last_scored:
                    # For recalculation, we need context - for now, apply decay
                    if scorer.config.enable_decay:
                        feedback.apply_decay(scorer.config.half_life_days)
                    
                    await scorer._save_feedback(feedback)
                    
                    results.append({
                        "memory_id": memory_id,
                        "new_score": feedback.get_effective_score(),
                        "status": "recalculated"
                    })
                else:
                    results.append({
                        "memory_id": memory_id,
                        "score": feedback.get_effective_score(),
                        "status": "skipped"
                    })
                    
            except Exception as e:
                logger.error(f"Failed to recalculate score for {memory_id}: {e}")
                failed_count += 1
                results.append({
                    "memory_id": memory_id,
                    "status": "failed",
                    "error": str(e)
                })
        
        return BulkRecalculateResponse(
            status="success",
            processed_count=len(memory_ids) - failed_count,
            failed_count=failed_count,
            results=results
        )
        
    except Exception as e:
        logger.error(f"Error in bulk recalculation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/rrf", response_model=list[dict[str, Any]])
async def apply_rrf_fusion(
    rankings: dict[str, list[str]],
    k: Optional[int] = Query(default=60, ge=1),
    scorer: RelevanceScorer = Depends(get_scorer)
) -> list[dict[str, Any]]:
    """
    Apply Reciprocal Rank Fusion to combine multiple ranking sources.
    
    This endpoint combines rankings from different retrieval methods
    (semantic, keyword, graph) using RRF algorithm.
    """
    try:
        # Apply RRF
        fused_results = await scorer.apply_reciprocal_rank_fusion(rankings, k)
        
        # Format response
        response = [
            {
                "memory_id": memory_id,
                "rrf_score": score,
                "rank": rank
            }
            for rank, (memory_id, score) in enumerate(fused_results, 1)
        ]
        
        return response
        
    except Exception as e:
        logger.error(f"Error applying RRF: {e}")
        raise HTTPException(status_code=500, detail=str(e))