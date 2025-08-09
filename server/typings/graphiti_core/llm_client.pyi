"""Type stubs for graphiti_core.llm_client module."""

from typing import Any, Dict, List, Optional, Protocol, TypedDict
from abc import ABC, abstractmethod
from pydantic import BaseModel

class LLMConfig(BaseModel):
    """Configuration for LLM clients."""
    api_key: Optional[str] = None
    model: str
    small_model: Optional[str] = None
    base_url: Optional[str] = None
    temperature: float = 0.7
    max_tokens: Optional[int] = None

class LLMResponse(TypedDict):
    """Response from LLM."""
    content: str
    usage: Dict[str, int]
    model: str

class LLMClient(Protocol):
    """Protocol for LLM client implementations."""
    config: LLMConfig
    model: str
    
    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None
    ) -> LLMResponse: ...
    
    async def generate_structured(
        self,
        prompt: str,
        response_model: type[BaseModel],
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None
    ) -> BaseModel: ...

class OpenAIClient(LLMClient):
    """OpenAI LLM client implementation."""
    config: LLMConfig
    model: str
    
    def __init__(self, config: LLMConfig, client: Optional[Any] = None) -> None: ...
    
    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None
    ) -> LLMResponse: ...
    
    async def generate_structured(
        self,
        prompt: str,
        response_model: type[BaseModel],
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None
    ) -> BaseModel: ...

class AnthropicClient(LLMClient):
    """Anthropic LLM client implementation."""
    
    def __init__(self, config: LLMConfig) -> None: ...
    
    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None
    ) -> LLMResponse: ...
    
    async def generate_structured(
        self,
        prompt: str,
        response_model: type[BaseModel],
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None
    ) -> BaseModel: ...

__all__ = [
    'LLMClient',
    'LLMConfig',
    'LLMResponse',
    'OpenAIClient',
    'AnthropicClient',
]