# FalkorDB Data Corruption: Comprehensive Root Cause Analysis & Fix Plan

## Executive Summary

**Status: 🔴 CRITICAL - Data corruption causing system instability**

The FalkorDB system is experiencing severe data corruption issues that manifest as:
- Memory exhaustion leading to container crashes
- Infinite loops during graph traversal
- Database name mismatches causing data inconsistency
- Cross-graph deduplication creating circular references
- Lack of query limits allowing runaway operations

## Root Cause Analysis

### 1. **Database Name Mismatch Crisis**
**Severity: Critical**

The system has inconsistent database naming across services:
- **Core Driver Default**: `default_db` (line 83 in `falkordb_driver.py`)
- **Services Configuration**: `graphiti_migration` (multiple docker-compose files)
- **Result**: Data written to different databases, causing corruption and inconsistency

### 2. **Cross-Graph Deduplication Bug**
**Severity: Critical**

The deduplication logic in `node_operations.py` is restricted to same `group_id`:
```python
# Lines 275-284: Exact match query restricts to same group
WHERE n.name = $name AND n.group_id = $group_id  # ← RESTRICTS TO SAME GROUP
```
This prevents proper cross-graph deduplication while allowing duplicate nodes to accumulate.

### 3. **Memory Exhaustion Pattern**
**Severity: High**

Multiple memory limit configurations exist but are inconsistent:
- Docker containers: 1GB-4GB limits
- FalkorDB internal: 2GB-6GB maxmemory
- No query-level timeouts or complexity limits

### 4. **Circular Reference Creation**
**Severity: High**

The merge operations in `merge_node_into()` can create circular references when:
- Cross-graph merges occur without proper validation
- Edge transfer logic doesn't check for existing relationships
- No cycle detection during graph operations

### 5. **Concurrent Write Conflicts**
**Severity: Medium**

Multiple services write simultaneously without coordination:
- Graph API service
- Visualizer Rust service  
- Centrality calculation service
- Search service

## Immediate Actions Required

### Phase 1: Emergency Stabilization (Day 1)

#### 1.1 Stop All Services and Clear Corrupted Data
```bash
# Stop all Graphiti services
docker-compose down
docker stop graphiti-falkordb-1 2>/dev/null || true

# Clear corrupted FalkorDB data in LXC container
# SSH to LXC container at 192.168.50.113
ssh root@192.168.50.113
systemctl stop falkordb
rm -rf /var/lib/falkordb/data/*
systemctl start falkordb
```

#### 1.2 Fix Database Name Consistency
**File**: `graphiti_core/driver/falkordb_driver.py`
```python
# Line 83: Change default database name
database: str = 'graphiti_migration',  # Changed from 'default_db'
```

#### 1.3 Configure Memory Limits and Query Timeouts
**File**: `falkordb-config.conf`
```conf
# Strict memory management
maxmemory 2gb
maxmemory-policy allkeys-lru

# Query timeouts (new)
timeout 30
tcp-keepalive 60

# Prevent runaway queries
lua-time-limit 5000
```

### Phase 2: Data Validation Implementation (Days 2-3)

#### 2.1 Add Query Complexity Limits
**File**: `graphiti_core/driver/falkordb_driver.py`
```python
async def execute_query(self, cypher_query_, **kwargs: Any):
    # Add query timeout and complexity validation
    if len(cypher_query_) > 10000:  # Prevent massive queries
        raise ValueError("Query too complex")
    
    # Set query timeout
    kwargs['timeout'] = kwargs.get('timeout', 30)
    
    # Existing code...
```

#### 2.2 Implement Cycle Detection
**File**: `graphiti_core/utils/maintenance/node_operations.py`
```python
async def validate_merge_safety(driver, canonical_uuid: str, duplicate_uuid: str) -> bool:
    """Validate that merging won't create cycles."""
    cycle_check_query = """
    MATCH path = (n1:Entity {uuid: $canonical})-[*1..5]-(n2:Entity {uuid: $duplicate})
    RETURN count(path) as cycle_count
    """
    result = await driver.execute_query(
        cycle_check_query,
        canonical=canonical_uuid,
        duplicate=duplicate_uuid
    )
    return result[0][0]['cycle_count'] == 0
```

