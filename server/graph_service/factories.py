"""
Factory functions for creating LLM and Embedder clients.

This module centralizes the logic for creating various client instances,
following the Single Responsibility Principle and eliminating code duplication.
"""

import os
import logging
from typing import Optional, Any

from graphiti_core.embedder import EmbedderClient, OpenAIEmbedder, OpenAIEmbedderConfig
from graphiti_core.llm_client import LLMClient, LLMConfig, OpenAIClient
from openai import AsyncOpenAI

from graph_service.config import Settings

logger = logging.getLogger(__name__)


def create_llm_client(settings: Settings) -> Optional[LLMClient]:
    """
    Factory function to create an LLM client based on settings.
    
    Args:
        settings: Application settings containing configuration
        
    Returns:
        LLMClient instance or None if not using Ollama
    """
    if not os.getenv('USE_OLLAMA', '').lower() == 'true':
        # In the future, this could create a standard OpenAI client
        # based on settings.openai_api_key, settings.openai_base_url, etc.
        return None

    ollama_base_url = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434/v1')
    ollama_model = os.getenv('OLLAMA_MODEL', 'mistral:latest')
    
    logger.info(
        f'Creating Ollama LLM client at {ollama_base_url} with model {ollama_model}'
    )
    
    client = AsyncOpenAI(base_url=ollama_base_url, api_key='ollama')
    config = LLMConfig(
        model=ollama_model,
        small_model=ollama_model,
        temperature=0.7,
        max_tokens=2000
    )
    
    return OpenAIClient(config=config, client=client)


def create_embedder_client(settings: Settings) -> Optional[EmbedderClient]:
    """
    Factory function to create an embedder client based on settings.
    
    Args:
        settings: Application settings containing configuration
        
    Returns:
        EmbedderClient instance or None if not using Ollama
    """
    if not os.getenv('USE_OLLAMA', '').lower() == 'true':
        # In the future, this could create a standard OpenAI embedder
        # or other embedding providers based on settings
        return None

    ollama_base_url = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434/v1')
    ollama_embed_model = os.getenv('OLLAMA_EMBEDDING_MODEL', 'mxbai-embed-large:latest')
    
    logger.info(
        f'Creating Ollama embedder at {ollama_base_url} with model {ollama_embed_model}'
    )

    client = AsyncOpenAI(base_url=ollama_base_url, api_key='ollama')
    config = OpenAIEmbedderConfig(embedding_model=ollama_embed_model)
    
    return OpenAIEmbedder(config=config, client=client)


def configure_non_ollama_clients(client: Any, settings: Settings) -> None:
    """
    Configure non-Ollama clients with custom settings.
    
    This handles the legacy configuration where OpenAI settings are
    applied after client creation.
    
    Args:
        client: ZepGraphiti instance to configure
        settings: Application settings
    """
    # Only configure OpenAI settings if not using Ollama
    if os.getenv('USE_OLLAMA', '').lower() == 'true':
        return
        
    if client.llm_client:
        if settings.openai_base_url is not None:
            client.llm_client.config.base_url = settings.openai_base_url
        if settings.openai_api_key is not None:
            client.llm_client.config.api_key = settings.openai_api_key
        if settings.model_name is not None:
            client.llm_client.model = settings.model_name