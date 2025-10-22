#!/usr/bin/env python3
"""
Graphiti Tool Ingestion Hook for Claude Code
Captures intermediate tool usage and sends to Graphiti knowledge graph
"""

import json
import sys
import os
import requests
from datetime import datetime
import hashlib

# Configuration
GRAPHITI_API_URL = os.getenv("GRAPHITI_API_URL", "http://localhost:8003")
GROUP_ID = os.getenv("GRAPHITI_GROUP_ID", "emmanuel_claude_tools")
USER_NAME = os.getenv("GRAPHITI_USER_NAME", "Emmanuel Umukoro")
ASSISTANT_NAME = "Claude"
ENABLE_TOOL_INGESTION = os.getenv("ENABLE_TOOL_INGESTION", "true").lower() == "true"

# Tool categories for better context
TOOL_CATEGORIES = {
    "Bash": "system_command",
    "Read": "file_operation",
    "Write": "file_operation", 
    "Edit": "file_operation",
    "MultiEdit": "file_operation",
    "Grep": "search_operation",
    "Glob": "search_operation",
    "LS": "file_operation",
    "WebFetch": "web_operation",
    "WebSearch": "web_operation",
    "TodoWrite": "task_management",
    "ExitPlanMode": "planning",
    "NotebookEdit": "file_operation",
    "Task": "agent_operation"
}

def should_ingest_tool(tool_name):
    """Determine if this tool usage should be ingested"""
    if not ENABLE_TOOL_INGESTION:
        return False
    
    # Skip very frequent/noisy tools unless important
    skip_tools = ["BashOutput", "KillBash"]  # These are follow-ups
    return tool_name not in skip_tools

def format_tool_content(tool_name, tool_input, tool_response=None, event_type="PreToolUse"):
    """Format tool usage as meaningful content for the knowledge graph"""
    
    category = TOOL_CATEGORIES.get(tool_name, "tool_operation")
    
    if event_type == "PreToolUse":
        # Format based on tool type
        if tool_name == "Bash":
            command = tool_input.get("command", "")
            description = tool_input.get("description", "")
            return f"{ASSISTANT_NAME} executed command: {command[:200]} - {description}"
        
        elif tool_name in ["Read", "Write", "Edit", "MultiEdit"]:
            file_path = tool_input.get("file_path", "")
            file_name = os.path.basename(file_path)
            action = tool_name.lower()
            return f"{ASSISTANT_NAME} {action} file {file_name} at {file_path}"
        
        elif tool_name in ["Grep", "Glob"]:
            pattern = tool_input.get("pattern", tool_input.get("query", ""))
            path = tool_input.get("path", "current directory")
            return f"{ASSISTANT_NAME} searched for '{pattern[:100]}' in {path}"
        
        elif tool_name == "TodoWrite":
            todos = tool_input.get("todos", [])
            active = [t for t in todos if t.get("status") == "in_progress"]
            completed = [t for t in todos if t.get("status") == "completed"]
            return f"{ASSISTANT_NAME} updated todo list: {len(active)} active, {len(completed)} completed tasks"
        
        elif tool_name == "WebFetch":
            url = tool_input.get("url", "")
            return f"{ASSISTANT_NAME} fetched web content from {url}"
        
        else:
            # Generic format
            return f"{ASSISTANT_NAME} used {tool_name} tool for {category}"
    
    elif event_type == "PostToolUse" and tool_response:
        # Add result context for important tools
        success = tool_response.get("success", True)
        status = "successfully" if success else "with errors"
        
        if tool_name == "Bash" and not success:
            error = tool_response.get("error", "")[:100]
            return f"{ASSISTANT_NAME} command failed: {error}"
        
        return None  # Don't duplicate unless there's important info
    
    return None

def ingest_tool_usage(tool_name, tool_input, tool_response=None, event_type="PreToolUse"):
    """Send tool usage to Graphiti for ingestion"""
    
    if not should_ingest_tool(tool_name):
        return
    
    content = format_tool_content(tool_name, tool_input, tool_response, event_type)
    if not content:
        return
    
    try:
        # Create message for Graphiti
        message = {
            "content": content,
            "name": f"{ASSISTANT_NAME} Tool Usage",
            "role_type": "assistant",
            "role": "assistant",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "source_description": f"Tool operation by {ASSISTANT_NAME} for {USER_NAME}"
        }
        
        payload = {
            "group_id": GROUP_ID,
            "messages": [message]
        }
        
        # Send to Graphiti
        response = requests.post(
            f"{GRAPHITI_API_URL}/messages",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=2  # Short timeout to not block
        )
        
        if response.status_code not in [200, 202]:
            # Log error but don't fail
            with open('/tmp/tool-ingestion-errors.log', 'a') as f:
                f.write(f"{datetime.utcnow().isoformat()} - Failed to ingest {tool_name}: {response.status_code}\n")
                
    except Exception as e:
        # Silent failure - don't disrupt tool execution
        with open('/tmp/tool-ingestion-errors.log', 'a') as f:
            f.write(f"{datetime.utcnow().isoformat()} - Error: {str(e)}\n")

def main():
    try:
        # Read input from stdin
        input_data = json.load(sys.stdin)
        
        hook_event = input_data.get("hook_event_name", "")
        tool_name = input_data.get("tool_name", "")
        
        if hook_event == "PreToolUse":
            tool_input = input_data.get("tool_input", {})
            ingest_tool_usage(tool_name, tool_input, event_type="PreToolUse")
            
        elif hook_event == "PostToolUse":
            tool_input = input_data.get("tool_input", {})
            tool_response = input_data.get("tool_response", {})
            
            # Only ingest post if there's important info (like errors)
            if not tool_response.get("success", True):
                ingest_tool_usage(tool_name, tool_input, tool_response, event_type="PostToolUse")
        
        # Always exit successfully
        sys.exit(0)
        
    except Exception:
        # Silent failure
        sys.exit(0)

if __name__ == "__main__":
    main()