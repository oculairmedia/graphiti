# ✅ RedisInsight is Configured!

## Access RedisInsight
🌐 **URL**: http://192.168.50.90:5540

## Connection Status
✅ **FalkorDB is already connected** with the following details:
- **Name**: FalkorDB Graph Database  
- **Host**: falkordb
- **Port**: 6379
- **Graph Module**: v4.10.3 (detected automatically)

## How to Query Your Data

### 1. Open RedisInsight
Navigate to http://192.168.50.90:5540 in your browser

### 2. Select the Database
Click on "FalkorDB Graph Database" from the database list

### 3. Use the CLI or Workbench
You have two options:

#### Option A: CLI (Command Line Interface)
1. Click on "CLI" in the left sidebar
2. Enter graph queries directly:
```
GRAPH.QUERY graphiti_migration "MATCH (n) RETURN count(n)"
```

#### Option B: Workbench
1. Click on "Workbench" in the left sidebar
2. Type your commands and press Run

## Example Queries to Try

### Count all nodes
```
GRAPH.QUERY graphiti_migration "MATCH (n) RETURN count(n)"
```

### Get first 10 nodes
```
GRAPH.QUERY graphiti_migration "MATCH (n) RETURN n LIMIT 10"
```

### Find Entity nodes
```
GRAPH.QUERY graphiti_migration "MATCH (n:Entity) RETURN n.name, n.type LIMIT 20"
```

### Show relationships
```
GRAPH.QUERY graphiti_migration "MATCH (a)-[r]->(b) RETURN a.name, type(r), b.name LIMIT 20"
```

### Search by name
```
GRAPH.QUERY graphiti_migration "MATCH (n) WHERE n.name CONTAINS 'Done' RETURN n"
```

## Visual Graph Explorer
Unfortunately, the Graph visualization in RedisInsight requires the older RedisGraph module format. Since FalkorDB uses a newer format, you'll need to use the CLI or Workbench for queries.

## Your Data Status
- **Graph Name**: `graphiti_migration`
- **Total Nodes**: 500
- **Total Relationships**: 27

## Tips
1. Results are displayed in a table format in the Workbench
2. You can export results as CSV or JSON
3. Query history is saved automatically
4. Use Ctrl+Enter to run queries in Workbench

---
🎉 **You're all set!** RedisInsight is configured and ready to explore your FalkorDB graph data.