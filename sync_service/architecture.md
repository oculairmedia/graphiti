# Neo4j-FalkorDB Sync Service Architecture

## Overview

The sync service maintains a hybrid architecture where Neo4j serves as the persistent ACID-compliant storage and FalkorDB serves as a high-performance cache for read operations.

## Architecture Principles

1. **Single Source of Truth**: Neo4j is the authoritative data store
2. **Performance Cache**: FalkorDB provides fast read access for visualization/queries
3. **Eventual Consistency**: FalkorDB is eventually consistent with Neo4j
4. **Fault Tolerance**: Sync service can recover from interruptions and inconsistencies
5. **Incremental Updates**: Only sync changed data to minimize overhead

## Data Flow

```
Graphiti Core → Neo4j (Primary Storage)
                   ↓
            Sync Service (Python)
                   ↓
            FalkorDB (Cache Layer)
                   ↓
      Graph Visualization (Rust Server)
```

## Core Components

### 1. Neo4j Extractor Module
- **Purpose**: Extract graph data from Neo4j using efficient queries
- **Features**: 
  - Incremental extraction based on timestamps
  - Batch processing for large datasets
  - Connection pooling and retry logic
  - Support for Entity nodes, Episodic nodes, and all edge types

### 2. FalkorDB Loader Module  
- **Purpose**: Load data into FalkorDB cache
- **Features**:
  - Upsert operations (create or update)
  - Batch loading for performance
  - Index creation and maintenance
  - Data validation and transformation

### 3. Sync Orchestrator
- **Purpose**: Coordinate the sync process
- **Features**:
  - Incremental sync based on change detection
  - Full sync for initial setup or recovery
  - Conflict resolution and error handling
  - Progress tracking and resumption

### 4. Configuration Management
- **Purpose**: Centralized configuration for all components
- **Features**:
  - Environment-based configuration
  - Database connection settings
  - Sync intervals and batch sizes
  - Logging levels and monitoring

## Data Model Mapping

### Node Types
- **Entity Nodes**: Direct mapping with all properties preserved
- **Episodic Nodes**: Direct mapping with content and metadata
- **Community Nodes**: Direct mapping for graph clustering

### Edge Types  
- **Entity Edges (RELATES_TO)**: Relationship facts between entities
- **Episodic Edges (MENTIONS)**: References from episodes to entities

### Temporal Data
- **created_at**: Preserved for all nodes and edges
- **valid_at/invalid_at**: Temporal validity for entity edges
- **expired_at**: Expiration timestamps

## Sync Strategies

### 1. Incremental Sync (Default)
- Query Neo4j for changes since last sync timestamp
- Use `created_at` and `updated_at` for change detection
- Sync only modified/new data to FalkorDB

### 2. Full Sync (Recovery Mode)
- Clear FalkorDB cache completely
- Extract all data from Neo4j
- Rebuild entire FalkorDB graph

### 3. Differential Sync (Advanced)
- Compare node/edge counts between databases
- Identify missing or orphaned data
- Perform targeted sync operations

## Performance Considerations

### Batch Sizes
- **Nodes**: 1000 per batch (configurable)
- **Edges**: 1000 per batch (configurable)
- **Memory Management**: Process batches sequentially to limit memory usage

### Connection Pooling
- **Neo4j**: AsyncSessionPool with 10 concurrent connections
- **FalkorDB**: Connection pool with 5 concurrent connections
- **Health Checks**: Regular connectivity validation

### Indexing Strategy
- **Neo4j**: Use existing Graphiti indices
- **FalkorDB**: Create matching indices for performance
- **Index Sync**: Ensure index consistency between databases

## Error Handling & Recovery

### Transactional Safety
- **Neo4j Transactions**: Use read transactions for extraction
- **FalkorDB Batches**: Group related operations
- **Rollback Capability**: Ability to revert failed sync operations

### Retry Logic
- **Connection Failures**: Exponential backoff retry
- **Partial Failures**: Skip failed items, continue processing
- **Deadlock Handling**: Retry with randomized delays

### Monitoring & Alerting
- **Health Endpoints**: HTTP endpoints for service status
- **Metrics Collection**: Sync duration, error rates, data volumes
- **Log Aggregation**: Structured logging for debugging

## Configuration Schema

```yaml
neo4j:
  uri: "bolt://neo4j:7687"
  user: "neo4j"
  password: "graphiti123"
  database: "neo4j"
  pool_size: 10

falkordb:
  host: "falkordb"
  port: 6379
  database: "graphiti_cache"
  pool_size: 5

sync:
  interval_seconds: 300  # 5 minutes
  batch_size: 1000
  full_sync_on_startup: false
  enable_incremental: true
  
logging:
  level: "INFO"
  format: "json"

monitoring:
  health_port: 8080
  metrics_enabled: true
```

## Deployment Strategy

### Docker Container
- **Base Image**: python:3.11-slim
- **Dependencies**: neo4j-driver, falkordb-py, asyncio libraries
- **Health Checks**: HTTP endpoint on port 8080
- **Resource Limits**: 512MB memory, 0.5 CPU cores

### Integration with docker-compose.yml
- **Service Name**: `sync-service`
- **Dependencies**: neo4j, falkordb services must be healthy
- **Network**: Share network with other Graphiti services
- **Volumes**: Configuration files and logs

## Security Considerations

### Authentication
- **Neo4j**: Username/password authentication
- **FalkorDB**: Redis AUTH if configured
- **Service**: No external authentication required

### Network Security  
- **Internal Only**: Service communicates only within Docker network
- **No Public Ports**: Only health endpoint exposed internally

### Data Protection
- **No Data Transformation**: Preserve all data integrity
- **Encryption**: Use encrypted connections where available
- **Audit Logging**: Log all sync operations

## Future Enhancements

### Real-time Sync
- **Change Data Capture**: Monitor Neo4j transaction logs
- **WebSocket Notifications**: Real-time updates to clients
- **Event-Driven Architecture**: React to specific data changes

### Advanced Conflict Resolution
- **Schema Evolution**: Handle schema changes gracefully
- **Data Validation**: Validate data consistency between systems
- **Manual Override**: Tools for resolving sync conflicts

### Performance Optimization
- **Parallel Processing**: Multi-threaded sync operations  
- **Compression**: Reduce network overhead for large transfers
- **Caching**: In-memory caching of frequently accessed data