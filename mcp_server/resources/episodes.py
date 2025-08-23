"""
Episode resource handlers for MCP.
"""

import json
import httpx
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from .base import BaseResourceHandler, ResourceInfo, ResourceContent


class EpisodeResourceHandler(BaseResourceHandler):
    """Handler for individual episode resources."""
    
    @property
    def uri_pattern(self) -> str:
        return r"graphiti://episode/{episode_id}"
    
    @property 
    def name(self) -> str:
        return "episode"
    
    @property
    def description(self) -> str:
        return "Individual episode from the knowledge graph"
    
    async def get_resource_info(self, uri: str) -> ResourceInfo:
        """Get episode resource information."""
        params = self.extract_params(uri)
        episode_id = params.get('episode_id', 'unknown')
        
        return ResourceInfo(
            uri=uri,
            name=f"episode_{episode_id}",
            title=f"Episode {episode_id}",
            description=f"Knowledge graph episode with ID: {episode_id}",
            mimeType="application/json",
            annotations={
                "episode_id": episode_id,
                "resource_type": "episode"
            }
        )
    
    async def get_resource_content(self, uri: str) -> ResourceContent:
        """Get episode content from the knowledge graph."""
        params = self.extract_params(uri)
        episode_id = params.get('episode_id')
        
        if not episode_id:
            raise ValueError("Episode ID is required")
        
        # For now, return a placeholder - will be implemented in full system
        return ResourceContent(
            text=json.dumps({
                "episode_id": episode_id,
                "message": "Episode resource handler - implementation pending",
                "resource_uri": uri,
                "resource_type": "episode"
            }, indent=2),
            mimeType="application/json"
        )


class EpisodeListResourceHandler(BaseResourceHandler):
    """Handler for episode list resources."""
    
    @property
    def uri_pattern(self) -> str:
        return r"graphiti://episodes/recent"
    
    @property
    def name(self) -> str:
        return "recent_episodes"
    
    @property
    def description(self) -> str:
        return "Recently created episodes in the knowledge graph"
    
    async def get_resource_info(self, uri: str) -> ResourceInfo:
        """Get episode list resource information."""
        return ResourceInfo(
            uri=uri,
            name="recent_episodes",
            title="Recent Episodes",
            description="Recently created episodes in the knowledge graph",
            mimeType="application/json",
            annotations={
                "resource_type": "episode_list"
            }
        )
    
    async def get_resource_content(self, uri: str) -> ResourceContent:
        """Get recent episodes content."""
        # For now, return a placeholder - will be implemented in full system
        return ResourceContent(
            text=json.dumps({
                "message": "Episode list resource handler - implementation pending",
                "resource_uri": uri,
                "resource_type": "episode_list"
            }, indent=2),
            mimeType="application/json"
        )