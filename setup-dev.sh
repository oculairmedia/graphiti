#!/bin/bash
# =============================================================================
# Graphiti Development Environment Setup Script
# =============================================================================
# This script sets up a complete development environment for Graphiti.
# It handles dependencies, environment configuration, and service startup.

set -euo pipefail  # Exit on error, undefined vars, pipe failures

# =============================================================================
# Configuration and Constants
# =============================================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
LOG_FILE="$PROJECT_ROOT/setup.log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default configuration
DEFAULT_ENV_FILE="$PROJECT_ROOT/.env.example"
ENV_FILE="$PROJECT_ROOT/.env"
COMPOSE_BASE="docker-compose.base.yml"
COMPOSE_DEV="docker-compose.override.yml"

# =============================================================================
# Logging and Output Functions
# =============================================================================
log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $*" | tee -a "$LOG_FILE"
}

info() {
    echo -e "${BLUE}ℹ️  $*${NC}" | tee -a "$LOG_FILE"
}

success() {
    echo -e "${GREEN}✅ $*${NC}" | tee -a "$LOG_FILE"
}

warning() {
    echo -e "${YELLOW}⚠️  $*${NC}" | tee -a "$LOG_FILE"
}

error() {
    echo -e "${RED}❌ $*${NC}" | tee -a "$LOG_FILE"
}

# =============================================================================
# Docker Compose Command Detection
# =============================================================================
get_docker_compose_cmd() {
    if docker compose version &> /dev/null; then
        echo "docker compose"
    elif command -v docker-compose &> /dev/null; then
        echo "docker-compose"
    else
        error "Neither 'docker compose' nor 'docker-compose' is available"
        exit 1
    fi
}

