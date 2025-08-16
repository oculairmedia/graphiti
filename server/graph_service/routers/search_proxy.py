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
# Use the container name since they're on the same Docker network
RUST_SEARCH_URL = "http://graphiti-search-rs:3004"

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
        # Generate embedding for the query
        query_vector = await generate_embedding(query.query)
        
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
                    "search_methods": ["fulltext", "similarity"],
                    "reranker": "rrf",
                    "bfs_max_depth": 2,
                    "sim_min_score": 0.0,
                    "mmr_lambda": 0.5
                },
                "node_config": {
                    "enabled": True,
                    "limit": query.max_facts,
                    "search_methods": ["fulltext", "similarity"],
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
        
        # Add query vector if generated
        if query_vector:
            rust_request["query_vector"] = query_vector
            logger.info(f"Generated embedding with {len(query_vector)} dimensions")
        else:
            logger.warning("Failed to generate embedding for query")
        
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