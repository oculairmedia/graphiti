# Graphiti Project Analysis - Complete Architecture Review

## Executive Summary

### Project Overview
Graphiti is a sophisticated **temporal knowledge graph platform** designed for AI agents and dynamic data environments. Built by Zep Software, it provides real-time incremental updates to knowledge graphs without batch recomputation, making it ideal for continuously evolving data scenarios.

### Core Capabilities
- **Bi-temporal data model** with explicit tracking of event occurrence times
- **Hybrid retrieval** combining semantic embeddings, keyword search (BM25), and graph traversal
- **Multi-database support** with Neo4j (persistent) and FalkorDB (in-memory cache)
- **High-performance visualization** using WebGL-based Cosmograph library
- **AI-powered ingestion** with support for multiple LLM providers
- **Real-time synchronization** between database backends
- **MCP integration** for AI assistant compatibility

### Technology Stack
- **Backend**: Python (FastAPI), Rust (Actix-web)
- **Frontend**: React, TypeScript, Vite, shadcn-ui, Cosmograph
- **Databases**: Neo4j 5.26+, FalkorDB (Redis-based)
- **LLM Providers**: Cerebras, OpenAI, Anthropic, Ollama, Chutes AI, Groq, Google
- **Infrastructure**: Docker Compose, Nginx, Redis
- **Visualization**: WebGL, Cosmograph, D3.js patterns

---