### Phase 3: Cross-Graph Deduplication Fix (Days 4-5)

#### 3.1 Enable Cross-Graph Deduplication
**File**: `graphiti_core/utils/maintenance/node_operations.py`

Modify the exact match query (lines 275-284):
```python
# Remove group_id restriction for cross-graph deduplication
exact_query = """
MATCH (n:Entity)
WHERE n.name = $name
RETURN n
ORDER BY n.created_at
LIMIT 1
"""
```

#### 3.2 Add Cross-Graph Merge Safety
```python
async def merge_node_into(
    driver,
    canonical_uuid: str,
    duplicate_uuid: str,
    maintain_audit_trail: bool = True,
    recalculate_centrality: bool = True,
    allow_cross_graph_merge: bool = True,  # Enable by default
) -> dict[str, Any]:
    # Add cycle detection before merge
    if not await validate_merge_safety(driver, canonical_uuid, duplicate_uuid):
        raise ValueError(f"Merge would create cycle: {duplicate_uuid} -> {canonical_uuid}")
    
    # Existing merge logic...
```

### Phase 4: Monitoring and Prevention (Days 6-7)

#### 4.1 Add Health Checks
**File**: `health_monitor.py` (new)
```python
async def check_graph_health(driver):
    """Monitor for corruption indicators."""
    checks = {
        'node_count': await get_node_count(driver),
        'edge_count': await get_edge_count(driver),
        'circular_refs': await detect_circular_references(driver),
        'orphaned_edges': await count_orphaned_edges(driver),
        'memory_usage': await get_memory_usage(driver)
    }
    
    # Alert if anomalies detected
    if checks['circular_refs'] > 0:
        logger.error(f"Circular references detected: {checks['circular_refs']}")
    
    return checks
```

#### 4.2 Implement Backup Strategy
```bash
# Automated backup script
#!/bin/bash
# backup_falkordb.sh
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/backups/falkordb"
mkdir -p $BACKUP_DIR

# Create backup
redis-cli --rdb $BACKUP_DIR/falkordb_backup_$DATE.rdb
```

## Configuration Changes Required

### Docker Compose Updates
**File**: `docker-compose.yml`
```yaml
environment:
  - FALKORDB_HOST=192.168.50.113
  - FALKORDB_PORT=6379
  - GRAPH_NAME=graphiti_migration  # Consistent naming
  - FALKORDB_MAX_MEMORY=2gb
  - QUERY_TIMEOUT=30
```

### Environment Variables
```bash
# Add to .env
FALKORDB_DATABASE=graphiti_migration
FALKORDB_MAX_MEMORY=2gb
FALKORDB_QUERY_TIMEOUT=30
ENABLE_CROSS_GRAPH_DEDUPLICATION=true
ENABLE_CYCLE_DETECTION=true
```

## Testing Strategy

### 1. Data Integrity Tests
```python
async def test_no_circular_references():
    """Ensure no circular references exist."""
    query = """
    MATCH (n)-[*2..10]->(n)
    RETURN count(n) as cycles
    """
    result = await driver.execute_query(query)
    assert result[0][0]['cycles'] == 0
```

### 2. Memory Usage Tests
```python
async def test_memory_limits():
    """Verify memory usage stays within limits."""
    info = await driver.execute_query("CALL dbms.queryJmx('java.lang:type=Memory')")
    memory_used = info['HeapMemoryUsage']['used']
    assert memory_used < 2_000_000_000  # 2GB limit
```

