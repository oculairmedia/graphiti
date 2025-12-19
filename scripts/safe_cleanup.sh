#!/bin/bash
# =============================================================================
# Safe Docker Cleanup Script for Graphiti Stack
# =============================================================================
# This script cleans up Docker resources WITHOUT touching critical data volumes.
# Use this instead of `docker system prune` to protect FalkorDB and Neo4j data.
#
# Usage:
#   ./safe_cleanup.sh           # Normal cleanup (images, containers, networks)
#   ./safe_cleanup.sh --all     # Aggressive cleanup (includes build cache)
#   ./safe_cleanup.sh --dry-run # Show what would be cleaned
# =============================================================================

set -e

# PROTECTED VOLUMES - NEVER DELETE THESE
PROTECTED_VOLUMES=(
    "graphiti_falkordb_data"
    "graphiti_neo4j_data"
    "graphiti_queued_data"
    "graphiti_visualizer_duckdb"
    "graphiti_grafana_data"
    "graphiti_prometheus_data"
    "graphiti_sync_metadata"
)

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

DRY_RUN=false
AGGRESSIVE=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run) DRY_RUN=true; shift ;;
        --all) AGGRESSIVE=true; shift ;;
        -h|--help)
            echo "Usage: $0 [--dry-run] [--all]"
            echo ""
            echo "Options:"
            echo "  --dry-run  Show what would be cleaned without doing it"
            echo "  --all      Aggressive cleanup (includes build cache)"
            echo ""
            echo "Protected volumes (NEVER deleted):"
            for vol in "${PROTECTED_VOLUMES[@]}"; do
                echo "  - $vol"
            done
            exit 0
            ;;
        *) log_error "Unknown option: $1"; exit 1 ;;
    esac
done

echo "=============================================="
echo "   Safe Docker Cleanup for Graphiti Stack"
echo "=============================================="
echo ""

# Verify protected volumes exist
log_info "Verifying protected volumes..."
for vol in "${PROTECTED_VOLUMES[@]}"; do
    if docker volume inspect "$vol" &>/dev/null; then
        SIZE=$(docker system df -v 2>/dev/null | grep "$vol" | awk '{print $4}' || echo "unknown")
        log_info "  ✓ $vol ($SIZE)"
    else
        log_warn "  ✗ $vol (not found - may not be created yet)"
    fi
done
echo ""

# Show current disk usage
log_info "Current Docker disk usage:"
docker system df
echo ""

if [[ "$DRY_RUN" == "true" ]]; then
    log_warn "DRY RUN MODE - No changes will be made"
    echo ""
fi

# 1. Remove stopped containers (except graphiti ones that might just be stopped)
log_info "Cleaning up stopped containers..."
if [[ "$DRY_RUN" == "true" ]]; then
    docker ps -a --filter "status=exited" --format "{{.Names}}" | grep -v "^graphiti-" || true
else
    docker container prune -f
fi

# 2. Remove dangling images
log_info "Cleaning up dangling images..."
if [[ "$DRY_RUN" == "true" ]]; then
    docker images -f "dangling=true" -q | head -10
    echo "  (showing first 10)"
else
    docker image prune -f
fi

# 3. Remove unused networks (except graphiti network)
log_info "Cleaning up unused networks..."
if [[ "$DRY_RUN" == "true" ]]; then
    docker network ls --filter "dangling=true" --format "{{.Name}}" | grep -v "graphiti" || true
else
    # Prune networks but graphiti_network will be protected if containers are using it
    docker network prune -f 2>/dev/null || true
fi

# 4. Clean up dangling volumes (BUT NOT PROTECTED ONES)
log_info "Cleaning up dangling volumes (protecting critical data)..."
DANGLING_VOLUMES=$(docker volume ls -qf dangling=true 2>/dev/null || true)
for vol in $DANGLING_VOLUMES; do
    PROTECTED=false
    for protected in "${PROTECTED_VOLUMES[@]}"; do
        if [[ "$vol" == "$protected" ]]; then
            PROTECTED=true
            break
        fi
    done
    
    if [[ "$PROTECTED" == "true" ]]; then
        log_warn "  PROTECTED (skipping): $vol"
    else
        if [[ "$DRY_RUN" == "true" ]]; then
            log_info "  Would remove: $vol"
        else
            log_info "  Removing: $vol"
            docker volume rm "$vol" 2>/dev/null || log_warn "  Failed to remove $vol"
        fi
    fi
done

# 5. Aggressive cleanup (build cache)
if [[ "$AGGRESSIVE" == "true" ]]; then
    log_info "Aggressive cleanup: Removing build cache..."
    if [[ "$DRY_RUN" == "true" ]]; then
        docker builder prune -a --dry-run 2>/dev/null || true
    else
        docker builder prune -a -f
    fi
fi

echo ""
log_info "Cleanup complete!"
echo ""

# Show new disk usage
log_info "Docker disk usage after cleanup:"
docker system df
echo ""

# Final safety check
log_info "Verifying protected volumes still exist..."
ALL_PROTECTED=true
for vol in "${PROTECTED_VOLUMES[@]}"; do
    if docker volume inspect "$vol" &>/dev/null; then
        log_info "  ✓ $vol"
    else
        log_error "  ✗ $vol MISSING!"
        ALL_PROTECTED=false
    fi
done

if [[ "$ALL_PROTECTED" == "true" ]]; then
    echo ""
    log_info "All critical data volumes are safe!"
else
    echo ""
    log_error "WARNING: Some protected volumes are missing!"
    log_error "You may need to restore from backup."
fi
