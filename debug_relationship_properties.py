#!/usr/bin/env python3
"""Debug what properties Neo4j RELATES_TO relationships actually have."""

import asyncio
from neo4j import AsyncGraphDatabase

async def check_relationship_properties():
    """Check what properties exist in Neo4j RELATES_TO relationships."""
    driver = AsyncGraphDatabase.driver(
        'bolt://localhost:7687',
        auth=('neo4j', 'demodemo')
    )
    
    async with driver.session() as session:
        # Get a sample of RELATES_TO relationships and their properties
        result = await session.run("""
            MATCH ()-[r:RELATES_TO]->()
            RETURN properties(r) as props, 
                   keys(properties(r)) as prop_keys
            LIMIT 10
        """)
        
        records = await result.data()
        
        print(f"Found {len(records)} RELATES_TO relationships")
        print("\nSample properties:")
        
        all_keys = set()
        missing_uuid = 0
        missing_group_id = 0
        
        for i, record in enumerate(records):
            props = record['props']
            keys = record['prop_keys']
            all_keys.update(keys)
            
            has_uuid = 'uuid' in props
            has_group_id = 'group_id' in props
            
            if not has_uuid:
                missing_uuid += 1
            if not has_group_id:
                missing_group_id += 1
            
            print(f"\nRelationship {i+1}:")
            print(f"  Keys: {keys}")
            print(f"  Has uuid: {has_uuid}")
            print(f"  Has group_id: {has_group_id}")
            if props:
                for key, value in props.items():
                    # Truncate long values for display
                    display_value = str(value)[:100] + "..." if len(str(value)) > 100 else str(value)
                    print(f"    {key}: {display_value}")
        
        print(f"\n=== SUMMARY ===")
        print(f"Total relationships checked: {len(records)}")
        print(f"All property keys found: {sorted(all_keys)}")
        print(f"Missing uuid: {missing_uuid}/{len(records)}")
        print(f"Missing group_id: {missing_group_id}/{len(records)}")
        
        # Check total count
        count_result = await session.run("MATCH ()-[r:RELATES_TO]->() RETURN count(r) as total")
        count_record = await count_result.single()
        total = count_record['total']
        print(f"Total RELATES_TO relationships in Neo4j: {total}")

    await driver.close()

if __name__ == "__main__":
    asyncio.run(check_relationship_properties())