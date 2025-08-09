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
from typing import Any, cast, Dict, Optional

import httpx
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from graph_service.config import get_settings
from graph_service.zep_graphiti import ZepGraphitiDep

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/centrality', tags=['centrality'])


class PageRankRequest(BaseModel):
    group_id: Optional[str] = Field(None, description='Optional group ID to filter nodes')
    damping_factor: float = Field(0.85, description='PageRank damping factor')
    iterations: int = Field(20, description='Number of iterations for convergence')
    store_results: bool = Field(True, description='Whether to store results in database')


class DegreeRequest(BaseModel):
    group_id: Optional[str] = Field(None, description='Optional group ID to filter nodes')
    direction: str = Field('both', description="Direction: 'in', 'out', or 'both'")
    store_results: bool = Field(True, description='Whether to store results in database')


class BetweennessRequest(BaseModel):
    group_id: Optional[str] = Field(None, description='Optional group ID to filter nodes')
    sample_size: Optional[int] = Field(None, description='Number of nodes to sample (None for all)')
    store_results: bool = Field(True, description='Whether to store results in database')


class AllCentralitiesRequest(BaseModel):
    group_id: Optional[str] = Field(None, description='Optional group ID to filter nodes')
    store_results: bool = Field(True, description='Whether to store results in database')


class CentralityResponse(BaseModel):
    scores: Dict[str, float] = Field(..., description='Node UUID to score mapping')
    metric: str = Field(..., description='The centrality metric calculated')
    nodes_processed: int = Field(..., description='Number of nodes processed')


class AllCentralitiesResponse(BaseModel):
    scores: Dict[str, Dict[str, float]] = Field(
        ..., description='Node UUID to all centrality scores mapping'
    )
    nodes_processed: int = Field(..., description='Number of nodes processed')


async def call_rust_centrality_service(endpoint: str, request_data: Dict[str, Any]) -> Dict[str, Any]:
    """Helper function to call the Rust centrality service."""
    settings = get_settings()
    
    if not settings.use_rust_centrality:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Rust centrality service is disabled"
        )
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{settings.rust_centrality_url}{endpoint}",
                json=request_data
            )
            
            if response.status_code != 200:
                logger.error(f"Rust centrality service returned {response.status_code}: {response.text}")
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Centrality calculation failed: {response.text}"
                )
            
            return cast(Dict[Any, Any], response.json())
    except httpx.TimeoutException:
        logger.error("Timeout calling Rust centrality service")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Centrality calculation timed out"
        )
    except Exception as e:
        logger.error(f"Error calling Rust centrality service: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Centrality calculation failed: {str(e)}"
        )


@router.post('/pagerank', status_code=status.HTTP_200_OK)
async def calculate_pagerank_endpoint(
    request: PageRankRequest,
    graphiti: ZepGraphitiDep,
) -> CentralityResponse:
    """
    Calculate PageRank centrality for all nodes in the graph.
    PageRank measures the importance of nodes based on the link structure.
    This endpoint proxies to the high-performance Rust centrality service.
    """
    result = await call_rust_centrality_service(
        "/centrality/pagerank",
        request.model_dump()
    )
    
    return CentralityResponse(
        scores=result.get("scores", {}),
        metric='pagerank',
        nodes_processed=result.get("nodes_processed", len(result.get("scores", {})))
    )


@router.post('/degree', status_code=status.HTTP_200_OK)
async def calculate_degree_endpoint(
    request: DegreeRequest,
    graphiti: ZepGraphitiDep,
) -> CentralityResponse:
    """
    Calculate degree centrality (number of connections) for all nodes.
    Degree centrality is the simplest measure of node importance.
    This endpoint proxies to the high-performance Rust centrality service.
    """
    result = await call_rust_centrality_service(
        "/centrality/degree",
        request.model_dump()
    )
    
    # The Rust service returns the appropriate scores based on direction
    scores = result.get("scores", {})
    
    return CentralityResponse(
        scores=scores,
        metric=f'degree_{request.direction}',
        nodes_processed=result.get("nodes_processed", len(scores))
    )


@router.post('/betweenness', status_code=status.HTTP_200_OK)
async def calculate_betweenness_endpoint(
    request: BetweennessRequest,
    graphiti: ZepGraphitiDep,
) -> CentralityResponse:
    """
    Calculate betweenness centrality using sampling for efficiency.
    Betweenness measures how often a node appears on shortest paths between other nodes.
    This endpoint proxies to the high-performance Rust centrality service.
    """
    result = await call_rust_centrality_service(
        "/centrality/betweenness",
        request.model_dump()
    )
    
    return CentralityResponse(
        scores=result.get("scores", {}),
        metric='betweenness',
        nodes_processed=result.get("nodes_processed", len(result.get("scores", {})))
    )


@router.post('/all', status_code=status.HTTP_200_OK)
async def calculate_all_centralities_endpoint(
    request: AllCentralitiesRequest,
    graphiti: ZepGraphitiDep,
) -> AllCentralitiesResponse:
    """
    Calculate all centrality metrics and store them.
    This includes PageRank, degree centrality, betweenness centrality, and a composite importance score.
    This endpoint proxies to the high-performance Rust centrality service.
    """
    result = await call_rust_centrality_service(
        "/centrality/all",
        request.model_dump()
    )
    
    # The Rust service returns scores in the expected format
    return AllCentralitiesResponse(
        scores=result.get("scores", {}),
        nodes_processed=result.get("nodes_processed", len(result.get("scores", {})))
    )