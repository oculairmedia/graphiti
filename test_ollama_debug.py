#!/usr/bin/env python3
"""
Debug script to see what's happening with Ollama integration.
"""

import asyncio
import os
from datetime import datetime

# Show environment
print("🔍 Environment Check:")
print(f"   USE_OLLAMA: {os.getenv('USE_OLLAMA')}")
print(f"   OLLAMA_BASE_URL: {os.getenv('OLLAMA_BASE_URL')}")
print(f"   OLLAMA_MODEL: {os.getenv('OLLAMA_MODEL')}")
print(f"   OPENAI_API_KEY: {'Set' if os.getenv('OPENAI_API_KEY') else 'Not set'}")

# Import and show what happens
print("\n📦 Importing Graphiti...")
try:
    from use_ollama import Graphiti
    print("   ✅ Import successful")
except Exception as e:
    print(f"   ❌ Import failed: {e}")
    exit(1)

async def test_llm_only():
    """Test just the LLM part without embeddings."""
    print("\n🦙 Testing LLM initialization...")
    
    # Initialize without connecting to DB
    try:
        graphiti = Graphiti(uri="bolt://localhost:6389", user="", password="")
        print("   ✅ Graphiti initialized")
        
        # Check LLM client
        if hasattr(graphiti, 'llm_client'):
            print(f"   LLM Client: {type(graphiti.llm_client).__name__}")
            if hasattr(graphiti.llm_client, 'config'):
                print(f"   Model: {graphiti.llm_client.config.model}")
        
        # Check embedder
        if hasattr(graphiti, 'embedder'):
            print(f"   Embedder: {type(graphiti.embedder).__name__}")
            
    except Exception as e:
        print(f"   ❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_llm_only())