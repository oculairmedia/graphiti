# Graphiti Frontend

React-based frontend for the Graphiti Knowledge Graph Visualization Platform, using Cosmograph for GPU-accelerated rendering.

## Overview

This frontend connects directly to the Rust visualization server for optimal performance, bypassing the Python backend for graph visualization while maintaining compatibility with Graphiti's data ingestion capabilities.

## Architecture

```
Frontend (React + Cosmograph)
    ↓
Rust Server (port 3000)
    ↓
FalkorDB
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

# The frontend will be available at http://localhost:8080
```

### Environment Variables

Create a `.env` file if you need to override defaults:

```env
VITE_RUST_API=http://localhost:3000
```

## Features

- **GPU-Accelerated Rendering**: WebGL-based visualization via Cosmograph
- **Real-time Updates**: WebSocket connection for live graph changes
- **Advanced Search**: Full-text search with node highlighting
- **Interactive Controls**: Pan, zoom, node selection, multiple layouts
- **Performance**: Handles 5000+ nodes at 60 FPS

## API Integration

The frontend connects to these Rust server endpoints:

- `GET /api/visualize` - Fetch graph data
- `GET /api/stats` - Get graph statistics
- `POST /api/search` - Search nodes (coming soon)
- `GET /api/nodes/{id}` - Get node details (coming soon)
- `WS /ws` - Real-time updates (coming soon)

## Project Structure

```
src/
├── api/                # API client and types
│   ├── graphClient.ts  # Rust API client
│   └── types.ts        # TypeScript types
├── components/         # React components
│   ├── GraphCanvas.tsx # Cosmograph integration
│   ├── SearchBar.tsx   # Search interface
│   └── ...            # Other UI components
└── pages/             # Page components
```

## Testing

```bash
# Run the test script from the root directory
./test_frontend_integration.sh
```

This will:
1. Check if the Rust server is running
2. Start the frontend development server
3. Open http://localhost:8080 in your browser

## Building for Production

```bash
npm run build
```

The built files will be in the `dist/` directory.

## Troubleshooting

### "Error loading graph"
- Make sure the Rust server is running at `localhost:3000`
- Check that FalkorDB is accessible
- Verify CORS is enabled in the Rust server

### Performance Issues
- Reduce the node limit in GraphCanvas.tsx
- Enable FPS monitor to diagnose issues
- Check browser console for WebGL errors

## Lovable Integration

This project was initially created with [Lovable](https://lovable.dev/projects/c9c6eb4c-f69c-417b-bdb7-8ac318654e44). You can still use Lovable for UI updates and modifications.

## Technologies Used

- **Vite**: Fast build tool and dev server
- **TypeScript**: Type-safe development
- **React**: UI framework
- **shadcn-ui**: Component library
- **Tailwind CSS**: Utility-first CSS
- **@cosmograph/react**: GPU-accelerated graph visualization
- **@tanstack/react-query**: Data fetching and caching

## Contributing

This frontend is part of the Graphiti monorepo. Please see the main README for contribution guidelines.