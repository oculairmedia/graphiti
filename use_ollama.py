#!/usr/bin/env python3
"""
Simple wrapper to use Graphiti with Ollama without modifying core files.
Just import from this file instead of graphiti_core.

Usage:
    from use_ollama import Graphiti
    
    # Then use exactly as before - it will automatically use Ollama if configured
    graphiti = Graphiti(uri, user, password)
"""

import os
from openai import AsyncOpenAI

# Load Ollama configuration if available
if os.path.exists('.env.ollama'):
    from dotenv import load_dotenv
    load_dotenv('.env.ollama', override=True)

from graphiti_core import Graphiti as BaseGraphiti
from graphiti_core.llm_client import OpenAIGenericClient, LLMConfig


class Graphiti(BaseGraphiti):
    """
    Drop-in replacement for Graphiti that uses Ollama when configured.
    """
    
    def __init__(self, uri=None, user=None, password=None, llm_client=None, **kwargs):
        # Only override llm_client if not explicitly provided and USE_OLLAMA is set
        if llm_client is None and os.getenv('USE_OLLAMA', '').lower() == 'true':
            # Get Ollama configuration
            ollama_base_url = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434/v1')
            ollama_model = os.getenv('OLLAMA_MODEL', 'mistral:latest')
            
            print(f"🦙 Using Ollama at {ollama_base_url} with model {ollama_model}")
            
            # Create Ollama client
            client = AsyncOpenAI(
                base_url=ollama_base_url,
                api_key="ollama"
            )
            
            # Configure LLM
            config = LLMConfig(
                model=ollama_model,
                small_model=ollama_model,
                temperature=0.7,
                max_tokens=2000
            )
            
            llm_client = OpenAIGenericClient(config=config, client=client)
        
        # Initialize parent with potentially overridden llm_client
        super().__init__(uri=uri, user=user, password=password, llm_client=llm_client, **kwargs)


# Re-export other commonly used classes so this can be a drop-in replacement
from graphiti_core import EntityNode, EntityEdge, EpisodicNode
from graphiti_core.search import SearchConfig

__all__ = ['Graphiti', 'EntityNode', 'EntityEdge', 'EpisodicNode', 'SearchConfig']