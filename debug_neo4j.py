#!/usr/bin/env python3
"""Debug Neo4j connection and query results."""

import asyncio
from graphiti_core.driver.neo4j_driver import Neo4jDriver

async def debug_connection():
    neo4j_driver = Neo4jDriver(
        uri="bolt://localhost:7687",
        user="neo4j",
        password="demodemo"
    )
    
    try:
        result = await neo4j_driver.execute_query("MATCH (n) RETURN count(n) as count")
        print(f"Result type: {type(result)}")
        print(f"Result: {result}")
        if result:
            print(f"First item type: {type(result[0])}")
            print(f"First item: {result[0]}")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await neo4j_driver.close()

asyncio.run(debug_connection())