# Graphiti Embedding Storage Specification

## Overview
This document outlines how embeddings are stored on nodes and edges in the Graphiti knowledge graph platform. Graphiti uses vector embeddings to enable semantic search, similarity matching, and enhanced retrieval capabilities across entities and relationships.

## Embedding Storage Architecture

### Database Support
- **Neo4j**: Primary persistent storage (stores embeddings as regular arrays)
- **FalkorDB**: In-memory cache layer (uses `vecf32()` vector type for optimized operations)

### Embedding Models
- **Default Model**: `dengcao/Qwen3-Embedding-4B:Q4_K_M`
- **Default Dimension**: 2560
- **Alternative Models**: `mxbai-embed-large` (1024), `nomic-embed-text` (768), `text-embedding-3-small` (1536), `text-embedding-3-large` (3072)

## Node Embedding Storage

### EntityNode Embeddings

#### Property Definition
```python
class EntityNode(Node):
    name_embedding: list[float] | None = Field(default=None, description='embedding of the name')
    # ... other fields
```

#### Storage Details
- **Property Name**: `name_embedding`
- **Source Text**: `name` field (entity name/title)
- **Data Type**: `list[float] | None`
- **Dimension**: 2560 (default) or model-specific
- **Purpose**: Semantic search across entity names, similarity matching, deduplication

#### Database Storage Format

**FalkorDB (Cache Layer)**:
```cypher
-- Storage with vector type casting
SET n.name_embedding = vecf32($entity_data.name_embedding)

-- Query example
MATCH (n:Entity) 
WHERE vec.cosineDistance(n.name_embedding, vecf32($query_vector)) < 0.5
RETURN n
```

**Neo4j (Persistent Storage)**:
```cypher
-- Storage as regular array
SET n.name_embedding = $entity_data.name_embedding

-- Query example (no vecf32 function)
MATCH (n:Entity) 
WHERE n.name_embedding IS NOT NULL
RETURN n
```

### EpisodicNode Embeddings

#### Property Definition
```python
class EpisodicNode(Node):
    # Standard fields: uuid, name, group_id, created_at, content, source, etc.
    # Note: name_embedding may be added for episodic content titles
```

#### Storage Details
- **Property Name**: `name_embedding` (for episode titles)
- **Additional Property**: `content_embedding` (for episode content - custom implementation)
- **Source Text**: `name` field (episode title) or `content` field
- **Data Type**: `list[float] | None`
- **Purpose**: Semantic search across episode titles and content

#### Database Storage
```cypher
-- FalkorDB storage for episodic content embeddings
MATCH (n:Episodic {uuid: $uuid})
SET n.content_embedding = vecf32($embedding)
```

### CommunityNode Embeddings

#### Property Definition
```python
class CommunityNode(Node):
    name_embedding: list[float] | None = Field(default=None)
    # ... other fields
```

#### Storage Details
- **Property Name**: `name_embedding`
- **Source Text**: `name` field (community name)
- **Purpose**: Semantic search across community clusters

## Edge Embedding Storage

### EntityEdge Embeddings

#### Property Definition
```python
class EntityEdge(Edge):
    name: str = Field(description='name of the edge, relation name')
    fact: str = Field(description='fact representing the edge and nodes that it connects')
    fact_embedding: list[float] | None = Field(default=None, description='embedding of the fact')
    # ... other fields
```

#### Storage Details
- **Property Name**: `fact_embedding`
- **Source Text**: `fact` field (relationship description)
- **Data Type**: `list[float] | None`
- **Dimension**: 2560 (default) or model-specific
- **Purpose**: Semantic search across relationships, similarity matching between facts, deduplication

#### Database Storage Format

**FalkorDB (Cache Layer)**:
```cypher
-- Storage with vector type casting
SET r.fact_embedding = vecf32($edge_data.fact_embedding)

-- Bulk storage
UNWIND $entity_edges AS edge
MATCH (source:Entity {uuid: edge.source_node_uuid}) 
MATCH (target:Entity {uuid: edge.target_node_uuid}) 
MERGE (source)-[r:RELATES_TO {uuid: edge.uuid, group_id: edge.group_id}]->(target)
SET r = edge
SET r.fact_embedding = vecf32(edge.fact_embedding)
```

**Neo4j (Persistent Storage)**:
```cypher
-- Storage as regular array
SET r.fact_embedding = $edge_data.fact_embedding
```