## System Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         Frontend Layer                        │
│  React UI (8084) ←→ Cosmograph Visualization                 │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────┐
│                     API & Service Layer                      │
│                                                              │
│  ┌──────────────┐  ┌─────────────┐  ┌──────────────┐      │
│  │ Python API   │  │ Rust Viz    │  │ MCP Server   │      │
│  │ (8003)       │  │ Server(3000)│  │ (3010)       │      │
│  └──────────────┘  └─────────────┘  └──────────────┘      │
│                                                              │
│  ┌──────────────┐  ┌─────────────┐  ┌──────────────┐      │
│  │ Centrality   │  │ Search      │  │ Queue Service│      │
│  │ Service(3003)│  │ Service(3004)│  │ (8093)       │      │
│  └──────────────┘  └─────────────┘  └──────────────┘      │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────┐
│                      Data Layer                              │
│                                                              │
│  ┌──────────────────────┐    ┌──────────────────────┐      │
│  │ Neo4j (7474/7687)    │←──→│ FalkorDB (6379)      │      │
│  │ Persistent Storage   │    │ In-Memory Cache      │      │
│  └──────────────────────┘    └──────────────────────┘      │
│                     ↑                                        │
│            ┌────────┴────────┐                              │
│            │ Sync Service    │                              │
│            │ (8082/8083)     │                              │
│            └─────────────────┘                              │
└──────────────────────────────────────────────────────────────┘
```

### Data Flow Patterns

1. **Ingestion Flow**: 
   - Client → Python API → LLM Processing → Graph Extraction → Database Storage → Webhook Notifications

2. **Query Flow**:
   - Client → Rust Search Service → FalkorDB → Embedding Search + Graph Traversal → Results

3. **Visualization Flow**:
   - React UI → Rust Viz Server → FalkorDB → Arrow Format → WebGL Rendering

4. **Sync Flow**:
   - Neo4j (source) → Sync Service → FalkorDB (target) → Auto-recovery on restart

---

## Core Components Analysis

### 1. graphiti_core/ - Main Library Engine

**Purpose**: Core graph operations, LLM integration, and data processing

**Key Modules**:
- `graphiti.py` (55KB) - Main orchestrator class, coordinates all operations
- `nodes.py` (26KB) - EntityNode, EpisodicNode, CommunityNode definitions
- `edges.py` (21KB) - EntityEdge, EpisodicEdge, relationship management
- `graph_queries.py` - Cypher query templates for both Neo4j and FalkorDB

**Sub-packages**:

#### driver/ - Database Abstraction Layer
- `driver.py` - Abstract base for graph database operations
- `neo4j_driver.py` - Neo4j implementation with enterprise features
- `falkor_driver.py` - FalkorDB implementation with Redis protocol

#### llm_client/ - LLM Provider Integration
- `openai_client.py` - OpenAI GPT models
- `anthropic_client.py` - Claude models
- `ollama_client.py` - Local Ollama models
- `cerebras_client.py` - Cerebras cloud models
- `chutes_client.py` - Chutes AI (GLM-4.5-FP8)
- `groq_client.py` - Groq cloud inference
- `google_client.py` - Google Gemini models

#### embedder/ - Embedding Generation
- `openai_embedder.py` - OpenAI text-embedding models
- `voyage_embedder.py` - Voyage AI embeddings
- `sentence_transformer_embedder.py` - Local SBERT models
- `ollama_embedder.py` - Ollama embedding models

#### search/ - Hybrid Search Implementation
- `search.py` - Main search orchestrator
- `search_config.py` - Configuration and result structures
- `search_utils.py` - Helper functions for relevance scoring
- `search_filters.py` - Query filtering logic

#### utils/ - Utility Functions
- `bulk_utils.py` - Batch processing operations
- `datetime_utils.py` - Timezone-aware datetime handling
- `resilient_ingestion.py` - Retry logic and error recovery
- `maintenance/` - Graph maintenance operations
  - `node_operations.py` - Node extraction and resolution
  - `edge_operations.py` - Edge building and deduplication
  - `community_operations.py` - Community detection
  - `graph_data_operations.py` - Index and constraint management

#### prompts/ - LLM Prompt Templates
- `extract_nodes.py` - Entity extraction prompts
- `dedupe_nodes.py` - Node deduplication prompts
- `extract_edges.py` - Relationship extraction
- `summarize_nodes.py` - Node summarization

### 2. server/ - FastAPI REST/GraphQL Service

**Purpose**: HTTP API layer for graph operations

**Structure**:
- `graph_service/main.py` - FastAPI application setup, lifecycle management
- `graph_service/config.py` - Environment configuration
- `graph_service/zep_graphiti.py` - Graphiti instance management

**Routers**:
- `ingest.py` - Data ingestion endpoints
- `retrieve.py` - Data retrieval and search
- `cached_retrieve.py` - Cached retrieval with Redis
- `search_proxy.py` - Proxy to Rust search service
- `centrality.py` - Graph centrality calculations
- `nodes.py` - Node-specific operations
- `metrics.py` - Service metrics and health
- `ingest_queue.py` - Queue-based async ingestion

**Features**:
- WebSocket support for real-time updates
- Webhook system for data synchronization
- CORS configuration for cross-origin requests
- Async request handling with connection pooling

### 3. mcp_server/ - Model Context Protocol Server

**Purpose**: Expose Graphiti functionality to AI assistants via MCP

**Key Files**:
- `graphiti_mcp_server.py` - Main MCP server implementation
- Custom entity types: `Requirement`, `Preference`, `Procedure`
- Integration with Chutes AI for enhanced processing

**Capabilities**:
- Add memories to knowledge graph
- Search nodes and facts
- Delete entities and episodes
- Retrieve episode history
- Support for progress tokens and notifications

### 4. graph-visualizer-rust/ - High-Performance Visualization

**Purpose**: WebGL-based graph visualization with Rust backend

**Technology**: 
- Rust with Actix-web framework
- FalkorDB direct connection
- Arrow format for efficient data transfer
- DuckDB for analytical queries

**Key Components**:
- `src/main.rs` - Main server with caching and WebSocket
- `src/duckdb_store.rs` - Analytical storage layer
- `src/arrow_converter.rs` - Arrow format conversion
- `src/delta_tracker.rs` - Change tracking for incremental updates
- `src/cache.rs` - Multi-layer caching system
- `static/cosmograph.html` - WebGL visualization interface

**Features**:
- Real-time graph updates via WebSocket
- Multiple layout algorithms (force, hierarchical, radial, circular)
- Node filtering by type, centrality, time
- Interactive node selection and details
- Path finding and subgraph exploration
- Performance optimized for 100K+ nodes

### 5. frontend/ - React User Interface

**Purpose**: Modern web UI for graph interaction

**Technology Stack**:
- React 19 with TypeScript
- Vite build system
- shadcn-ui components
- Cosmograph React integration
- TanStack Query for data fetching

**Key Features**:
- GPU-accelerated graph rendering
- Direct connection to Rust server (bypasses Python)
- Responsive design with Tailwind CSS
- Real-time updates via WebSocket
- Advanced search and filtering
- Node detail panels with metadata

### 6. sync_service/ - Database Synchronization

**Purpose**: Bidirectional sync between Neo4j and FalkorDB

**Components**:
- `orchestrator/sync_orchestrator.py` - Main sync coordinator
- `extractors/neo4j_extractor.py` - Neo4j data extraction
- `extractors/falkordb_extractor.py` - FalkorDB data extraction
- `loaders/neo4j_loader.py` - Neo4j data loading
- `loaders/falkordb_loader.py` - FalkorDB data loading

**Sync Modes**:
- INCREMENTAL - Sync only changes since last run
- FULL - Complete database sync
- DIFFERENTIAL - Smart sync based on timestamps
- REVERSE_FULL - FalkorDB to Neo4j full sync
- REVERSE_INCREMENTAL - FalkorDB to Neo4j incremental
- MIGRATION_FULL - One-time migration

**Features**:
- Automatic recovery and retry logic
- Progress tracking and metrics
- Batch processing for large datasets
- Embedding dimension handling (1024 vs 2560)

### 7. queued/ - Rust Queue Service

**Purpose**: High-performance message queue for async processing

**Implementation**:
- Zero-configuration single-binary service
- REST API for queue operations
- Persistent storage with durability guarantees
- Rate limiting and flow control

**Components**:
- `queued/` - Main service implementation
- `libqueued/` - Core library
- `queued-client-rs/` - Rust client
- `queued-client-py/` - Python client
- `queued-client-js/` - JavaScript client

---

## Database Architecture

### Neo4j (Primary Storage)
- **Version**: 5.26.2
- **Purpose**: Persistent graph storage with ACID compliance
- **Port**: 7474 (HTTP), 7687 (Bolt)
- **Features**:
  - Full-text search indexes
  - Vector similarity search
  - Constraint enforcement
  - Enterprise parallel runtime (optional)

### FalkorDB (Cache Layer)
- **Version**: Latest
- **Purpose**: In-memory graph cache for fast queries
- **Port**: 6379 (Redis protocol)
- **Features**:
  - Auto-restored from Neo4j on startup
  - Optimized for read-heavy workloads
  - Vector search with custom dimensions
  - No persistence (memory-only)

### Data Model

**Node Types**:
1. **EntityNode** - Represents entities (people, places, concepts)
   - Properties: uuid, name, type, summary, created_at, embedding
   
2. **EpisodicNode** - Represents events or episodes
   - Properties: uuid, name, content, created_at, valid_at, embedding
   
3. **CommunityNode** - Represents entity clusters
   - Properties: uuid, name, summary, centrality metrics

**Edge Types**:
1. **EntityEdge** - Relationships between entities
   - Properties: uuid, type, fact, created_at, valid_at, invalid_at
   
2. **EpisodicEdge** - Links episodes to entities
   - Properties: uuid, created_at

3. **DUPLICATE_OF** - Entity deduplication markers

4. **MENTIONED_IN** - Episode-entity references

---

## Service Infrastructure

### Docker Compose Services

| Service | Port | Purpose |
|---------|------|---------|
| neo4j | 7474, 7687 | Primary graph database |
| falkordb | 6379 | In-memory graph cache |
| graph-visualizer-rust | 3000 | Visualization server |
| graphiti-centrality-rs | 3003 | Centrality calculations |
| graphiti-search-rs | 3004 | Search service |
| graph (API) | 8003 | Python GraphQL/REST API |
| graphiti-mcp | 3010 | MCP server |
| sync-service | 8082, 8083 | Database sync |
| graphiti-queued | 8093 | Queue service |
| nginx | 8088, 8443 | Reverse proxy |
| frontend | 8084 | React UI |

### Network Configuration
- Internal network: `graphiti_network`
- Service discovery via Docker DNS
- Health checks for all services
- Automatic restart policies

### Resource Limits
- Neo4j: 4GB memory
- FalkorDB: 2GB memory  
- Other services: Dynamic allocation

---

## Testing Infrastructure

### Test Suites Location: `testing/demos/`

### Cerebras Testing
- `test_cerebras_api_only.py` - API connectivity
- `test_minimal_cerebras.py` - Basic functionality
- `test_cerebras_structured.py` - JSON output validation
- `test_full_cerebras.py` - Complete integration
- `run_cerebras_test_suite.py` - Orchestration

### Ollama Testing
- `test_ollama_connection.py` - Service connectivity
- `test_minimal_ollama.py` - Basic setup
- `test_full_ollama.py` - Neo4j integration
- `test_full_ollama_falkor.py` - FalkorDB integration

### Chutes AI Testing
- `test_chutes_api_only.py` - API connectivity
- `test_minimal_chutes.py` - Basic functionality
- `test_chutes_structured.py` - GLM-4.5 capabilities
- `run_chutes_test_suite.py` - Test orchestration

### Benchmarking (`cli/benchmark.py`)
- Dry-run testing without database writes
- Performance comparison between backends
- Hyperparameter tuning
- Resource usage monitoring

---

## Maintenance & Operations

### Key Maintenance Scripts

1. **Embedding Generation**
   - `regenerate_all_embeddings.py` - Regenerate all embeddings
   - `regenerate_node_embeddings_ollama.py` - Node embeddings
   - `regenerate_edge_embeddings_ollama.py` - Edge embeddings
   - `regenerate_episodic_embeddings_ollama.py` - Episode embeddings

2. **Migration Tools**
   - `migrate_working.py` - Active migration script
   - `migrate_falkor_to_neo4j.py` - Reverse migration
   - `create_falkor_constraints.py` - Database setup

3. **Data Management**
   - `maintenance_extract_entities.py` - Entity extraction
   - `fix_mentions_embeddings.py` - Repair embeddings
   - `dedupe_comparison.py` - Deduplication analysis

4. **Monitoring**
   - `analyze_missing_embeddings.py` - Find missing embeddings
   - `validate_falkor_dates.py` - Date format validation
   - `calculate_centrality_simple.py` - Centrality metrics

### Configuration Management

**Primary Config Files**:
- `.env` - Environment variables
- `docker-compose.yml` - Service definitions
- `pyproject.toml` - Python dependencies
- `server/pyproject.toml` - Server-specific config
- `sync_service/config.yaml` - Sync configuration

**Key Environment Variables**:
```bash
# Database Selection
DEFAULT_DATABASE=falkordb
USE_FALKORDB=true

