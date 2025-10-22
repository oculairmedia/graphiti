# CocoIndex Embedding Remediation & Integration Guide

**Audience:** CocoIndex ingestion developers (no direct access to Graphiti repo required)  
**Last updated:** 2025‑10‑09  
**Maintainer contact:** Graphiti ingestion team (graphiti@zep.com)

---

## 1. Problem Overview

Recent CocoIndex runs write entities and episodic documents directly into the Graphiti FalkorDB graph. Those records do **not** include `name_embedding` (and sometimes `fact_embedding`) vectors, so semantic search, dedupe, and ranking pipelines ignore them even though the nodes exist.

### Impact Snapshot (Oct‑2025)

| Group ID            | Entity nodes | Missing `name_embedding` | Episodic nodes | Missing episodic `name_embedding` |
|---------------------|-------------:|--------------------------:|---------------:|-----------------------------------:|
| `huly-coco`         | 68           | 68                        | 40             | 40                                 |
| `bookstack-default` | 1,740        | 1,691                     | 153            | 153 (after fix → 0)                |
| `bookstack_content` | 4            | 1                         | 6              | 6 (after fix → 0)                  |

Verification query (any FalkorDB shell):
```bash
redis-cli GRAPH.QUERY graphiti_migration "
  MATCH (n:Entity {group_id:'huly-coco'})
  WHERE n.name_embedding IS NULL
  RETURN count(n)
"
```

Without embeddings, Graphiti’s `/search` endpoint, centrality updates, and dedupe tooling skip the CocoIndex nodes entirely.

---

## 2. One‑Time Backfill for Existing Data

The script below can be run standalone (no repo checkout needed) to generate missing embeddings for the affected groups. It reads configuration from a local `.env` file and will work on any machine that can reach FalkorDB and the embedding endpoint.

### 2.1 Setup Environment File
Create `.env` in the working directory (same folder where you will save the script) and populate it with your embedder endpoint. Example using the shared Ollama instance:
```bash
cat <<'EOF' > .env
USE_OLLAMA=true
USE_OLLAMA_EMBEDDINGS=true
OLLAMA_BASE_URL=http://192.168.50.80:11434/v1
OLLAMA_EMBEDDING_BASE_URL=http://192.168.50.80:11434/v1
OLLAMA_EMBEDDING_MODEL=dengcao/Qwen3-Embedding-4B:Q4_K_M
FALKORDB_HOST=falkordb
FALKORDB_PORT=6379
FALKORDB_DATABASE=graphiti_migration
EOF
```
Adjust host/port/model as needed. If you prefer OpenAI, set `OPENAI_API_KEY` and either leave `USE_OLLAMA=false` or omit it (OpenAI becomes the default).

