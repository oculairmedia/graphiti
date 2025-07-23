#!/usr/bin/env python3
"""
Test Ollama embeddings directly to verify they work.
"""

import asyncio
from openai import AsyncOpenAI


async def test_ollama_embeddings():
    """Test Ollama's embedding capabilities."""
    
    print("🦙 Testing Ollama Embeddings")
    print("=" * 50)
    
    # Create Ollama client
    client = AsyncOpenAI(
        base_url="http://100.81.139.20:11434/v1",
        api_key="ollama"
    )
    
    # Test texts
    test_texts = [
        "Machine learning is a subset of artificial intelligence.",
        "Deep learning uses neural networks with multiple layers.",
        "The weather today is sunny and warm."
    ]
    
    print("\n📝 Test texts:")
    for i, text in enumerate(test_texts, 1):
        print(f"  {i}. {text}")
    
    # Test with different embedding models if available
    models_to_test = ["mxbai-embed-large", "nomic-embed-text", "all-minilm"]
    
    for model in models_to_test:
        print(f"\n🔍 Testing model: {model}")
        try:
            # Create embeddings
            response = await client.embeddings.create(
                model=model,
                input=test_texts
            )
            
            print(f"✅ Success! Generated {len(response.data)} embeddings")
            
            # Show embedding dimensions
            if response.data:
                embedding_dim = len(response.data[0].embedding)
                print(f"   Embedding dimension: {embedding_dim}")
                
                # Calculate similarity between first two embeddings
                if len(response.data) >= 2:
                    emb1 = response.data[0].embedding
                    emb2 = response.data[1].embedding
                    
                    # Simple cosine similarity
                    import math
                    dot_product = sum(a * b for a, b in zip(emb1, emb2))
                    norm1 = math.sqrt(sum(a * a for a in emb1))
                    norm2 = math.sqrt(sum(b * b for b in emb2))
                    similarity = dot_product / (norm1 * norm2)
                    
                    print(f"   Similarity between text 1 & 2: {similarity:.4f}")
                
        except Exception as e:
            print(f"❌ Error with {model}: {e}")
    
    print("\n✨ Embedding test complete!")


async def list_ollama_models():
    """List available Ollama models."""
    
    print("\n📋 Listing available Ollama models...")
    
    client = AsyncOpenAI(
        base_url="http://100.81.139.20:11434/v1",
        api_key="ollama"
    )
    
    try:
        # Try to list models
        models = await client.models.list()
        
        print("\nAvailable models:")
        for model in models.data:
            print(f"  - {model.id}")
            
    except Exception as e:
        print(f"❌ Error listing models: {e}")
        print("\nTry running: curl http://100.81.139.20:11434/api/tags")


if __name__ == "__main__":
    asyncio.run(test_ollama_embeddings())
    asyncio.run(list_ollama_models())