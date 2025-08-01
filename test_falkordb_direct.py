#!/usr/bin/env python3
"""
Direct test of FalkorDB without using Graphiti drivers.
"""

import asyncio

from falkordb import FalkorDB


async def test_falkordb():
    """Test FalkorDB directly."""
    print('Testing FalkorDB direct connection...')

    # Connect to FalkorDB
    db = FalkorDB(host='localhost', port=6379)
    graph = db.select_graph('test_graph')

    try:
        # Clear any existing data
        print('\nClearing graph...')
        graph.query('MATCH (n) DETACH DELETE n')

        # Create simple test nodes
        print('\nCreating test nodes...')
        nodes = [
            ("CREATE (n:Technology {name: 'FalkorDB', type: 'GraphDB'})", 'FalkorDB'),
            ("CREATE (n:Technology {name: 'Neo4j', type: 'GraphDB'})", 'Neo4j'),
            ("CREATE (n:Concept {name: 'GraphDatabase', type: 'Concept'})", 'GraphDatabase'),
            ("CREATE (n:Language {name: 'Cypher', type: 'QueryLanguage'})", 'Cypher'),
        ]

        for query, name in nodes:
            result = graph.query(query)
            print(f'  Created: {name}')

        # Create relationships
        print('\nCreating relationships...')
        relationships = [
            (
                "MATCH (a:Technology {name: 'FalkorDB'}), (b:Concept {name: 'GraphDatabase'}) CREATE (a)-[:IS_A]->(b)",
                'FalkorDB IS_A GraphDatabase',
            ),
            (
                "MATCH (a:Technology {name: 'Neo4j'}), (b:Concept {name: 'GraphDatabase'}) CREATE (a)-[:IS_A]->(b)",
                'Neo4j IS_A GraphDatabase',
            ),
            (
                "MATCH (a:Technology {name: 'FalkorDB'}), (b:Language {name: 'Cypher'}) CREATE (a)-[:SUPPORTS]->(b)",
                'FalkorDB SUPPORTS Cypher',
            ),
            (
                "MATCH (a:Technology {name: 'Neo4j'}), (b:Language {name: 'Cypher'}) CREATE (a)-[:SUPPORTS]->(b)",
                'Neo4j SUPPORTS Cypher',
            ),
        ]

        for query, desc in relationships:
            result = graph.query(query)
            print(f'  Created: {desc}')

        # Query the data
        print('\nQuerying data...')

        # Count nodes
        result = graph.query('MATCH (n) RETURN count(n) as count')
        print(f'\nTotal nodes: {result.result_set[0][0]}')

        # Count relationships
        result = graph.query('MATCH ()-[r]->() RETURN count(r) as count')
        print(f'Total relationships: {result.result_set[0][0]}')

        # Show all nodes
        print('\nAll nodes:')
        result = graph.query('MATCH (n) RETURN n.name, labels(n)')
        for row in result.result_set:
            name = row[0]
            labels = row[1]
            print(f'  - {name} (labels: {labels})')

        # Show all relationships
        print('\nAll relationships:')
        result = graph.query('MATCH (a)-[r]->(b) RETURN a.name, type(r), b.name')
        for row in result.result_set:
            print(f'  - {row[0]} --[{row[1]}]--> {row[2]}')

        # Test pattern matching
        print('\nTechnologies that support Cypher:')
        result = graph.query(
            "MATCH (t:Technology)-[:SUPPORTS]->(c:Language {name: 'Cypher'}) RETURN t.name"
        )
        for row in result.result_set:
            print(f'  - {row[0]}')

        print('\n✓ FalkorDB is working correctly!')

    except Exception as e:
        print(f'\n✗ Error: {e}')
        import traceback

        traceback.print_exc()

    finally:
        db.close()


if __name__ == '__main__':
    asyncio.run(test_falkordb())