# LLM Configuration  
USE_CEREBRAS=true
USE_OLLAMA=true
CEREBRAS_API_KEY=xxx
OLLAMA_BASE_URL=http://host:11434/v1

# Embedding Configuration
EMBEDDING_DIMENSION=2560
USE_OLLAMA_EMBEDDINGS=true

# Performance Tuning
SEMAPHORE_LIMIT=5
CEREBRAS_BATCH_SIZE=1
```

---

## Deployment Considerations

### Production Readiness
1. **Database Persistence**: Neo4j for durable storage, FalkorDB as cache
2. **High Availability**: Docker Compose with restart policies
3. **Monitoring**: Health checks, metrics endpoints, logging
4. **Scalability**: Horizontal scaling via queue service
5. **Security**: Environment-based configuration, no hardcoded secrets

### Performance Optimization
1. **Caching Layers**: Redis, Arrow format, LRU caches
2. **Batch Processing**: Bulk operations for large datasets
3. **Async Operations**: Non-blocking I/O throughout
4. **Resource Management**: Memory limits, connection pooling
5. **Index Optimization**: Full-text and vector indexes

### Integration Points
1. **MCP Protocol**: AI assistant integration
2. **Webhooks**: Real-time data synchronization
3. **REST/GraphQL APIs**: Standard HTTP interfaces
4. **WebSocket**: Live updates for UI
5. **Arrow Format**: Efficient data transfer

---

## Project Evolution & Roadmap

### Recent Developments
- Chutes AI integration (GLM-4.5-FP8 support)
- Resilient ingestion with automatic retries
- Enhanced embedding dimension handling (1024 → 2560)
- Improved FalkorDB synchronization
- React frontend with Cosmograph integration

### Active Issues (GRAPH Project in Huly)
- GRAPH-48: Implement search functionality
- GRAPH-49: Add node details endpoints
- GRAPH-50: WebSocket real-time updates
- GRAPH-51: Layout algorithm support
- GRAPH-52: Large graph optimization

### Architecture Strengths
1. **Modularity**: Clean separation of concerns
2. **Performance**: Rust services for critical paths
3. **Flexibility**: Multiple LLM/embedding providers
4. **Resilience**: Retry logic, error recovery
5. **Observability**: Comprehensive logging, metrics

### Technical Debt & Considerations
1. Embedding dimension migration complexity
2. Dual database synchronization overhead
3. LLM rate limiting management
4. Memory usage with large graphs
5. Test coverage for edge cases

---

## Frontend Architecture Deep Dive

### Context Provider Architecture

The frontend uses a sophisticated nested context provider pattern for state management:

```typescript
<ParallelInitProvider>      // Parallel data loading orchestration
  <DuckDBProvider>          // In-browser analytical database
    <RustWebSocketProvider> // Real-time updates from Rust server
      <GraphConfigProvider> // Graph configuration management
        <Components/>
      </GraphConfigProvider>
    </RustWebSocketProvider>
  </DuckDBProvider>
