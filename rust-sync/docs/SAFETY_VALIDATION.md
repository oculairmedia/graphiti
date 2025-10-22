# Safety Validation Guide

## Overview

The Graphiti Rust Sync Service includes comprehensive safety validation to prevent accidental data loss during sync operations. Safety checks run automatically before every sync and will **block dangerous operations** that would result in significant data reduction.

## How It Works

### Pre-Sync Validation

Before each sync operation, the service:

1. **Counts entities** in both source and target databases:
   - Entity nodes
   - Episodic nodes  
   - Community nodes
   - Edges/relationships

2. **Calculates reduction percentages** for each category

3. **Compares against thresholds** (default: 50%)

4. **Blocks the sync** if any reduction exceeds the threshold

5. **Logs detailed reports** showing what would be lost

### Validation Report Example

```
🛡️  Safety Validation Report
   Direction: falkor-to-neo4j
   Status: UNSAFE ❌

   ✅ SAFE: Entity nodes counts match (1000 = 1000)
   ❌ UNSAFE: Episodic nodes would lose 75.0% of data (800 → 200). Threshold: 50.0%
   ✅ SAFE: Community nodes will gain data (50 → 75)  
   ✅ SAFE: Edges within acceptable threshold (5000 → 4800)

   ❌ BLOCKED: 1 of 4 safety checks failed for falkor-to-neo4j sync

Error: Sync blocked by safety validation: ❌ BLOCKED: 1 of 4 safety checks failed for falkor-to-neo4j sync. 
Use FORCE_UNSAFE_SYNC=true to override.
```

## Configuration

### Environment Variables

| Variable | Description | Default | Type |
|----------|-------------|---------|------|
| `SYNC_SAFETY_ENABLED` | Enable/disable safety validation | `true` | boolean |
| `SYNC_SAFETY_NODE_THRESHOLD_PCT` | Max acceptable node reduction (%) | `50.0` | float |
| `SYNC_SAFETY_EDGE_THRESHOLD_PCT` | Max acceptable edge reduction (%) | `50.0` | float |
| `FORCE_UNSAFE_SYNC` | Override safety checks (DANGEROUS) | `false` | boolean |

### Threshold Configuration

The threshold percentage represents the **maximum acceptable data loss**. For example:

- **50% threshold**: Blocks syncs that would lose more than half the data
- **25% threshold**: More strict - blocks syncs losing more than a quarter
- **75% threshold**: More permissive - allows up to 75% data loss
- **0% threshold**: Strictest - blocks ANY data reduction

**Recommended thresholds:**

```bash
# Production (conservative)
export SYNC_SAFETY_NODE_THRESHOLD_PCT=25.0
export SYNC_SAFETY_EDGE_THRESHOLD_PCT=30.0

# Development (moderate)
export SYNC_SAFETY_NODE_THRESHOLD_PCT=50.0
export SYNC_SAFETY_EDGE_THRESHOLD_PCT=50.0

# Testing (permissive) 
export SYNC_SAFETY_NODE_THRESHOLD_PCT=75.0
export SYNC_SAFETY_EDGE_THRESHOLD_PCT=75.0
```

## Common Scenarios

### Scenario 1: Initial Migration (Empty Target)

**Situation**: Migrating from Neo4j (1000 nodes) to empty FalkorDB (0 nodes)

**Result**: ✅ SAFE - Adding data is always safe

```
✅ SAFE: Entity nodes will gain data (0 → 1000)
```

### Scenario 2: Regular Sync (Small Changes)

**Situation**: Neo4j has 1000 nodes, FalkorDB has 995 nodes

**Result**: ✅ SAFE - Only 0.5% reduction, well below 50% threshold

```
✅ SAFE: Entity nodes within acceptable threshold (1000 → 995)
```

### Scenario 3: Dangerous Reduction

**Situation**: Neo4j has 400 nodes, FalkorDB has 1000 nodes (60% reduction)

**Result**: ❌ BLOCKED - 60% reduction exceeds 50% threshold

```
❌ UNSAFE: Entity nodes would lose 60.0% of data (1000 → 400). Threshold: 50.0%
```

### Scenario 4: Intentional Data Cleanup

**Situation**: You intentionally deleted 700 nodes in Neo4j and want to sync

**Options:**

1. **Adjust threshold temporarily:**
   ```bash
   SYNC_SAFETY_NODE_THRESHOLD_PCT=75.0 ./graphiti-sync-rs sync-loop neo4j-to-falkor
   ```

2. **Force override (USE WITH CAUTION):**
   ```bash
   FORCE_UNSAFE_SYNC=true ./graphiti-sync-rs sync-loop neo4j-to-falkor
   ```

## Force Override

### When to Use FORCE_UNSAFE_SYNC

Use `FORCE_UNSAFE_SYNC=true` **ONLY** in these situations:

✅ **Intentional data migration** - Moving from old to new database schema
✅ **Disaster recovery** - Recovering after catastrophic database failure
✅ **Testing environments** - Non-production testing and development
✅ **Planned deletions** - You intentionally removed data and want to sync it

### When NOT to Use

