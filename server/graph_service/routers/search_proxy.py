"""
Proxy router for search requests to Rust search service.
Forwards requests from Python API to graphiti-search-rs service.
"""

import httpx
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import os
import logging

router = APIRouter(tags=["search"])
logger = logging.getLogger(__name__)

# Rust search service URL
# Use environment variable or fallback to localhost for development
RUST_SEARCH_URL = os.getenv('RUST_SEARCH_URL', 'http://localhost:3004')

class SearchQuery(BaseModel):
    """Search query matching the expected format"""
    query: str = Field(description="Search query text")
    max_facts: int = Field(default=10, description="Maximum number of facts to return")
    group_ids: Optional[List[str]] = Field(default=None, description="Group IDs to filter by")

class FactResult(BaseModel):
    """Individual fact from search results"""
    uuid: str
    name: str
    fact: str
    valid_at: Optional[str] = None
    invalid_at: Optional[str] = None
    created_at: Optional[str] = None
    expired_at: Optional[str] = None

class SearchResults(BaseModel):
    """Search results response"""
    facts: List[FactResult]

class NodeSearchQuery(BaseModel):
    """Node search query matching frontend expectations"""
    query: str = Field(description="Search query text")
    max_nodes: int = Field(default=10, description="Maximum number of nodes to return")
    group_ids: Optional[List[str]] = Field(default=None, description="Group IDs to filter by")
    center_node_uuid: Optional[str] = Field(default=None, description="Center node UUID for graph search")
    entity: Optional[str] = Field(default=None, description="Entity type filter")

class NodeResult(BaseModel):
    """Node result matching frontend expectations"""
    uuid: str
    name: str
    summary: Optional[str] = None
    labels: List[str] = Field(default_factory=list)
    group_id: Optional[str] = None
    created_at: Optional[str] = None
    attributes: Dict[str, Any] = Field(default_factory=dict)

class NodeSearchResults(BaseModel):
    """Node search results response"""
    nodes: List[NodeResult]

class EdgeResult(BaseModel):
    """Edge result matching frontend expectations"""
    uuid: str
    name: str
    fact: str
    valid_at: Optional[str] = None
    invalid_at: Optional[str] = None
    created_at: Optional[str] = None
    expired_at: Optional[str] = None

class EdgesByNodeResponse(BaseModel):
    """Edges by node response matching frontend expectations"""
    edges: List[EdgeResult]
    source_edges: List[EdgeResult]
    target_edges: List[EdgeResult]

async def generate_embedding(text: str) -> Optional[List[float]]:
    """Generate embedding for the query text using Ollama"""
    try:
        ollama_url = os.getenv('OLLAMA_BASE_URL', 'http://192.168.50.80:11434/v1')
        ollama_model = os.getenv('OLLAMA_EMBEDDING_MODEL', 'mxbai-embed-large:latest')
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{ollama_url}/embeddings",
                json={
                    "input": text,
                    "model": ollama_model
                },
                headers={"Authorization": "Bearer ollama"}
            )
            
            if response.status_code == 200:
                result = response.json()
                # Extract embedding from response
                if 'data' in result and len(result['data']) > 0:
                    return result['data'][0]['embedding']
            else:
                logger.warning(f"Failed to generate embedding: {response.status_code}")
                
    except Exception as e:
        logger.error(f"Error generating embedding: {e}")
    
    return None

