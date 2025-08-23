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
        
        try:
            # Query the FastAPI server for episode details
            response = await self.http_client.get(f'/episode/{episode_id}')
            
            if response.status_code == 404:
                return ResourceContent(
                    text=json.dumps({
                        "error": "Episode not found",
                        "episode_id": episode_id,
                        "message": f"No episode found with ID: {episode_id}"
                    }, indent=2),
                    mimeType="application/json"
                )
            
            response.raise_for_status()
            episode_data = response.json()
            
            # Format episode data for resource consumption
            formatted_data = {
                "episode_id": episode_id,
                "uuid": episode_data.get("uuid", episode_id),
                "name": episode_data.get("name", ""),
                "content": episode_data.get("content", ""),
                "source": episode_data.get("source", ""),
                "source_description": episode_data.get("source_description", ""),
                "group_id": episode_data.get("group_id", ""),
                "created_at": episode_data.get("created_at", ""),
                "updated_at": episode_data.get("updated_at", ""),
                "metadata": episode_data.get("metadata", {}),
                "related_entities": episode_data.get("related_entities", []),
                "resource_uri": uri,
                "resource_type": "episode"
            }
            
            return ResourceContent(
                text=json.dumps(formatted_data, indent=2),
                mimeType="application/json"
            )
            
        except httpx.HTTPStatusError as e:
            self.logger.error(f"HTTP error getting episode {episode_id}: {e}")
            return ResourceContent(
                text=json.dumps({
                    "error": "Failed to retrieve episode",
                    "episode_id": episode_id,
                    "status_code": e.response.status_code,
                    "message": f"Server error: {e.response.status_code}"
                }, indent=2),
                mimeType="application/json"
            )
        except Exception as e:
            self.logger.error(f"Error getting episode {episode_id}: {e}")
            return ResourceContent(
                text=json.dumps({
                    "error": "Internal error",
                    "episode_id": episode_id,
                    "message": str(e)
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
        try:
            # Use the get_episodes functionality to retrieve recent episodes
            group_id = self.config.group_id if self.config.group_id else 'default'
            
            response = await self.http_client.get(f'/episodes/{group_id}', params={'last_n': 20})
            response.raise_for_status()
            
            result = response.json()
            episodes = result.get('episodes', [])
            
            # Format episodes for resource consumption
            formatted_data = {
                "filter": "recent",
                "group_id": group_id,
                "total_count": len(episodes),
                "episodes": [
                    {
                        "uuid": episode.get("uuid", ""),
                        "name": episode.get("name", ""),
                        "content": episode.get("content", "")[:200] + "..." if len(episode.get("content", "")) > 200 else episode.get("content", ""),
                        "source": episode.get("source", ""),
                        "group_id": episode.get("group_id", ""),
                        "created_at": episode.get("created_at", ""),
                        "episode_uri": f"graphiti://episode/{episode.get('uuid', '')}"
                    }
                    for episode in episodes
                ],
                "resource_uri": uri,
                "resource_type": "episode_list",
                "generated_at": datetime.now(timezone.utc).isoformat()
            }
            
            return ResourceContent(
                text=json.dumps(formatted_data, indent=2),
                mimeType="application/json"
            )
            
        except httpx.HTTPStatusError as e:
            self.logger.error(f"HTTP error getting recent episodes: {e}")
            return ResourceContent(
                text=json.dumps({
                    "error": "Failed to retrieve recent episodes",
                    "status_code": e.response.status_code,
                    "message": f"Server error: {e.response.status_code}"
                }, indent=2),
                mimeType="application/json"
            )
        except Exception as e:
            self.logger.error(f"Error getting recent episodes: {e}")
            return ResourceContent(
                text=json.dumps({
                    "error": "Internal error",
                    "message": str(e)
                }, indent=2),
                mimeType="application/json"
            )