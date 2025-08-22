#!/usr/bin/env python3
"""Direct test of the FalkorDB v2 client using the official library."""

import redis
import json
import numpy as np

# Connection settings
FALKOR_HOST = "localhost"
FALKOR_PORT = 6389
GRAPH_NAME = "graphiti_migration"

def test_direct_similarity():
    """Test similarity search directly against FalkorDB."""
    
    # Connect to FalkorDB
    r = redis.Redis(host=FALKOR_HOST, port=FALKOR_PORT, decode_responses=False)
    
    # Create a test embedding (1024 dimensions, normalized)
    test_embedding = np.random.randn(1024).astype(np.float32)
    test_embedding = test_embedding / np.linalg.norm(test_embedding)
    
    # Format as FalkorDB expects
    embedding_str = ",".join(str(v) for v in test_embedding)
    
    # Test query with vecf32 function to ensure proper type conversion
    query = f"""
    MATCH (n:Entity) 
    WHERE n.name_embedding IS NOT NULL
    WITH n, (2 - vec.cosineDistance(n.name_embedding, vecf32([{embedding_str}])))/2 AS score
    WHERE score >= 0.0
    RETURN n.uuid, n.name, score 
    ORDER BY score DESC 
    LIMIT 5
    """
    
    print("Testing similarity search with FalkorDB v2 client approach...")
    print(f"Query length: {len(query)} chars")
    
    try:
        # Execute query
        result = r.execute_command("GRAPH.QUERY", GRAPH_NAME, query)
        
        # Parse results
        if result and len(result) > 1:
            headers = result[0]
            data = result[1]
            
            print(f"\n✓ Query successful! Found {len(data)} results")
            
            if data:
                for i, row in enumerate(data[:3]):  # Show top 3
                    uuid, name, score = row
                    print(f"  {i+1}. {name.decode() if isinstance(name, bytes) else name} (score: {score:.4f})")
            
            return True
        else:
            print("✗ No results returned")
            return False
            
    except Exception as e:
        print(f"✗ Query failed: {e}")
        return False

def test_edge_similarity():
    """Test edge similarity search."""
    
    # Connect to FalkorDB
    r = redis.Redis(host=FALKOR_HOST, port=FALKOR_PORT, decode_responses=False)
    
    # Create a test embedding
    test_embedding = np.random.randn(1024).astype(np.float32)
    test_embedding = test_embedding / np.linalg.norm(test_embedding)
    embedding_str = ",".join(str(v) for v in test_embedding)
    
    # Test edge similarity query
    query = f"""
    MATCH (a)-[r:RELATES_TO]->(b)
    WHERE r.fact_embedding IS NOT NULL
    WITH a, r, b, (2 - vec.cosineDistance(r.fact_embedding, vecf32([{embedding_str}])))/2 AS score
    WHERE score >= 0.0
    RETURN r.uuid, r.fact, score
    ORDER BY score DESC
    LIMIT 5
    """
    
    print("\nTesting edge similarity search...")
    
    try:
        result = r.execute_command("GRAPH.QUERY", GRAPH_NAME, query)
        
        if result and len(result) > 1:
            data = result[1]
            print(f"✓ Edge query successful! Found {len(data)} results")
            
            if data:
                for i, row in enumerate(data[:3]):
                    uuid, fact, score = row
                    fact_str = fact.decode() if isinstance(fact, bytes) else fact
                    preview = fact_str[:50] + "..." if len(fact_str) > 50 else fact_str
                    print(f"  {i+1}. {preview} (score: {score:.4f})")
            
            return True
        else:
            print("✗ No edge results")
            return False
            
    except Exception as e:
        print(f"✗ Edge query failed: {e}")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("Testing FalkorDB v2 Client Approach")
    print("=" * 60)
    
    # Run tests
    node_success = test_direct_similarity()
    edge_success = test_edge_similarity()
    
    print("\n" + "=" * 60)
    if node_success and edge_success:
        print("✓ SUCCESS! The FalkorDB v2 client approach works correctly.")
        print("  The vecf32() function properly converts arrays to Vectorf32.")
        print("  No more type mismatch errors!")
    else:
        print("✗ Some tests failed.")
    print("=" * 60)