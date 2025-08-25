# Neo4j-FalkorDB Sync Service

A high-performance synchronization service that maintains a hybrid architecture where Neo4j serves as the persistent ACID-compliant storage and FalkorDB serves as a high-performance cache for read operations.

## Architecture Overview

The sync service implements a **write-to-Neo4j, read-from-FalkorDB** pattern:

```
Graphiti Applications → Neo4j (Primary Storage)
                           ↓ (Sync Service)
                      FalkorDB (Cache Layer)
                           ↓
               Graph Visualization & Queries
```

### Key Benefits

- **Data Persistence**: Neo4j provides ACID guarantees and persistent storage
- **High Performance**: FalkorDB serves as a fast cache for read operations
- **Scalability**: Separates write and read workloads for optimal performance
- **Reliability**: Automatic sync with error handling and recovery

## Features

- ✅ **Incremental Sync**: Only sync changes since last update
- ✅ **Full Sync**: Complete data rebuild for recovery scenarios  
- ✅ **Differential Sync**: Smart comparison-based synchronization
- ✅ **Batch Processing**: Efficient processing of large datasets
- ✅ **Health Monitoring**: HTTP endpoints for health checks and metrics
- ✅ **Real-time Updates**: WebSocket support for live status updates
- ✅ **Error Recovery**: Automatic retry logic with exponential backoff
- ✅ **Performance Metrics**: Comprehensive statistics and monitoring

## Quick Start

### Using Docker Compose

The sync service is integrated into the main Graphiti docker-compose.yml:

```bash
# Start all services including sync
docker-compose up -d

# Check sync service status
curl http://localhost:8080/health

# View sync metrics
curl http://localhost:8081/metrics
```

### Configuration

Key environment variables:

```bash
# Database connections
NEO4J_URI=bolt://neo4j:7687
FALKORDB_HOST=falkordb
FALKORDB_PORT=6379

# Sync behavior
SYNC_INTERVAL_SECONDS=300  # 5 minutes
SYNC_BATCH_SIZE=1000
SYNC_FULL_ON_STARTUP=false
SYNC_ENABLE_CONTINUOUS=true

# Monitoring
SYNC_HEALTH_PORT=8080
SYNC_METRICS_PORT=8081
```

## API Endpoints

### Health Check
```bash
GET /health
```
Returns service health status and sync information.

### Metrics (Prometheus Format)
```bash
GET /metrics
```
Returns performance metrics in Prometheus format.

### Sync Status
```bash
GET /api/sync/status
```
Returns current sync orchestrator status.

### Sync Statistics  
```bash
GET /api/sync/statistics
```
Returns comprehensive sync statistics.

### Manual Sync Operations
```bash
# Trigger full sync
POST /api/sync/full

# Trigger incremental sync  
POST /api/sync/incremental

# Start continuous sync
POST /api/sync/start

# Stop continuous sync
POST /api/sync/stop
```

### Real-time Updates
```bash
WebSocket: /ws/updates
```
Provides real-time sync status updates.

## Sync Modes

### Incremental Sync (Default)
- Syncs only data modified since last sync
- Based on `created_at` timestamps
- Minimal resource usage
- Runs every 5 minutes by default

### Full Sync  
- Clears FalkorDB cache completely
- Rebuilds entire graph from Neo4j
- Used for initial setup or recovery
- Can be triggered manually or on startup

### Differential Sync
- Compares data counts between databases
- Triggers full sync if discrepancies found
- Useful for detecting data drift

## Data Flow

### Supported Data Types
- **Entity Nodes**: Graph entities with properties and relationships
- **Episodic Nodes**: Episode/content nodes with temporal information  
- **Community Nodes**: Graph clustering and community data
- **Entity Edges**: Relationships between entities (RELATES_TO)
- **Episodic Edges**: References from episodes to entities (MENTIONS)

### Sync Process
1. **Extract**: Query Neo4j for changed data using batch processing
2. **Transform**: Convert datetime objects and prepare data for FalkorDB
3. **Load**: Upsert data into FalkorDB using efficient batch operations
4. **Verify**: Track success rates and handle errors
5. **Monitor**: Update metrics and broadcast status

