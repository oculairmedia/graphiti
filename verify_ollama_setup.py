#!/usr/bin/env python3
"""
Quick verification script for Ollama setup with Graphiti.
"""

import os
import sys
from dotenv import load_dotenv

print("🔍 Verifying Ollama Setup for Graphiti")
print("=" * 50)

# Check for .env.ollama
if os.path.exists('.env.ollama'):
    print("✅ Found .env.ollama file")
    load_dotenv('.env.ollama', override=True)
else:
    print("❌ .env.ollama file not found")
    sys.exit(1)

# Check environment variables
env_vars = {
    'USE_OLLAMA': os.getenv('USE_OLLAMA'),
    'OLLAMA_BASE_URL': os.getenv('OLLAMA_BASE_URL'),
    'OLLAMA_MODEL': os.getenv('OLLAMA_MODEL'),
    'OPENAI_API_KEY': os.getenv('OPENAI_API_KEY')
}

print("\n📋 Environment Variables:")
for var, value in env_vars.items():
    if value:
        if var == 'OPENAI_API_KEY':
            # Mask the API key
            masked = value[:8] + '...' + value[-4:] if len(value) > 12 else '***'
            print(f"   {var}: {masked}")
        else:
            print(f"   {var}: {value}")
    else:
        print(f"   {var}: ❌ Not set")

# Check Ollama connectivity
if env_vars['USE_OLLAMA'] == 'true':
    print("\n🦙 Testing Ollama Connection...")
    import requests
    
    try:
        base_url = env_vars['OLLAMA_BASE_URL'].rstrip('/v1')
        response = requests.get(f"{base_url}/api/tags", timeout=5)
        
        if response.status_code == 200:
            print("   ✅ Connected to Ollama")
            models = response.json().get('models', [])
            
            if models:
                print("   Available models:")
                for model in models:
                    name = model.get('name', 'unknown')
                    size = model.get('size', 0) / (1024**3)  # Convert to GB
                    print(f"     - {name} ({size:.1f} GB)")
                    
                # Check if requested model is available
                model_names = [m.get('name') for m in models]
                requested_model = env_vars['OLLAMA_MODEL']
                
                if requested_model in model_names:
                    print(f"\n   ✅ Requested model '{requested_model}' is available")
                else:
                    print(f"\n   ⚠️  Requested model '{requested_model}' not found")
                    print(f"   Available models: {', '.join(model_names)}")
            else:
                print("   ⚠️  No models found in Ollama")
        else:
            print(f"   ❌ Ollama returned status {response.status_code}")
            
    except requests.exceptions.ConnectionError:
        print("   ❌ Cannot connect to Ollama")
        print(f"   Make sure Ollama is running at {env_vars['OLLAMA_BASE_URL']}")
    except Exception as e:
        print(f"   ❌ Error: {e}")

# Test import
print("\n🐍 Testing Python imports...")
try:
    from use_ollama import Graphiti
    print("   ✅ Successfully imported Graphiti from use_ollama.py")
    
    # Check if it will use Ollama
    if env_vars['USE_OLLAMA'] == 'true':
        print("   ✅ Graphiti will use Ollama for LLM calls")
    else:
        print("   ⚠️  Graphiti will use OpenAI (USE_OLLAMA != 'true')")
        
except ImportError as e:
    print(f"   ❌ Import error: {e}")

# Check FalkorDB connection
print("\n🗄️  Checking FalkorDB...")
try:
    from falkordb import FalkorDB
    
    host = os.getenv('FALKORDB_HOST', 'localhost')
    port = int(os.getenv('FALKORDB_PORT', '6389') or '6389')
    
    db = FalkorDB(host=host, port=port)
    db.select_graph("test_connection")
    print(f"   ✅ Connected to FalkorDB at {host}:{port}")
    
except Exception as e:
    print(f"   ❌ FalkorDB connection error: {e}")
    print("   Make sure FalkorDB is running")

print("\n✨ Setup verification complete!")

# Summary
if env_vars['USE_OLLAMA'] == 'true' and env_vars['OLLAMA_BASE_URL']:
    print("\n📌 Summary: Graphiti is configured to use Ollama")
    print(f"   Model: {env_vars['OLLAMA_MODEL']}")
    print(f"   Endpoint: {env_vars['OLLAMA_BASE_URL']}")
else:
    print("\n📌 Summary: Graphiti will use OpenAI (default)")