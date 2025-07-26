# Multi-stage build for optimized production image
FROM rust:1.83-slim as builder

# Install required system dependencies
RUN apt-get update && apt-get install -y \
    pkg-config \
    libssl-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy manifests and dependencies first for better caching
COPY Cargo.toml Cargo.lock ./

# Create dummy source to build dependencies
RUN mkdir src && echo "fn main() {}" > src/main.rs && echo "// placeholder" > src/lib.rs

# Build dependencies (this layer will be cached unless Cargo.toml changes)
RUN cargo build --release
RUN rm src/main.rs src/lib.rs

# Copy actual source code
COPY src ./src

# Build application with optimizations
RUN cargo build --release

# Production stage
FROM debian:bookworm-slim

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    ca-certificates \
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

# Run the application
CMD ["./graphiti-centrality"]