## Performance

### Batch Processing
- Default batch size: 1000 items
- Configurable per data type
- Memory-efficient streaming
- Progress tracking and resumption

### Connection Pooling
- Neo4j: 10 concurrent connections
- FalkorDB: 5 concurrent connections  
- Health check validation
- Automatic reconnection

### Resource Usage
- Memory limit: 512MB
- CPU limit: 0.5 cores
- Efficient async processing
- Minimal network overhead

## Monitoring & Alerting

### Health Monitoring
- Service uptime tracking
- Database connectivity checks
- Sync operation status
- Error rate monitoring

### Performance Metrics
- Items processed per second
- Sync duration tracking  
- Success/failure rates
- Memory and CPU usage

### Log Analysis
- Structured JSON logging
- Configurable log levels
- File rotation support
- Error correlation

## Configuration Reference

### Neo4j Settings
```yaml
neo4j:
  uri: "bolt://neo4j:7687"
  user: "neo4j"
  password: "graphiti123"
  database: "neo4j"
  pool_size: 10
```

### FalkorDB Settings
```yaml
falkordb:
  host: "falkordb"
  port: 6379
  database: "graphiti_cache"
  pool_size: 5
```

### Sync Settings
```yaml
sync:
  interval_seconds: 300
  batch_size: 1000
  full_sync_on_startup: false
  enable_incremental: true
  enable_continuous: true
  max_retries: 3
  retry_delay_seconds: 30
```

### Logging Settings
```yaml
logging:
  level: "INFO"
  format: "json"
  file_path: "/app/logs/sync.log"
  max_file_size_mb: 100
  backup_count: 5
```

### Monitoring Settings
```yaml
monitoring:
  health_port: 8080
  metrics_port: 8081
  metrics_enabled: true
```

## Troubleshooting

### Common Issues

**Sync Service Won't Start**
```bash
# Check database connectivity
docker-compose logs neo4j
docker-compose logs falkordb

# Check sync service logs
docker-compose logs sync-service
```

**Sync Operations Failing**
```bash
# Check sync statistics
curl http://localhost:8080/api/sync/statistics

# View recent operation history
curl http://localhost:8080/api/sync/history?limit=10

# Check system metrics
curl http://localhost:8080/api/system/metrics
```

**Performance Issues**
```bash
# Monitor resource usage
curl http://localhost:8081/metrics | grep process_

# Check batch processing rates
curl http://localhost:8080/api/sync/statistics | jq '.average_duration_seconds'

# Adjust batch size
export SYNC_BATCH_SIZE=500
docker-compose restart sync-service
```

### Debug Mode
```bash
# Enable debug logging
export LOG_LEVEL=DEBUG
docker-compose restart sync-service

# View detailed logs
docker-compose logs -f sync-service
```

## Development

### Local Development Setup
```bash
# Install dependencies
cd sync_service
pip install -r requirements.txt

# Run tests
python -m pytest tests/

# Run locally
python -m sync_service.main config.yaml
```

### Building Docker Image
```bash
# Build image
docker build -t graphiti-sync-service ./sync_service

# Run container
docker run -p 8080:8080 -p 8081:8081 graphiti-sync-service
```

## Integration with Huly

This sync service is tracked in Huly project **GRAPH** under the "Neo4j-FalkorDB Sync Service" milestone. All implementation follows the architecture and requirements defined in:

- **GRAPH-474**: Design sync service architecture and data flow ✅
- **GRAPH-475**: Implement Neo4j data extraction module ✅  
- **GRAPH-476**: Implement FalkorDB data loading module ✅
- **GRAPH-477**: Build sync orchestration engine ✅
- **GRAPH-478**: Add configuration management system ✅
- **GRAPH-479**: Implement logging and monitoring ✅
- **GRAPH-480**: Create Docker containerization ✅

## License

Copyright 2024, Zep Software, Inc. Licensed under the Apache License 2.0.