</ParallelInitProvider>
```

**Key Providers**:
- `ParallelInitProvider` - Orchestrates parallel initialization of data sources
- `DuckDBProvider` - Manages in-browser DuckDB instance for analytics
- `RustWebSocketProvider` - Handles WebSocket connections to Rust services
- `GraphConfigProvider` - Centralizes graph visualization configuration
- `CentralityStatsContext` - Manages centrality metrics and statistics
- `LoadingCoordinator` - Coordinates loading states across components
- `WebSocketProvider` - Python API WebSocket connection management

### Advanced Hooks System

The frontend implements **50+ custom hooks** for sophisticated functionality:

#### Data Management Hooks
- `useGraphDataQuery` - Advanced data fetching with caching
- `useGraphDataManagement` - Node/edge CRUD operations
- `useIncrementalUpdates` - Handle incremental graph updates
- `useCosmographIncrementalUpdates` - Cosmograph-specific updates
- `useOptimizedIncrementalUpdates` - Performance-optimized updates
- `useProgressiveGraphData` - Progressive data loading
- `useStreamingData` - Server-sent events handling

#### Visualization Hooks
- `useGraphCamera` - Camera controls and positioning
- `useGraphSimulation` - Force simulation management
- `useGraphVisualEffects` - Visual effects and animations
- `useGraphSelection` - Multi-node selection logic
- `useGraphInteractions` - User interaction handling
- `useGraphStatistics` - Real-time graph metrics
- `useLinkStrengthAnimation` - Edge animation effects

#### Performance Hooks
- `useVirtualRendering` - Virtual rendering for large graphs
- `useParallelDataLoader` - Parallel data loading
- `useGraphCache` - Client-side caching
- `useServiceWorker` - Service worker management
- `useDebouncedConfig` - Debounced configuration updates
- `useMemoryOptimizedStore` - Memory-efficient data storage

#### WebSocket & Real-time
- `useWebSocket` - Base WebSocket functionality
- `useEnhancedWebSocket` - Advanced WebSocket features
- `useGraphWebSocket` - Graph-specific WebSocket
- `useWebSocketDeltas` - Delta-based updates
- `useRealtimeDataSync` - Real-time synchronization
- `useVersionSync` - Version consistency

### Component Architecture

#### Core Visualization Component
**GraphCanvasV2** (67KB) - Main graph visualization component
- Modular architecture with 12+ specialized hooks
- Support for 100K+ nodes with WebGL rendering
- Real-time incremental updates
- Multiple selection modes (rect, polygon)
- Advanced camera controls (zoom, pan, focus)
- Performance monitoring and optimization

#### Control Components
- **FilterPanel** - Advanced filtering with 20+ filter types
- **ControlPanel** - Graph manipulation controls
- **StatsPanel** - Real-time statistics dashboard
- **NodeDetailsPanel** - Detailed node information
- **GraphTimeline** - Temporal navigation
- **GraphSearch** - Full-text and semantic search
- **WebSocketMonitor** - Connection status monitoring
- **CacheControl** - Cache management UI

### Data Flow Architecture

```
User Action → React Component → Custom Hook → Service Layer
                                      ↓
                               Context Updates
                                      ↓
                            WebSocket/API Call
                                      ↓
                              Rust/Python Backend
                                      ↓
                               Database Update
                                      ↓
                            WebSocket Broadcast
                                      ↓
                            Component Re-render
