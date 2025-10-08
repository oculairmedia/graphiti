#!/bin/bash

# =============================================================================
# Graphiti Environment Validation Script
# =============================================================================
# This script validates that all required environment variables are set
# and provides helpful error messages for missing or invalid configurations.
#
# Usage:
#   ./scripts/validate-env.sh [--strict]
#   
# Options:
#   --strict    Exit with error code 1 if any warnings are found
# =============================================================================

set -e

# Colors for output
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Counters
ERRORS=0
WARNINGS=0
INFO=0
STRICT_MODE=false

# Parse command line arguments
if [[ "$1" == "--strict" ]]; then
    STRICT_MODE=true
fi

# Helper functions
error() {
    printf "${RED}[ERROR]${NC} %s\n" "$1"
    ((ERRORS++))
}

warning() {
    printf "${YELLOW}[WARNING]${NC} %s\n" "$1"
    ((WARNINGS++))
}

info() {
    printf "${GREEN}[INFO]${NC} %s\n" "$1"
    ((INFO++))
}

debug() {
    printf "${BLUE}[DEBUG]${NC} %s\n" "$1"
}

# Check if variable is set and not empty
check_required() {
    local var_name="$1"
    local var_value="${!var_name}"
    local description="$2"
    
    if [[ -z "$var_value" ]]; then
        error "Required variable $var_name is not set or empty"
        echo "       Description: $description"
        echo "       Set this in your .env file or environment"
        return 1
    else
        debug "$var_name is set to: $var_value"
        return 0
    fi
}

# Check if variable is set with a default warning
check_with_default() {
    local var_name="$1"
    local default_value="$2"
    local description="$3"
    local var_value="${!var_name}"
    
    if [[ -z "$var_value" ]]; then
        info "$var_name not set, will use default: $default_value"
        echo "       Description: $description"
    else
        debug "$var_name is set to: $var_value"
    fi
}

# Check if URL is accessible
check_url() {
    local url="$1"
    local service_name="$2"
    local timeout="${3:-5}"
    
    if command -v curl >/dev/null 2>&1; then
        if curl -s --max-time "$timeout" --head "$url" >/dev/null 2>&1; then
            info "$service_name is accessible at $url"
        else
            warning "$service_name might not be accessible at $url"
            echo "        This could cause connection issues during runtime"
        fi
    else
        debug "curl not available, skipping URL check for $url"
    fi
}

# Check if port is valid
check_port() {
    local var_name="$1"
    local var_value="${!var_name}"
    
    if [[ -n "$var_value" ]]; then
        if [[ "$var_value" =~ ^[0-9]+$ ]] && [ "$var_value" -ge 1 ] && [ "$var_value" -le 65535 ]; then
            debug "$var_name port $var_value is valid"
        else
            error "$var_name has invalid port number: $var_value"
            echo "       Ports must be between 1 and 65535"
        fi
    fi
}

echo "==================================================================="
echo "                Graphiti Environment Validation"
echo "==================================================================="
echo

# Load .env file if it exists
if [[ -f ".env" ]]; then
    info "Loading environment from .env file"
    set -a  # automatically export all variables
    source .env
    set +a
else
    warning ".env file not found, using only system environment"
    echo "        Copy .env.example to .env and customize for your setup"
fi

echo
echo "==================================================================="
echo "Validating Core Configuration..."
echo "==================================================================="

# Validate LLM Configuration
if [[ "${USE_CEREBRAS:-false}" == "true" ]]; then
    echo "🧠 Cerebras Configuration:"
    check_required "CEREBRAS_API_KEY" "Cerebras API key for high-speed inference"
    check_with_default "CEREBRAS_MODEL" "qwen-3-coder-480b" "Primary Cerebras model"
    check_with_default "CEREBRAS_SMALL_MODEL" "qwen-3-coder-480b" "Smaller Cerebras model"
else
    info "Cerebras is disabled (USE_CEREBRAS=${USE_CEREBRAS:-false})"
fi

