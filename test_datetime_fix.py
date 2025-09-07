#!/usr/bin/env python3
"""Test that datetime fields are preserved in migration."""

import asyncio
from sync_service.simple_migration import perform_simple_migration
from falkordb import FalkorDB

async def test_datetime_fix():
    # Clear and migrate
    falkor_db = FalkorDB(host='localhost', port=6379)
    falkor_graph = falkor_db.select_graph('graphiti_migration')
    
    print('Clearing database...')
    try:
        falkor_graph.delete()
    except:
        pass
    
    print('Running migration...')
    neo4j_config = {
        'uri': 'bolt://localhost:7687',
        'user': 'neo4j',
        'password': 'demodemo'
    }
    
    falkordb_config = {
        'host': 'localhost',
        'port': 6379,
        'database': 'graphiti_migration'
    }
    
    stats = await perform_simple_migration(neo4j_config, falkordb_config)
    print(f'Migration completed: {stats["relationships_migrated"]} relationships')
    
    # Check RELATES_TO datetime fields
    result = falkor_graph.query("""
        MATCH ()-[r:RELATES_TO]->()
        RETURN properties(r) as props
        LIMIT 5
    """)
    
    print('\nChecking RELATES_TO relationships for datetime fields:')
    date_field_counts = {'valid_at': 0, 'created_at': 0, 'invalid_at': 0, 'expired_at': 0}
    
    for i, record in enumerate(result.result_set, 1):
        props = record[0]
        print(f'\nRelationship {i}:')
        has_dates = False
        for key in ['valid_at', 'created_at', 'invalid_at', 'expired_at']:
            if key in props:
                print(f'  ✓ {key}: {props[key]}')
                date_field_counts[key] += 1
                has_dates = True
                # Check for corruption
                if props[key].startswith('197'):
                    print(f'    ⚠️ CORRUPTED DATE!')
        if not has_dates:
            print('  ✗ NO DATETIME FIELDS FOUND')
            print(f'  Properties: {list(props.keys())}')
    
    print('\n' + '='*50)
    print('Summary:')
    for field, count in date_field_counts.items():
        print(f'  {field}: {count}/5 relationships have this field')

if __name__ == "__main__":
    asyncio.run(test_datetime_fix())