❌ **Production syncs** - Never bypass safety in production without understanding
❌ **Automated scripts** - Don't hardcode force override in automated processes
❌ **Uncertainty** - If you're not 100% sure why sync is blocked, investigate first

### How to Use Safely

1. **Backup first** - Always backup both databases before forcing
   ```bash
   # Backup Neo4j
   neo4j-admin dump --to=/backup/neo4j-backup.dump
   
   # Backup FalkorDB  
   redis-cli --rdb /backup/falkordb-backup.rdb
   ```

2. **Verify intention** - Double-check you WANT this data loss
   ```bash
   # Check counts manually
   neo4j-cypher-shell "MATCH (n:Entity) RETURN count(n)"
   falkordb-cli GRAPH.QUERY graphiti "MATCH (n:Entity) RETURN count(n)"
   ```

3. **Enable force flag**
   ```bash
   FORCE_UNSAFE_SYNC=true ./graphiti-sync-rs sync-loop falkor-to-neo4j
   ```

4. **Verify result**
   ```bash
   # Check final counts
   neo4j-cypher-shell "MATCH (n) RETURN labels(n), count(n)"
   ```

## Disabling Safety

To completely disable safety validation (NOT RECOMMENDED):

```bash
export SYNC_SAFETY_ENABLED=false
./graphiti-sync-rs sync-loop falkor-to-neo4j
```

**Warning**: Disabling safety removes ALL protection against data loss. Only use in controlled environments where data loss is acceptable.

## Safety Metrics

The service tracks safety validation events via Prometheus metrics:

- `graphiti_sync_failure_total{direction="safety_check"}` - Safety check failures
- Logs include full safety reports for audit trails

## Troubleshooting

### "Safety validation failed" Error

**Problem**: Sync is blocked by safety checks

**Solutions**:

1. **Investigate why counts differ**
   ```bash
   # Check source counts
   # Check target counts
   # Determine if reduction is intentional
   ```

2. **If reduction is expected**:
   - Adjust threshold temporarily
   - Or use `FORCE_UNSAFE_SYNC=true`

3. **If reduction is unexpected**:
   - DO NOT override safety
   - Investigate root cause
   - Fix source data issues
   - Restore from backup if needed

### Safety Checks Not Running

**Problem**: Syncs proceed without safety validation

**Check**:

1. Verify safety is enabled:
   ```bash
   echo $SYNC_SAFETY_ENABLED  # Should be 'true' or unset
   ```

2. Check logs for safety reports:
   ```bash
   grep "Safety Validation" sync.log
   ```

3. Ensure not using force override:
   ```bash
   echo $FORCE_UNSAFE_SYNC  # Should be 'false' or unset
   ```

### False Positives

**Problem**: Legitimate syncs being blocked

**Solutions**:

1. **Increase threshold** for expected variance:
   ```bash
   export SYNC_SAFETY_NODE_THRESHOLD_PCT=60.0
   ```

2. **Different thresholds** for nodes vs edges:
   ```bash
   export SYNC_SAFETY_NODE_THRESHOLD_PCT=30.0
   export SYNC_SAFETY_EDGE_THRESHOLD_PCT=50.0  # More permissive for edges
   ```

## Best Practices

### Production Deployments

1. **Enable safety** (default):
   ```bash
   export SYNC_SAFETY_ENABLED=true
   ```

2. **Use conservative thresholds**:
   ```bash
   export SYNC_SAFETY_NODE_THRESHOLD_PCT=25.0
   export SYNC_SAFETY_EDGE_THRESHOLD_PCT=30.0
   ```

3. **Monitor safety metrics**:
   - Alert on `graphiti_sync_failure_total{direction}`
   - Review safety reports in logs

4. **Never hardcode force override**:
   - Use only interactively
   - Require manual approval
   - Document every override

### Development & Testing

1. **Use permissive thresholds**:
   ```bash
   export SYNC_SAFETY_NODE_THRESHOLD_PCT=75.0
   ```

2. **Or disable for rapid iteration**:
   ```bash
   export SYNC_SAFETY_ENABLED=false
   ```

3. **Re-enable before production**:
   - Never deploy with safety disabled
   - Test with production-like thresholds

### Disaster Recovery

1. **Document recovery procedures**:
   - Include force override steps
   - Specify approval requirements
   - List backup restoration steps

2. **Test recovery scenarios**:
   - Practice force override in staging
   - Verify backup restoration works
   - Document lessons learned

## Implementation Details

### Safety Validation Algorithm

```rust
fn validate_reduction(source: usize, target: usize, threshold: f64) -> bool {
    // Adding data is always safe
    if source >= target {
        return true;
    }
    
    // Calculate reduction percentage
    let reduction = ((target - source) as f64 / target as f64) * 100.0;
    
    // Check against threshold
    reduction <= threshold
}
```

### Integration Points

Safety validation runs at these points:

1. **Continuous sync loop** - Before each sync cycle
2. **One-time sync** - Before test-sync operations
3. **Manual sync** - When using sync-loop command

## See Also

- [ENVIRONMENT_VARIABLES.md](ENVIRONMENT_VARIABLES.md) - Full configuration reference
- [README.md](../README.md) - General usage guide
- [src/safety.rs](../src/safety.rs) - Implementation source code