# =============================================================================
# System Requirements Check
# =============================================================================
check_requirements() {
    info "Checking system requirements..."
    
    local missing_deps=()
    
    # Check Docker
    if ! command -v docker &> /dev/null; then
        missing_deps+=("docker")
    fi
    
    # Check Docker Compose (prefer v2 plugin, fallback to standalone)
    if ! docker compose version &> /dev/null && ! command -v docker-compose &> /dev/null; then
        missing_deps+=("docker-compose")
    fi
    
    # Check Python (optional, for local development)
    if ! command -v python3 &> /dev/null; then
        warning "Python 3 not found - required for local development"
    fi
    
    # Check Node.js (optional, for frontend development)
    if ! command -v node &> /dev/null; then
        warning "Node.js not found - required for frontend development"
    fi
    
    # Check UV (Python package manager)
    if ! command -v uv &> /dev/null; then
        warning "UV not found - install with: curl -LsSf https://astral.sh/uv/install.sh | sh"
    fi
    
    if [ ${#missing_deps[@]} -gt 0 ]; then
        error "Missing required dependencies: ${missing_deps[*]}"
        error "Please install the missing dependencies and run this script again."
        exit 1
    fi
    
    success "All required dependencies are available"
}

# =============================================================================
# Environment Configuration
# =============================================================================
setup_environment() {
    info "Setting up environment configuration..."
    
    # Create .env from example if it doesn't exist
    if [[ ! -f "$ENV_FILE" ]]; then
        if [[ -f "$DEFAULT_ENV_FILE" ]]; then
            cp "$DEFAULT_ENV_FILE" "$ENV_FILE"
            success "Created .env file from .env.example"
        else
            error ".env.example not found. Cannot create environment file."
            exit 1
        fi
    else
        info ".env file already exists, skipping creation"
    fi
    
    # Check for required environment variables
    local required_vars=("OPENAI_API_KEY" "FALKORDB_HOST" "FALKORDB_PORT")
    local missing_vars=()
    
    # Source the .env file to check variables
    set -a  # Export all variables
    source "$ENV_FILE" 2>/dev/null || true
    set +a  # Stop exporting
    
    for var in "${required_vars[@]}"; do
        if [[ -z "${!var:-}" ]] || [[ "${!var}" == "sk-dummy" ]]; then
            missing_vars+=("$var")
        fi
    done
    
    if [ ${#missing_vars[@]} -gt 0 ]; then
        warning "The following environment variables need to be configured:"
        for var in "${missing_vars[@]}"; do
            echo "  - $var"
        done
        warning "Please edit .env file with your values"
    else
        success "Environment variables are properly configured"
    fi
}

# =============================================================================
# Docker Services Management
# =============================================================================
setup_docker_services() {
    info "Setting up Docker services..."
    
    # Check if Docker is running
    if ! docker info &> /dev/null; then
        error "Docker is not running. Please start Docker and try again."
        exit 1
    fi
    
    # Get Docker Compose command
    local compose_cmd=$(get_docker_compose_cmd)
    
    # Pull latest images
    info "Pulling latest Docker images..."
    $compose_cmd -f "$COMPOSE_BASE" -f "$COMPOSE_DEV" pull || {
        warning "Failed to pull some images, continuing with existing images"
    }
    
    # Build any local images if needed
    info "Building local images..."
    $compose_cmd -f "$COMPOSE_BASE" -f "$COMPOSE_DEV" build || {
        warning "Failed to build some images, continuing"
    }
    
    success "Docker images are ready"
}

# =============================================================================
# Service Health Checks
# =============================================================================
wait_for_service() {
    local service_name="$1"
    local health_url="$2"
    local max_attempts="${3:-30}"
    local wait_time="${4:-2}"
    
    info "Waiting for $service_name to be healthy..."
    
    for ((i=1; i<=max_attempts; i++)); do
        if curl -f -s "$health_url" &> /dev/null; then
            success "$service_name is healthy"
            return 0
        fi
        
        if [[ $i -eq $max_attempts ]]; then
            error "$service_name failed to become healthy after $max_attempts attempts"
            return 1
        fi
        
        echo -n "."
        sleep "$wait_time"
    done
}

# =============================================================================
# Development Database Setup
# =============================================================================
setup_database() {
    info "Setting up development database..."
    
    # Get Docker Compose command
    local compose_cmd=$(get_docker_compose_cmd)
    
    # Start database services first
    $compose_cmd -f "$COMPOSE_BASE" -f "$COMPOSE_DEV" up -d falkordb redis
    
    # Wait for database to be ready - use docker health check instead of URL
    info "Waiting for FalkorDB to be healthy..."
    local attempts=0
    while [[ $attempts -lt 30 ]]; do
        if $compose_cmd -f "$COMPOSE_BASE" -f "$COMPOSE_DEV" ps falkordb | grep -q "healthy"; then
            success "FalkorDB is healthy"
            break
        elif [[ $attempts -eq 29 ]]; then
            error "FalkorDB failed to become healthy after 30 attempts"
            $compose_cmd -f "$COMPOSE_BASE" -f "$COMPOSE_DEV" logs falkordb
            return 1
        fi
        echo -n "."
        sleep 2
        ((attempts++))
    done
    
    success "Database services are running"
}

# =============================================================================
# Service Startup
# =============================================================================
start_services() {
    local services_mode="${1:-dev}"
    
    info "Starting Graphiti services in $services_mode mode..."
    
    # Get Docker Compose command
    local compose_cmd=$(get_docker_compose_cmd)
    
    case "$services_mode" in
        "dev"|"development")
            # Start core development services
            $compose_cmd -f "$COMPOSE_BASE" -f "$COMPOSE_DEV" up -d
            ;;
        "minimal")
            # Start only essential services
            $compose_cmd -f "$COMPOSE_BASE" -f "$COMPOSE_DEV" up -d falkordb redis graph-visualizer-rust
            ;;
        "full")
            # Start all services including optional ones
            $compose_cmd -f "$COMPOSE_BASE" -f "$COMPOSE_DEV" --profile tools --profile frontend up -d
            ;;
        *)
            error "Unknown services mode: $services_mode"
            return 1
            ;;
    esac
    
    # Wait for key services to be healthy
    sleep 10
    
    local api_port="${API_PORT:-8003}"
    local frontend_port="${FRONTEND_PORT:-8080}"
    local rust_port="${RUST_SERVER_PORT:-3000}"
    
    # Check service health
    if [[ "$services_mode" != "minimal" ]]; then
        wait_for_service "API Server" "http://localhost:$api_port/healthcheck" 20 3 || {
            warning "API Server health check failed, checking if service is running..."
            docker-compose -f "$COMPOSE_BASE" -f "$COMPOSE_DEV" logs graph
        }
    fi
    
    wait_for_service "Rust Visualizer" "http://localhost:$rust_port/health" 15 2 || {
        warning "Rust Visualizer health check failed, checking if service is running..."
        docker-compose -f "$COMPOSE_BASE" -f "$COMPOSE_DEV" logs graph-visualizer-rust
    }
    
    success "Services are starting up successfully"
}

# =============================================================================
# Development Tools Setup
# =============================================================================
setup_development_tools() {
    info "Setting up development tools..."
    
    # Check if UV is available for Python development
    if command -v uv &> /dev/null; then
        info "Setting up Python development environment..."
        cd "$PROJECT_ROOT"
        
        # Install core dependencies
        uv sync --extra dev || warning "Failed to install Python dependencies"
        
        # Install server dependencies
        if [[ -d "server" ]]; then
            cd server
            uv sync --extra dev || warning "Failed to install server dependencies"
            cd "$PROJECT_ROOT"
        fi
        
        success "Python development environment ready"
    fi
    
    # Check if Node.js is available for frontend development
    if command -v node &> /dev/null && [[ -d "frontend" ]]; then
        info "Setting up frontend development environment..."
        cd "$PROJECT_ROOT/frontend"
        
        npm install || warning "Failed to install frontend dependencies"
        
        cd "$PROJECT_ROOT"
        success "Frontend development environment ready"
    fi
}

