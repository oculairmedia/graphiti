# Graphiti Frontend

React-based frontend for the Graphiti Knowledge Graph Visualization Platform, using Cosmograph for GPU-accelerated rendering.

## Overview

This frontend connects directly to the Rust visualization server for optimal performance, bypassing the Python backend for graph visualization while maintaining compatibility with Graphiti's data ingestion capabilities.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Frontend (React)                         │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │   Cosmograph    │  │  React Query    │  │   Zustand       │  │
│  │   (WebGL)       │  │  (Data Fetch)   │  │   (State)       │  │
│  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘  │
│           │                    │                    │           │
│  ┌────────┴────────────────────┴────────────────────┴────────┐  │
│  │              RustWebSocketProvider (Active)                │  │
│  │              - Real-time graph updates                     │  │
│  │              - Delta sync (add/update/delete)              │  │
│  └────────────────────────────┬─────────────────────────────┘  │
└───────────────────────────────┼─────────────────────────────────┘
                                │
                    ┌───────────┴───────────┐
                    │                       │
            ┌───────▼───────┐       ┌───────▼───────┐
            │ Rust Server   │       │ Python Server │
            │ (port 3000)   │       │ (port 8003)   │
            │ ✅ Active     │       │ ⚠️ Deprecated │
            │               │       │               │
            │ • Graph data  │       │ • Mutations   │
            │ • WebSocket   │       │ • Ingestion   │
            │ • Search      │       │ • node_access │
            │ • Centrality  │       │   (planned    │
            └───────┬───────┘       │    move)      │
                    │               └───────┬───────┘
                    │                       │
                    └───────────┬───────────┘
                                │
                        ┌───────▼───────┐
                        │   FalkorDB    │
                        │  (port 6379)  │
                        └───────────────┘
```

## WebSocket Architecture

### Active Provider: RustWebSocketProvider

The frontend uses `RustWebSocketProvider` for all real-time communication:

```
src/contexts/RustWebSocketProvider.tsx (334 lines)
    │
    ├── Connects to: ws://localhost:3000/ws
    ├── Events: graph:delta, graph:update, stats:update
    └── Used by: useGraphWebSocket, useRealtimeDataSync
```

### Deprecated: WebSocketProvider (Python)

The Python WebSocket provider is **no longer in the provider tree** and should not be used:

```
src/contexts/WebSocketProvider.tsx (256 lines) - ⚠️ NOT MOUNTED
src/hooks/useWebSocket.ts (313 lines) - ⚠️ ORPHANED
src/hooks/useRustWebSocket.ts (155 lines) - ❌ DEAD CODE (never imported)
```

**Note**: The `node_access` event (search highlighting) was originally from Python WebSocket. This feature is planned to move to Rust WebSocket as part of search consolidation.

### Hook Hierarchy

```
useGraphWebSocket (752 lines) - High-level unified hook
    │
    ├── useRustWebSocketContext() - Active, provides real-time updates
    │
    └── useWebSocketContext() - ⚠️ Would throw if called (provider not mounted)

Dependent hooks (may need refactoring):
├── useGraphLiveCounts.ts - Uses useWebSocketContext
├── useGraphNodeAccessEvents.ts - Uses useWebSocketContext  
├── useGraphCache.ts - Uses useWebSocketContext
├── useDuckDBService.ts - Uses useWebSocketContext
└── useRealtimeDataSync.ts - Uses useRustWebSocket ✅
```

## Development

### Prerequisites

- Node.js 18+ and npm
- Rust visualization server running at `localhost:3000`
- FalkorDB instance

### Setup

```bash
# Install dependencies
npm install

# Start development server
npm run dev

# The frontend will be available at http://localhost:8084
```

### Environment Variables

Create a `.env` file if you need to override defaults:

```env
VITE_RUST_API=http://localhost:3000
VITE_RUST_WS=ws://localhost:3000/ws
```

## Features

- **GPU-Accelerated Rendering**: WebGL-based visualization via Cosmograph
- **Real-time Updates**: WebSocket connection for live graph changes
- **Advanced Search**: Full-text search with node highlighting
- **Interactive Controls**: Pan, zoom, node selection, multiple layouts
- **Centrality Metrics**: PageRank, betweenness, degree centrality
- **Performance**: Handles 50,000+ nodes at 60 FPS

## API Integration

The frontend connects to these Rust server endpoints:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/visualize` | GET | Fetch graph data (nodes + edges) |
| `/api/stats` | GET | Get graph statistics |
| `/api/search` | POST | Search nodes |
| `/api/centrality` | GET | Get centrality metrics |
| `/health` | GET | Health check |
| `/ws` | WS | Real-time updates |

## Project Structure

```
src/
├── api/                    # API client and types
│   ├── graphClient.ts      # Rust API client
│   └── types.ts            # TypeScript types
├── components/             # React components
│   ├── GraphCanvasV2.tsx   # Main Cosmograph integration
│   ├── SearchBar.tsx       # Search interface
│   └── ui/                 # Shadcn UI components
├── contexts/               # React context providers
│   ├── RustWebSocketProvider.tsx  # ✅ Active WebSocket
│   ├── WebSocketProvider.tsx      # ⚠️ Deprecated
│   ├── GraphConfigContext.tsx     # Graph configuration
│   └── DuckDBProvider.tsx         # DuckDB integration
├── hooks/                  # Custom React hooks
│   ├── useGraphWebSocket.ts       # Unified WebSocket hook
│   ├── useGraphDataQuery.ts       # Data fetching
│   ├── useGraphSelection.ts       # Node selection
│   ├── useGraphCamera.ts          # Camera controls
│   └── useCosmograph*.ts          # Cosmograph integration
├── lib/                    # Utilities
└── pages/                  # Page components
```

## Testing

```bash
# Run tests
npm test

# Run tests with UI
npm run test:ui

# Run tests with coverage
npm run test:coverage
```

## Building

```bash
# Production build
npm run build

# Preview production build
npm run preview
```

## Known Issues

1. **Python WebSocket Orphaned**: Several hooks import `useWebSocketContext()` but the provider is not mounted. These will throw if invoked.

2. **node_access Feature**: Search highlighting via `node_access` events is currently disabled pending migration to Rust WebSocket.

## Contributing

See [CONTRIBUTING.md](../CONTRIBUTING.md) for development guidelines.
