"""
Mock implementation of LLMClient for testing.

Provides controllable LLM responses for testing LLM-dependent code
without actual API calls.
"""

from __future__ import annotations

import json
from typing import Any
from pydantic import BaseModel

from graphiti_core.llm_client.config import LLMConfig, ModelSize


class MockLLMClient:
    """
    Mock implementation of LLMClient for testing.

    Provides controllable responses for testing without actual LLM API calls.
    Supports:
    - Canned responses for specific prompts
    - Default responses based on response_model
    - Response tracking for verification

    Attributes:
        responses: Queue of responses to return
        default_responses: Default responses by response model class name
        call_log: List of (messages, response_model, kwargs) tuples
        config: LLM configuration
    """

    def __init__(self, config: LLMConfig | None = None, cache: bool = False):
        self.config = config or LLMConfig()
        self.model = self.config.model
        self.small_model = self.config.small_model
        self.temperature = self.config.temperature
        self.max_tokens = self.config.max_tokens
        self.cache_enabled = cache
        self.cache_dir = None

        self.responses: list[dict[str, Any]] = []
        self.default_responses: dict[str, dict[str, Any]] = {}
        self.call_log: list[tuple[list, type | None, dict]] = []

    def add_response(self, response: dict[str, Any]):
        """
        Add a response to the queue.

        Responses are returned in FIFO order.
        """
        self.responses.append(response)

    def set_default_response(self, model_name: str, response: dict[str, Any]):
        """
        Set a default response for a specific response model class.

        Args:
            model_name: Name of the response model class
            response: Response to return for that model
        """
        self.default_responses[model_name] = response

    def clear(self):
        """Clear all responses and call log."""
        self.responses.clear()
        self.default_responses.clear()
        self.call_log.clear()

    def _clean_input(self, input: str) -> str:
        """Clean input string (mimics real LLMClient behavior)."""
        cleaned = input.encode('utf-8', errors='ignore').decode('utf-8')
        zero_width = '\u200b\u200c\u200d\ufeff\u2060'
        for char in zero_width:
            cleaned = cleaned.replace(char, '')
        cleaned = ''.join(char for char in cleaned if ord(char) >= 32 or char in '\n\r\t')
        return cleaned

    async def generate_response(
        self,
        messages: list,
        response_model: type[BaseModel] | None = None,
        max_tokens: int | None = None,
        model_size: ModelSize = ModelSize.medium,
    ) -> dict[str, Any]:
        """
        Generate a mock response.

        Priority:
        1. Return next queued response if available
        2. Return default response for response_model if set
        3. Generate default response based on response_model schema
        4. Return empty dict
        """
        self.call_log.append(
            (messages, response_model, {'max_tokens': max_tokens, 'model_size': model_size})
        )

        # Return queued response if available
        if self.responses:
            return self.responses.pop(0)

        # Return default response for model
        if response_model:
            model_name = response_model.__name__
            if model_name in self.default_responses:
                return self.default_responses[model_name]

            # Generate default response from schema
            return self._generate_default_from_schema(response_model)

        return {}

    async def _generate_response(
        self,
        messages: list,
        response_model: type[BaseModel] | None = None,
        max_tokens: int = 4096,
        model_size: ModelSize = ModelSize.medium,
    ) -> dict[str, Any]:
        """Internal generate response (for compatibility)."""
        return await self.generate_response(messages, response_model, max_tokens, model_size)

    def _generate_default_from_schema(self, response_model: type[BaseModel]) -> dict[str, Any]:
        """
        Generate a default response based on the response model schema.

        Creates sensible defaults for common field types:
        - str: empty string
        - int: 0
        - float: 0.0
        - bool: False
        - list: empty list
        - dict: empty dict
        """
        schema = response_model.model_json_schema()
        properties = schema.get('properties', {})
        required = schema.get('required', [])

        result = {}
        for field_name, field_info in properties.items():
            field_type = field_info.get('type', 'string')

            # Handle common types
            if field_type == 'string':
                result[field_name] = ''
            elif field_type == 'integer':
                result[field_name] = 0
            elif field_type == 'number':
                result[field_name] = 0.0
            elif field_type == 'boolean':
                result[field_name] = False
            elif field_type == 'array':
                result[field_name] = []
            elif field_type == 'object':
                result[field_name] = {}
            else:
                result[field_name] = None

        return result


# Common response factories for testing


def create_extracted_entities_response(
    entities: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Create a response for extract_nodes prompts.

    Args:
        entities: List of entity dicts with 'name', 'entity_type_id', etc.
    """
    return {'extracted_entities': entities or []}


def create_node_resolutions_response(
    resolutions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Create a response for dedupe_nodes prompts.

    Args:
        resolutions: List of resolution dicts with 'id', 'duplicate_idx', etc.
    """
    return {'entity_resolutions': resolutions or []}


def create_edge_resolutions_response(
    resolutions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Create a response for dedupe_edges prompts.

    Args:
        resolutions: List of resolution dicts
    """
    return {'edge_resolutions': resolutions or []}


def create_summary_response(summary: str = 'Test summary') -> dict[str, Any]:
    """Create a response for summary generation prompts."""
    return {'summary': summary}
