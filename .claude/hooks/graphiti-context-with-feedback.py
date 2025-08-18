#!/usr/bin/env python3
"""
Graphiti Context Hook with Relevance Feedback for Claude Code
Retrieves context from Graphiti and sends relevance feedback to centrality service
"""

import json
import sys
import os
import urllib.request
import urllib.parse
import urllib.error
import hashlib
from typing import Dict, Any, List
from datetime import datetime

# Configuration
GRAPHITI_API_URL = os.getenv("GRAPHITI_API_URL", "http://192.168.50.90:8003")
CENTRALITY_API_URL = os.getenv("CENTRALITY_API_URL", "http://localhost:3003")
ENABLE_FEEDBACK = os.getenv("ENABLE_GRAPHITI_FEEDBACK", "true").lower() == "true"

# Store context for later feedback evaluation
CONTEXT_CACHE_FILE = "/tmp/graphiti_context_cache.json"

def search_graphiti(query: str, limit: int = 10, group_ids: list = None) -> Dict[str, Any]:
    """Simple HTTP request to Graphiti search API matching exact API schema"""
    try:
        request_data = {
            "query": query,
            "max_facts": limit
        }
        
        if group_ids:
            request_data["group_ids"] = group_ids
        
        data = json.dumps(request_data).encode('utf-8')
        
        req = urllib.request.Request(
            f"{GRAPHITI_API_URL}/search",
            data=data,
            headers={'Content-Type': 'application/json'}
        )
        
        with urllib.request.urlopen(req, timeout=5) as response:
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
            f"{GRAPHITI_API_URL}/nodes/search",
            data=data,
            headers={'Content-Type': 'application/json'}
        )
        
        with urllib.request.urlopen(req, timeout=5) as response:
            return json.loads(response.read().decode('utf-8'))
    except Exception as e:
        return {"error": str(e)}

def save_context_for_feedback(query: str, facts: List[Dict], entities: List[str]):
    """Save context data for later feedback evaluation"""
    if not ENABLE_FEEDBACK:
        return
    
    try:
        # Generate query ID from query hash
        query_id = hashlib.md5(f"{query}_{datetime.utcnow().isoformat()}".encode()).hexdigest()[:16]
        
        # Create memory mapping from facts
        memory_map = {}
        for fact in facts:
            # Extract memory ID from fact (could be uuid, name, or fact text hash)
            if 'uuid' in fact:
                memory_id = fact['uuid']
            elif 'name' in fact:
                memory_id = hashlib.md5(fact['name'].encode()).hexdigest()[:16]
            else:
                memory_id = hashlib.md5(str(fact).encode()).hexdigest()[:16]
            
            memory_map[memory_id] = {
                'content': fact.get('fact', str(fact)),
                'type': fact.get('type', 'unknown')
            }
        
        # Store context data
        context_data = {
            'query_id': query_id,
            'query_text': query,
            'timestamp': datetime.utcnow().isoformat(),
            'memories': memory_map,
            'entities': entities
        }
        
        # Append to cache file (keep last 10 contexts)
        cache = []
        if os.path.exists(CONTEXT_CACHE_FILE):
            try:
                with open(CONTEXT_CACHE_FILE, 'r') as f:
                    cache = json.load(f)
            except:
                cache = []
        
        cache.append(context_data)
        cache = cache[-10:]  # Keep only last 10
        
        with open(CONTEXT_CACHE_FILE, 'w') as f:
            json.dump(cache, f)
            
    except Exception:
        pass  # Silently fail - feedback is non-critical

def send_relevance_feedback(query_id: str, memory_scores: Dict[str, float], response_text: str = None):
    """Send relevance feedback to centrality service"""
    try:
        payload = {
            "query_id": query_id,
            "query_text": "Claude evaluation",
            "memory_scores": memory_scores,
            "response_text": response_text,
            "source": "claude"
        }
        
        data = json.dumps(payload).encode('utf-8')
        
        req = urllib.request.Request(
            f"{CENTRALITY_API_URL}/feedback/relevance",
            data=data,
            headers={'Content-Type': 'application/json'}
        )
        
        with urllib.request.urlopen(req, timeout=2) as response:
            return json.loads(response.read().decode('utf-8'))
    except Exception:
        return None  # Feedback is best-effort

def format_context(search_results: Dict[str, Any], node_results: Dict[str, Any]) -> str:
    """Format search results as context string with metadata for feedback"""
    sections = []
    
    # Process search results (facts/relationships)
    if search_results and not search_results.get("error"):
        facts = search_results.get("facts", [])
        if facts:
            sections.append("Knowledge from Graphiti:")
            for fact in facts[:10]:
                if isinstance(fact, dict) and 'fact' in fact:
                    sections.append(f"• {fact['fact']}")
                else:
                    sections.append(f"• {fact}")
    
    # Process node results (entities)
    entities = []
    if node_results and not node_results.get("error"):
        nodes = node_results.get("nodes", [])
        if nodes:
            sections.append("\nRelevant entities:")
            for node in nodes[:5]:
                if isinstance(node, dict):
                    name = node.get('name', node.get('uuid', 'Unknown'))
                    entities.append(name)
                    sections.append(f"• {name}")
    
    # Save for feedback if enabled
    if ENABLE_FEEDBACK and search_results:
        facts = search_results.get("facts", [])
        save_context_for_feedback(
            query=search_results.get("query", ""),
            facts=facts,
            entities=entities
        )
    
    return "\n".join(sections) if sections else ""

def main():
    try:
        # Read input from stdin
        input_data = json.load(sys.stdin)
        
        # Get user query
        prompt = input_data.get("prompt", "").strip()
        if not prompt:
            print("", end="")
            sys.exit(0)
        
        # Search Graphiti
        search_results = search_graphiti(prompt, limit=10)
        node_results = search_nodes(prompt, limit=5)
        
        # Format context
        context = format_context(search_results, node_results)
        
        if context:
            # Output formatted context
            print(f"<!-- Graphiti Context -->\n{context}\n<!-- End Graphiti Context -->")
            
            # Schedule feedback collection for Stop hook
            if ENABLE_FEEDBACK:
                feedback_flag = {
                    'enabled': True,
                    'query_id': hashlib.md5(f"{prompt}_{datetime.utcnow().isoformat()}".encode()).hexdigest()[:16]
                }
                with open('/tmp/graphiti_feedback_pending.json', 'w') as f:
                    json.dump(feedback_flag, f)
        else:
            print("", end="")
        
        sys.exit(0)
        
    except Exception as e:
        # Silent failure - don't disrupt user experience
        print("", end="")
        sys.exit(0)

if __name__ == "__main__":
    main()