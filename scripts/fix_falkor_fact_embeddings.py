#!/usr/bin/env python3
"""Fix RELATES_TO.fact_embedding values stored as plain lists in FalkorDB.

The ingestion pipeline expects relationship embeddings to be stored as VectorF32
so Falkor's `vec.cosineDistance` can operate on them. During past migrations we
persisted some edges with raw Python lists, which now trigger type mismatches
whenever similarity queries run. This script scans the graph for relationships
whose `fact_embedding` is still a list and rewrites them using `vecf32(...)`.

Usage:
    python scripts/fix_falkor_fact_embeddings.py \
        --host localhost --port 6379 --database graphiti_migration

Connection details default to the same environment variables used by the worker:
    FALKORDB_HOST, FALKORDB_PORT, FALKORDB_USERNAME, FALKORDB_PASSWORD,
    FALKORDB_DATABASE.

The script is idempotent: already-normalized edges are skipped after the type
check. Progress is logged every batch so operators can monitor long runs.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
from typing import Any

from falkordb.asyncio import FalkorDB

# Configure logging for straightforward CLI usage
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Normalize Falkor relationship embeddings to VectorF32")
    parser.add_argument("--host", default=os.getenv("FALKORDB_HOST", "localhost"), help="FalkorDB host")
    parser.add_argument("--port", type=int, default=int(os.getenv("FALKORDB_PORT", "6379")), help="FalkorDB port")
    parser.add_argument("--username", default=os.getenv("FALKORDB_USERNAME"), help="FalkorDB username")
    parser.add_argument("--password", default=os.getenv("FALKORDB_PASSWORD"), help="FalkorDB password")
    parser.add_argument(
        "--database",
        default=os.getenv("FALKORDB_DATABASE", "graphiti_migration"),
        help="FalkorDB graph / database name",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=200,
        help="Number of relationships to process per batch fetch",
    )
    return parser.parse_args()


async def fetch_batch(graph, cursor: str | None, limit: int) -> tuple[list[dict[str, Any]], str | None]:
    """Fetch a batch of relationships with embeddings, using a UUID cursor."""
    if cursor:
        query = (
            "MATCH ()-[e:RELATES_TO]->()\n"
            "WHERE e.fact_embedding IS NOT NULL AND e.uuid > $cursor\n"
            "RETURN e.uuid AS uuid, e.fact_embedding AS embedding\n"
            "ORDER BY e.uuid\n"
            "LIMIT $limit"
        )
        params = {"cursor": cursor, "limit": limit}
    else:
        query = (
            "MATCH ()-[e:RELATES_TO]->()\n"
            "WHERE e.fact_embedding IS NOT NULL\n"
            "RETURN e.uuid AS uuid, e.fact_embedding AS embedding\n"
            "ORDER BY e.uuid\n"
            "LIMIT $limit"
        )
        params = {"limit": limit}

    result = await graph.query(query, params)
    header = [h[1] for h in result.header]
    rows = [dict(zip(header, row)) for row in result.result_set]

    next_cursor = rows[-1]["uuid"] if rows else None
    return rows, next_cursor


async def normalize_embeddings(graph, host: str, port: int, database: str, batch_size: int) -> None:
    logger.info(
        "Connecting to FalkorDB at %s:%s (graph=%s) to normalize RELATES_TO.fact_embedding",
        host,
        port,
        database,
    )

    processed = 0
    converted = 0
    cursor: str | None = None

    while True:
        rows, cursor = await fetch_batch(graph, cursor, batch_size)
        if not rows:
            break

        for row in rows:
            embedding = row["embedding"]
            uuid = row["uuid"]
            processed += 1

            if isinstance(embedding, list):
                await graph.query(
                    "MATCH ()-[e:RELATES_TO {uuid: $uuid}]->()\n"
                    "SET e.fact_embedding = vecf32($embedding)",
                    {"uuid": uuid, "embedding": embedding},
                )
                converted += 1
            # Skip relationships that already store VectorF32

        logger.info(
            "Processed %d relationships so far (converted %d).%s",
            processed,
            converted,
            " Continuing..." if cursor else "",
        )

        if cursor is None:
            break

    logger.info("Done. Total processed: %d, converted: %d", processed, converted)


async def main() -> None:
    args = parse_args()
    client = FalkorDB(host=args.host, port=args.port, username=args.username, password=args.password)
    graph = client.select_graph(args.database)

    try:
        await normalize_embeddings(graph, args.host, args.port, args.database, args.batch_size)
    finally:
        if hasattr(client, "aclose"):
            await client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
