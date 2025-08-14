#!/usr/bin/env python3
"""
Graphiti Conversation Ingestion Hook for Claude Code v2
Reads conversation from transcript file on Stop event
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


def read_last_exchange(transcript_path):
    """Read the last user-assistant exchange from the transcript"""
    if not os.path.exists(transcript_path):
        logger.error(f"Transcript not found: {transcript_path}")
        return None, None
    
    try:
        # Read all lines from the transcript
        exchanges = []
        with open(transcript_path, 'r') as f:
            for line in f:
                if line.strip():
                    exchanges.append(json.loads(line))
        
        if not exchanges:
            return None, None
        
        # Find the last user prompt and assistant response
        last_user_prompt = None
        last_assistant_response = None
        
        # Go through exchanges in reverse to find the most recent pair
        for i in range(len(exchanges) - 1, -1, -1):
            exchange = exchanges[i]
            
            # Look for assistant response
            if exchange.get('type') == 'assistant_response' and not last_assistant_response:
                # Extract text content from the response
                content = exchange.get('content', '')
                if isinstance(content, str):
                    last_assistant_response = content
                elif isinstance(content, list):
                    # Handle structured content
                    text_parts = []
                    for item in content:
                        if isinstance(item, dict) and item.get('type') == 'text':
                            text_parts.append(item.get('text', ''))
                    last_assistant_response = ' '.join(text_parts)
            
            # Look for user prompt
            elif exchange.get('type') == 'user_prompt' and not last_user_prompt:
                last_user_prompt = exchange.get('content', '')
            
            # If we have both, we're done
            if last_user_prompt and last_assistant_response:
                break
        
        return last_user_prompt, last_assistant_response
        
    except Exception as e:
        logger.error(f"Error reading transcript: {e}")
        return None, None


def should_ingest(prompt, response):
    """Determine if this exchange should be ingested"""
    if not prompt and not response:
        return False
    
    # Skip certain types of messages
    skip_patterns = [
        '/help',
        '/mcp',
        '/hooks',
        '/settings',
        'Error:',
        'Warning:',
        'ok check the logs',  # Skip simple commands
        'No ',  # Skip negative responses
    ]
    
    # Check prompt
    if prompt:
        prompt_lower = prompt.lower()
        if any(pattern.lower() in prompt_lower for pattern in skip_patterns):
            logger.debug(f"Skipping prompt with pattern: {prompt[:50]}")
            return False
        
        # Skip very short prompts
        if len(prompt.strip()) < 10:
            logger.debug(f"Skipping short prompt: {prompt}")
            return False
    
    return True


def ingest_message(prompt, response):
    """Send conversation messages to Graphiti for ingestion"""
    
    messages = []
    timestamp = datetime.utcnow().isoformat() + "Z"
    
    # Create a combined message with both prompt and response for better context
    if prompt and response:
        # Combine into a single episodic memory
        combined_content = f"User asked: {prompt}\n\nAssistant responded: {response[:1000]}"
        messages.append({
            "content": combined_content,
            "name": "Conversation",
            "role_type": "system",
            "role": "system",
            "timestamp": timestamp,
            "source_description": "Claude Code conversation"
        })
    elif prompt:
        messages.append({
            "content": prompt,
            "name": "User",
            "role_type": "user",
            "role": "user",
            "timestamp": timestamp,
            "source_description": "Claude Code user prompt"
        })
    elif response:
        messages.append({
            "content": response[:1000],
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
        
        # Only process Stop events
        if hook_event != "Stop":
            sys.exit(0)
        
        # Get transcript path
        transcript_path = input_data.get("transcript_path", "")
        if not transcript_path:
            logger.warning("No transcript path provided")
            sys.exit(0)
        
        # Read the last exchange from the transcript
        prompt, response = read_last_exchange(transcript_path)
        
        # Check if we should ingest this exchange
        if not should_ingest(prompt, response):
            logger.debug(f"Skipping exchange: prompt={prompt[:30] if prompt else 'None'}...")
            sys.exit(0)
        
        # Ingest the conversation
        success = ingest_message(prompt, response)
        
        if success:
            logger.info(f"Ingested conversation: {prompt[:50] if prompt else 'No prompt'}...")
        else:
            logger.warning(f"Failed to ingest conversation")
        
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