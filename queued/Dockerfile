# Build stage
FROM rust:1.74 AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y \
    clang \
    libclang-dev \
    git \
    && rm -rf /var/lib/apt/lists/*

# Clone and build queued
RUN git clone https://github.com/wilsonzlin/queued.git /tmp/queued
WORKDIR /tmp/queued

# Build with optimizations and reduced debug info to speed up compilation
ENV CARGO_PROFILE_RELEASE_DEBUG=0
ENV CARGO_PROFILE_RELEASE_LTO=false
RUN cargo build --release --jobs 2

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