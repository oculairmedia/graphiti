# Remote Frontend Development Guide

This guide explains how to run a local development version of the Graphiti frontend on a separate machine while connecting to the production backend services.

## Prerequisites

- Node.js 18+ (recommended: 20.x LTS)
- pnpm (preferred) or npm
- Network access to the Graphiti server (default: `192.168.1.99` or your server IP)
- Git access to the repository

## Server Endpoints

The Graphiti stack exposes these ports that the frontend needs:

| Service | Port | Description |
|---------|------|-------------|
| Nginx (API proxy) | 8088 | Main API gateway - proxies to visualizer and graph API |
| Rust Visualizer | 3000 | Graph data endpoints (nodes, edges, stats) |
| Graph API | 8003 | Python API for ingestion and queries |
| Frontend (prod) | 8085 | Production frontend (nginx serving static files) |

## Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/oculairmedia/graphiti.git
cd graphiti/frontend
```

### 2. Install Dependencies

```bash
# Using pnpm (recommended)
pnpm install

# Or using npm
npm install
```

### 3. Configure Environment

Create a `.env.local` file in the `frontend/` directory:

```bash
# Point to the remote Graphiti server
# Replace with your server's IP or hostname
VITE_API_BASE_URL=http://192.168.1.99:8088
VITE_VISUALIZER_URL=http://192.168.1.99:3000
VITE_GRAPH_API_URL=http://192.168.1.99:8003

# Optional: Enable debug logging
VITE_DEBUG=true
```

### 4. Start Development Server

```bash
# Using pnpm
pnpm dev

# Or using npm
npm run dev
```

The dev server will start at `http://localhost:5173` (or next available port).

## API Endpoints Reference

### Rust Visualizer API (port 3000)

```bash
# Get graph statistics
curl http://192.168.1.99:3000/api/stats

# Get nodes (Apache Arrow format)
curl http://192.168.1.99:3000/api/arrow/nodes

# Get edges (Apache Arrow format)
curl http://192.168.1.99:3000/api/arrow/edges

# Search nodes
curl "http://192.168.1.99:3000/api/search?q=searchterm"

# Get node details
curl http://192.168.1.99:3000/api/nodes/{node_id}

# Get node neighbors
curl http://192.168.1.99:3000/api/nodes/{node_id}/neighbors
```

### Nginx Proxy (port 8088)

The nginx proxy forwards requests:
- `/api/*` → Rust Visualizer (port 3000)
- `/graph/*` → Python Graph API (port 8003)

```bash
# Via nginx proxy
curl http://192.168.1.99:8088/api/stats
curl http://192.168.1.99:8088/api/arrow/nodes
```

### Python Graph API (port 8003)

```bash
# Health check
curl http://192.168.1.99:8003/health

# Search entities
curl "http://192.168.1.99:8003/search?query=term"
```

## Vite Configuration

The frontend uses Vite. Key configuration in `vite.config.ts`:

```typescript
export default defineConfig({
  server: {
    proxy: {
      '/api': {
        target: process.env.VITE_API_BASE_URL || 'http://localhost:8088',
        changeOrigin: true,
      },
    },
  },
  // ... rest of config
});
```

## Troubleshooting

### CORS Issues

If you encounter CORS errors, the backend nginx is configured to allow cross-origin requests. However, for local development, ensure you're using the proxy configuration in Vite.

If issues persist, you can temporarily disable CORS in the browser or use a CORS proxy.

### Connection Refused

1. Check the server is reachable:
   ```bash
   ping 192.168.1.99
   curl http://192.168.1.99:8088/api/stats
   ```

2. Verify services are running on the server:
   ```bash
   # On the server
   docker ps | grep -E "visualizer|nginx|frontend"
   ```

3. Check firewall rules allow the ports (8088, 3000, 8003)

### Gray Screen / React Errors

1. Check browser console (F12) for errors
2. If you see `createContext` errors, ensure React 18 is installed (not React 19)
3. Run `window.__GRAPHITI_LAST_ERROR__` in console for detailed error info

### Visualizer Not Ready

The Rust visualizer needs to load data from FalkorDB on startup. Check status:

```bash
# On the server
curl http://localhost:3000/api/stats

# Should return something like:
# {"node_count":48000,"edge_count":145000,"last_updated":"..."}
```

If edge_count is 0 or very low, the visualizer is still loading.

## Development Workflow

### Hot Reload

The Vite dev server supports hot module replacement (HMR). Changes to React components will reflect immediately without full page reload.

### Building for Production

```bash
# Build production bundle
pnpm build

# Preview production build locally
pnpm preview
```

### Type Checking

```bash
# Run TypeScript type check
pnpm typecheck

# Or
npx tsc --noEmit
```

### Linting

```bash
pnpm lint
```

## Key Files

```
frontend/
├── src/
│   ├── components/
│   │   ├── ErrorBoundary.tsx    # Error handling with debug info
│   │   ├── GraphVisualization/  # Main graph component (uses Cosmograph)
│   │   └── ...
│   ├── hooks/
│   │   └── useGraphData.ts      # Data fetching hooks
│   ├── utils/
│   │   └── logger.ts            # Logging utilities
│   └── App.tsx                  # Main application
├── vite.config.ts               # Vite configuration
├── package.json                 # Dependencies (React 18!)
└── .env.local                   # Local environment (create this)
```

## Notes for Agents

### Testing Changes Remotely

1. Make changes to frontend code
2. Run `pnpm dev` to start local dev server
3. Access `http://localhost:5173` in browser
4. Frontend connects to remote backend at configured IP

### Deploying Changes

After testing locally:

```bash
# Commit changes
git add .
git commit -m "feat(frontend): description of changes"
git push origin main
```

GitHub Actions will automatically build and push a new Docker image. On the server:

```bash
# Pull and deploy new image
docker pull ghcr.io/oculairmedia/graphiti-frontend:latest
docker rm -f graphiti-frontend-1
docker run -d --name graphiti-frontend-1 \
  --network graphiti_graphiti_network \
  -p 8085:80 \
  --restart unless-stopped \
  ghcr.io/oculairmedia/graphiti-frontend:latest
```

### Checking Production Frontend

```bash
# Check what's running
curl -I http://192.168.1.99:8085

# Check if it's serving the app
curl -s http://192.168.1.99:8085 | head -20
```

## React Version Compatibility

**IMPORTANT**: This project uses React 18, NOT React 19.

The `@cosmograph/react` library is not compatible with React 19. If you see errors like:
```
Cannot read properties of undefined (reading 'createContext')
```

Ensure `package.json` has:
```json
{
  "dependencies": {
    "react": "^18",
    "react-dom": "^18"
  }
}
```
