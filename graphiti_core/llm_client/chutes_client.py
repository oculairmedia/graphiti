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

import ast
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

DEFAULT_MODEL = 'zai-org/GLM-4.5-FP8'
DEFAULT_BASE_URL = 'https://llm.chutes.ai/v1'


class ChutesClient(LLMClient):
    """
    ChutesClient is a client class for interacting with Chutes AI's language models.

    This class extends the LLMClient and provides methods to initialize the client
    and generate responses from the Chutes AI language model using OpenAI-compatible API.

    Attributes:
        client (AsyncOpenAI): The OpenAI-compatible client used to interact with the Chutes AI API.
        model (str): The model name to use for generating responses.
        temperature (float): The temperature to use for generating responses.
        max_tokens (int): The maximum number of tokens to generate in a response.

    Methods:
        __init__(config: LLMConfig | None = None, cache: bool = False, client: typing.Any = None):
            Initializes the ChutesClient with the provided configuration, cache setting, and client.

        _generate_response(messages: list[Message]) -> dict[str, typing.Any]:
            Generates a response from the language model based on the provided messages.
    """

    # Class-level constants
    MAX_RETRIES: ClassVar[int] = 2

    def __init__(
        self, config: LLMConfig | None = None, cache: bool = False, client: typing.Any = None
    ):
        """
        Initialize the ChutesClient with the provided configuration, cache setting, and client.

        Args:
            config (LLMConfig | None): The configuration for the LLM client, including API key, model, base URL, temperature, and max tokens.
            cache (bool): Whether to use caching for responses. Defaults to False.
            client (Any | None): An optional async client instance to use. If not provided, a new AsyncOpenAI client is created.

        """
        # removed caching to simplify the `generate_response` override
        if cache:
            raise NotImplementedError('Caching is not implemented for ChutesClient')

        if config is None:
            config = LLMConfig()

        super().__init__(config, cache)

        if client is None:
            base_url = config.base_url or DEFAULT_BASE_URL
            self.client = AsyncOpenAI(api_key=config.api_key, base_url=base_url)
        else:
            self.client = client

    def _parse_chutes_response(self, content: str) -> dict[str, typing.Any] | None:
        """
        Robust parser for Chutes AI responses that can handle multiple formats.
        
        Chutes often returns Python dict format instead of JSON, so we try multiple strategies:
        1. Standard JSON parsing
        2. Python dict string evaluation (ast.literal_eval)
        3. Manual conversion of Python syntax to JSON
        4. Regex extraction of structured data
        
        Args:
            content: Raw response content from Chutes AI
            
        Returns:
            Parsed dictionary if successful, None if all strategies fail
        """
        content = content.strip()
        
        # Strategy 1: Try standard JSON parsing first
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            logger.debug('Standard JSON parsing failed, trying alternative strategies')
        
        # Strategy 2: Try Python dict evaluation (handles True/False, single quotes)
        if content.startswith('{') and content.endswith('}'):
            try:
                result = ast.literal_eval(content)
                if isinstance(result, dict):
                    logger.info('Successfully parsed as Python dict using ast.literal_eval')
                    return result
            except (ValueError, SyntaxError):
                logger.debug('ast.literal_eval failed, trying manual conversion')
        
        # Strategy 3: Manual conversion of Python syntax to JSON
        try:
            # Replace Python boolean/null values with JSON equivalents
            json_content = content
            json_content = json_content.replace("True", "true")
            json_content = json_content.replace("False", "false")
            json_content = json_content.replace("None", "null")
            
            # Replace single quotes with double quotes (careful with nested quotes)
            # This is a simplified approach - could be more robust
            json_content = re.sub(r"'([^']*)':", r'"\1":', json_content)  # Keys
            json_content = re.sub(r":\s*'([^']*)'", r': "\1"', json_content)  # Values
            
            result = json.loads(json_content)
            logger.info('Successfully converted Python syntax to JSON')
            return result
        except (json.JSONDecodeError, Exception):
            logger.debug('Manual JSON conversion failed, trying regex extraction')
        
        # Strategy 4: Regex extraction for common patterns
        # Look for dictionary-like structures even if not perfectly formatted
        
        # Try to find entities array pattern
        entities_match = re.search(r"'entities':\s*\[(.*?)\]", content, re.DOTALL)
        if entities_match:
            try:
                entities_content = entities_match.group(1)
                # Try to build a basic structure
                return {'entities': self._extract_entities_from_text(entities_content)}
            except Exception:
                pass
        
        # Try to find duplicates array pattern
        duplicates_match = re.search(r"'duplicates':\s*\[(.*?)\]", content, re.DOTALL)
        if duplicates_match:
            try:
                duplicates_content = duplicates_match.group(1)
                return {'duplicates': self._extract_duplicates_from_text(duplicates_content)}
            except Exception:
                pass
        
        # Try to find relationships array pattern
        relationships_match = re.search(r"'relationships':\s*\[(.*?)\]", content, re.DOTALL)
        if relationships_match:
            try:
                relationships_content = relationships_match.group(1)
                return {'relationships': self._extract_relationships_from_text(relationships_content)}
            except Exception:
                pass
        
        logger.warning('All parsing strategies failed')
        return None
    
    def _extract_entities_from_text(self, text: str) -> list[dict[str, str]]:
        """Extract entities from malformed text using regex patterns."""
        entities = []
        
        # Look for entity dict patterns like {'name': 'value', 'type': 'value', 'context': 'value'}
        entity_pattern = r"\{'name':\s*'([^']*)',\s*'type':\s*'([^']*)',\s*'context':\s*'([^']*)'\}"
        matches = re.findall(entity_pattern, text)
        
        for name, entity_type, context in matches:
            entities.append({
                'name': name,
                'type': entity_type,
                'context': context
            })
        
        return entities
    
    def _extract_duplicates_from_text(self, text: str) -> list[dict]:
        """Extract duplicates from malformed text using regex patterns."""
        duplicates = []
        
        # Pattern for duplicate entries
        duplicate_pattern = r"\{'index':\s*(\d+),\s*'is_duplicate':\s*(True|False),\s*'confidence':\s*([\d.]+),\s*'reason':\s*'([^']*)'\}"
        matches = re.findall(duplicate_pattern, text)
        
        for index, is_dup, confidence, reason in matches:
            duplicates.append({
                'index': int(index),
                'is_duplicate': is_dup == 'True',
                'confidence': float(confidence),
                'reason': reason
            })
        
        return duplicates
    
    def _extract_relationships_from_text(self, text: str) -> list[dict[str, str]]:
        """Extract relationships from malformed text using regex patterns."""
        relationships = []
        
        # Pattern for relationship entries
        rel_pattern = r"\{'source':\s*'([^']*)',\s*'target':\s*'([^']*)',\s*'relationship_type':\s*'([^']*)',\s*'context':\s*'([^']*)'\}"
        matches = re.findall(rel_pattern, text)
        
        for source, target, rel_type, context in matches:
            relationships.append({
                'source': source,
                'target': target, 
                'relationship_type': rel_type,
                'context': context
            })
        
        return relationships

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
        try:
            logger.debug(f'Making request to Chutes AI with model: {self.model or DEFAULT_MODEL}')
            
            # Make the API request
            response = await self.client.chat.completions.create(
                model=self.model or DEFAULT_MODEL,
                messages=openai_messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                response_format={'type': 'json_object'},
            )
            
            if not response.choices or not response.choices[0].message:
                logger.warning('Received malformed response structure from Chutes AI')
                raise ValueError('Malformed response structure from Chutes AI')
                
            result = response.choices[0].message.content or ''
            
            # Handle empty or whitespace-only responses
            if not result.strip():
                logger.warning('Received empty response content from Chutes AI')
                raise ValueError('Empty response content from Chutes AI')
            
            # Try multiple parsing strategies to extract valid format
            parsed_response = self._parse_chutes_response(result)
            if parsed_response is not None:
                logger.debug(f'Successfully parsed Chutes AI response')
                return parsed_response
            
            # If all parsing strategies fail, this is a wasted request
            logger.error(f'All parsing strategies failed for Chutes response: {repr(result[:500])}...')
            raise ValueError(f'Could not extract valid format from Chutes AI response')
                
        except openai.RateLimitError as e:
            logger.warning(f'Chutes AI rate limit hit: {e}')
            raise RateLimitError from e
        except Exception as e:
            logger.error(f'Error in Chutes AI response generation: {e.__class__.__name__}: {e}')
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
            except ValueError as e:
                # Don't retry on JSON parsing errors or empty responses - these waste requests
                error_msg = str(e).lower()
                if any(keyword in error_msg for keyword in ['json', 'empty response', 'malformed response']):
                    logger.error(f'Non-retryable error (would waste API requests): {e}')
                    raise
                # Other ValueError types can be retried
                last_error = e
                if retry_count >= self.MAX_RETRIES:
                    logger.error(f'Max retries ({self.MAX_RETRIES}) exceeded. Last error: {e}')
                    raise
                retry_count += 1
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