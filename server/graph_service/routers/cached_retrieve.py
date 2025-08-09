"""
Cached version of retrieve router with high-performance optimizations.

This module wraps the retrieve endpoints with caching to dramatically
reduce latency for repeated queries.
"""

import time
import logging
from typing import Any, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, status

from graph_service.dto import (
    EdgesByNodeResponse,
    GetMemoryRequest,
    GetMemoryResponse,
    Message,
    NodeResult,
    NodeSearchQuery,
    NodeSearchResults,
    SearchQuery,
    SearchResults,
)
from graph_service.zep_graphiti import ZepGraphitiDep, get_fact_result_from_edge
from graph_service.async_webhooks import dispatcher
from graph_service.cache import search_cache, embedding_cache

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cached", tags=["cached"])


@router.post('/search', status_code=status.HTTP_200_OK)
async def cached_search(query: SearchQuery, graphiti: ZepGraphitiDep) -> SearchResults:
    """
    Cached version of search endpoint.
    
    Cache key includes: query, group_ids, max_facts
    TTL: 5 minutes (configurable)
    """
    start_time = time.time()
    
    # Check cache
    cache_params = {"max_facts": query.max_facts}
    cached_result = await search_cache.get_search_results(
        query.query,
        query.group_ids,
        cache_params
    )
    
    if cached_result is not None:
        # Emit webhook for cached result
        if cached_result.get("node_ids"):
            await dispatcher.emit_node_access(
                node_ids=cached_result["node_ids"],
                access_type="search_cached",
                query=query.query,
                metadata={"group_ids": query.group_ids, "cache_hit": True}
            )
        
        elapsed_ms = (time.time() - start_time) * 1000
        logger.info(f"Cache hit for search query: {query.query[:50]}... ({elapsed_ms:.2f}ms)")
        
        # Reconstruct SearchResults from cached data
        return SearchResults(facts=cached_result["facts"])
    
    # Cache miss - perform actual search
    logger.debug(f"Cache miss for search query: {query.query[:50]}...")
    
    # Use embedding cache for query embedding
    async def compute_embedding(text: str):
        result = await graphiti.embedder.create(input_data=[text.replace('\n', ' ')])
        return result[0] if isinstance(result, list) else result
    
    # The actual search will use cached embedding if available
    relevant_edges = await graphiti.search(
        group_ids=query.group_ids,
        query=query.query,
        num_results=query.max_facts,
    )
    
    facts = [get_fact_result_from_edge(edge) for edge in relevant_edges]
    
    # Extract unique node IDs from the edges
    node_ids = set()
    for edge in relevant_edges:
        if hasattr(edge, 'source_node_uuid') and edge.source_node_uuid:
            node_ids.add(edge.source_node_uuid)
        if hasattr(edge, 'target_node_uuid') and edge.target_node_uuid:
            node_ids.add(edge.target_node_uuid)
    
    # Cache the result
    cache_data = {
        "facts": facts,
        "node_ids": list(node_ids)
    }
    
    await search_cache.set_search_results(
        query.query,
        cache_data,
        query.group_ids,
        cache_params,
        ttl_seconds=300  # 5 minutes
    )
    
    # Emit webhook event for accessed nodes
    if node_ids:
        await dispatcher.emit_node_access(
            node_ids=list(node_ids),
            access_type="search",
            query=query.query,
            metadata={"group_ids": query.group_ids, "cache_hit": False}
        )
    
    elapsed_ms = (time.time() - start_time) * 1000
    logger.info(f"Search completed and cached: {query.query[:50]}... ({elapsed_ms:.2f}ms)")
    
    return SearchResults(facts=facts)


