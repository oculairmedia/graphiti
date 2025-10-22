# syntax=docker/dockerfile:1.6

###########################
# Dependency planning stage
###########################
FROM rust:1.83-slim AS chef

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    pkg-config \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/* && \
    cargo install cargo-chef

COPY Cargo.toml Cargo.lock ./

RUN cargo chef prepare --recipe-path recipe.json

###########################
# Build stage
###########################
FROM rust:1.83-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    pkg-config \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

COPY --from=chef /usr/local/cargo/bin/cargo-chef /usr/local/cargo/bin/cargo-chef
COPY --from=chef /app/recipe.json recipe.json
RUN cargo chef cook --release --locked --recipe-path recipe.json

COPY . .
RUN cargo build --release --locked

###########################
# Runtime stage
###########################
FROM gcr.io/distroless/cc-debian12:nonroot AS runtime

WORKDIR /app

# Copy binary and SSL libraries
COPY --from=builder /app/target/release/graphiti-sync-rs /app/graphiti-sync-rs
COPY --from=builder /usr/lib/x86_64-linux-gnu/libssl.so.3 /usr/lib/x86_64-linux-gnu/libssl.so.3
COPY --from=builder /usr/lib/x86_64-linux-gnu/libcrypto.so.3 /usr/lib/x86_64-linux-gnu/libcrypto.so.3

# Metadata
LABEL org.opencontainers.image.title="Graphiti Sync Service"
LABEL org.opencontainers.image.description="High-performance Rust-based graph synchronization service for Neo4j and FalkorDB"
LABEL org.opencontainers.image.version="0.1.0"
LABEL org.opencontainers.image.vendor="Graphiti"

# Health check and metrics ports
EXPOSE 8080 8081

# Health check (runs every 30s, starts after 5s, timeout 3s, 3 retries)
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD ["/app/graphiti-sync-rs", "--help"]

ENTRYPOINT ["/app/graphiti-sync-rs"]
