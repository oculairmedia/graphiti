"""
Entity resource handlers for MCP.
"""

import json
import httpx
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from .base import BaseResourceHandler, ResourceInfo, ResourceContent


class EntityResourceHandler(BaseResourceHandler):
    """Handler for individual entity resources."""
    
    @property
    def uri_pattern(self) -> str:
        return r"graphiti://entity/{entity_id}"
    
    @property 
    def name(self) -> str:
        return "entity"
    
    @property
    def description(self) -> str:
        return "Individual entity from the knowledge graph"
    
    async def get_resource_info(self, uri: str) -> ResourceInfo:
        """Get entity resource information."""
        params = self.extract_params(uri)
        entity_id = params.get('entity_id', 'unknown')
        
        return ResourceInfo(
            uri=uri,
            name=f"entity_{entity_id}",
            title=f"Entity {entity_id}",
            description=f"Knowledge graph entity with ID: {entity_id}",
            mimeType="application/json",
            annotations={
                "entity_id": entity_id,
                "resource_type": "entity"
            }
        )
    
    async def get_resource_content(self, uri: str) -> ResourceContent:
        """Get entity content from the knowledge graph."""
        params = self.extract_params(uri)
        entity_id = params.get('entity_id')
        
        if not entity_id:
            raise ValueError("Entity ID is required")
        
        try:
            # Query the FastAPI server for entity details
            response = await self.http_client.get(f'/entity/{entity_id}')
            
            if response.status_code == 404:
                return ResourceContent(
                    text=json.dumps({
                        "error": "Entity not found",
                        "entity_id": entity_id,
                        "message": f"No entity found with ID: {entity_id}"
                    }, indent=2),
                    mimeType="application/json"
                )
            
            response.raise_for_status()
            entity_data = response.json()
            
            # Format entity data for resource consumption
            formatted_data = {
                "entity_id": entity_id,
                "uuid": entity_data.get("uuid", entity_id),
                "name": entity_data.get("name", ""),
                "summary": entity_data.get("summary", ""),
                "labels": entity_data.get("labels", []),
                "group_id": entity_data.get("group_id", ""),
                "created_at": entity_data.get("created_at", ""),
                "updated_at": entity_data.get("updated_at", ""),
                "attributes": entity_data.get("attributes", {}),
                "relationships": entity_data.get("relationships", []),
                "resource_uri": uri,
                "resource_type": "entity"
            }
            
            return ResourceContent(
                text=json.dumps(formatted_data, indent=2),
                mimeType="application/json"
            )
            
        except httpx.HTTPStatusError as e:
            self.logger.error(f"HTTP error getting entity {entity_id}: {e}")
            return ResourceContent(
                text=json.dumps({
                    "error": "Failed to retrieve entity",
                    "entity_id": entity_id,
                    "status_code": e.response.status_code,
                    "message": f"Server error: {e.response.status_code}"
                }, indent=2),
                mimeType="application/json"
            )
        except Exception as e:
            self.logger.error(f"Error getting entity {entity_id}: {e}")
            return ResourceContent(
                text=json.dumps({
                    "error": "Internal error",
                    "entity_id": entity_id,
                    "message": str(e)
                }, indent=2),
                mimeType="application/json"
            )


