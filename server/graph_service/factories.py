"""
Factory functions for creating LLM and Embedder clients.

This module centralizes the logic for creating various client instances,
following the Single Responsibility Principle and eliminating code duplication.
"""

import os
import logging
from typing import Optional, Any

from graphiti_core.embedder import EmbedderClient
from graphiti_core.llm_client import LLMClient

from graph_service.config import Settings

logger = logging.getLogger(__name__)


def create_llm_client(settings: Settings) -> Optional[LLMClient]:
    """
    Factory function to create an LLM client based on settings.
    
    Args:
        settings: Application settings containing configuration
        
    Returns:
        LLMClient instance or None if not using special LLM provider
    """
    # Check if we should use the centralized factory for Cerebras, Chutes, or Ollama
    if (os.getenv('USE_CEREBRAS', '').lower() == 'true' or 
        os.getenv('USE_CHUTES', '').lower() == 'true' or 
        os.getenv('USE_OLLAMA', '').lower() == 'true'):
        # Use the centralized factory which supports Cerebras, Chutes, Ollama, and OpenAI
        from graphiti_core.client_factory import GraphitiClientFactory
        
        if os.getenv('USE_CEREBRAS', '').lower() == 'true':
            logger.info('Creating Cerebras LLM client via centralized factory')
        elif os.getenv('USE_CHUTES', '').lower() == 'true':
            logger.info('Creating Chutes AI LLM client via centralized factory')
        else:
            logger.info('Creating Ollama LLM client via centralized factory')
        
        return GraphitiClientFactory.create_llm_client()
    
    # Default behavior - return None for standard OpenAI client
    # (which will be configured later via configure_non_ollama_clients)
    return None


def create_embedder_client(settings: Settings) -> Optional[EmbedderClient]:
    """
    Factory function to create an embedder client based on settings.
    
    Args:
        settings: Application settings containing configuration
        
    Returns:
        EmbedderClient instance or None if not using special embedder
    """
    # Check if we should use the centralized factory for Cerebras, Chutes, or Ollama
    if (os.getenv('USE_CEREBRAS', '').lower() == 'true' or 
        os.getenv('USE_CHUTES', '').lower() == 'true' or 
        os.getenv('USE_OLLAMA', '').lower() == 'true'):
        # Use the centralized factory which handles embedder creation
        from graphiti_core.client_factory import GraphitiClientFactory
        
        if os.getenv('USE_CEREBRAS', '').lower() == 'true':
            logger.info('Creating embedder via centralized factory (for Cerebras mode)')
        elif os.getenv('USE_CHUTES', '').lower() == 'true':
            logger.info('Creating embedder via centralized factory (for Chutes mode)')
        else:
            logger.info('Creating Ollama embedder via centralized factory')
        
        return GraphitiClientFactory.create_embedder()
    
    # Default behavior - return None for standard OpenAI embedder
    # (which will be configured later if needed)
    return None



def configure_non_ollama_clients(client: Any, settings: Settings) -> None:
    """
    Configure non-Ollama/non-Cerebras clients with custom settings.
    
    This handles the legacy configuration where OpenAI settings are
    applied after client creation.
    
    Args:
        client: ZepGraphiti instance to configure
        settings: Application settings
    """
    # Skip configuration if using Ollama, Cerebras, or Chutes (they're already configured)
    if (os.getenv('USE_OLLAMA', '').lower() == 'true' or 
        os.getenv('USE_CEREBRAS', '').lower() == 'true' or
        os.getenv('USE_CHUTES', '').lower() == 'true'):
        return
        
    if client.llm_client:
        if settings.openai_base_url is not None:
            client.llm_client.config.base_url = settings.openai_base_url
        if settings.openai_api_key is not None:
            client.llm_client.config.api_key = settings.openai_api_key
        if settings.model_name is not None:
            client.llm_client.model = settings.model_name