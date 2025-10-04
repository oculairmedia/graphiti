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
import typing
from typing import ClassVar

import openai
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam
from pydantic import BaseModel

from ..prompts.models import Message
from .client import MULTILINGUAL_EXTRACTION_RESPONSES, LLMClient
from .config import DEFAULT_MAX_TOKENS, LLMConfig, ModelSize
from .errors import RateLimitError, RefusalError

logger = logging.getLogger(__name__)

DEFAULT_MODEL = 'gpt-4.1-mini'


class OpenAIGenericClient(LLMClient):
    """
    OpenAIClient is a client class for interacting with OpenAI's language models.

    This class extends the LLMClient and provides methods to initialize the client,
    get an embedder, and generate responses from the language model.

    Attributes:
        client (AsyncOpenAI): The OpenAI client used to interact with the API.
        model (str): The model name to use for generating responses.
        temperature (float): The temperature to use for generating responses.
        max_tokens (int): The maximum number of tokens to generate in a response.

    Methods:
        __init__(config: LLMConfig | None = None, cache: bool = False, client: typing.Any = None):
            Initializes the OpenAIClient with the provided configuration, cache setting, and client.

        _generate_response(messages: list[Message]) -> dict[str, typing.Any]:
            Generates a response from the language model based on the provided messages.
    """

    # Class-level constants
    MAX_RETRIES: ClassVar[int] = 2

    def __init__(
        self, config: LLMConfig | None = None, cache: bool = False, client: typing.Any = None
    ):
        """
        Initialize the OpenAIClient with the provided configuration, cache setting, and client.

        Args:
            config (LLMConfig | None): The configuration for the LLM client, including API key, model, base URL, temperature, and max tokens.
            cache (bool): Whether to use caching for responses. Defaults to False.
            client (Any | None): An optional async client instance to use. If not provided, a new AsyncOpenAI client is created.

        """
        # removed caching to simplify the `generate_response` override
        if cache:
            raise NotImplementedError('Caching is not implemented for OpenAI')

        if config is None:
            config = LLMConfig()

        super().__init__(config, cache)

        if client is None:
            self.client = AsyncOpenAI(api_key=config.api_key, base_url=config.base_url)
        else:
            self.client = client

    async def _generate_response(
        self,
        messages: list[Message],
        response_model: type[BaseModel] | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        model_size: ModelSize = ModelSize.medium,
    ) -> dict[str, typing.Any]:
        openai_messages: list[ChatCompletionMessageParam] = []
        total_chars = 0
        for m in messages:
            m.content = self._clean_input(m.content)
            total_chars += len(m.content)
            if m.role == 'user':
                openai_messages.append({'role': 'user', 'content': m.content})
            elif m.role == 'system':
                openai_messages.append({'role': 'system', 'content': m.content})

        # Estimate token count (rough: 1 token ≈ 4 characters)
        estimated_tokens = total_chars // 4

        # Try to identify prompt type from content
        prompt_type = "unknown"
        if len(messages) > 0:
            user_content = next((m.content for m in messages if m.role == 'user'), '')
            if 'PREVIOUS MESSAGES' in user_content or 'CURRENT MESSAGE' in user_content:
                prompt_type = "entity_extraction"
            elif 'EXTRACTED ENTITIES' in user_content and 'ENTITY PAIRS' in user_content:
                prompt_type = "edge_extraction"
            elif 'EXISTING NODES' in user_content and 'duplication' in user_content.lower():
                prompt_type = "deduplication"
            elif 'EXTRACTED ENTITIES' in user_content and 'missed' in user_content.lower():
                prompt_type = "reflexion"

        logger.info(f"LLM Request [{prompt_type}]: {len(messages)} messages, ~{total_chars:,} chars, ~{estimated_tokens:,} tokens")

        # Debug: Save large prompts to file for analysis
        if estimated_tokens > 10000:
            import os as os_module
            debug_dir = '/tmp/prompt_debug'
            os_module.makedirs(debug_dir, exist_ok=True)

            # Save full prompt to file
            prompt_file = f'{debug_dir}/prompt_{prompt_type}_{estimated_tokens}.json'
            with open(prompt_file, 'w') as f:
                json.dump({
                    'type': prompt_type,
                    'estimated_tokens': estimated_tokens,
                    'messages': [{'role': m.role, 'content': m.content} for m in messages]
                }, f, indent=2)

            logger.warning(f"LARGE PROMPT DETECTED ({estimated_tokens:,} tokens). Saved to {prompt_file}")
        
        # Configure response format based on whether response_model is provided
        if response_model is not None:
            # Use structured outputs with JSON schema for better reliability
            response_format = {
                'type': 'json_schema',
                'json_schema': {
                    'name': 'response',
                    'strict': False,  # Allow flexibility for Ollama and other models
                    'schema': response_model.model_json_schema()
                }
            }
            logger.debug(f"Using structured output with schema: {response_model.__name__}")
        else:
            # Fallback to basic JSON object format
            response_format = {'type': 'json_object'}
            logger.debug("Using basic JSON object format")
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model or DEFAULT_MODEL,
                messages=openai_messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                response_format=response_format,
            )
            result = response.choices[0].message.content or ''

            # Log token usage if available
            if hasattr(response, 'usage') and response.usage:
                logger.info(
                    f"LLM Response: {response.usage.prompt_tokens} prompt tokens, "
                    f"{response.usage.completion_tokens} completion tokens, "
                    f"{response.usage.total_tokens} total tokens"
                )
            else:
                # Estimate for providers that don't return usage
                response_chars = len(result)
                estimated_response_tokens = response_chars // 4
                logger.info(f"LLM Response: ~{response_chars:,} chars, ~{estimated_response_tokens:,} tokens (estimated)")

            return json.loads(result)
        except openai.RateLimitError as e:
            raise RateLimitError from e
        except Exception as e:
            logger.error(f'Error in generating LLM response: {e}')
            raise

    async def generate_response(
        self,
        messages: list[Message],
        response_model: type[BaseModel] | None = None,
        max_tokens: int | None = None,
        model_size: ModelSize = ModelSize.medium,
    ) -> dict[str, typing.Any]:
        if max_tokens is None:
            max_tokens = self.max_tokens

        retry_count = 0
        last_error = None

        if response_model is not None:
            serialized_model = json.dumps(response_model.model_json_schema())
            messages[
                -1
            ].content += (
                f'\n\nRespond with a JSON object in the following format:\n\n{serialized_model}'
            )

        # Add multilingual extraction instructions
        messages[0].content += MULTILINGUAL_EXTRACTION_RESPONSES

        while retry_count <= self.MAX_RETRIES:
            try:
                response = await self._generate_response(
                    messages, response_model, max_tokens=max_tokens, model_size=model_size
                )
                return response
            except (RateLimitError, RefusalError):
                # These errors should not trigger retries
                raise
            except (openai.APITimeoutError, openai.APIConnectionError, openai.InternalServerError):
                # Let OpenAI's client handle these retries
                raise
            except Exception as e:
                last_error = e

                # Don't retry if we've hit the max retries
                if retry_count >= self.MAX_RETRIES:
                    logger.error(f'Max retries ({self.MAX_RETRIES}) exceeded. Last error: {e}')
                    raise

                retry_count += 1

                # Construct a detailed error message for the LLM
                error_context = (
                    f'The previous response attempt was invalid. '
                    f'Error type: {e.__class__.__name__}. '
                    f'Error details: {str(e)}. '
                    f'Please try again with a valid response, ensuring the output matches '
                    f'the expected format and constraints.'
                )

                error_message = Message(role='user', content=error_context)
                messages.append(error_message)
                logger.warning(
                    f'Retrying after application error (attempt {retry_count}/{self.MAX_RETRIES}): {e}'
                )

        # If we somehow get here, raise the last error
        raise last_error or Exception('Max retries exceeded with no specific error')
