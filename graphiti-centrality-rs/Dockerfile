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

# Create non-root user
RUN groupadd -r graphiti && useradd -r -g graphiti graphiti

# Create app directory
WORKDIR /app

# Copy binary from builder stage
COPY --from=builder /app/target/release/graphiti-centrality /app/graphiti-centrality

# Change ownership to non-root user
RUN chown -R graphiti:graphiti /app

# Switch to non-root user
USER graphiti

# Expose port
EXPOSE 3003

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:3003/health || exit 1

# Set environment variables
ENV RUST_LOG=graphiti_centrality=info,info
ENV BIND_ADDR=0.0.0.0:3003
ENV FALKORDB_HOST=falkordb
ENV FALKORDB_PORT=6379
ENV GRAPH_NAME=graphiti_migration

# Run the application
CMD ["./graphiti-centrality"]