### EpisodicEdge Embeddings

#### Property Definition
```python
class EpisodicEdge(Edge):
    # Standard fields: uuid, source_node_uuid, target_node_uuid, created_at, group_id
    # Note: No embeddings typically stored on episodic edges (MENTIONS relationships)
```

#### Storage Details
- **Embedding Storage**: Not typically used
- **Relationship Type**: `MENTIONS` (Episode → Entity)
- **Purpose**: Links episodes to mentioned entities without semantic embedding

## Embedding Generation and Management

### Generation Methods

#### Node Embedding Generation
```python
async def create_entity_node_embeddings(embedder: EmbedderClient, nodes: list[EntityNode]):
    if not nodes:
        return
    name_embeddings = await embedder.create_batch([node.name for node in nodes])
    for node, name_embedding in zip(nodes, name_embeddings, strict=True):
        node.name_embedding = name_embedding
```

#### Edge Embedding Generation
```python
async def generate_embedding(self, embedder: EmbedderClient):
    text = self.fact.replace('\n', ' ')
    self.fact_embedding = await embedder.create(input_data=[text])
    return self.fact_embedding
```

### Batch Processing
- **Node Embeddings**: Generated in batches using `embedder.create_batch()`
- **Edge Embeddings**: Generated individually or in batches
- **Regeneration Scripts**: Available for bulk embedding updates (`regenerate_*_embeddings_ollama.py`)

## Vector Operations and Indexing

### FalkorDB Vector Functions
- **`vecf32(array)`**: Converts array to float32 vector type
- **`vec.cosineDistance(vector1, vector2)`**: Cosine distance calculation
- **`vec.euclideanDistance(vector1, vector2)`**: Euclidean distance calculation

### Vector Indexing
```cypher
-- Create vector index (FalkorDB)
CREATE VECTOR INDEX FOR (n:Entity) ON n.name_embedding OPTIONS {dimension: 2560}

-- Drop vector index
DROP VECTOR INDEX FOR (n:Entity) ON n.name_embedding
```

### Search Integration
- **Similarity Search**: Uses cosine distance for semantic similarity
- **Hybrid Search**: Combines embeddings with BM25 keyword search and graph traversal
- **Search Services**: Rust-based search services (`graphiti-search-rs`) for high-performance queries

## Configuration and Environment

### Environment Variables
```bash
EMBEDDING_DIMENSION=2560                    # Vector dimension
EMBEDDING_MODEL=dengcao/Qwen3-Embedding-4B:Q4_K_M
OLLAMA_BASE_URL=http://192.168.50.80:11434/v1
```

### Model Configuration
```python
class EmbedderConfig(BaseModel):
    embedding_dim: int = Field(default=2560, frozen=True)
    model: str = "dengcao/Qwen3-Embedding-4B:Q4_K_M"
    base_url: str = "http://192.168.50.80:11434/v1"
```

## Data Synchronization and Persistence

### Sync Service Considerations
- **Forward Sync** (Neo4j → FalkorDB): Must use `vecf32()` casting for proper vector storage
- **Reverse Sync** (FalkorDB → Neo4j): Stores embeddings as regular arrays
- **Migration Scripts**: Handle embedding preservation during database migrations
- **Disaster Recovery**: May skip embeddings by design; requires regeneration

### Best Practices
1. **Persist embeddings in Neo4j** (system of record) for disaster recovery
2. **Use parameterized queries** instead of string concatenation for arrays
3. **Cast embeddings to vector types** using `vecf32()` in FalkorDB
4. **Validate embedding dimensions** match model specifications
5. **Create vector indexes** for optimal similarity search performance

## Troubleshooting

### Common Issues
1. **Dimension Mismatches**: Ensure `EMBEDDING_DIMENSION` matches model output
2. **Type Mismatches**: Use `vecf32()` casting in FalkorDB queries
3. **Missing Embeddings**: Run regeneration scripts after data migration
4. **Sync Failures**: Verify embedding properties are properly handled in sync services

### Validation Queries
```cypher
-- Check embedding presence and dimensions
MATCH (n:Entity) 
WHERE n.name_embedding IS NOT NULL 
RETURN count(n), size(n.name_embedding[0..1]) as sample_dims

-- Check edge embeddings
MATCH ()-[r:RELATES_TO]->() 
WHERE r.fact_embedding IS NOT NULL 
RETURN count(r), size(r.fact_embedding[0..1]) as sample_dims
```