if [[ "${USE_OLLAMA:-true}" == "true" ]]; then
    echo "🦙 Ollama Configuration:"
    check_with_default "OLLAMA_BASE_URL" "http://100.81.139.20:11434/v1" "Ollama server endpoint"
    check_with_default "OLLAMA_MODEL" "gemma3:12b" "Primary Ollama model"
    
    # Test Ollama connectivity if URL is set
    if [[ -n "${OLLAMA_BASE_URL}" ]]; then
        check_url "${OLLAMA_BASE_URL}/models" "Ollama API"
    fi
else
    warning "Ollama is disabled (USE_OLLAMA=${USE_OLLAMA:-true})"
    echo "        Make sure you have another LLM provider configured"
fi

# Validate Database Configuration  
echo
echo "📊 Database Configuration:"
if [[ "${USE_FALKORDB:-true}" == "true" ]]; then
    check_with_default "FALKORDB_HOST" "falkordb" "FalkorDB hostname"
    check_with_default "FALKORDB_PORT" "6379" "FalkorDB port"
    check_with_default "FALKORDB_DATABASE" "graphiti_migration" "FalkorDB database name"
    check_port "FALKORDB_PORT"
else
    warning "FalkorDB is disabled, make sure Neo4j is properly configured"
fi

# Validate Port Configuration
echo
echo "🔌 Port Configuration:"
check_port "API_PORT"
check_port "FRONTEND_PORT" 
check_port "RUST_SERVER_PORT"
check_port "RUST_CENTRALITY_PORT"
check_port "RUST_SEARCH_PORT"
check_port "MCP_PORT"
check_port "QUEUE_PORT"
check_port "NGINX_HTTP_PORT"
check_port "NGINX_HTTPS_PORT"

# Validate Network Configuration
echo
echo "🌐 Network Configuration:"
check_with_default "HOMEPAGE_HOST" "192.168.50.90" "Homepage/dashboard host"

if [[ -n "${HOMEPAGE_HOST}" ]]; then
    info "Services will be accessible at http://${HOMEPAGE_HOST}:PORT"
fi

# Validate Performance Settings
echo
echo "⚡ Performance Configuration:"
check_with_default "NODE_LIMIT" "100000" "Maximum nodes in visualization"
check_with_default "EDGE_LIMIT" "100000" "Maximum edges in visualization"
check_with_default "SEMAPHORE_LIMIT" "5" "Concurrent operation limit"
check_with_default "WORKER_COUNT" "2" "Number of worker processes"

# Check for common configuration issues
echo
echo "==================================================================="
echo "Checking for Common Issues..."
echo "==================================================================="

# Check for conflicting configurations
if [[ "${USE_CEREBRAS:-false}" == "false" && "${USE_OLLAMA:-true}" == "false" ]]; then
    error "No LLM provider enabled! Enable either Cerebras or Ollama"
fi

# Check for missing critical directories in Docker context
if [[ -f "docker-compose.yml" ]]; then
    info "Docker Compose configuration found"
    
    # Check if required directories exist for volume mounts
    if [[ ! -d "nginx" ]]; then
        warning "nginx/ directory not found - Nginx service may fail to start"
    fi
else
    warning "docker-compose.yml not found in current directory"
    echo "        Make sure you're running this from the project root"
fi

# Check for suspicious default values that should be changed
if [[ "${OPENAI_API_KEY}" == "sk-dummy" ]] || [[ "${OPENAI_API_KEY}" == "dummy_key_using_ollama_instead" ]]; then
    info "Using dummy OpenAI API key (OK if using only Ollama/Cerebras)"
fi

# Summary
echo
echo "==================================================================="
echo "                    Validation Summary"
echo "==================================================================="

if [[ $ERRORS -eq 0 && $WARNINGS -eq 0 ]]; then
    echo -e "${GREEN}✅ Configuration looks good! No errors or warnings found.${NC}"
    exit 0
elif [[ $ERRORS -eq 0 ]]; then
    echo -e "${YELLOW}⚠️  Configuration has $WARNINGS warning(s) but no errors.${NC}"
    echo "   Your setup should work but consider addressing the warnings."
    
    if [[ "$STRICT_MODE" == "true" ]]; then
        echo -e "${RED}❌ Exiting with error code due to --strict mode${NC}"
        exit 1
    fi
    exit 0
else
    echo -e "${RED}❌ Configuration has $ERRORS error(s) and $WARNINGS warning(s).${NC}"
    echo "   Please fix the errors before proceeding."
    exit 1
fi