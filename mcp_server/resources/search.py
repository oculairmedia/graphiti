"""
Search resource handlers for MCP.
"""

import json
import httpx
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from .base import BaseResourceHandler, ResourceInfo, ResourceContent


class NodeSearchResourceHandler(BaseResourceHandler):
    """Handler for node search resources."""
    
    @property
    def uri_pattern(self) -> str:
        return r"graphiti://search/nodes/{query}"
    
    @property 
    def name(self) -> str:
        return "search_nodes"
    
    @property
    def description(self) -> str:
        return "Search results for nodes matching query"
    
    async def get_resource_info(self, uri: str) -> ResourceInfo:
        """Get search resource information."""
        params = self.extract_params(uri)
        query = params.get('query', 'unknown')
        
        return ResourceInfo(
            uri=uri,
            name=f"search_nodes_{query}",
            title=f"Node Search: {query}",
            description=f"Search results for nodes matching: {query}",
            mimeType="application/json",
            annotations={
                "query": query,
                "resource_type": "search_nodes"
            }
        )
    
    async def get_resource_content(self, uri: str) -> ResourceContent:
        """Get node search content."""
        params = self.extract_params(uri)
        query = params.get('query', '')
        
        # For now, return a placeholder - will be implemented in full system
        return ResourceContent(
            text=json.dumps({
                "query": query,
                "message": "Node search resource handler - implementation pending",
                "resource_uri": uri,
                "resource_type": "search_nodes"
            }, indent=2),
            mimeType="application/json"
        )


class FactSearchResourceHandler(BaseResourceHandler):
    """Handler for fact search resources."""
    
    @property
    def uri_pattern(self) -> str:
        return r"graphiti://search/facts/{query}"
    
    @property
    def name(self) -> str:
        return "search_facts"
    
    @property
    def description(self) -> str:
        return "Search results for facts matching query"
    
    async def get_resource_info(self, uri: str) -> ResourceInfo:
        """Get fact search resource information."""
        params = self.extract_params(uri)
        query = params.get('query', 'unknown')
        
        return ResourceInfo(
            uri=uri,
            name=f"search_facts_{query}",
            title=f"Fact Search: {query}",
            description=f"Search results for facts matching: {query}",
            mimeType="application/json",
            annotations={
                "query": query,
                "resource_type": "search_facts"
            }
        )
    
    async def get_resource_content(self, uri: str) -> ResourceContent:
        """Get fact search content."""
        params = self.extract_params(uri)
        query = params.get('query', '')
        
        # For now, return a placeholder - will be implemented in full system
        return ResourceContent(
            text=json.dumps({
                "query": query,
                "message": "Fact search resource handler - implementation pending",
                "resource_uri": uri,
                "resource_type": "search_facts"
            }, indent=2),
            mimeType="application/json"
        )


class SearchResourceHandler(BaseResourceHandler):
    """General search resource handler."""
    
    @property
    def uri_pattern(self) -> str:
        return r"graphiti://search/{query}"
    
    @property
    def name(self) -> str:
        return "search"
    
    @property
    def description(self) -> str:
        return "General search results for query"
    
    async def get_resource_info(self, uri: str) -> ResourceInfo:
        """Get search resource information.""" 
        params = self.extract_params(uri)
        query = params.get('query', 'unknown')
        
        return ResourceInfo(
            uri=uri,
            name=f"search_{query}",
            title=f"Search: {query}",
            description=f"General search results for: {query}",
            mimeType="application/json",
            annotations={
                "query": query,
                "resource_type": "search"
            }
        )
    
    async def get_resource_content(self, uri: str) -> ResourceContent:
        """Get search content."""
        params = self.extract_params(uri)
        query = params.get('query', '')
        
        # For now, return a placeholder - will be implemented in full system
        return ResourceContent(
            text=json.dumps({
                "query": query,
                "message": "General search resource handler - implementation pending",
                "resource_uri": uri,
                "resource_type": "search"
            }, indent=2),
            mimeType="application/json"
        )