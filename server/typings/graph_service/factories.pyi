"""Type stubs for graph_service.factories module."""

from typing import Optional
from graphiti_core.embedder import EmbedderClient
from graphiti_core.llm_client import LLMClient
from graph_service.config import Settings
from graph_service.zep_graphiti import ZepGraphiti

def create_llm_client(settings: Settings) -> Optional[LLMClient]: ...

def create_embedder_client(settings: Settings) -> Optional[EmbedderClient]: ...

def configure_non_ollama_clients(client: ZepGraphiti, settings: Settings) -> None: ...