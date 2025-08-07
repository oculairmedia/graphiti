#!/bin/bash

echo "Attempting to extract data from FalkorDB database..."

# Create a temporary directory for extraction
mkdir -p /tmp/falkordb_extract
cp /var/lib/docker/volumes/graphiti_falkordb_data/_data/falkordb.rdb /tmp/falkordb_extract/

# Try to start a Redis container with strict memory limits to load the data
docker run -d \
  --name redis-extract \
  --memory="2g" \
  --memory-swap="2g" \
  -v /tmp/falkordb_extract:/data \
  redis:7-alpine \
  redis-server \
  --dir /data \
  --dbfilename falkordb.rdb \
  --maxmemory 1gb \
  --maxmemory-policy allkeys-lru \
  --save ""

echo "Waiting for Redis to start..."
sleep 5

# Check if it's running
if docker ps | grep redis-extract > /dev/null; then
    echo "Redis started successfully. Attempting to dump keys..."
    
    # Get all keys
    docker exec redis-extract redis-cli --scan > /tmp/falkordb_extract/keys.txt
    
    # Try to dump the database to JSON
    docker exec redis-extract redis-cli --rdb /data/dump.rdb
    
    # Get info about the database
    docker exec redis-extract redis-cli INFO > /tmp/falkordb_extract/info.txt
    
    # Try to get graph-specific keys
    docker exec redis-extract redis-cli KEYS "*" > /tmp/falkordb_extract/all_keys.txt
    
    echo "Data extraction attempt complete. Check /tmp/falkordb_extract/"
else
    echo "Redis failed to start. Checking logs..."
    docker logs redis-extract
fi

# Cleanup
docker stop redis-extract 2>/dev/null
docker rm redis-extract 2>/dev/null

echo "Extraction process finished."