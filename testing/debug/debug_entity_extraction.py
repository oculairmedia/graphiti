#!/usr/bin/env python3
"""
Debug entity extraction by checking what entities were actually created
"""

import json

from falkordb import FalkorDB

# Connect to FalkorDB
falkor_db = FalkorDB(host='localhost', port=6389)
db = falkor_db.select_graph('graphiti_migration')

# Get all entities from test group
query = """
MATCH (e:Episodic {group_id: 'test_entity_extraction'})-[:MENTIONS]->(n:Entity)
RETURN e.uuid as episode_id, e.name as episode_name, n.uuid as entity_id, n.name as entity_name, n.type as entity_type, n.summary as entity_summary
ORDER BY e.created_at DESC
"""

result = db.query(query)

print('Entities Extracted from Test Episodes:')
print('=' * 100)

current_episode = None
for record in result.result_set:
    episode_id = record[0]
    episode_name = record[1]
    entity_id = record[2]
    entity_name = record[3]
    entity_type = record[4]
    entity_summary = record[5]

    if current_episode != episode_id:
        if current_episode:
            print()
        current_episode = episode_id
        print(f'Episode: {episode_name} ({episode_id})')
        print('-' * 50)

    print(f'  - Entity: {entity_name}')
    print(f'    Type: {entity_type}')
    print(f'    ID: {entity_id}')
    if entity_summary:
        print(f'    Summary: {entity_summary[:100]}...')

# Also check if there are any entities without the test group
query2 = """
MATCH (n:Entity)
WHERE n.created_at > datetime() - duration('PT10M')
RETURN n.name, n.type, n.group_id
ORDER BY n.created_at DESC
LIMIT 20
"""

result2 = db.query(query2)

print('\n\nRecent Entities (last 10 minutes):')
print('=' * 100)
for record in result2.result_set:
    name = record[0]
    entity_type = record[1]
    group_id = record[2]
    print(f'{name} ({entity_type}) - group: {group_id}')
