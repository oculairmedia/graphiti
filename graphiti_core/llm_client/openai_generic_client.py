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
import re
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


def _robust_json_parse(content: str) -> dict[str, typing.Any]:
    """
    Robust JSON parser that handles common LLM output issues.

    Handles:
    - Multiple JSON objects concatenated (takes first one)
    - Markdown code blocks (```json ... ```)
    - Explanatory text around JSON
    - Trailing commas
    - Single quotes instead of double quotes

    Args:
        content: Raw LLM response content

    Returns:
        Parsed dictionary

    Raises:
        json.JSONDecodeError: If no valid JSON can be extracted
    """
    content = content.strip()

    # Strategy 1: Try direct parsing first
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # Strategy 2: Handle markdown code blocks
    if '```json' in content:
        try:
            # Extract content between ```json and ```
            match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
            if match:
                return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    if '```' in content:
        try:
            # Extract content between ``` and ```
            match = re.search(r'```\s*(.*?)\s*```', content, re.DOTALL)
            if match:
                return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Strategy 3: Extract first complete JSON object or array (handles multiple objects/extra text)
    # This specifically addresses the "Extra data: line 2 column 1" error
    try:
        # Find the first { or [ and track brackets to find matching } or ]
        obj_idx = content.find('{')
        arr_idx = content.find('[')

        # Determine which comes first (or only one exists)
        if obj_idx == -1 and arr_idx == -1:
            pass  # No JSON structure found
        else:
            # Use whichever comes first (or the one that exists)
            if obj_idx == -1:
                start_idx, open_char, close_char = arr_idx, '[', ']'
            elif arr_idx == -1:
                start_idx, open_char, close_char = obj_idx, '{', '}'
            else:
                # Both exist - use whichever comes first
                if obj_idx < arr_idx:
                    start_idx, open_char, close_char = obj_idx, '{', '}'
                else:
                    start_idx, open_char, close_char = arr_idx, '[', ']'

            depth = 0
            in_string = False
            escape_next = False

            for i, char in enumerate(content[start_idx:], start_idx):
                if escape_next:
                    escape_next = False
                    continue
                if char == '\\':
                    escape_next = True
                    continue
                if char == '"' and not escape_next:
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if char == open_char:
                    depth += 1
                elif char == close_char:
                    depth -= 1
                    if depth == 0:
                        json_str = content[start_idx : i + 1]
                        return json.loads(json_str)
    except json.JSONDecodeError:
        pass

    # Strategy 4: Try regex to extract JSON object
    try:
        # Match a JSON object pattern
        json_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
        matches = re.findall(json_pattern, content, re.DOTALL)

        for match in matches:
            try:
                return json.loads(match)
            except json.JSONDecodeError:
                # Try with cleanup
                cleaned = match
                # Replace single quotes with double quotes (careful with apostrophes)
                cleaned = re.sub(r"(?<![a-zA-Z])'([^']*)'(?![a-zA-Z])", r'"\1"', cleaned)
                # Fix trailing commas
                cleaned = re.sub(r',\s*}', '}', cleaned)
                cleaned = re.sub(r',\s*]', ']', cleaned)
                try:
                    return json.loads(cleaned)
                except json.JSONDecodeError:
                    continue
    except Exception:
        pass

    # Strategy 5: Last resort - try to find any JSON-like structure
    try:
        # Remove common prefixes/suffixes that models add
        cleaned = content
        prefixes_to_remove = [
            'Here is the JSON:',
            "Here's the JSON:",
            'JSON:',
            'Output:',
            'Result:',
        ]
        for prefix in prefixes_to_remove:
            if cleaned.lower().startswith(prefix.lower()):
                cleaned = cleaned[len(prefix) :].strip()

        # Try parsing the cleaned content
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # If all strategies fail, raise the original error
    raise json.JSONDecodeError(f'Could not extract valid JSON from response', content, 0)


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
        for m in messages:
            m.content = self._clean_input(m.content)
            if m.role == 'user':
                openai_messages.append({'role': 'user', 'content': m.content})
            elif m.role == 'system':
                openai_messages.append({'role': 'system', 'content': m.content})

        # Detect if we're using vLLM (check for common vLLM patterns in base_url)
        base_url = str(self.client.base_url) if hasattr(self.client, 'base_url') else ''
        is_vllm = (
            'vllm' in base_url.lower() or ':11434' in base_url
        )  # vLLM or Ollama-like endpoints

        # Prepare API call kwargs
        call_kwargs = {
            'model': self.model or DEFAULT_MODEL,
            'messages': openai_messages,
            'temperature': self.temperature,
            'max_tokens': self.max_tokens,
        }

        # Configure response format based on whether response_model is provided
        if response_model is not None:
            json_schema = response_model.model_json_schema()

            if is_vllm:
                # vLLM uses guided_json via extra_body when using OpenAI SDK
                call_kwargs['extra_body'] = {'guided_json': json_schema}
                logger.debug(f'Using vLLM guided_json with schema: {response_model.__name__}')
            else:
                # OpenAI uses response_format
                call_kwargs['response_format'] = {
                    'type': 'json_schema',
                    'json_schema': {'name': 'response', 'strict': False, 'schema': json_schema},
                }
                logger.debug(
                    f'Using OpenAI structured output with schema: {response_model.__name__}'
                )
        else:
            if is_vllm:
                # vLLM: use basic guided_json for free-form JSON via extra_body
                call_kwargs['extra_body'] = {'guided_json': {'type': 'object'}}
                logger.debug('Using vLLM guided_json with basic object schema')
            else:
                # OpenAI: use response_format
                call_kwargs['response_format'] = {'type': 'json_object'}
                logger.debug('Using OpenAI basic JSON object format')

        try:
            response = await self.client.chat.completions.create(**call_kwargs)
            result = response.choices[0].message.content or ''

            # Use robust JSON parser to handle common LLM output issues
            # This handles: multiple JSON objects, markdown blocks, explanatory text, etc.
            return _robust_json_parse(result)
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

        # IMPORTANT: Create deep copy of messages to avoid mutations across retries
        # Without this, retries will accumulate content and cause role alternation errors
        import copy

        messages_copy = copy.deepcopy(messages)

        if response_model is not None:
            serialized_model = json.dumps(response_model.model_json_schema())
            messages_copy[
                -1
            ].content += (
                f'\n\nRespond with a JSON object in the following format:\n\n{serialized_model}'
            )

        # Add multilingual extraction instructions
        messages_copy[0].content += MULTILINGUAL_EXTRACTION_RESPONSES

        while retry_count <= self.MAX_RETRIES:
            try:
                response = await self._generate_response(
                    messages_copy, response_model, max_tokens=max_tokens, model_size=model_size
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
