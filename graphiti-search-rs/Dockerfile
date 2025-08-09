# Build stage  
FROM rust:latest as builder

WORKDIR /app

# Copy manifests
COPY Cargo.toml Cargo.lock ./

# Create dummy main file for dependency caching
RUN mkdir src && echo "fn main() {}" > src/main.rs

# Build dependencies only
RUN cargo build --release
RUN rm -rf src

# Copy source code
COPY src ./src

# Build for release
RUN touch src/main.rs
RUN cargo build --release

# Runtime stage
FROM debian:bookworm-slim

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