from pydantic import BaseModel, Field

from graph_service.dto.common import Message


class AddMessagesRequest(BaseModel):
    group_id: str = Field(..., description='The group id of the messages to add')
    messages: list[Message] = Field(..., description='The messages to add')


class AddEntityNodeRequest(BaseModel):
    uuid: str = Field(..., description='The uuid of the node to add')
    group_id: str = Field(..., description='The group id of the node to add')
    name: str = Field(..., description='The name of the node to add')
    summary: str = Field(default='', description='The summary of the node to add')


class AddEntityEdgeRequest(BaseModel):
    uuid: str = Field(..., description='The uuid of the edge to add')
    source_node_uuid: str = Field(..., description='UUID of the source entity node')
    target_node_uuid: str = Field(..., description='UUID of the target entity node')
    name: str = Field(..., description='The relationship type (e.g., CONTAINS, DEPENDS_ON)')
    group_id: str = Field(..., description='The group id for data partitioning')
    fact: str = Field(default='', description='Human-readable description of the relationship')
