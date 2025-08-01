#!/usr/bin/env python3
"""
Direct FalkorDB test using redis-cli to understand the data format.
"""

import json
import subprocess


def run_falkor_query(database, query):
    """Run a query directly through redis-cli."""
    cmd = ['docker', 'exec', 'graphiti-falkordb-1', 'redis-cli', 'GRAPH.QUERY', database, query]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            return result.stdout
        else:
            return f'Error: {result.stderr}'
    except Exception as e:
        return f'Exception: {e}'


def main():
    print('🔍 Direct FalkorDB Query Test')
    print('=' * 50)

    database = 'devstral_test'

    # Test 1: Get episodes
    print('\n1️⃣ Getting all episodes...')
    result = run_falkor_query(
        database,
        'MATCH (e:Episodic) RETURN e.name as name, e.content as content ORDER BY e.created_at',
    )
    print('Raw result:')
    print(result)

    # Test 2: Count nodes
    print('\n2️⃣ Counting all nodes...')
    result = run_falkor_query(database, 'MATCH (n) RETURN count(n)')
    print('Raw result:')
    print(result)

    # Test 3: Search for McCarthy
    print("\n3️⃣ Searching for 'McCarthy'...")
    result = run_falkor_query(
        database, "MATCH (e:Episodic) WHERE e.content CONTAINS 'McCarthy' RETURN e.name, e.content"
    )
    print('Raw result:')
    print(result)

    # Test 4: Get node labels
    print('\n4️⃣ Getting node labels...')
    result = run_falkor_query(database, 'MATCH (n) RETURN DISTINCT labels(n)')
    print('Raw result:')
    print(result)

    # Test 5: Check embeddings
    print('\n5️⃣ Checking for embeddings...')
    result = run_falkor_query(
        database,
        'MATCH (e:Episodic) WHERE EXISTS(e.embedding) RETURN e.name, SIZE(e.embedding) as embed_size LIMIT 1',
    )
    print('Raw result:')
    print(result)

    print('\n✨ Direct query test complete!')


if __name__ == '__main__':
    main()
