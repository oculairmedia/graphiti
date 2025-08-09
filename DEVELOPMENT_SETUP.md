# Development Setup Script

This document provides a complete setup for running the Graphiti stack in development mode with the Rust backend on port 4543 and frontend on port 8082.

## Prerequisites

1. Docker containers running (for FalkorDB):
```bash
cd /opt/stacks/graphiti
docker-compose up -d falkordb
```

2. Ensure FalkorDB is healthy:
```bash
docker-compose ps falkordb
# Should show "healthy" status
```

## Development Script

Create a file `dev.sh` in the project root:

```bash
#!/bin/bash

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Starting Graphiti Development Environment${NC}"

# Check if FalkorDB is running
if ! docker-compose ps falkordb | grep -q "healthy"; then
    echo -e "${RED}FalkorDB is not running or not healthy!${NC}"
    echo "Starting FalkorDB..."
    docker-compose up -d falkordb
    echo "Waiting for FalkorDB to be healthy..."
    sleep 5
fi

# Kill any existing processes on our ports
echo -e "${YELLOW}Cleaning up existing processes...${NC}"
lsof -ti:4543 | xargs -r kill -9 2>/dev/null
lsof -ti:8082 | xargs -r kill -9 2>/dev/null

# Start Rust backend on port 4543
echo -e "${GREEN}Starting Rust backend on port 4543...${NC}"
cd graph-visualizer-rust

# Build in release mode for better performance
cargo build --release

# Start with environment variables for dev
FALKORDB_HOST=localhost \
FALKORDB_PORT=6389 \
GRAPH_NAME=graphiti_migration \
BIND_ADDR=0.0.0.0:4543 \
RUST_LOG=graph_visualizer=debug,tower_http=debug \
NODE_LIMIT=100000 \
EDGE_LIMIT=100000 \
MIN_DEGREE_CENTRALITY=0.0 \
CACHE_ENABLED=false \
CACHE_TTL_SECONDS=0 \
FORCE_FRESH_DATA=true \
cargo run --release &

RUST_PID=$!
echo "Rust backend PID: $RUST_PID"

# Wait for Rust server to be ready
echo "Waiting for Rust server to start..."
while ! curl -s http://localhost:4543/health > /dev/null 2>&1; do
    sleep 1
done
echo -e "${GREEN}Rust backend is ready!${NC}"

# Start Frontend on port 8082
echo -e "${GREEN}Starting Frontend on port 8082...${NC}"
cd ../frontend

# Create a temporary vite config for dev mode
cat > vite.config.dev.ts << 'EOF'
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";
import { componentTagger } from "lovable-tagger";

export default defineConfig(({ mode }) => ({
  server: {
    host: "::",
    port: 8082,
    proxy: {
      '/api': {
        target: 'http://localhost:4543',
        changeOrigin: true,
      },
      '/ws': {
        target: 'http://localhost:4543',
        ws: true,
        changeOrigin: true,
        configure: (proxy, options) => {
          proxy.on('error', (err) => {
            console.log('WebSocket proxy error:', err);
          });
          proxy.on('proxyReqWs', (proxyReq, req, socket) => {
            console.log('WebSocket upgrade request:', req.url);
          });
        },
      },
      '/graphiti': {
        target: 'http://localhost:8003',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/graphiti/, ''),
      },
    },
  },
  plugins: [
    react({
      babel: {
        plugins: ['babel-plugin-react-compiler']
      }
    }),
    mode === 'development' &&
    componentTagger(),
  ].filter(Boolean),
  resolve: {
    alias: {
      "@": path.resolve(process.cwd(), "./src"),
    },
  },
}));
EOF

# Install dependencies if needed
if [ ! -d "node_modules" ]; then
    echo "Installing frontend dependencies..."
    npm install
fi

# Start with custom config
npx vite --config vite.config.dev.ts &

FRONTEND_PID=$!
echo "Frontend PID: $FRONTEND_PID"

# Create cleanup function
cleanup() {
    echo -e "\n${YELLOW}Shutting down development environment...${NC}"
    kill $RUST_PID 2>/dev/null
    kill $FRONTEND_PID 2>/dev/null
    rm -f frontend/vite.config.dev.ts
    echo -e "${GREEN}Development environment stopped${NC}"
    exit 0
}

# Register cleanup on exit
trap cleanup SIGINT SIGTERM

# Wait and show logs
echo -e "\n${GREEN}Development environment is running!${NC}"
echo -e "  Frontend: ${GREEN}http://192.168.50.90:8082${NC}"
echo -e "  Rust API: ${GREEN}http://192.168.50.90:4543${NC}"
echo -e "  FalkorDB: ${GREEN}localhost:6389${NC}"
echo -e "\nPress ${YELLOW}Ctrl+C${NC} to stop all services\n"

# Keep script running and show logs
wait
```

