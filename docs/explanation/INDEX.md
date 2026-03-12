# Explanations Index

> Architecture concepts and design decisions. Understanding-oriented.

## Core Architecture

| File | Keywords | Description |
|------|----------|-------------|
| [architecture.md](architecture.md) | `architecture`, `services`, `data-flow`, `components` | System architecture overview |
| [ingestion-pipeline.md](ingestion-pipeline.md) | `ingestion`, `pipeline`, `extraction`, `resolution`, `temporal` | How data flows through |
| [consolidation-system.md](consolidation-system.md) | `consolidation`, `prune`, `merge`, `sleep`, `nightly` | Graph cleanup and optimization |

## Data Models

| File | Keywords | Description |
|------|----------|-------------|
| [bi-temporal-model.md](bi-temporal-model.md) | `temporal`, `t_valid_at`, `t_invalid_at`, `history` | Bi-temporal tracking |
| [vector-search.md](vector-search.md) | `vector`, `hnsw`, `similarity`, `search`, `embedding` | Vector search mechanics |

## Algorithms

| File | Keywords | Description |
|------|----------|-------------|
| [centrality.md](centrality.md) | `centrality`, `pagerank`, `eigenvector`, `betweenness` | Graph centrality algorithms |

---

## Quick Overview

### Service Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   Frontend  │────▶│  Visualizer  │────▶│  FalkorDB   │
│  (React)    │     │   (Rust)     │     │  (Storage)  │
└─────────────┘     └──────────────┘     └─────────────┘
                            │
                            ▼
                     ┌──────────────┐
                     │  Graph API   │
                     │  (FastAPI)   │
                     └──────────────┘
                            │
                            ▼
                     ┌──────────────┐
                     │   Temporal   │
                     │  (Workflows) │
                     └──────────────┘
```

### Ingestion Pipeline

```
Episode → Extract Nodes → Resolve Nodes → Extract Edges → Persist
              │               │               │
              └───────────────┴───────────────┘
                          LLM Calls
```

### Consolidation Phases

1. **PRUNE**: Remove orphans, junk entities, old episodic nodes
2. **MERGE**: Deduplicate entities by name and semantic similarity
3. **ENRICH**: Regenerate summaries, backfill embeddings, recalculate centrality

---

> **Tip**: For step-by-step guides, see [../how-to/](../how-to/). For API details, see [../reference/](../reference/).
