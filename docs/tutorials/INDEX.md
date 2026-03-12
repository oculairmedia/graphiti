# Tutorials Index

> Learning-oriented guides. Start here if new to the codebase.

| File | Keywords | Description |
|------|----------|-------------|
| [getting-started.md](getting-started.md) | `start`, `quick`, `first`, `episode`, `setup` | Quick start guide |
| [local-development.md](local-development.md) | `local`, `dev`, `setup`, `environment`, `docker` | Local development setup |

---

## Prerequisites

- Python 3.10+
- Docker and Docker Compose
- OpenAI API key (or other LLM provider)

## Quick Start

1. **Clone and setup**:
   ```bash
   cd /opt/stacks/graphiti
   cp .env.example .env
   # Edit .env with your API keys
   ```

2. **Start services**:
   ```bash
   docker-compose up -d
   ```

3. **Add your first episode**:
   ```python
   from graphiti_core import Graphiti
   
   graphiti = Graphiti("bolt://localhost:7687", "neo4j", "password")
   await graphiti.add_episode(
       name="first_episode",
       source_content="Hello, Graphiti!",
   )
   ```

4. **Search the graph**:
   ```python
   results = await graphiti.search("Hello")
   ```

---

> **Next steps**: See [../how-to/](../how-to/) for specific tasks, or [../explanation/](../explanation/) for architecture understanding.