```

---

## Advanced Data Management

### Progressive Loading Strategy

The system implements a multi-tier progressive loading approach:

1. **Initial Load** - Critical nodes (high centrality)
2. **Progressive Enhancement** - Additional nodes in batches
3. **On-Demand Loading** - User-triggered expansions
4. **Predictive Prefetching** - ML-based prediction of next nodes

### Incremental Update Pipeline

```typescript
New Data → Validation → Deduplication → Conflict Resolution 
         → Delta Compression → Store Update → UI Update
```

**Key Services**:
- `incrementalUpdatePipeline.ts` - Main pipeline orchestrator
- `conflictResolution.ts` - Resolve update conflicts
- `deltaCompression.ts` - Compress update deltas
- `messageDeduplication.ts` - Remove duplicate messages
- `memoryOptimizedStore.ts` - Efficient storage

### DuckDB Integration

The frontend embeds DuckDB for:
- Client-side analytics
- Complex graph queries
- Aggregations and statistics
- Export functionality
- Offline query capabilities

**Implementation**:
- WebAssembly-based DuckDB
- Arrow format for data transfer
- Lazy loading for performance
- IndexedDB persistence

### Caching Architecture

Multi-layer caching system:
1. **Browser Cache** - HTTP caching headers
2. **Service Worker** - Offline support
3. **IndexedDB** - Persistent storage
4. **Memory Cache** - LRU in-memory cache
5. **Redis Cache** - Server-side caching

---

## Service Layer Architecture

### Worker Service

**Purpose**: Background processing for async tasks

**Components**:
- `worker_service.py` - Main worker implementation
- `dashboard.py` - Worker monitoring dashboard
- Queue integration with `graphiti-queued`
- Webhook dispatching
- Batch processing

### Queue-based Ingestion

**Architecture**:
```
Client → API → Queue → Worker → Graphiti → Database
                ↓
           Monitoring Dashboard
