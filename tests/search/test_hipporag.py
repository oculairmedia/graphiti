"""
Tests for HippoRAG search method.

These tests verify that HippoRAG spreading activation search is correctly
integrated into both Python config and Rust service.
"""

import pytest

from graphiti_core.search.search_config import (
    EdgeSearchMethod,
    EdgeSearchConfig,
    NodeSearchMethod,
    NodeSearchConfig,
    SearchConfig,
)
from graphiti_core.search.rust_client import PYTHON_TO_RUST_SEARCH_METHOD, RustSearchClient


class TestHippoRAGEnums:
    """Tests for HippoRAG enum values."""

    def test_node_search_method_hipporag_exists(self):
        assert hasattr(NodeSearchMethod, 'hipporag')
        assert NodeSearchMethod.hipporag.value == 'hipporag'

    def test_edge_search_method_hipporag_exists(self):
        assert hasattr(EdgeSearchMethod, 'hipporag')
        assert EdgeSearchMethod.hipporag.value == 'hipporag'

    def test_hipporag_in_rust_mapping(self):
        assert 'hipporag' in PYTHON_TO_RUST_SEARCH_METHOD
        assert PYTHON_TO_RUST_SEARCH_METHOD['hipporag'] == 'hipporag'


class TestHippoRAGConfig:
    """Tests for HippoRAG configuration fields."""

    def test_node_search_config_hipporag_defaults(self):
        config = NodeSearchConfig(search_methods=[NodeSearchMethod.hipporag])
        assert config.hipporag_max_hops == 2
        assert config.hipporag_decay == 0.85
        assert config.hipporag_seed_count == 10

    def test_node_search_config_hipporag_custom(self):
        config = NodeSearchConfig(
            search_methods=[NodeSearchMethod.hipporag],
            hipporag_max_hops=3,
            hipporag_decay=0.9,
            hipporag_seed_count=15,
        )
        assert config.hipporag_max_hops == 3
        assert config.hipporag_decay == 0.9
        assert config.hipporag_seed_count == 15

    def test_edge_search_config_hipporag_defaults(self):
        config = EdgeSearchConfig(search_methods=[EdgeSearchMethod.hipporag])
        assert config.hipporag_max_hops == 2
        assert config.hipporag_decay == 0.85
        assert config.hipporag_seed_count == 10

    def test_combined_search_methods(self):
        config = NodeSearchConfig(
            search_methods=[
                NodeSearchMethod.cosine_similarity,
                NodeSearchMethod.hipporag,
            ]
        )
        assert len(config.search_methods) == 2
        assert NodeSearchMethod.hipporag in config.search_methods


class TestHippoRAGRustClientSerialization:
    """Tests for Rust client serialization of HippoRAG config."""

    def test_serialize_hipporag_search_method(self):
        node_config = NodeSearchConfig(
            search_methods=[NodeSearchMethod.hipporag],
            hipporag_max_hops=3,
            hipporag_decay=0.9,
            hipporag_seed_count=15,
        )
        search_config = SearchConfig(node_config=node_config)

        client = RustSearchClient()
        serialized = client._serialize_config(search_config)

        assert serialized['node_config'] is not None
        assert 'hipporag' in serialized['node_config']['search_methods']
        assert serialized['node_config']['hipporag_max_hops'] == 3
        assert serialized['node_config']['hipporag_decay'] == 0.9
        assert serialized['node_config']['hipporag_seed_count'] == 15

    def test_serialize_combined_methods(self):
        node_config = NodeSearchConfig(
            search_methods=[NodeSearchMethod.cosine_similarity, NodeSearchMethod.hipporag],
        )
        search_config = SearchConfig(node_config=node_config)

        client = RustSearchClient()
        serialized = client._serialize_config(search_config)

        methods = serialized['node_config']['search_methods']
        assert 'similarity' in methods
        assert 'hipporag' in methods
        assert len(methods) == 2
