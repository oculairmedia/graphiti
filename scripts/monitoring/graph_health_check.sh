#!/bin/bash
# Graphiti Graph Health Check
# Monitors for detached nodes, edge counts, and ingestion health

echo "========================================"
echo "Graphiti Graph Health Check"
echo "$(date)"
echo "========================================"
echo ""

# 1. Check isolated episodic nodes
echo "1. Isolated Episodic Nodes (detached points)"
echo "   ----------------------------------------"
isolated=$(redis-cli -h localhost -p 6379 GRAPH.QUERY graphiti_migration "
MATCH (e:Episodic) WHERE NOT (e)-[]-() RETURN count(e) as c
" 2>/dev/null | grep -E '^[0-9]+$' | head -1)
echo "   Count: $isolated"
if [ "$isolated" -gt "0" ]; then
    echo "   WARNING: Found $isolated isolated episodic nodes!"
    echo "   Recent isolated nodes:"
    redis-cli -h localhost -p 6379 GRAPH.QUERY graphiti_migration "
    MATCH (e:Episodic) WHERE NOT (e)-[]-() 
    RETURN e.name, e.created_at ORDER BY e.created_at DESC LIMIT 3
    " 2>/dev/null | grep -E "^(Claude|Session|[0-9]{4})" | head -6
fi
echo ""

# 2. Check node counts
echo "2. Node Counts"
echo "   -----------"
entity_count=$(redis-cli -h localhost -p 6379 GRAPH.QUERY graphiti_migration "
MATCH (n:Entity) RETURN count(n) as c
" 2>/dev/null | grep -E '^[0-9]+$' | head -1)
episodic_count=$(redis-cli -h localhost -p 6379 GRAPH.QUERY graphiti_migration "
MATCH (n:Episodic) RETURN count(n) as c
" 2>/dev/null | grep -E '^[0-9]+$' | head -1)
echo "   Entity nodes: $entity_count"
echo "   Episodic nodes: $episodic_count"
echo ""

# 3. Check edge counts
echo "3. Edge Counts"
echo "   -----------"
relates_to=$(redis-cli -h localhost -p 6379 GRAPH.QUERY graphiti_migration "
MATCH ()-[r:RELATES_TO]->() RETURN count(r) as c
" 2>/dev/null | grep -E '^[0-9]+$' | head -1)
mentions=$(redis-cli -h localhost -p 6379 GRAPH.QUERY graphiti_migration "
MATCH ()-[r:MENTIONS]->() RETURN count(r) as c
" 2>/dev/null | grep -E '^[0-9]+$' | head -1)
echo "   RELATES_TO edges: $relates_to"
echo "   MENTIONS edges: $mentions"
echo ""

# 4. Check recent ingestion (last hour)
echo "4. Recent Ingestion (last hour)"
echo "   ----------------------------"
one_hour_ago=$(date -u -d '1 hour ago' '+%Y-%m-%dT%H:%M:%S')
recent_episodes=$(redis-cli -h localhost -p 6379 GRAPH.QUERY graphiti_migration "
MATCH (e:Episodic) WHERE e.created_at > '$one_hour_ago' RETURN count(e) as c
" 2>/dev/null | grep -E '^[0-9]+$' | head -1)
recent_edges=$(redis-cli -h localhost -p 6379 GRAPH.QUERY graphiti_migration "
MATCH ()-[r]->() WHERE r.created_at > '$one_hour_ago' RETURN count(r) as c
" 2>/dev/null | grep -E '^[0-9]+$' | head -1)
echo "   New episodes: $recent_episodes"
echo "   New edges: $recent_edges"

# Check if recent episodes have edges
if [ "$recent_episodes" -gt "0" ]; then
    recent_isolated=$(redis-cli -h localhost -p 6379 GRAPH.QUERY graphiti_migration "
    MATCH (e:Episodic) WHERE e.created_at > '$one_hour_ago' AND NOT (e)-[]-() RETURN count(e) as c
    " 2>/dev/null | grep -E '^[0-9]+$' | head -1)
    if [ "$recent_isolated" -gt "0" ]; then
        echo "   WARNING: $recent_isolated recent episodes have NO edges!"
    else
        echo "   OK: All recent episodes have edges"
    fi
fi
echo ""

# 5. Worker status
echo "5. Worker Status"
echo "   -------------"
for worker in persist extract resolve edge; do
    status=$(docker ps --filter "name=graphiti-graphiti-temporal-ingestion-${worker}-worker" --format "{{.Status}}" 2>/dev/null | head -1)
    if [ -n "$status" ]; then
        echo "   ${worker}: $status"
    else
        echo "   ${worker}: NOT RUNNING"
    fi
done
echo ""

echo "========================================"
echo "Health check complete"
echo "========================================"
