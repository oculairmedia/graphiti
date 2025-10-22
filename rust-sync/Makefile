.PHONY: help build test clean run fmt lint check docker dev watch

help:
	@echo "Graphiti Rust Sync POC - Available targets:"
	@echo "  make check     - Quick compile check"
	@echo "  make build     - Build release version"
	@echo "  make test      - Run all tests"
	@echo "  make run       - Run the sync service"
	@echo "  make fmt       - Format code with rustfmt"
	@echo "  make lint      - Run clippy linter"
	@echo "  make watch     - Auto-rebuild on changes"
	@echo "  make docker    - Build Docker image"
	@echo "  make docker-up - Start test databases"
	@echo "  make clean     - Clean build artifacts"

check:
	@echo "🔍 Running cargo check..."
	cargo check --all-targets

build:
	@echo "🔨 Building release version..."
	cargo build --release

build-dev:
	@echo "🔨 Building debug version..."
	cargo build

test:
	@echo "🧪 Running tests..."
	cargo test --verbose

test-watch:
	@echo "🧪 Running tests in watch mode..."
	cargo watch -x test

clean:
	@echo "🧹 Cleaning build artifacts..."
	cargo clean

run:
	@echo "🚀 Running sync service..."
	cargo run --release

run-dev:
	@echo "🚀 Running sync service (debug)..."
	cargo run

fmt:
	@echo "✨ Formatting code..."
	cargo fmt --all

fmt-check:
	@echo "🔍 Checking code formatting..."
	cargo fmt --all -- --check

lint:
	@echo "🔍 Running clippy..."
	cargo clippy -- -D warnings

audit:
	@echo "🔒 Checking for security vulnerabilities..."
	cargo audit

outdated:
	@echo "📦 Checking for outdated dependencies..."
	cargo outdated

watch:
	@echo "👀 Starting watch mode..."
	cargo watch -x check -x test

docker:
	@echo "🐳 Building Docker image..."
	docker build -f docker/Dockerfile -t graphiti-sync-rs:latest .

docker-up:
	@echo "🐳 Starting test databases..."
	cd docker && docker-compose up -d neo4j-test falkordb-test

docker-down:
	@echo "🐳 Stopping test databases..."
	cd docker && docker-compose down

docker-logs:
	@echo "📋 Showing database logs..."
	cd docker && docker-compose logs -f

docker-test:
	@echo "🐳 Starting full stack with sync service..."
	cd docker && docker-compose --profile sync up

dev: docker-up
	@echo "🚀 Starting development environment..."
	@make watch

all: fmt lint test build

ci: fmt-check lint test
	@echo "✅ CI checks passed!"
