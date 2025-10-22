#!/usr/bin/env python3
"""
Backfill name embeddings for CocoIndex-ingested groups.

Certain CocoIndex pipelines write nodes directly to FalkorDB without generating
`name_embedding` vectors, which breaks vector search and retrieval. This utility
repairs those records by generating embeddings via the configured Graphiti
embedder and updating the affected nodes (and, optionally, episodic documents).

Example:
    python3 scripts/backfill_cocoindex_embeddings.py \\
        --groups huly-coco bookstack-default \\
        --batch-size 100
"""

import argparse
import asyncio
import logging
import os
from pathlib import Path
from typing import Iterable, List

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = REPO_ROOT / ".env"

# Load workspace .env regardless of invocation location.
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)
else:  # fallback to default behaviour
    load_dotenv()

from graphiti_core.client_factory import GraphitiClientFactory
from graphiti_core.driver.falkordb_driver import FalkorDriver


logger = logging.getLogger("cocoindex-backfill")


def configure_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


async def _embed_batch(embedder, texts: List[str]) -> List[List[float]]:
    """Generate embeddings using the provided embedder, with graceful fallback."""
    if not texts:
        return []

    if hasattr(embedder, "create_batch"):
        try:
            embeddings = await embedder.create_batch(texts)
            if embeddings:
                return embeddings
        except NotImplementedError:
            logger.debug("Embedder does not support create_batch; falling back to single embeds.")
        except Exception as exc:  # pragma: no cover - defensive safeguard
            logger.warning("Batch embedding failed (%s); falling back to single embeds.", exc)

    embeddings: List[List[float]] = []
    for text in texts:
        embedding = await embedder.create(text)
        embeddings.append(embedding)
    return embeddings


async def _process_entity_batch(
    driver: FalkorDriver,
    embedder,
    group_id: str,
    batch_size: int,
    dry_run: bool,
) -> int:
    """Process a single batch of entities for the given group."""
    query = """
    MATCH (n:Entity {group_id: $group_id})
    WHERE (n.name_embedding IS NULL OR NOT EXISTS(n.name_embedding))
      AND n.name IS NOT NULL
      AND trim(n.name) <> ''
    RETURN n.uuid AS uuid, n.name AS name
    LIMIT $batch_size
    """
    records, _, _ = await driver.execute_query(query, group_id=group_id, batch_size=batch_size)

    if not records:
        return 0

    names = [record["name"] for record in records]
    uuids = [record["uuid"] for record in records]

    logger.debug("Embedding %d entity names for group %s", len(names), group_id)

    if dry_run:
        for uuid, name in zip(uuids, names, strict=True):
            logger.info("[DRY-RUN] Would embed entity %s (%s)", uuid, name)
        return len(records)

    embeddings = await _embed_batch(embedder, names)
    update_query = """
    MATCH (n:Entity {uuid: $uuid})
    SET n.name_embedding = vecf32($embedding)
    RETURN n.uuid
    """

    for uuid, embedding in zip(uuids, embeddings, strict=True):
        await driver.execute_query(update_query, uuid=uuid, embedding=embedding)

    return len(records)


async def _process_episode_batch(
    driver: FalkorDriver,
    embedder,
    group_id: str,
    batch_size: int,
    dry_run: bool,
) -> int:
    """Generate embeddings for episodic nodes when requested."""
    query = """
    MATCH (e:Episodic {group_id: $group_id})
    WHERE (e.name_embedding IS NULL OR NOT EXISTS(e.name_embedding))
    RETURN e.uuid AS uuid,
           e.name AS name,
           e.content AS content
    LIMIT $batch_size
    """
    records, _, _ = await driver.execute_query(query, group_id=group_id, batch_size=batch_size)

    if not records:
        return 0

    texts: List[str] = []
    uuids: List[str] = []
    for record in records:
        name = (record.get("name") or "").strip()
        content = (record.get("content") or "").strip()

        if name:
            text = name
        elif content:
            text = content[:2048]
        else:
            logger.debug("Skipping episodic %s: empty name/content", record.get("uuid"))
            continue

        uuids.append(record["uuid"])
        texts.append(text)

    if not uuids:
        return len(records)

    logger.debug("Embedding %d episodic titles/snippets for group %s", len(texts), group_id)

    if dry_run:
        for uuid, text in zip(uuids, texts, strict=True):
            preview = (text[:80] + "…") if len(text) > 80 else text
            logger.info("[DRY-RUN] Would embed episode %s (%s)", uuid, preview)
        return len(records)

    embeddings = await _embed_batch(embedder, texts)
    update_query = """
    MATCH (e:Episodic {uuid: $uuid})
    SET e.name_embedding = vecf32($embedding)
    RETURN e.uuid
    """

    for uuid, embedding in zip(uuids, embeddings, strict=True):
        await driver.execute_query(update_query, uuid=uuid, embedding=embedding)

    return len(records)


