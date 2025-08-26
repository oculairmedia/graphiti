"""Fallback LLM client that switches through multiple backups when primary fails."""

import logging
from typing import Any, Optional

from pydantic import BaseModel

from ..prompts.models import Message
from .client import LLMClient
from .config import LLMConfig, ModelSize
from .errors import RateLimitError

logger = logging.getLogger(__name__)


class FallbackLLMClient(LLMClient):
    """LLM client that cascades through multiple fallback clients on rate limits or errors."""
    
    def __init__(self, primary_client: LLMClient, fallback_client: LLMClient = None, clients: list[LLMClient] = None):
        """
        Initialize fallback client with primary and backup clients.
        
        Args:
            primary_client: Primary LLM client to use first (for backward compatibility)
            fallback_client: Secondary backup client (for backward compatibility) 
            clients: List of clients in priority order (new cascading approach)
        """
        # Use primary client's config and cache settings
        super().__init__(primary_client.config, primary_client.cache_enabled)
        
        # Handle both old (2-client) and new (multi-client) initialization
        if clients is not None:
            self.clients = clients
            self.client_names = [self._get_client_name(client) for client in clients]
        else:
            # Backward compatibility: convert to new format
            self.clients = [primary_client]
            self.client_names = [self._get_client_name(primary_client)]
            if fallback_client is not None:
                self.clients.append(fallback_client)
                self.client_names.append(self._get_client_name(fallback_client))
        
        self._current_client_index = 0  # Start with the first client
        self._failed_clients = set()  # Track temporarily failed clients
        
        logger.info(f"FallbackLLMClient initialized with cascade: {' → '.join(self.client_names)}")
    
    def _get_client_name(self, client: LLMClient) -> str:
        """Get a human-readable name for a client."""
        client_name = type(client).__name__.replace('Client', '')
        
        # Special case for Ollama - check if it's using Ollama base URL
        if (client_name == 'OpenAI' and hasattr(client, 'client') and 
            hasattr(client.client, 'base_url') and 
            '11434' in str(client.client.base_url)):
            client_name = 'Ollama'
        
        if hasattr(client, 'model') and client.model:
            return f"{client_name}({client.model})"
        return client_name
        
    async def _generate_response(
        self,
        messages: list[Message],
        response_model: type[BaseModel] | None = None,
        max_tokens: int = 16384,
        model_size: ModelSize = ModelSize.medium,
    ) -> dict[str, Any]:
        """
        Generate response, cascading through clients on rate limits or errors.
        
        Args:
            messages: List of messages for the conversation.
            response_model: Optional Pydantic model for structured output.
            max_tokens: Maximum tokens to generate.
            model_size: Size of the model to use.
            
        Returns:
            Generated response as a dictionary.
        """
        last_error = None
        
        # First, try to recover any previously failed clients (try higher priority clients)
        if self._current_client_index > 0:
            for i in range(self._current_client_index):
                if i not in self._failed_clients:
                    try:
                        client = self.clients[i]
                        logger.info(f"Attempting to recover higher priority client: {self.client_names[i]}")
                        result = await client._generate_response(
                            messages, response_model, max_tokens, model_size
                        )
                        # Success! Update current client and clear failed status
                        self._current_client_index = i
                        self._failed_clients.discard(i)
                        logger.info(f"Successfully recovered to {self.client_names[i]}")
                        return result
                    except Exception as e:
                        # Still failing, keep trying other clients
                        logger.debug(f"Client {self.client_names[i]} still failing: {e}")
                        self._failed_clients.add(i)
                        continue
        
        # Try clients starting from current position
        for attempt_index in range(self._current_client_index, len(self.clients)):
            client = self.clients[attempt_index]
            client_name = self.client_names[attempt_index]
            
            # Skip clients we know are currently failed
            if attempt_index in self._failed_clients:
                logger.debug(f"Skipping known failed client: {client_name}")
                continue
            
            try:
                if attempt_index != self._current_client_index:
                    logger.info(f"Switching to fallback client: {client_name}")
                    self._current_client_index = attempt_index
                
                result = await client._generate_response(
                    messages, response_model, max_tokens, model_size
                )
                
                # Success! Remove from failed set if it was there
                self._failed_clients.discard(attempt_index)
                logger.debug(f"Successfully generated response using {client_name}")
                return result
                
            except RateLimitError as e:
                logger.warning(f"Client {client_name} rate limited: {e}")
                self._failed_clients.add(attempt_index)
                last_error = e
                continue
                
            except Exception as e:
                # Check if it's a rate limit or quota error by string matching
                error_str = str(e).lower()
                if any(keyword in error_str for keyword in ["429", "rate", "quota", "limit"]):
                    logger.warning(f"Client {client_name} error (likely rate limit): {e}")
                    self._failed_clients.add(attempt_index)
                    last_error = e
                    continue
                else:
                    # Non-rate-limit error, re-raise immediately
                    logger.error(f"Client {client_name} failed with non-rate-limit error: {e}")
                    raise
        
        # If we get here, all clients have failed
        if last_error:
            logger.error(f"All clients in cascade failed. Last error: {last_error}")
            raise last_error
        else:
            raise Exception("All clients in fallback cascade have failed")