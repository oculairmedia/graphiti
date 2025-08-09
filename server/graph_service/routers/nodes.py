from fastapi import APIRouter, HTTPException, status
from graphiti_core.errors import NodeNotFoundError
from graphiti_core.nodes import EntityNode

from graph_service.dto.nodes import NodeResponse, UpdateNodeSummaryRequest
from graph_service.zep_graphiti import ZepGraphitiDep

router = APIRouter()


@router.patch(
    '/nodes/{node_uuid}/summary', status_code=status.HTTP_200_OK, response_model=NodeResponse
)
async def update_node_summary(
    node_uuid: str, request: UpdateNodeSummaryRequest, graphiti: ZepGraphitiDep
) -> NodeResponse:
    """Update the summary of a specific entity node"""
    try:
        # Get the existing node
        node = await EntityNode.get_by_uuid(graphiti.driver, node_uuid)

        # Update the summary
        node.summary = request.summary

        # Save the updated node
        await node.save(graphiti.driver)

        # Return the updated node
        return NodeResponse(
            uuid=node.uuid,
            name=node.name,
            group_id=node.group_id,
            summary=node.summary,
            labels=node.labels,
            created_at=node.created_at,
            attributes=dict(node.attributes),  # Convert to dict explicitly
        )

    except NodeNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f'Node with uuid {node_uuid} not found'
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f'Failed to update node summary: {str(e)}',
        )