class EntityListResourceHandler(BaseResourceHandler):
    """Handler for entity list resources by type."""
    
    @property
    def uri_pattern(self) -> str:
        return r"graphiti://entities/{entity_type}"
    
    @property
    def name(self) -> str:
        return "entities_by_type"
    
    @property
    def description(self) -> str:
        return "List of entities filtered by type"
    
    async def get_resource_info(self, uri: str) -> ResourceInfo:
        """Get entity list resource information."""
        params = self.extract_params(uri)
        entity_type = params.get('entity_type', 'all')
        
        return ResourceInfo(
            uri=uri,
            name=f"entities_{entity_type}",
            title=f"Entities of type: {entity_type}",
            description=f"List of knowledge graph entities with type: {entity_type}",
            mimeType="application/json",
            annotations={
                "entity_type": entity_type,
                "resource_type": "entity_list"
            }
        )
    
    async def get_resource_content(self, uri: str) -> ResourceContent:
        """Get entity list content filtered by type."""
        params = self.extract_params(uri)
        entity_type = params.get('entity_type', 'all')
        
        try:
            # Use the search endpoint to find entities by type
            group_ids = [self.config.group_id] if self.config.group_id else []
            
            payload = {
                'query': f'entities of type {entity_type}',
                'group_ids': group_ids,
                'num_results': 50,  # Reasonable limit for resource content
                'entity_types': [entity_type] if entity_type != 'all' else []
            }
            
            response = await self.http_client.post('/search/nodes', json=payload)
            response.raise_for_status()
            
            result = response.json()
            entities = result.get('nodes', [])
            
            # Format entities for resource consumption
            formatted_data = {
                "entity_type": entity_type,
                "total_count": len(entities),
                "entities": [
                    {
                        "uuid": entity.get("uuid", ""),
                        "name": entity.get("name", ""),
                        "summary": entity.get("summary", ""),
                        "labels": entity.get("labels", []),
                        "group_id": entity.get("group_id", ""),
                        "created_at": entity.get("created_at", ""),
                        "entity_uri": f"graphiti://entity/{entity.get('uuid', '')}"
                    }
                    for entity in entities
                ],
                "resource_uri": uri,
                "resource_type": "entity_list",
                "generated_at": datetime.now(timezone.utc).isoformat()
            }
            
            return ResourceContent(
                text=json.dumps(formatted_data, indent=2),
                mimeType="application/json"
            )
            
        except httpx.HTTPStatusError as e:
            self.logger.error(f"HTTP error getting entities of type {entity_type}: {e}")
            return ResourceContent(
                text=json.dumps({
                    "error": "Failed to retrieve entities",
                    "entity_type": entity_type,
                    "status_code": e.response.status_code,
                    "message": f"Server error: {e.response.status_code}"
                }, indent=2),
                mimeType="application/json"
            )
        except Exception as e:
            self.logger.error(f"Error getting entities of type {entity_type}: {e}")
            return ResourceContent(
                text=json.dumps({
                    "error": "Internal error",
                    "entity_type": entity_type,
                    "message": str(e)
                }, indent=2),
                mimeType="application/json"
            )


class EntityRecentResourceHandler(BaseResourceHandler):
    """Handler for recent entities resource."""
    
    @property
    def uri_pattern(self) -> str:
        return r"graphiti://entities/recent"
    
    @property
    def name(self) -> str:
        return "recent_entities"
    
    @property
    def description(self) -> str:
        return "Recently created entities in the knowledge graph"
    
    async def get_resource_info(self, uri: str) -> ResourceInfo:
        """Get recent entities resource information."""
        return ResourceInfo(
            uri=uri,
            name="recent_entities",
            title="Recent Entities",
            description="Recently created entities in the knowledge graph",
            mimeType="application/json",
            annotations={
                "resource_type": "entity_list",
                "filter": "recent"
            }
        )
    
    async def get_resource_content(self, uri: str) -> ResourceContent:
        """Get recent entities content."""
        try:
            # Use search to get recent entities (simple approach)
            group_ids = [self.config.group_id] if self.config.group_id else []
            
            payload = {
                'query': 'recent entities',
                'group_ids': group_ids, 
                'num_results': 20  # Recent entities limit
            }
            
            response = await self.http_client.post('/search/nodes', json=payload)
            response.raise_for_status()
            
            result = response.json()
            entities = result.get('nodes', [])
            
            # Sort by created_at if available
            entities.sort(key=lambda x: x.get('created_at', ''), reverse=True)
            
            formatted_data = {
                "filter": "recent",
                "total_count": len(entities),
                "entities": [
                    {
                        "uuid": entity.get("uuid", ""),
                        "name": entity.get("name", ""),
                        "summary": entity.get("summary", "")[:100] + "..." if len(entity.get("summary", "")) > 100 else entity.get("summary", ""),
                        "labels": entity.get("labels", []),
                        "group_id": entity.get("group_id", ""),
                        "created_at": entity.get("created_at", ""),
                        "entity_uri": f"graphiti://entity/{entity.get('uuid', '')}"
                    }
                    for entity in entities
                ],
                "resource_uri": uri,
                "resource_type": "entity_list",
                "generated_at": datetime.now(timezone.utc).isoformat()
            }
            
            return ResourceContent(
                text=json.dumps(formatted_data, indent=2),
                mimeType="application/json"
            )
            
        except Exception as e:
            self.logger.error(f"Error getting recent entities: {e}")
            return ResourceContent(
                text=json.dumps({
                    "error": "Failed to retrieve recent entities",
                    "message": str(e)
                }, indent=2),
                mimeType="application/json"
            )