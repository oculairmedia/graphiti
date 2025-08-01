#!/usr/bin/env python3
"""
Debug FalkorDB parameter issue.
"""

import asyncio

from falkordb.asyncio import FalkorDB


async def test_falkor_params():
    """Test different parameter syntaxes with FalkorDB."""

    print('🔍 Testing FalkorDB Parameter Syntax')
    print('=' * 50)

    # Connect to FalkorDB
    db = FalkorDB(host='localhost', port=6389)
    graph = db.select_graph('test_params')

    try:
        # Test 1: Simple query without parameters
        print('\n1️⃣ Testing query without parameters...')
        try:
            result = await graph.query("CREATE (n:Test {name: 'test1'}) RETURN n")
            print('✅ Success: Query without parameters works')
        except Exception as e:
            print(f'❌ Error: {e}')

        # Test 2: Query with parameters (Neo4j style)
        print('\n2️⃣ Testing query with Neo4j-style parameters ($param)...')
        try:
            params = {'test_name': 'test2'}
            result = await graph.query('CREATE (n:Test {name: $test_name}) RETURN n', params)
            print('✅ Success: Neo4j-style parameters work')
        except Exception as e:
            print(f'❌ Error: {e}')

        # Test 3: Query with parameters (old style)
        print('\n3️⃣ Testing query with old-style parameters...')
        try:
            params = {'test_name': 'test3'}
            result = await graph.query('CREATE (n:Test {name: {test_name}}) RETURN n', params)
            print('✅ Success: Old-style parameters work')
        except Exception as e:
            print(f'❌ Error: {e}')

        # Test 4: What Graphiti might be sending
        print('\n4️⃣ Testing CYPHER params syntax...')
        try:
            # This is what the error suggests
            result = await graph.query('CYPHER params', {'test': 'value'})
            print('✅ Success: CYPHER params syntax works')
        except Exception as e:
            print(f'❌ Error: {e}')

        # Test 5: Check what's in the database
        print('\n5️⃣ Checking what was created...')
        try:
            result = await graph.query('MATCH (n:Test) RETURN n.name as name')
            print(f'✅ Found {len(result.result_set)} nodes')
            for row in result.result_set:
                print(f'   - {row[0]}')
        except Exception as e:
            print(f'❌ Error: {e}')

        # Test 6: Complex parameter query
        print('\n6️⃣ Testing complex parameter query...')
        try:
            params = {'name': 'Complex Test', 'props': {'key1': 'value1', 'key2': 123}}
            result = await graph.query(
                'CREATE (n:Test {name: $name, data: $props}) RETURN n', params
            )
            print('✅ Success: Complex parameters work')
        except Exception as e:
            print(f'❌ Error: {e}')

    finally:
        await db.close()
        print('\n✨ Test complete!')


if __name__ == '__main__':
    asyncio.run(test_falkor_params())
