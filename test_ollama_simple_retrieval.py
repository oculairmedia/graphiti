#!/usr/bin/env python3
"""
Simple test to verify data can be retrieved after adding with Ollama.
Uses direct database queries to avoid API compatibility issues.
"""

import asyncio

from graphiti_core.driver.falkordb_driver import FalkorDriver


async def test_falkordb_direct():
    """Test FalkorDB directly to see what data exists."""

    print('🔍 Direct FalkorDB Data Inspection')
    print('=' * 50)

    # Create FalkorDB driver
    driver = FalkorDriver(host='localhost', port=6389, database='graphiti_test')

    try:
        # Test 1: Basic connectivity
        print('\n1️⃣ Testing FalkorDB connection...')
        try:
            # Simple query without parameters
            result = await driver.execute_query('RETURN 1 as test')
            print(f'✅ Connection successful: {result}')
        except Exception as e:
            print(f'❌ Connection failed: {e}')
            return

        # Test 2: Count all nodes
        print('\n2️⃣ Counting all nodes...')
        try:
            result = await driver.execute_query('MATCH (n) RETURN count(n) as count')
            if result and len(result) > 0:
                # FalkorDB returns a list of lists
                count = result[0][0] if isinstance(result[0], list) else result[0].get('count', 0)
                print(f'✅ Total nodes: {count}')
            else:
                print('❌ No result returned')
        except Exception as e:
            print(f'❌ Count failed: {e}')

        # Test 3: Get node labels
        print('\n3️⃣ Getting node types...')
        try:
            result = await driver.execute_query(
                'MATCH (n) RETURN DISTINCT labels(n) as types, count(n) as count'
            )
            if result:
                print('✅ Node types found:')
                for row in result:
                    if isinstance(row, list) and len(row) >= 2:
                        print(f'   - {row[0]}: {row[1]} nodes')
                    elif isinstance(row, dict):
                        print(f'   - {row.get("types", "Unknown")}: {row.get("count", 0)} nodes')
            else:
                print('❌ No node types found')
        except Exception as e:
            print(f'❌ Labels query failed: {e}')

        # Test 4: Get some actual nodes
        print('\n4️⃣ Getting sample nodes...')
        try:
            result = await driver.execute_query('MATCH (n) RETURN n LIMIT 5')
            if result:
                print(f'✅ Found {len(result)} nodes:')
                for i, row in enumerate(result):
                    print(f'\n   Node {i + 1}:')
                    if isinstance(row, list) and len(row) > 0:
                        node = row[0]
                        if hasattr(node, 'properties'):
                            props = node.properties
                            print(f'   - Properties: {dict(props) if props else "None"}')
                        else:
                            print(f'   - Data: {node}')
                    else:
                        print(f'   - Raw: {row}')
            else:
                print('❌ No nodes found')
        except Exception as e:
            print(f'❌ Node retrieval failed: {e}')

        # Test 5: Check for Entity nodes specifically
        print('\n5️⃣ Looking for Entity nodes...')
        try:
            result = await driver.execute_query(
                'MATCH (n:Entity) RETURN n.name as name, n.uuid as uuid LIMIT 10'
            )
            if result:
                print(f'✅ Found {len(result)} Entity nodes:')
                for row in result:
                    if isinstance(row, list) and len(row) >= 2:
                        print(f'   - Name: {row[0]}, UUID: {row[1]}')
                    elif isinstance(row, dict):
                        print(
                            f'   - Name: {row.get("name", "N/A")}, UUID: {row.get("uuid", "N/A")}'
                        )
            else:
                print('❌ No Entity nodes found')
        except Exception as e:
            print(f'❌ Entity query failed: {e}')

        # Test 6: Check for Episode nodes
        print('\n6️⃣ Looking for Episode nodes...')
        try:
            result = await driver.execute_query(
                'MATCH (n:EpisodicNode) RETURN n.name as name, n.created_at as created LIMIT 10'
            )
            if result:
                print(f'✅ Found {len(result)} Episode nodes:')
                for row in result:
                    if isinstance(row, list) and len(row) >= 2:
                        print(f'   - Name: {row[0]}, Created: {row[1]}')
                    elif isinstance(row, dict):
                        print(
                            f'   - Name: {row.get("name", "N/A")}, Created: {row.get("created", "N/A")}'
                        )
            else:
                print('❌ No Episode nodes found')
        except Exception as e:
            print(f'❌ Episode query failed: {e}')

        # Test 7: Check graph schema
        print('\n7️⃣ Checking graph schema...')
        try:
            # Try to get all relationship types
            result = await driver.execute_query(
                'MATCH ()-[r]->() RETURN DISTINCT type(r) as rel_type, count(r) as count'
            )
            if result:
                print('✅ Relationship types found:')
                for row in result:
                    if isinstance(row, list) and len(row) >= 2:
                        print(f'   - {row[0]}: {row[1]} relationships')
                    elif isinstance(row, dict):
                        print(
                            f'   - {row.get("rel_type", "Unknown")}: {row.get("count", 0)} relationships'
                        )
            else:
                print('❌ No relationships found')
        except Exception as e:
            print(f'❌ Relationship query failed: {e}')

        print('\n✨ Inspection complete!')

    except Exception as e:
        print(f'\n❌ Test failed: {e}')
        import traceback

        traceback.print_exc()

    finally:
        await driver.close()


async def main():
    """Run the simple retrieval test."""
    await test_falkordb_direct()


if __name__ == '__main__':
    asyncio.run(main())