@router.post('/search', response_model=SearchResults, status_code=status.HTTP_200_OK)
async def search_proxy(query: SearchQuery) -> SearchResults:
    """
    Proxy search requests to Rust search service.
    Transforms the request format to match Rust service expectations.
    """
    try:
        # Don't generate embeddings here - let Rust service handle it
        # The Rust service has Ollama embedding generation built-in
        
        # Transform request to Rust service format with full config
        rust_request = {
            "query": query.query,
            "config": {
                "limit": query.max_facts,
                "reranker_min_score": 0.0,
                "alpha": 0.5,  # Balance between semantic and keyword search
                "edge_config": {
                    "enabled": True,
                    "limit": query.max_facts,
                    "search_methods": ["fulltext", "similarity"],  # Re-enable similarity
                    "reranker": "rrf",
                    "bfs_max_depth": 2,
                    "sim_min_score": 0.0,
                    "mmr_lambda": 0.5
                },
                "node_config": {
                    "enabled": True,
                    "limit": query.max_facts,
                    "search_methods": ["fulltext", "similarity"],  # Re-enable similarity
                    "reranker": "rrf",
                    "bfs_max_depth": 2,
                    "sim_min_score": 0.0,
                    "mmr_lambda": 0.5
                }
            },
            "filters": {}
        }
        
        # Add group filters if provided
        if query.group_ids:
            rust_request["filters"]["group_ids"] = query.group_ids
        
        # Don't add query_vector - let Rust service generate it
        logger.info(f"Forwarding search query to Rust service: {query.query}")
        
        # Forward to Rust service
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{RUST_SEARCH_URL}/search",
                json=rust_request
            )
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Rust search service error: {response.text}"
                )
            
            rust_result = response.json()
            
            # Transform Rust response to API format
            facts = []
            
            # Extract facts from edges
            for edge in rust_result.get("edges", []):
                fact = FactResult(
                    uuid=edge.get("uuid", ""),
                    name=edge.get("name", ""),
                    fact=edge.get("fact", edge.get("name", "")),
                    valid_at=edge.get("valid_at"),
                    invalid_at=edge.get("invalid_at"),
                    created_at=edge.get("created_at"),
                    expired_at=edge.get("expired_at")
                )
                facts.append(fact)
            
            # Also include nodes as facts if no edges found
            if not facts:
                for node in rust_result.get("nodes", []):
                    fact = FactResult(
                        uuid=node.get("uuid", ""),
                        name=node.get("name", ""),
                        fact=node.get("summary", node.get("name", "")),
                        valid_at=node.get("valid_at"),
                        invalid_at=node.get("invalid_at"),
                        created_at=node.get("created_at"),
                        expired_at=None
                    )
                    facts.append(fact)
            
            return SearchResults(facts=facts)
            
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to connect to search service: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search proxy error: {str(e)}"
        )

@router.post('/search/nodes', response_model=NodeSearchResults, status_code=status.HTTP_200_OK)
async def search_nodes(query: NodeSearchQuery) -> NodeSearchResults:
    """
    Search for nodes using the Rust search service.
    Matches the frontend GraphitiClient expectations.
    """
    try:
        # Transform request to Rust service format
        rust_request = {
            "query": query.query,
            "config": {
                "limit": query.max_nodes,
                "reranker_min_score": 0.0,
                "alpha": 0.5,
                "node_config": {
                    "enabled": True,
                    "limit": query.max_nodes,
                    "search_methods": ["fulltext", "similarity"],
                    "reranker": "rrf",
                    "bfs_max_depth": 2,
                    "sim_min_score": 0.0,
                    "mmr_lambda": 0.5
                },
                "edge_config": {
                    "enabled": False,  # Disable edge search for node-only queries
                    "limit": 0,
                    "search_methods": [],
                    "reranker": "rrf",
                    "bfs_max_depth": 2,
                    "sim_min_score": 0.0,
                    "mmr_lambda": 0.5
                }
            },
            "filters": {}
        }
        
        # Add filters if provided
        if query.group_ids:
            rust_request["filters"]["group_ids"] = query.group_ids
        if query.entity:
            rust_request["filters"]["entity_type"] = query.entity
        if query.center_node_uuid:
            rust_request["filters"]["center_node_uuid"] = query.center_node_uuid
        
        logger.info(f"Forwarding node search query to Rust service: {query.query}")
        
        # Forward to Rust service
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{RUST_SEARCH_URL}/search",
                json=rust_request
            )
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Rust search service error: {response.text}"
                )
            
            rust_result = response.json()
            
            # Transform Rust response to frontend format
            nodes = []
            for node in rust_result.get("nodes", []):
                # Extract node_type as a label
                node_type = node.get("node_type", "entity")
                labels = [node_type] if node_type else []
                
                node_result = NodeResult(
                    uuid=node.get("uuid", ""),
                    name=node.get("name", ""),
                    summary=node.get("summary"),
                    labels=labels,
                    group_id=node.get("group_id"),
                    created_at=node.get("created_at"),
                    attributes={}  # Rust doesn't return attributes, use empty dict
                )
                nodes.append(node_result)
            
            return NodeSearchResults(nodes=nodes)
            
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to connect to search service: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Node search error: {str(e)}"
        )

