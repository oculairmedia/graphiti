# Simple single-stage build using development mode
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install uv
ADD https://astral.sh/uv/install.sh /uv-installer.sh
RUN sh /uv-installer.sh && rm /uv-installer.sh
ENV PATH="/root/.local/bin:$PATH"

# Configure uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

# Copy entire project source
COPY ./pyproject.toml ./README.md ./
COPY ./graphiti_core ./graphiti_core
COPY ./server ./server

# Install graphiti-core in development mode with FalkorDB support (uses source directly)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system -e .[falkordb]

# Install server dependencies and ensure it uses our development graphiti-core
WORKDIR /app/server
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev
# Install our development graphiti-core into server venv to override PyPI version
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --python .venv/bin/python -e /app[falkordb]
# Ensure falkordb is available in server venv
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --python .venv/bin/python falkordb>=1.1.2

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PATH="/root/.local/bin:/app/server/.venv/bin:$PATH" \
    PYTHONPATH="/app:$PYTHONPATH"

# Set port
ENV PORT=8000
EXPOSE $PORT

# Use uvicorn module directly with proper path
CMD ["/app/server/.venv/bin/python", "-m", "uvicorn", "graph_service.main:app", "--host", "0.0.0.0", "--port", "8000"]
