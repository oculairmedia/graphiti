from datetime import datetime, timezone
from typing import List, Any, Optional, Dict

from fastapi import APIRouter, status

from graph_service.dto import (
    EdgesByNodeResponse,
    GetMemoryRequest,
    GetMemoryResponse,
    Message,
)
from graph_service.zep_graphiti import ZepGraphitiDep, get_fact_result_from_edge
from graph_service.webhooks import webhook_service

router = APIRouter()


# Search endpoints removed - handled by Rust search proxy service
# Original search and search/nodes endpoints moved to search_proxy.router


@router.get('/entity-edge/{uuid}', status_code=status.HTTP_200_OK)
async def get_entity_edge(uuid: str, graphiti: ZepGraphitiDep) -> Any:
    entity_edge = await graphiti.get_entity_edge(uuid)
    
    # Emit webhook event for accessed nodes
    node_ids = []
    if hasattr(entity_edge, 'source_node_uuid') and entity_edge.source_node_uuid:
        node_ids.append(entity_edge.source_node_uuid)
    if hasattr(entity_edge, 'target_node_uuid') and entity_edge.target_node_uuid:
        node_ids.append(entity_edge.target_node_uuid)
    
    if node_ids:
        await webhook_service.emit_node_access(
            node_ids=node_ids,
            access_type="direct_edge_access",
            metadata={"edge_uuid": uuid}
        )
    
    return get_fact_result_from_edge(entity_edge)


@router.get('/edges/by-node/{node_uuid}', status_code=status.HTTP_200_OK)
async def get_edges_by_node(node_uuid: str, graphiti: ZepGraphitiDep) -> EdgesByNodeResponse:
    from graphiti_core.edges import EntityEdge

    # Get all edges connected to this node
    all_edges = await EntityEdge.get_by_node_uuid(graphiti.driver, node_uuid)

    # Separate edges by relationship to the node
    source_edges = []
    target_edges = []

    for edge in all_edges:
        edge_fact = get_fact_result_from_edge(edge)
        if edge.source_node_uuid == node_uuid:
            source_edges.append(edge_fact)
        if edge.target_node_uuid == node_uuid:
            target_edges.append(edge_fact)

    # All edges (some may appear in both lists if it's a self-referential edge)
    all_edge_facts = [get_fact_result_from_edge(edge) for edge in all_edges]
    
    # Emit webhook event for the accessed node and connected nodes
    node_ids = {node_uuid}  # Include the queried node
    for edge in all_edges:
        if edge.source_node_uuid and edge.source_node_uuid != node_uuid:
            node_ids.add(edge.source_node_uuid)
        if edge.target_node_uuid and edge.target_node_uuid != node_uuid:
            node_ids.add(edge.target_node_uuid)
    
    if node_ids:
        await webhook_service.emit_node_access(
            node_ids=list(node_ids),
            access_type="node_edges_access",
            metadata={"center_node_uuid": node_uuid}
        )

    return EdgesByNodeResponse(
        edges=all_edge_facts, source_edges=source_edges, target_edges=target_edges
    )


@router.get('/episodes/{group_id}', status_code=status.HTTP_200_OK)
async def get_episodes(group_id: str, last_n: int = 10, graphiti: ZepGraphitiDep) -> Dict[str, Any]:
    episodes_data = await graphiti.retrieve_episodes(
        group_ids=[group_id], last_n=last_n, reference_time=datetime.now(timezone.utc)  # type: ignore[call-arg]
    )
    
    # Format episodes to match MCP server expectations
    episodes = []
    if hasattr(episodes_data, '__iter__'):
        for episode in episodes_data:
            # Convert episode to dict format expected by MCP server
            episode_dict = {
                'uuid': getattr(episode, 'uuid', ''),
                'name': getattr(episode, 'name', ''),
                'group_id': getattr(episode, 'group_id', group_id),
                'created_at': getattr(episode, 'created_at', ''),
                'content': getattr(episode, 'content', ''),
                'source': getattr(episode, 'source', ''),
                'source_description': getattr(episode, 'source_description', ''),
                'valid_at': getattr(episode, 'valid_at', ''),
                'summary': getattr(episode, 'summary', ''),
            }
            episodes.append(episode_dict)
    
    return {
        'episodes': episodes
    }


@router.post('/get-memory', status_code=status.HTTP_200_OK)
async def get_memory(
    request: GetMemoryRequest,
    graphiti: ZepGraphitiDep,
) -> GetMemoryResponse:
    combined_query = compose_query_from_messages(request.messages)
    result = await graphiti.search(
        group_ids=[request.group_id],
        query=combined_query,
        num_results=request.max_facts,
    )
    facts = [get_fact_result_from_edge(edge) for edge in result]  # type: ignore[arg-type]
    
    # Emit webhook event for accessed nodes (for Letta integration)
    node_ids = set()
    for edge in result:
        if edge.source_node_uuid:  # type: ignore[attr-defined]
            node_ids.add(edge.source_node_uuid)  # type: ignore[attr-defined]
        if edge.target_node_uuid:  # type: ignore[attr-defined]
            node_ids.add(edge.target_node_uuid)  # type: ignore[attr-defined]
    
    if node_ids:
        print(f"[GET_MEMORY] Emitting node access for {len(node_ids)} nodes")
        await webhook_service.emit_node_access(
            node_ids=list(node_ids),
            access_type="letta_memory_retrieval",
            query=combined_query,
            metadata={
                "group_id": request.group_id,
                "messages_count": len(request.messages)
            }
        )
    
    return GetMemoryResponse(facts=facts)


def compose_query_from_messages(messages: list[Message]) -> str:
    combined_query = ''
    for message in messages:
        role = message.role or ""
        combined_query += f'{message.role_type}({role}): {message.content}\n'
    return combined_query
