# 📊 Interactive Graph Visualization in RedisInsight

## How to Visualize Your Graph Data

### Step 1: Open RedisInsight
Navigate to: http://192.168.50.90:5540

### Step 2: Connect to FalkorDB
Click on "FalkorDB Graph Database" from the database list

### Step 3: Use the Workbench for Graph Queries

1. Click on **"Workbench"** in the left sidebar
2. Enter your graph query with the GRAPH.QUERY command

### Step 4: Run Graph Queries that Return Nodes and Relationships

Here are queries optimized for visualization:

#### 🔍 Visualize a Small Subset (Recommended to Start)
```
GRAPH.QUERY graphiti_migration "MATCH (n)-[r]-(m) RETURN n, r, m LIMIT 50"
```

#### 🎯 Visualize High PageRank Nodes and Their Connections
```
GRAPH.QUERY graphiti_migration "MATCH (n) WHERE n.pagerank_centrality > 0.001 WITH n ORDER BY n.pagerank_centrality DESC LIMIT 20 MATCH (n)-[r]-(m) RETURN n, r, m"
```

#### 🔗 Visualize Specific Entity Types
```
GRAPH.QUERY graphiti_migration "MATCH (n:Entity)-[r]-(m:Entity) WHERE n.type = 'task' OR m.type = 'task' RETURN n, r, m LIMIT 100"
```

#### 🌐 Explore Neighborhood of a Specific Node
```
GRAPH.QUERY graphiti_migration "MATCH (n) WHERE n.name CONTAINS 'data' WITH n LIMIT 1 MATCH (n)-[r*1..2]-(m) RETURN n, r, m LIMIT 50"
```

#### 📈 Visualize Episodic Connections
```
GRAPH.QUERY graphiti_migration "MATCH (e:Episodic)-[r]-(n) RETURN e, r, n LIMIT 100"
```

### Step 5: View Results

RedisInsight will display results in different formats:
- **Table View**: Shows raw data
- **JSON View**: Shows structured data
- **Graph View**: If the query returns nodes and relationships, you may see visualization options

### Important Tips for Better Visualization:

1. **Start Small**: Begin with LIMIT 50 or 100 to avoid overwhelming the visualization
2. **Return Full Patterns**: Always return nodes AND relationships (n, r, m) for proper visualization
3. **Use Filters**: Filter by properties to get meaningful subgraphs

### Example: Finding Connected Components

```
# Find clusters of highly connected entities
GRAPH.QUERY graphiti_migration "MATCH (n:Entity) WHERE n.degree_centrality > 5 WITH n LIMIT 30 MATCH (n)-[r]-(m:Entity) WHERE m.degree_centrality > 3 RETURN n, r, m"
```

### If Graph Visualization Isn't Available:

RedisInsight's graph visualization depends on the query results format. If you don't see a graph view:

1. **Alternative Tool - RedisGraph Visualizer**:
   - You can export query results as JSON
   - Use external tools like Gephi or Cytoscape
   - Or use online graph visualizers

2. **Export Data for Visualization**:
   ```
   GRAPH.QUERY graphiti_migration "MATCH (n)-[r]-(m) RETURN n.uuid as source, m.uuid as target, type(r) as relationship, n.name as source_name, m.name as target_name LIMIT 1000"
   ```
   Export this as CSV and import into any graph visualization tool.

### Your Graph Statistics:
- **Total Nodes**: 4,437
- **Total Relationships**: 13,849
- **Node Types**: Entity (1,239) and Episodic (3,198)

Start with smaller subsets for interactive exploration, then expand as needed!