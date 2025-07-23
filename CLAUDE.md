# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Graphiti is a Python framework for building temporally-aware knowledge graphs designed for AI agents. It enables real-time incremental updates to knowledge graphs without batch recomputation, making it suitable for dynamic environments.

Key features:

- Bi-temporal data model with explicit tracking of event occurrence times
- Hybrid retrieval combining semantic embeddings, keyword search (BM25), and graph traversal
- Support for custom entity definitions via Pydantic models
- Integration with Neo4j and FalkorDB as graph storage backends
- Advanced graph visualization with WebGL-based Cosmograph library
- Rust-based high-performance visualization server
- React frontend with GPU-accelerated rendering via Cosmograph

## Development Commands

### Main Development Commands (run from project root)

```bash
# Install dependencies
uv sync --extra dev

# Format code (ruff import sorting + formatting)
make format

# Lint code (ruff + pyright type checking)
make lint

# Run tests
make test

# Run all checks (format, lint, test)
make check
```

### Server Development (run from server/ directory)

```bash
cd server/
# Install server dependencies
uv sync --extra dev

# Run server in development mode
uvicorn graph_service.main:app --reload

# Format, lint, test server code
make format
make lint
make test
```

### MCP Server Development (run from mcp_server/ directory)

```bash
cd mcp_server/
# Install MCP server dependencies
uv sync

# Run with Docker Compose
docker-compose up
```

### Frontend Development (run from frontend/ directory)

```bash
cd frontend/
# Install dependencies
npm install

# Run development server (port 8080)
npm run dev

# Build for production
npm run build

# Run linter
npm run lint
```

### Full Stack Development

```bash
# Terminal 1: Run Rust visualization server
cd graph-visualizer-rust/
cargo run --release

# Terminal 2: Run React frontend
cd frontend/
npm run dev

# Terminal 3 (Optional): Run Python server for data ingestion
cd server/
uvicorn graph_service.main:app --reload
```

## Code Architecture

### Core Library (`graphiti_core/`)

- **Main Entry Point**: `graphiti.py` - Contains the main `Graphiti` class that orchestrates all functionality
- **Graph Storage**: `driver/` - Database drivers for Neo4j and FalkorDB
- **LLM Integration**: `llm_client/` - Clients for OpenAI, Anthropic, Gemini, Groq
- **Embeddings**: `embedder/` - Embedding clients for various providers
- **Graph Elements**: `nodes.py`, `edges.py` - Core graph data structures
- **Search**: `search/` - Hybrid search implementation with configurable strategies
- **Prompts**: `prompts/` - LLM prompts for entity extraction, deduplication, summarization
- **Utilities**: `utils/` - Maintenance operations, bulk processing, datetime handling

### Server (`server/`)

- **FastAPI Service**: `graph_service/main.py` - REST API server
- **Routers**: `routers/` - API endpoints for ingestion and retrieval
- **DTOs**: `dto/` - Data transfer objects for API contracts

### MCP Server (`mcp_server/`)

- **MCP Implementation**: `graphiti_mcp_server.py` - Model Context Protocol server for AI assistants
- **Docker Support**: Containerized deployment with Neo4j

### Graph Visualization (`graph-visualizer-rust/`)

- **Rust Server**: High-performance Actix-web server for graph queries
- **WebGL Frontend**: `static/cosmograph.html` - Interactive graph visualization using Cosmograph
- **FalkorDB Integration**: Direct connection to FalkorDB for graph data
- **Features**: Force-directed layouts, custom layout algorithms, interactive node management

### React Frontend (`frontend/`)

- **Modern UI**: React + TypeScript + Vite + shadcn-ui
- **Cosmograph Integration**: GPU-accelerated graph rendering
- **Direct Rust Connection**: Bypasses Python backend for visualization performance
- **API Client**: TypeScript client for Rust server endpoints
- **Real-time Updates**: WebSocket support for live graph changes

## Testing

- **Unit Tests**: `tests/` - Comprehensive test suite using pytest
- **Integration Tests**: Tests marked with `_int` suffix require database connections
- **Evaluation**: `tests/evals/` - End-to-end evaluation scripts

## Configuration

### Environment Variables