async def process_group(
    driver: FalkorDriver,
    embedder,
    group_id: str,
    batch_size: int,
    include_episodes: bool,
    dry_run: bool,
) -> None:
    """Process all missing embeddings for a specific group."""
    logger.info("=== Processing group %s ===", group_id)
    total_entities = 0
    total_episodes = 0

    while True:
        processed = await _process_entity_batch(driver, embedder, group_id, batch_size, dry_run)
        if processed == 0:
            break
        total_entities += processed

    if include_episodes:
        while True:
            processed = await _process_episode_batch(
                driver, embedder, group_id, batch_size, dry_run
            )
            if processed == 0:
                break
            total_episodes += processed

    logger.info(
        "Group %s: updated %d entities%s",
        group_id,
        total_entities,
        f", {total_episodes} episodes" if include_episodes else "",
    )


async def backfill_embeddings(args: argparse.Namespace) -> None:
    # Provide a sensible default embedder configuration if none is defined.
    openai_key = os.getenv("OPENAI_API_KEY")
    if not openai_key and not os.getenv("USE_OLLAMA"):
        if os.getenv("OLLAMA_BASE_URL") or os.getenv("OLLAMA_EMBEDDING_BASE_URL"):
            logger.debug("OPENAI_API_KEY not set; enabling Ollama embeddings for this session.")
            os.environ.setdefault("USE_OLLAMA", "true")
            os.environ.setdefault("USE_OLLAMA_EMBEDDINGS", "true")
        else:
            # Provide a sensible local default to avoid silent failures.
            os.environ.setdefault("USE_OLLAMA", "true")
            os.environ.setdefault("USE_OLLAMA_EMBEDDINGS", "true")
            os.environ.setdefault("OLLAMA_BASE_URL", "http://localhost:11434/v1")

    try:
        embedder = GraphitiClientFactory.create_embedder()
    except Exception as exc:  # pragma: no cover - defensive fallback
        raise RuntimeError(
            "Failed to create embedder client. Set OPENAI_API_KEY or configure "
            "USE_OLLAMA/USE_OLLAMA_EMBEDDINGS with a reachable Ollama endpoint."
        ) from exc

    if embedder is None:
        raise RuntimeError("Failed to create embedder client; check environment configuration.")

    driver = FalkorDriver(
        host=os.getenv("FALKORDB_HOST", "localhost"),
        port=int(os.getenv("FALKORDB_PORT", "6379")),
        database=os.getenv("FALKORDB_DATABASE", "graphiti_migration"),
    )

    try:
        for group_id in args.groups:
            await process_group(
                driver,
                embedder,
                group_id=group_id,
                batch_size=args.batch_size,
                include_episodes=args.include_episodes,
                dry_run=args.dry_run,
            )
    finally:
        await driver.close()


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill embeddings for CocoIndex-managed groups."
    )
    parser.add_argument(
        "--groups",
        nargs="+",
        required=True,
        help="Group IDs to process (e.g., huly-coco bookstack-default).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="How many nodes to process per batch (default: 100).",
    )
    parser.add_argument(
        "--include-episodes",
        action="store_true",
        help="Also backfill Episodic nodes (off by default).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be updated without writing changes.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging.",
    )
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> None:
    args = parse_args(argv)
    configure_logging(verbose=args.verbose)

    try:
        asyncio.run(backfill_embeddings(args))
    except KeyboardInterrupt:  # pragma: no cover - CLI convenience
        logger.warning("Interrupted by user.")


if __name__ == "__main__":
    main()
