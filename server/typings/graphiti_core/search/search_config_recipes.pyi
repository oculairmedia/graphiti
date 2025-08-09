"""Type stubs for graphiti_core.search.search_config_recipes module."""

from graphiti_core.search import SearchConfig

def get_default_search_config() -> SearchConfig: ...

def get_semantic_search_config() -> SearchConfig: ...

def get_bm25_search_config() -> SearchConfig: ...

def get_hybrid_search_config(
    bm25_weight: float = 0.5,
    semantic_weight: float = 0.5
) -> SearchConfig: ...

def get_mmr_search_config(
    mmr_lambda: float = 0.5
) -> SearchConfig: ...

__all__ = [
    'get_default_search_config',
    'get_semantic_search_config',
    'get_bm25_search_config',
    'get_hybrid_search_config',
    'get_mmr_search_config',
]