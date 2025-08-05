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
from graph_service.webhooks import webhook_service

router = APIRouter()


@router.post('/search', status_code=status.HTTP_200_OK)
async def search(query: SearchQuery, graphiti: ZepGraphitiDep):
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
    
    # Emit webhook event for accessed nodes
    if node_ids:
        print(f"[SEARCH] Emitting node access for {len(node_ids)} nodes")
        await webhook_service.emit_node_access(
            node_ids=list(node_ids),
            access_type="search",
            query=query.query,
            metadata={"group_ids": query.group_ids}
        )
    
    return SearchResults(
        facts=facts,
    )


@router.post('/search/nodes', status_code=status.HTTP_200_OK)
async def search_nodes(query: NodeSearchQuery, graphiti: ZepGraphitiDep):
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
    for node in search_results.nodes:
        nodes.append(
            NodeResult(
                uuid=node.uuid,
                name=node.name,
                summary=getattr(node, 'summary', ''),
                labels=getattr(node, 'labels', []),
                group_id=node.group_id,
                created_at=node.created_at,
                attributes=getattr(node, 'attributes', {}),
            )
        )
        node_ids.append(node.uuid)
    
    # Emit webhook event for accessed nodes
    if node_ids:
        print(f"[NODE_SEARCH] Emitting node access for {len(node_ids)} nodes")
        await webhook_service.emit_node_access(
            node_ids=node_ids,
            access_type="node_search",
            query=query.query,
            metadata={
                "group_ids": query.group_ids,
                "center_node_uuid": query.center_node_uuid,
                "entity": query.entity
            }
        )

    return NodeSearchResults(nodes=nodes)


@router.get('/entity-edge/{uuid}', status_code=status.HTTP_200_OK)
async def get_entity_edge(uuid: str, graphiti: ZepGraphitiDep):
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
async def get_edges_by_node(node_uuid: str, graphiti: ZepGraphitiDep):
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
async def get_episodes(group_id: str, last_n: int, graphiti: ZepGraphitiDep):
    episodes = await graphiti.retrieve_episodes(
        group_ids=[group_id], last_n=last_n, reference_time=datetime.now(timezone.utc)
    )
    return episodes


@router.post('/get-memory', status_code=status.HTTP_200_OK)
async def get_memory(
    request: GetMemoryRequest,
    graphiti: ZepGraphitiDep,
):
    combined_query = compose_query_from_messages(request.messages)
    result = await graphiti.search(
        group_ids=[request.group_id],
        query=combined_query,
        num_results=request.max_facts,
    )
    facts = [get_fact_result_from_edge(edge) for edge in result]
    return GetMemoryResponse(facts=facts)


def compose_query_from_messages(messages: list[Message]):
    combined_query = ''
    for message in messages:
        combined_query += f'{message.role_type or ""}({message.role or ""}): {message.content}\n'
    return combined_query
