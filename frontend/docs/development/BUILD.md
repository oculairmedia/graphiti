# Building Graphiti Frontend Container

This guide helps you build the Graphiti frontend Docker container on a system with more resources.

## Prerequisites

- Docker installed and running
- Access to the source files at `/opt/stacks/graphiti/frontend`
- At least 4GB available RAM
- At least 5GB available disk space

## Build Instructions

### 1. Navigate to the frontend directory
```bash
cd /opt/stacks/graphiti/frontend
```

### 2. Clean build with no cache
```bash
# Build using docker-compose (preferred)
docker-compose build --no-cache frontend

# OR build directly with docker
docker build --no-cache -f Dockerfile.simple -t graphiti-frontend .
```

### 3. If memory issues persist, try these alternatives:

#### Option A: Build with limited parallelism
```bash
docker build --no-cache --memory=2g --memory-swap=4g -f Dockerfile.simple -t graphiti-frontend .
```

#### Option B: Multi-stage build with cleanup between stages
```bash
# Build just the builder stage first
docker build --no-cache --target builder -f Dockerfile.simple -t graphiti-frontend-builder .

# Then build the final image
docker build --no-cache -f Dockerfile.simple -t graphiti-frontend .
```

### 4. Save the built image for transfer
```bash
# Save the image to a tar file
docker save graphiti-frontend:latest | gzip > graphiti-frontend.tar.gz

# Transfer back to the original system and load:
# docker load < graphiti-frontend.tar.gz
```

## Alternative: Build without Docker

If Docker continues to have issues, you can build the static files directly:

```bash
# Install dependencies
npm install --force

# Build production files
npm run build

# The built files will be in the dist/ directory
# You can serve these with any static file server
```

## Container Details

The frontend container uses:
- Base image: `node:18-alpine`
- Build process: Vite
- Production server: `serve` package
- Exposed port: 3000
- Static files location: `/app/dist`

## Environment Variables

No environment variables are required for the frontend build, but these are used at runtime:
- API proxy is configured in `vite.config.ts` to forward `/api` requests to the Rust server

## Notes

- The build process may show warnings about chunk sizes >500KB - this is normal
- The CSS import warning can be ignored - it doesn't affect functionality
- Build time is typically 15-30 seconds on a modern system
- The final image size should be around 200-300MB

## Troubleshooting

If you encounter "cannot allocate memory" errors:
1. Check available memory: `free -h`
2. Stop unnecessary containers: `docker ps -a` and `docker stop <container_id>`
3. Prune Docker resources: `docker system prune -f` (careful not to delete important data)
4. Restart Docker daemon: `sudo systemctl restart docker`
5. Use a machine with more available RAM

## Success Verification

After building, verify the image:
```bash
docker images | grep graphiti-frontend
```

You should see the newly built image with a recent timestamp.