### 3. Cross-Graph Deduplication Tests
```python
async def test_cross_graph_deduplication():
    """Verify entities are deduplicated across graphs."""
    # Create same entity in different groups
    entity1 = EntityNode(name="John Doe", group_id="group1")
    entity2 = EntityNode(name="John Doe", group_id="group2")
    
    # Should be merged into single entity
    result = await resolve_extracted_nodes([entity1, entity2])
    assert len(result[0]) == 1  # Only one entity remains
```

## Success Metrics

1. **Zero Memory Crashes**: No OOM kills for 7 days
2. **Query Performance**: All queries complete within 30 seconds
3. **Data Consistency**: No duplicate entities across graphs
4. **System Stability**: 99.9% uptime for 30 days

## Risk Mitigation

### Rollback Plan
1. Restore from backup if corruption persists
2. Revert to previous configuration
3. Implement gradual rollout of fixes

### Monitoring Alerts
1. Memory usage > 80%
2. Query duration > 25 seconds
3. Circular reference detection
4. Duplicate entity count increase

## Timeline

- **Day 1**: Emergency stabilization
- **Days 2-3**: Data validation implementation  
- **Days 4-5**: Cross-graph deduplication fix
- **Days 6-7**: Monitoring and prevention
- **Week 2**: Testing and validation
- **Week 3**: Production deployment with monitoring

This comprehensive plan addresses all identified root causes and provides a systematic approach to eliminating data corruption while preventing future occurrences.

## Critical Implementation Details

### Database Schema Validation

#### Current Schema Issues
Based on the codebase analysis, several schema inconsistencies exist:

1. **Temporal Fields Mismatch**: The system has inconsistent handling of `created_at` vs `created_at_timestamp`
2. **Vector Storage**: FalkorDB vector storage requires `vecf32()` conversion but this isn't consistently applied
3. **Edge Properties**: Edge merge operations don't properly validate property schemas

#### Schema Fixes Required

**File**: `graphiti_core/utils/maintenance/schema_validator.py` (new)
```python
async def validate_node_schema(driver, node_data: dict) -> bool:
    """Validate node data against expected schema."""
    required_fields = ['uuid', 'name', 'created_at']

    for field in required_fields:
        if field not in node_data:
            logger.error(f"Missing required field: {field}")
            return False

    # Validate UUID format
    try:
        uuid.UUID(node_data['uuid'])
    except ValueError:
        logger.error(f"Invalid UUID format: {node_data['uuid']}")
        return False

    return True

async def fix_temporal_field_consistency(driver):
    """Fix created_at vs created_at_timestamp inconsistencies."""
    query = """
    MATCH (n:Entity)
    WHERE n.created_at IS NULL AND n.created_at_timestamp IS NOT NULL
    SET n.created_at = datetime({epochSeconds: n.created_at_timestamp})
    RETURN count(n) as fixed_nodes
    """
    result = await driver.execute_query(query)
    logger.info(f"Fixed temporal fields for {result[0][0]['fixed_nodes']} nodes")
```

### Memory Management Deep Dive

#### Current Memory Issues
1. **Unbounded Query Results**: No LIMIT clauses on large graph traversals
2. **Vector Embedding Storage**: Large embedding vectors consume excessive memory
3. **Cache Accumulation**: Frontend cache grows without bounds

#### Memory Optimization Implementation

**File**: `graphiti_core/driver/falkordb_driver.py`
```python
class QueryLimiter:
    """Enforce query limits to prevent memory exhaustion."""

    MAX_RESULT_SIZE = 10000
    MAX_TRAVERSAL_DEPTH = 5

    @staticmethod
    def validate_query(query: str) -> str:
        """Add safety limits to queries."""
        query_upper = query.upper()

        # Add LIMIT if missing
        if 'LIMIT' not in query_upper and 'RETURN' in query_upper:
            query += f" LIMIT {QueryLimiter.MAX_RESULT_SIZE}"

        # Prevent deep traversals
        if query.count('-[*') > 0:
            # Extract traversal depth and limit it
            import re
            pattern = r'-\[\*(\d+)\.\.(\d+)\]-'
            matches = re.findall(pattern, query)
            for start, end in matches:
                if int(end) > QueryLimiter.MAX_TRAVERSAL_DEPTH:
                    query = query.replace(
                        f'-[*{start}..{end}]-',
                        f'-[*{start}..{QueryLimiter.MAX_TRAVERSAL_DEPTH}]-'
                    )

        return query

async def execute_query(self, cypher_query_, **kwargs: Any):
    # Apply query limits
    cypher_query_ = QueryLimiter.validate_query(cypher_query_)

    # Set memory limit for this query
    kwargs['maxmemory'] = kwargs.get('maxmemory', '100mb')

    # Existing implementation...
```

