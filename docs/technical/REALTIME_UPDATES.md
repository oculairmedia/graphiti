# Real-Time Updates Architecture

## Overview
The real-time update pipeline enables live graph updates without page refresh when new data is ingested through the Graphiti Python API.

## Architecture Flow
```
Python API (port 8003)
    ↓ (webhook on data ingestion)
Rust Server (port 3000)
    ↓ (WebSocket broadcast)
React Frontend (port 8080)
    ↓ (visual update)
Graph Visualization (Cosmograph)
```

## Components

### 1. Python API Server
- **Location**: `/opt/stacks/graphiti/server/`
- **Webhook URL**: Configured via `GRAPHITI_DATA_WEBHOOK_URLS` environment variable
- **Sends**: POST request to Rust server on data ingestion
- **Payload**: Nodes and edges in Graphiti format

### 2. Rust Visualization Server  
- **Location**: `/opt/stacks/graphiti/graph-visualizer-rust/`
- **Webhook Endpoint**: `/api/webhooks/data-ingestion`
- **WebSocket Endpoint**: `/ws`
- **Processing**:
  - Receives webhook from Python API
  - Transforms Graphiti format to internal format
  - Updates DuckDB store
  - Broadcasts delta updates via WebSocket

### 3. React Frontend
- **Location**: `/opt/stacks/graphiti/frontend/`
- **WebSocket Provider**: `RustWebSocketProvider.tsx`
- **Graph Component**: `GraphCanvas.tsx`
- **Processing**:
  - Subscribes to delta updates
  - Queues updates for batch processing
  - Applies updates to Cosmograph visualization

## Configuration

### Docker Compose Environment Variables
```yaml
graph:
  environment:
    - GRAPHITI_DATA_WEBHOOK_URLS=http://172.17.0.1:3000/api/webhooks/data-ingestion
    - RUST_SERVER_URL=http://172.17.0.1:3000
    - ENABLE_CACHE_INVALIDATION=true
```

### Local Development Setup
1. **Run Rust server locally** (faster iteration):
```bash
cd /opt/stacks/graphiti/graph-visualizer-rust
FALKORDB_HOST=localhost FALKORDB_PORT=6389 cargo run --release
```

2. **Run React frontend locally**:
```bash
cd /opt/stacks/graphiti/frontend
npm run dev
```

3. **Docker services** (FalkorDB, Python API):
```bash
cd /opt/stacks/graphiti
docker-compose up falkordb graph
```

## WebSocket Message Format

### Delta Update (from Rust to Frontend)
```json
{
  "type": "graph:delta",
  "data": {
    "operation": "add",
    "nodes": [{
      "id": "uuid",
      "label": "name", 
      "node_type": "type",
      "properties": {}
    }],
    "edges": [{
      "from": "source_uuid",
      "to": "target_uuid",
      "edge_type": "relationship"
    }],
    "timestamp": 1234567890
  }
}
```

## Known Issues & Improvements Needed

### 1. Production Deployment
- [ ] Fix nginx configuration for containerized frontend
- [ ] Add SSL/TLS for WebSocket connections
- [ ] Implement authentication for WebSocket connections

### 2. Error Handling
- [ ] Add retry logic for failed webhook deliveries
- [ ] Handle WebSocket disconnections gracefully
- [ ] Validate data consistency (orphaned edges)

### 3. Performance
- [ ] Implement update deduplication
- [ ] Add queue size limits
- [ ] Optimize batch processing timing
- [ ] Add backpressure handling

### 4. Monitoring
- [ ] Add metrics for update latency
- [ ] Track WebSocket connection health
- [ ] Log failed updates

### 5. User Experience  
- [ ] Show connection status in UI
- [ ] Add visual feedback for updates (glow effect)
- [ ] Display update count/rate
- [ ] Allow users to pause/resume updates

## Testing Real-Time Updates

1. **Ingest data through Python API**:
```bash
curl -X POST http://192.168.50.90:8003/add-episode \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Episode",
    "content": "This is a test",
    "source": "manual"
  }'
```

2. **Monitor WebSocket messages** in browser console:
- Open DevTools → Network → WS tab
- Look for messages on `ws://192.168.50.90:3000/ws`

3. **Check Rust server logs**:
```bash
# If running in Docker
docker logs graphiti-graph-visualizer-rust-1

# If running locally
# Logs appear in terminal where cargo run was executed
```

## Troubleshooting

### WebSocket Won't Connect
1. Check Rust server is running: `curl http://localhost:3000/api/health`
2. Check for CORS issues in browser console
3. Verify WebSocket URL in RustWebSocketProvider.tsx

### Updates Not Appearing
1. Check Python API webhook configuration
2. Verify Rust server receives webhook: check logs
3. Ensure frontend subscription is active: check console logs

### Graph Not Updating Visually
1. Check GraphCanvas.tsx processDeltaBatch function
2. Verify Cosmograph instance is initialized
3. Check for JavaScript errors in console

## Future Enhancements
1. **Bidirectional Updates**: Allow frontend to send updates back
2. **Selective Subscriptions**: Subscribe to specific node types
3. **Update Filtering**: Client-side filtering of updates
4. **Conflict Resolution**: Handle concurrent updates
5. **Offline Support**: Queue updates when disconnected