# Multi-stage build for Neo4j-FalkorDB Sync Service
FROM python:3.11-slim AS builder

# Set working directory
WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Production stage
FROM python:3.11-slim

# Set labels
LABEL maintainer="Graphiti Team"
LABEL description="Neo4j to FalkorDB synchronization service"
LABEL version="1.0.0"

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r syncuser && useradd -r -g syncuser syncuser

# Set working directory
WORKDIR /app

# Copy Python packages from builder stage
COPY --from=builder /root/.local /home/syncuser/.local

# Copy application code
COPY . .

# Create directories for logs and ensure proper ownership
RUN mkdir -p /app/logs /app/data && \
    chown -R syncuser:syncuser /app

# Set environment variables
ENV PATH=/home/syncuser/.local/bin:$PATH
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Switch to non-root user
USER syncuser

# Expose ports
EXPOSE 8080 8081

# Default command
CMD ["python", "-m", "sync_service.main", "/app/config.yaml"]