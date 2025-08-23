.PHONY: install format lint test all check setup dev-setup docker-dev docker-prod docker-clean docker-logs docker-status help

# Define variables
PYTHON = python3
UV = uv
PYTEST = $(UV) run pytest
RUFF = $(UV) run ruff
PYRIGHT = $(UV) run pyright

# Docker Compose files
COMPOSE_BASE = docker-compose.base.yml
COMPOSE_DEV = docker-compose.override.yml
COMPOSE_PROD = docker-compose.prod.override.yml

# Default target
all: format lint test

# =============================================================================
# Development Setup
# =============================================================================

# Install dependencies
install:
	$(UV) sync --extra dev

# Setup complete development environment
setup: dev-setup

# Full development environment setup
dev-setup:
	@echo "🚀 Setting up Graphiti development environment..."
	./setup-dev.sh dev

# Minimal development setup (essential services only)
setup-minimal:
	@echo "🚀 Setting up minimal Graphiti environment..."
	./setup-dev.sh minimal

# Full development setup with all tools
setup-full:
	@echo "🚀 Setting up full Graphiti environment..."
	./setup-dev.sh full

# =============================================================================
# Code Quality
# =============================================================================

# Format code
format:
	$(RUFF) check --select I --fix
	$(RUFF) format

# Lint code
lint:
	$(RUFF) check
	$(PYRIGHT) ./graphiti_core 

# Run tests
test:
	$(PYTEST)

# Run all checks (format, lint, test)
check: format lint test

# =============================================================================
# Docker Commands
# =============================================================================

# Start development environment with Docker
docker-dev:
	@echo "🐳 Starting development services..."
	docker-compose -f $(COMPOSE_BASE) -f $(COMPOSE_DEV) up -d

# Start production environment with Docker
docker-prod:
	@echo "🐳 Starting production services..."
	docker-compose -f $(COMPOSE_BASE) -f $(COMPOSE_PROD) up -d

# Start frontend-only environment
docker-frontend:
	@echo "🐳 Starting frontend services..."
	docker-compose -f $(COMPOSE_BASE) -f docker-compose.frontend.override.yml up -d

# Start queue-only environment
docker-queue:
	@echo "🐳 Starting queue services..."
	docker-compose -f $(COMPOSE_BASE) -f docker-compose.queue.override.yml up -d

# Stop all services
docker-stop:
	@echo "🛑 Stopping all services..."
	docker-compose -f $(COMPOSE_BASE) -f $(COMPOSE_DEV) down

# Clean up Docker resources
docker-clean:
	@echo "🧹 Cleaning up Docker resources..."
	docker-compose -f $(COMPOSE_BASE) -f $(COMPOSE_DEV) down -v
	docker system prune -f

# View service logs
docker-logs:
	@echo "📋 Viewing service logs..."
	docker-compose -f $(COMPOSE_BASE) -f $(COMPOSE_DEV) logs -f

# Show service status
docker-status:
	@echo "📊 Service status:"
	docker-compose -f $(COMPOSE_BASE) -f $(COMPOSE_DEV) ps

# Rebuild and restart services
docker-rebuild:
	@echo "🔄 Rebuilding and restarting services..."
	docker-compose -f $(COMPOSE_BASE) -f $(COMPOSE_DEV) up -d --build

# Pull latest images
docker-pull:
	@echo "📥 Pulling latest images..."
	docker-compose -f $(COMPOSE_BASE) -f $(COMPOSE_DEV) pull

# =============================================================================
# Development Utilities
# =============================================================================

# Quick health check of services
health-check:
	@echo "🏥 Checking service health..."
	@curl -f -s http://localhost:8003/healthcheck && echo "✅ API Server: OK" || echo "❌ API Server: Failed"
	@curl -f -s http://localhost:3000/health && echo "✅ Rust Visualizer: OK" || echo "❌ Rust Visualizer: Failed"
	@redis-cli -h localhost -p 6379 ping > /dev/null && echo "✅ FalkorDB: OK" || echo "❌ FalkorDB: Failed"

# Open development URLs in browser
open-dev:
	@echo "🌐 Opening development URLs..."
	@command -v open >/dev/null && open http://localhost:8003 || echo "API: http://localhost:8003"
	@command -v open >/dev/null && open http://localhost:8080 || echo "Frontend: http://localhost:8080"
	@command -v open >/dev/null && open http://localhost:3000 || echo "Visualizer: http://localhost:3000"

# Validate environment configuration
validate-env:
	@echo "🔍 Validating environment configuration..."
	@test -f .env && echo "✅ .env file exists" || echo "❌ .env file missing"
	@grep -q "OPENAI_API_KEY" .env && echo "✅ OPENAI_API_KEY configured" || echo "❌ OPENAI_API_KEY missing"
	@grep -q "FALKORDB_HOST" .env && echo "✅ FALKORDB_HOST configured" || echo "❌ FALKORDB_HOST missing"

# Reset development environment
reset-dev: docker-clean setup

# =============================================================================
# Help and Documentation
# =============================================================================

# Show help information
help:
	@echo "Graphiti Development Makefile"
	@echo ""
	@echo "📋 Main Commands:"
	@echo "  setup          - Setup complete development environment"
	@echo "  dev-setup      - Full development setup"
	@echo "  setup-minimal  - Minimal services setup"
	@echo "  setup-full     - Full setup with all tools"
	@echo ""
	@echo "🐳 Docker Commands:"
	@echo "  docker-dev     - Start development services"
	@echo "  docker-prod    - Start production services"
	@echo "  docker-stop    - Stop all services"
	@echo "  docker-clean   - Clean up Docker resources"
	@echo "  docker-logs    - View service logs"
	@echo "  docker-status  - Show service status"
	@echo ""
	@echo "🔧 Code Quality:"
	@echo "  format         - Format Python code"
	@echo "  lint           - Lint Python code"
	@echo "  test           - Run Python tests"
	@echo "  check          - Run format, lint, and test"
	@echo ""
	@echo "🛠️  Utilities:"
	@echo "  health-check   - Check service health"
	@echo "  validate-env   - Validate environment config"
	@echo "  open-dev       - Open development URLs"
	@echo "  reset-dev      - Reset development environment"
	@echo "  help           - Show this help message"