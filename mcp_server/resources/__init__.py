"""
Graphiti MCP Resources System

This module implements the MCP resources system for exposing Graphiti knowledge graph data
as accessible resources via URI patterns.
"""

from .base import ResourceManager, BaseResourceHandler
from .entities import EntityResourceHandler, EntityListResourceHandler, EntityRecentResourceHandler
from .episodes import EpisodeResourceHandler, EpisodeListResourceHandler
from .search import SearchResourceHandler, NodeSearchResourceHandler, FactSearchResourceHandler
from .analytics import GraphStatsResourceHandler, NodeMetricsResourceHandler, TemporalAnalyticsResourceHandler, GroupAnalyticsResourceHandler
from .templates import WildcardResourceHandler, ParameterizedResourceHandler, DynamicResourceHandler, TemplateRegistryResourceHandler

__all__ = [
    'ResourceManager',
    'BaseResourceHandler',
    'EntityResourceHandler',
    'EntityListResourceHandler',
    'EntityRecentResourceHandler',
    'EpisodeResourceHandler',
    'EpisodeListResourceHandler',
    'SearchResourceHandler',
    'NodeSearchResourceHandler',
    'FactSearchResourceHandler',
    'GraphStatsResourceHandler',
    'NodeMetricsResourceHandler',
    'TemporalAnalyticsResourceHandler',
    'GroupAnalyticsResourceHandler',
    'WildcardResourceHandler',
    'ParameterizedResourceHandler',
    'DynamicResourceHandler',
    'TemplateRegistryResourceHandler',
]