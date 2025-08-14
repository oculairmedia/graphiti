#!/usr/bin/env python3
"""
Graphiti Conversation Ingestion Hook for Claude Code v3
Properly parses Claude Code transcript format
"""

import json
import sys
import os
import requests
from datetime import datetime
import logging
import re

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
GROUP_ID = os.getenv("GRAPHITI_GROUP_ID", "emmanuel_claude_session")
USER_NAME = os.getenv("GRAPHITI_USER_NAME", "Emmanuel Umukoro")
ASSISTANT_NAME = "Claude"


def extract_text_from_content(content):
    """Extract text from Claude's content structure"""
    if isinstance(content, str):
        return content
    elif isinstance(content, list):
        text_parts = []
        for item in content:
            if isinstance(item, dict):
                if item.get('type') == 'text':
                    text_parts.append(item.get('text', ''))
                elif item.get('type') == 'tool_result':
                    # Skip tool results as they're usually not conversational
                    continue
        return ' '.join(text_parts).strip()
    return ""


def read_last_exchange(transcript_path):
    """Read the last meaningful user-assistant exchange from the transcript"""
    if not os.path.exists(transcript_path):
        logger.error(f"Transcript not found: {transcript_path}")
        return None, None
    
    try:
        # Read all lines from the transcript
        exchanges = []
        with open(transcript_path, 'r') as f:
            for line in f:
                if line.strip():
                    try:
                        exchanges.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        
        if not exchanges:
            return None, None
        
        # Find the last user prompt and assistant response
        last_user_prompt = None
        last_assistant_response = None
        
        # Go through exchanges in reverse to find the most recent meaningful pair
        for i in range(len(exchanges) - 1, -1, -1):
            exchange = exchanges[i]
            exchange_type = exchange.get('type', '')
            
            # Handle assistant responses
            if exchange_type == 'assistant' and not last_assistant_response:
                # Check if it has actual content
                if 'content' in exchange:
                    text = extract_text_from_content(exchange['content'])
                    if text and len(text) > 10:  # Skip very short responses
                        last_assistant_response = text
                elif 'message' in exchange and 'content' in exchange['message']:
                    text = extract_text_from_content(exchange['message']['content'])
                    if text and len(text) > 10:
                        last_assistant_response = text
            
            # Handle user prompts - look for actual text prompts, not tool results
            elif exchange_type == 'user' and not last_user_prompt:
                # Try to find the actual user text
                if 'message' in exchange:
                    message = exchange['message']
                    if 'content' in message:
                        # Check if this is a text message, not a tool result
                        content = message['content']
                        if isinstance(content, str):
                            if content and not content.startswith('[Request'):
                                last_user_prompt = content
                        elif isinstance(content, list):
                            # Look for text content, not tool results
                            for item in content:
                                if isinstance(item, dict) and item.get('type') == 'text':
                                    text = item.get('text', '')
                                    if text and not text.startswith('[Request'):
                                        last_user_prompt = text
                                        break
                
                # Also check for direct prompt field
                if not last_user_prompt and 'prompt' in exchange:
                    prompt = exchange['prompt']
                    if prompt and not prompt.startswith('[Request'):
                        last_user_prompt = prompt
            
            # Look for 'prompt' type entries (older format)
            elif exchange_type == 'prompt' and not last_user_prompt:
                content = exchange.get('content', '')
                if content and not content.startswith('[Request'):
                    last_user_prompt = content
            
            # If we have both, we're done
            if last_user_prompt and last_assistant_response:
                break
        
        # If we couldn't find a proper user prompt, look harder
        if not last_user_prompt and last_assistant_response:
            # Search backwards for any text that looks like a user question
            for i in range(len(exchanges) - 1, -1, -1):
                exchange = exchanges[i]
                # Look for system messages that might contain user prompts
                if exchange.get('type') == 'system':
                    content = exchange.get('content', '')
                    if isinstance(content, str) and content:
                        # Extract user prompts from system messages
                        if 'user:' in content.lower():
                            parts = content.split('user:', 1)
                            if len(parts) > 1:
                                last_user_prompt = parts[1].strip()[:200]
                                break
        
        logger.debug(f"Found prompt: {last_user_prompt[:50] if last_user_prompt else 'None'}")
        logger.debug(f"Found response: {last_assistant_response[:50] if last_assistant_response else 'None'}")
        
        return last_user_prompt, last_assistant_response
        
    except Exception as e:
        logger.error(f"Error reading transcript: {e}")
        return None, None


