"""Cursor-based FalkorDB → Neo4j migration with MERGE idempotency."""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from falkordb import FalkorDB
from neo4j import AsyncGraphDatabase

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("falkor_to_neo4j_cursor")

EMBEDDING_KEYS = {
    "name_embedding",
    "summary_embedding",
    "fact_embedding",
    "content_embedding",
}

SKIP_KEYS = {"_id", "internal_id"}


@dataclass
class MigrationConfig:
    falkordb_host: str = "localhost"
    falkordb_port: int = 6379
    falkordb_user: Optional[str] = None
    falkordb_password: Optional[str] = None
    falkordb_graph: str = "graphiti_migration"

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "demodemo"

    node_batch_size: int = 1000
    rel_batch_size: int = 500


def should_skip_property(key: str, value: Any) -> bool:
    if key in SKIP_KEYS:
        return True
    if key in EMBEDDING_KEYS:
        return False
    if value is None:
        return True
    if isinstance(value, dict):
        return True
    if isinstance(value, list) and len(value) > 5000:
        return True
    return False


def normalize_properties(props: Dict[str, Any]) -> Dict[str, Any]:
    normalized: Dict[str, Any] = {}
    for key, value in props.items():
        if should_skip_property(key, value):
            continue
        normalized[key] = value
    return normalized


async def stream_nodes(config: MigrationConfig, falkor_graph: Any, neo4j_driver: Any) -> int:
    logger.info("Streaming nodes from FalkorDB → Neo4j")

    query = """
    MATCH (n)
    RETURN n.uuid as uuid, labels(n) as labels, properties(n) as props
    ORDER BY n.uuid
    """

    result = falkor_graph.query(query)
    rows = result.result_set if result and result.result_set else []

    async with neo4j_driver.session() as session:
        processed = 0
        for row in rows:
            uuid = row[0]
            labels = row[1] or []
            props = normalize_properties(row[2] or {})

            if not uuid or not labels:
                continue

            primary_label = labels[0]

            params = {"uuid": uuid, **{k: v for k, v in props.items() if k != "uuid"}}
            set_clause = ", ".join(f"n.{k} = ${k}" for k in props if k != "uuid")
            cypher = f"""
            MERGE (n:{primary_label} {{uuid: $uuid}})
            SET {set_clause}
            """ if set_clause else f"MERGE (n:{primary_label} {{uuid: $uuid}})"

            await session.run(cypher, params)

            processed += 1
            if processed % 500 == 0:
                logger.info("Nodes merged: %s", processed)

    logger.info("Finished node merge: %s nodes", processed)
    return processed


async def stream_relationships(config: MigrationConfig, falkor_graph: Any, neo4j_driver: Any) -> int:
    logger.info("Streaming relationships with UUID cursor")

    # Count for progress reference
    count_result = falkor_graph.query("MATCH ()-[r]->() RETURN count(r) as total")
    total = count_result.result_set[0][0] if count_result.result_set else 0
    logger.info("Total relationships in FalkorDB: %s", total)

    last_uuid: Optional[str] = None
    processed = 0
    batch_size = config.rel_batch_size

    async with neo4j_driver.session() as session:
        while True:
            where_clauses = ["s.uuid IS NOT NULL", "t.uuid IS NOT NULL"]
            params: Dict[str, Any] = {}
            if last_uuid:
                where_clauses.append("r.uuid > $last_uuid")
                params["last_uuid"] = last_uuid

            where_clause = "WHERE " + " AND ".join(where_clauses)
            rel_query = f"""
            MATCH (s)-[r]->(t)
            {where_clause}
            RETURN r.uuid as uuid, s.uuid as source_uuid, t.uuid as target_uuid, type(r) as rel_type, properties(r) as props
            ORDER BY r.uuid
            LIMIT {batch_size}
            """

            try:
                rel_result = falkor_graph.query(rel_query, params=params)
            except Exception as exc:
                logger.error(
                    "Failed fetching batch last_uuid=%s size=%s: %s",
                    last_uuid,
                    batch_size,
                    exc,
                )
                if batch_size > 25:
                    batch_size = max(25, batch_size // 2)
                    logger.info("Reducing batch size to %s", batch_size)
                    continue
                raise

            rows = rel_result.result_set if rel_result and rel_result.result_set else []
            if not rows:
                break

            for row in rows:
                rel_uuid, source_uuid, target_uuid, rel_type, props = row
                if not rel_uuid or not source_uuid or not target_uuid:
                    continue

                props = normalize_properties(props or {})

                cypher = f"""
                MATCH (s {{uuid: $source_uuid}}), (t {{uuid: $target_uuid}})
                MERGE (s)-[r:{rel_type} {{uuid: $uuid}}]->(t)
                SET r += $props
                """

                parameters = {
                    "source_uuid": source_uuid,
                    "target_uuid": target_uuid,
                    "uuid": rel_uuid,
                    "props": {k: v for k, v in props.items() if k != "uuid"},
                }

                await session.run(cypher, parameters)
                processed += 1

            last_uuid = rows[-1][0]
            if total:
                logger.info("Relationships merged: %s/%s (%.1f%%)", processed, total, processed / total * 100)
            else:
                logger.info("Relationships merged so far: %s", processed)

    logger.info("Finished relationship merge: %s relationships", processed)
    return processed


async def main():
    config = MigrationConfig()

    falkor_db = FalkorDB(
        host=config.falkordb_host,
        port=config.falkordb_port,
        username=config.falkordb_user,
        password=config.falkordb_password,
    )
    falkor_graph = falkor_db.select_graph(config.falkordb_graph)

    neo4j_driver = AsyncGraphDatabase.driver(
        config.neo4j_uri,
        auth=(config.neo4j_user, config.neo4j_password),
    )

    try:
        node_total = await stream_nodes(config, falkor_graph, neo4j_driver)
        rel_total = await stream_relationships(config, falkor_graph, neo4j_driver)
        logger.info("Migration complete: %s nodes, %s relationships", node_total, rel_total)
    finally:
        await neo4j_driver.close()


if __name__ == "__main__":
    asyncio.run(main())
