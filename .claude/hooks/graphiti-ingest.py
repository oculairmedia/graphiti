#!/usr/bin/env python3
"""
Graphiti Conversation Ingestion Hook for Claude Code

This hook automatically ingests conversation messages into Graphiti's knowledge graph.
Triggers on UserPromptComplete events to capture both user prompts and assistant responses.
"""

import json
import sys
import os
import requests
from datetime import datetime
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/tmp/graphiti-ingest-hook.log'),
        logging.StreamHandler(sys.stderr) if os.getenv('DEBUG') else logging.NullHandler()
    ]
)
logger = logging.getLogger(__name__)

# Configuration
GRAPHITI_API_URL = os.getenv("GRAPHITI_API_URL", "http://localhost:8003")
GROUP_ID = os.getenv("GRAPHITI_GROUP_ID", "claude_code_session")


def ingest_message(prompt: str, response: str = None):
    """Send conversation messages to Graphiti for ingestion"""
    
    messages = []
    timestamp = datetime.utcnow().isoformat() + "Z"
    
    # Add user message
    if prompt:
        messages.append({
            "content": prompt,
            "name": "User",
            "role_type": "user",
            "role": "user",
            "timestamp": timestamp,
            "source_description": "Claude Code conversation"
        })
    
    # Add assistant response if available
    if response:
        messages.append({
            "content": response[:2000],  # Truncate very long responses
            "name": "Claude",
            "role_type": "assistant",
            "role": "assistant",
            "timestamp": timestamp,
            "source_description": "Claude Code assistant response"
        })
    
    if not messages:
        return False
    
    # Prepare request payload
    payload = {
        "group_id": GROUP_ID,
        "messages": messages
    }
    
    try:
        # Send to Graphiti API
        response = requests.post(
            f"{GRAPHITI_API_URL}/messages",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=5
        )
        
        if response.status_code in [200, 202]:
            result = response.json()
            logger.info(f"Successfully ingested messages: {result}")
            return True
        else:
            logger.error(f"Failed to ingest: {response.status_code} - {response.text}")
            return False
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Request failed: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return False


def main():
    """Main entry point for the hook"""
    try:
        # Read input from stdin
        input_data = json.load(sys.stdin)
        hook_event = input_data.get("hook_event_name", "")
        
        # Only process Stop events (when Claude finishes responding)
        if hook_event != "Stop":
            sys.exit(0)
        
        # Extract prompt and response from Stop event
        # The Stop event contains the full conversation context
        prompt = input_data.get("user_prompt", "")
        response = input_data.get("assistant_response", "")
        
        # Skip if no content
        if not prompt and not response:
            sys.exit(0)
        
        # Skip certain types of messages
        skip_patterns = [
            "/help",
            "/mcp",
            "/hooks",
            "```",  # Skip code blocks
            "Error:",
            "Warning:"
        ]
        
        if any(pattern in prompt for pattern in skip_patterns):
            logger.debug(f"Skipping prompt with pattern: {prompt[:50]}")
            sys.exit(0)
        
        # Ingest the conversation
        success = ingest_message(prompt, response)
        
        if success:
            logger.info(f"Ingested conversation: {prompt[:50]}...")
        else:
            logger.warning(f"Failed to ingest conversation: {prompt[:50]}...")
        
        # Exit successfully (don't block Claude)
        sys.exit(0)
        
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON input: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Hook error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()