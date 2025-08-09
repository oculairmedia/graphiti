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
RUN cargo build --release

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
COPY --from=builder /app/target/release/graphiti-search-rs /app/graphiti-search-rs

# Create non-root user
RUN useradd -m -u 1001 -U -s /bin/sh appuser && \
    chown -R appuser:appuser /app

USER appuser

# Environment variables
ENV PORT=3004
ENV FALKORDB_HOST=falkordb
ENV FALKORDB_PORT=6379
ENV GRAPH_NAME=graphiti_migration
ENV REDIS_URL=redis://redis:6379
ENV MAX_CONNECTIONS=32
ENV CACHE_TTL=300
ENV ENABLE_SIMD=true
ENV PARALLEL_THRESHOLD=100
ENV RUST_LOG=graphiti_search=debug,info

EXPOSE 3004

CMD ["./graphiti-search-rs"]