.PHONY: help build test run dev docker-build docker-run docker-push clean benchmark

# Variables
BINARY_NAME := graphiti-search-rs
DOCKER_IMAGE := ghcr.io/oculairmedia/graphiti-search-rs
VERSION := $(shell git describe --tags --always --dirty 2>/dev/null || echo "dev")
RUST_LOG := graphiti_search=debug,info

help: ## Show this help message
	@echo "Usage: make [target]"
	@echo ""
	@echo "Available targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-20s %s\n", $$1, $$2}'

build: ## Build the release binary
	cargo build --release
	@echo "Binary built at: target/release/$(BINARY_NAME)"

test: ## Run all tests
	cargo test --verbose

dev: ## Run in development mode with hot reloading
	RUST_LOG=$(RUST_LOG) cargo watch -x run

run: ## Run the release binary
	RUST_LOG=$(RUST_LOG) ./target/release/$(BINARY_NAME)

check: ## Run cargo check
	cargo check

fmt: ## Format code
	cargo fmt

lint: ## Run clippy linter
	cargo clippy -- -D warnings

clean: ## Clean build artifacts
	cargo clean
	rm -rf target/

docker-build: ## Build Docker image
	docker build -t $(DOCKER_IMAGE):$(VERSION) -t $(DOCKER_IMAGE):latest .

docker-run: ## Run Docker container locally
	docker run -d \
		--name $(BINARY_NAME) \
		-p 3004:3004 \
		-e FALKORDB_HOST=host.docker.internal \
		-e FALKORDB_PORT=6379 \
		-e REDIS_URL=redis://host.docker.internal:6379 \
		-e RUST_LOG=$(RUST_LOG) \
		$(DOCKER_IMAGE):latest

docker-push: ## Push Docker image to registry
	docker push $(DOCKER_IMAGE):$(VERSION)
	docker push $(DOCKER_IMAGE):latest

docker-compose-up: ## Start services with docker-compose
	docker-compose up -d

docker-compose-down: ## Stop services with docker-compose
	docker-compose down

docker-compose-logs: ## Show docker-compose logs
	docker-compose logs -f

benchmark: ## Run benchmarks
	cargo build --release
	@echo "Running benchmarks..."
	@if [ -d "benches" ]; then \
		cargo bench; \
	else \
		echo "No benchmarks found. Add benchmark files to 'benches/' directory."; \
	fi

install-deps: ## Install required dependencies
	@echo "Installing Rust toolchain..."
	@which rustup > /dev/null || curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
	@echo "Installing cargo-watch for development..."
	cargo install cargo-watch
	@echo "Installing cargo-audit for security checks..."
	cargo install cargo-audit

security-audit: ## Run security audit on dependencies
	cargo audit

perf-test: ## Run performance test against local instance
	@echo "Running performance test..."
	@echo "Testing health endpoint..."
	@curl -s -o /dev/null -w "Health check: %{http_code} in %{time_total}s\n" http://localhost:3004/health
	@echo ""
	@echo "Testing search endpoint..."
	@time curl -X POST http://localhost:3004/search \
		-H "Content-Type: application/json" \
		-d '{"query":"test","config":{"limit":10,"reranker_min_score":0.5},"filters":{}}' \
		-s -o /dev/null -w "Search: %{http_code} in %{time_total}s\n"

local-stack: ## Start local development stack (FalkorDB + Redis)
	@echo "Starting local development stack..."
	docker run -d --name falkordb-dev -p 6379:6379 falkordb/falkordb:latest || true
	docker run -d --name redis-dev -p 6380:6379 redis:7-alpine || true
	@echo "Stack started. FalkorDB on :6379, Redis on :6380"

stop-local-stack: ## Stop local development stack
	@echo "Stopping local development stack..."
	docker stop falkordb-dev redis-dev || true
	docker rm falkordb-dev redis-dev || true

integration-test: ## Run integration tests against running service
	@echo "Running integration tests..."
	@python3 -c "import asyncio; from graphiti_core.search.rust_client import RustSearchClient; \
		async def test(): \
			async with RustSearchClient('http://localhost:3004') as client: \
				health = await client.health_check(); \
				print(f'Health: {health}'); \
		asyncio.run(test())"