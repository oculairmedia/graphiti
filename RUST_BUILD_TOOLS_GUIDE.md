# Rust Build Tools & Development Setup Guide

## Essential Tools for Rust Development

### 1. Core Toolchain

#### rustup (Rust Installer & Version Manager)
**Installation**:
```bash
# Linux/macOS
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# Windows
# Download and run: https://rustup.rs/
```

**Key Commands**:
```bash
# Update Rust toolchain
rustup update

# Check installed version
rustc --version
cargo --version

# Install specific toolchain
rustup install stable
rustup install nightly

# Set default toolchain
rustup default stable

# Add targets for cross-compilation
rustup target add x86_64-unknown-linux-musl

# Add components
rustup component add rustfmt      # Code formatter
rustup component add clippy       # Linter
rustup component add rust-analyzer # LSP for IDEs
```

---

### 2. Cargo (Build System & Package Manager)

Cargo is Rust's built-in build tool (comes with rustup). It's like npm/pip for Rust.

#### Essential Cargo Commands
```bash
# Create new project
cargo new graphiti-sync-rs
cargo new --lib my-library

# Build project
cargo build              # Debug build
cargo build --release    # Optimized release build

# Run project
cargo run
cargo run --release

# Run tests
cargo test
cargo test --lib        # Only library tests
cargo test --test integration_test  # Specific test file

# Check code (fast compile check without building)
cargo check

# Format code
cargo fmt

# Lint code
cargo clippy
cargo clippy -- -D warnings  # Treat warnings as errors

# Update dependencies
cargo update

# Generate documentation
cargo doc --open

# Clean build artifacts
cargo clean

# Show dependency tree
cargo tree
```

#### Cargo.toml Structure
```toml
[package]
name = "graphiti-sync-rs"
version = "0.1.0"
edition = "2021"
authors = ["Your Name <you@example.com>"]
description = "High-performance sync service for Graphiti"
license = "MIT"
repository = "https://github.com/yourorg/graphiti-sync-rs"

[dependencies]
# Runtime dependencies
neo4rs = "0.9.0-rc.8"
falkordb = { version = "0.1.11", features = ["tokio", "tracing"] }
tokio = { version = "1.45", features = ["full"] }
serde = { version = "1.0", features = ["derive"] }

[dev-dependencies]
# Development-only dependencies (tests, benchmarks)
criterion = "0.5"
mockall = "0.12"

[build-dependencies]
# Build script dependencies
# (for build.rs files)

[profile.release]
# Optimization settings
opt-level = 3
lto = true           # Link-time optimization
codegen-units = 1    # Better optimization, slower compile
strip = true         # Remove debug symbols

[profile.dev]
# Development profile (faster compilation)
opt-level = 0

[workspace]
# For multi-crate projects
members = [
    "sync-service",
    "shared-types",
    "cli-tools",
]
```

---

### 3. Essential Cargo Extensions

Install these with `cargo install <name>`:

#### cargo-edit
Manage dependencies from command line
```bash
cargo install cargo-edit

# Usage
cargo add tokio --features full
cargo add serde --features derive
cargo rm old-dependency
cargo upgrade
```

#### cargo-watch
Auto-rebuild on file changes
```bash
cargo install cargo-watch

# Usage
cargo watch -x check
cargo watch -x test
cargo watch -x run
cargo watch -x 'run --bin my-binary'
```

#### cargo-expand
View macro expansions
```bash
cargo install cargo-expand

# Usage
cargo expand           # Expand all macros
cargo expand module    # Expand specific module
```

#### cargo-audit
Security vulnerability scanner
```bash
cargo install cargo-audit

# Usage
cargo audit
cargo audit --deny warnings
```

#### cargo-outdated
Check for outdated dependencies
```bash
cargo install cargo-outdated

# Usage
cargo outdated
cargo outdated -R  # Include root dependencies only
```

#### cargo-bloat
Find what takes up space in binary
```bash
cargo install cargo-bloat

# Usage
cargo bloat --release
cargo bloat --release --crates
```

#### cargo-flamegraph
Generate performance flamegraphs
```bash
cargo install flamegraph

# Usage (requires perf on Linux)
cargo flamegraph
```

#### cargo-nextest
Faster test runner
```bash
cargo install cargo-nextest

# Usage
cargo nextest run
cargo nextest run --release
```

---

### 4. Development Environment Setup

#### VSCode Extensions
```json
{
  "recommendations": [
    "rust-lang.rust-analyzer",      // LSP for Rust
    "vadimcn.vscode-lldb",          // Debugger
    "serayuzgur.crates",            // Cargo.toml helper
    "tamasfe.even-better-toml",     // TOML support
    "usernamehw.errorlens",         // Inline errors
    "ms-azuretools.vscode-docker"   // Docker support
  ]
}
```

Save as `.vscode/extensions.json`

#### VSCode Settings
```json
{
  "[rust]": {
    "editor.defaultFormatter": "rust-lang.rust-analyzer",
    "editor.formatOnSave": true
  },
  "rust-analyzer.checkOnSave.command": "clippy",
  "rust-analyzer.cargo.features": "all"
}
```

