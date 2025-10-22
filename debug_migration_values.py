#!/usr/bin/env python3
"""Debug script to see what types of values Neo4j returns."""

import asyncio
from neo4j import AsyncGraphDatabase
from datetime import datetime

async def debug_neo4j_values():
    driver = AsyncGraphDatabase.driver(
        'bolt://localhost:7687',
        auth=('neo4j', 'demodemo')
    )
    
    async with driver.session() as session:
        # Get a sample node with datetime fields
        # Get sample node properties to see datetime handling
        result = await session.run("""
            MATCH (n) 
            WHERE n.created_at IS NOT NULL
            RETURN properties(n) as props, labels(n)[0] as label
            LIMIT 1
        """)
        
        record = await result.single()
        if record:
            props = record['props']
            label = record['label']
            print(f"Node type: {label}")
            print(f"All properties with datetime-related fields:")
            
            for key, value in props.items():
                if any(suffix in key.lower() for suffix in ['date', 'created', '_at', 'timestamp']):
                    print(f"\n{key}:")
                    print(f"  Type: {type(value)}")
                    print(f"  Value: {value}")
                    print(f"  Repr: {repr(value)}")
                    
                    if hasattr(value, 'to_native'):
                        try:
                            native = value.to_native()
                            print(f"  to_native() type: {type(native)}")
                            print(f"  to_native() value: {native}")
                        except Exception as e:
                            print(f"  to_native() error: {e}")
                            
                    # Test our format_value function
                    try:
                        from sync_service.simple_migration import format_value
                        formatted = format_value(value, key)
                        print(f"  format_value() result: {formatted}")
                    except Exception as e:
                        print(f"  format_value() error: {e}")
                        
        else:
            print("No records found with created_at field")

    await driver.close()

if __name__ == "__main__":
    asyncio.run(debug_neo4j_values())