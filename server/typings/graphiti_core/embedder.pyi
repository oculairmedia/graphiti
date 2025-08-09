"""Type stubs for graphiti_core.embedder module."""

from typing import List, Optional, Protocol
from pydantic import BaseModel

class OpenAIEmbedderConfig(BaseModel):
    """Configuration for OpenAI embedder."""
    api_key: Optional[str]
    model: str = "text-embedding-3-small"
    base_url: Optional[str] = None
    dimensions: Optional[int] = None

class EmbedderClient(Protocol):
    """Protocol for embedder client implementations."""
    
    async def embed(self, text: str) -> List[float]: ...
    
    async def embed_batch(self, texts: List[str]) -> List[List[float]]: ...

class OpenAIEmbedder(EmbedderClient):
    """OpenAI embedder implementation."""
    
    def __init__(self, config: OpenAIEmbedderConfig) -> None: ...
    
    async def embed(self, text: str) -> List[float]: ...
    
    async def embed_batch(self, texts: List[str]) -> List[List[float]]: ...

class VoyageEmbedder(EmbedderClient):
    """Voyage embedder implementation."""
    
    def __init__(self, api_key: Optional[str] = None, model: str = "voyage-3") -> None: ...
    
    async def embed(self, text: str) -> List[float]: ...
    
    async def embed_batch(self, texts: List[str]) -> List[List[float]]: ...

__all__ = [
    'EmbedderClient',
    'OpenAIEmbedder',
    'OpenAIEmbedderConfig',
    'VoyageEmbedder',
]