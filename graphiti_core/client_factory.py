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

import logging
import os
from typing import Optional

from graphiti_core.cross_encoder.openai_reranker_client import OpenAIRerankerClient
from graphiti_core.embedder import EmbedderClient, OpenAIEmbedder, OpenAIEmbedderConfig
from graphiti_core.llm_client import LLMClient, LLMConfig, OpenAIClient
from graphiti_core.llm_client.cerebras_client import CerebrasClient
from graphiti_core.llm_client.fallback_client import FallbackLLMClient

logger = logging.getLogger(__name__)


class GraphitiClientFactory:
    """Centralized factory for creating Graphiti clients with environment-aware configuration."""

    @staticmethod
    def create_llm_client() -> Optional[LLMClient]:
        """Create LLM client based on environment configuration."""
        logger.info("=== GraphitiClientFactory.create_llm_client() called ===")
        cerebras_client = None
        ollama_client = None
        
        # Check if we should enable fallback mode
        use_fallback = os.getenv('ENABLE_FALLBACK', 'true').lower() == 'true'
        
        # Debug environment variables
        use_cerebras_raw = os.getenv('USE_CEREBRAS', '')
        use_cerebras_lower = use_cerebras_raw.lower()
        logger.info(f'Environment check: USE_CEREBRAS="{use_cerebras_raw}" -> "{use_cerebras_lower}" -> {use_cerebras_lower == "true"}')
        
        # Try to create Cerebras client
        if use_cerebras_lower == 'true':
            try:
                cerebras_model = os.getenv('CEREBRAS_MODEL', 'qwen-3-coder-480b')
                cerebras_small_model = os.getenv('CEREBRAS_SMALL_MODEL', 'qwen-3-32b')
                cerebras_api_key = os.getenv('CEREBRAS_API_KEY')
                
                logger.info(
                    f'Creating Cerebras LLM client with model {cerebras_model}'
                )
                logger.info(f'Cerebras API key present: {cerebras_api_key is not None}')
                logger.info(f'USE_CEREBRAS={os.getenv("USE_CEREBRAS")}, use_fallback={use_fallback}')
                
                config = LLMConfig(
                    api_key=cerebras_api_key,
                    model=cerebras_model,
                    small_model=cerebras_small_model,
                    temperature=0.7,  # Recommended temperature for qwen-3-coder-480b
                    max_tokens=4000,
                    # Note: top_p=0.8 recommended but not exposed in current config
                )
                logger.info('LLMConfig created successfully')
                
                logger.info('About to instantiate CerebrasClient...')
                cerebras_client = CerebrasClient(config=config)
                logger.info('CerebrasClient instantiated successfully!')
                
                # If fallback is disabled, return just Cerebras
                if not use_fallback:
                    logger.info('Fallback disabled, returning Cerebras client only')
                    return cerebras_client
                else:
                    logger.info('Fallback enabled, will create Ollama client next')
                    
            except Exception as e:
                logger.error(f'Failed to create Cerebras LLM client: {e}')
                logger.error(f'Exception type: {type(e).__name__}')
                import traceback
                logger.error(f'Full traceback: {traceback.format_exc()}')
                if not use_fallback:
                    logger.info('Falling back to OpenAI LLM client')
        
        # Try to create Ollama client (for standalone use or as fallback)
        if os.getenv('USE_OLLAMA', '').lower() == 'true' or (cerebras_client and use_fallback):
            try:
                from openai import AsyncOpenAI

                ollama_base_url = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434/v1')
                ollama_model = os.getenv('OLLAMA_MODEL', 'mistral:latest')

                logger.info(
                    f'Creating Ollama LLM client with model {ollama_model} at {ollama_base_url}'
                )

                client = AsyncOpenAI(base_url=ollama_base_url, api_key='ollama')

                config = LLMConfig(
                    model=ollama_model, small_model=ollama_model, temperature=0.7, max_tokens=2000
                )

                ollama_client = OpenAIClient(config=config, client=client)
                
                # If we have both Cerebras and Ollama with fallback enabled, create fallback client
                if cerebras_client and ollama_client and use_fallback:
                    logger.info('Creating fallback LLM client (Cerebras primary, Ollama backup)')
                    return FallbackLLMClient(
                        primary_client=cerebras_client,
                        fallback_client=ollama_client
                    )
                
                # Return just Ollama if no Cerebras
                if ollama_client and not cerebras_client:
                    return ollama_client
                    
            except Exception as e:
                logger.error(f'Failed to create Ollama LLM client: {e}')
                # If we have Cerebras but couldn't create Ollama fallback, return just Cerebras
                if cerebras_client:
                    logger.warning('Running without fallback - Ollama unavailable')
                    return cerebras_client
                logger.info('Falling back to OpenAI LLM client')

        # If we have just Cerebras without fallback
        if cerebras_client:
            return cerebras_client

        # Default to OpenAI client
        return OpenAIClient()

    @staticmethod
    def _get_embedding_endpoint() -> str:
        """Determine the appropriate embedding endpoint."""
        use_dedicated = os.getenv('USE_DEDICATED_EMBEDDING_ENDPOINT', 'false').lower() == 'true'
        
        if use_dedicated:
            dedicated_url = os.getenv('OLLAMA_EMBEDDING_BASE_URL')
            if dedicated_url:
                logger.info(f'Using dedicated embedding endpoint: {dedicated_url}')
                return dedicated_url
            elif os.getenv('EMBEDDING_ENDPOINT_FALLBACK', 'true').lower() == 'true':
                fallback_url = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434/v1')
                logger.warning(f'Dedicated embedding endpoint not configured, falling back to main Ollama URL: {fallback_url}')
                return fallback_url
            else:
                raise ValueError('Dedicated embedding endpoint required but not configured (OLLAMA_EMBEDDING_BASE_URL not set)')
        
        # Use main Ollama URL for embeddings
        main_url = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434/v1')
        logger.debug(f'Using main Ollama endpoint for embeddings: {main_url}')
        return main_url

    @staticmethod
    def create_embedder() -> Optional[EmbedderClient]:
        """Create embedder client based on environment configuration."""
        # Check for Ollama embeddings even if main LLM is Cerebras
        if os.getenv('USE_OLLAMA_EMBEDDINGS', '').lower() == 'true' or os.getenv('USE_OLLAMA', '').lower() == 'true':
            try:
                from openai import AsyncOpenAI

                # Determine embedding endpoint with dedicated support
                embedding_base_url = GraphitiClientFactory._get_embedding_endpoint()
                ollama_embed_model = os.getenv('OLLAMA_EMBEDDING_MODEL', 'mxbai-embed-large:latest')

                logger.info(
                    f'Creating Ollama embedder with model {ollama_embed_model} at {embedding_base_url}'
                )

                # Use dedicated API key if provided, otherwise default to 'ollama'
                embedding_api_key = os.getenv('OLLAMA_EMBEDDING_API_KEY', 'ollama')
                client = AsyncOpenAI(base_url=embedding_base_url, api_key=embedding_api_key)

                config = OpenAIEmbedderConfig(embedding_model=ollama_embed_model)

                embedder = OpenAIEmbedder(config=config, client=client)
                logger.info(
                    f'Successfully created Ollama embedder with model: {config.embedding_model}'
                )
                return embedder
            except Exception as e:
                logger.error(f'Failed to create Ollama embedder: {e}')
                logger.info('Falling back to OpenAI embedder')

        # Default to OpenAI embedder
        logger.info('Creating default OpenAI embedder')
        return OpenAIEmbedder()

    @staticmethod
    def create_cross_encoder():
        """Create cross encoder client (currently only OpenAI supported)."""
        return OpenAIRerankerClient()
