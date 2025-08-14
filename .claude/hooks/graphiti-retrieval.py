#!/usr/bin/env python3
"""
Graphiti Knowledge Retrieval Hook for Claude Code

This hook intercepts user prompts and tool usage to automatically retrieve
relevant context from the Graphiti knowledge graph when needed.
"""

import json
import sys
import os
import re
import asyncio
from typing import Dict, List, Any, Optional
from datetime import datetime
import aiohttp

# Configuration
GRAPHITI_API_URL = os.getenv("GRAPHITI_API_URL", "http://localhost:8003")
GRAPHITI_SEARCH_ENDPOINT = f"{GRAPHITI_API_URL}/search"
GRAPHITI_GRAPH_ENDPOINT = f"{GRAPHITI_API_URL}/graph"
MAX_RESULTS = 10
SIMILARITY_THRESHOLD = 0.7

# Patterns that trigger Graphiti search
SEARCH_TRIGGERS = [
    r"(?i)\b(what|how|when|where|who|why)\b.*\b(did|does|is|was|were|are)\b",
    r"(?i)\b(explain|describe|tell me about|show me)\b",
    r"(?i)\b(search|find|look for|retrieve|get)\b.*\b(from|in)\b.*\b(graph|knowledge|memory|context)\b",
    r"(?i)\b(remember|recall|previous|earlier|before)\b",
    r"(?i)\b(context|background|history|related to)\b",
]

# Keywords that indicate knowledge graph queries
KNOWLEDGE_KEYWORDS = [
    "knowledge", "graph", "memory", "context", "history",
    "previous", "earlier", "remember", "recall", "related",
    "connection", "relationship", "entity", "episode"
]


