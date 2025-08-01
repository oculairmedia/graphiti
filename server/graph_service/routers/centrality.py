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

from typing import Dict, Optional

from fastapi import APIRouter, status
from graphiti_core.utils.maintenance import (
    calculate_all_centralities,
    calculate_betweenness_centrality,
    calculate_degree_centrality,
    calculate_pagerank,
    store_centrality_scores,
)
from pydantic import BaseModel, Field

from graph_service.zep_graphiti import ZepGraphitiDep

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


@router.post('/pagerank', status_code=status.HTTP_200_OK)
async def calculate_pagerank_endpoint(
    request: PageRankRequest,
    graphiti: ZepGraphitiDep,
) -> CentralityResponse:
    """
    Calculate PageRank centrality for all nodes in the graph.
    PageRank measures the importance of nodes based on the link structure.
    """
    scores = await calculate_pagerank(
        driver=graphiti.driver,
        damping_factor=request.damping_factor,
        iterations=request.iterations,
        group_id=request.group_id,
    )

    if request.store_results:
        formatted_scores = {uuid: {'pagerank': score} for uuid, score in scores.items()}
        await store_centrality_scores(graphiti.driver, formatted_scores)

    return CentralityResponse(
        scores=scores,
        metric='pagerank',
        nodes_processed=len(scores),
    )


@router.post('/degree', status_code=status.HTTP_200_OK)
async def calculate_degree_endpoint(
    request: DegreeRequest,
    graphiti: ZepGraphitiDep,
) -> CentralityResponse:
    """
    Calculate degree centrality (number of connections) for all nodes.
    Degree centrality is the simplest measure of node importance.
    """
    degrees = await calculate_degree_centrality(
        driver=graphiti.driver,
        direction=request.direction,
        group_id=request.group_id,
    )

    # Flatten the degree dictionary for response
    scores = {}
    for uuid, degree_dict in degrees.items():
        if request.direction == 'both':
            scores[uuid] = float(degree_dict.get('total', 0))
        elif request.direction == 'in':
            scores[uuid] = float(degree_dict.get('in', 0))
        else:  # out
            scores[uuid] = float(degree_dict.get('out', 0))

    if request.store_results:
        formatted_scores = {uuid: {'degree': score} for uuid, score in scores.items()}
        await store_centrality_scores(graphiti.driver, formatted_scores)

    return CentralityResponse(
        scores=scores,
        metric=f'degree_{request.direction}',
        nodes_processed=len(scores),
    )


@router.post('/betweenness', status_code=status.HTTP_200_OK)
async def calculate_betweenness_endpoint(
    request: BetweennessRequest,
    graphiti: ZepGraphitiDep,
) -> CentralityResponse:
    """
    Calculate betweenness centrality using sampling for efficiency.
    Betweenness measures how often a node appears on shortest paths between other nodes.
    """
    scores = await calculate_betweenness_centrality(
        driver=graphiti.driver,
        sample_size=request.sample_size,
        group_id=request.group_id,
    )

    if request.store_results:
        formatted_scores = {uuid: {'betweenness': score} for uuid, score in scores.items()}
        await store_centrality_scores(graphiti.driver, formatted_scores)

    return CentralityResponse(
        scores=scores,
        metric='betweenness',
        nodes_processed=len(scores),
    )


@router.post('/all', status_code=status.HTTP_200_OK)
async def calculate_all_centralities_endpoint(
    request: AllCentralitiesRequest,
    graphiti: ZepGraphitiDep,
) -> AllCentralitiesResponse:
    """
    Calculate all centrality metrics and store them.
    This includes PageRank, degree centrality, betweenness centrality, and a composite importance score.
    """
    scores = await calculate_all_centralities(
        driver=graphiti.driver,
        group_id=request.group_id,
        store_results=request.store_results,
    )

    return AllCentralitiesResponse(
        scores=scores,
        nodes_processed=len(scores),
    )
