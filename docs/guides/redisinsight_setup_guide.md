# RedisInsight Setup Guide for FalkorDB

## Overview
RedisInsight is now running as part of your Graphiti stack, providing a comprehensive GUI for managing and querying your FalkorDB graph database.

## Access RedisInsight
- **URL**: http://192.168.50.90:5540
- **First Run**: Accept the privacy settings and EULA

## Connect to FalkorDB

### Step 1: Add Database Connection
1. Click on "Add Redis Database"
2. Enter the following connection details:
   - **Host**: `falkordb` (NOT localhost - use the Docker service name)
   - **Port**: `6379` (internal port, not 6389)
   - **Database Alias**: `FalkorDB Graph` (or any name you prefer)
   - **Username**: Leave empty
   - **Password**: Leave empty (we disabled authentication)
3. Click "Add Redis Database"

### Step 2: Access the Graph Module
1. Once connected, click on your FalkorDB connection
2. In the left sidebar, look for "Graph" under modules
3. Click on "Graph" to access the graph query interface

### Step 3: Select Your Graph
In the query interface, you'll need to specify which graph to query:
- **Graph Name**: `graphiti_migration` (contains your migrated data)

## Example Queries

### Basic Queries
```cypher
# Count all nodes
GRAPH.QUERY graphiti_migration "MATCH (n) RETURN count(n)"

# Get first 10 nodes with names
GRAPH.QUERY graphiti_migration "MATCH (n) WHERE n.name IS NOT NULL RETURN n.name, labels(n) LIMIT 10"

# Show all node types
GRAPH.QUERY graphiti_migration "MATCH (n) RETURN DISTINCT labels(n)"

# Count relationships
GRAPH.QUERY graphiti_migration "MATCH ()-[r]->() RETURN count(r)"
```

### More Complex Queries
```cypher
# Find all Entity nodes
GRAPH.QUERY graphiti_migration "MATCH (n:Entity) RETURN n.name, n.type LIMIT 20"

# Find all Episodic nodes
GRAPH.QUERY graphiti_migration "MATCH (n:Episodic) RETURN n.name, n.created_at LIMIT 20"

# Show relationships between entities
GRAPH.QUERY graphiti_migration "MATCH (a:Entity)-[r]->(b:Entity) RETURN a.name, type(r), b.name LIMIT 20"

# Find nodes by name pattern
GRAPH.QUERY graphiti_migration "MATCH (n) WHERE n.name CONTAINS 'Done' RETURN n"
```

## Features in RedisInsight

### Graph Visualization
- Query results can be viewed as:
  - **Graph View**: Visual representation of nodes and relationships
  - **Table View**: Tabular format for data analysis
  - **JSON View**: Raw JSON response

### Query Builder
- Syntax highlighting for Cypher queries
- Auto-completion support
- Query history
- Save frequently used queries

### Performance Monitoring
- Query execution time
- Memory usage
- Result set size

## Troubleshooting

### Connection Issues
If you can't connect to FalkorDB:
1. Ensure you're using `falkordb` as the host, not `localhost`
2. Verify FalkorDB is running: `docker ps | grep falkordb`
3. Check they're on the same network: `docker network inspect graphiti_graphiti_network`

### No Data Visible
If you don't see your migrated data:
1. Make sure to specify the correct graph name: `graphiti_migration`
2. Run the migration script again if needed: `python3 migrate_working.py`

## Current Data Status
- **Migrated Nodes**: 500
- **Migrated Relationships**: 27
- **Graph Name**: `graphiti_migration`

## Additional Resources
- [RedisInsight Documentation](https://redis.io/docs/latest/operate/redisinsight/)
- [FalkorDB Documentation](https://docs.falkordb.com/)
- [Cypher Query Language](https://neo4j.com/docs/cypher-manual/current/)