"""
Base classes for MCP resource handlers.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Pattern
import re
import httpx
from datetime import datetime, timezone
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ResourceContent(BaseModel):
    """Base model for resource content."""
    text: Optional[str] = None
    blob: Optional[bytes] = None
    mimeType: str = 'application/json'


class ResourceInfo(BaseModel):
    """Resource information model."""
    uri: str
    name: str
    title: str
    description: str
    mimeType: str = 'application/json'
    annotations: Dict[str, Any] = {}


class BaseResourceHandler(ABC):
    """Abstract base class for resource handlers."""
    
    def __init__(self, http_client: httpx.AsyncClient, config):
        self.http_client = http_client
        self.config = config
        self.logger = logger.getChild(self.__class__.__name__)
    
    @property
    @abstractmethod
    def uri_pattern(self) -> str:
        """Return the URI pattern this handler manages."""
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Return the handler name."""
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """Return the handler description."""
        pass
    
    def matches_uri(self, uri: str) -> bool:
        """Check if this handler can process the given URI."""
        pattern = re.compile(self.uri_pattern.replace('{', '(?P<').replace('}', '>[^/]+)'))
        return bool(pattern.match(uri))
    
    def extract_params(self, uri: str) -> Dict[str, str]:
        """Extract parameters from URI using the pattern."""
        pattern = re.compile(self.uri_pattern.replace('{', '(?P<').replace('}', '>[^/]+)'))
        match = pattern.match(uri)
        return match.groupdict() if match else {}
    
    @abstractmethod
    async def get_resource_info(self, uri: str) -> ResourceInfo:
        """Get resource information without content."""
        pass
    
    @abstractmethod
    async def get_resource_content(self, uri: str) -> ResourceContent:
        """Get resource content."""
        pass


class ResourceManager:
    """Manages MCP resources for Graphiti."""
    
    def __init__(self, http_client: httpx.AsyncClient, config):
        self.http_client = http_client
        self.config = config
        self.handlers: List[BaseResourceHandler] = []
        self.logger = logger.getChild('ResourceManager')
    
    def register_handler(self, handler: BaseResourceHandler):
        """Register a resource handler."""
        self.handlers.append(handler)
        self.logger.info(f"Registered resource handler: {handler.name} ({handler.uri_pattern})")
    
    def find_handler(self, uri: str) -> Optional[BaseResourceHandler]:
        """Find handler for the given URI."""
        for handler in self.handlers:
            if handler.matches_uri(uri):
                return handler
        return None
    
    async def list_resources(self) -> List[ResourceInfo]:
        """List all available static resources."""
        resources = []
        
        # Static resources - these are examples/templates
        static_resources = [
            ResourceInfo(
                uri="graphiti://status",
                name="status", 
                title="Server Status",
                description="Current status of the Graphiti MCP server",
                mimeType="application/json"
            )
        ]
        
        resources.extend(static_resources)
        
        # Add handler information as template resources
        for handler in self.handlers:
            try:
                info = ResourceInfo(
                    uri=handler.uri_pattern,
                    name=handler.name,
                    title=f"{handler.name.title()} Resource",
                    description=handler.description,
                    mimeType="application/json",
                    annotations={"template": True}
                )
                resources.append(info)
            except Exception as e:
                self.logger.warning(f"Failed to get info for handler {handler.name}: {e}")
        
        return resources
    
    async def get_resource_info(self, uri: str) -> Optional[ResourceInfo]:
        """Get resource information."""
        handler = self.find_handler(uri)
        if not handler:
            return None
        
        try:
            return await handler.get_resource_info(uri)
        except Exception as e:
            self.logger.error(f"Error getting resource info for {uri}: {e}")
            return None
    
    async def get_resource_content(self, uri: str) -> Optional[ResourceContent]:
        """Get resource content."""
        # Handle static resources
        if uri == "graphiti://status":
            return ResourceContent(
                text='{"status": "ok", "message": "Graphiti MCP server is running"}',
                mimeType="application/json"
            )
        
        handler = self.find_handler(uri)
        if not handler:
            return None
        
        try:
            return await handler.get_resource_content(uri)
        except Exception as e:
            self.logger.error(f"Error getting resource content for {uri}: {e}")
            return None