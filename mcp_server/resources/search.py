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
        
        if not query:
            return ResourceContent(
                text=json.dumps({
                    "error": "Search query is required",
                    "resource_uri": uri,
                    "resource_type": "search_nodes"
                }, indent=2),
                mimeType="application/json"
            )
        
        try:
            # Use the search_memory_nodes functionality
            group_ids = [self.config.group_id] if self.config.group_id else []
            
            payload = {
                'query': query,
                'group_ids': group_ids,
                'num_results': 25,  # Reasonable limit for resource content
            }
            
            response = await self.http_client.post('/search/nodes', json=payload)
            response.raise_for_status()
            
            result = response.json()
            nodes = result.get('nodes', [])
            
            # Format search results for resource consumption
            formatted_data = {
                "query": query,
                "search_type": "nodes",
                "total_results": len(nodes),
                "results": [
                    {
                        "uuid": node.get("uuid", ""),
                        "name": node.get("name", ""),
                        "summary": node.get("summary", ""),
                        "labels": node.get("labels", []),
                        "group_id": node.get("group_id", ""),
                        "created_at": node.get("created_at", ""),
                        "entity_uri": f"graphiti://entity/{node.get('uuid', '')}"
                    }
                    for node in nodes
                ],
                "resource_uri": uri,
                "resource_type": "search_nodes",
                "generated_at": datetime.now(timezone.utc).isoformat()
            }
            
            return ResourceContent(
                text=json.dumps(formatted_data, indent=2),
                mimeType="application/json"
            )
            
        except httpx.HTTPStatusError as e:
            self.logger.error(f"HTTP error searching nodes for '{query}': {e}")
            return ResourceContent(
                text=json.dumps({
                    "error": "Failed to search nodes",
                    "query": query,
                    "status_code": e.response.status_code,
                    "message": f"Server error: {e.response.status_code}"
                }, indent=2),
                mimeType="application/json"
            )
        except Exception as e:
            self.logger.error(f"Error searching nodes for '{query}': {e}")
            return ResourceContent(
                text=json.dumps({
                    "error": "Internal error",
                    "query": query,
                    "message": str(e)
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
        
        if not query:
            return ResourceContent(
                text=json.dumps({
                    "error": "Search query is required",
                    "resource_uri": uri,
                    "resource_type": "search_facts"
                }, indent=2),
                mimeType="application/json"
            )
        
        try:
            # Use the search_memory_facts functionality
            group_ids = [self.config.group_id] if self.config.group_id else []
            
            payload = {
                'query': query,
                'group_ids': group_ids,
                'num_results': 25,  # Reasonable limit for resource content
            }
            
            response = await self.http_client.post('/search', json=payload)
            response.raise_for_status()
            
            result = response.json()
            facts = result.get('edges', [])
            
            # Format search results for resource consumption
            formatted_data = {
                "query": query,
                "search_type": "facts",
                "total_results": len(facts),
                "results": [
                    {
                        "uuid": fact.get("uuid", ""),
                        "relation_type": fact.get("relation_type", ""),
                        "source_node_uuid": fact.get("source_node_uuid", ""),
                        "target_node_uuid": fact.get("target_node_uuid", ""),
                        "group_id": fact.get("group_id", ""),
                        "created_at": fact.get("created_at", ""),
                        "source_entity_uri": f"graphiti://entity/{fact.get('source_node_uuid', '')}",
                        "target_entity_uri": f"graphiti://entity/{fact.get('target_node_uuid', '')}"
                    }
                    for fact in facts
                ],
                "resource_uri": uri,
                "resource_type": "search_facts",
                "generated_at": datetime.now(timezone.utc).isoformat()
            }
            
            return ResourceContent(
                text=json.dumps(formatted_data, indent=2),
                mimeType="application/json"
            )
            
        except httpx.HTTPStatusError as e:
            self.logger.error(f"HTTP error searching facts for '{query}': {e}")
            return ResourceContent(
                text=json.dumps({
                    "error": "Failed to search facts",
                    "query": query,
                    "status_code": e.response.status_code,
                    "message": f"Server error: {e.response.status_code}"
                }, indent=2),
                mimeType="application/json"
            )
        except Exception as e:
            self.logger.error(f"Error searching facts for '{query}': {e}")
            return ResourceContent(
                text=json.dumps({
                    "error": "Internal error",
                    "query": query,
                    "message": str(e)
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
        """Get search content - combines nodes and facts."""
        params = self.extract_params(uri)
        query = params.get('query', '')
        
        if not query:
            return ResourceContent(
                text=json.dumps({
                    "error": "Search query is required",
                    "resource_uri": uri,
                    "resource_type": "search"
                }, indent=2),
                mimeType="application/json"
            )
        
        try:
            # Perform both node and fact searches
            group_ids = [self.config.group_id] if self.config.group_id else []
            
            # Search nodes
            node_payload = {
                'query': query,
                'group_ids': group_ids,
                'num_results': 15,
            }
            
            node_response = await self.http_client.post('/search/nodes', json=node_payload)
            nodes = []
            if node_response.status_code == 200:
                node_result = node_response.json()
                nodes = node_result.get('nodes', [])
            
            # Search facts
            fact_payload = {
                'query': query,
                'group_ids': group_ids,
                'num_results': 15,
            }
            
            fact_response = await self.http_client.post('/search', json=fact_payload)
            facts = []
            if fact_response.status_code == 200:
                fact_result = fact_response.json()
                facts = fact_result.get('edges', [])
            
            # Format combined search results
            formatted_data = {
                "query": query,
                "search_type": "combined",
                "nodes": {
                    "count": len(nodes),
                    "results": [
                        {
                            "uuid": node.get("uuid", ""),
                            "name": node.get("name", ""),
                            "summary": node.get("summary", "")[:100] + "..." if len(node.get("summary", "")) > 100 else node.get("summary", ""),
                            "labels": node.get("labels", []),
                            "entity_uri": f"graphiti://entity/{node.get('uuid', '')}"
                        }
                        for node in nodes[:10]  # Limit for resource size
                    ]
                },
                "facts": {
                    "count": len(facts),
                    "results": [
                        {
                            "uuid": fact.get("uuid", ""),
                            "relation_type": fact.get("relation_type", ""),
                            "source_entity_uri": f"graphiti://entity/{fact.get('source_node_uuid', '')}",
                            "target_entity_uri": f"graphiti://entity/{fact.get('target_node_uuid', '')}"
                        }
                        for fact in facts[:10]  # Limit for resource size
                    ]
                },
                "total_results": len(nodes) + len(facts),
                "resource_uri": uri,
                "resource_type": "search",
                "generated_at": datetime.now(timezone.utc).isoformat()
            }
            
            return ResourceContent(
                text=json.dumps(formatted_data, indent=2),
                mimeType="application/json"
            )
            
        except Exception as e:
            self.logger.error(f"Error in general search for '{query}': {e}")
            return ResourceContent(
                text=json.dumps({
                    "error": "Internal error",
                    "query": query,
                    "message": str(e)
                }, indent=2),
                mimeType="application/json"
            )