#!/usr/bin/env python3
"""
Graphiti Post-Tool Context Hook
Provides relevant context from the knowledge graph AFTER each tool use
This context IS visible to Claude!
"""

import json
import sys
import os
import urllib.request
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
            timeout=2
        )
        
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode('utf-8'))
            facts = result.get("facts", [])
            
            fact_texts = []
            for fact in facts[:limit]:
                if isinstance(fact, dict):
                    fact_texts.append(fact.get('fact', str(fact)))
                else:
                    fact_texts.append(str(fact))
            
            return fact_texts
    except:
        return []

def get_context_after_tool(tool_name: str, tool_input: Dict[str, Any], tool_response: Dict[str, Any]) -> str:
    """Generate context based on what the tool just did"""
    
    context_parts = []
    
    # Tool-specific context queries based on what was done
    if tool_name == "Read":
        file_path = tool_input.get("file_path", "")
        if file_path:
            file_name = os.path.basename(file_path)
            # Search for info about this file
            facts = search_graphiti(f"{file_name} edited modified created", 3)
            if facts:
                context_parts.append(f"\n🔍 Knowledge about {file_name}:")
                context_parts.extend([f"• {fact}" for fact in facts])
    
    elif tool_name in ["Edit", "MultiEdit", "Write"]:
        file_path = tool_input.get("file_path", "")
        if file_path and tool_response.get("success"):
            file_name = os.path.basename(file_path)
            # Record this edit and search for related work
            facts = search_graphiti(f"{file_name} related connected imports", 3)
            if facts:
                context_parts.append(f"\n🔍 Related to {file_name} edit:")
                context_parts.extend([f"• {fact}" for fact in facts])
    
    elif tool_name == "Bash":
        command = tool_input.get("command", "")
        success = tool_response.get("success", True)
        
        if not success:
            # Search for similar errors
            cmd_parts = command.split()
            if cmd_parts:
                main_cmd = cmd_parts[0]
                facts = search_graphiti(f"{main_cmd} error failed", 3)
                if facts:
                    context_parts.append(f"\n🔍 Previous {main_cmd} issues:")
                    context_parts.extend([f"• {fact}" for fact in facts])
        else:
            # Search for related successful commands
            cmd_parts = command.split()
            if cmd_parts:
                main_cmd = cmd_parts[0]
                facts = search_graphiti(f"{main_cmd} executed successful", 2)
                if facts:
                    context_parts.append(f"\n🔍 Related {main_cmd} operations:")
                    context_parts.extend([f"• {fact}" for fact in facts])
    
    elif tool_name in ["Grep", "Glob"]:
        pattern = tool_input.get("pattern", tool_input.get("query", ""))
        if pattern and tool_response.get("success"):
            # Search for what we might have been looking for
            facts = search_graphiti(f"{pattern[:30]}", 3)
            if facts:
                context_parts.append(f"\n🔍 Knowledge about '{pattern[:30]}':")
                context_parts.extend([f"• {fact}" for fact in facts])
    
    elif tool_name == "TodoWrite":
        # Search for task-related context
        facts = search_graphiti("todo task completed pending", 3)
        if facts:
            context_parts.append(f"\n🔍 Task history:")
            context_parts.extend([f"• {fact}" for fact in facts])
    
    # If we have context, return it
    if context_parts:
        return "\n".join(context_parts) + "\n"
    
    return ""

def main():
    try:
        # Read input from stdin
        input_data = json.load(sys.stdin)
        
        # Log that we're running
        with open('/tmp/posttool-activity.log', 'a') as f:
            f.write(f"PostTool hook called: {input_data.get('hook_event_name')} for {input_data.get('tool_name')}\n")
        
        # Only process PostToolUse events
        if input_data.get("hook_event_name") != "PostToolUse":
            sys.exit(0)
        
        tool_name = input_data.get("tool_name", "")
        tool_input = input_data.get("tool_input", {})
        tool_response = input_data.get("tool_response", {})
        
        # Get relevant context after this tool use
        context = get_context_after_tool(tool_name, tool_input, tool_response)
        
        if context:
            # Output context that WILL be shown to Claude!
            print(context)
            # Also log it
            with open('/tmp/posttool-activity.log', 'a') as f:
                f.write(f"Context provided: {context[:100]}...\n")
        
        # Exit code 0 means success
        sys.exit(0)
        
    except Exception as e:
        # Log error but don't disrupt
        with open('/tmp/posttool-errors.log', 'a') as f:
            f.write(f"Error: {str(e)}\n")
        sys.exit(0)

if __name__ == "__main__":
    main()