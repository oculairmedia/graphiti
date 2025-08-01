#!/usr/bin/env python3

import asyncio

from neo4j import AsyncGraphDatabase


async def check_neo4j():
    driver = AsyncGraphDatabase.driver('bolt://192.168.50.90:7687', auth=('neo4j', 'demodemo'))

    try:
        async with driver.session() as session:
            # Check total node count
            result = await session.run('MATCH (n) RETURN count(n) as total_nodes')
            record = await result.single()
            total_nodes = record['total_nodes']
            print(f'Total nodes in Neo4j: {total_nodes}')

            # Check recent nodes (if any)
            result = await session.run("""
                MATCH (n) 
                RETURN labels(n) as labels, count(*) as count 
                ORDER BY count DESC 
                LIMIT 10
            """)

            print('\nNode types and counts:')
            async for record in result:
                print(f'  {record["labels"]}: {record["count"]}')

            # Check for any nodes with recent timestamps or group_ids
            result = await session.run("""
                MATCH (n) 
                WHERE n.group_id IS NOT NULL 
                RETURN n.group_id as group_id, labels(n) as labels, count(*) as count
                ORDER BY count DESC
                LIMIT 10
            """)

            print('\nNodes by group_id:')
            async for record in result:
                print(
                    f'  Group: {record["group_id"]}, Labels: {record["labels"]}, Count: {record["count"]}'
                )

    except Exception as e:
        print(f'Error: {e}')
    finally:
        await driver.close()


if __name__ == '__main__':
    asyncio.run(check_neo4j())