Save as `.vscode/settings.json`

---

### 5. Formatter & Linter Configuration

#### rustfmt.toml
```toml
# Rust code formatting configuration
edition = "2021"
max_width = 100
hard_tabs = false
tab_spaces = 4
newline_style = "Auto"
use_small_heuristics = "Default"
reorder_imports = true
reorder_modules = true
remove_nested_parens = true
```

#### clippy.toml
```toml
# Clippy linting configuration
cognitive-complexity-threshold = 30
```

Or use in Cargo.toml:
```toml
[lints.clippy]
all = "warn"
pedantic = "warn"
nursery = "warn"
```

---

### 6. Testing Tools

#### Cargo Built-in Testing
```bash
# Run all tests
cargo test

# Run specific test
cargo test test_name

# Run tests with output
cargo test -- --nocapture

# Run tests in single thread
cargo test -- --test-threads=1

# Run ignored tests
cargo test -- --ignored

# Run benchmarks
cargo bench
```

#### Test Organization
```rust
// Unit tests (in same file as code)
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_something() {
        assert_eq!(2 + 2, 4);
    }

    #[test]
    #[should_panic]
    fn test_panic() {
        panic!("Expected panic");
    }

    #[test]
    #[ignore]
    fn expensive_test() {
        // Only run with: cargo test -- --ignored
    }
}

// Integration tests (in tests/ directory)
// tests/integration_test.rs
use graphiti_sync_rs::*;

#[tokio::test]
async fn test_full_sync() {
    // Test code here
}
```

---

### 7. Docker Integration

#### Dockerfile for Rust
```dockerfile
# Multi-stage build for smaller images

# Build stage
FROM rust:1.75-slim as builder

WORKDIR /app

# Copy manifests
COPY Cargo.toml Cargo.lock ./

# Cache dependencies
RUN mkdir src && \
    echo "fn main() {}" > src/main.rs && \
    cargo build --release && \
    rm -rf src

# Copy source
COPY src ./src

# Build application
RUN cargo build --release

# Runtime stage
FROM debian:bookworm-slim

# Install runtime dependencies
RUN apt-get update && \
    apt-get install -y ca-certificates libssl3 && \
    rm -rf /var/lib/apt/lists/*

# Copy binary from builder
COPY --from=builder /app/target/release/graphiti-sync-rs /usr/local/bin/

# Run
CMD ["graphiti-sync-rs"]
```

#### .dockerignore
```
target/
Cargo.lock
**/*.rs.bk
.git/
.vscode/
*.md
```

---

### 8. CI/CD Configuration

#### GitHub Actions (.github/workflows/ci.yml)
```yaml
name: CI

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]

env:
  CARGO_TERM_COLOR: always

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Install Rust
        uses: dtolnay/rust-toolchain@stable
        with:
          components: rustfmt, clippy
      
      - name: Cache cargo registry
        uses: actions/cache@v4
        with:
          path: ~/.cargo/registry
          key: ${{ runner.os }}-cargo-registry-${{ hashFiles('**/Cargo.lock') }}
      
      - name: Cache cargo index
        uses: actions/cache@v4
        with:
          path: ~/.cargo/git
          key: ${{ runner.os }}-cargo-git-${{ hashFiles('**/Cargo.lock') }}
      
      - name: Cache target directory
        uses: actions/cache@v4
        with:
          path: target
          key: ${{ runner.os }}-target-${{ hashFiles('**/Cargo.lock') }}
      
      - name: Check formatting
        run: cargo fmt -- --check
      
      - name: Run clippy
        run: cargo clippy -- -D warnings
      
      - name: Run tests
        run: cargo test --verbose
      
      - name: Build release
        run: cargo build --release --verbose

  security-audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions-rs/audit-check@v1
        with:
          token: ${{ secrets.GITHUB_TOKEN }}
```

---

### 9. Debugging Tools

#### LLDB (VSCode)
`.vscode/launch.json`:
```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "type": "lldb",
      "request": "launch",
      "name": "Debug executable",
      "cargo": {
        "args": [
          "build",
          "--bin=graphiti-sync-rs",
          "--package=graphiti-sync-rs"
        ],
        "filter": {
          "name": "graphiti-sync-rs",
          "kind": "bin"
        }
      },
      "args": [],
      "cwd": "${workspaceFolder}"
    },
    {
      "type": "lldb",
      "request": "launch",
      "name": "Debug unit tests",
      "cargo": {
        "args": [
          "test",
          "--no-run",
          "--lib",
          "--package=graphiti-sync-rs"
        ],
        "filter": {
          "name": "graphiti-sync-rs",
          "kind": "lib"
        }
      },
      "args": [],
      "cwd": "${workspaceFolder}"
    }
  ]
}
```

---

### 10. Performance Tools

