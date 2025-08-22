# Using GitHub Actions to Build Frontend Container

This setup uses GitHub Actions to build the Docker container, avoiding local resource constraints.

## Setup Instructions

### 1. Push the workflow to GitHub
```bash
git add .github/workflows/build-frontend.yml
git commit -m "feat: add GitHub Actions workflow for frontend container builds"
git push origin feature/real-time-node-glow
```

### 2. Trigger the build
The build will trigger automatically on push, or you can trigger manually:
- Go to GitHub repository → Actions → "Build and Push Frontend Container"
- Click "Run workflow" → Select branch → Run

### 3. Monitor the build
- Check the Actions tab on GitHub for build progress
- Build typically takes 2-5 minutes

### 4. Pull and use the built image

After the build completes:

```bash
# Login to GitHub Container Registry (one-time setup)
echo $GITHUB_TOKEN | docker login ghcr.io -u USERNAME --password-stdin

# Pull the image
docker pull ghcr.io/oculairmedia/graphiti-frontend:feature-real-time-node-glow

# Use with docker-compose override
docker-compose -f docker-compose.yml -f docker-compose.ghcr.yml up -d frontend

# Or run directly
docker run -d -p 8080:3000 ghcr.io/oculairmedia/graphiti-frontend:feature-real-time-node-glow
```

## Available Tags

- `latest` - Latest from main branch
- `main` - Main branch builds
- `feature-real-time-node-glow` - Feature branch builds
- `main-SHA` - Specific commit on main
- `feature-real-time-node-glow-SHA` - Specific commit on feature branch

## Benefits

1. **No local resource constraints** - GitHub provides clean build environment
2. **Automatic builds** on every push
3. **Container registry included** - Images stored in GitHub Packages
4. **Multi-platform builds** possible (amd64, arm64)
5. **Build caching** for faster subsequent builds

## Troubleshooting

If the image pull fails:
1. Ensure you're logged into ghcr.io
2. Check if the repository is public or you have access
3. Verify the image tag exists in the packages section of the repo

## Local Development

You can still build locally when needed:
```bash
npm install
npm run dev  # Development server
npm run build  # Production build
```