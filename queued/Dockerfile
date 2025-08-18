# Build stage with latest Rust
FROM rust:latest AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y \
    clang \
    libclang-dev \
    git \
    && rm -rf /var/lib/apt/lists/*

# Clone queued repository
RUN git clone https://github.com/wilsonzlin/queued.git /tmp/queued
WORKDIR /tmp/queued

# Set build optimizations for faster CI builds
ENV CARGO_NET_GIT_FETCH_WITH_CLI=true
ENV CARGO_PROFILE_RELEASE_DEBUG=false
ENV CARGO_PROFILE_RELEASE_LTO=false
ENV CARGO_PROFILE_RELEASE_CODEGEN_UNITS=256
ENV CARGO_PROFILE_RELEASE_INCREMENTAL=false

# Build with limited parallelism to avoid OOM in CI
RUN cargo build --release -j 1

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
COPY --from=builder --chown=queued:queued /tmp/queued/target/release/queued /usr/local/bin/queued

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