def should_ingest(prompt, response):
    """Determine if this exchange should be ingested"""
    # If there's no content at all, skip
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
        '[Request interrupted',
        '[Request rejected',
        'No response requested',  # Skip explicit no-response messages
    ]
    
    # Check prompt if present
    if prompt:
        prompt_lower = prompt.lower()
        if any(pattern.lower() in prompt_lower for pattern in skip_patterns):
            logger.debug(f"Skipping prompt with pattern: {prompt[:50]}")
            return False
    
    # Check response if present
    if response:
        response_lower = response.lower()
        if any(pattern.lower() in response_lower for pattern in skip_patterns):
            logger.debug(f"Skipping response with pattern: {response[:50]}")
            return False
        
        # Only skip VERY short responses (under 30 chars)
        if len(response.strip()) < 30:
            logger.debug(f"Skipping very short response: {response}")
            return False
    
    # IMPORTANT: Ingest if we have a substantial response, even without a user prompt
    # This captures Claude's work when the user just approves
    if response and len(response) >= 30:
        logger.debug(f"Ingesting Claude's response (no prompt needed): {response[:50]}...")
        return True
    
    # Also ingest if we have a user prompt, even if short
    if prompt and len(prompt.strip()) > 0:
        logger.debug(f"Ingesting user prompt: {prompt[:50]}...")
        return True
    
    return False


def ingest_message(prompt, response):
    """Send conversation messages to Graphiti for ingestion"""
    
    messages = []
    timestamp = datetime.utcnow().isoformat() + "Z"
    
    # Create appropriate message based on what we have
    if prompt and response:
        # Full conversation exchange
        prompt_clean = re.sub(r'<[^>]+>', '', prompt)[:500]  # Remove HTML tags, limit length
        response_clean = re.sub(r'<[^>]+>', '', response)[:1000]
        
        combined_content = f"{USER_NAME} asked: {prompt_clean}\n\n{ASSISTANT_NAME} explained: {response_clean}"
        
        messages.append({
            "content": combined_content,
            "name": f"{USER_NAME} and {ASSISTANT_NAME} Conversation",
            "role_type": "system",
            "role": "system",
            "timestamp": timestamp,
            "source_description": f"Technical discussion between {USER_NAME} and {ASSISTANT_NAME}"
        })
    elif response:
        # Claude's response (even without explicit prompt - user may have just approved)
        response_clean = re.sub(r'<[^>]+>', '', response)[:1500]  # Allow longer responses
        
        # Add context that this was Claude working autonomously
        content = f"{ASSISTANT_NAME} performed technical work: {response_clean}"
        if prompt:
            content = f"{USER_NAME} (approval/continuation)\n\n{ASSISTANT_NAME}: {response_clean}"
        
        messages.append({
            "content": content,
            "name": ASSISTANT_NAME,
            "role_type": "assistant",
            "role": "assistant",
            "timestamp": timestamp,
            "source_description": f"{ASSISTANT_NAME}'s technical work for {USER_NAME}"
        })
    elif prompt:
        # User prompt only (rare case)
        messages.append({
            "content": f"{USER_NAME}: {prompt[:500]}",
            "name": USER_NAME,
            "role_type": "user",
            "role": "user",
            "timestamp": timestamp,
            "source_description": f"{USER_NAME}'s input"
        })
    
    if not messages:
        return False
    
    # Prepare request payload - NO UUID!
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
        
        logger.debug(f"Processing transcript: {transcript_path}")
        
        # Read the last exchange from the transcript
        prompt, response = read_last_exchange(transcript_path)
        
        # Check if we should ingest this exchange
        if not should_ingest(prompt, response):
            logger.debug(f"Skipping exchange: prompt={prompt[:30] if prompt else 'None'}...")
            sys.exit(0)
        
        # Ingest the conversation
        success = ingest_message(prompt, response)
        
        if success:
            logger.info(f"Ingested {USER_NAME}'s conversation: {prompt[:50] if prompt else 'No prompt'}...")
        else:
            logger.warning(f"Failed to ingest {USER_NAME}'s conversation")
        
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