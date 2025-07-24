#!/bin/bash

# Graphiti Frontend Startup Script
# This script sets up and starts the Graphiti frontend stack

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
COMPOSE_FILE="docker-compose.frontend.yml"
ENVIRONMENT=${1:-"development"}

echo -e "${BLUE}🚀 Graphiti Frontend Startup Script${NC}"
echo -e "${BLUE}====================================${NC}"
echo ""

# Function to print status
print_status() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Check prerequisites
echo -e "${BLUE}Checking prerequisites...${NC}"

if ! command -v docker &> /dev/null; then
    print_error "Docker is not installed. Please install Docker first."
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    print_error "Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

print_status "Docker and Docker Compose are available"

# Check if Docker is running
if ! docker info &> /dev/null; then
    print_error "Docker is not running. Please start Docker first."
    exit 1
fi

print_status "Docker daemon is running"

# Create necessary directories
echo -e "${BLUE}Creating necessary directories...${NC}"
mkdir -p logs
mkdir -p data/falkordb
mkdir -p data/redisinsight

print_status "Directories created"

# Set environment-specific configuration
case $ENVIRONMENT in
    "production")
        echo -e "${BLUE}Starting production environment...${NC}"
        COMPOSE_PROFILES="--profile production"
        ;;
    "development")
        echo -e "${BLUE}Starting development environment...${NC}"
        COMPOSE_PROFILES="--profile tools"
        ;;
    *)
        echo -e "${BLUE}Starting default environment...${NC}"
        COMPOSE_PROFILES=""
        ;;
esac

# Check if services are already running
if docker-compose -f $COMPOSE_FILE ps | grep -q "Up"; then
    print_warning "Some services are already running. Stopping them first..."
    docker-compose -f $COMPOSE_FILE down
fi

# Build images
echo -e "${BLUE}Building Docker images...${NC}"
docker-compose -f $COMPOSE_FILE build

print_status "Images built successfully"

# Start services
echo -e "${BLUE}Starting services...${NC}"
docker-compose -f $COMPOSE_FILE $COMPOSE_PROFILES up -d

# Wait for services to be ready
echo -e "${BLUE}Waiting for services to be ready...${NC}"

# Function to wait for service
wait_for_service() {
    local service_name=$1
    local health_url=$2
    local max_attempts=$3
    local attempt=1

    echo -e "${YELLOW}Waiting for $service_name...${NC}"
    
    while [ $attempt -le $max_attempts ]; do
        if curl -sf $health_url > /dev/null 2>&1; then
            print_status "$service_name is ready"
            return 0
        fi
        
        echo -e "${YELLOW}Attempt $attempt/$max_attempts - $service_name not ready yet...${NC}"
        sleep 5
        ((attempt++))
    done
    
    print_error "$service_name failed to start"
    return 1
}

# Wait for FalkorDB
echo -e "${YELLOW}Checking FalkorDB...${NC}"
if docker exec graphiti-falkordb redis-cli ping > /dev/null 2>&1; then
    print_status "FalkorDB is ready"
else
    print_error "FalkorDB is not responding"
fi

# Wait for Rust server
wait_for_service "Rust Server" "http://localhost:3000/health" 12

# Wait for Frontend
wait_for_service "Frontend" "http://localhost:8080/health" 10

# Show service status
echo -e "${BLUE}Service Status:${NC}"
docker-compose -f $COMPOSE_FILE ps

# Show URLs
echo ""
echo -e "${GREEN}🎉 Graphiti Frontend Stack Started Successfully!${NC}"
echo -e "${GREEN}=============================================${NC}"
echo ""
echo -e "${YELLOW}📊 Access URLs:${NC}"
echo -e "  Frontend Application: ${BLUE}http://localhost:8080${NC}"
echo -e "  Rust API Server:      ${BLUE}http://localhost:3000${NC}"
echo -e "  FalkorDB:            ${BLUE}localhost:6379${NC}"

if [[ $ENVIRONMENT == "development" ]] || [[ $COMPOSE_PROFILES == *"tools"* ]]; then
    echo -e "  Redis Insight:       ${BLUE}http://localhost:8001${NC}"
fi

if [[ $ENVIRONMENT == "production" ]] || [[ $COMPOSE_PROFILES == *"production"* ]]; then
    echo -e "  Load Balancer:       ${BLUE}http://localhost:80${NC}"
fi

echo ""
echo -e "${YELLOW}📝 Useful Commands:${NC}"
echo -e "  View logs:           ${BLUE}docker-compose -f $COMPOSE_FILE logs -f${NC}"
echo -e "  Stop services:       ${BLUE}docker-compose -f $COMPOSE_FILE down${NC}"
echo -e "  Restart services:    ${BLUE}docker-compose -f $COMPOSE_FILE restart${NC}"
echo -e "  Use Makefile:        ${BLUE}make -f Makefile.frontend help${NC}"

echo ""
echo -e "${GREEN}✨ Ready to visualize your knowledge graphs!${NC}"