"""Fallback LLM client that switches to backup when primary fails."""

import logging
from typing import Any, Optional

from pydantic import BaseModel

from ..prompts.models import Message
from .client import LLMClient
from .config import LLMConfig, ModelSize
from .errors import RateLimitError

logger = logging.getLogger(__name__)


class FallbackLLMClient(LLMClient):
    """LLM client that falls back to secondary client on rate limits or errors."""
    
    def __init__(self, primary_client: LLMClient, fallback_client: LLMClient):
        """
        Initialize fallback client with primary and backup clients.
        
        Args:
            primary_client: Primary LLM client to use first
            fallback_client: Backup client to use on failures
        """
        # Use primary client's config and cache settings
        super().__init__(primary_client.config, primary_client.cache_enabled)
        self.primary_client = primary_client
        self.fallback_client = fallback_client
        self._using_fallback = False
        
    async def _generate_response(
        self,
        messages: list[Message],
        response_model: type[BaseModel] | None = None,
        max_tokens: int = 16384,
        model_size: ModelSize = ModelSize.medium,
    ) -> dict[str, Any]:
        """
        Generate response, falling back to secondary client on rate limits.
        
        Args:
            messages: List of messages for the conversation.
            response_model: Optional Pydantic model for structured output.
            max_tokens: Maximum tokens to generate.
            model_size: Size of the model to use.
            
        Returns:
            Generated response as a dictionary.
        """
        try:
            # Try primary client first
            if not self._using_fallback:
                result = await self.primary_client._generate_response(
                    messages, response_model, max_tokens, model_size
                )
                if self._using_fallback:
                    logger.info("Primary client recovered, switching back from fallback")
                    self._using_fallback = False
                return result
        except RateLimitError as e:
            logger.warning(f"Primary client rate limited: {e}")
            logger.info("Switching to fallback client (Ollama)")
            self._using_fallback = True
        except Exception as e:
            if "429" in str(e) or "rate" in str(e).lower() or "quota" in str(e).lower():
                logger.warning(f"Primary client error (likely rate limit): {e}")
                logger.info("Switching to fallback client (Ollama)")
                self._using_fallback = True
            else:
                # Re-raise non-rate-limit errors
                raise
        
        # Use fallback client
        try:
            logger.debug(f"Using fallback client for request")
            result = await self.fallback_client._generate_response(
                messages, response_model, max_tokens, model_size
            )
            return result
        except Exception as e:
            logger.error(f"Fallback client also failed: {e}")
            # Try primary one more time in case it recovered
            self._using_fallback = False
            return await self.primary_client._generate_response(
                messages, response_model, max_tokens, model_size
            )