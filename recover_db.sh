#!/bin/bash

echo "Attempting to recover FalkorDB database with strict memory limits..."

# Start a FalkorDB container with very strict memory limits
docker run -d \
  --name falkordb-recovery \
  --memory="1g" \
  --memory-swap="1g" \
  -v /var/lib/docker/volumes/graphiti_falkordb_data/_data:/data:ro \
  -p 6380:6379 \
  falkordb/falkordb:latest \
  redis-server \
  --loadmodule /var/lib/falkordb/bin/falkordb.so \
  --dir /data \
  --dbfilename falkordb.rdb \
  --maxmemory 800mb \
  --maxmemory-policy allkeys-lru \
  --save "" \
  --loglevel debug

echo "Waiting for FalkorDB to start..."
sleep 10

# Check if it's running
if docker ps | grep falkordb-recovery > /dev/null; then
    echo "FalkorDB started! Attempting to list graphs..."
    
    # List all graphs
    docker exec falkordb-recovery redis-cli GRAPH.LIST > /tmp/graphs.txt 2>&1
    cat /tmp/graphs.txt
    
    # Try to get graph info for each graph
    if [ -f /tmp/graphs.txt ] && [ -s /tmp/graphs.txt ]; then
        while IFS= read -r graph; do
            if [ ! -z "$graph" ]; then
                echo "Getting info for graph: $graph"
                docker exec falkordb-recovery redis-cli GRAPH.INFO "$graph" > "/tmp/graph_${graph}_info.txt" 2>&1
            fi
        done < /tmp/graphs.txt
    fi
    
    echo "Attempting to export data..."
    docker exec falkordb-recovery redis-cli --rdb /tmp/export.rdb
    docker cp falkordb-recovery:/tmp/export.rdb /tmp/falkordb_export.rdb 2>/dev/null
    
else
    echo "FalkorDB failed to start. Checking logs..."
    docker logs --tail 50 falkordb-recovery
fi

# Check container status
echo "Container status:"
docker ps -a | grep falkordb-recovery

# Cleanup
echo "Keeping container for manual inspection. To remove, run:"
echo "docker stop falkordb-recovery && docker rm falkordb-recovery"