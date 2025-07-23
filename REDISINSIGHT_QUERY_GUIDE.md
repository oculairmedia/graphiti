# 🎯 Step-by-Step Guide to Query FalkorDB in RedisInsight

## Step 1: Open RedisInsight
Go to: http://192.168.50.90:5540

## Step 2: Click on Your Database
You'll see "FalkorDB Graph Database" in the list - **click on it**

## Step 3: Choose Where to Query
Once you're in the database, you have two options in the left sidebar:

### Option A: CLI (Command Line Interface) ✅ RECOMMENDED
1. Click on **"CLI"** in the left sidebar
2. You'll see a command prompt at the bottom
3. Type your GRAPH.QUERY commands here

### Option B: Workbench
1. Click on **"Workbench"** in the left sidebar
2. Type commands in the editor
3. Click "Run" or press Ctrl+Enter

## Step 4: Run Graph Queries

### In the CLI, type exactly:
```
GRAPH.QUERY graphiti_migration "MATCH (n) RETURN count(n)"
```

### Or try these queries:

**Count all nodes:**
```
GRAPH.QUERY graphiti_migration "MATCH (n) RETURN count(n)"
```

**Get first 10 nodes:**
```
GRAPH.QUERY graphiti_migration "MATCH (n) RETURN n.name, labels(n) LIMIT 10"
```

**Find nodes with highest PageRank:**
```
GRAPH.QUERY graphiti_migration "MATCH (n) WHERE n.pagerank_centrality IS NOT NULL RETURN n.name, n.pagerank_centrality ORDER BY n.pagerank_centrality DESC LIMIT 10"
```

**Search for error-related nodes:**
```
GRAPH.QUERY graphiti_migration "MATCH (n) WHERE n.name CONTAINS 'error' RETURN n.name, labels(n) LIMIT 20"
```

## Important Notes:
- ❗ You do NOT need to click on "Graph" in the sidebar (that's for the old RedisGraph format)
- ✅ Use CLI or Workbench for FalkorDB queries
- 📝 Always start queries with: `GRAPH.QUERY graphiti_migration "..."`
- 🔍 The graph name is `graphiti_migration`

## Visual Guide:
```
RedisInsight Home
  └─> Click "FalkorDB Graph Database"
      └─> Click "CLI" (left sidebar)
          └─> Type: GRAPH.QUERY graphiti_migration "MATCH (n) RETURN count(n)"
              └─> Press Enter
```

## Troubleshooting:
- If you don't see results, make sure you included `GRAPH.QUERY graphiti_migration` before your Cypher query
- The quotes around the Cypher query are required
- Case matters - use GRAPH.QUERY in uppercase