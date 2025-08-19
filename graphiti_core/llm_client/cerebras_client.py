"""
Copyright 2024, Zep Software, Inc.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import json
import logging
import os
import typing
from typing import Any

from cerebras.cloud.sdk import Cerebras, CerebrasError
from pydantic import BaseModel

from ..prompts.models import Message
from .client import LLMClient
from .config import DEFAULT_MAX_TOKENS, LLMConfig, ModelSize
from .errors import RateLimitError

logger = logging.getLogger(__name__)

DEFAULT_CEREBRAS_MODEL = 'qwen-3-coder-480b'
DEFAULT_CEREBRAS_SMALL_MODEL = 'qwen-3-coder-480b'  # Use same model for all tasks


class CerebrasClient(LLMClient):
    """
    CerebrasClient is a client class for interacting with Cerebras's Qwen language models.
    
    This class extends the LLMClient and provides Cerebras-specific implementation
    for creating completions using the Qwen Coder model.
    
    Attributes:
        client (Cerebras): The Cerebras client used to interact with the API.
    """
    
    def __init__(
        self,
        config: LLMConfig | None = None,
        cache: bool = False,
        client: typing.Any = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ):
        """
        Initialize the CerebrasClient with the provided configuration.
        
        Args:
            config (LLMConfig | None): The configuration for the LLM client.
            cache (bool): Whether to use caching for responses. Defaults to False.
            client (Any | None): An optional Cerebras client instance to use.
        """
        if cache:
            raise NotImplementedError('Caching is not implemented for Cerebras client')
        
        if config is None:
            config = LLMConfig()
            
        # Set default models if not provided
        if not config.model:
            config.model = DEFAULT_CEREBRAS_MODEL
        if not config.small_model:
            config.small_model = DEFAULT_CEREBRAS_SMALL_MODEL
            
        super().__init__(config, cache)
        self.max_tokens = max_tokens
        
        if client is None:
            # Get API key from config or environment
            api_key = config.api_key or os.getenv('CEREBRAS_API_KEY')
            if not api_key:
                raise ValueError(
                    'Cerebras API key not provided. Set CEREBRAS_API_KEY environment variable '
                    'or provide api_key in config.'
                )
            self.client = Cerebras(api_key=api_key)
        else:
            self.client = client
    
    def _get_model_for_size(self, model_size: ModelSize) -> str:
        """Get the appropriate model name based on the requested size."""
        if model_size == ModelSize.small:
            return self.small_model or DEFAULT_CEREBRAS_SMALL_MODEL
        else:
            return self.model or DEFAULT_CEREBRAS_MODEL
    
    def _convert_messages_to_cerebras_format(
        self, messages: list[Message]
    ) -> list[dict[str, str]]:
        """Convert internal Message format to Cerebras message format."""
        cerebras_messages = []
        for m in messages:
            m.content = self._clean_input(m.content)
            if m.role in ['user', 'system']:
                cerebras_messages.append({'role': m.role, 'content': m.content})
        return cerebras_messages
    
    def _create_json_schema(self, response_model: type[BaseModel]) -> dict:
        """Create a Cerebras-compatible JSON schema from a Pydantic model."""
        schema = response_model.model_json_schema()
        
        # Cerebras requires additionalProperties to be set to false
        # and all properties to be in the required array
        def fix_schema_for_cerebras(obj, path=''):
            if isinstance(obj, dict):
                if 'type' in obj and obj['type'] == 'object':
                    obj['additionalProperties'] = False
                    # Ensure all properties are in required array
                    if 'properties' in obj:
                        obj['required'] = list(obj['properties'].keys())
                for key, value in obj.items():
                    fix_schema_for_cerebras(value, f'{path}.{key}')
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    fix_schema_for_cerebras(item, f'{path}[{i}]')
        
        fix_schema_for_cerebras(schema)
        
        return {
            'name': response_model.__name__.lower(),
            'strict': True,
            'schema': schema
        }
    
    async def _generate_response(
        self,
        messages: list[Message],
        response_model: type[BaseModel] | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        model_size: ModelSize = ModelSize.medium,
    ) -> dict[str, Any]:
        """
        Generate a response using the Cerebras API.
        
        Args:
            messages: List of messages in the conversation.
            response_model: Optional Pydantic model for structured output.
            max_tokens: Maximum tokens to generate.
            model_size: Size of the model to use.
            
        Returns:
            Dictionary containing the response.
        """
        cerebras_messages = self._convert_messages_to_cerebras_format(messages)
        model = self._get_model_for_size(model_size)
        
        try:
            completion_params = {
                'messages': cerebras_messages,
                'model': model,
                'max_completion_tokens': max_tokens or self.max_tokens,
                'temperature': self.temperature,
                'top_p': 0.8,  # Recommended for qwen-3-coder-480b
                # Note: top_k, frequency_penalty, repetition_penalty not supported by Cerebras API
            }
            
            # Add structured output format if response model is provided
            if response_model:
                json_schema = self._create_json_schema(response_model)
                completion_params['response_format'] = {
                    'type': 'json_schema',
                    'json_schema': json_schema
                }
            else:
                # For non-structured responses, still request JSON format
                completion_params['response_format'] = {
                    'type': 'json_schema',
                    'json_schema': {
                        'name': 'response',
                        'strict': False,
                        'schema': {
                            'type': 'object',
                            'additionalProperties': True
                        }
                    }
                }
            
            # Use synchronous API call and wrap in async context
            # Note: Cerebras SDK doesn't have native async support yet
            import asyncio
            loop = asyncio.get_event_loop()
            
            def sync_completion():
                return self.client.chat.completions.create(**completion_params)
            
            chat_completion = await loop.run_in_executor(None, sync_completion)
            
            if chat_completion.choices and len(chat_completion.choices) > 0:
                content = chat_completion.choices[0].message.content
                
                if content:
                    try:
                        result = json.loads(content)
                        
                        # Log token usage if available
                        if hasattr(chat_completion, 'usage') and chat_completion.usage:
                            logger.debug(
                                f'Token usage - Prompt: {chat_completion.usage.prompt_tokens}, '
                                f'Completion: {chat_completion.usage.completion_tokens}, '
                                f'Total: {chat_completion.usage.total_tokens}'
                            )
                        
                        return result
                    except json.JSONDecodeError as e:
                        logger.error(f'Failed to parse JSON response: {content[:500]}')
                        raise e
                else:
                    logger.error('Empty response from Cerebras API')
                    return {}
            else:
                logger.error('No choices in Cerebras response')
                return {}
                
        except CerebrasError as e:
            if 'rate_limit' in str(e).lower():
                raise RateLimitError(f'Cerebras rate limit exceeded: {e}')
            logger.error(f'Cerebras API error: {e}')
            raise e
        except Exception as e:
            logger.error(f'Unexpected error in Cerebras client: {e}')
            raise e