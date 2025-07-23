# Use official Rust image as builder
FROM rust:latest as builder

# Create app directory
WORKDIR /usr/src/app

# Copy Cargo files
COPY Cargo.toml Cargo.lock ./

# Copy source code
COPY src ./src
COPY static ./static

# Build the application in release mode
RUN cargo build --release --bin graph-visualizer-backend

# Runtime image
FROM debian:bookworm-slim

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    ca-certificates \
    libssl3 \
    && rm -rf /var/lib/apt/lists/*

# Copy the binary from builder
COPY --from=builder /usr/src/app/target/release/graph-visualizer-backend /usr/local/bin/graph-visualizer-backend

# Copy static files
COPY --from=builder /usr/src/app/static /static

# Make sure binary is executable
RUN chmod +x /usr/local/bin/graph-visualizer-backend

# Set environment variables
ENV RUST_LOG=info

# Expose port
EXPOSE 3000

# Run the binary
CMD ["graph-visualizer-backend"]