- `OPENAI_API_KEY` - Required for LLM inference and embeddings
- `USE_PARALLEL_RUNTIME` - Optional boolean for Neo4j parallel runtime (enterprise only)
- Provider-specific keys: `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, `GROQ_API_KEY`, `VOYAGE_API_KEY`

### Database Setup

- **Neo4j**: Version 5.26+ required, available via Neo4j Desktop
  - Database name defaults to `neo4j` (hardcoded in Neo4jDriver)
  - Override by passing `database` parameter to driver constructor
- **FalkorDB**: Version 1.1.2+ as alternative backend
  - Database name defaults to `default_db` (hardcoded in FalkorDriver)
  - Override by passing `database` parameter to driver constructor

## Development Guidelines

### Code Style

- Use Ruff for formatting and linting (configured in pyproject.toml)
- Line length: 100 characters
- Quote style: single quotes
- Type checking with Pyright is enforced
- Main project uses `typeCheckingMode = "basic"`, server uses `typeCheckingMode = "standard"`

### Testing Requirements

- Run tests with `make test` or `pytest`
- Integration tests require database connections and are marked with `_int` suffix
- Use `pytest-xdist` for parallel test execution
- Run specific test files: `pytest tests/test_specific_file.py`
- Run specific test methods: `pytest tests/test_file.py::test_method_name`
- Run only integration tests: `pytest tests/ -k "_int"`
- Run only unit tests: `pytest tests/ -k "not _int"`

### LLM Provider Support

The codebase supports multiple LLM providers but works best with services supporting structured output (OpenAI, Gemini). Other providers may cause schema validation issues, especially with smaller models.

### MCP Server Usage Guidelines

When working with the MCP server, follow the patterns established in `mcp_server/cursor_rules.md`:

- Always search for existing knowledge before adding new information
- Use specific entity type filters (`Preference`, `Procedure`, `Requirement`)
- Store new information immediately using `add_memory`
- Follow discovered procedures and respect established preferences

## Huly Project Integration

This repository is tracked in Huly under project **GRAPH** (Graphiti Knowledge Graph Platform).

### Components

1. **Graph Visualization** - WebGL-based interactive graph visualization system using Cosmograph library, Rust server, and FalkorDB backend.
2. **Frontend Bridge** - React frontend integration with Rust graph server - connects graph-sight UI to existing Rust visualization endpoints.

### Recent Issues (Graph Visualization Module)

1. **GRAPH-32**: Implement Neo4j to FalkorDB Migration Script (High Priority)
2. **GRAPH-28**: Setup FalkorDB Infrastructure with Docker (High Priority)
3. **GRAPH-25**: Create Rust-based Graph Visualization Server (High Priority)
4. **GRAPH-24**: Implement Cosmograph WebGL Visualization (High Priority)
5. **GRAPH-26**: Add Interactive Node Selection and Details Panel (Medium Priority)
6. **GRAPH-23**: Implement Mouse-based Navigation Controls (Medium Priority)
7. **GRAPH-29**: Add Node Size and Visual Controls (Medium Priority)
8. **GRAPH-27**: Build Advanced Search and Filter System (Medium Priority)
9. **GRAPH-30**: Create Custom Graph Layout Algorithms (Medium Priority)
10. **GRAPH-31**: Add Graph Navigation Tools (Medium Priority)
11. **GRAPH-34**: Implement Interactive Node Management (Medium Priority)
12. **GRAPH-36**: Add Force Physics Customization (Low Priority)
13. **GRAPH-33**: Fix Label Display and Persistence (Medium Priority)
14. **GRAPH-37**: Create Debug Tools and Testing Utilities (Low Priority)
15. **GRAPH-35**: Document Graph Visualization Module (Medium Priority)

### Graph Visualization Features Implemented

- **Migration**: Neo4j to FalkorDB data migration with centrality metrics
- **Infrastructure**: Docker-based FalkorDB setup with custom UI
- **Server**: Rust Actix-web server with graph query endpoints
- **Visualization**: Cosmograph WebGL rendering for 4000+ nodes
- **Interaction**: Node selection, multi-select, details panel
- **Navigation**: Pan, zoom, drag nodes, middle-mouse navigation
- **Customization**: Node size, colors by type/centrality, link styling
- **Search**: Real-time search with filters (type, metrics, time)
- **Layouts**: Force-directed, hierarchical, radial, circular, temporal, cluster
- **Tools**: Path finding, neighbor exploration, subgraph focus
- **Management**: Pin nodes, hide/show, collapse/expand, export
- **Physics**: Customizable forces, gravity, repulsion, friction
### Frontend Integration (React-Rust Bridge)

#### Milestone: React-Rust Frontend Integration
- **Status**: In Progress
- **Target Date**: Feb 3, 2025

#### Issues Created:
1. **GRAPH-43**: Move graph-sight into graphiti repository (Done)
2. **GRAPH-44**: Connect data flow from Rust to React (In Progress)
3. **GRAPH-45**: Set up API proxy and TypeScript client (Done)
4. **GRAPH-46**: Integrate Cosmograph React library (Done)
5. **GRAPH-47**: Add CORS support to Rust server (Done)
6. **GRAPH-48**: Implement search functionality (Backlog)
7. **GRAPH-49**: Add node details endpoints (Backlog)
8. **GRAPH-50**: Implement real-time updates via WebSocket (Backlog)
9. **GRAPH-51**: Add layout algorithm support (Backlog)
10. **GRAPH-52**: Optimize for large graphs (Backlog)

### Integration Architecture

```
React Frontend (port 8080)
    ↓ API calls via proxy
Rust Server (port 3000) ← Direct connection to FalkorDB
    ↑
Python Server (port 8000) - For data ingestion only
```

The frontend connects directly to the Rust server for visualization, bypassing the Python backend for optimal performance while maintaining compatibility with Graphiti's data ingestion capabilities.
