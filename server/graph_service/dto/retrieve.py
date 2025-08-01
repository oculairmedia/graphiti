from datetime import datetime, timezone

from pydantic import BaseModel, Field

from graph_service.dto.common import Message


class SearchQuery(BaseModel):
    group_ids: list[str] | None = Field(
        None, description='The group ids for the memories to search'
    )
    query: str
    max_facts: int = Field(default=10, description='The maximum number of facts to retrieve')


class FactResult(BaseModel):
    uuid: str
    name: str
    fact: str
    valid_at: datetime | None
    invalid_at: datetime | None
    created_at: datetime
    expired_at: datetime | None

    class Config:
        json_encoders = {datetime: lambda v: v.astimezone(timezone.utc).isoformat()}


class SearchResults(BaseModel):
    facts: list[FactResult]


class GetMemoryRequest(BaseModel):
    group_id: str = Field(..., description='The group id of the memory to get')
    max_facts: int = Field(default=10, description='The maximum number of facts to retrieve')
    center_node_uuid: str | None = Field(
        ..., description='The uuid of the node to center the retrieval on'
    )
    messages: list[Message] = Field(
        ..., description='The messages to build the retrieval query from '
    )


class GetMemoryResponse(BaseModel):
    facts: list[FactResult] = Field(..., description='The facts that were retrieved from the graph')


class NodeSearchQuery(BaseModel):
    group_ids: list[str] | None = Field(None, description='The group ids for the nodes to search')
    query: str
    max_nodes: int = Field(default=10, description='The maximum number of nodes to retrieve')
    center_node_uuid: str | None = Field(
        None, description='Optional UUID of a node to center the search around'
    )
    entity: str = Field(default='', description='Optional entity type to filter results')


class NodeResult(BaseModel):
    uuid: str
    name: str
    summary: str
    labels: list[str]
    group_id: str
    created_at: datetime
    attributes: dict

    class Config:
        json_encoders = {datetime: lambda v: v.astimezone(timezone.utc).isoformat()}


class NodeSearchResults(BaseModel):
    nodes: list[NodeResult]


class EdgesByNodeResponse(BaseModel):
    edges: list[FactResult]
    source_edges: list[FactResult] = Field(..., description='Edges where this node is the source')
    target_edges: list[FactResult] = Field(..., description='Edges where this node is the target')
