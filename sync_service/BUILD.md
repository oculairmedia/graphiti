# Sync Service Build & Deployment

## Automated CI/CD Pipeline

The sync service includes a comprehensive GitHub Actions workflow that automatically builds and deploys the service when changes are pushed.

### Trigger Conditions

The build pipeline triggers on:
- **Push to main**: Automatic deployment of production images  
- **Push to feature branches**: Testing builds for development branches like `feature/neo4j-falkordb-hybrid`
- **Pull Requests**: Validation builds for code review
- **Manual Dispatch**: On-demand builds via GitHub UI
- **Workflow Call**: Can be triggered by other workflows

### Build Features

✅ **Path-based Triggers**: Only builds when sync service or core files change
✅ **Multi-layer Caching**: GitHub Actions cache + registry cache for fast builds  
✅ **Multi-platform Support**: Built for linux/amd64 architecture
✅ **Configuration Validation**: Tests configuration loading and validation
✅ **Module Import Testing**: Ensures all Python modules import correctly
✅ **Container Registry**: Publishes to GitHub Container Registry (GHCR)
✅ **Debug Information**: Detailed build logs and directory structure validation

### Container Registry

Images are published to: `ghcr.io/oculairmedia/graphiti-sync`

**Available Tags**:
- `main` - Latest from main branch (production)  
- `<branch-name>` - Feature branch builds
- `<commit-sha>` - Specific commit builds
- `pr-<number>` - Pull request builds

### Build Validation Steps

1. **Repository Checkout** - Fetches source code
2. **Directory Debug** - Lists sync service structure and files
3. **Docker Buildx Setup** - Multi-platform build support
4. **Registry Login** - Authenticate with GitHub Container Registry
5. **Metadata Extraction** - Generate tags and labels
6. **Docker Build & Push** - Build image with caching optimizations
7. **Configuration Validation** - Test config loading and validation
8. **Module Import Testing** - Verify all Python modules load correctly
9. **Output Details** - Display registry information

### Docker Compose Integration

The service is integrated into the main docker-compose.yml with:

```yaml
sync-service:
  image: ghcr.io/oculairmedia/graphiti-sync:main
  restart: unless-stopped
  ports:
    - "${SYNC_HEALTH_PORT:-8080}:8080"
    - "${SYNC_METRICS_PORT:-8081}:8081"
```

### Deployment Commands

```bash
# Deploy latest from main branch
docker-compose pull sync-service
docker-compose up -d sync-service

# Deploy specific version
export SYNC_IMAGE_TAG=feature-neo4j-falkordb-hybrid
docker-compose up -d sync-service

# Check service status
docker-compose logs sync-service
curl http://localhost:8080/health
```

### Environment Configuration

Key environment variables for deployment:

```bash
# Database connections
NEO4J_URI=bolt://neo4j:7687
NEO4J_USER=neo4j  
NEO4J_PASSWORD=graphiti123
FALKORDB_HOST=falkordb
FALKORDB_PORT=6379

# Sync configuration  
SYNC_INTERVAL_SECONDS=300
SYNC_BATCH_SIZE=1000
SYNC_FULL_ON_STARTUP=false
SYNC_ENABLE_CONTINUOUS=true

# Monitoring
SYNC_HEALTH_PORT=8080
SYNC_METRICS_PORT=8081
LOG_LEVEL=INFO
```

### Build Workflow Features Adopted

Our workflow adopts best practices from existing Graphiti workflows:

**From API Server Workflow**:
- Path-based triggering for efficiency
- GitHub Container Registry integration
- Cache optimization strategies
- Metadata extraction and tagging

**From Worker Service Workflow**: 
- Multi-branch support for feature development
- Workflow call capability for orchestration
- Comprehensive environment variable handling

**From Frontend Workflow**:
- Debug steps for troubleshooting builds
- Directory structure validation
- File existence verification

**Enhanced Features Unique to Sync Service**:
- Configuration validation testing
- Module import verification  
- Container health checks
- Comprehensive error handling

### Manual Build Commands

For local development and testing:

```bash
# Build locally
docker build -t sync-service-local ./sync_service

# Test configuration
docker run --rm -e NEO4J_URI=bolt://test:7687 -e FALKORDB_HOST=test \
  sync-service-local python -c "
  from sync_service.config.settings import load_config, validate_config;
  config = load_config(); validate_config(config); print('OK')"

# Test module imports  
docker run --rm sync-service-local python -c "
  import sync_service.main; 
  import sync_service.orchestrator.sync_orchestrator;
  print('All modules imported successfully')"
```

### Monitoring Build Status

- **GitHub Actions**: View build status in repository Actions tab
- **Container Registry**: Check published images at ghcr.io
- **Health Endpoints**: Test deployed service at `/health` endpoint
- **Metrics**: Monitor performance at `/metrics` endpoint

This automated pipeline ensures consistent, tested, and validated deployments of the sync service across all environments.