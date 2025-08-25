#!/usr/bin/env python3
"""
Chutes AI Client Library
Provides consistent interface for LLM integration across Graphiti tools
"""

import os
import json
import logging
from typing import Optional, Dict, Any, List
import httpx
from datetime import datetime

logger = logging.getLogger(__name__)

class ChutesClient:
    """Client for interacting with Chutes AI API"""
    
    def __init__(self, api_key: Optional[str] = None):
        """Initialize Chutes client
        
        Args:
            api_key: Chutes AI API key. If not provided, will look for CHUTES_API_KEY env var
        """
        self.api_key = api_key or os.getenv("CHUTES_API_KEY")
        if not self.api_key:
            raise ValueError("Chutes API key is required. Set CHUTES_API_KEY env var or pass api_key parameter.")
        
        self.base_url = "https://api.chutes.ai/v1"
        self.timeout = 30.0
        
    async def complete_chat(
        self, 
        messages: List[Dict[str, str]], 
        model: str = "zai-org/GLM-4.5-FP8",
        max_tokens: int = 1000,
        temperature: float = 0.1,
        system_prompt: Optional[str] = None
    ) -> str:
        """Complete a chat conversation
        
        Args:
            messages: List of message dicts with 'role' and 'content' keys
            model: Model to use for completion
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            system_prompt: Optional system prompt to prepend
            
        Returns:
            Generated response text
        """
        try:
            # Prepare messages with system prompt if provided
            formatted_messages = []
            if system_prompt:
                formatted_messages.append({"role": "system", "content": system_prompt})
            formatted_messages.extend(messages)
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": model,
                        "messages": formatted_messages,
                        "max_tokens": max_tokens,
                        "temperature": temperature
                    }
                )
                
                if response.status_code == 200:
                    result = response.json()
                    return result["choices"][0]["message"]["content"].strip()
                else:
                    logger.error(f"Chutes API error: {response.status_code} - {response.text}")
                    return ""
                    
        except Exception as e:
            logger.error(f"Error calling Chutes API: {e}")
            return ""
    
    async def enhance_query(self, query: str, context: Optional[str] = None) -> str:
        """Enhance a search query for better knowledge graph retrieval
        
        Args:
            query: Original user query
            context: Optional context about the query
            
        Returns:
            Enhanced query string
        """
        system_prompt = """You are a query enhancement assistant for a knowledge graph search system. 
Your job is to improve search queries to get better results from graph databases.

Guidelines:
1. Identify key entities, relationships, and concepts
2. Add relevant synonyms and related terms
3. Consider temporal aspects if relevant
4. Maintain the user's intent while expanding scope appropriately
5. Return only the enhanced query, no explanation"""

        messages = [{"role": "user", "content": f"Enhance this query: {query}"}]
        if context:
            messages[0]["content"] += f"\nContext: {context}"
            
        return await self.complete_chat(messages, system_prompt=system_prompt, max_tokens=200)
    
    async def summarize_context(self, content: str, max_length: int = 500) -> str:
        """Summarize content while preserving key information
        
        Args:
            content: Content to summarize
            max_length: Maximum length of summary
            
        Returns:
            Summarized content
        """
        system_prompt = f"""You are a content summarization assistant. 
Create concise summaries that preserve key information, entities, and relationships.
Keep summaries under {max_length} characters while maintaining essential details."""

        messages = [{"role": "user", "content": f"Summarize this content:\n\n{content}"}]
        
        return await self.complete_chat(messages, system_prompt=system_prompt, max_tokens=max_length//4)
    
    async def extract_entities(self, text: str) -> List[str]:
        """Extract key entities from text
        
        Args:
            text: Text to analyze
            
        Returns:
            List of extracted entities
        """
        system_prompt = """Extract key entities (people, places, organizations, concepts, tools, technologies) from the given text.
Return as a JSON array of strings. Only include entities that are clearly mentioned."""

        messages = [{"role": "user", "content": f"Extract entities from: {text}"}]
        
        response = await self.complete_chat(messages, system_prompt=system_prompt, max_tokens=300)
        
        try:
            # Try to parse as JSON
            entities = json.loads(response)
            return entities if isinstance(entities, list) else []
        except:
            # Fallback: split by comma if not valid JSON
            return [e.strip() for e in response.split(',') if e.strip()]
    
    async def classify_content(self, content: str, categories: List[str]) -> str:
        """Classify content into one of the provided categories
        
        Args:
            content: Content to classify
            categories: List of possible categories
            
        Returns:
            Best matching category
        """
        system_prompt = f"""Classify the given content into one of these categories: {', '.join(categories)}
Return only the category name that best fits the content."""

        messages = [{"role": "user", "content": f"Classify this content:\n\n{content}"}]
        
        response = await self.complete_chat(messages, system_prompt=system_prompt, max_tokens=50)
        
        # Return the response if it matches a category, otherwise return first category
        response_clean = response.strip().lower()
        for category in categories:
            if category.lower() in response_clean:
                return category
        return categories[0] if categories else "unknown"

# Singleton instance for easy access
_chutes_client = None

def get_chutes_client() -> ChutesClient:
    """Get singleton ChutesClient instance"""
    global _chutes_client
    if _chutes_client is None:
        _chutes_client = ChutesClient()
    return _chutes_client

def is_chutes_available() -> bool:
    """Check if Chutes AI is available (API key is set)"""
    return bool(os.getenv("CHUTES_API_KEY"))