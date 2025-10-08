#!/bin/bash
# Script to set up FalkorDB and migrate Neo4j data

echo "=== FalkorDB Setup Script ==="

# Function to check if a service is running
check_service() {
    local service=$1
    local port=$2
    nc -z localhost $port 2>/dev/null
    return $?
}

# Step 1: Start FalkorDB container
echo -e "\n1. Starting FalkorDB container..."
docker-compose up -d falkordb

# Wait for FalkorDB to be ready
echo "   Waiting for FalkorDB to start..."
for i in {1..30}; do
    if check_service "FalkorDB" 6379; then
        echo "   ✓ FalkorDB is running"
        break
    fi
    sleep 1
done

# Step 2: Check if Neo4j is running
echo -e "\n2. Checking Neo4j status..."
if check_service "Neo4j" 7687; then
    echo "   ✓ Neo4j is running"
else
    echo "   ✗ Neo4j is not running. Please start it first:"
    echo "     docker-compose up -d neo4j"
    exit 1
fi

# Step 3: Install FalkorDB support if needed
echo -e "\n3. Checking Python dependencies..."
if ! python3 -c "import falkordb" 2>/dev/null; then
    echo "   Installing FalkorDB Python client..."
    pip install redis falkordb
fi

# Step 4: Run migration
echo -e "\n4. Ready to migrate data?"
echo "   This will copy all data from Neo4j to FalkorDB"
read -p "   Continue? (y/n) " -n 1 -r
echo

if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo -e "\n   Running migration..."
    python3 scripts/migrate_neo4j_to_falkordb.py
else
    echo "   Migration cancelled"
fi

# Step 5: Show access information
echo -e "\n=== Access Information ==="
echo "FalkorDB UI: http://localhost:3000"
echo "FalkorDB Port: 6379"
echo "Neo4j Browser: http://localhost:7474"
echo ""
echo "To test FalkorDB with Graphiti:"
echo "  python3 examples/falkordb_ollama_example.py"
echo ""
echo "To connect to FalkorDB CLI:"
echo "  docker exec -it graphiti-falkordb-1 redis-cli"
echo "  Then: GRAPH.QUERY graphiti_migration 'MATCH (n) RETURN count(n)'"