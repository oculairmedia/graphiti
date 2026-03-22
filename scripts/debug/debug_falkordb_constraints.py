#!/usr/bin/env python3
"""Debug FalkorDB constraints and their enforcement."""

import asyncio
from falkordb import FalkorDB


async def debug_falkordb_constraints():
    """Check FalkorDB constraints and their enforcement."""
    print('=== FalkorDB Constraint Investigation ===')

    # Connect to FalkorDB
    falkor_db = FalkorDB(host='localhost', port=6379)
    falkor_graph = falkor_db.select_graph('knowledge_graph')

    try:
        # Check if there are any existing constraints
        print('\n1. Checking existing constraints:')
        try:
            constraints_result = falkor_graph.query('CALL db.constraints()')
            constraints = constraints_result.result_set
            if constraints:
                for constraint in constraints:
                    print(f'   Constraint: {constraint}')
            else:
                print('   No constraints found')
        except Exception as e:
            print(f'   Error checking constraints: {e}')

        # Check existing RELATES_TO relationships and their properties
        print('\n2. Checking existing RELATES_TO relationships:')
        try:
            rels_result = falkor_graph.query("""
                MATCH ()-[r:RELATES_TO]->() 
                RETURN count(r) as total_relates_to
            """)
            total_relates_to = rels_result.result_set[0][0] if rels_result.result_set else 0
            print(f'   Total RELATES_TO relationships: {total_relates_to}')

            if total_relates_to > 0:
                # Sample a few relationships to check their properties
                sample_result = falkor_graph.query("""
                    MATCH ()-[r:RELATES_TO]->() 
                    RETURN properties(r) as props 
                    LIMIT 5
                """)
                print('   Sample relationship properties:')
                for i, record in enumerate(sample_result.result_set):
                    props = record[0]
                    print(f'     Relationship {i + 1}: {props}')

                    # Check specifically for uuid and group_id
                    has_uuid = 'uuid' in props if props else False
                    has_group_id = 'group_id' in props if props else False
                    print(f'       Has uuid: {has_uuid}, Has group_id: {has_group_id}')
        except Exception as e:
            print(f'   Error checking relationships: {e}')

        # Try to create a test RELATES_TO relationship to see what happens
        print('\n3. Testing RELATES_TO relationship creation:')

        # First create two test nodes
        try:
            falkor_graph.query("""
                CREATE (s:TestNode {uuid: 'test-source-uuid', name: 'test-source'})
                CREATE (t:TestNode {uuid: 'test-target-uuid', name: 'test-target'})
            """)
            print('   Created test nodes')

            # Try creating relationship WITHOUT required properties
            try:
                falkor_graph.query("""
                    MATCH (s:TestNode {uuid: 'test-source-uuid'}), (t:TestNode {uuid: 'test-target-uuid'})
                    CREATE (s)-[:RELATES_TO]->(t)
                """)
                print('   ✓ RELATES_TO without properties: SUCCESS')
            except Exception as e:
                print(f'   ✗ RELATES_TO without properties: FAILED - {e}')

            try:
                falkor_graph.query("""
                    MATCH (s:TestNode {uuid: 'test-source-uuid'}), (t:TestNode {uuid: 'test-target-uuid'})
                    CREATE (s)-[:RELATES_TO {uuid: 'test-rel-uuid'}]->(t)
                """)
                print('   ✓ RELATES_TO with uuid only: SUCCESS')
            except Exception as e:
                print(f'   ✗ RELATES_TO with uuid only: FAILED - {e}')

            try:
                falkor_graph.query("""
                    MATCH (s:TestNode {uuid: 'test-source-uuid'}), (t:TestNode {uuid: 'test-target-uuid'})
                    CREATE (s)-[:RELATES_TO {uuid: 'test-rel-uuid-2', group_id: 'test-group'}]->(t)
                """)
                print('   ✓ RELATES_TO with uuid and group_id: SUCCESS')
            except Exception as e:
                print(f'   ✗ RELATES_TO with uuid and group_id: FAILED - {e}')

            # Clean up test data
            falkor_graph.query("""
                MATCH (n:TestNode) DETACH DELETE n
            """)
            print('   Cleaned up test nodes')

        except Exception as e:
            print(f'   Error during relationship testing: {e}')

        # Check database info
        print('\n4. Database information:')
        try:
            info_result = falkor_graph.query('CALL db.info()')
            info = info_result.result_set
            if info:
                for item in info:
                    print(f'   {item}')
        except Exception as e:
            print(f'   Error getting db info: {e}')

        # Check graph statistics
        print('\n5. Graph statistics:')
        try:
            # Node count by label
            node_result = falkor_graph.query("""
                MATCH (n) 
                RETURN labels(n)[0] as label, count(n) as count 
                ORDER BY count DESC
            """)
            print('   Nodes by label:')
            for record in node_result.result_set:
                label = record[0] if record[0] else 'UNLABELED'
                count = record[1]
                print(f'     {label}: {count}')

            # Relationship count by type
            rel_result = falkor_graph.query("""
                MATCH ()-[r]->() 
                RETURN type(r) as rel_type, count(r) as count 
                ORDER BY count DESC
            """)
            print('   Relationships by type:')
            for record in rel_result.result_set:
                rel_type = record[0]
                count = record[1]
                print(f'     {rel_type}: {count}')

        except Exception as e:
            print(f'   Error getting statistics: {e}')

    except Exception as e:
        print(f'Error connecting to FalkorDB: {e}')

    print('\n=== Investigation Complete ===')


if __name__ == '__main__':
    asyncio.run(debug_falkordb_constraints())
