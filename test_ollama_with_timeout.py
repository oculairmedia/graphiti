#!/usr/bin/env python3
"""
Test Ollama with timeout to see where it hangs.
"""

import asyncio
import os
from datetime import datetime
from use_ollama import Graphiti
from graphiti_core.nodes import EpisodeType

async def test_with_steps():
    print("🦙 Testing Ollama with Graphiti - Step by Step")
    print("=" * 50)
    
    # Connect to FalkorDB
    print("\n1️⃣ Connecting to FalkorDB...")
    graphiti = Graphiti(uri="bolt://localhost:6389", user="", password="")
    print("   ✅ Connected")
    
    # Prepare test data
    print("\n2️⃣ Preparing test episode...")
    test_content = """
    Alice is a senior software engineer working on the Graphiti project.
    She specializes in graph databases and distributed systems.
    """
    
    print("\n3️⃣ Calling add_episode...")
    print("   This is where it might hang if Ollama has issues with the prompts...")
    
    try:
        # Add timeout to see if it hangs
        await asyncio.wait_for(
            graphiti.add_episode(
                name="Alice's Work Update",
                episode_body=test_content,
                source_description="Team Update - Daily standup",
                reference_time=datetime.now(),
                source=EpisodeType.text,
                group_id="test_group"
            ),
            timeout=30.0  # 30 second timeout
        )
        print("   ✅ Episode added successfully!")
        
    except asyncio.TimeoutError:
        print("   ⏱️ TIMEOUT: add_episode took longer than 30 seconds")
        print("   This suggests Ollama might be struggling with the prompts")
        
    except Exception as e:
        print(f"   ❌ Error: {e}")
        import traceback
        traceback.print_exc()

async def test_llm_directly():
    """Test calling Ollama directly to see if it works."""
    print("\n🔍 Testing Ollama directly...")
    
    from openai import AsyncOpenAI
    
    client = AsyncOpenAI(
        base_url="http://100.81.139.20:11434/v1",
        api_key="ollama"
    )
    
    try:
        print("   Sending test prompt to Ollama...")
        response = await client.chat.completions.create(
            model="mistral:latest",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Say 'Hello, I am working!' in 5 words or less."}
            ],
            max_tokens=50,
            temperature=0.7
        )
        
        print(f"   ✅ Ollama response: {response.choices[0].message.content}")
        
    except Exception as e:
        print(f"   ❌ Direct Ollama test failed: {e}")

async def main():
    # First test Ollama directly
    await test_llm_directly()
    
    # Then test with Graphiti
    await test_with_steps()

if __name__ == "__main__":
    asyncio.run(main())