```

**Features**:
- Rate limiting and throttling
- Retry logic with exponential backoff
- Dead letter queue
- Progress tracking
- Bulk operations

### Webhook System

**Data Flow**:
```
Data Update → Webhook Service → Registered Handlers
                              → WebSocket Broadcast
                              → External Services
```

**Handlers**:
- Node access tracking
- Data ingestion notifications
- Sync triggers
- External integrations

---

## Rust Services Architecture

### Graph Visualizer Server

**Technology Stack**:
- Axum web framework
- FalkorDB direct connection
- DuckDB for analytics
- Arrow format for data transfer
- WebSocket for real-time updates

**Key Components**:
- `duckdb_store.rs` - Analytical data storage
- `arrow_converter.rs` - Arrow format conversion
- `delta_tracker.rs` - Change tracking
- `cache.rs` - Multi-tier caching
- `websocket.rs` - Real-time broadcasting

**Caching Strategy**:
- Aggressive/Moderate/Disabled modes
- ETags for cache validation
- LRU eviction policy
- Bloom filters for existence checks

### Centrality Service

**Purpose**: Calculate graph centrality metrics

**Metrics Calculated**:
- Degree centrality
- Betweenness centrality
- Closeness centrality
- Eigenvector centrality
- PageRank

**Implementation**:
- Parallel computation with Rayon
- Incremental updates
- Cached results
- REST API endpoints

### Search Service

**Features**:
- Hybrid search (semantic + keyword)
- Multiple search modes (nodes, edges, episodes, communities)
- Embedding generation with Ollama
- Redis caching
- Parallel query execution

**Search Pipeline**:
```
Query → Embedding Generation → Vector Search
      → Keyword Search       → BM25 Scoring
      → Graph Traversal      → Path Finding
                            ↓
                     Result Fusion & Ranking
