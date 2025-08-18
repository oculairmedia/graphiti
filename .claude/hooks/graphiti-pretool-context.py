#!/usr/bin/env python3
"""
Graphiti Pre-Tool Context Hook
Provides relevant context from the knowledge graph before each tool use
"""

import json
import sys
import os
import urllib.request
import urllib.parse
from typing import Dict, Any, List

# Configuration
GRAPHITI_API_URL = os.getenv("GRAPHITI_API_URL", "http://localhost:8003")
MAX_CONTEXT_FACTS = 5

def search_graphiti(query: str, limit: int = 5) -> List[str]:
    """Search Graphiti and return relevant facts"""
    try:
        payload = {
            "query": query,
            "max_facts": limit
        }
        
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            f"{GRAPHITI_API_URL}/search",
            data=data,
            headers={'Content-Type': 'application/json'},
            timeout=2  # Quick timeout to not slow down tools
        )
        
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode('utf-8'))
            facts = result.get("facts", [])
            
            # Extract just the fact text
            fact_texts = []
            for fact in facts[:limit]:
                if isinstance(fact, dict):
                    fact_texts.append(fact.get('fact', str(fact)))
                else:
                    fact_texts.append(str(fact))
            
            return fact_texts
    except:
        return []  # Fail silently to not disrupt tool execution

def get_context_for_tool(tool_name: str, tool_input: Dict[str, Any]) -> str:
    """Generate context based on the tool being used"""
    
    context_parts = []
    
    # Tool-specific context queries
    if tool_name == "Read":
        file_path = tool_input.get("file_path", "")
        if file_path:
            file_name = os.path.basename(file_path)
            # Search for previous edits to this file
            facts = search_graphiti(f"edited {file_name}", 3)
            if facts:
                context_parts.append(f"Previous work on {file_name}:")
                context_parts.extend([f"• {fact}" for fact in facts])
    
    elif tool_name == "Edit" or tool_name == "MultiEdit":
        file_path = tool_input.get("file_path", "")
        if file_path:
            file_name = os.path.basename(file_path)
            # Search for context about this file
            facts = search_graphiti(f"{file_name} file edited modified", 3)
            if facts:
                context_parts.append(f"Previous edits to {file_name}:")
                context_parts.extend([f"• {fact}" for fact in facts])
    
    elif tool_name == "Bash":
        command = tool_input.get("command", "")
        # Extract key command (first word)
        cmd_parts = command.split()
        if cmd_parts:
            main_cmd = cmd_parts[0]
            # Search for similar commands
            facts = search_graphiti(f"executed command {main_cmd}", 3)
            if facts:
                context_parts.append(f"Previous {main_cmd} commands:")
                context_parts.extend([f"• {fact}" for fact in facts])
    
    elif tool_name == "Grep" or tool_name == "Glob":
        pattern = tool_input.get("pattern", tool_input.get("query", ""))
        if pattern:
            # Search for previous searches with similar patterns
            facts = search_graphiti(f"searched for {pattern[:30]}", 3)
            if facts:
                context_parts.append(f"Previous searches for similar patterns:")
                context_parts.extend([f"• {fact}" for fact in facts])
    
    elif tool_name == "Write":
        file_path = tool_input.get("file_path", "")
        if file_path:
            file_name = os.path.basename(file_path)
            # Search for any previous work on this file
            facts = search_graphiti(f"{file_name} created wrote", 3)
            if facts:
                context_parts.append(f"Previous work with {file_name}:")
                context_parts.extend([f"• {fact}" for fact in facts])
    
    elif tool_name == "WebFetch" or tool_name == "WebSearch":
        url = tool_input.get("url", "")
        query = tool_input.get("query", "")
        search_term = url or query
        if search_term:
            # Search for related web operations
            facts = search_graphiti(f"web fetch {search_term[:30]}", 3)
            if facts:
                context_parts.append(f"Previous web operations:")
                context_parts.extend([f"• {fact}" for fact in facts])
    
    # If we have context, format it nicely
    if context_parts:
        return "\n<!-- Graphiti Tool Context -->\n" + "\n".join(context_parts) + "\n<!-- End Graphiti Tool Context -->\n"
    
    return ""

def main():
    try:
        # Read input from stdin
        input_data = json.load(sys.stdin)
        
        # Only process PreToolUse events
        if input_data.get("hook_event_name") != "PreToolUse":
            sys.exit(0)
        
        tool_name = input_data.get("tool_name", "")
        tool_input = input_data.get("tool_input", {})
        
        # Get relevant context for this tool
        context = get_context_for_tool(tool_name, tool_input)
        
        if context:
            # Output context that will be shown to Claude
            print(context, end="")
        
        sys.exit(0)
        
    except Exception:
        # Silent failure - don't disrupt tool execution
        sys.exit(0)

if __name__ == "__main__":
    main()