#### Benchmarking with Criterion
```rust
// benches/sync_benchmark.rs
use criterion::{black_box, criterion_group, criterion_main, Criterion};
use graphiti_sync_rs::*;

fn benchmark_node_extraction(c: &mut Criterion) {
    c.bench_function("extract 1000 nodes", |b| {
        b.iter(|| {
            // Your benchmark code
            black_box(extract_nodes(1000))
        });
    });
}

criterion_group!(benches, benchmark_node_extraction);
criterion_main!(benches);
```

Run with:
```bash
cargo bench
```

---

### 11. Cross-Compilation

```bash
# Install target
rustup target add x86_64-unknown-linux-musl

# Build for target
cargo build --release --target x86_64-unknown-linux-musl

# Using cross (for easy cross-compilation)
cargo install cross

# Build for different platforms
cross build --target x86_64-pc-windows-gnu
cross build --target aarch64-unknown-linux-gnu
```

---

### 12. Dependency Management Best Practices

#### Using Workspaces (Multi-crate projects)
```
graphiti-sync/
├── Cargo.toml          # Workspace root
├── sync-service/
│   ├── Cargo.toml
│   └── src/
├── shared-types/
│   ├── Cargo.toml
│   └── src/
└── cli-tools/
    ├── Cargo.toml
    └── src/
```

Root `Cargo.toml`:
```toml
[workspace]
members = [
    "sync-service",
    "shared-types",
    "cli-tools",
]

[workspace.dependencies]
# Shared dependency versions
tokio = { version = "1.45", features = ["full"] }
serde = { version = "1.0", features = ["derive"] }
```

Each member `Cargo.toml`:
```toml
[dependencies]
tokio = { workspace = true }
serde = { workspace = true }
shared-types = { path = "../shared-types" }
```

---

### 13. Makefile for Common Tasks

```makefile
# Makefile for Rust project

.PHONY: help build test clean run fmt lint check docker

help:
	@echo "Available targets:"
	@echo "  build   - Build the project"
	@echo "  test    - Run tests"
	@echo "  run     - Run the application"
	@echo "  fmt     - Format code"
	@echo "  lint    - Run clippy"
	@echo "  check   - Quick compile check"
	@echo "  docker  - Build Docker image"

build:
	cargo build --release

test:
	cargo test --verbose

test-cov:
	cargo tarpaulin --out Html --output-dir coverage

clean:
	cargo clean

run:
	cargo run --release

fmt:
	cargo fmt --all

lint:
	cargo clippy -- -D warnings

check:
	cargo check --all-targets

audit:
	cargo audit

outdated:
	cargo outdated

docker:
	docker build -t graphiti-sync-rs:latest .

bench:
	cargo bench

doc:
	cargo doc --open

watch:
	cargo watch -x check -x test -x run
```

---

### 14. Pre-commit Hooks

Install with:
```bash
cargo install cargo-husky
```

`.cargo-husky/hooks/pre-commit`:
```bash
#!/bin/sh
set -e

# Format check
cargo fmt -- --check

# Linting
cargo clippy -- -D warnings

# Tests
cargo test
```

---

### 15. Quick Start Checklist

```bash
# 1. Install Rust
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source $HOME/.cargo/env

# 2. Install essential tools
cargo install cargo-edit cargo-watch cargo-audit cargo-outdated

# 3. Create project
cargo new graphiti-sync-rs
cd graphiti-sync-rs

# 4. Add dependencies
cargo add tokio --features full
cargo add neo4rs
cargo add falkordb --features tokio,tracing
cargo add serde --features derive
cargo add tracing
cargo add tracing-subscriber

# 5. Development cycle
cargo watch -x check              # Auto-check on save
cargo test                        # Run tests
cargo clippy                      # Lint
cargo fmt                         # Format
cargo build --release            # Build optimized

# 6. Before commit
cargo fmt
cargo clippy -- -D warnings
cargo test
```

---

## Recommended Learning Resources

### Books
- **The Rust Programming Language** (Free online: https://doc.rust-lang.org/book/)
- **Rust by Example** (https://doc.rust-lang.org/rust-by-example/)
- **Asynchronous Programming in Rust** (https://rust-lang.github.io/async-book/)

### Tools Documentation
- Cargo Book: https://doc.rust-lang.org/cargo/
- Rustup Book: https://rust-lang.github.io/rustup/
- Clippy Lints: https://rust-lang.github.io/rust-clippy/

### Community
- Rust Users Forum: https://users.rust-lang.org/
- Official Discord: https://discord.gg/rust-lang
- Reddit: r/rust

---

## Summary

### Must-Have Tools
1. ✅ **rustup** - Rust version manager
2. ✅ **cargo** - Build system (included)
3. ✅ **rustfmt** - Code formatter
4. ✅ **clippy** - Linter
5. ✅ **rust-analyzer** - IDE support

### Highly Recommended
6. ✅ **cargo-watch** - Auto-rebuild
7. ✅ **cargo-edit** - Dependency management
8. ✅ **cargo-audit** - Security scanning
9. ✅ **cargo-nextest** - Better testing

### For Production
10. ✅ **Docker** - Containerization
11. ✅ **GitHub Actions** - CI/CD
12. ✅ **criterion** - Benchmarking

Start with the must-have tools, then add others as needed!