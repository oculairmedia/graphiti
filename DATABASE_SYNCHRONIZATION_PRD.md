# PRD: Database Synchronization & Unified Search Architecture

## Executive Summary

This PRD addresses the critical issue of two unsynchronized database systems causing search inconsistencies between the main Graphiti search and the cosmograph direct search. The solution involves implementing a unified node identification system and robust synchronization mechanisms.

## Problem Statement

### Current Architecture Issues
1. **Dual Database System**: 
   - **FalkorDB/Neo4j**: Main graph database used by Python API and Graphiti search
   - **DuckDB**: In-memory database used by Rust server for cosmograph visualization

2. **Search Inconsistencies**:
   - Main search bar uses Graphiti search (queries FalkorDB)
   - Top cosmograph search bar queries DuckDB directly
   - Results don't target the same nodes due to data misalignment

3. **Synchronization Gaps**:
   - Webhook-based updates may fail or be delayed
   - No validation that DuckDB matches FalkorDB state
   - Different node indexing schemes between systems

## Current Data Flow Analysis

```
Data Ingestion:
Python API → FalkorDB → Webhook → Rust Server → DuckDB → Frontend

Search Flows:
1. Main Search: Frontend → Python API → FalkorDB → Results
2. Cosmograph Search: Frontend → Rust Server → DuckDB → Results

Problem: Node IDs/indices don't match between FalkorDB and DuckDB
```

### Identified Root Causes

1. **Inconsistent Node Identification**:
   - FalkorDB uses UUIDs as primary identifiers
   - DuckDB uses sequential indices (`idx`) for cosmograph
   - No stable mapping between UUID and cosmograph index

2. **Webhook Reliability Issues**:
   - Network failures can cause missed updates
   - No retry mechanism for failed webhook deliveries
   - No validation that webhook data was processed correctly

3. **Data Transformation Inconsistencies**:
   - Different serialization formats between systems
   - Property mapping differences
   - Timing issues during concurrent updates

## Proposed Solution

### 1. Unified Node Identification System

#### Stable UUID-to-Index Mapping
```rust
// In DuckDB schema
CREATE TABLE node_mapping (
    uuid TEXT PRIMARY KEY,
    cosmograph_idx INTEGER UNIQUE,
    created_at TIMESTAMP,
    last_updated TIMESTAMP
);

// Ensure consistent mapping
pub struct NodeMapper {
    uuid_to_idx: HashMap<String, u32>,
    idx_to_uuid: HashMap<u32, String>,
    next_idx: u32,
}

impl NodeMapper {
    pub fn get_or_create_index(&mut self, uuid: &str) -> u32 {
        if let Some(&idx) = self.uuid_to_idx.get(uuid) {
            return idx;
        }
        
        let idx = self.next_idx;
        self.uuid_to_idx.insert(uuid.to_string(), idx);
        self.idx_to_uuid.insert(idx, uuid.to_string());
        self.next_idx += 1;
        
        // Persist mapping to DuckDB
        self.persist_mapping(uuid, idx);
        idx
    }
}
```

#### Search Result Mapping
```typescript
// Frontend search result mapping
interface SearchResultMapper {
  mapGraphitiToCosmograph(graphitiResults: GraphitiNode[]): CosmographNode[];
  mapCosmographToGraphiti(cosmographResults: CosmographNode[]): GraphitiNode[];
  getCosmographIndex(uuid: string): number | null;
  getUuidFromIndex(index: number): string | null;
}
```

### 2. Robust Synchronization Mechanisms

#### Webhook Reliability Enhancement
```python
# Enhanced webhook service with retry and validation
class ReliableWebhookService:
    def __init__(self):
        self.retry_attempts = 3
        self.retry_delay = 1.0  # seconds
        self.validation_enabled = True
        
    async def emit_data_ingestion(self, operation: str, nodes: List[Any], edges: List[Any]):
        for attempt in range(self.retry_attempts):
            try:
                # Send webhook with correlation ID
                correlation_id = str(uuid.uuid4())
                payload = {
                    "correlation_id": correlation_id,
                    "operation": operation,
                    "nodes": self.serialize_nodes(nodes),
                    "edges": self.serialize_edges(edges),
                    "timestamp": time.time()
                }
                
                response = await self.send_webhook(payload)
                
                # Validate synchronization if enabled
                if self.validation_enabled:
                    await self.validate_sync(correlation_id, nodes, edges)
                    
                return response
                
            except Exception as e:
                if attempt < self.retry_attempts - 1:
                    await asyncio.sleep(self.retry_delay * (2 ** attempt))
                    continue
                raise e
```

#### Synchronization Validation
```rust
// Rust server validation endpoint
#[derive(Serialize, Deserialize)]
pub struct SyncValidationRequest {
    correlation_id: String,
    expected_nodes: Vec<String>,  // UUIDs
    expected_edges: Vec<String>,  // Edge IDs
}

pub async fn validate_synchronization(
    State(state): State<AppState>,
    Json(request): Json<SyncValidationRequest>
) -> Result<Json<SyncValidationResponse>, StatusCode> {
    let missing_nodes = state.duckdb_store
        .find_missing_nodes(&request.expected_nodes)
        .await
        .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;
        
    let missing_edges = state.duckdb_store
        .find_missing_edges(&request.expected_edges)
        .await
        .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;
        
    Ok(Json(SyncValidationResponse {
        correlation_id: request.correlation_id,
        is_synchronized: missing_nodes.is_empty() && missing_edges.is_empty(),
        missing_nodes,
        missing_edges,
    }))
}
```

