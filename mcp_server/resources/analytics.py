"""
Analytics resource handlers for MCP resources system.
Provides graph analytics, statistics, and metrics via URI patterns.
"""

import json
import re
from datetime import datetime, timezone
from typing import Any, Dict
import httpx

from .base import BaseResourceHandler, ResourceContent, ResourceInfo


class GraphStatsResourceHandler(BaseResourceHandler):
    """Handles graph statistics via graphiti://analytics/graph-stats pattern."""
    
    @property
    def name(self) -> str:
        return "graph-stats"
    
    @property
    def description(self) -> str:
        return "Overall graph statistics including node count, edge count, and group information"
    
    @property
    def uri_pattern(self) -> str:
        return r"graphiti://analytics/graph-stats"
    
    async def get_resource_info(self, uri: str) -> ResourceInfo:
        return ResourceInfo(
            uri=uri,
            name="Graph Statistics",
            description="Overall graph statistics including node count, edge count, and group information",
            mimeType="application/json",
            modified=datetime.now(timezone.utc).isoformat()
        )
    
    async def get_resource_content(self, uri: str) -> ResourceContent:
        try:
            # Get graph stats from FastAPI endpoint
            response = await self.http_client.get('/analytics/graph-stats')
            response.raise_for_status()
            
            stats_data = response.json()
            
            # Format the response as structured JSON
            content_data = {
                "uri": uri,
                "type": "graph-statistics",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "statistics": stats_data,
                "metadata": {
                    "source": "graphiti-fastapi",
                    "query_time": datetime.now(timezone.utc).isoformat()
                }
            }
            
            return ResourceContent(
                uri=uri,
                mimeType="application/json", 
                text=json.dumps(content_data, indent=2)
            )
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                error_data = {
                    "uri": uri,
                    "error": "Graph statistics not found",
                    "status_code": 404,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            else:
                error_data = {
                    "uri": uri,
                    "error": f"HTTP error {e.response.status_code}: {e.response.text}",
                    "status_code": e.response.status_code,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            return ResourceContent(
                uri=uri,
                mimeType="application/json",
                text=json.dumps(error_data, indent=2)
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


class NodeMetricsResourceHandler(BaseResourceHandler):
    """Handles node metrics via graphiti://analytics/nodes/{node_id}/metrics pattern."""
    
    @property
    def name(self) -> str:
        return "node-metrics"
    
    @property
    def description(self) -> str:
        return "Detailed metrics for individual nodes including centrality scores and relationships"
    
    @property
    def uri_pattern(self) -> str:
        return r"graphiti://analytics/nodes/([^/]+)/metrics"
    
    async def get_resource_info(self, uri: str) -> ResourceInfo:
        node_id = self._extract_node_id(uri)
        return ResourceInfo(
            uri=uri,
            name=f"Node Metrics: {node_id}",
            description=f"Metrics and analytics for node {node_id}",
            mimeType="application/json",
            modified=datetime.now(timezone.utc).isoformat()
        )
    
    async def get_resource_content(self, uri: str) -> ResourceContent:
        try:
            node_id = self._extract_node_id(uri)
            
            # Get node metrics from FastAPI endpoint
            response = await self.http_client.get(f'/analytics/nodes/{node_id}/metrics')
            response.raise_for_status()
            
            metrics_data = response.json()
            
            # Format the response as structured JSON
            content_data = {
                "uri": uri,
                "type": "node-metrics",
                "node_id": node_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "metrics": metrics_data,
                "metadata": {
                    "source": "graphiti-fastapi",
                    "query_time": datetime.now(timezone.utc).isoformat()
                }
            }
            
            return ResourceContent(
                uri=uri,
                mimeType="application/json",
                text=json.dumps(content_data, indent=2)
            )
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                error_data = {
                    "uri": uri,
                    "error": f"Node metrics not found for {self._extract_node_id(uri)}",
                    "node_id": self._extract_node_id(uri),
                    "status_code": 404,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            else:
                error_data = {
                    "uri": uri,
                    "error": f"HTTP error {e.response.status_code}: {e.response.text}",
                    "node_id": self._extract_node_id(uri),
                    "status_code": e.response.status_code,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            return ResourceContent(
                uri=uri,
                mimeType="application/json",
                text=json.dumps(error_data, indent=2)
            )
        except Exception as e:
            error_data = {
                "uri": uri,
                "error": f"Internal error: {str(e)}",
                "node_id": self._extract_node_id(uri) if self._extract_node_id(uri) else "unknown",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            return ResourceContent(
                uri=uri,
                mimeType="application/json",
                text=json.dumps(error_data, indent=2)
            )
    
    def _extract_node_id(self, uri: str) -> str:
        """Extract node ID from URI pattern."""
        pattern = re.compile(r"graphiti://analytics/nodes/([^/]+)/metrics")
        match = pattern.match(uri)
        if match:
            return match.group(1)
        return ""


class TemporalAnalyticsResourceHandler(BaseResourceHandler):
    """Handles temporal analytics via graphiti://analytics/temporal/{time_range} pattern."""
    
    @property
    def name(self) -> str:
        return "temporal-analytics"
    
    @property
    def description(self) -> str:
        return "Time-based analytics showing graph evolution and activity patterns over different time ranges"
    
    @property
    def uri_pattern(self) -> str:
        return r"graphiti://analytics/temporal/([^/]+)"
    
    async def get_resource_info(self, uri: str) -> ResourceInfo:
        time_range = self._extract_time_range(uri)
        return ResourceInfo(
            uri=uri,
            name=f"Temporal Analytics: {time_range}",
            description=f"Temporal analytics and trends for {time_range}",
            mimeType="application/json",
            modified=datetime.now(timezone.utc).isoformat()
        )
    
    async def get_resource_content(self, uri: str) -> ResourceContent:
        try:
            time_range = self._extract_time_range(uri)
            
            # Get temporal analytics from FastAPI endpoint
            response = await self.http_client.get(f'/analytics/temporal/{time_range}')
            response.raise_for_status()
            
            analytics_data = response.json()
            
            # Format the response as structured JSON
            content_data = {
                "uri": uri,
                "type": "temporal-analytics",
                "time_range": time_range,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "analytics": analytics_data,
                "metadata": {
                    "source": "graphiti-fastapi",
                    "query_time": datetime.now(timezone.utc).isoformat()
                }
            }
            
            return ResourceContent(
                uri=uri,
                mimeType="application/json",
                text=json.dumps(content_data, indent=2)
            )
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                error_data = {
                    "uri": uri,
                    "error": f"Temporal analytics not found for {self._extract_time_range(uri)}",
                    "time_range": self._extract_time_range(uri),
                    "status_code": 404,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            else:
                error_data = {
                    "uri": uri,
                    "error": f"HTTP error {e.response.status_code}: {e.response.text}",
                    "time_range": self._extract_time_range(uri),
                    "status_code": e.response.status_code,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            return ResourceContent(
                uri=uri,
                mimeType="application/json",
                text=json.dumps(error_data, indent=2)
            )
        except Exception as e:
            error_data = {
                "uri": uri,
                "error": f"Internal error: {str(e)}",
                "time_range": self._extract_time_range(uri) if self._extract_time_range(uri) else "unknown",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            return ResourceContent(
                uri=uri,
                mimeType="application/json",
                text=json.dumps(error_data, indent=2)
            )
    
    def _extract_time_range(self, uri: str) -> str:
        """Extract time range from URI pattern."""
        pattern = re.compile(r"graphiti://analytics/temporal/([^/]+)")
        match = pattern.match(uri)
        if match:
            return match.group(1)
        return ""


class GroupAnalyticsResourceHandler(BaseResourceHandler):
    """Handles group analytics via graphiti://analytics/groups/{group_id} pattern."""
    
    @property
    def name(self) -> str:
        return "group-analytics"
    
    @property
    def description(self) -> str:
        return "Analytics and statistics for specific graph groups including node distributions and activity metrics"
    
    @property
    def uri_pattern(self) -> str:
        return r"graphiti://analytics/groups/([^/]+)"
    
    async def get_resource_info(self, uri: str) -> ResourceInfo:
        group_id = self._extract_group_id(uri)
        return ResourceInfo(
            uri=uri,
            name=f"Group Analytics: {group_id}",
            description=f"Analytics and statistics for group {group_id}",
            mimeType="application/json",
            modified=datetime.now(timezone.utc).isoformat()
        )
    
    async def get_resource_content(self, uri: str) -> ResourceContent:
        try:
            group_id = self._extract_group_id(uri)
            
            # Get group analytics from FastAPI endpoint
            response = await self.http_client.get(f'/analytics/groups/{group_id}')
            response.raise_for_status()
            
            analytics_data = response.json()
            
            # Format the response as structured JSON
            content_data = {
                "uri": uri,
                "type": "group-analytics",
                "group_id": group_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "analytics": analytics_data,
                "metadata": {
                    "source": "graphiti-fastapi",
                    "query_time": datetime.now(timezone.utc).isoformat()
                }
            }
            
            return ResourceContent(
                uri=uri,
                mimeType="application/json",
                text=json.dumps(content_data, indent=2)
            )
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                error_data = {
                    "uri": uri,
                    "error": f"Group analytics not found for {self._extract_group_id(uri)}",
                    "group_id": self._extract_group_id(uri),
                    "status_code": 404,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            else:
                error_data = {
                    "uri": uri,
                    "error": f"HTTP error {e.response.status_code}: {e.response.text}",
                    "group_id": self._extract_group_id(uri),
                    "status_code": e.response.status_code,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            return ResourceContent(
                uri=uri,
                mimeType="application/json",
                text=json.dumps(error_data, indent=2)
            )
        except Exception as e:
            error_data = {
                "uri": uri,
                "error": f"Internal error: {str(e)}",
                "group_id": self._extract_group_id(uri) if self._extract_group_id(uri) else "unknown",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            return ResourceContent(
                uri=uri,
                mimeType="application/json",
                text=json.dumps(error_data, indent=2)
            )
    
    def _extract_group_id(self, uri: str) -> str:
        """Extract group ID from URI pattern."""
        pattern = re.compile(r"graphiti://analytics/groups/([^/]+)")
        match = pattern.match(uri)
        if match:
            return match.group(1)
        return ""