### Edge Validation System

#### Current Edge Issues
1. **Orphaned Edges**: Edges pointing to non-existent nodes
2. **Duplicate Edges**: Multiple edges between same nodes
3. **Circular Dependencies**: Self-referencing edge chains

#### Edge Validation Implementation

**File**: `graphiti_core/utils/maintenance/edge_validator.py` (new)
```python
async def validate_edge_integrity(driver) -> dict:
    """Comprehensive edge validation."""

    # Check for orphaned edges
    orphaned_query = """
    MATCH (n1)-[r]->(n2)
    WHERE n1 IS NULL OR n2 IS NULL
    RETURN count(r) as orphaned_edges
    """

    # Check for duplicate edges
    duplicate_query = """
    MATCH (n1)-[r1]->(n2), (n1)-[r2]->(n2)
    WHERE r1 <> r2 AND type(r1) = type(r2)
    RETURN count(r1) as duplicate_edges
    """

    # Check for self-loops
    self_loop_query = """
    MATCH (n)-[r]->(n)
    RETURN count(r) as self_loops
    """

    results = {}
    results['orphaned'] = await driver.execute_query(orphaned_query)
    results['duplicates'] = await driver.execute_query(duplicate_query)
    results['self_loops'] = await driver.execute_query(self_loop_query)

    return results

async def fix_orphaned_edges(driver):
    """Remove edges pointing to non-existent nodes."""
    cleanup_query = """
    MATCH (n1)-[r]->(n2)
    WHERE n1 IS NULL OR n2 IS NULL
    DELETE r
    RETURN count(r) as cleaned_edges
    """
    result = await driver.execute_query(cleanup_query)
    logger.info(f"Cleaned {result[0][0]['cleaned_edges']} orphaned edges")
```

### Service Coordination

#### Current Coordination Issues
1. **Race Conditions**: Multiple services modifying same nodes
2. **Transaction Conflicts**: No distributed locking
3. **Cache Invalidation**: Inconsistent cache states across services

#### Coordination Implementation

**File**: `graphiti_core/coordination/service_coordinator.py` (new)
```python
import asyncio
import redis
from contextlib import asynccontextmanager

class ServiceCoordinator:
    """Coordinate operations across multiple Graphiti services."""

    def __init__(self, redis_url: str):
        self.redis = redis.from_url(redis_url)
        self.lock_timeout = 30  # seconds

    @asynccontextmanager
    async def node_lock(self, node_uuid: str):
        """Distributed lock for node operations."""
        lock_key = f"graphiti:lock:node:{node_uuid}"
        lock_acquired = False

        try:
            # Try to acquire lock
            lock_acquired = self.redis.set(
                lock_key,
                "locked",
                nx=True,
                ex=self.lock_timeout
            )

            if not lock_acquired:
                raise RuntimeError(f"Could not acquire lock for node {node_uuid}")

            yield

        finally:
            if lock_acquired:
                self.redis.delete(lock_key)

    async def invalidate_caches(self, node_uuids: list[str]):
        """Invalidate caches across all services."""
        for uuid in node_uuids:
            cache_key = f"graphiti:cache:node:{uuid}"
            self.redis.delete(cache_key)

        # Notify services of cache invalidation
        self.redis.publish("graphiti:cache:invalidate", ",".join(node_uuids))
```

## Emergency Recovery Procedures