## Alternative: Using Environment Variables

If you prefer to modify the existing configuration files with environment variables:

### Frontend (.env.development)
```bash
# frontend/.env.development
VITE_API_BASE_URL=http://localhost:4543/api
VITE_WS_URL=ws://localhost:4543/ws
VITE_GRAPHITI_WS_URL=ws://localhost:8003/ws
```

### Update RustWebSocketProvider.tsx

The WebSocket provider needs to be updated to use the dev port:

```typescript
// Line 43 in RustWebSocketProvider.tsx
let rustWsUrl = 'ws://localhost:4543/ws';  // Changed from 3000 to 4543
```

Or better, use an environment variable:

```typescript
let rustWsUrl = import.meta.env.VITE_WS_URL || 'ws://localhost:3000/ws';
```

## Manual Commands

If you prefer to run the services manually in separate terminals:

### Terminal 1: Rust Backend
```bash
cd graph-visualizer-rust
FALKORDB_HOST=localhost \
FALKORDB_PORT=6389 \
GRAPH_NAME=graphiti_migration \
BIND_ADDR=0.0.0.0:4543 \
RUST_LOG=graph_visualizer=debug \
CACHE_ENABLED=false \
cargo run --release
```

### Terminal 2: Frontend
```bash
cd frontend
# Update vite.config.ts proxy target to 4543
npm run dev
```

## Docker-based Development

For a hybrid approach where only specific services run locally:

```bash
# Start only FalkorDB and backup services
docker-compose up -d falkordb falkordb-backup

# Run Rust and Frontend locally as above
```

## Troubleshooting

### Port Already in Use
```bash
# Find and kill process on port
lsof -ti:4543 | xargs kill -9
lsof -ti:8082 | xargs kill -9
```

### FalkorDB Connection Issues
```bash
# Check FalkorDB is accessible
redis-cli -p 6389 ping
# Should return "PONG"

# Check graph exists
redis-cli -p 6389 GRAPH.QUERY graphiti_migration "MATCH (n) RETURN COUNT(n)"
```

### WebSocket Connection Failed
1. Check Rust server is running: `curl http://localhost:4543/health`
2. Check browser console for CORS errors
3. Ensure proxy configuration in vite.config.ts is correct

### Graph Not Loading
1. Ensure FalkorDB has data:
```bash
docker exec graphiti-falkordb-1 redis-cli GRAPH.QUERY graphiti_migration "MATCH (n) RETURN n LIMIT 1"
```

2. Check Rust server logs for query errors:
```bash
RUST_LOG=debug cargo run --release 2>&1 | grep ERROR
```

## Performance Optimization

For development with large graphs:

1. **Disable caching** during active development:
```bash
CACHE_ENABLED=false
```

2. **Limit initial data** for faster loads:
```bash
NODE_LIMIT=1000
EDGE_LIMIT=5000
```

3. **Use release builds** for Rust:
```bash
cargo build --release
cargo run --release
```

## Making the Script Executable

```bash
chmod +x dev.sh
./dev.sh
```

## VSCode Launch Configuration

Add to `.vscode/launch.json`:

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Rust Backend Dev",
      "type": "lldb",
      "request": "launch",
      "cargo": {
        "args": ["build", "--release"],
        "filter": {
          "name": "graph-visualizer-rust",
          "kind": "bin"
        }
      },
      "args": [],
      "env": {
        "FALKORDB_HOST": "localhost",
        "FALKORDB_PORT": "6389",
        "BIND_ADDR": "0.0.0.0:4543",
        "GRAPH_NAME": "graphiti_migration",
        "RUST_LOG": "debug"
      },
      "cwd": "${workspaceFolder}/graph-visualizer-rust"
    }
  ]
}
```

## Summary

This setup provides:
- **Rust backend** on port 4543 connected to FalkorDB on localhost:6389
- **Frontend** on port 8082 configured to proxy API/WS requests to Rust on 4543
- **FalkorDB** running in Docker on port 6389
- Hot-reload for both frontend (Vite) and backend (cargo watch optional)
- Proper WebSocket connections for real-time updates
- Environment-based configuration for easy switching between dev/prod