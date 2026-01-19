#!/bin/bash
# Continuous graph quality monitoring
# Watches for: detached nodes, edge ratios, ingestion failures

INTERVAL=${1:-60}  # Check every 60 seconds by default

echo "=========================================="
echo "Graph Quality Monitor (interval: ${INTERVAL}s)"
echo "=========================================="
echo "Legend: Eps=Episodic, RT=RELATES_TO, M=MENTIONS"
echo "Expected ratio: ~5.3 edges per episode"
echo ""

# Baseline for ratio checks
LAST_EPISODIC=0
LAST_EDGES=0

while true; do
    NOW=$(date '+%H:%M:%S')
    
    # Get current counts
    isolated=$(redis-cli -h localhost -p 6379 GRAPH.QUERY graphiti_migration "
    MATCH (e:Episodic) WHERE NOT (e)-[]-() RETURN count(e) as c
    " 2>/dev/null | grep -E '^[0-9]+$' | head -1)
    
    episodic=$(redis-cli -h localhost -p 6379 GRAPH.QUERY graphiti_migration "
    MATCH (e:Episodic) RETURN count(e) as c
    " 2>/dev/null | grep -E '^[0-9]+$' | head -1)
    
    edges=$(redis-cli -h localhost -p 6379 GRAPH.QUERY graphiti_migration "
    MATCH ()-[r]->() RETURN count(r) as c
    " 2>/dev/null | grep -E '^[0-9]+$' | head -1)
    
    relates_to=$(redis-cli -h localhost -p 6379 GRAPH.QUERY graphiti_migration "
    MATCH ()-[r:RELATES_TO]->() RETURN count(r) as c
    " 2>/dev/null | grep -E '^[0-9]+$' | head -1)
    
    mentions=$(redis-cli -h localhost -p 6379 GRAPH.QUERY graphiti_migration "
    MATCH ()-[r:MENTIONS]->() RETURN count(r) as c
    " 2>/dev/null | grep -E '^[0-9]+$' | head -1)
    
    # Calculate deltas
    if [ "$LAST_EPISODIC" -gt "0" ]; then
        delta_ep=$((episodic - LAST_EPISODIC))
        delta_edges=$((edges - LAST_EDGES))
    else
        delta_ep="-"
        delta_edges="-"
    fi
    
    # Calculate edge ratio using awk (no bc needed)
    ratio=$(awk "BEGIN {printf \"%.2f\", $edges / $episodic}")
    ratio_int=$(awk "BEGIN {printf \"%d\", $edges / $episodic}")
    
    # Status line
    STATUS="OK"
    ALERTS=""
    
    # Check for problems
    if [ "$isolated" -gt "0" ]; then
        STATUS="WARN"
        ALERTS="$ALERTS [DETACHED:$isolated]"
    fi
    
    # Check edge ratio (should be ~5+ edges per episode)
    if [ "$ratio_int" -lt "3" ]; then
        STATUS="WARN"
        ALERTS="$ALERTS [LOW_RATIO]"
    fi
    
    # Check if new episodes are getting edges
    if [ "$delta_ep" != "-" ] && [ "$delta_ep" -gt "0" ] && [ "$delta_edges" -eq "0" ]; then
        STATUS="ALERT"
        ALERTS="$ALERTS [NEW_EPS_NO_EDGES]"
    fi
    
    # Output
    printf "[%s] %-5s | Eps:%d (+%s) | Edges:%d (+%s) | RT:%d M:%d | Ratio:%s | Iso:%d%s\n" \
        "$NOW" "$STATUS" "$episodic" "$delta_ep" "$edges" "$delta_edges" \
        "$relates_to" "$mentions" "$ratio" "$isolated" "$ALERTS"
    
    # Save for next iteration
    LAST_EPISODIC=$episodic
    LAST_EDGES=$edges
    
    sleep $INTERVAL
done
