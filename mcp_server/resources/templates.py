"""
Template resource handlers for MCP resources system.
Provides template and wildcard support for dynamic resource patterns.
"""

import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List
import httpx

from .base import BaseResourceHandler, ResourceContent, ResourceInfo


class WildcardResourceHandler(BaseResourceHandler):
    """Handles wildcard patterns via graphiti://templates/wildcard/* patterns."""
    
    @property
    def uri_pattern(self) -> str:
        return r"graphiti://templates/wildcard/(.*)"
    
    async def get_resource_info(self, uri: str) -> ResourceInfo:
        wildcard_path = self._extract_wildcard_path(uri)
        return ResourceInfo(
            uri=uri,
            name=f"Wildcard: {wildcard_path}",
            description=f"Wildcard resource template for pattern: {wildcard_path}",
            mimeType="application/json",
            modified=datetime.now(timezone.utc).isoformat()
        )
    
    async def get_resource_content(self, uri: str) -> ResourceContent:
        try:
            wildcard_path = self._extract_wildcard_path(uri)
            
            # Parse wildcard path to extract parameters
            path_parts = wildcard_path.split('/') if wildcard_path else []
            
            # Create template response with parameter extraction
            content_data = {
                "uri": uri,
                "type": "wildcard-template",
                "wildcard_path": wildcard_path,
                "path_parts": path_parts,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "template_info": {
                    "pattern": "graphiti://templates/wildcard/*",
                    "supports_dynamic_paths": True,
                    "parameter_count": len(path_parts)
                },
                "metadata": {
                    "source": "graphiti-mcp",
                    "template_type": "wildcard",
                    "query_time": datetime.now(timezone.utc).isoformat()
                }
            }
            
            return ResourceContent(
                uri=uri,
                mimeType="application/json",
                text=json.dumps(content_data, indent=2)
            )
            
        except Exception as e:
            error_data = {
                "uri": uri,
                "error": f"Internal error: {str(e)}",
                "wildcard_path": self._extract_wildcard_path(uri) if self._extract_wildcard_path(uri) else "unknown",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            return ResourceContent(
                uri=uri,
                mimeType="application/json",
                text=json.dumps(error_data, indent=2)
            )
    
    def _extract_wildcard_path(self, uri: str) -> str:
        """Extract wildcard path from URI pattern."""
        pattern = re.compile(r"graphiti://templates/wildcard/(.*)")
        match = pattern.match(uri)
        if match:
            return match.group(1)
        return ""


class ParameterizedResourceHandler(BaseResourceHandler):
    """Handles parameterized templates via graphiti://templates/params/{template_name}/{params} patterns."""
    
    @property
    def uri_pattern(self) -> str:
        return r"graphiti://templates/params/([^/]+)/(.*)"
    
    async def get_resource_info(self, uri: str) -> ResourceInfo:
        template_name, params_str = self._extract_template_info(uri)
        return ResourceInfo(
            uri=uri,
            name=f"Template: {template_name}",
            description=f"Parameterized template {template_name} with parameters: {params_str}",
            mimeType="application/json",
            modified=datetime.now(timezone.utc).isoformat()
        )
    
    async def get_resource_content(self, uri: str) -> ResourceContent:
        try:
            template_name, params_str = self._extract_template_info(uri)
            
            # Parse parameters from path
            params_list = params_str.split('/') if params_str else []
            
            # Create template response with structured parameters
            content_data = {
                "uri": uri,
                "type": "parameterized-template",
                "template_name": template_name,
                "parameters": {
                    "raw_params": params_str,
                    "parsed_params": params_list,
                    "param_count": len(params_list)
                },
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "template_info": {
                    "pattern": "graphiti://templates/params/{template_name}/{params}",
                    "supports_parameters": True,
                    "template_name": template_name
                },
                "metadata": {
                    "source": "graphiti-mcp",
                    "template_type": "parameterized",
                    "query_time": datetime.now(timezone.utc).isoformat()
                }
            }
            
            return ResourceContent(
                uri=uri,
                mimeType="application/json",
                text=json.dumps(content_data, indent=2)
            )
            
        except Exception as e:
            template_name, params_str = self._extract_template_info(uri)
            error_data = {
                "uri": uri,
                "error": f"Internal error: {str(e)}",
                "template_name": template_name if template_name else "unknown",
                "params": params_str if params_str else "none",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            return ResourceContent(
                uri=uri,
                mimeType="application/json",
                text=json.dumps(error_data, indent=2)
            )
    
    def _extract_template_info(self, uri: str) -> tuple[str, str]:
        """Extract template name and parameters from URI pattern."""
        pattern = re.compile(r"graphiti://templates/params/([^/]+)/(.*)")
        match = pattern.match(uri)
        if match:
            return match.group(1), match.group(2)
        return "", ""


class DynamicResourceHandler(BaseResourceHandler):
    """Handles dynamic resource generation via graphiti://templates/dynamic/{resource_type} patterns."""
    
    @property
    def uri_pattern(self) -> str:
        return r"graphiti://templates/dynamic/([^/]+)"
    
    async def get_resource_info(self, uri: str) -> ResourceInfo:
        resource_type = self._extract_resource_type(uri)
        return ResourceInfo(
            uri=uri,
            name=f"Dynamic: {resource_type}",
            description=f"Dynamic resource template for type: {resource_type}",
            mimeType="application/json",
            modified=datetime.now(timezone.utc).isoformat()
        )
    
    async def get_resource_content(self, uri: str) -> ResourceContent:
        try:
            resource_type = self._extract_resource_type(uri)
            
            # Generate dynamic content based on resource type
            if resource_type == "summary":
                # Generate resource summary
                content_data = await self._generate_resource_summary()
            elif resource_type == "registry":
                # Generate resource registry
                content_data = await self._generate_resource_registry()
            elif resource_type == "patterns":
                # Generate pattern documentation
                content_data = await self._generate_pattern_docs()
            else:
                # Default template info
                content_data = {
                    "uri": uri,
                    "type": "dynamic-template",
                    "resource_type": resource_type,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "message": f"Dynamic resource template for {resource_type}",
                    "template_info": {
                        "pattern": "graphiti://templates/dynamic/{resource_type}",
                        "supports_dynamic_generation": True,
                        "resource_type": resource_type
                    },
                    "metadata": {
                        "source": "graphiti-mcp",
                        "template_type": "dynamic",
                        "query_time": datetime.now(timezone.utc).isoformat()
                    }
                }
            
            return ResourceContent(
                uri=uri,
                mimeType="application/json",
                text=json.dumps(content_data, indent=2)
            )
            
        except Exception as e:
            error_data = {
                "uri": uri,
                "error": f"Internal error: {str(e)}",
                "resource_type": self._extract_resource_type(uri) if self._extract_resource_type(uri) else "unknown",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            return ResourceContent(
                uri=uri,
                mimeType="application/json",
                text=json.dumps(error_data, indent=2)
            )
    
    def _extract_resource_type(self, uri: str) -> str:
        """Extract resource type from URI pattern."""
        pattern = re.compile(r"graphiti://templates/dynamic/([^/]+)")
        match = pattern.match(uri)
        if match:
            return match.group(1)
        return ""
    
    async def _generate_resource_summary(self) -> Dict[str, Any]:
        """Generate a summary of all available resources."""
        return {
            "uri": "graphiti://templates/dynamic/summary",
            "type": "resource-summary",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "resources": {
                "entities": ["graphiti://entity/{entity_id}", "graphiti://entities/{entity_type}", "graphiti://entities/recent"],
                "episodes": ["graphiti://episode/{episode_id}", "graphiti://episodes/recent"],
                "search": ["graphiti://search/{query}", "graphiti://search/nodes/{query}", "graphiti://search/facts/{query}"],
                "analytics": [
                    "graphiti://analytics/graph-stats",
                    "graphiti://analytics/nodes/{node_id}/metrics",
                    "graphiti://analytics/temporal/{time_range}",
                    "graphiti://analytics/groups/{group_id}"
                ],
                "templates": [
                    "graphiti://templates/wildcard/*",
                    "graphiti://templates/params/{template_name}/{params}",
                    "graphiti://templates/dynamic/{resource_type}"
                ]
            },
            "metadata": {
                "total_patterns": 13,
                "template_patterns": 3,
                "data_patterns": 10,
                "generated_at": datetime.now(timezone.utc).isoformat()
            }
        }
    
    async def _generate_resource_registry(self) -> Dict[str, Any]:
        """Generate a registry of all resource handlers."""
        return {
            "uri": "graphiti://templates/dynamic/registry",
            "type": "resource-registry",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "registry": {
                "entity_handlers": ["EntityResourceHandler", "EntityListResourceHandler", "EntityRecentResourceHandler"],
                "episode_handlers": ["EpisodeResourceHandler", "EpisodeListResourceHandler"],
                "search_handlers": ["NodeSearchResourceHandler", "FactSearchResourceHandler", "SearchResourceHandler"],
                "analytics_handlers": [
                    "GraphStatsResourceHandler", 
                    "NodeMetricsResourceHandler", 
                    "TemporalAnalyticsResourceHandler", 
                    "GroupAnalyticsResourceHandler"
                ],
                "template_handlers": ["WildcardResourceHandler", "ParameterizedResourceHandler", "DynamicResourceHandler"]
            },
            "metadata": {
                "total_handlers": 12,
                "handler_categories": 5,
                "supports_wildcards": True,
                "supports_parameters": True,
                "supports_dynamic_generation": True
            }
        }
    
    async def _generate_pattern_docs(self) -> Dict[str, Any]:
        """Generate documentation for URI patterns."""
        return {
            "uri": "graphiti://templates/dynamic/patterns",
            "type": "pattern-documentation",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "patterns": {
                "entity_patterns": {
                    "single": "graphiti://entity/{entity_id}",
                    "by_type": "graphiti://entities/{entity_type}",
                    "recent": "graphiti://entities/recent"
                },
                "episode_patterns": {
                    "single": "graphiti://episode/{episode_id}",
                    "recent": "graphiti://episodes/recent"
                },
                "search_patterns": {
                    "combined": "graphiti://search/{query}",
                    "nodes": "graphiti://search/nodes/{query}",
                    "facts": "graphiti://search/facts/{query}"
                },
                "analytics_patterns": {
                    "graph_stats": "graphiti://analytics/graph-stats",
                    "node_metrics": "graphiti://analytics/nodes/{node_id}/metrics",
                    "temporal": "graphiti://analytics/temporal/{time_range}",
                    "group": "graphiti://analytics/groups/{group_id}"
                },
                "template_patterns": {
                    "wildcard": "graphiti://templates/wildcard/*",
                    "parameterized": "graphiti://templates/params/{template_name}/{params}",
                    "dynamic": "graphiti://templates/dynamic/{resource_type}"
                }
            },
            "usage_examples": {
                "entity_lookup": "graphiti://entity/12345",
                "recent_episodes": "graphiti://episodes/recent",
                "node_search": "graphiti://search/nodes/alice",
                "graph_stats": "graphiti://analytics/graph-stats",
                "wildcard_demo": "graphiti://templates/wildcard/demo/path/here",
                "parameterized_demo": "graphiti://templates/params/user-query/alice/recent/10"
            }
        }


class TemplateRegistryResourceHandler(BaseResourceHandler):
    """Handles template registry via graphiti://templates/registry pattern."""
    
    @property
    def uri_pattern(self) -> str:
        return r"graphiti://templates/registry"
    
    async def get_resource_info(self, uri: str) -> ResourceInfo:
        return ResourceInfo(
            uri=uri,
            name="Template Registry",
            description="Registry of all available template patterns and handlers",
            mimeType="application/json",
            modified=datetime.now(timezone.utc).isoformat()
        )
    
    async def get_resource_content(self, uri: str) -> ResourceContent:
        try:
            # Generate comprehensive template registry
            content_data = {
                "uri": uri,
                "type": "template-registry",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "template_system": {
                    "version": "1.0.0",
                    "features": ["wildcards", "parameterization", "dynamic_generation"],
                    "supported_schemes": ["graphiti"]
                },
                "available_templates": {
                    "wildcard": {
                        "pattern": "graphiti://templates/wildcard/*",
                        "description": "Catch-all template for arbitrary paths",
                        "examples": [
                            "graphiti://templates/wildcard/any/path/here",
                            "graphiti://templates/wildcard/demo/123/test"
                        ]
                    },
                    "parameterized": {
                        "pattern": "graphiti://templates/params/{template_name}/{params}",
                        "description": "Template with named parameters",
                        "examples": [
                            "graphiti://templates/params/user-data/alice/profile",
                            "graphiti://templates/params/search-query/entities/recent/5"
                        ]
                    },
                    "dynamic": {
                        "pattern": "graphiti://templates/dynamic/{resource_type}",
                        "description": "Dynamically generated resources",
                        "examples": [
                            "graphiti://templates/dynamic/summary",
                            "graphiti://templates/dynamic/registry",
                            "graphiti://templates/dynamic/patterns"
                        ]
                    }
                },
                "metadata": {
                    "source": "graphiti-mcp",
                    "total_templates": 4,
                    "supports_nested_parameters": True,
                    "query_time": datetime.now(timezone.utc).isoformat()
                }
            }
            
            return ResourceContent(
                uri=uri,
                mimeType="application/json",
                text=json.dumps(content_data, indent=2)
            )
            
        except Exception as e:
            error_data = {
                "uri": uri,
                "error": f"Internal error: {str(e)}",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            return ResourceContent(
                uri=uri,
                mimeType="application/json",
                text=json.dumps(error_data, indent=2)
            )