"""
Factory function to create LLM client based on environment configuration.
This allows switching between OpenAI and Ollama without modifying existing code.
"""

import os
from openai import AsyncOpenAI
from .openai_client import OpenAIClient
from .openai_generic_client import OpenAIGenericClient
from .config import LLMConfig


def create_llm_client(config: LLMConfig | None = None, cache: bool = False):
    """
    Create appropriate LLM client based on environment configuration.
    
    If USE_OLLAMA is set to 'true', creates an Ollama client.
    Otherwise, returns standard OpenAI client.
    """
    use_ollama = os.getenv('USE_OLLAMA', '').lower() == 'true'
    
    if use_ollama:
        # Get Ollama configuration from environment
        ollama_base_url = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434/v1')
        ollama_model = os.getenv('OLLAMA_MODEL', 'mistral:latest')
        
        # Override config with Ollama model if not specified
        if config is None:
            config = LLMConfig()
        
        config.model = ollama_model
        config.small_model = ollama_model
        
        # Create Ollama client
        client = AsyncOpenAI(
            base_url=ollama_base_url,
            api_key="ollama"  # Ollama doesn't require a real key
        )
        
        return OpenAIGenericClient(config=config, cache=cache, client=client)
    else:
        # Return standard OpenAI client
        return OpenAIClient(config=config, cache=cache)