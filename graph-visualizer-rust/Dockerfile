# Use cargo-chef for better caching
FROM lukemathwalker/cargo-chef:latest-rust-1 AS chef
WORKDIR /app

# Plan stage - prepare recipe
FROM chef AS planner
COPY Cargo.toml Cargo.lock ./
COPY src ./src
RUN cargo chef prepare --recipe-path recipe.json

# Build stage - cook dependencies first
FROM chef AS builder

# Build dependencies - this layer is cached unless dependencies change!
COPY --from=planner /app/recipe.json recipe.json
RUN cargo chef cook --release --recipe-path recipe.json

# Copy source code and build application
COPY Cargo.toml Cargo.lock ./
COPY src ./src
RUN cargo build --release --bin graph-visualizer-backend

# Runtime stage - minimal image
FROM debian:bookworm-slim AS runtime

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    ca-certificates \
    libssl3 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy binary from builder
COPY --from=builder /app/target/release/graph-visualizer-backend /usr/local/bin/graph-visualizer-backend

# Copy static files
COPY static /static

# Create non-root user
RUN useradd -m -u 1001 -U -s /bin/sh appuser && \
    chown -R appuser:appuser /app && \
    chown -R appuser:appuser /static

USER appuser

# Environment variables
ENV RUST_LOG=info
ENV FALKORDB_HOST=falkordb
ENV FALKORDB_PORT=6379
ENV GRAPH_NAME=graphiti_migration
ENV REDIS_URL=redis://redis:6379/2
ENV CACHE_ENABLED=true
ENV CACHE_TTL_SECONDS=300
ENV CACHE_STRATEGY=aggressive

# Expose port
EXPOSE 3000

# Run the binary
CMD ["graph-visualizer-backend"]