#!/usr/bin/env python3

import asyncio
import os
import sys
from datetime import datetime

# Add the project root to the Python path
sys.path.insert(0, '/opt/stacks/graphiti')

from graphiti_core.llm_client.chutes_client import ChutesClient
from graphiti_core.prompts import Message

async def debug_chutes_summary():
    """Debug Chutes AI summary generation issues."""
    
    print("🔍 Debugging Chutes AI Summary Generation")
    print("=" * 50)
    
    client = ChutesClient(
        api_key=os.getenv("CHUTES_API_KEY", "cpk_8cadd3bbe05b4c7d88bee9140f213a23.bb20b5a1d58c50c9bc051e74b2a39d7c.xyoKOY5cSWESvNGLI41CQzzTiDt0fBAc"),
        model="zai-org/GLM-4.5-FP8"
    )
    
    # Test message that should generate a summary
    messages = [
        Message(
            role="system",
            content="You are an AI assistant that extracts information from text and creates concise summaries."
        ),
        Message(
            role="user", 
            content="Please extract and summarize the following: 'Claude Code is a powerful development environment that integrates with various AI models including Cerebras, Chutes AI, and Ollama for enhanced coding assistance.'"
        )
    ]
    
    try:
        print("🔄 Making request to Chutes AI...")
        
        # Test with no response model (basic summary)
        response = await client.generate_response(messages)
        
        print("📋 Response received:")
        print(f"   Type: {type(response)}")
        if isinstance(response, dict):
            print(f"   Keys: {list(response.keys())}")
            print(f"   Full response: {response}")
            
            if 'summary' in response:
                print(f"✅ Summary found: {response['summary']}")
            else:
                print("❌ No 'summary' key found in response")
                
                # Check for alternative keys
                likely_keys = [k for k in response.keys() 
                              if 'summary' in k.lower() or 'content' in k.lower() or 'text' in k.lower()]
                if likely_keys:
                    print(f"🔍 Possible summary keys: {likely_keys}")
                    for key in likely_keys:
                        print(f"   {key}: {response[key]}")
        else:
            print(f"   Content: {response}")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(debug_chutes_summary())