### 2.2 Save the Backfill Script
Copy the script below into `backfill_cocoindex_embeddings.py`.
```python
#!/usr/bin/env python3
"""
CocoIndex backfill utility (standalone).
Generates missing name embeddings for Entity/Episodic nodes written directly by
the CocoIndex pipeline.

Usage examples:
    python3 backfill_cocoindex_embeddings.py \
        --groups huly-coco bookstack-default bookstack_content \
        --batch-size 200 --include-episodes

    python3 backfill_cocoindex_embeddings.py \
        --groups huly-coco --dry-run --verbose
"""

import argparse
import asyncio
import logging
import os
from pathlib import Path
from typing import Iterable, List

from dotenv import load_dotenv
from openai import AsyncOpenAI

# ---------------------------------------------------------------------------
# Environment bootstrap
# ---------------------------------------------------------------------------
WORK_DIR = Path(__file__).resolve().parent
ENV_PATH = WORK_DIR / ".env"
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)
else:
    load_dotenv()

logger = logging.getLogger("cocoindex-backfill")

# ---------------------------------------------------------------------------
# Minimal FalkorDB driver (async) using redis-py
# ---------------------------------------------------------------------------
import redis.asyncio as redis

class FalkorDriver:
    def __init__(self, host: str, port: int, database: str):
        self.host = host
        self.port = port
        self.database = database
        self._client = redis.Redis(host=self.host, port=self.port, decode_responses=True)

    async def execute_query(self, cypher: str, **params):
        """
        Execute a GRAPH.QUERY call and return (records, header, _) to mimic Graphiti.
        """
        statement = [cypher, params] if params else [cypher]
        raw = await self._client.execute_command(
            "GRAPH.QUERY", self.database, *statement, "--compact"
        )
        header = raw[0] if raw and isinstance(raw[0], list) else []
        rows = raw[1] if len(raw) > 1 and isinstance(raw[1], list) else []

        records = []
        for row in rows:
            record = {}
            for idx, col in enumerate(header):
                col_name = col if isinstance(col, str) else col[1]
                record[col_name] = row[idx]
            records.append(record)
        return records, header, None

    async def close(self):
        await self._client.close()

# ---------------------------------------------------------------------------
# Embedder helpers
# ---------------------------------------------------------------------------
def _resolve_embedder() -> AsyncOpenAI:
    """
    Create an AsyncOpenAI client targeting either Ollama or OpenAI based on .env.
    """
    use_ollama = os.getenv("USE_OLLAMA", "false").lower() == "true"

    if use_ollama:
        base_url = os.getenv("OLLAMA_EMBEDDING_BASE_URL") or os.getenv("OLLAMA_BASE_URL")
        if not base_url:
            raise RuntimeError("OLLAMA_BASE_URL or OLLAMA_EMBEDDING_BASE_URL must be set when USE_OLLAMA=true")
        api_key = os.getenv("OLLAMA_EMBEDDING_API_KEY", "ollama")
        return AsyncOpenAI(base_url=base_url, api_key=api_key)

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set and USE_OLLAMA=false; cannot create embedder client")
    base_url = os.getenv("OPENAI_BASE_URL")
    return AsyncOpenAI(api_key=api_key, base_url=base_url)

async def _embed_texts(client: AsyncOpenAI, texts: List[str], model: str) -> List[List[float]]:
    """
    Generate embeddings, using batch if the backend supports it.
    """
    if not texts:
        return []

    try:
        result = await client.embeddings.create(model=model, input=texts)
        return [item.embedding for item in result.data]
    except Exception as batch_err:
        logger.warning("Batch embed failed (%s); falling back to single requests.", batch_err)

    embeddings: List[List[float]] = []
    for text in texts:
        result = await client.embeddings.create(model=model, input=[text])
        embeddings.append(result.data[0].embedding)
    return embeddings

# ---------------------------------------------------------------------------
# Core backfill logic
# ---------------------------------------------------------------------------
async def _process_entities(driver: FalkorDriver, embed_client: AsyncOpenAI, group_id: str,
                            model: str, batch_size: int, dry_run: bool) -> int:
    cypher = """
    MATCH (n:Entity {group_id: $group_id})
    WHERE (n.name_embedding IS NULL OR NOT EXISTS(n.name_embedding))
      AND n.name IS NOT NULL AND trim(n.name) <> ''
    RETURN n.uuid AS uuid, n.name AS name
    LIMIT $batch_size
    """
    records, _, _ = await driver.execute_query(cypher, group_id=group_id, batch_size=batch_size)
    if not records:
        return 0

    uuids = [rec["uuid"] for rec in records]
    names = [rec["name"] for rec in records]

    if dry_run:
        for uuid, name in zip(uuids, names, strict=True):
            logger.info("[DRY-RUN] would embed entity %s (%s)", uuid, name)
        return len(records)

    embeddings = await _embed_texts(embed_client, names, model)
    update = """
    MATCH (n:Entity {uuid: $uuid})
    SET n.name_embedding = vecf32($embedding)
    RETURN n.uuid
    """
    for uuid, embedding in zip(uuids, embeddings, strict=True):
        await driver.execute_query(update, uuid=uuid, embedding=embedding)
    return len(records)

async def _process_episodes(driver: FalkorDriver, embed_client: AsyncOpenAI, group_id: str,
                             model: str, batch_size: int, dry_run: bool) -> int:
    cypher = """
    MATCH (e:Episodic {group_id: $group_id})
    WHERE (e.name_embedding IS NULL OR NOT EXISTS(e.name_embedding))
    RETURN e.uuid AS uuid, coalesce(nullif(trim(e.name), ''), e.content) AS text
    LIMIT $batch_size
    """
    records, _, _ = await driver.execute_query(cypher, group_id=group_id, batch_size=batch_size)
    if not records:
        return 0

    uuids, texts = [], []
    for rec in records:
        text = (rec.get("text") or "").strip()
        if not text:
            continue
        uuids.append(rec["uuid"])
        texts.append(text[:2048])  # safety truncate

    if dry_run:
        for uuid, text in zip(uuids, texts, strict=True):
            preview = text[:80] + ("…" if len(text) > 80 else "")
            logger.info("[DRY-RUN] would embed episode %s (%s)", uuid, preview)
        return len(uuids)

    embeddings = await _embed_texts(embed_client, texts, model)
    update = """
    MATCH (e:Episodic {uuid: $uuid})
    SET e.name_embedding = vecf32($embedding)
    RETURN e.uuid
    """
    for uuid, embedding in zip(uuids, embeddings, strict=True):
        await driver.execute_query(update, uuid=uuid, embedding=embedding)
    return len(uuids)

async def backfill(groups: List[str], batch_size: int, include_episodes: bool,
                   dry_run: bool, verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    embed_model = os.getenv("OLLAMA_EMBEDDING_MODEL") or os.getenv("OPENAI_EMBEDDING_MODEL") or "text-embedding-3-small"
    embed_client = _resolve_embedder()

    driver = FalkorDriver(
        host=os.getenv("FALKORDB_HOST", "localhost"),
        port=int(os.getenv("FALKORDB_PORT", "6379")),
        database=os.getenv("FALKORDB_DATABASE", "graphiti_migration"),
    )

    try:
        for group in groups:
            logger.info("=== Processing group %s ===", group)
            entity_total = episode_total = 0
            while True:
                processed = await _process_entities(driver, embed_client, group, embed_model, batch_size, dry_run)
                if processed == 0:
                    break
                entity_total += processed

            if include_episodes:
                while True:
                    processed = await _process_episodes(driver, embed_client, group, embed_model, batch_size, dry_run)
                    if processed == 0:
                        break
                    episode_total += processed

            logger.info("Group %s: updated %d entities%s",
                        group, entity_total,
                        f", {episode_total} episodes" if include_episodes else "")
    finally:
        await driver.close()

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill CocoIndex embeddings.")
    parser.add_argument("--groups", nargs="+", required=True, help="Group IDs to fix (e.g., huly-coco bookstack-default).")
    parser.add_argument("--batch-size", type=int, default=100, help="Batch size for processing (default 100).")
    parser.add_argument("--include-episodes", action="store_true", help="Also backfill Episodic nodes.")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without writing changes.")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging.")
    return parser.parse_args()

def main() -> None:
    args = parse_args()
    asyncio.run(backfill(
        groups=args.groups,
        batch_size=args.batch_size,
        include_episodes=args.include_episodes,
        dry_run=args.dry_run,
        verbose=args.verbose,
    ))

if __name__ == "__main__":
    main()
```
Make the script executable if desired: `chmod +x backfill_cocoindex_embeddings.py`.

