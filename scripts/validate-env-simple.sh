#!/bin/bash

# Simple Graphiti Environment Validation
# Usage: ./scripts/validate-env-simple.sh

set -e

echo "========================================"
echo "    Graphiti Environment Validation"  
echo "========================================"

# Colors
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
NC='\033[0m'

ERRORS=0
WARNINGS=0

# Load .env file if exists
if [[ -f ".env" ]]; then
    echo "Loading .env file..."
    source .env
else
    echo "WARNING: .env file not found!"
    ((WARNINGS++))
fi

echo
echo "Checking Core Configuration..."

# Check LLM Configuration
echo "🧠 LLM Provider Check:"
if [[ "${USE_CEREBRAS:-false}" == "true" ]]; then
    if [[ -z "${CEREBRAS_API_KEY}" ]]; then
        printf "${RED}ERROR: CEREBRAS_API_KEY required when USE_CEREBRAS=true${NC}\n"
        ((ERRORS++))
    else
        printf "${GREEN}✓ Cerebras API key configured${NC}\n"
    fi
fi

if [[ "${USE_OLLAMA:-true}" == "true" ]]; then
    if [[ -z "${OLLAMA_BASE_URL}" ]]; then
        printf "${YELLOW}WARNING: OLLAMA_BASE_URL not set, using default${NC}\n"
        ((WARNINGS++))
    else
        printf "${GREEN}✓ Ollama URL: ${OLLAMA_BASE_URL}${NC}\n"
    fi
fi

# Check Database Configuration  
echo
echo "📊 Database Check:"
if [[ "${USE_FALKORDB:-true}" == "true" ]]; then
    printf "${GREEN}✓ Using FalkorDB (default)${NC}\n"
    printf "   Host: ${FALKORDB_HOST:-falkordb}\n"
    printf "   Port: ${FALKORDB_PORT:-6379}\n"
    printf "   Database: ${FALKORDB_DATABASE:-graphiti_migration}\n"
else
    printf "${YELLOW}WARNING: FalkorDB disabled${NC}\n"
    ((WARNINGS++))
fi

# Check Port Configuration
echo
echo "🔌 Port Configuration:"
printf "   API: ${API_PORT:-8003}\n"
printf "   Frontend: ${FRONTEND_PORT:-8084}\n" 
printf "   Visualizer: ${RUST_SERVER_PORT:-3000}\n"
printf "   Queue: ${QUEUE_PORT:-8093}\n"

# Check Network
echo
echo "🌐 Network:"
printf "   Homepage Host: ${HOMEPAGE_HOST:-192.168.50.90}\n"

# Check for conflicting settings
echo
echo "⚠️  Checking for Issues..."
if [[ "${USE_CEREBRAS:-false}" == "false" && "${USE_OLLAMA:-true}" == "false" ]]; then
    printf "${RED}ERROR: No LLM provider enabled!${NC}\n"
    ((ERRORS++))
fi

# Summary
echo
echo "========================================"
echo "              Summary"
echo "========================================"

if [[ $ERRORS -eq 0 && $WARNINGS -eq 0 ]]; then
    printf "${GREEN}✅ All checks passed!${NC}\n"
    exit 0
elif [[ $ERRORS -eq 0 ]]; then
    printf "${YELLOW}⚠️  Configuration OK with $WARNINGS warning(s)${NC}\n"
    exit 0
else
    printf "${RED}❌ Found $ERRORS error(s) and $WARNINGS warning(s)${NC}\n"
    exit 1
fi