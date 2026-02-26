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

import asyncio
import ast
import json
import logging
import re
import typing
from typing import Any, ClassVar, Dict, List, TYPE_CHECKING

import openai
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam
from pydantic import BaseModel, Field, ValidationError, field_validator
from pydantic_core import from_json

from ..dspy.config import ZAITokenTracker
from ..prompts.models import Message
from ..utils.prompt_compression import get_prompt_compressor
from .client import MULTILINGUAL_EXTRACTION_RESPONSES, LLMClient
from .config import DEFAULT_MAX_TOKENS, LLMConfig, ModelSize
from .errors import RateLimitError, RefusalError

if TYPE_CHECKING:
    # Forward references for type hints only
    from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

DEFAULT_MODEL = 'deepseek-ai/DeepSeek-V3.1'
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
    BASE_RETRY_DELAY: ClassVar[float] = 5.0  # Start with 5 second delay for slow API
    MAX_RETRY_DELAY: ClassVar[float] = 60.0  # Cap at 60 seconds
    # Token budget tracking is handled by ZAITokenTracker (shared with DSPy)

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
            # Set extended timeouts for Chutes AI - their models may take longer to respond
            self.client = AsyncOpenAI(
                api_key=config.api_key,
                base_url=base_url,
                timeout=120.0,  # 2 minutes timeout for Chutes AI
                max_retries=3,
            )
        else:
            self.client = client

    def _parse_chutes_response(self, content: str) -> dict[str, typing.Any] | None:
        """
        Enhanced robust parser for Chutes AI responses using proven strategies.

        This method now leverages the robust parsing strategies developed through
        extensive testing to handle various GLM-4.5-FP8 response formats.

        Args:
            content: Raw response content from Chutes AI

        Returns:
            Parsed dictionary if successful, None if all strategies fail
        """
        content = content.strip()

        # For single response parsing, we'll use a subset of the robust strategies

        # Strategy 0: Handle DeepSeek V3.1 schema inclusion pattern
        # DeepSeek V3.1 includes both Pydantic schema definition AND data in response
        try:
            result = json.loads(content)
            # Check if this looks like DeepSeek's schema+data response
            if isinstance(result, dict):
                # Pattern 1: Data mixed with schema at top level
                if '$defs' in result or 'properties' in result:
                    data_fields = {}

                    # Extract actual data fields (not schema fields)
                    for key, value in result.items():
                        if key not in [
                            '$defs',
                            'properties',
                            'required',
                            'title',
                            'type',
                            'description',
                        ]:
                            data_fields[key] = value

                    # Pattern 2: Data nested in properties
                    # Example: {"properties": {"summary": {"value": "actual text"}}}
                    # Or GLM pattern: {"properties": {"summary": "actual text"}}
                    if 'properties' in result and isinstance(result['properties'], dict):
                        for prop_key, prop_value in result['properties'].items():
                            # GLM pattern: value is directly a string (not a schema dict)
                            if isinstance(prop_value, str):
                                data_fields[prop_key] = prop_value
                            elif isinstance(prop_value, dict):
                                # Check for 'value' field within property definition
                                if 'value' in prop_value:
                                    data_fields[prop_key] = prop_value['value']
                                # Also check if the property has actual data as default
                                elif prop_key not in data_fields and 'default' in prop_value:
                                    data_fields[prop_key] = prop_value['default']
                                # Skip if it's just a schema definition (has 'type' but no actual data)
                                elif 'type' in prop_value and 'description' in prop_value:
                                    # This is a schema definition, not actual data - skip
                                    pass

                    if data_fields:
                        logger.info(
                            f'Detected DeepSeek V3.1 schema response, extracted fields: {list(data_fields.keys())}'
                        )
                        return data_fields
        except (json.JSONDecodeError, TypeError):
            pass

        # Strategy 1: Handle GLM markdown JSON format first
        if content.startswith('```json') and content.endswith('```'):
            try:
                json_content = content[7:-3].strip()  # Remove ```json and ```
                result = json.loads(json_content)
                logger.info('Successfully parsed GLM markdown JSON format')
                return result
            except json.JSONDecodeError:
                logger.debug('GLM markdown JSON parsing failed, trying other strategies')

        # Strategy 2: Try standard JSON parsing
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            logger.debug('Standard JSON parsing failed, trying alternative strategies')

        # Strategy 3: Use Pydantic's partial JSON parsing
        try:
            result = from_json(content, allow_partial=True)
            if isinstance(result, dict):
                logger.info('Successfully parsed with partial JSON parsing')
                return result
        except Exception:
            logger.debug('Partial JSON parsing failed, trying cleanup strategies')

        # Strategy 3.5: GLM "analysis then JSON" pattern - find LAST valid JSON in response
        # GLM often outputs analysis/thinking before the JSON, so look from the end
        try:
            # Find all positions where a JSON object might start
            brace_positions = [i for i, c in enumerate(content) if c == '{']

            # Try from the last position backwards (GLM puts JSON at the end)
            for pos in reversed(brace_positions):
                # Count braces to find matching closing brace
                depth = 0
                in_string = False
                escape_next = False
                end_pos = pos

                for i, c in enumerate(content[pos:], pos):
                    if escape_next:
                        escape_next = False
                        continue
                    if c == '\\' and in_string:
                        escape_next = True
                        continue
                    if c == '"' and not escape_next:
                        in_string = not in_string
                        continue
                    if in_string:
                        continue
                    if c == '{':
                        depth += 1
                    elif c == '}':
                        depth -= 1
                        if depth == 0:
                            end_pos = i + 1
                            break

                if depth == 0 and end_pos > pos:
                    candidate = content[pos:end_pos]
                    try:
                        result = json.loads(candidate)
                        if isinstance(result, dict) and len(result) > 0:
                            logger.info(
                                f'Successfully extracted JSON from GLM analysis+JSON response (pos {pos})'
                            )
                            return result
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            logger.debug(f'GLM analysis+JSON extraction failed: {e}')

        # Strategy 4: Extract JSON from verbose/explanatory text (GLM-4.5-FP8 reasoning)
        try:
            # Look for JSON objects embedded in explanatory text
            json_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
            matches = re.findall(json_pattern, content, re.DOTALL)

            for match in matches:
                try:
                    # Clean up the extracted JSON
                    cleaned = match.strip()
                    # Replace single quotes with double quotes for JSON validity
                    cleaned = re.sub(r"'([^']*)'", r'"\1"', cleaned)
                    # Fix trailing commas
                    cleaned = re.sub(r',\s*}', '}', cleaned)
                    cleaned = re.sub(r',\s*]', ']', cleaned)

                    result = json.loads(cleaned)
                    logger.info('Successfully extracted JSON from verbose GLM response')
                    return result
                except json.JSONDecodeError:
                    continue
            logger.debug('No valid JSON found in explanatory text, trying cleanup strategies')
        except Exception:
            logger.debug('JSON extraction from verbose text failed, trying cleanup strategies')

        # Strategy 5: Clean up common JSON formatting issues
        try:
            cleaned = content

            # Remove common prefixes
            prefixes = [
                'Here is the extraction:',
                'Here are the results:',
                'Extraction results:',
                'JSON output:',
                '```',
                'json',
                'JSON:',
            ]
            for prefix in prefixes:
                if cleaned.startswith(prefix):
                    cleaned = cleaned[len(prefix) :].strip()

            # Remove trailing markdown markers
            if cleaned.endswith('```'):
                cleaned = cleaned[:-3].strip()

            # Fix common JSON issues
            # Replace single quotes with double quotes
            cleaned = re.sub(r"'([^']*)'", r'"\1"', cleaned)

            # Fix trailing commas
            cleaned = re.sub(r',\s*}', '}', cleaned)
            cleaned = re.sub(r',\s*]', ']', cleaned)

            result = json.loads(cleaned)
            logger.info('Successfully parsed with cleanup strategies')
            return result
        except (json.JSONDecodeError, Exception):
            logger.debug('JSON cleanup failed, trying legacy methods')

        # Strategy 6: Python dict evaluation (legacy compatibility)
        if content.startswith('{') and content.endswith('}'):
            try:
                result = ast.literal_eval(content)
                if isinstance(result, dict):
                    logger.info('Successfully parsed as Python dict using ast.literal_eval')
                    return result
            except (ValueError, SyntaxError):
                logger.debug('ast.literal_eval failed, trying manual conversion')

        # Strategy 7: Manual conversion of Python syntax to JSON (legacy)
        try:
            # Replace Python boolean/null values with JSON equivalents
            json_content = content
            json_content = json_content.replace('True', 'true')
            json_content = json_content.replace('False', 'false')
            json_content = json_content.replace('None', 'null')

            # Replace single quotes with double quotes (careful with nested quotes)
            json_content = re.sub(r"'([^']*)':", r'"\1":', json_content)  # Keys
            json_content = re.sub(r":\s*'([^']*)'", r': "\1"', json_content)  # Values

            result = json.loads(json_content)
            logger.info('Successfully converted Python syntax to JSON')
            return result
        except (json.JSONDecodeError, Exception):
            logger.debug('Manual JSON conversion failed, trying regex extraction')

        # Strategy 8: Regex extraction for legacy patterns
        # Try to find entities array pattern
        entities_match = re.search(r"'entities':\s*\[(.*?)\]", content, re.DOTALL)
        if entities_match:
            try:
                entities_content = entities_match.group(1)
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
                return {
                    'relationships': self._extract_relationships_from_text(relationships_content)
                }
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
            entities.append({'name': name, 'type': entity_type, 'context': context})

        return entities

    def _extract_duplicates_from_text(self, text: str) -> list[dict]:
        """Extract duplicates from malformed text using regex patterns."""
        duplicates = []

        # Pattern for duplicate entries
        duplicate_pattern = r"\{'index':\s*(\d+),\s*'is_duplicate':\s*(True|False),\s*'confidence':\s*([\d.]+),\s*'reason':\s*'([^']*)'\}"
        matches = re.findall(duplicate_pattern, text)

        for index, is_dup, confidence, reason in matches:
            duplicates.append(
                {
                    'index': int(index),
                    'is_duplicate': is_dup == 'True',
                    'confidence': float(confidence),
                    'reason': reason,
                }
            )

        return duplicates

    def _extract_relationships_from_text(self, text: str) -> list[dict[str, str]]:
        """Extract relationships from malformed text using regex patterns."""
        relationships = []

        # Pattern for relationship entries
        rel_pattern = r"\{'source':\s*'([^']*)',\s*'target':\s*'([^']*)',\s*'relationship_type':\s*'([^']*)',\s*'context':\s*'([^']*)'\}"
        matches = re.findall(rel_pattern, text)

        for source, target, rel_type, context in matches:
            relationships.append(
                {
                    'source': source,
                    'target': target,
                    'relationship_type': rel_type,
                    'context': context,
                }
            )

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
            # Select model based on model_size parameter
            if model_size == ModelSize.small and self.config.small_model:
                selected_model = self.config.small_model
            else:
                selected_model = self.model or DEFAULT_MODEL

            logger.info(f'🔀 Chutes AI request: model={selected_model}, size={model_size.value}')

            ZAITokenTracker.wait_for_budget_sync()
            logger.info('Budget check passed, making HTTP request...')

            # GLM-4.5 returns empty content with json_schema format - use json_object instead
            response_format = typing.cast(typing.Any, {'type': 'json_object'})
            if response_model is not None:
                logger.debug(f'Using json_object format for schema: {response_model.__name__}')

            # Make the API request
            response = await self.client.chat.completions.create(
                model=selected_model,
                messages=openai_messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                response_format=response_format,
            )

            if not response.choices or not response.choices[0].message:
                logger.warning('Received malformed response structure from Chutes AI')
                raise ValueError('Malformed response structure from Chutes AI')

            # Record token usage for budget tracking (uses shared ZAITokenTracker)
            if response.usage and response.usage.total_tokens:
                total_tokens = response.usage.total_tokens
                ZAITokenTracker.record_usage(total_tokens, source=f'Chutes:{selected_model}')
            else:
                # Z.AI may not return usage info - estimate from request/response
                input_chars = sum(len(str(m.get('content', ''))) for m in openai_messages)
                output_chars = len(response.choices[0].message.content or '')
                estimated_tokens = (input_chars + output_chars) // 4
                ZAITokenTracker.record_usage(
                    estimated_tokens, source=f'Chutes:{selected_model}(est)'
                )

            # GLM-4.5-FP8 sometimes puts response in reasoning_content instead of content
            message = response.choices[0].message
            result = message.content or ''

            # Check reasoning_content field if content is empty (GLM-4.5-FP8 behavior)
            reasoning_content = getattr(message, 'reasoning_content', None)
            if not result.strip() and isinstance(reasoning_content, str) and reasoning_content:
                result = reasoning_content
                logger.debug('Using reasoning_content field from GLM-4.5-FP8 response')

            # Handle empty or whitespace-only responses
            if not result.strip():
                logger.warning('Received empty response content from Chutes AI')
                raise ValueError('Empty response content from Chutes AI')

            # Try multiple parsing strategies to extract valid format
            parsed_response = self._parse_chutes_response(result)
            if parsed_response is not None:
                logger.debug(f'Successfully parsed Chutes AI response')

                # Validate against response model if provided (similar to Cerebras client fix)
                if response_model is not None:
                    try:
                        validated_model = response_model.model_validate(parsed_response)
                        # Return as a dictionary for API consistency
                        validated_response = validated_model.model_dump()
                        logger.debug(
                            f'Successfully validated response against model {response_model.__name__}'
                        )
                        return validated_response
                    except Exception as e:
                        logger.error(
                            f'Failed to validate Chutes response against model {response_model.__name__}: {e}'
                        )
                        logger.error(
                            f'Raw response that failed validation: {json.dumps(parsed_response, indent=2)[:500]}...'
                        )
                        raise e

                return parsed_response

            # If all parsing strategies fail, this is a wasted request
            logger.error(
                f'All parsing strategies failed for Chutes response: {repr(result[:500])}...'
            )
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

        # Add GLM-specific strict JSON instructions to SYSTEM message
        messages[0].content += (
            '\n\nCRITICAL OUTPUT RULES:'
            '\n- You MUST output ONLY valid JSON, nothing else.'
            '\n- NO explanations, NO analysis, NO thinking, NO commentary.'
            '\n- Your entire response must be a single JSON object starting with { and ending with }.'
            '\n- Any text before or after the JSON will cause a system error.'
        )

        # Reinforce in user message with stronger phrasing
        messages[-1].content += (
            '\n\n⚠️ STRICT REQUIREMENT: Output ONLY the raw JSON object. '
            'Do NOT write any analysis, explanation, or text before the JSON. '
            'Start your response IMMEDIATELY with { - any other text will cause failure.'
        )

        # Debug logging: Track summary generation calls
        # Use response_model type to accurately detect summary calls
        # (previous content-based detection had false positives with dedupe prompts)
        is_summary_call = (
            response_model is not None
            and hasattr(response_model, 'model_fields')
            and 'summary' in response_model.model_fields
        )
        if is_summary_call:
            logger.debug(f'🔍 ChutesClient: Summary generation call detected')
            logger.debug(
                f'   Response model: {response_model.__name__ if response_model else "None"}'
            )

        while retry_count <= self.MAX_RETRIES:
            try:
                response = await self._generate_response(
                    messages, response_model, max_tokens=max_tokens, model_size=model_size
                )

                # Debug logging: Track summary responses
                if is_summary_call:
                    logger.debug(f'🔍 ChutesClient: Summary response received')
                    if isinstance(response, dict):
                        logger.debug(f'   Response keys: {list(response.keys())}')
                        if 'summary' in response:
                            summary_text = response['summary']
                            logger.debug(f'   Summary generated: {len(summary_text)} characters')
                            logger.info(
                                f'✅ ChutesClient generated summary: {len(summary_text)} chars'
                            )
                        else:
                            logger.warning(f"⚠️ ChutesClient: No 'summary' key in response!")
                            logger.debug(f'   Available keys: {list(response.keys())}')

                            # Try to recover summary from alternative fields
                            summary_recovered = False
                            for alt_key in ['content', 'text', 'result', 'output']:
                                if alt_key in response and isinstance(response[alt_key], str):
                                    response['summary'] = response[alt_key]
                                    logger.info(
                                        f"✅ ChutesClient: Recovered summary from '{alt_key}' field: {len(response['summary'])} chars"
                                    )
                                    summary_recovered = True
                                    break

                            if not summary_recovered and is_summary_call:
                                # For summary calls, this is unacceptable - raise error to trigger retry
                                logger.error(
                                    f'❌ ChutesClient: Failed to extract summary from response: {response}'
                                )
                                raise ValueError(
                                    'ChutesClient: Summary extraction failed - no valid summary field found'
                                )

                    else:
                        logger.warning(f'⚠️ ChutesClient: Response is not dict: {type(response)}')
                        if is_summary_call:
                            # Summary calls must return dict format
                            raise ValueError(
                                'ChutesClient: Summary call returned non-dict response'
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
                if any(
                    keyword in error_msg
                    for keyword in ['json', 'empty response', 'malformed response']
                ):
                    logger.error(f'Non-retryable error (would waste API requests): {e}')
                    raise
                # Other ValueError types can be retried with backoff
                last_error = e
                if retry_count >= self.MAX_RETRIES:
                    logger.error(f'Max retries ({self.MAX_RETRIES}) exceeded. Last error: {e}')
                    raise
                retry_count += 1

                # Add delay before retry to be API-friendly
                import random

                delay = min(self.BASE_RETRY_DELAY * (2 ** (retry_count - 1)), self.MAX_RETRY_DELAY)
                delay += random.uniform(-delay * 0.2, delay * 0.2)
                logger.warning(
                    f'ValueError retry {retry_count}/{self.MAX_RETRIES}, waiting {delay:.1f}s...'
                )
                await asyncio.sleep(delay)
            except Exception as e:
                last_error = e

                # Don't retry if we've hit the max retries
                if retry_count >= self.MAX_RETRIES:
                    logger.error(f'Max retries ({self.MAX_RETRIES}) exceeded. Last error: {e}')
                    raise

                retry_count += 1

                # Calculate exponential backoff delay to be API-friendly
                import random

                delay = min(self.BASE_RETRY_DELAY * (2 ** (retry_count - 1)), self.MAX_RETRY_DELAY)
                # Add jitter (±20%) to prevent thundering herd
                delay += random.uniform(-delay * 0.2, delay * 0.2)

                logger.warning(
                    f'Retrying after error (attempt {retry_count}/{self.MAX_RETRIES}): {e}. '
                    f'Waiting {delay:.1f}s before retry...'
                )

                await asyncio.sleep(delay)

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

        # If we somehow get here, raise the last error
        raise last_error or Exception('Max retries exceeded with no specific error')

    # ============================================================================
    # Batch Processing Methods
    # ============================================================================

    async def extract_entities_batch(
        self, episodes: List[str], max_tokens: int = 4096, optimal_batch_size: int = 5
    ) -> 'BatchProcessingResult':
        """
        Extract entities and relationships from a batch of episodes using robust parsing.

        This method implements the proven batch processing approach that reduces
        API calls by up to 80% while maintaining extraction quality.

        Args:
            episodes: List of episode texts to process
            max_tokens: Maximum tokens for the LLM response
            optimal_batch_size: Preferred batch size (5-6 is optimal based on testing)

        Returns:
            BatchProcessingResult with all extracted entities and relationships
        """
        if not episodes:
            return BatchProcessingResult()

        # Initialize robust parser
        parser = RobustJSONParser()

        # Determine actual batch size (don't exceed optimal size or episode count)
        batch_size = min(len(episodes), optimal_batch_size)
        batch_episodes = episodes[:batch_size]

        # Create optimized prompt for batch extraction
        system_prompt = self._get_batch_system_prompt(batch_size)
        user_prompt = self._create_batch_user_prompt(batch_episodes)

        # Create messages for LLM
        messages = [
            Message(role='system', content=system_prompt),
            Message(role='user', content=user_prompt),
        ]

        try:
            logger.info(f'Processing batch of {batch_size} episodes with Chutes AI')

            # Make API call with extended timeout for batch processing
            response = await self._generate_response(
                messages, max_tokens=max_tokens, model_size=ModelSize.medium
            )

            # Convert response to string for parsing
            content = ''
            if isinstance(response, dict):
                content = json.dumps(response)
            else:
                content = str(response)

            # Parse with robust parser
            result = parser.parse(content, expected_episodes=batch_size)

            # Add success metadata
            result.parsing_metadata['api_call'] = 'success'
            result.parsing_metadata['batch_size'] = batch_size
            result.parsing_metadata['model'] = self.model or DEFAULT_MODEL

            logger.info(
                f'Batch extraction completed: {result.total_entities} entities, '
                f'{result.total_relationships} relationships'
            )

            return result

        except Exception as e:
            logger.error(f'Batch extraction failed: {e}')

            # Return empty result with error metadata
            return BatchProcessingResult(
                episodes=[BatchEpisodeResult(episode_index=i) for i in range(batch_size)],
                parsing_metadata={'api_call': 'failed', 'error': str(e), 'batch_size': batch_size},
            )

    def _get_batch_system_prompt(self, batch_size: int) -> str:
        """Get optimized system prompt for batch processing."""
        return f"""You are an expert entity and relationship extractor.
You will process {batch_size} episodes and extract ALL entities and relationships.

CRITICAL: You MUST return valid JSON in this exact format:
{{
    "episodes": [
        {{
            "entities": [
                {{"name": "Entity Name", "type": "entity_type", "context": "brief context"}}
            ],
            "relationships": [
                {{"source": "Entity1", "target": "Entity2", "relationship_type": "RELATIONSHIP_TYPE", "context": "brief context"}}
            ]
        }}
    ]
}}

Rules:
1. Return ONLY valid JSON, no other text
2. Process ALL {batch_size} episodes completely  
3. Extract ALL entities and relationships from each episode
4. Use descriptive relationship types in SCREAMING_SNAKE_CASE
5. Entity types: person, organization, location, technology, event, concept
6. Provide brief context for entities and relationships
7. Ensure each episode has an entry in the episodes array"""

    def _create_batch_user_prompt(self, episodes: List[str]) -> str:
        """Create user prompt for batch extraction."""
        prompt = f'Extract entities and relationships from these {len(episodes)} episodes:\n\n'

        for i, episode in enumerate(episodes):
            prompt += f'Episode {i}:\n{episode}\n\n'

        prompt += '\nReturn the extraction results as valid JSON following the specified format.'
        return prompt

    async def extract_entities_batch_parallel(
        self,
        episodes: List[str],
        max_concurrent: int = 3,
        batch_size: int = 5,
        max_tokens: int = 4096,
    ) -> List['BatchProcessingResult']:
        """
        Process multiple batches of episodes in parallel for maximum efficiency.

        This method splits episodes into optimal batch sizes and processes them
        concurrently to maximize quota efficiency and speed.

        Args:
            episodes: List of all episode texts to process
            max_concurrent: Maximum number of parallel API calls
            batch_size: Size of each batch (5-6 is optimal)
            max_tokens: Maximum tokens per API call

        Returns:
            List of BatchProcessingResult objects, one per batch
        """
        if not episodes:
            return []

        # Split episodes into batches
        batches = []
        for i in range(0, len(episodes), batch_size):
            batch = episodes[i : i + batch_size]
            batches.append(batch)

        # Limit concurrent batches
        if len(batches) > max_concurrent:
            logger.info(f'Processing {len(batches)} batches in groups of {max_concurrent}')

        # Process batches in parallel groups
        all_results = []

        for i in range(0, len(batches), max_concurrent):
            batch_group = batches[i : i + max_concurrent]

            # Create tasks for this group
            tasks = []
            for batch in batch_group:
                task = self.extract_entities_batch(
                    batch, max_tokens=max_tokens, optimal_batch_size=batch_size
                )
                tasks.append(task)

            # Execute this group in parallel
            try:
                group_results = await asyncio.gather(*tasks, return_exceptions=True)

                # Process results
                for result in group_results:
                    if isinstance(result, Exception):
                        logger.error(f'Batch failed: {result}')
                        # Create empty result for failed batch
                        all_results.append(
                            BatchProcessingResult(
                                parsing_metadata={'api_call': 'failed', 'error': str(result)}
                            )
                        )
                    else:
                        all_results.append(result)

            except Exception as e:
                logger.error(f'Batch group processing failed: {e}')
                # Add empty results for this failed group
                for _ in batch_group:
                    all_results.append(
                        BatchProcessingResult(
                            parsing_metadata={'api_call': 'failed', 'error': str(e)}
                        )
                    )

        logger.info(f'Parallel batch processing completed: {len(all_results)} batches')
        return all_results

    def calculate_batch_efficiency(
        self, total_episodes: int, batch_results: List['BatchProcessingResult']
    ) -> Dict[str, Any]:
        """
        Calculate efficiency metrics for batch processing.

        Args:
            total_episodes: Total number of episodes processed
            batch_results: Results from batch processing

        Returns:
            Dictionary with efficiency metrics
        """
        successful_batches = [
            r for r in batch_results if r.parsing_metadata.get('api_call') == 'success'
        ]

        # Calculate totals
        total_entities = sum(r.total_entities for r in successful_batches)
        total_relationships = sum(r.total_relationships for r in successful_batches)
        total_api_calls = len(batch_results)

        # Calculate efficiency
        sequential_calls = total_episodes  # 1 call per episode in sequential processing
        quota_savings = (
            ((sequential_calls - total_api_calls) / sequential_calls) * 100
            if sequential_calls > 0
            else 0
        )
        api_efficiency = total_episodes / total_api_calls if total_api_calls > 0 else 0

        # Success rate
        success_rate = (len(successful_batches) / len(batch_results)) * 100 if batch_results else 0

        # Parsing strategy distribution
        strategies = {}
        for result in successful_batches:
            strategy = result.parsing_metadata.get('strategy', 'unknown')
            strategies[strategy] = strategies.get(strategy, 0) + 1

        return {
            'total_episodes': total_episodes,
            'total_api_calls': total_api_calls,
            'quota_savings_percent': quota_savings,
            'api_efficiency_multiplier': api_efficiency,
            'success_rate_percent': success_rate,
            'total_entities': total_entities,
            'total_relationships': total_relationships,
            'avg_entities_per_episode': total_entities / total_episodes
            if total_episodes > 0
            else 0,
            'parsing_strategies': strategies,
            'successful_batches': len(successful_batches),
            'failed_batches': len(batch_results) - len(successful_batches),
        }

    async def dedupe_entities_batch(
        self,
        episodes_nodes: List[List[Dict[str, Any]]],
        episode_contents: List[str],
        existing_nodes: List[Dict[str, Any]] | None = None,
        *,
        existing_nodes_text: str | None = None,
        batch_size: int = 5,
    ) -> Dict[str, Any]:
        """
        Deduplicate entities from multiple episodes in a single API call.

        Args:
            episodes_nodes: List of node lists, one per episode
            episode_contents: List of episode content strings
            existing_nodes: Previously seen nodes to check against
            batch_size: Maximum episodes per API call

        Returns:
            Dictionary with deduplication results
        """
        if not episodes_nodes:
            return {'entity_resolutions': []}

        existing_nodes_list = list(existing_nodes or [])
        compressor = get_prompt_compressor()

        metadata = [
            {
                'idx': idx,
                'name': node.get('name', ''),
                'uuid': node.get('uuid', ''),
                'labels': node.get('labels', []),
            }
            for idx, node in enumerate(existing_nodes_list)
        ]

        context_existing_text = existing_nodes_text
        if context_existing_text is None and existing_nodes_list:
            compress_for_batch = getattr(compressor, 'compress_existing_entities_for_batch', None)
            if callable(compress_for_batch):
                compress_for_batch_fn = typing.cast(
                    typing.Callable[[list[dict[str, Any]]], object],
                    compress_for_batch,
                )
                compression_result = compress_for_batch_fn(existing_nodes_list)
                if isinstance(compression_result, tuple) and len(compression_result) == 2:
                    context_existing_text = typing.cast(str, compression_result[0])
                    compression_stats = compression_result[1]
                    if (
                        getattr(compression_stats, 'original_tokens', 0)
                        and getattr(compression_stats, 'compression_ratio', 1.0) < 0.95
                    ):
                        logger.debug(
                            'Chutes batch dedup compression stats: %s',
                            getattr(compression_stats, '__dict__', {}),
                        )

        existing_nodes_block = context_existing_text or ''

        # Build prompt for batch deduplication
        prompt_context = {
            'extracted_nodes': [],
            'existing_nodes': metadata,
            'existing_nodes_text': existing_nodes_block,
            'episode_content': '\n\n'.join(episode_contents),
            'previous_episodes': [],
        }

        # Flatten nodes with episode tracking
        for episode_idx, nodes in enumerate(episodes_nodes):
            for node in nodes:
                node_with_episode = {
                    **node,
                    'episode_index': episode_idx,
                    'duplication_candidates': metadata,
                }
                prompt_context['extracted_nodes'].append(node_with_episode)

        # Build the prompt using the existing deduplication prompt template
        from graphiti_core.prompts import prompt_library

        messages = prompt_library.dedupe_nodes.nodes(prompt_context)

        # Make single API call for batch deduplication
        try:
            response = await self.generate_response(
                messages,
                response_model=None,  # We'll parse manually for robustness
            )

            # Parse the response with robust handling
            return self._parse_deduplication_response(response, len(episodes_nodes))

        except Exception as e:
            logger.error(f'Batch deduplication failed: {e}')
            # Return empty resolutions on error
            return {'entity_resolutions': []}

    def _parse_deduplication_response(
        self, response: Dict[str, Any], episode_count: int
    ) -> Dict[str, Any]:
        """
        Parse deduplication response with robust error handling.

        Args:
            response: Raw response from API
            episode_count: Number of episodes being processed

        Returns:
            Parsed deduplication results
        """
        if isinstance(response, dict) and 'entity_resolutions' in response:
            return response

        # Try to extract resolutions from various response formats
        if isinstance(response, str):
            try:
                import json

                parsed = json.loads(response)
                if 'entity_resolutions' in parsed:
                    return parsed
            except:
                pass

        # Fallback: return empty resolutions
        logger.warning('Could not parse deduplication response, returning empty resolutions')
        return {'entity_resolutions': []}


# ============================================================================
# Pydantic Models for Batch Processing
# ============================================================================


class BatchEntity(BaseModel):
    """Entity extracted from batch processing."""

    name: str = Field(..., min_length=1, description='Entity name')
    type: str = Field(..., description='Entity type')
    context: str = Field(default='', description='Entity context')

    @field_validator('name')
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Ensure name is not just whitespace."""
        if not v.strip():
            raise ValueError('Entity name cannot be empty or whitespace')
        return v.strip()


class BatchRelationship(BaseModel):
    """Relationship extracted from batch processing."""

    source: str = Field(..., min_length=1, description='Source entity name')
    target: str = Field(..., min_length=1, description='Target entity name')
    relationship_type: str = Field(..., description='Type of relationship')
    context: str = Field(default='', description='Relationship context')

    @field_validator('source', 'target')
    @classmethod
    def validate_entity_names(cls, v: str) -> str:
        """Ensure entity names are not just whitespace."""
        if not v.strip():
            raise ValueError('Entity name cannot be empty or whitespace')
        return v.strip()


class BatchEpisodeResult(BaseModel):
    """Results for a single episode in batch processing."""

    episode_index: int = Field(..., ge=0)
    entities: List[BatchEntity] = Field(default_factory=list)
    relationships: List[BatchRelationship] = Field(default_factory=list)

    def is_empty(self) -> bool:
        """Check if this episode has no extractions."""
        return len(self.entities) == 0 and len(self.relationships) == 0


class BatchProcessingResult(BaseModel):
    """Complete batch processing results."""

    episodes: List[BatchEpisodeResult] = Field(default_factory=list)
    total_entities: int = Field(default=0)
    total_relationships: int = Field(default=0)
    parsing_metadata: Dict[str, Any] = Field(default_factory=dict)

    def calculate_totals(self):
        """Calculate total counts from episodes."""
        self.total_entities = sum(len(ep.entities) for ep in self.episodes)
        self.total_relationships = sum(len(ep.relationships) for ep in self.episodes)


# ============================================================================
# Robust JSON Parser with Multiple Strategies
# ============================================================================


class RobustJSONParser:
    """
    Robust JSON parser implementing best practices from Pydantic documentation.
    Uses multiple strategies with fallback chain for parsing LLM outputs.
    """

    def __init__(self):
        self.strategies = [
            self._parse_clean_json,
            self._parse_markdown_json,
            self._parse_with_cleanup,
            self._parse_partial_json,
            self._parse_with_regex_extraction,
            self._parse_individual_episodes,
            self._parse_with_recovery,
        ]

    def parse(self, content: str, expected_episodes: int) -> BatchProcessingResult:
        """
        Parse content using multiple strategies until one succeeds.

        Args:
            content: Raw LLM output to parse
            expected_episodes: Number of episodes we expect to find

        Returns:
            BatchProcessingResult with parsed data
        """
        errors = []

        for strategy in self.strategies:
            try:
                logger.debug(f'Trying parsing strategy: {strategy.__name__}')
                result = strategy(content, expected_episodes)

                # Validate we got reasonable results
                if self._validate_result(result, expected_episodes):
                    logger.info(f'Successfully parsed with strategy: {strategy.__name__}')
                    result.parsing_metadata['strategy'] = strategy.__name__
                    return result
                else:
                    logger.debug(f'Strategy {strategy.__name__} returned invalid results')

            except Exception as e:
                logger.debug(f'Strategy {strategy.__name__} failed: {e}')
                errors.append((strategy.__name__, str(e)))

        # If all strategies fail, return empty result with error info
        logger.warning(f'All parsing strategies failed. Errors: {errors}')
        return BatchProcessingResult(
            episodes=[BatchEpisodeResult(episode_index=i) for i in range(expected_episodes)],
            parsing_metadata={'errors': errors, 'strategy': 'fallback_empty'},
        )

    def _validate_result(self, result: BatchProcessingResult, expected_episodes: int) -> bool:
        """Validate that parsing result is reasonable."""
        # Check we have the right number of episodes
        if len(result.episodes) != expected_episodes:
            return False

        # Check at least some episodes have content
        non_empty = sum(1 for ep in result.episodes if not ep.is_empty())
        if non_empty == 0:
            return False

        # Check episode indices are correct
        for i, ep in enumerate(result.episodes):
            if ep.episode_index != i:
                return False

        return True

    def _parse_clean_json(self, content: str, expected_episodes: int) -> BatchProcessingResult:
        """Strategy 1: Parse clean JSON directly."""
        data = json.loads(content)
        return self._convert_to_result(data, expected_episodes)

    def _parse_markdown_json(self, content: str, expected_episodes: int) -> BatchProcessingResult:
        """Strategy 2: Extract JSON from markdown code blocks."""
        # Look for ```json ... ``` blocks
        pattern = r'```json\s*(.*?)\s*```'
        matches = re.findall(pattern, content, re.DOTALL)

        if matches:
            # Try each JSON block found
            for json_str in matches:
                try:
                    data = json.loads(json_str)
                    return self._convert_to_result(data, expected_episodes)
                except:
                    continue

        raise ValueError('No valid JSON found in markdown blocks')

    def _parse_with_cleanup(self, content: str, expected_episodes: int) -> BatchProcessingResult:
        """Strategy 3: Clean up common JSON formatting issues."""
        # Remove common prefixes/suffixes
        cleaned = content.strip()

        # Remove common prefixes
        prefixes = [
            'Here is the extraction:',
            'Here are the results:',
            'Extraction results:',
            'JSON output:',
            '```',
            'json',
            'JSON:',
        ]
        for prefix in prefixes:
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix) :].strip()

        # Remove trailing markdown markers
        if cleaned.endswith('```'):
            cleaned = cleaned[:-3].strip()

        # Fix common JSON issues
        # Replace single quotes with double quotes
        cleaned = re.sub(r"'([^']*)'", r'"\1"', cleaned)

        # Fix trailing commas
        cleaned = re.sub(r',\s*}', '}', cleaned)
        cleaned = re.sub(r',\s*]', ']', cleaned)

        data = json.loads(cleaned)
        return self._convert_to_result(data, expected_episodes)

    def _parse_partial_json(self, content: str, expected_episodes: int) -> BatchProcessingResult:
        """Strategy 4: Use Pydantic's partial JSON parsing."""
        try:
            # Use pydantic_core's from_json with allow_partial
            data = from_json(content, allow_partial=True)
            return self._convert_to_result(data, expected_episodes)
        except Exception as e:
            # Try with trailing-strings mode for incomplete strings
            data = from_json(content, allow_partial='trailing-strings')
            return self._convert_to_result(data, expected_episodes)

    def _parse_with_regex_extraction(
        self, content: str, expected_episodes: int
    ) -> BatchProcessingResult:
        """Strategy 5: Extract structured data using regex patterns."""
        result = BatchProcessingResult()

        # Pattern for episode blocks
        episode_pattern = r'Episode\s+(\d+)[:\s]*\n(.*?)(?=Episode\s+\d+|$)'
        episode_matches = re.findall(episode_pattern, content, re.DOTALL | re.IGNORECASE)

        for episode_idx, episode_content in episode_matches:
            idx = int(episode_idx)
            if idx >= expected_episodes:
                continue

            episode = BatchEpisodeResult(episode_index=idx)

            # Extract entities
            entity_pattern = r'(?:Entity|Person|Organization|Location|Technology):\s*([^,\n]+)(?:\s*\(([^)]+)\))?'
            for match in re.finditer(entity_pattern, episode_content, re.IGNORECASE):
                name = match.group(1).strip()
                entity_type = match.group(2).strip() if match.group(2) else 'unknown'
                if name:
                    episode.entities.append(BatchEntity(name=name, type=entity_type))

            # Extract relationships
            rel_pattern = (
                r'([^,\n]+)\s+(?:->|→|relates to|connected to)\s+([^,\n]+)(?:\s*\(([^)]+)\))?'
            )
            for match in re.finditer(rel_pattern, episode_content, re.IGNORECASE):
                source = match.group(1).strip()
                target = match.group(2).strip()
                rel_type = match.group(3).strip() if match.group(3) else 'RELATED_TO'
                if source and target:
                    episode.relationships.append(
                        BatchRelationship(
                            source=source,
                            target=target,
                            relationship_type=rel_type,
                        )
                    )

            result.episodes.append(episode)

        # Fill in missing episodes
        existing_indices = {ep.episode_index for ep in result.episodes}
        for i in range(expected_episodes):
            if i not in existing_indices:
                result.episodes.append(BatchEpisodeResult(episode_index=i))

        # Sort by index
        result.episodes.sort(key=lambda x: x.episode_index)
        result.calculate_totals()

        return result

    def _parse_individual_episodes(
        self, content: str, expected_episodes: int
    ) -> BatchProcessingResult:
        """Strategy 6: Try to parse each episode individually."""
        result = BatchProcessingResult()

        # Try to find JSON arrays or objects for each episode
        json_pattern = r'(\{[^{}]*\}|\[[^\[\]]*\])'
        json_matches = re.findall(json_pattern, content)

        episode_idx = 0
        for json_str in json_matches:
            if episode_idx >= expected_episodes:
                break

            try:
                data = json.loads(json_str)
                episode = BatchEpisodeResult(episode_index=episode_idx)

                # Try to extract entities and relationships from the data
                if isinstance(data, dict):
                    # Look for entities key
                    for key in ['entities', 'entity', 'extracted_entities', 'extractedEntities']:
                        if key in data:
                            entities = data[key]
                            if isinstance(entities, list):
                                for e in entities:
                                    if isinstance(e, dict):
                                        # Handle field name variations from different LLMs
                                        entity_name = (
                                            e.get('name')
                                            or e.get('entity_name')
                                            or e.get('entityName')
                                        )
                                        if entity_name:
                                            episode.entities.append(
                                                BatchEntity(
                                                    name=entity_name,
                                                    type=e.get(
                                                        'type', e.get('entity_type', 'unknown')
                                                    ),
                                                    context=e.get('context', ''),
                                                )
                                            )

                    # Look for relationships key
                    for key in ['relationships', 'relations', 'edges']:
                        if key in data:
                            relationships = data[key]
                            if isinstance(relationships, list):
                                for r in relationships:
                                    if isinstance(r, dict) and 'source' in r and 'target' in r:
                                        episode.relationships.append(
                                            BatchRelationship(
                                                source=r['source'],
                                                target=r['target'],
                                                relationship_type=r.get(
                                                    'relationship_type', r.get('type', 'RELATED_TO')
                                                ),
                                                context=r.get('context', ''),
                                            )
                                        )

                result.episodes.append(episode)
                episode_idx += 1

            except:
                continue

        # Fill in missing episodes
        while len(result.episodes) < expected_episodes:
            result.episodes.append(BatchEpisodeResult(episode_index=len(result.episodes)))

        result.calculate_totals()
        return result

    def _parse_with_recovery(self, content: str, expected_episodes: int) -> BatchProcessingResult:
        """Strategy 7: Best-effort recovery parsing."""
        result = BatchProcessingResult()

        # Create empty episodes
        for i in range(expected_episodes):
            result.episodes.append(BatchEpisodeResult(episode_index=i))

        # Try to extract any entities we can find
        entity_patterns = [
            r'"name":\s*"([^"]+)"',
            r'(?:Entity|Person|Organization):\s*([^,\n]+)',
            r'\b([A-Z][a-z]+ [A-Z][a-z]+)\b',  # Proper names
        ]

        entities_found = []
        for pattern in entity_patterns:
            for match in re.finditer(pattern, content):
                name = match.group(1).strip()
                if name and len(name) > 2:
                    entities_found.append(name)

        # Distribute entities across episodes
        if entities_found:
            entities_per_episode = max(1, len(entities_found) // expected_episodes)
            for i, entity_name in enumerate(entities_found):
                episode_idx = min(i // entities_per_episode, expected_episodes - 1)
                result.episodes[episode_idx].entities.append(
                    BatchEntity(name=entity_name, type='unknown', context='')
                )

        result.calculate_totals()
        return result

    def _convert_to_result(self, data: Any, expected_episodes: int) -> BatchProcessingResult:
        """Convert parsed data to BatchProcessingResult."""
        result = BatchProcessingResult()

        # Handle different data structures
        if isinstance(data, dict):
            # Look for episodes key
            if 'episodes' in data:
                episodes_data = data['episodes']
            elif 'results' in data:
                episodes_data = data['results']
            elif 'extractions' in data:
                episodes_data = data['extractions']
            else:
                # Treat the whole dict as a single episode
                episodes_data = [data]
        elif isinstance(data, list):
            episodes_data = data
        else:
            raise ValueError(f'Unexpected data type: {type(data)}')

        # Parse each episode
        for i, episode_data in enumerate(episodes_data):
            if i >= expected_episodes:
                break

            episode = BatchEpisodeResult(episode_index=i)

            if isinstance(episode_data, dict):
                # Extract entities - handle field name variations from different LLMs
                entities = (
                    episode_data.get('entities')
                    or episode_data.get('extracted_entities')
                    or episode_data.get('extractedEntities')
                    or []
                )
                if isinstance(entities, list):
                    for e in entities:
                        if isinstance(e, dict):
                            # Handle field name variations
                            entity_name = (
                                e.get('name') or e.get('entity_name') or e.get('entityName')
                            )
                            if entity_name:
                                try:
                                    episode.entities.append(
                                        BatchEntity(
                                            name=entity_name,
                                            type=e.get('type', e.get('entity_type', 'unknown')),
                                            context=e.get('context', ''),
                                        )
                                    )
                                except ValidationError:
                                    continue

                # Extract relationships
                relationships = episode_data.get('relationships', episode_data.get('relations', []))
                if isinstance(relationships, list):
                    for r in relationships:
                        if isinstance(r, dict) and 'source' in r and 'target' in r:
                            try:
                                episode.relationships.append(
                                    BatchRelationship(
                                        source=r['source'],
                                        target=r['target'],
                                        relationship_type=r.get(
                                            'relationship_type', r.get('type', 'RELATED_TO')
                                        ),
                                        context=r.get('context', ''),
                                    )
                                )
                            except ValidationError:
                                continue

            result.episodes.append(episode)

        # Fill in any missing episodes
        existing_indices = {ep.episode_index for ep in result.episodes}
        for i in range(expected_episodes):
            if i not in existing_indices:
                result.episodes.append(BatchEpisodeResult(episode_index=i))

        # Sort by index and calculate totals
        result.episodes.sort(key=lambda x: x.episode_index)
        result.calculate_totals()

        return result
