#!/bin/bash

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Starting Graphiti Development Environment${NC}"

# Check if FalkorDB is running
if ! docker-compose ps falkordb 2>/dev/null | grep -q "healthy"; then
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
  define: {
    'import.meta.env.VITE_RUST_WS_URL': JSON.stringify('ws://localhost:4543/ws'),
    'import.meta.env.VITE_RUST_WS_PORT': JSON.stringify('4543'),
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