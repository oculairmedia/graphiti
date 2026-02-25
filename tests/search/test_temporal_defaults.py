"""Tests for temporal validity defaults in search pipeline."""

import os
from unittest.mock import patch

from graphiti_core.search.search_filters import (
    SearchFilters,
    edge_search_filter_query_constructor,
)


class TestExcludeInvalidated:
    """Tests for exclude_invalidated filter."""

    def test_default_is_false(self):
        """Backward compat: exclude_invalidated defaults to False."""
        filters = SearchFilters()
        assert filters.exclude_invalidated is False

    def test_exclude_invalidated_true(self):
        """Can set exclude_invalidated to True."""
        filters = SearchFilters(exclude_invalidated=True)
        assert filters.exclude_invalidated is True

    def test_current_only_classmethod(self):
        """SearchFilters.current_only() creates filter with exclude_invalidated=True."""
        filters = SearchFilters.current_only()
        assert filters.exclude_invalidated is True

    def test_current_only_with_extra_filters(self):
        """current_only() accepts additional filter kwargs."""
        filters = SearchFilters.current_only(node_labels=['Person'])
        assert filters.exclude_invalidated is True
        assert filters.node_labels == ['Person']


class TestEdgeFilterQueryConstruction:
    """Tests for edge search filter query construction with temporal defaults."""

    def test_exclude_invalidated_appends_null_check(self):
        """When exclude_invalidated=True, adds IS NULL check for invalid_at."""
        filters = SearchFilters(exclude_invalidated=True)
        query, params = edge_search_filter_query_constructor(filters)
        assert 'r.invalid_at IS NULL' in query

    def test_default_does_not_add_null_check(self):
        """When exclude_invalidated=False (default), no IS NULL added."""
        filters = SearchFilters()
        query, params = edge_search_filter_query_constructor(filters)
        assert 'invalid_at IS NULL' not in query

    def test_exclude_invalidated_with_other_filters(self):
        """exclude_invalidated works alongside other filters."""
        filters = SearchFilters(
            exclude_invalidated=True,
            edge_types=['RELATES_TO'],
        )
        query, params = edge_search_filter_query_constructor(filters)
        assert 'r.invalid_at IS NULL' in query
        assert 'r.name in $edge_types' in query

    def test_explicit_invalid_at_filter_still_works(self):
        """Existing DateFilter-based invalid_at filtering still works."""
        from datetime import datetime
        from graphiti_core.search.search_filters import DateFilter, ComparisonOperator

        date_filter = DateFilter(
            date=datetime(2025, 1, 1),
            comparison_operator=ComparisonOperator.less_than,
        )
        filters = SearchFilters(invalid_at=[[date_filter]])
        query, params = edge_search_filter_query_constructor(filters)
        assert 'r.invalid_at' in query
        assert 'invalid_at_0' in params


class TestEnvVarOverride:
    """Tests for SEARCH_EXCLUDE_INVALIDATED env var."""

    def test_env_var_enables_filtering(self):
        """SEARCH_EXCLUDE_INVALIDATED=true enables filtering globally."""
        filters = SearchFilters()  # exclude_invalidated=False
        with patch.dict(os.environ, {'SEARCH_EXCLUDE_INVALIDATED': 'true'}):
            query, params = edge_search_filter_query_constructor(filters)
            assert 'r.invalid_at IS NULL' in query

    def test_env_var_false_no_filtering(self):
        """SEARCH_EXCLUDE_INVALIDATED=false does not enable filtering."""
        filters = SearchFilters()
        with patch.dict(os.environ, {'SEARCH_EXCLUDE_INVALIDATED': 'false'}):
            query, params = edge_search_filter_query_constructor(filters)
            assert 'invalid_at IS NULL' not in query

    def test_explicit_true_overrides_env_false(self):
        """Explicit exclude_invalidated=True works even if env says false."""
        filters = SearchFilters(exclude_invalidated=True)
        with patch.dict(os.environ, {'SEARCH_EXCLUDE_INVALIDATED': 'false'}):
            query, params = edge_search_filter_query_constructor(filters)
            assert 'r.invalid_at IS NULL' in query


class TestNodeSearchUnaffected:
    """Tests that node search is not affected by edge-only temporal filter."""

    def test_node_filter_no_invalidated_clause(self):
        """Node search filter constructor does not add invalid_at clause."""
        from graphiti_core.search.search_filters import node_search_filter_query_constructor

        filters = SearchFilters(exclude_invalidated=True)
        query, params = node_search_filter_query_constructor(filters)
        assert 'invalid_at' not in query