@router.post('/search/nodes', status_code=status.HTTP_200_OK)
async def cached_search_nodes(query: NodeSearchQuery, graphiti: ZepGraphitiDep) -> NodeSearchResults:
    """
    Cached version of node search endpoint.
    
    Cache key includes: query, group_ids, center_node_uuid, entity, max_nodes
    TTL: 5 minutes
    """
    start_time = time.time()
    
    # Check cache
    cache_params = {
        "center_node_uuid": query.center_node_uuid,
        "entity": query.entity,
        "max_nodes": query.max_nodes,
    }
    
    cached_result = await search_cache.get_search_results(
        query.query,
        query.group_ids,
        cache_params
    )
    
    if cached_result is not None:
        # Emit webhook for cached result
        node_ids = [node["uuid"] for node in cached_result["nodes"]]
        if node_ids:
            await dispatcher.emit_node_access(
                node_ids=node_ids,
                access_type="node_search_cached",
                query=query.query,
                metadata={
                    "group_ids": query.group_ids,
                    "center_node_uuid": query.center_node_uuid,
                    "entity": query.entity,
                    "cache_hit": True
                }
            )
        
        elapsed_ms = (time.time() - start_time) * 1000
        logger.info(f"Cache hit for node search: {query.query[:50]}... ({elapsed_ms:.2f}ms)")
        
        # Reconstruct NodeSearchResults
        nodes = [NodeResult(**node_data) for node_data in cached_result["nodes"]]
        return NodeSearchResults(nodes=nodes)
    
    # Cache miss - perform actual search
    from graphiti_core.search.search_config_recipes import (
        NODE_HYBRID_SEARCH_NODE_DISTANCE,
        NODE_HYBRID_SEARCH_RRF,
    )
    from graphiti_core.search.search_filters import SearchFilters
    
    # Determine search configuration
    if query.center_node_uuid is not None:
        search_config = NODE_HYBRID_SEARCH_NODE_DISTANCE.model_copy(deep=True)
    else:
        search_config = NODE_HYBRID_SEARCH_RRF.model_copy(deep=True)
    search_config.limit = query.max_nodes
    
    # Set up filters if entity type is specified
    filters = SearchFilters()
    if query.entity:
        filters.node_labels = [query.entity]
    
    # Perform the search
    search_results = await graphiti._search(
        query=query.query,
        config=search_config,
        group_ids=query.group_ids or [],
        center_node_uuid=query.center_node_uuid,
        search_filter=filters,
    )
    
    # Format the results
    nodes = []
    node_ids = []
    nodes_data = []
    
    for node in search_results.nodes:
        node_dict = {
            "uuid": node.uuid,
            "name": node.name,
            "summary": getattr(node, 'summary', ''),
            "labels": getattr(node, 'labels', []),
            "group_id": node.group_id,
            "created_at": node.created_at,
            "attributes": getattr(node, 'attributes', {}),
        }
        nodes_data.append(node_dict)
        
        nodes.append(NodeResult(**node_dict))
        node_ids.append(node.uuid)
    
    # Cache the result
    cache_data = {"nodes": nodes_data}
    
    await search_cache.set_search_results(
        query.query,
        cache_data,
        query.group_ids,
        cache_params,
        ttl_seconds=300  # 5 minutes
    )
    
    # Emit webhook event for accessed nodes
    if node_ids:
        await dispatcher.emit_node_access(
            node_ids=node_ids,
            access_type="node_search",
            query=query.query,
            metadata={
                "group_ids": query.group_ids,
                "center_node_uuid": query.center_node_uuid,
                "entity": query.entity,
                "cache_hit": False
            }
        )
    
    elapsed_ms = (time.time() - start_time) * 1000
    logger.info(f"Node search completed and cached: {query.query[:50]}... ({elapsed_ms:.2f}ms)")
    
    return NodeSearchResults(nodes=nodes)


@router.get('/cache/metrics', status_code=status.HTTP_200_OK)
async def get_cache_metrics() -> dict:
    """Get cache performance metrics."""
    return {
        "search_cache": search_cache.get_metrics(),
        "embedding_cache": embedding_cache.get_metrics(),
    }


@router.post('/cache/invalidate', status_code=status.HTTP_200_OK)
async def invalidate_cache(pattern: Optional[str] = None, group_id: Optional[str] = None) -> dict:
    """
    Invalidate cache entries.
    
    Args:
        pattern: Pattern to match cache keys (e.g., "*user_123*")
        group_id: Invalidate all entries for a specific group
    """
    if group_id:
        await search_cache.invalidate_group(group_id)
        return {"status": "success", "invalidated": f"group_{group_id}"}
    elif pattern:
        count = await search_cache.invalidate_pattern(pattern)
        return {"status": "success", "invalidated": count}
    else:
        # Clear all caches
        await search_cache.l1_cache.clear()
        if search_cache.redis_client:
            await search_cache.redis_client.flushdb()
        return {"status": "success", "invalidated": "all"}