### 2.3 Run the Backfill
```bash
# Dry run to inspect
python3 backfill_cocoindex_embeddings.py \
  --groups huly-coco bookstack-default bookstack_content \
  --dry-run --verbose

# Execute (entities + episodic)
python3 backfill_cocoindex_embeddings.py \
  --groups huly-coco bookstack-default bookstack_content \
  --batch-size 200 --include-episodes
```

### 2.4 Verify
```bash
redis-cli GRAPH.QUERY graphiti_migration "
  MATCH (n:Entity {group_id:'bookstack-default'})
  WHERE n.name_embedding IS NULL
  RETURN count(n)
"
```
A successful run should return `0`. Repeat for `huly-coco`, `bookstack_content`, and episodic nodes (replace `Entity` with `Episodic`).

---

## 3. Forward Fix: Generating Embeddings at Ingestion Time

Backfilling is a temporary repair. Update the CocoIndex ingestion pipeline so future writes include embeddings **before** writing to FalkorDB.

1. **Use Graphiti ingestion APIs** (`POST /messages` or `/entity-node`): Graphiti workers handle embedding creation automatically. Preferred when latency is acceptable.
2. **If direct FalkorDB writes are required**, call the embedder directly (Ollama/OpenAI) before executing Cypher. Ensure you wrap vectors with `vecf32($embedding)` and the dimension matches `EMBEDDING_DIMENSION`.

Checklist for CocoIndex developers:
- [ ] Every `MERGE (n:Entity …)` sets `n.name_embedding`.
- [ ] Every `MERGE (e:Episodic …)` sets `e.name_embedding`.
- [ ] Relationship facts requiring embeddings set `fact_embedding` the same way.
- [ ] Add unit/integration tests verifying embeddings are present post-ingestion.
- [ ] Document the embedder dependency in deployment runbooks.

---

## 4. Monitoring & Follow‑Up

1. Add periodic health checks to confirm the embedder endpoint responds (avoid silent regressions).
2. Watch Graphiti logs/metrics for ingestion warnings or DLQ spikes.
3. After pipeline changes, run the Cypher verification queries again to ensure no new NULL embeddings appear.

---

## 5. Support
- **Graphiti ingestion team:** graphiti@zep.com
- Mention this document (“CocoIndex Embedding Remediation & Integration Guide”) when asking for assistance so on-call engineers can pick up context immediately.
