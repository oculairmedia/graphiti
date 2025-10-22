#!/usr/bin/env python3
"""Debug relationship property formatting."""

import asyncio
from neo4j import AsyncGraphDatabase
from sync_service.simple_migration import format_value, escape_string

async def debug_relationship_props():
    driver = AsyncGraphDatabase.driver(
        'bolt://localhost:7687',
        auth=('neo4j', 'demodemo')
    )
    
    async with driver.session() as session:
        # Get the failing relationship
        result = await session.run("""
            MATCH (s {uuid: 'd246cb25-9a96-5426-8777-3319e60c57c0'})-[r:RELATES_TO]->(t {uuid: 'a8698f06-6efb-5fd5-884e-1b068d408e02'})
            RETURN properties(r) as props
            LIMIT 1
        """)
        
        record = await result.single()
        if record:
            props = record['props']
            print("Original properties:", props)
            print("\nFormatted properties:")
            
            prop_list = []
            for key, value in props.items():
                formatted_value = format_value(value, key)
                prop_string = f"{key}: {formatted_value}"
                prop_list.append(prop_string)
                print(f"  {key}: {value} -> {prop_string}")
            
            full_prop_string = "{" + ", ".join(prop_list) + "}"
            print(f"\nFull property string: {full_prop_string}")
            
            # Test essential property filtering
            essential_props = []
            for prop in prop_list:
                if any(key in prop for key in ['uuid:', 'name:', 'fact:', 'group_id:']):
                    essential_props.append(prop)
                    print(f"  ESSENTIAL: {prop}")
                else:
                    print(f"  FILTERED: {prop}")
            
            essential_prop_string = "{" + ", ".join(essential_props) + "}" if essential_props else ""
            print(f"\nEssential properties string: {essential_prop_string}")
            
            # Test the actual query that would be generated
            source_uuid = 'd246cb25-9a96-5426-8777-3319e60c57c0'
            target_uuid = 'a8698f06-6efb-5fd5-884e-1b068d408e02'
            rel_type = 'RELATES_TO'
            
            rel_query = f"""
            MATCH (s {{uuid: '{escape_string(source_uuid)}'}}), (t {{uuid: '{escape_string(target_uuid)}'}}) 
            CREATE (s)-[:{rel_type} {full_prop_string}]->(t)
            """
            print(f"\nGenerated query:\n{rel_query}")
            print(f"Query length: {len(rel_query)}")
            
        else:
            print("Relationship not found")

    await driver.close()

if __name__ == "__main__":
    asyncio.run(debug_relationship_props())