class GraphitiRetriever:
    """Handles retrieval of information from Graphiti knowledge graph"""
    
    def __init__(self):
        self.session = None
        self.cache = {}
        self.cache_ttl = 300  # 5 minutes
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    def should_search(self, text: str) -> bool:
        """Determine if the text warrants a Graphiti search"""
        # Check for explicit triggers
        for pattern in SEARCH_TRIGGERS:
            if re.search(pattern, text):
                return True
        
        # Check for knowledge keywords
        text_lower = text.lower()
        keyword_count = sum(1 for keyword in KNOWLEDGE_KEYWORDS if keyword in text_lower)
        if keyword_count >= 2:
            return True
            
        return False
    
    def extract_search_query(self, text: str) -> str:
        """Extract the most relevant search query from text"""
        # Remove common question words and clean up
        query = re.sub(r"(?i)^(what|how|when|where|who|why|explain|describe|tell me about|show me)\s+", "", text)
        query = re.sub(r"(?i)\b(is|are|was|were|did|does|do)\b", "", query)
        query = re.sub(r"[?!.]$", "", query)
        
        # Extract entities and important terms
        # This is a simple implementation - could be enhanced with NLP
        important_words = []
        for word in query.split():
            if len(word) > 3 and word[0].isupper():  # Likely entities
                important_words.append(word)
            elif word.lower() not in ["the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for"]:
                important_words.append(word)
        
        return " ".join(important_words[:5])  # Limit to 5 most important terms
    
    async def search_graphiti(self, query: str, limit: int = MAX_RESULTS) -> Dict[str, Any]:
        """Search Graphiti for relevant information"""
        # Check cache
        cache_key = f"search:{query}:{limit}"
        if cache_key in self.cache:
            cached_time, cached_result = self.cache[cache_key]
            if (datetime.now() - cached_time).seconds < self.cache_ttl:
                return cached_result
        
        try:
            # Perform search
            async with self.session.post(
                GRAPHITI_SEARCH_ENDPOINT,
                json={
                    "query": query,
                    "limit": limit,
                    "similarity_threshold": SIMILARITY_THRESHOLD,
                    "include_edges": True,
                    "include_metadata": True
                },
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    # Cache result
                    self.cache[cache_key] = (datetime.now(), result)
                    return result
                else:
                    return {"error": f"API returned status {response.status}"}
                    
        except asyncio.TimeoutError:
            return {"error": "Search timeout"}
        except Exception as e:
            return {"error": str(e)}
    
    async def get_entity_context(self, entity_id: str) -> Dict[str, Any]:
        """Get detailed context for a specific entity"""
        cache_key = f"entity:{entity_id}"
        if cache_key in self.cache:
            cached_time, cached_result = self.cache[cache_key]
            if (datetime.now() - cached_time).seconds < self.cache_ttl:
                return cached_result
        
        try:
            async with self.session.get(
                f"{GRAPHITI_GRAPH_ENDPOINT}/entity/{entity_id}",
                timeout=aiohttp.ClientTimeout(total=5)
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    self.cache[cache_key] = (datetime.now(), result)
                    return result
                else:
                    return {"error": f"API returned status {response.status}"}
                    
        except Exception as e:
            return {"error": str(e)}
    
    def format_results(self, results: Dict[str, Any]) -> str:
        """Format search results for Claude"""
        if "error" in results:
            return f"<!-- Graphiti search failed: {results['error']} -->"
        
        if not results.get("results"):
            return "<!-- No relevant information found in Graphiti -->"
        
        formatted = ["<!-- Retrieved from Graphiti Knowledge Graph -->"]
        formatted.append("<graphiti-context>")
        
        # Format entities
        if "entities" in results:
            formatted.append("\n## Relevant Entities:")
            for entity in results["entities"][:5]:
                formatted.append(f"\n### {entity.get('name', 'Unknown')}")
                formatted.append(f"- Type: {entity.get('entity_type', 'Unknown')}")
                formatted.append(f"- Created: {entity.get('created_at', 'Unknown')}")
                if entity.get('content'):
                    formatted.append(f"- Content: {entity['content'][:200]}...")
                if entity.get('properties'):
                    formatted.append(f"- Properties: {json.dumps(entity['properties'], indent=2)}")
        
        # Format relationships
        if "edges" in results:
            formatted.append("\n## Relationships:")
            for edge in results["edges"][:5]:
                formatted.append(f"- {edge.get('source_name', '?')} --[{edge.get('relationship_type', '?')}]--> {edge.get('target_name', '?')}")
                if edge.get('properties'):
                    formatted.append(f"  Properties: {json.dumps(edge['properties'], indent=2)}")
        
        # Format episodes/context
        if "episodes" in results:
            formatted.append("\n## Related Episodes:")
            for episode in results["episodes"][:3]:
                formatted.append(f"\n- {episode.get('name', 'Unknown Episode')}")
                formatted.append(f"  Created: {episode.get('created_at', 'Unknown')}")
                if episode.get('content'):
                    formatted.append(f"  Content: {episode['content'][:300]}...")
        
        formatted.append("\n</graphiti-context>")
        formatted.append("<!-- End of Graphiti context -->")
        
        return "\n".join(formatted)


async def handle_user_prompt(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """Handle UserPromptSubmit hook"""
    prompt = input_data.get("prompt", "")
    
    async with GraphitiRetriever() as retriever:
        # Check if we should search
        if not retriever.should_search(prompt):
            return {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": ""}}
        
        # Extract search query
        query = retriever.extract_search_query(prompt)
        if not query:
            return {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": ""}}
        
        # Search Graphiti
        results = await retriever.search_graphiti(query)
        
        # Format results as context
        context = retriever.format_results(results)
        
        # Add metadata about the search
        metadata = f"\n<!-- Graphiti search performed for: '{query}' -->"
        
        return {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": context + metadata
            }
        }


async def handle_pre_tool_use(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """Handle PreToolUse hook for tools that might benefit from context"""
    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})
    
    # Tools that might benefit from Graphiti context
    context_tools = ["Task", "Write", "Edit", "MultiEdit"]
    
    if tool_name not in context_tools:
        return {}
    
    # For Task tool, check if it's asking about knowledge
    if tool_name == "Task":
        description = tool_input.get("description", "")
        prompt = tool_input.get("prompt", "")
        combined = f"{description} {prompt}"
        
        async with GraphitiRetriever() as retriever:
            if retriever.should_search(combined):
                query = retriever.extract_search_query(combined)
                results = await retriever.search_graphiti(query)
                context = retriever.format_results(results)
                
                # Inject context into the task prompt
                tool_input["prompt"] = f"{context}\n\n{prompt}"
                
                return {
                    "decision": "approve",
                    "reason": "Added Graphiti context to task",
                    "suppressOutput": True
                }
    
    return {}


async def handle_session_start(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """Handle SessionStart hook to load recent context"""
    source = input_data.get("source", "")
    
    # Only load context for resume sessions
    if source != "resume":
        return {}
    
    async with GraphitiRetriever() as retriever:
        # Get recent episodes/entities
        results = await retriever.search_graphiti("recent updates", limit=5)
        
        if "error" not in results and results.get("results"):
            context = retriever.format_results(results)
            return {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": f"<!-- Recent Graphiti context loaded -->\n{context}"
                }
            }
    
    return {}


async def main():
    """Main entry point for the hook"""
    try:
        # Read input
        input_data = json.load(sys.stdin)
        hook_event = input_data.get("hook_event_name", "")
        
        # Route to appropriate handler
        if hook_event == "UserPromptSubmit":
            output = await handle_user_prompt(input_data)
        elif hook_event == "PreToolUse":
            output = await handle_pre_tool_use(input_data)
        elif hook_event == "SessionStart":
            output = await handle_session_start(input_data)
        else:
            output = {}
        
        # Output result
        if output:
            print(json.dumps(output))
            sys.exit(0)
        else:
            sys.exit(0)
            
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON input: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())