### 3. Unified Search Interface

#### Search Result Harmonization
```typescript
// Unified search service
class UnifiedSearchService {
  async search(query: string, searchType: 'graphiti' | 'cosmograph' | 'unified'): Promise<UnifiedSearchResults> {
    switch (searchType) {
      case 'graphiti':
        const graphitiResults = await this.searchGraphiti(query);
        return this.harmonizeResults(graphitiResults, 'graphiti');
        
      case 'cosmograph':
        const cosmographResults = await this.searchCosmograph(query);
        return this.harmonizeResults(cosmographResults, 'cosmograph');
        
      case 'unified':
        // Search both systems and merge results
        const [gResults, cResults] = await Promise.all([
          this.searchGraphiti(query),
          this.searchCosmograph(query)
        ]);
        return this.mergeAndDeduplicateResults(gResults, cResults);
    }
  }
  
  private harmonizeResults(results: any[], source: string): UnifiedSearchResults {
    return {
      nodes: results.map(node => ({
        uuid: node.uuid || node.id,
        cosmographIndex: this.mapper.getCosmographIndex(node.uuid),
        label: node.label || node.name,
        nodeType: node.node_type || node.type,
        source: source,
        canTarget: !!this.mapper.getCosmographIndex(node.uuid)
      }))
    };
  }
}
```

### 4. Real-time Synchronization Monitoring

#### Sync Health Dashboard
```typescript
interface SyncHealthMetrics {
  lastSyncTimestamp: number;
  pendingWebhooks: number;
  failedWebhooks: number;
  nodeCountMismatch: number;
  edgeCountMismatch: number;
  averageSyncLatency: number;
}

class SyncMonitor {
  async checkSyncHealth(): Promise<SyncHealthMetrics> {
    const [falkorStats, duckdbStats] = await Promise.all([
      this.getFalkorDBStats(),
      this.getDuckDBStats()
    ]);
    
    return {
      lastSyncTimestamp: this.getLastSyncTime(),
      pendingWebhooks: this.getPendingWebhookCount(),
      failedWebhooks: this.getFailedWebhookCount(),
      nodeCountMismatch: Math.abs(falkorStats.nodeCount - duckdbStats.nodeCount),
      edgeCountMismatch: Math.abs(falkorStats.edgeCount - duckdbStats.edgeCount),
      averageSyncLatency: this.getAverageSyncLatency()
    };
  }
}
```

## Implementation Plan

### Phase 1: Node Mapping System (Week 1)
1. Implement UUID-to-index mapping table in DuckDB
2. Create NodeMapper service in Rust server
3. Update data ingestion to maintain consistent mapping
4. Add mapping persistence and recovery mechanisms

### Phase 2: Webhook Reliability (Week 2)
1. Implement retry mechanism with exponential backoff
2. Add correlation IDs for tracking webhook delivery
3. Create synchronization validation endpoints
4. Add webhook failure alerting and monitoring

### Phase 3: Unified Search (Week 3)
1. Create unified search service in frontend
2. Implement result harmonization and mapping
3. Update search UI to use unified service
4. Add search result validation and error handling

### Phase 4: Monitoring & Recovery (Week 4)
1. Implement sync health monitoring dashboard
2. Create automatic sync recovery mechanisms
3. Add performance metrics and alerting
4. Implement manual sync trigger for emergency recovery

## Success Criteria

### Functional Requirements
1. **Search Consistency**: Both search bars target the same nodes 100% of the time
2. **Data Synchronization**: DuckDB matches FalkorDB state within 5 seconds of updates
3. **Reliability**: Webhook delivery success rate > 99.9%
4. **Recovery**: Automatic sync recovery within 30 seconds of detection

### Performance Requirements
1. **Search Latency**: No additional latency from mapping operations
2. **Sync Latency**: Data appears in cosmograph within 5 seconds of ingestion
3. **Memory Usage**: Node mapping overhead < 10MB for 100k nodes
4. **Throughput**: Support 1000+ concurrent updates without sync failures

## Risk Mitigation

### Data Consistency Risks
1. **Mapping Corruption**: Implement mapping validation and recovery
2. **Partial Updates**: Use atomic transactions for multi-table updates
3. **Race Conditions**: Implement proper locking for concurrent access

### Performance Risks
1. **Memory Growth**: Implement LRU eviction for mapping cache
2. **Sync Bottlenecks**: Use async processing and batching
3. **Network Failures**: Implement circuit breakers and fallback mechanisms

## Monitoring & Alerting

### Key Metrics
1. **Sync Health Score**: Composite metric of data consistency
2. **Webhook Success Rate**: Percentage of successful webhook deliveries
3. **Search Result Accuracy**: Percentage of searches that target correct nodes
4. **Data Freshness**: Time lag between FalkorDB and DuckDB updates

### Alert Conditions
1. Node count mismatch > 1% for more than 5 minutes
2. Webhook failure rate > 1% over 10 minutes
3. Search targeting accuracy < 95%
4. Sync latency > 30 seconds for any update