```

---

## Nginx Routing Architecture

### Upstream Configuration

```nginx
upstream frontend { server frontend:80; }
upstream rust-api { server graph-visualizer-rust:3000; }
upstream graphiti-api { server graph:8000; }
upstream rust-search { server graphiti-search-rs:3004; }
```

### Route Mapping

| Path | Service | Purpose |
|------|---------|---------|
| `/` | Frontend | React application |
| `/api/` | Rust Visualizer | Graph data API |
| `/graphiti/` | Python API | Ingestion/retrieval |
| `/search-rs/` | Rust Search | Search service |
| `/ws` | Python WebSocket | Real-time updates |
| `/rust-ws` | Rust WebSocket | Graph updates |

### Security Configuration
- CORS headers for cross-origin requests
- CSP (Content Security Policy)
- XSS protection
- Gzip compression
- Client body size limits (100M)

---

## Testing Infrastructure

### Frontend Testing

**Test Coverage**:
- 50+ test files
- Component tests with React Testing Library
- Hook tests with custom test utilities
- Integration tests for data flow
- WebSocket flow testing
- Memory optimization tests

**Test Organization**:
```
__tests__/
├── components/     # Component unit tests
├── hooks/         # Custom hook tests
├── integration/   # End-to-end tests
├── api/          # API client tests
└── utils/        # Utility function tests
```

### Backend Testing

**Python Tests** (`tests/`):
- Unit tests for core functionality
- Integration tests with databases
- LLM client mocking
- Benchmark suites
- Performance tests

**Rust Tests**:
- Unit tests in `src/` modules
- Integration tests in `tests/`
- Benchmarks with Criterion
- Property-based testing

---

## Development Tools & Utilities

### Maintenance Scripts

**Embedding Management**:
- `regenerate_all_embeddings.py` - Batch embedding regeneration
- `fix_mentions_embeddings.py` - Repair corrupted embeddings
- `analyze_missing_embeddings.py` - Find missing embeddings

**Migration Tools**:
- `migrate_working.py` - Neo4j to FalkorDB migration
- `migrate_falkor_to_neo4j.py` - Reverse migration
- `create_falkor_constraints.py` - Database setup

**Performance Tools**:
- `calculate_centrality_simple.py` - Centrality calculation
- `dedupe_comparison.py` - Deduplication analysis
- `run_benchmark.py` - Performance benchmarking

### CLI Tools

**Benchmark CLI** (`cli/benchmark.py`):
- Dry-run testing without writes
- Hyperparameter tuning
- Database comparison
- Performance profiling
- Export to JSON/CSV/HTML

### Documentation Structure

```
docs/
├── architecture/      # System design docs
├── deployment/       # Deployment guides
├── development/      # Developer guides
├── integrations/     # Integration docs
├── performance/      # Performance analysis
├── security/        # Security documentation
└── investigations/  # Technical investigations
```

---

## Performance Optimizations

### Frontend Optimizations
- Virtual rendering for large graphs
- Progressive data loading
- Memory monitoring and cleanup
- Service worker caching
- WebAssembly for compute
- GPU acceleration via WebGL

### Backend Optimizations
- Connection pooling
- Batch processing
- Parallel query execution
- Index optimization
- Query result caching
- Incremental computations

### Network Optimizations
- HTTP/2 support
- Gzip/Brotli compression
- CDN for static assets
- WebSocket connection reuse
- Delta-based updates
- Request batching

---

## Production Considerations

### Monitoring & Observability
- Health check endpoints
- Metrics collection
- Distributed tracing
- Error tracking
- Performance monitoring
- Resource usage tracking

### Scalability Patterns
- Horizontal scaling via Docker Swarm/K8s
- Queue-based load distribution
- Cache-aside pattern
- Read replicas for Neo4j
- FalkorDB clustering
- CDN for frontend assets

### Security Measures
- Environment-based secrets
- CORS configuration
- Rate limiting
- Input validation
- SQL injection prevention
- XSS protection

### Deployment Strategies
- Blue-green deployments
- Rolling updates
- Feature flags
- Canary releases
- Rollback procedures
- Database migrations

---

## Conclusion

Graphiti represents an exceptionally sophisticated knowledge graph platform with:

- **Advanced Frontend**: React with 50+ custom hooks, WebGL visualization, and in-browser analytics
- **Multi-Service Backend**: Python for AI/ingestion, Rust for performance-critical paths
- **Sophisticated Data Management**: Progressive loading, incremental updates, multi-tier caching
- **Real-time Capabilities**: WebSocket broadcasting, live updates, delta synchronization
- **Enterprise Features**: Comprehensive testing, monitoring, security, and scalability
- **AI-Native Design**: Multi-provider LLM support, embedding generation, semantic search

The architecture demonstrates exceptional engineering with clear separation of concerns, performance optimization at every layer, and production-ready reliability features. The combination of Python's AI ecosystem, Rust's performance, and React's rich UI capabilities creates a powerful platform for temporal knowledge graph applications.