### Data Recovery from Backup
```bash
#!/bin/bash
# emergency_recovery.sh

echo "🚨 EMERGENCY FALKORDB RECOVERY PROCEDURE"
echo "========================================"

# 1. Stop all services
echo "Stopping all Graphiti services..."
docker-compose down
ssh root@192.168.50.113 "systemctl stop falkordb"

# 2. Backup current corrupted state
echo "Backing up corrupted state for analysis..."
ssh root@192.168.50.113 "cp -r /var/lib/falkordb/data /var/lib/falkordb/data.corrupted.$(date +%Y%m%d_%H%M%S)"

# 3. Restore from latest backup
echo "Restoring from latest backup..."
LATEST_BACKUP=$(ssh root@192.168.50.113 "ls -t /backups/falkordb/*.rdb | head -1")
ssh root@192.168.50.113 "cp $LATEST_BACKUP /var/lib/falkordb/data/dump.rdb"

# 4. Start with memory limits
echo "Starting FalkorDB with strict memory limits..."
ssh root@192.168.50.113 "systemctl start falkordb"

# 5. Verify recovery
echo "Verifying recovery..."
sleep 10
redis-cli -h 192.168.50.113 -p 6379 ping
redis-cli -h 192.168.50.113 -p 6379 GRAPH.LIST

echo "✅ Recovery complete. Monitor system closely."
```

### Corruption Detection Script
```python
#!/usr/bin/env python3
# detect_corruption.py

async def detect_corruption_patterns(driver):
    """Detect common corruption patterns."""

    corruption_indicators = {}

    # 1. Circular reference detection
    circular_query = """
    MATCH path = (n)-[*2..5]->(n)
    RETURN count(path) as circular_refs, collect(n.uuid)[0..10] as sample_nodes
    """
    result = await driver.execute_query(circular_query)
    corruption_indicators['circular_refs'] = result[0][0]

    # 2. Orphaned node detection
    orphaned_query = """
    MATCH (n:Entity)
    WHERE NOT (n)-[]-()
    RETURN count(n) as orphaned_nodes
    """
    result = await driver.execute_query(orphaned_query)
    corruption_indicators['orphaned_nodes'] = result[0][0]['orphaned_nodes']

    # 3. Duplicate entity detection
    duplicate_query = """
    MATCH (n1:Entity), (n2:Entity)
    WHERE n1.name = n2.name AND n1.uuid <> n2.uuid
    RETURN count(n1) as potential_duplicates
    """
    result = await driver.execute_query(duplicate_query)
    corruption_indicators['duplicates'] = result[0][0]['potential_duplicates']

    # 4. Memory usage check
    memory_query = "CALL dbms.queryJmx('java.lang:type=Memory')"
    try:
        result = await driver.execute_query(memory_query)
        memory_used = result[0][0]['HeapMemoryUsage']['used']
        corruption_indicators['memory_usage_mb'] = memory_used / 1024 / 1024
    except:
        corruption_indicators['memory_usage_mb'] = "unknown"

    return corruption_indicators

if __name__ == "__main__":
    import asyncio
    from graphiti_core.driver.falkordb_driver import FalkorDriver

    async def main():
        driver = FalkorDriver(
            host="192.168.50.113",
            port=6379,
            database="graphiti_migration"
        )

        indicators = await detect_corruption_patterns(driver)

        print("🔍 CORRUPTION DETECTION REPORT")
        print("=" * 40)
        for key, value in indicators.items():
            status = "🔴" if (
                (key == 'circular_refs' and value['circular_refs'] > 0) or
                (key == 'orphaned_nodes' and value > 100) or
                (key == 'duplicates' and value > 50) or
                (key == 'memory_usage_mb' and value > 1500)
            ) else "✅"
            print(f"{status} {key}: {value}")

    asyncio.run(main())
```

This comprehensive plan now includes detailed implementation steps, emergency procedures, and corruption detection mechanisms to ensure complete resolution of the FalkorDB data corruption issues.
