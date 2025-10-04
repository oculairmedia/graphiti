# Local Build Guide for Graphiti

## Overview

This guide explains how to build and deploy Graphiti services locally instead of using pre-built images from GitHub Container Registry.

## Docker Compose Configuration

The `docker-compose.yml` has been configured to build services locally:

### Graph API Service

```yaml
graph:
  build:
    context: .
    dockerfile: Dockerfile
  image: graphiti-api-local:latest
  restart: unless-stopped
  # ... rest of config
```

### Worker Service

```yaml
graphiti-worker:
  build:
    context: .
    dockerfile: Dockerfile
  image: graphiti-api-local:latest
  restart: unless-stopped
  # ... rest of config
```

Both services use the **same Dockerfile** and create the **same image** (`graphiti-api-local:latest`).

## Build Commands

### Quick Build (Recommended)

```bash
# Build all services that have local build configs
docker-compose build

# Build specific service
docker-compose build graph

# Build with no cache (clean build)
docker-compose build --no-cache graph
```

### Direct Docker Build

If you need more control or docker-compose isn't working:

```bash
# Build the image directly
docker build --no-cache -t graphiti-api-local:latest -f Dockerfile .

# Verify the image was created
docker images | grep graphiti-api-local
```

## Deployment Commands

### Start Services

```bash
# Start all services
docker-compose up -d

# Start specific service
docker-compose up -d graph

# Start with rebuild
docker-compose up -d --build graph
```

### Restart After Code Changes

```bash
# Full rebuild and restart
docker-compose build --no-cache graph
docker-compose up -d --force-recreate graph

# Or in one command
docker-compose up -d --build --force-recreate graph
```

### Stop Services

```bash
# Stop specific service
docker-compose stop graph

# Stop all services
docker-compose down

# Stop and remove volumes (careful!)
docker-compose down -v
```

## Verification

### Check Running Services

```bash
# List all services
docker-compose ps

# Check specific service
docker-compose ps graph

# Expected output:
# NAME                  STATUS              PORTS
# graphiti-graph-1      Up 2 minutes        0.0.0.0:8003->8000/tcp
```

### Check Logs

```bash
# Follow logs for specific service
docker-compose logs -f graph

# View last 100 lines
docker-compose logs --tail=100 graph

# Check for errors
docker-compose logs graph | grep -i error
```

### Verify Image

```bash
# Check image exists
docker images | grep graphiti-api-local

# Expected output:
# graphiti-api-local   latest   abc123def456   2 minutes ago   1.2GB

# Inspect image
docker inspect graphiti-api-local:latest
```

## Common Workflows

### Workflow 1: Fix Code and Test

```bash
# 1. Make code changes
vim graphiti_core/utils/replay/candidate_detector.py

# 2. Rebuild
docker-compose build --no-cache graph

# 3. Restart
docker-compose up -d --force-recreate graph

# 4. Wait for ready
docker-compose logs -f graph  # Wait for "startup complete"

# 5. Test
curl -X POST "http://localhost:8003/replay/trigger?dry_run=true" | jq
```

### Workflow 2: Debug Build Issues

```bash
# 1. Clean everything
docker-compose down
docker rmi graphiti-api-local:latest

# 2. Build with verbose output
docker build --no-cache --progress=plain -t graphiti-api-local:latest -f Dockerfile .

# 3. Check for errors in output
# Look for failed steps, missing dependencies, etc.

# 4. If successful, start services
docker-compose up -d
```

### Workflow 3: Compare Local vs Remote

```bash
# 1. Pull remote image
docker pull ghcr.io/oculairmedia/graphiti-api:feature-memory-replay-system

# 2. Tag it for comparison
docker tag ghcr.io/oculairmedia/graphiti-api:feature-memory-replay-system graphiti-api-remote:latest

# 3. Compare image sizes
docker images | grep graphiti-api

# 4. Run remote version
docker run -it --rm graphiti-api-remote:latest python -c "from graphiti_core import __version__; print(__version__)"

# 5. Run local version
docker run -it --rm graphiti-api-local:latest python -c "from graphiti_core import __version__; print(__version__)"
```

## Troubleshooting

### Issue: Build Fails with "No such file or directory"

**Cause:** Build context doesn't include required files.

