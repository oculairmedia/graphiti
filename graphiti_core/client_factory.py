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

# Add immediate module-level logging to verify code is loaded
_logger = logging.getLogger(__name__)
_logger.info("!!! GraphitiClientFactory module loaded - FORCE BUILD CACHE INVALIDATION !!!")

from graphiti_core.cross_encoder.openai_reranker_client import OpenAIRerankerClient
from graphiti_core.embedder import EmbedderClient, OpenAIEmbedder, OpenAIEmbedderConfig
from graphiti_core.llm_client import LLMClient, LLMConfig, OpenAIClient
from graphiti_core.llm_client.cerebras_client import CerebrasClient
from graphiti_core.llm_client.chutes_client import ChutesClient
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
        chutes_client = None
        
        # Check if we should enable fallback mode
        use_fallback = os.getenv('ENABLE_FALLBACK', 'true').lower() == 'true'
        
        # Debug environment variables
        use_cerebras_raw = os.getenv('USE_CEREBRAS', '')
        use_cerebras_lower = use_cerebras_raw.lower()
        use_chutes_raw = os.getenv('USE_CHUTES', '')
        use_chutes_lower = use_chutes_raw.lower()
        use_ollama_raw = os.getenv('USE_OLLAMA', '')
        use_ollama_lower = use_ollama_raw.lower()
        
        logger.info(f'Environment check: USE_CEREBRAS="{use_cerebras_raw}" -> "{use_cerebras_lower}" -> {use_cerebras_lower == "true"}')
        logger.info(f'Environment check: USE_CHUTES="{use_chutes_raw}" -> "{use_chutes_lower}" -> {use_chutes_lower == "true"}')
        logger.info(f'Environment check: USE_OLLAMA="{use_ollama_raw}" -> "{use_ollama_lower}" -> {use_ollama_lower == "true"}')
        logger.info(f'Fallback enabled: {use_fallback}')
        
        # Try to create all requested clients (no early returns for cascading)
        available_clients = []
        client_names = []
        
        # 1. Try to create Cerebras client (highest priority)
        if use_cerebras_lower == 'true':
            try:
                cerebras_model = os.getenv('CEREBRAS_MODEL', 'qwen-3-coder-480b')
                cerebras_small_model = os.getenv('CEREBRAS_SMALL_MODEL', 'qwen-3-32b')
                cerebras_api_key = os.getenv('CEREBRAS_API_KEY')
                
                logger.info(f'Creating Cerebras LLM client with model {cerebras_model}')
                logger.info(f'Cerebras API key present: {cerebras_api_key is not None}')
                
                config = LLMConfig(
                    api_key=cerebras_api_key,
                    model=cerebras_model,
                    small_model=cerebras_small_model,
                    temperature=0.7,  # Recommended temperature for qwen-3-coder-480b
                    max_tokens=4000,
                )
                
                cerebras_client = CerebrasClient(config=config)
                available_clients.append(cerebras_client)
                client_names.append("Cerebras")
                logger.info('CerebrasClient instantiated successfully!')
                    
            except Exception as e:
                logger.error(f'Failed to create Cerebras LLM client: {e}')
                import traceback
                logger.error(f'Full traceback: {traceback.format_exc()}')
        
        # 2. Try to create Chutes AI client (second priority)
        if use_chutes_lower == 'true':
            try:
                chutes_model = os.getenv('CHUTES_MODEL', 'glm-4-flash')
                chutes_small_model = os.getenv('CHUTES_SMALL_MODEL', 'glm-4-flash')
                chutes_api_key = os.getenv('CHUTES_API_KEY')
                chutes_base_url = os.getenv('CHUTES_BASE_URL', 'https://llm.chutes.ai/v1')
                
                logger.info(f'Creating Chutes AI LLM client with model {chutes_model} at {chutes_base_url}')
                logger.info(f'Chutes API key present: {chutes_api_key is not None}')
                
                config = LLMConfig(
                    api_key=chutes_api_key,
                    model=chutes_model,
                    small_model=chutes_small_model,
                    base_url=chutes_base_url,
                    temperature=0.7,
                    max_tokens=4000,
                )
                
                chutes_client = ChutesClient(config=config)
                available_clients.append(chutes_client)
                client_names.append("Chutes")
                logger.info('ChutesClient instantiated successfully!')
                    
            except Exception as e:
                logger.error(f'Failed to create Chutes AI LLM client: {e}')
                import traceback
                logger.error(f'Full traceback: {traceback.format_exc()}')
        
        # 3. Try to create Ollama client (lowest priority, final fallback)
        if use_ollama_lower == 'true':
            try:
                from openai import AsyncOpenAI

                ollama_base_url = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434/v1')
                ollama_model = os.getenv('OLLAMA_MODEL', 'mistral:latest')

                logger.info(f'Creating Ollama LLM client with model {ollama_model} at {ollama_base_url}')

                client = AsyncOpenAI(base_url=ollama_base_url, api_key='ollama')

                config = LLMConfig(
                    model=ollama_model, small_model=ollama_model, temperature=0.7, max_tokens=2000
                )

                ollama_client = OpenAIClient(config=config, client=client)
                available_clients.append(ollama_client)
                client_names.append("Ollama")
                logger.info('Ollama client instantiated successfully!')
                    
            except Exception as e:
                logger.error(f'Failed to create Ollama LLM client: {e}')
                import traceback
                logger.error(f'Full traceback: {traceback.format_exc()}')
        
        # Now decide what to return based on available clients and fallback settings
        if len(available_clients) == 0:
            logger.warning('No specialized clients available, defaulting to OpenAI')
            return OpenAIClient()
        
        if len(available_clients) == 1:
            logger.info(f'Single client available: {client_names[0]}')
            return available_clients[0]
        
        if not use_fallback:
            # Return only the highest priority client
            logger.info(f'Fallback disabled, using highest priority client: {client_names[0]}')
            return available_clients[0]
        
        # Create cascading fallback client with all available clients
        logger.info(f'Creating cascading fallback client: {" → ".join(client_names)}')
        return FallbackLLMClient(
            primary_client=available_clients[0],  # For backward compatibility
            clients=available_clients  # New cascading approach
        )

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
