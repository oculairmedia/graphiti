#!/bin/bash
# =============================================================================
# Quality of Life Improvements Test Suite
# =============================================================================
# This script tests all the quality of life improvements implemented

set -euo pipefail

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

success() {
    echo -e "${GREEN}✅ $*${NC}"
}

error() {
    echo -e "${RED}❌ $*${NC}"
}

info() {
    echo -e "${BLUE}ℹ️  $*${NC}"
}

warning() {
    echo -e "${YELLOW}⚠️  $*${NC}"
}

# Test counters
TESTS_TOTAL=0
TESTS_PASSED=0

run_test() {
    local test_name="$1"
    local test_command="$2"
    
    ((TESTS_TOTAL++))
    info "Testing: $test_name"
    
    if eval "$test_command" > /dev/null 2>&1; then
        success "$test_name"
        ((TESTS_PASSED++))
    else
        error "$test_name"
    fi
}

echo "🧪 Quality of Life Improvements Test Suite"
echo "=========================================="
echo ""

# =============================================================================
# Environment Variable Tests
# =============================================================================
info "📋 Environment Variable Tests"
run_test "Environment file exists" "test -f .env"
run_test "Environment documentation exists" "test -f .env.example"
run_test "Environment validation command" "make validate-env"
run_test "Environment has API key configured" "grep -q 'OPENAI_API_KEY' .env"
run_test "Environment has database config" "grep -q 'FALKORDB_HOST' .env"
run_test "No exposed secrets in .env" "! grep -E 'csk-[a-zA-Z0-9]|sk-[a-zA-Z0-9]' .env"

echo ""

# =============================================================================
# Docker Compose Tests
# =============================================================================
info "🐳 Docker Compose Configuration Tests"
run_test "Base compose file exists" "test -f docker-compose.base.yml"
run_test "Dev override exists" "test -f docker-compose.override.yml"
run_test "Production override exists" "test -f docker-compose.prod.override.yml"
run_test "Frontend override exists" "test -f docker-compose.frontend.override.yml"
run_test "Queue override exists" "test -f docker-compose.queue.override.yml"
run_test "All compose files validate" "make validate-compose"
run_test "No hardcoded IPs in base config" "! grep -E '192\.168\.50\.90|100\.81\.139\.20' docker-compose.base.yml"

echo ""

# =============================================================================
# Setup Script Tests  
# =============================================================================
info "📜 Setup Script Tests"
run_test "Setup script exists and is executable" "test -x setup-dev.sh"
run_test "Setup script shows help" "./setup-dev.sh --help"
run_test "Setup script has Docker Compose detection" "grep -q 'get_docker_compose_cmd' setup-dev.sh"
run_test "Setup script uses environment variables" "grep -q 'COMPOSE_BASE' setup-dev.sh"

echo ""

# =============================================================================
# Makefile Tests
# =============================================================================
info "🔧 Makefile Tests"
run_test "Makefile exists" "test -f Makefile"
run_test "Makefile help command" "make help"
run_test "Makefile uses Docker Compose v2" "grep -q 'docker compose' Makefile"
run_test "Makefile has validation commands" "grep -q 'validate-compose' Makefile"
run_test "Makefile has all Docker commands" "make help | grep -q 'docker-dev'"

echo ""

# =============================================================================
# Documentation Tests
# =============================================================================
info "📚 Documentation Tests"
run_test "Docker Compose README exists" "test -f docker-compose.README.md"
run_test "Environment variables guide exists" "test -f docs/ENVIRONMENT_VARIABLES.md"
run_test "VS Code configuration exists" "test -f .vscode/settings.json"
run_test "Development tasks configured" "test -f .vscode/tasks.json"

echo ""

# =============================================================================
# Service Health Tests (if services are running)
# =============================================================================
if docker compose -f docker-compose.base.yml -f docker-compose.override.yml ps | grep -q "Up"; then
    info "🏥 Service Health Tests (services detected)"
    run_test "API server health endpoint" "curl -f -s http://localhost:8003/healthcheck"
    run_test "FalkorDB accessible" "docker compose -f docker-compose.base.yml -f docker-compose.override.yml exec -T falkordb redis-cli ping"
    run_test "Services show healthy status" "make health-check"
else
    warning "Services not running - skipping health tests"
fi

echo ""

# =============================================================================
# Security Tests
# =============================================================================
info "🔒 Security Tests"
run_test "No API keys in compose files" "! find . -name 'docker-compose*.yml' -exec grep -l 'csk-\|sk-[a-zA-Z0-9]' {} \;"
run_test "No hardcoded passwords in configs" "! grep -r 'password.*=' docker-compose*.yml | grep -v 'PASSWORD=\${'"
run_test "Environment example has no real secrets" "! grep -E 'csk-[a-zA-Z0-9]|sk-[a-zA-Z0-9]' .env.example"

echo ""

# =============================================================================
# Results Summary
# =============================================================================
echo "📊 Test Results Summary"
echo "======================"
echo "Tests Passed: $TESTS_PASSED/$TESTS_TOTAL"

if [ $TESTS_PASSED -eq $TESTS_TOTAL ]; then
    success "All tests passed! 🎉"
    echo ""
    echo "🚀 Quality of life improvements are working correctly!"
    echo "You can now use:"
    echo "  • make setup - One-command development setup"
    echo "  • make validate-compose - Validate all configurations" 
    echo "  • make health-check - Check service health"
    echo "  • make help - See all available commands"
    exit 0
else
    warning "Some tests failed. Check the output above for details."
    exit 1
fi