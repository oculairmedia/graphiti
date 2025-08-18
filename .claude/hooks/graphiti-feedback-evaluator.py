#!/usr/bin/env python3
"""
Graphiti Feedback Evaluator Hook for Claude Code
Runs on Stop event to evaluate relevance of provided context and send feedback
"""

import json
import sys
import os
import re
import urllib.request
import hashlib
from typing import Dict, Any, List
from datetime import datetime

# Configuration
GRAPHITI_API_URL = os.getenv("GRAPHITI_API_URL", "http://192.168.50.90:8003")
CONTEXT_CACHE_FILE = "/tmp/graphiti_context_cache.json"
FEEDBACK_PENDING_FILE = "/tmp/graphiti_feedback_pending.json"

def load_last_context() -> Dict[str, Any]:
    """Load the most recent context from cache"""
    try:
        if os.path.exists(CONTEXT_CACHE_FILE):
            with open(CONTEXT_CACHE_FILE, 'r') as f:
                cache = json.load(f)
                if cache:
                    return cache[-1]  # Return most recent
    except:
        pass
    return None

def extract_response_from_transcript(transcript_path: str) -> str:
    """Extract Claude's last response from transcript"""
    try:
        if not os.path.exists(transcript_path):
            return None
            
        with open(transcript_path, 'r') as f:
            exchanges = [json.loads(line) for line in f if line.strip()]
        
        # Find last assistant response
        for exchange in reversed(exchanges):
            if exchange.get('type') == 'assistant':
                content = exchange.get('content', '')
                if isinstance(content, str):
                    return content
                elif isinstance(content, list):
                    texts = [item.get('text', '') for item in content 
                           if isinstance(item, dict) and item.get('type') == 'text']
                    return ' '.join(texts)
    except:
        pass
    return None

def evaluate_memory_relevance(memory: Dict, query: str, response: str) -> float:
    """
    Evaluate how relevant a memory was to the conversation
    Returns a score between 0.0 and 1.0
    """
    score = 0.3  # Base score for being retrieved
    content = memory.get('content', '').lower()
    
    if not response:
        return score
    
    response_lower = response.lower()
    
    # Check if memory content appears in response (high relevance)
    if content in response_lower:
        score += 0.4
    
    # Check for partial matches (medium relevance)
    words = content.split()
    significant_words = [w for w in words if len(w) > 4]  # Skip short words
    if significant_words:
        matches = sum(1 for w in significant_words if w in response_lower)
        score += (matches / len(significant_words)) * 0.2
    
    # Check if entities from memory appear in response
    entities = re.findall(r'`([^`]+)`', content)
    if entities:
        entity_matches = sum(1 for e in entities if e.lower() in response_lower)
        score += (entity_matches / len(entities)) * 0.1
    
    return min(score, 1.0)

def send_relevance_feedback(context: Dict, response: str):
    """Evaluate relevance and send feedback to centrality service"""
    try:
        query_id = context.get('query_id')
        memories = context.get('memories', {})
        query_text = context.get('query_text', '')
        
        if not query_id or not memories:
            return
        
        # Evaluate each memory's relevance
        memory_scores = {}
        for memory_id, memory_data in memories.items():
            score = evaluate_memory_relevance(memory_data, query_text, response)
            memory_scores[memory_id] = score
        
        # Send feedback to Graphiti Python API using the wrapped format
        feedback_data = {
            "query_id": query_id,
            "query_text": query_text,
            "memory_scores": memory_scores,
            "response_text": response[:500] if response else None,  # Truncate for size
            "metadata": {"source": "claude_hooks"}
        }
        
        # Wrap in expected format for FastAPI endpoint
        payload = {
            "feedback_request": feedback_data,
            "settings": {}  # Empty settings object
        }
        
        data = json.dumps(payload).encode('utf-8')
        
        req = urllib.request.Request(
            f"{GRAPHITI_API_URL}/feedback/relevance",
            data=data,
            headers={'Content-Type': 'application/json'}
        )
        
        with urllib.request.urlopen(req, timeout=3) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            
            # Log success with more details
            with open('/tmp/graphiti_feedback.log', 'a') as f:
                avg_score = sum(memory_scores.values()) / len(memory_scores) if memory_scores else 0
                f.write(f"{datetime.utcnow().isoformat()} - Sent feedback for {len(memory_scores)} memories (avg score: {avg_score:.3f})\n")
                
    except Exception as e:
        # Log error but don't fail
        with open('/tmp/graphiti_feedback.log', 'a') as f:
            f.write(f"{datetime.utcnow().isoformat()} - Error: {str(e)}\n")

def main():
    try:
        # Read input from stdin
        input_data = json.load(sys.stdin)
        
        # Only process Stop events
        if input_data.get("hook_event_name") != "Stop":
            sys.exit(0)
        
        # Check if feedback is pending
        if not os.path.exists(FEEDBACK_PENDING_FILE):
            sys.exit(0)
        
        # Load pending flag
        try:
            with open(FEEDBACK_PENDING_FILE, 'r') as f:
                pending = json.load(f)
                if not pending.get('enabled'):
                    sys.exit(0)
        except:
            sys.exit(0)
        
        # Clear pending flag
        os.remove(FEEDBACK_PENDING_FILE)
        
        # Get transcript path
        transcript_path = input_data.get("transcript_path")
        if not transcript_path:
            sys.exit(0)
        
        # Load last context
        context = load_last_context()
        if not context:
            sys.exit(0)
        
        # Extract Claude's response
        response = extract_response_from_transcript(transcript_path)
        if not response:
            sys.exit(0)
        
        # Send relevance feedback
        send_relevance_feedback(context, response)
        
        sys.exit(0)
        
    except Exception as e:
        # Silent failure
        with open('/tmp/graphiti_feedback.log', 'a') as f:
            f.write(f"{datetime.utcnow().isoformat()} - Hook error: {str(e)}\n")
        sys.exit(0)

if __name__ == "__main__":
    main()