**Solution:**
```bash
# Check Dockerfile COPY commands
cat Dockerfile | grep COPY

# Verify files exist
ls -la graphiti_core/
ls -la server/

# Build from correct directory
cd u:\graphiti  # Must be in repo root
docker build -t graphiti-api-local:latest -f Dockerfile .
```

### Issue: "Image not found" when starting services

**Cause:** Image wasn't built or has wrong name.

**Solution:**
```bash
# Check if image exists
docker images | grep graphiti-api-local

# If not, build it
docker-compose build graph

# Or build directly
docker build -t graphiti-api-local:latest -f Dockerfile .
```

### Issue: Changes not reflected after rebuild

**Cause:** Docker is using cached layers.

**Solution:**
```bash
# Force clean build
docker-compose build --no-cache graph

# Or with docker directly
docker build --no-cache -t graphiti-api-local:latest -f Dockerfile .

# Also force recreate container
docker-compose up -d --force-recreate graph
```

### Issue: "Port already in use"

**Cause:** Old container still running.

**Solution:**
```bash
# Stop old container
docker-compose stop graph

# Or remove it
docker-compose rm -f graph

# Check what's using the port
netstat -ano | findstr :8003  # Windows
lsof -i :8003                 # Linux/Mac

# Kill the process if needed
taskkill /PID <pid> /F        # Windows
kill -9 <pid>                 # Linux/Mac
```

### Issue: Build is very slow

**Cause:** Large build context or slow network.

**Solution:**
```bash
# Check .dockerignore exists
cat .dockerignore

# Add common excludes if missing:
echo "node_modules/" >> .dockerignore
echo "__pycache__/" >> .dockerignore
echo "*.pyc" >> .dockerignore
echo ".git/" >> .dockerignore
echo "*.log" >> .dockerignore

# Use BuildKit for faster builds
DOCKER_BUILDKIT=1 docker build -t graphiti-api-local:latest -f Dockerfile .
```

## Environment Variables

The local build uses the same environment variables as the remote image:

```bash
# Check current environment
docker-compose config | grep -A 50 "graph:"

# Override environment variables
REPLAY_STALE_DAYS=2 docker-compose up -d graph

# Or edit .env file
echo "REPLAY_STALE_DAYS=2" >> .env
docker-compose up -d graph
```

## Switching Between Local and Remote

### Use Local Build

```yaml
# docker-compose.yml
graph:
  build:
    context: .
    dockerfile: Dockerfile
  image: graphiti-api-local:latest
```

### Use Remote Image

```yaml
# docker-compose.yml
graph:
  image: ghcr.io/oculairmedia/graphiti-api:feature-memory-replay-system
```

### Quick Switch Script

```bash
# switch-to-local.sh
sed -i 's|image: ghcr.io/oculairmedia/graphiti-api.*|build:\n    context: .\n    dockerfile: Dockerfile\n  image: graphiti-api-local:latest|' docker-compose.yml

# switch-to-remote.sh
sed -i 's|build:.*\n.*dockerfile.*\n.*image: graphiti-api-local.*|image: ghcr.io/oculairmedia/graphiti-api:feature-memory-replay-system|' docker-compose.yml
```

## Best Practices

1. **Always use `--no-cache` for critical fixes** to ensure clean build
2. **Check logs after restart** to verify service started correctly
3. **Tag images with versions** for easier rollback: `graphiti-api-local:v1.2.3`
4. **Keep .dockerignore updated** to speed up builds
5. **Use BuildKit** for faster, more efficient builds
6. **Test locally before pushing** to avoid breaking production

## Quick Reference

```bash
# Build
docker-compose build --no-cache graph

# Restart
docker-compose up -d --force-recreate graph

# Logs
docker-compose logs -f graph

# Test
curl http://localhost:8003/health

# Stop
docker-compose stop graph

# Clean up
docker-compose down
docker rmi graphiti-api-local:latest
```

## Related Documentation

- **Fixing Candidate Detection:** `docs/FIXING_CANDIDATE_DETECTION.md`
- **Remaining Work:** `docs/MEMORY_REPLAY_REMAINING_WORK.md`
- **Operations Guide:** `docs/11-memory-replay-operations.md`
- **Main README:** `README.md`

