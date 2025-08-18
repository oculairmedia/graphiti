# Graphiti Architecture Overview

## Core System Architecture

### 1. **Core Library (`graphiti_core/`)**
The heart of Graphiti - a Python framework for building temporally-aware knowledge graphs.

#### Main Components:
- **`graphiti.py`**: Main orchestrator class
  - `add_episode()`: Ingests new episodic data
  - `add_episode_bulk()`: Batch ingestion
  - `search()`: Hybrid search functionality
  - `build_communities()`: Community detection
  - `build_indices_and_constraints()`: Database optimization

#### Data Models:
- **Nodes**: 
  - `EntityNode`: Core knowledge entities
  - `EpisodicNode`: Time-stamped events
  - `CommunityNode`: Clustered entity groups
- **Edges**:
  - `EntityEdge`: Relationships between entities
  - `EpisodicEdge`: Temporal relationships

#### Storage Drivers (`driver/`):
- **Neo4j Driver**: Primary graph database (v5.26+)
- **FalkorDB Driver**: Alternative Redis-based graph DB

### 2. **LLM Integration (`llm_client/`)**
Supports multiple LLM providers for entity extraction and reasoning:
- OpenAI (primary, with structured output)
- Anthropic Claude
- Google Gemini
- Groq
- Ollama (local models)

#### Prompt Templates (`prompts/`):
- `extract_nodes.py`: Entity extraction from text
- `extract_edges.py`: Relationship extraction
- `dedupe_nodes.py`: Entity deduplication
- `dedupe_edges.py`: Relationship deduplication
- `summarize_nodes.py`: Entity summarization

### 3. **Search System (`search/`)**

#### Hybrid Search Methods:
- **Fulltext Search**: BM25 keyword matching
- **Vector Similarity**: Semantic search using embeddings
- **Graph Traversal**: BFS-based exploration
- **Community Search**: Cluster-based retrieval

#### Reranking Strategies:
- **RRF (Reciprocal Rank Fusion)**: Combines multiple rankings
- **MMR (Maximal Marginal Relevance)**: Diversity-aware ranking
- **Cross-Encoder**: Neural reranking
- **Node Distance**: Graph proximity scoring

### 4. **API Server (`server/`)**

FastAPI-based REST service with endpoints:
- `/ingest/*`: Data ingestion endpoints
- `/search/*`: Search and retrieval
- `/nodes/*`: Node management
- `/centrality/*`: Centrality metrics
- `/metrics/*`: System metrics

#### Key Features:
- WebSocket support for real-time updates
- Webhook system for event notifications
- Redis-based caching layer
- CORS support for web clients

### 5. **Rust Components**

#### Search Service (`graphiti-search-rs/`):
High-performance search engine in Rust:
- Direct FalkorDB integration
- Ollama embedding generation
- Parallel query execution
- Optimized for low latency

#### Visualization Server (`graph-visualizer-rust/`):
WebGL-based graph visualization:
- Actix-web server
- Cosmograph integration for GPU rendering
- Real-time WebSocket updates
- DuckDB for analytics
- Arrow format for efficient data transfer

### 6. **Frontend (`frontend/`)**

React + TypeScript application:
- **Cosmograph**: GPU-accelerated graph rendering
- **shadcn/ui**: Modern UI components
- **WebSocket**: Real-time graph updates
- **DuckDB WASM**: Client-side analytics

### 7. **Infrastructure**

#### Docker Services:
```yaml
- graphiti-api: Python API server
- graphiti-search-rs: Rust search service
- graph-visualizer-rust: Visualization server
- graphiti-frontend: React UI
- falkordb: Graph database
- nginx: Reverse proxy
```

## Data Flow

1. **Ingestion Pipeline**:
   ```
   Raw Episode → LLM Extraction → Entity/Edge Resolution → Graph Storage
   ```

2. **Search Pipeline**:
   ```
   Query → Embedding → Hybrid Search → Reranking → Results
   ```

3. **Visualization Pipeline**:
   ```
   FalkorDB → Rust Server → WebSocket → Frontend → Cosmograph → GPU
   ```

## Key Innovations

1. **Bi-temporal Model**: Tracks both event time and knowledge validity
2. **Hybrid Retrieval**: Combines semantic, keyword, and graph methods
3. **Incremental Updates**: No batch recomputation needed
4. **Community Detection**: Automatic clustering of related entities
5. **Multi-LLM Support**: Flexible provider switching

## Performance Optimizations

- Rust services for hot paths (search, visualization)
- Redis caching for frequent queries
- Arrow format for data transfer
- GPU acceleration for rendering
- Parallel processing with semaphores

## Current Limitations

- Vector search in FalkorDB requires workarounds
- Layout algorithms limited to force-directed
- Scores not yet returned from Rust search
- Frontend bundle size needs optimization

## Future Enhancements

- Native vector search in FalkorDB
- Additional layout algorithms
- Relevance scoring improvements
- Real-time collaborative features
- Enhanced temporal analytics