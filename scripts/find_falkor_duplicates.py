#!/usr/bin/env python3
"""Scan FalkorDB for duplicate UUIDs on nodes and relationships.

Usage:
    python scripts/find_falkor_duplicates.py --host localhost --port 6379 --graph graphiti_migration

The script prints any UUID that appears more than once for a given label (nodes)
or relationship type. It helps diagnose duplicate data that causes downstream
unique-constraint violations (e.g., in the visualizer DuckDB store).
"""

from __future__ import annotations

import argparse
from typing import Iterable

from falkordb.asyncio import FalkorDB
import asyncio


async def query_dup_nodes(graph, label: str | None = None) -> list[tuple[str, int, list[str], list[str]]]:
    label_clause = f":{label}" if label else ""
    query = f"""
        MATCH (n{label_clause})
        WITH n.uuid AS uuid, collect(DISTINCT labels(n)) AS labels, collect(n.group_id) AS groups, COUNT(*) AS cnt
        WHERE cnt > 1
        RETURN uuid, cnt, labels, groups
        ORDER BY cnt DESC
    """
    result = await graph.query(query)
    return result.result_set


async def query_dup_relations(graph, rel_type: str | None = None) -> list[tuple[str, int, list[str], list[str]]]:
    type_clause = f":{rel_type}" if rel_type else ""
    query = f"""
        MATCH ()-[r{type_clause}]->()
        WITH r.uuid AS uuid, collect(DISTINCT type(r)) AS types, collect(r.group_id) AS groups, COUNT(*) AS cnt
        WHERE cnt > 1
        RETURN uuid, cnt, types, groups
        ORDER BY cnt DESC
    """
    result = await graph.query(query)
    return result.result_set


async def run(args: argparse.Namespace) -> None:
    client = FalkorDB(host=args.host, port=args.port, username=args.username, password=args.password)
    graph = client.select_graph(args.graph)

    print(f"Scanning FalkorDB graph `{args.graph}` for duplicate UUIDs...\n")

    node_labels: Iterable[str | None] = args.node_labels or (None,)
    rel_types: Iterable[str | None] = args.rel_types or (None,)

    found = False

    for label in node_labels:
        rows = await query_dup_nodes(graph, label)
        if not rows:
            continue
        found = True
        label_desc = label or "(any label)"
        print(f"Duplicate node UUIDs for label {label_desc}:")
        for uuid, cnt, labels, groups in rows:
            print(f"  {uuid} -> {cnt} instances | labels={labels} | groups={groups}")
        print()

    for rel in rel_types:
        rows = await query_dup_relations(graph, rel)
        if not rows:
            continue
        found = True
        rel_desc = rel or "(any type)"
        print(f"Duplicate relationship UUIDs for type {rel_desc}:")
        for uuid, cnt, types, groups in rows:
            print(f"  {uuid} -> {cnt} instances | types={types} | groups={groups}")
        print()

    if not found:
        print("No duplicate UUIDs detected with the provided filters.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Find duplicate UUIDs in FalkorDB")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=6379)
    parser.add_argument("--graph", default="graphiti_migration")
    parser.add_argument("--username", default=None)
    parser.add_argument("--password", default=None)
    parser.add_argument("--node-labels", nargs="*", help="Optional list of node labels to check (defaults to all)")
    parser.add_argument("--rel-types", nargs="*", help="Optional list of relationship types to check (defaults to all)")
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(run(parse_args()))
