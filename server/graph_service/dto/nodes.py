from datetime import datetime
from typing import Any, Dict, List

from pydantic import BaseModel, Field


class UpdateNodeSummaryRequest(BaseModel):
    summary: str = Field(
        ..., description='The new summary text for the node', min_length=0, max_length=5000
    )


class NodeResponse(BaseModel):
    uuid: str = Field(..., description='Node unique identifier')
    name: str = Field(..., description='Node name/label')
    group_id: str = Field(..., description='Node group identifier')
    summary: str = Field(default='', description='Node summary')
    labels: List[str] = Field(default_factory=list, description='Node labels')
    created_at: datetime = Field(..., description='Node creation timestamp')
    attributes: Dict[str, Any] = Field(
        default_factory=dict, description='Additional node attributes'
    )

    class Config:
        from_attributes = True
