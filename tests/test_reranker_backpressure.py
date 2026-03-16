"""Tests for reranker backpressure constants and search_proxy singleton contracts.

NOTE: graphiti_core cannot be imported in this environment due to a broken
dspy -> litellm -> openai.types.responses import chain. Tests that require
graphiti_core classes (OpenAIRerankerClient, GeminiRerankerClient) use AST
parsing to verify the code contracts instead.

The constants test uses importlib.util to load helpers.py directly.
"""

import ast
import importlib.util
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
_GC = PROJECT_ROOT / 'graphiti_core'


def _load_file(name: str, path: Path):
    """Load a .py file without triggering package __init__."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    # Prevent __init__.py from firing by pre-registering the package
    pkg_name = name.rsplit('.', 1)[0] if '.' in name else name
    if pkg_name not in sys.modules:
        import types as _t

        sys.modules[pkg_name] = _t.ModuleType(pkg_name)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# Pre-register graphiti_core.errors (needed by helpers.py)
sys.modules.setdefault('graphiti_core', type(sys)('graphiti_core'))
_load_file('graphiti_core.errors', _GC / 'errors.py')
helpers = _load_file('graphiti_core.helpers', _GC / 'helpers.py')


# ---------------------------------------------------------------------------
# helpers.py constants — direct runtime test
# ---------------------------------------------------------------------------


class TestRerankerConstants:
    def test_reranker_semaphore_limit_exists(self):
        assert hasattr(helpers, 'RERANKER_SEMAPHORE_LIMIT')

    def test_max_rerank_passages_exists(self):
        assert hasattr(helpers, 'MAX_RERANK_PASSAGES')

    def test_reranker_semaphore_limit_is_lower_than_global(self):
        assert helpers.RERANKER_SEMAPHORE_LIMIT < helpers.SEMAPHORE_LIMIT

    def test_reranker_semaphore_default_is_5(self):
        assert helpers.RERANKER_SEMAPHORE_LIMIT == 5

    def test_max_rerank_passages_default_is_40(self):
        assert helpers.MAX_RERANK_PASSAGES == 40

    def test_max_rerank_passages_is_sane_range(self):
        assert 10 <= helpers.MAX_RERANK_PASSAGES <= 200


# ---------------------------------------------------------------------------
# OpenAI reranker — AST contract test (passage cap + semaphore)
# ---------------------------------------------------------------------------


class TestOpenAIRerankerContract:
    """Verify the reranker source code contains passage cap and semaphore limit."""

    @classmethod
    def setup_class(cls):
        src = (_GC / 'cross_encoder' / 'openai_reranker_client.py').read_text()
        cls.tree = ast.parse(src)
        cls.src = src

    def test_imports_max_rerank_passages(self):
        assert 'MAX_RERANK_PASSAGES' in self.src

    def test_imports_reranker_semaphore_limit(self):
        assert 'RERANKER_SEMAPHORE_LIMIT' in self.src

    def test_rank_method_caps_passages(self):
        """rank() must contain `passages[:MAX_RERANK_PASSAGES]`."""
        assert 'passages[:MAX_RERANK_PASSAGES]' in self.src

    def test_semaphore_gather_uses_reranker_limit(self):
        """semaphore_gather must use max_coroutines=RERANKER_SEMAPHORE_LIMIT."""
        assert 'max_coroutines=RERANKER_SEMAPHORE_LIMIT' in self.src


# ---------------------------------------------------------------------------
# Gemini reranker — AST contract test
# ---------------------------------------------------------------------------


class TestGeminiRerankerContract:
    @classmethod
    def setup_class(cls):
        src = (_GC / 'cross_encoder' / 'gemini_reranker_client.py').read_text()
        cls.tree = ast.parse(src)
        cls.src = src

    def test_imports_max_rerank_passages(self):
        assert 'MAX_RERANK_PASSAGES' in self.src

    def test_imports_reranker_semaphore_limit(self):
        assert 'RERANKER_SEMAPHORE_LIMIT' in self.src

    def test_rank_method_caps_passages(self):
        assert 'passages[:MAX_RERANK_PASSAGES]' in self.src

    def test_semaphore_gather_uses_reranker_limit(self):
        assert 'max_coroutines=RERANKER_SEMAPHORE_LIMIT' in self.src


# ---------------------------------------------------------------------------
# search.py — AST contract test (batch size caps)
# ---------------------------------------------------------------------------


class TestSearchBatchCaps:
    @classmethod
    def setup_class(cls):
        cls.src = (_GC / 'search' / 'search.py').read_text()

    def test_node_search_caps_before_rerank(self):
        """Node cross_encoder branch must use [:limit] on values()."""
        assert 'node_uuid_map.values())[:limit]' in self.src

    def test_community_search_uses_rrf_prefilter(self):
        """Community cross_encoder must RRF-prefilter before reranking."""
        # The community reranker section should contain rrf() + [:limit]
        assert 'rrf_result_uuids = rrf(search_result_uuids' in self.src


# ---------------------------------------------------------------------------
# search_proxy — AST contract test (singleton pattern)
# ---------------------------------------------------------------------------


class TestSearchProxyContract:
    @classmethod
    def setup_class(cls):
        cls.src = (
            PROJECT_ROOT / 'server' / 'graph_service' / 'routers' / 'search_proxy.py'
        ).read_text()

    def test_has_pool_limits(self):
        assert 'httpx.Limits(' in self.src

    def test_has_get_embedding_client(self):
        assert 'def get_embedding_client()' in self.src

    def test_has_get_reranker_client(self):
        assert 'def get_reranker_client()' in self.src

    def test_has_close_proxy_clients(self):
        assert 'async def close_proxy_clients()' in self.src

    def test_generate_embedding_uses_singleton(self):
        """generate_embedding must call get_embedding_client(), not httpx.AsyncClient()."""
        # Find the function body and verify it uses the singleton
        tree = ast.parse(self.src)
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == 'generate_embedding':
                body_src = ast.get_source_segment(self.src, node)
                assert body_src is not None
                assert 'get_embedding_client()' in body_src
                assert 'httpx.AsyncClient(' not in body_src
                return
        pytest.fail('generate_embedding function not found')

    def test_rerank_uses_singleton(self):
        """rerank_facts_with_cross_encoder must call get_reranker_client()."""
        tree = ast.parse(self.src)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.AsyncFunctionDef)
                and node.name == 'rerank_facts_with_cross_encoder'
            ):
                body_src = ast.get_source_segment(self.src, node)
                assert body_src is not None
                assert 'get_reranker_client()' in body_src
                assert 'httpx.AsyncClient(' not in body_src
                return
        pytest.fail('rerank_facts_with_cross_encoder function not found')


# ---------------------------------------------------------------------------
# Ollama reranker — AST contract test (async context manager)
# ---------------------------------------------------------------------------


class TestOllamaRerankerContract:
    @classmethod
    def setup_class(cls):
        cls.src = (_GC / 'cross_encoder' / 'ollama_reranker_client.py').read_text()

    def test_has_aenter(self):
        assert 'async def __aenter__' in self.src

    def test_has_aexit(self):
        assert 'async def __aexit__' in self.src

    def test_del_checks_is_closed(self):
        assert 'self.client.is_closed' in self.src

    def test_del_uses_get_running_loop(self):
        assert 'get_running_loop()' in self.src
