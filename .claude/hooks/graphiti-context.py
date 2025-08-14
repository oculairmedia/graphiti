#!/usr/bin/env python3
"""
Graphiti Context Hook for Claude Code
Simple and robust hook for retrieving context from Graphiti knowledge graph
"""

import json
import sys
import os
import urllib.request
import urllib.parse
import urllib.error
from typing import Dict, Any

# Configuration
GRAPHITI_API_URL = os.getenv("GRAPHITI_API_URL", "http://192.168.50.90:8003")

def search_graphiti(query: str, limit: int = 5) -> Dict[str, Any]:
    """Simple HTTP request to Graphiti search API"""
    try:
        # Use the /search endpoint for facts
        data = json.dumps({
            "query": query,
            "max_facts": limit
        }).encode('utf-8')
        
        req = urllib.request.Request(
            f"{GRAPHITI_API_URL}/search",
            data=data,
            headers={'Content-Type': 'application/json'}
        )
        
        with urllib.request.urlopen(req, timeout=3) as response:
            return json.loads(response.read().decode('utf-8'))
    except Exception as e:
        return {"error": str(e)}

def search_nodes(query: str, limit: int = 5) -> Dict[str, Any]:
    """Search for nodes in Graphiti"""
    try:
        data = json.dumps({
            "query": query,
            "limit": limit
        }).encode('utf-8')
        
        req = urllib.request.Request(
            f"{GRAPHITI_API_URL}/search/nodes",
            data=data,
            headers={'Content-Type': 'application/json'}
        )
        
        with urllib.request.urlopen(req, timeout=3) as response:
            return json.loads(response.read().decode('utf-8'))
    except Exception as e:
        return {"error": str(e)}

def extract_keywords(text: str) -> str:
    """Extract important keywords from text"""
    # Remove common words
    stopwords = {'what', 'how', 'when', 'where', 'who', 'why', 'is', 'are', 'was', 
                 'were', 'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 
                 'to', 'for', 'of', 'with', 'by', 'from', 'about', 'into', 'through'}
    
    words = text.lower().split()
    keywords = [w for w in words if w not in stopwords and len(w) > 2]
    return ' '.join(keywords[:5])  # Top 5 keywords

def format_as_context(results: Dict[str, Any], node_results: Dict[str, Any] = None) -> str:
    """Format search results as context"""
    if "error" in results and (not node_results or "error" in node_results):
        return ""
    
    lines = []
    lines.append("\n<!-- Graphiti Context -->")
    
    # Format facts if present
    if "facts" in results and results["facts"]:
        lines.append("Knowledge from Graphiti:")
        for fact in results["facts"][:5]:
            name = fact.get("name", "Unknown")
            fact_text = fact.get("fact", "")
            if fact_text:
                lines.append(f"• {name}: {fact_text}")
    
    # Format nodes if present
    if node_results and "nodes" in node_results and node_results["nodes"]:
        lines.append("\nRelevant entities:")
        for node in node_results["nodes"][:3]:
            name = node.get("name", "Unknown")
            node_type = node.get("entity_type", node.get("type", ""))
            if node_type:
                lines.append(f"• {name} ({node_type})")
            else:
                lines.append(f"• {name}")
    
    # Format episodes if present
    if node_results and "episodes" in node_results and node_results["episodes"]:
        lines.append("\nRelated episodes:")
        for episode in node_results["episodes"][:2]:
            name = episode.get("name", "Unknown")
            content = episode.get("content", "")
            if content:
                content = content[:100] + "..." if len(content) > 100 else content
                lines.append(f"• {name}: {content}")
    
    lines.append("<!-- End Graphiti Context -->\n")
    return "\n".join(lines) if len(lines) > 2 else ""

def main():
    try:
        # Read input from stdin
        input_data = json.load(sys.stdin)
        hook_event = input_data.get("hook_event_name", "")
        
        # Only process UserPromptSubmit events
        if hook_event != "UserPromptSubmit":
            sys.exit(0)
        
        prompt = input_data.get("prompt", "")
        
        # Check if prompt mentions knowledge, graph, or context
        trigger_words = ["knowledge", "graph", "remember", "recall", "previous", 
                        "context", "earlier", "history", "what did", "what do we know"]
        
        prompt_lower = prompt.lower()
        if not any(word in prompt_lower for word in trigger_words):
            sys.exit(0)  # No context needed
        
        # Extract keywords and search
        keywords = extract_keywords(prompt)
        if keywords:
            # Search for facts
            results = search_graphiti(keywords)
            # Also search for nodes
            node_results = search_nodes(keywords)
            
            context = format_as_context(results, node_results)
            
            if context:
                # Output the context for Claude to see
                output = {
                    "hookSpecificOutput": {
                        "hookEventName": "UserPromptSubmit",
                        "additionalContext": context
                    }
                }
                print(json.dumps(output))
        
        sys.exit(0)
        
    except json.JSONDecodeError:
        # Invalid JSON input - exit silently
        sys.exit(1)
    except Exception:
        # Any other error - exit silently
        sys.exit(1)

if __name__ == "__main__":
    main()