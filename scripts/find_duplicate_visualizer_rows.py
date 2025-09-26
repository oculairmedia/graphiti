#!/usr/bin/env python3
"""Inspect DuckDB store of the graph visualizer for duplicate rows.

The script connects to the DuckDB database used by graphiti-graph-visualizer-rust,
scans the entity and edge tables (deduped views if available) and reports any
primary-key duplicates that would trigger constraint violations.

Run from repo root:
    python scripts/find_duplicate_visualizer_rows.py --db /path/to/graph.db
"""

from __future__ import annotations

import argparse
import os
import duckdb
from pathlib import Path

DEFAULT_DB_PATH = "/var/lib/duckdb/graph.db"

ENTITY_TABLES = [
    "entities",
    "nodes",
    "entity_nodes",
]

EDGE_TABLES = [
    "edges",
    "relations",
]


def table_exists(conn: duckdb.DuckDBPyConnection, table: str) -> bool:
    try:
        conn.execute(f"DESCRIBE {table}")
    except duckdb.CatalogException:
        return False
    return True


def find_duplicates(conn: duckdb.DuckDBPyConnection, table: str, key: str = "uuid") -> list[tuple]:
    query = f"""
        SELECT {key}, COUNT(*) AS cnt
        FROM {table}
        GROUP BY {key}
        HAVING COUNT(*) > 1
        ORDER BY cnt DESC
    """
    return conn.execute(query).fetchall()


def main() -> None:
    parser = argparse.ArgumentParser(description="Find duplicate rows in DuckDB visualizer store")
    parser.add_argument("--db", default=os.getenv("DUCKDB_PATH", DEFAULT_DB_PATH), help="Path to DuckDB database")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        raise SystemExit(f"DuckDB database not found at {db_path}")

    conn = duckdb.connect(str(db_path), read_only=True)

    print(f"Inspecting {db_path}\n")

    any_dup = False

    for table in ENTITY_TABLES + EDGE_TABLES:
        if not table_exists(conn, table):
            continue
        duplicates = find_duplicates(conn, table)
        if duplicates:
            any_dup = True
            print(f"Duplicates in table `{table}` (key = uuid):")
            for uuid, count in duplicates:
                print(f"  {uuid} -> {count} rows")
            print()

    if not any_dup:
        print("No duplicate UUIDs detected in known tables.")


if __name__ == "__main__":
    main()
