# Graphiti Rust Sync Service - POC

High-performance graph synchronization service written in Rust for syncing data between Neo4j and FalkorDB.

## Project Status: Feature Complete ✅

### Core Features (Complete)
- ✅ Neo4j extractor with pagination and retry logic
- ✅ FalkorDB extractor with batch processing
- ✅ Neo4j loader with optimized batch UNWIND and caching
- ✅ FalkorDB loader with batch writes and instrumentation
- ✅ Bi-directional sync (Neo4j ↔ FalkorDB)
- ✅ Continuous sync orchestrator with change detection
- ✅ Health check HTTP server (Axum) with database connectivity checks
- ✅ Prometheus metrics endpoint (`/metrics`)
- ✅ Comprehensive environment variable configuration
- ✅ Telemetry and sync state tracking
- ✅ Structured error handling with retry logic
- ✅ Docker containerization

### Monitoring & Observability
- ✅ Health endpoints (`/health`, `/healthz`, `/live`, `/ready`)
- ✅ Prometheus metrics (counters, gauges, histograms)
- ✅ Configurable log levels (TRACE, DEBUG, INFO, WARN, ERROR)
- ✅ Sync progress tracking and statistics
- ✅ Database connectivity verification

### Pending Enhancements
- ⏳ Structured JSON logging (GRAPH-18)
- ⏳ Safety validation and disaster recovery (GRAPH-26, GRAPH-24)
- ⏳ Incremental/differential sync modes (GRAPH-22, GRAPH-21)
- ⏳ Comprehensive documentation (GRAPH-33)

## Quick Start

### Prerequisites
```bash
# Install Rust
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# Recommended tools
cargo install cargo-watch
```

### Development Commands
```bash
# Check compilation (fast)
make check

# Build release version
make build

# Run application
make run

# Development with auto-rebuild
make watch

# Format code
make fmt

# Lint code
make lint

# Run tests
make test
```

### Docker Test Environment
```bash
# Start test databases (different ports from main Graphiti stack)
make docker-up

# Stop test databases
make docker-down

# View logs
make docker-logs
```

Test instances run on:
- Neo4j: http://localhost:7475 (browser), bolt://localhost:7688
- FalkorDB: localhost:6380

## Project Structure

```
rust-sync-poc/
├── Cargo.toml              # Project dependencies
├── Makefile                # Development commands
├── rustfmt.toml            # Code formatting rules
├── .vscode/                # VSCode configuration
│   ├── settings.json
│   └── extensions.json
├── docker/                 # Test environment
│   ├── docker-compose.yml
│   └── Dockerfile
└── src/
    ├── main.rs             # Application entry point
    ├── error.rs            # Error types
    ├── config/             # Configuration management
    │   ├── mod.rs
    │   └── settings.rs
    ├── models/             # Data models
    │   ├── mod.rs
    │   ├── node.rs         # GraphNode model
    │   ├── edge.rs         # GraphEdge model
    │   └── stats.rs        # Statistics tracking
    ├── extractors/         # [TODO] Neo4j data extraction
    ├── loaders/            # [TODO] FalkorDB data loading
    ├── orchestrator/       # [TODO] Sync orchestration
    └── health/             # [TODO] Health check server
```

## Configuration

### Environment Variables

All configuration uses the `SYNC_` prefix. See **[docs/ENVIRONMENT_VARIABLES.md](docs/ENVIRONMENT_VARIABLES.md)** for complete documentation.

**Quick Example:**
```bash
# Neo4j configuration
export SYNC_NEO4J_URI=bolt://neo4j:7687
export SYNC_NEO4J_USER=neo4j
export SYNC_NEO4J_PASSWORD=graphiti123
export SYNC_NEO4J_DATABASE=neo4j

# FalkorDB configuration
export SYNC_FALKORDB_HOST=falkordb
export SYNC_FALKORDB_PORT=6379
export SYNC_FALKORDB_DATABASE=graphiti

# Performance tuning
export SYNC_SYNC_BATCH_SIZE=500
export SYNC_SYNC_PARALLEL_WORKERS=8

# Monitoring
export SYNC_HEALTH_PORT=8080
export SYNC_METRICS_PORT=8081
export LOG_LEVEL=INFO

# Run continuous sync
./graphiti-sync-rs sync-loop falkor-to-neo4j
```

### Configuration Validation

The service validates all configuration on startup and will:
- Log all settings (passwords sanitized)
- Fail fast on invalid values
- Show clear error messages

See [docs/ENVIRONMENT_VARIABLES.md](docs/ENVIRONMENT_VARIABLES.md) for:
- Complete variable reference
- Default values
- Docker Compose examples
- Troubleshooting guide

## Architecture Design

Based on research document `RUST_SYNC_SERVICE_RESEARCH.md`, targeting:
- **3-4x faster** than Python implementation
- **3x lower memory** usage
- **4x better** concurrent query handling

### Core Components

1. **Neo4j Extractor** (`extractors/neo4j.rs`)
   - Uses `neo4rs` v0.9.0-rc.8
   - Implements SKIP/LIMIT pagination
   - Streams data via tokio channels
   - Batch size: configurable (default 1000)

2. **FalkorDB Loader** (`loaders/falkordb.rs`)
   - Uses `falkordb-rs` v0.1.11
   - Batch MERGE operations
   - Connection pooling
   - Error recovery with retries

3. **Sync Orchestrator** (`orchestrator/sync.rs`)
   - Coordinates extraction and loading
   - Channel-based communication
   - Progress tracking
   - Performance metrics

4. **Health Server** (`health/server.rs`)
   - Axum-based HTTP server
   - `/health` endpoint
   - Sync status reporting

## Performance Targets

| Operation | Python (baseline) | Rust (target) | Improvement |
|-----------|------------------|---------------|-------------|
| Node Extraction (10K) | ~2.5s | ~0.8s | 3.1x |
| Node Loading (10K) | ~3.0s | ~1.0s | 3.0x |
| Full Sync (100K nodes) | ~45s | ~15s | 3.0x |
| Memory Usage (peak) | ~500MB | ~150MB | 3.3x |

## Development Best Practices

### Code Quality
- Run `make fmt` before committing
- Fix all `make lint` warnings
- Write tests for new functionality
- Use `make check` for quick feedback

### Testing
```bash
# Run all tests
cargo test

# Run with output
cargo test -- --nocapture

# Run specific test
cargo test test_node_creation
```

### Continuous Integration
```bash
# Run full CI checks
make ci
```

This runs:
1. Format checking (`cargo fmt --check`)
2. Linting (`cargo clippy`)
3. All tests (`cargo test`)

## Next Steps

1. **Implement Neo4j Extractor**
   - Connection setup with neo4rs
   - Paginated node/edge extraction
   - Error handling and retries

2. **Implement FalkorDB Loader**
   - Connection setup with falkordb-rs
   - Batch MERGE operations
   - Performance optimization

3. **Build Sync Orchestrator**
   - Channel-based pipeline
   - Progress tracking
   - Statistics collection

4. **Add Health Server**
   - Axum HTTP server
   - Status endpoints
   - Metrics reporting

5. **Integration Testing**
   - Connect to real Graphiti databases
   - Performance benchmarking
   - Comparison with Python implementation

## Resources

- [Rust Sync Research Document](../graphiti/RUST_SYNC_SERVICE_RESEARCH.md)
- [Neo4rs Documentation](https://github.com/neo4j-labs/neo4rs)
- [FalkorDB-rs Documentation](https://github.com/FalkorDB/falkordb-rs)
- [Tokio Documentation](https://tokio.rs/)

## License

Part of the Graphiti Knowledge Graph Platform
