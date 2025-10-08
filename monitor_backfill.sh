#!/bin/bash

LOGFILE="/tmp/edge_backfill.log"
TOTAL_EDGES=17323
CHECK_INTERVAL=30

echo "🔄 Monitoring edge embedding backfill..."
echo "📊 Total edges to process: $TOTAL_EDGES"
echo ""

while true; do
    # Check if process is still running
    if ! ps aux | grep -q "[p]ython3 regenerate_edge_embeddings_ollama.py"; then
        echo "✅ Backfill process completed or stopped!"
        break
    fi
    
    # Get current progress
    CURRENT_SKIP=$(grep -o "skip': [0-9]*" "$LOGFILE" 2>/dev/null | tail -1 | awk '{print $2}')
    
    if [ -n "$CURRENT_SKIP" ]; then
        PERCENT=$((CURRENT_SKIP * 100 / TOTAL_EDGES))
        REMAINING=$((TOTAL_EDGES - CURRENT_SKIP))
        BATCHES_LEFT=$((REMAINING / 50))
        
        echo "[$(date '+%H:%M:%S')] Progress: $CURRENT_SKIP / $TOTAL_EDGES edges ($PERCENT%) - $BATCHES_LEFT batches remaining"
    fi
    
    sleep $CHECK_INTERVAL
done

echo ""
echo "🎉 Backfill complete! Restarting worker..."
cd /opt/stacks/graphiti
docker-compose start graphiti-worker

echo ""
echo "✅ Worker restarted. Monitoring worker logs..."
docker logs -f --tail=50 graphiti-graphiti-worker-1
