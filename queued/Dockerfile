# Use cargo-chef with Rust 1.82 for icu crates compatibility
FROM lukemathwalker/cargo-chef:latest-rust-1.82 AS chef
WORKDIR /app

# Plan stage - prepare the dependency list
FROM chef AS planner
# Copy local source files instead of cloning from GitHub
COPY . /app/
# Prepare the recipe for caching dependencies
RUN cargo chef prepare --recipe-path recipe.json

# Build stage - cache dependencies
FROM chef AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y \
    clang \
    libclang-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy the recipe from planner
COPY --from=planner /app/recipe.json recipe.json

# Build dependencies - this layer will be cached!
RUN cargo chef cook --release --recipe-path recipe.json

# Copy the actual source code
COPY . /app/

# Build the actual application - only runs when source changes
RUN cargo build --release

# Runtime stage
FROM debian:bookworm-slim

# Install runtime dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create data directory and user
RUN mkdir -p /data && \
    useradd -m -u 1000 queued && \
    chown -R queued:queued /data

# Copy the built queued binary from builder stage
COPY --from=builder --chown=queued:queued /app/target/release/queued /usr/local/bin/queued

# Make it executable
RUN chmod +x /usr/local/bin/queued

USER queued
WORKDIR /data

# Expose the service port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/queues || exit 1

# Run the service
CMD ["/usr/local/bin/queued", \
     "--interface", "0.0.0.0", \
     "--port", "8080", \
     "--data-dir", "/data"]