from datetime import datetime
from typing import Any, Literal

from graphiti_core.utils.datetime_utils import utc_now
from pydantic import BaseModel, Field, validator


class Result(BaseModel):
    message: str
    success: bool


class SuccessResponse(BaseModel):
    success: bool = True
    message: str = 'Operation completed successfully'


FALLBACK_EPISODE_NAME = 'unnamed-episode'


class Message(BaseModel):
    content: str = Field(..., description='The content of the message')
    uuid: str | None = Field(default=None, description='The uuid of the message (optional)')
    name: str = Field(
        default='', description='The name of the episodic node for the message (optional)'
    )
    role_type: Literal['user', 'assistant', 'system'] = Field(
        ..., description='The role type of the message (user, assistant or system)'
    )
    role: str | None = Field(
        description='The custom role of the message to be used alongside role_type (user name, bot name, etc.)',
    )
    timestamp: datetime = Field(default_factory=utc_now, description='The timestamp of the message')
    source_description: str = Field(
        default='', description='The description of the source of the message'
    )

    @validator('name', pre=True, always=True)
    def ensure_name_not_empty(cls, value: str | None, values: dict[str, Any]) -> str:
        normalized = (value or '').strip()
        if normalized:
            return normalized
        content: str = values.get('content', '')
        if content:
            content_preview = content[:60].replace('\n', ' ').strip()
            return content_preview or FALLBACK_EPISODE_NAME
        return FALLBACK_EPISODE_NAME

    @validator('source_description', pre=True, always=True)
    def ensure_source_description(cls, value: str | None) -> str:
        normalized = (value or '').strip()
        return normalized if normalized else 'unspecified'
