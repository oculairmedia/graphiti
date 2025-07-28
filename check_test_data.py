#!/usr/bin/env python3
"""
Check test data in FalkorDB
"""

from falkordb import FalkorDB

# Connect to FalkorDB
falkor_db = FalkorDB(host='localhost', port=6389)
db = falkor_db.select_graph('graphiti_migration')

# Query episodic nodes for test group
query = """
MATCH (e:Episodic {group_id: 'test_entity_extraction'})
RETURN e.uuid, e.name, e.content
ORDER BY e.created_at DESC
LIMIT 10
"""

result = db.query(query)

print("Test Episodic Nodes:")
print("=" * 80)
for record in result.result_set:
    uuid = record[0]
    name = record[1]
    content = record[2][:100] if record[2] else "No content"
    print(f"UUID: {uuid}")
    print(f"Name: {name}")
    print(f"Content: {content}...")
    print("-" * 40)

# Check entities created from test messages
entity_query = """
MATCH (e:Episodic {group_id: 'test_entity_extraction'})-[:MENTIONS]->(n:Entity)
RETURN DISTINCT n.name, n.type, COUNT(e) as mention_count
ORDER BY mention_count DESC
"""

entity_result = db.query(entity_query)

print("\nEntities Extracted from Test Messages:")
print("=" * 80)
for record in entity_result.result_set:
    name = record[0]
    entity_type = record[1]
    mentions = record[2]
    print(f"{name} ({entity_type}) - {mentions} mentions")

# Count total test episodes
count_query = """
MATCH (e:Episodic {group_id: 'test_entity_extraction'})
RETURN COUNT(e) as total
"""

count_result = db.query(count_query)
total = count_result.result_set[0][0] if count_result.result_set else 0
print(f"\nTotal test episodes: {total}")