@router.get('/edges/by-node/{node_uuid}', response_model=EdgesByNodeResponse, status_code=status.HTTP_200_OK)
async def get_edges_by_node(node_uuid: str) -> EdgesByNodeResponse:
    """
    Get all edges connected to a specific node.
    Returns edges where the node is either source or target.
    """
    try:
        # Query Rust service for edges
        rust_request = {
            "query": "",  # Empty query for direct UUID lookup
            "config": {
                "limit": 100,
                "edge_config": {
                    "enabled": True,
                    "limit": 100,
                    "search_methods": ["fulltext"],
                    "reranker": "rrf",
                    "bfs_max_depth": 1,
                    "sim_min_score": 0.0,
                    "mmr_lambda": 0.5
                },
                "node_config": {
                    "enabled": False,
                    "limit": 0,
                    "search_methods": [],
                    "reranker": "rrf",
                    "bfs_max_depth": 1,
                    "sim_min_score": 0.0,
                    "mmr_lambda": 0.5
                }
            },
            "filters": {
                "node_uuid": node_uuid
            }
        }
        
        logger.info(f"Fetching edges for node: {node_uuid}")
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{RUST_SEARCH_URL}/search",
                json=rust_request
            )
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Rust search service error: {response.text}"
                )
            
            rust_result = response.json()
            
            # Transform edges to frontend format
            all_edges = []
            source_edges = []
            target_edges = []
            
            for edge in rust_result.get("edges", []):
                edge_result = EdgeResult(
                    uuid=edge.get("uuid", ""),
                    name=edge.get("name", ""),
                    fact=edge.get("fact", ""),
                    valid_at=edge.get("valid_at"),
                    invalid_at=edge.get("invalid_at"),
                    created_at=edge.get("created_at"),
                    expired_at=edge.get("expired_at")
                )
                
                all_edges.append(edge_result)
                
                # Categorize by source/target
                if edge.get("source_node_uuid") == node_uuid:
                    source_edges.append(edge_result)
                elif edge.get("target_node_uuid") == node_uuid:
                    target_edges.append(edge_result)
            
            return EdgesByNodeResponse(
                edges=all_edges,
                source_edges=source_edges,
                target_edges=target_edges
            )
            
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to connect to search service: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching edges: {str(e)}"
        )

@router.patch('/nodes/{node_uuid}/summary', response_model=NodeResult, status_code=status.HTTP_200_OK)
async def update_node_summary(node_uuid: str, summary_update: Dict[str, Any]) -> NodeResult:
    """
    Update the summary of a specific node.
    This endpoint would normally update the node in the database.
    For now, it returns a mock response.
    """
    try:
        summary = summary_update.get("summary", "")
        
        # TODO: Implement actual node update in FalkorDB
        # For now, return a mock response
        logger.info(f"Updating summary for node {node_uuid}: {summary[:50]}...")
        
        # Return mock updated node
        return NodeResult(
            uuid=node_uuid,
            name="Updated Node",
            node_type="entity",
            summary=summary,
            created_at=None,
            group_id=None,
            centrality=None
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating node summary: {str(e)}"
        )