# =============================================================================
# Status and Information Display
# =============================================================================
display_status() {
    info "Displaying service status..."
    
    echo ""
    echo "=== Graphiti Development Environment Status ==="
    echo ""
    
    # Get Docker Compose command and show running services
    local compose_cmd=$(get_docker_compose_cmd)
    $compose_cmd -f "$COMPOSE_BASE" -f "$COMPOSE_DEV" ps
    
    echo ""
    echo "=== Access URLs ==="
    local api_port="${API_PORT:-8003}"
    local frontend_port="${FRONTEND_PORT:-8080}"
    local rust_port="${RUST_SERVER_PORT:-3000}"
    local mcp_port="${MCP_PORT:-3010}"
    local db_port="${FALKORDB_PORT:-6379}"
    
    echo "🌐 API Server:      http://localhost:$api_port"
    echo "🌐 Frontend:        http://localhost:$frontend_port"
    echo "🌐 Graph Visualizer: http://localhost:$rust_port"
    echo "🌐 MCP Server:      http://localhost:$mcp_port"
    echo "🗄️  FalkorDB:       redis://localhost:$db_port"
    
    echo ""
    echo "=== Quick Commands ==="
    echo "📊 View logs:       docker-compose -f $COMPOSE_BASE -f $COMPOSE_DEV logs -f"
    echo "🔄 Restart:         docker-compose -f $COMPOSE_BASE -f $COMPOSE_DEV restart"
    echo "🛑 Stop:            docker-compose -f $COMPOSE_BASE -f $COMPOSE_DEV down"
    echo "🔧 Shell:           docker-compose -f $COMPOSE_BASE -f $COMPOSE_DEV exec <service> bash"
    
    echo ""
    echo "=== Development Commands ==="
    echo "🐍 Python tests:   make test"
    echo "🐍 Python format:  make format"
    echo "🐍 Python lint:    make lint"
    echo "⚛️  Frontend dev:   cd frontend && npm run dev"
    echo "🦀 Rust build:     cd graph-visualizer-rust && cargo build --release"
    
    echo ""
    success "Setup complete! Your development environment is ready."
}

# =============================================================================
# Cleanup and Error Handling
# =============================================================================
cleanup() {
    local exit_code=$?
    
    if [[ $exit_code -ne 0 ]]; then
        error "Setup failed with exit code $exit_code"
        echo ""
        echo "=== Troubleshooting ==="
        echo "📋 Check logs: tail -f $LOG_FILE"
        echo "🐳 Docker logs: docker-compose -f $COMPOSE_BASE -f $COMPOSE_DEV logs"
        echo "🔍 Service status: docker-compose -f $COMPOSE_BASE -f $COMPOSE_DEV ps"
        echo ""
        echo "Common issues:"
        echo "- Ensure Docker is running"
        echo "- Check port conflicts (run 'netstat -tulpn | grep LISTEN')"
        echo "- Verify environment variables in .env"
        echo "- Ensure sufficient disk space and memory"
    fi
    
    exit $exit_code
}

# =============================================================================
# Main Script Logic
# =============================================================================
main() {
    local services_mode="${1:-dev}"
    local skip_health_check="${2:-false}"
    
    echo "=== Graphiti Development Environment Setup ==="
    echo "Starting setup at $(date)"
    echo "Log file: $LOG_FILE"
    echo ""
    
    # Initialize log file
    log "=== Starting Graphiti Development Setup ==="
    
    # Run setup steps
    check_requirements
    setup_environment
    setup_docker_services
    setup_database
    start_services "$services_mode"
    
    if [[ "$skip_health_check" != "true" ]]; then
        setup_development_tools
    fi
    
    display_status
    
    log "=== Setup completed successfully ==="
}

# =============================================================================
# Script Entry Point
# =============================================================================
trap cleanup EXIT

# Parse command line arguments
case "${1:-}" in
    "--help"|"-h")
        echo "Graphiti Development Environment Setup"
        echo ""
        echo "Usage: $0 [MODE] [OPTIONS]"
        echo ""
        echo "Modes:"
        echo "  dev          Full development setup (default)"
        echo "  minimal      Only essential services"
        echo "  full         All services including optional tools"
        echo ""
        echo "Options:"
        echo "  --skip-tools  Skip development tools setup"
        echo "  --help, -h    Show this help message"
        echo ""
        echo "Examples:"
        echo "  $0                    # Default development setup"
        echo "  $0 minimal            # Minimal services only"
        echo "  $0 full               # Full setup with all tools"
        echo "  $0 dev --skip-tools   # Development without tool setup"
        exit 0
        ;;
    *)
        main "$@"
        ;;
esac