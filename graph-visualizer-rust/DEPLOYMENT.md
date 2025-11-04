# Deployment Guide - Incremental Updates

## Quick Start

The Docker image is building in the background. Once complete, deploy with these commands:

### 1. Check Build Status

```bash
# Monitor build progress
tail -f /opt/stacks/graphiti/graph-visualizer-rust/docker-build.log

# Wait for "Successfully tagged graphiti-rust-visualizer:incremental-updates"
```

### 2. Update Docker Compose

Edit `/opt/stacks/graphiti/docker-compose.yml` to use the new local image:

```yaml
graph-visualizer-rust:
  # Change this:
  # image: ghcr.io/oculairmedia/graphiti-rust-visualizer:feature-chutes-ai-integration
  
  # To this:
  image: graphiti-rust-visualizer:incremental-updates
  
  # Rest of configuration stays the same
  restart: unless-stopped
  deploy:
    resources:
      limits:
        memory: 4G
      reservations:
        memory: 512M
  ports:
    - ${RUST_SERVER_PORT:-3000}:3000
  # ... etc
```

### 3. Deploy the New Version

```bash
cd /opt/stacks/graphiti

# Stop the old container
docker-compose stop graph-visualizer-rust

# Remove the old container
docker-compose rm -f graph-visualizer-rust

# Start the new container with incremental updates
docker-compose up -d graph-visualizer-rust

# Verify it's running
docker-compose ps graph-visualizer-rust
docker-compose logs -f graph-visualizer-rust
```

### 4. Verify Incremental Updates are Working

Watch the logs for these messages:

```
# On first sync after restart:
INFO First sync detected - performing full data load
INFO Fetched 32577 nodes and 90408 edges from FalkorDB
INFO DuckDB loaded successfully with initial data
INFO Initial sync complete. Latest timestamp: "2025-01-04T12:34:56Z"

# On subsequent syncs (every 30 seconds):
INFO Graph changed: nodes 32577 -> 32582, edges 90408 -> 90420
INFO Performing incremental update from timestamp: "2025-01-04T12:34:56Z"
INFO Fetched 5 new nodes and 12 new edges since 2025-01-04T12:34:56Z
INFO ✨ DuckDB updated incrementally: +5 nodes, +12 edges
INFO Incremental update complete. New timestamp: "2025-01-04T12:35:26Z"
INFO Caches cleared after incremental update
```

## Manual Build (if needed)

If the background build failed or you want to rebuild:

```bash
cd /opt/stacks/graphiti/graph-visualizer-rust

# Build locally (takes 10-20 minutes)
docker build -t graphiti-rust-visualizer:incremental-updates .

# Or use the build script (includes validation)
./build.sh
```

## Troubleshooting

### Build Issues

**Problem**: Cargo-chef fails with "can't find bench"
**Solution**: Ensure Dockerfile includes:
```dockerfile
COPY benches ./benches
COPY tests ./tests
```

**Problem**: Build takes too long or hangs
**Solution**: 
- Check available disk space: `df -h`
- Check memory: `free -h`
- Kill and restart: `pkill -f "docker build"`, then retry

### Runtime Issues

**Problem**: Container keeps restarting
**Solution**: Check logs for errors:
```bash
docker-compose logs graph-visualizer-rust | tail -100
```

**Problem**: Incremental updates not working (still doing full reloads)
**Solution**: Check FalkorDB has `created_at` timestamps:
```bash
# Connect to FalkorDB
docker exec -it graphiti-falkordb-1 redis-cli

# Check node timestamps
GRAPH.QUERY graphiti_migration "MATCH (n) WHERE EXISTS(n.created_at) RETURN COUNT(n)"
```

**Problem**: API slow or timing out
**Solution**: 
- Check DuckDB file isn't corrupted: `docker exec graphiti-graph-visualizer-rust-1 ls -lh /app/data/`
- Restart with clean state: `docker-compose down graph-visualizer-rust && docker volume rm graphiti_visualizer_duckdb`

## Performance Monitoring

### Key Metrics to Watch

1. **Update Latency**
   ```bash
   docker-compose logs graph-visualizer-rust | grep "incremental update"
   # Should show ~0.1s or less
   ```

2. **Memory Usage**
   ```bash
   docker stats graphiti-graph-visualizer-rust-1
   # Should stay under 512MB for normal operations
   ```

3. **Cache Hit Rate**
   ```bash
   curl http://localhost:3000/api/cache/stats
   # Look for high hit rates (>80%)
   ```

4. **Update Frequency**
   ```bash
   docker-compose logs graph-visualizer-rust | grep "DuckDB updated incrementally" | tail -20
   # Should show updates every 30s when data changes
   ```

## Rollback Plan

If incremental updates cause issues:

```bash
cd /opt/stacks/graphiti

# Stop new version
docker-compose stop graph-visualizer-rust

# Revert docker-compose.yml to use old image
# image: ghcr.io/oculairmedia/graphiti-rust-visualizer:feature-chutes-ai-integration

# Start old version
docker-compose up -d graph-visualizer-rust
```

## Environment Variables

No new environment variables required. Existing configuration works:

```yaml
environment:
  - FALKORDB_HOST=falkordb
  - FALKORDB_PORT=6379
  - GRAPH_NAME=graphiti_migration
  - NODE_LIMIT=100000
  - EDGE_LIMIT=100000
  - CACHE_ENABLED=true
  - CACHE_TTL_SECONDS=300
  - CACHE_STRATEGY=aggressive
  - RUST_LOG=info
```

## Health Checks

The container includes a health check:

```bash
# Check health status
docker inspect --format='{{.State.Health.Status}}' graphiti-graph-visualizer-rust-1

# Should return: healthy

# View health check logs
docker inspect --format='{{json .State.Health}}' graphiti-graph-visualizer-rust-1 | jq
```

## Production Checklist

Before deploying to production:

- [ ] Build completed successfully
- [ ] All 33 tests passing (`cargo test`)
- [ ] Benchmarks confirm sub-millisecond performance (`cargo bench`)
- [ ] FalkorDB has `created_at` timestamps on all nodes
- [ ] Container starts and becomes healthy
- [ ] First sync completes successfully (full load)
- [ ] Incremental updates working (check logs)
- [ ] API endpoints responding (<100ms latency)
- [ ] WebSocket broadcasting working
- [ ] Memory usage stable (<1GB)
- [ ] Monitoring/alerts configured

## Support

If you encounter issues:

1. **Check logs**: `docker-compose logs -f graph-visualizer-rust`
2. **Check health**: `curl http://localhost:3000/health`
3. **Check stats**: `curl http://localhost:3000/api/stats`
4. **Review documentation**: 
   - [INCREMENTAL_UPDATE_SUCCESS.md](./INCREMENTAL_UPDATE_SUCCESS.md)
   - [INCREMENTAL_UPDATE_COMPLETE.md](./INCREMENTAL_UPDATE_COMPLETE.md)
5. **Git history**: `git log --oneline | head -5` (see recent changes)

---

**Build Status**: Check `/opt/stacks/graphiti/graph-visualizer-rust/docker-build.log`  
**Expected Build Time**: 10-20 minutes (first build), 2-5 minutes (subsequent)  
**Image Name**: `graphiti-rust-visualizer:incremental-updates`  
**Container Name**: `graphiti-graph-visualizer-rust-1`
