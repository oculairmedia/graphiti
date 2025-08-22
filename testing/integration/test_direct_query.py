#!/usr/bin/env python3
"""
Test the specific query that was failing with FalkorDB.
"""

import asyncio

from graphiti_core.driver.falkordb_driver import FalkorDriver


async def test_problematic_query():
    print('🔍 Testing Direct FalkorDB Query')
    print('=' * 60)

    # Connect to FalkorDB
    falkor_driver = FalkorDriver(host='localhost', port=6389, database='direct_test')

    try:
        # Build basic indices first
        print('\n1️⃣ Creating indices...')
        await falkor_driver.execute_query(
            'CREATE INDEX FOR (n:Entity) ON (n.uuid, n.group_id, n.name, n.created_at)'
        )
        print('✅ Entity index created')

        # Create a test entity with embedding
        print('\n2️⃣ Creating test entity with embedding...')
        test_embedding = [0.1] * 384  # Create a dummy 384-dimensional embedding

        await falkor_driver.execute_query(
            """
            CREATE (n:Entity {
                uuid: $uuid,
                name: $name,
                group_id: $group_id,
                created_at: $created_at,
                summary: $summary,
                name_embedding: vecf32($embedding)
            })
            RETURN n.uuid as uuid
            """,
            uuid='test-entity-1',
            name='Albert Einstein',
            group_id='_',
            created_at='2024-01-01T00:00:00Z',
            summary='Physicist who developed the theory of relativity',
            embedding=test_embedding,
        )
        print('✅ Test entity created')

        # Now test the problematic query that was failing
        print('\n3️⃣ Testing the similarity search query...')

        # This is the query that was failing with "CYPHER params" error
        search_vector = [0.1] * 384  # Another dummy embedding for search

        result = await falkor_driver.execute_query(
            """
            MATCH (n:Entity)
            WHERE n.group_id IS NOT NULL AND n.group_id IN $group_ids
            WITH n, (2 - vec.cosineDistance(n.name_embedding, vecf32($search_vector)))/2 AS score
            WHERE score > $min_score
            RETURN
                n.uuid AS uuid, 
                n.name AS name,
                n.group_id AS group_id,
                n.created_at AS created_at, 
                n.summary AS summary,
                labels(n) AS labels,
                score
            ORDER BY score DESC
            LIMIT $limit
            """,
            search_vector=search_vector,
            group_ids=['_'],
            limit=10,
            min_score=0.0,
            routing_='r',
        )

        if result and result[0]:
            print(f'✅ Query succeeded! Found {len(result[0])} results')
            for i, row in enumerate(result[0]):
                print(f'\n   Result {i + 1}:')
                print(f'   - Name: {row["name"]}')
                print(f'   - Score: {row["score"]:.4f}')
                print(f'   - Summary: {row["summary"]}')
        else:
            print('✅ Query executed but no results found')

        # Test with the RUNTIME_QUERY prefix (this should fail if not fixed)
        print('\n4️⃣ Testing with RUNTIME_QUERY prefix...')
        try:
            # This would be the problematic query with Neo4j runtime hint
            result = await falkor_driver.execute_query(
                """CYPHER runtime = parallel parallelRuntimeSupport=all
                MATCH (n:Entity)
                WHERE n.group_id IS NOT NULL
                RETURN n.name as name
                LIMIT 1
                """,
                group_ids=['_'],
            )
            print("❌ RUNTIME_QUERY prefix should have failed but didn't!")
        except Exception as e:
            print(f'✅ Expected error with RUNTIME_QUERY prefix: {str(e)[:100]}...')

        # Test fulltext search
        print('\n5️⃣ Testing fulltext search...')
        await falkor_driver.execute_query(
            'CREATE FULLTEXT INDEX FOR (n:Entity) ON (n.name, n.summary, n.group_id)'
        )

        # FalkorDB uses Redis search syntax with @ for fulltext
        result = await falkor_driver.execute_query(
            """
            MATCH (n:Entity)
            WHERE n.name =~ '.*Einstein.*'
            RETURN n.name as name, n.summary as summary
            """
        )

        if result and result[0]:
            print(f'✅ Fulltext search found {len(result[0])} results')

    except Exception as e:
        print(f'\n❌ Test failed: {e}')
        import traceback

        traceback.print_exc()

    finally:
        await falkor_driver.close()
        print('\n✨ Test complete!')


if __name__ == '__main__':
    asyncio.run(test_problematic_query())
