#!/usr/bin/env python3
"""Remove duplicate nodes and relationships in FalkorDB by UUID.

The script keeps the first record (lowest internal id) for each UUID and
`DETACH DELETE`s the remaining copies. Intended for cleanup after fixing the
MERGE logic that previously allowed duplicate UUIDs.

Usage:
    python scripts/cleanup_falkor_duplicates.py --host localhost --graph graphiti_migration

NOTE: This deletes duplicate records and their relationships. Ensure you have a
backup before running in production.
"""

from __future__ import annotations

import argparse
import asyncio
from typing import Iterable

from falkordb.asyncio import FalkorDB


async def get_duplicate_uuids(graph, entity: str) -> list[str]:
    query = f"""
    MATCH ({entity})
    WITH {entity}.uuid AS uuid, COUNT(*) AS cnt
    WHERE cnt > 1
    RETURN uuid
    """
    result = await graph.query(query)
    return [row[0] for row in result.result_set]


async def cleanup_duplicate_nodes(graph) -> int:
    uuids = await get_duplicate_uuids(graph, "n")
    deleted = 0
    for uuid in uuids:
        query = """
        MATCH (n:Entity {uuid: $uuid})
        WITH n
        ORDER BY id(n)
        WITH collect(n) AS nodes
        WITH nodes[0] AS keep, nodes[1..] AS dups
        UNWIND dups AS dup
        DETACH DELETE dup
        RETURN count(*)
        """
        await graph.query(query, {"uuid": uuid})
        deleted += 1
    return deleted


async def cleanup_duplicate_relationships(graph) -> int:
    query = """
    MATCH ()-[r]->()
    WITH r.uuid AS uuid, collect(r) AS rels
    WHERE size(rels) > 1
    UNWIND tail(rels) AS dup
    DELETE dup
    RETURN COUNT(*)
    """
    result = await graph.query(query)
    count = result.result_set[0][0] if result.result_set else 0
    return count


async def run(args: argparse.Namespace) -> None:
    client = FalkorDB(host=args.host, port=args.port, username=args.username, password=args.password)
    graph = client.select_graph(args.graph)

    node_deleted = await cleanup_duplicate_nodes(graph)
    rel_deleted = await cleanup_duplicate_relationships(graph)

    print(f"Removed duplicate nodes: {node_deleted}")
    print(f"Removed duplicate relationships: {rel_deleted}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cleanup duplicate UUIDs in FalkorDB")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=6379)
    parser.add_argument("--graph", default="graphiti_migration")
    parser.add_argument("--username", default=None)
    parser.add_argument("--password", default=None)
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(run(parse_args()))
