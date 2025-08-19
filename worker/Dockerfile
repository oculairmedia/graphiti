# Dockerfile for Graphiti ingestion worker
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy all project files (needed for installation)
COPY pyproject.toml /app/
COPY README.md /app/
COPY graphiti_core /app/graphiti_core
COPY worker /app/worker

# Install Python dependencies using uv
RUN pip install --no-cache-dir uv && \
    uv pip install --system -e ".[falkordb,cerebras]"

# Install additional worker dependencies
RUN pip install --no-cache-dir msgpack httpx cerebras-cloud-sdk>=1.46.0

# Create non-root user
RUN useradd -m -u 1000 worker && chown -R worker:worker /app
USER worker

# Health check - just check if Python is responsive
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import sys; sys.exit(0)"

# Run the worker service
CMD ["python", "-u", "worker/worker_service.py"]