# CocoIndex Integration with Graphiti FalkorDB

## Overview

This document provides the complete specifications for integrating CocoIndex with Graphiti's FalkorDB setup, enabling seamless BookStack content ingestion into the knowledge graph via Cypher queries.

## FalkorDB Connection Configuration

### Connection Details
```yaml
host: falkordb                    # Docker service name
port: 6379                       # Redis protocol port
database: graphiti_migration     # Primary graph name
protocol: redis                  # FalkorDB uses Redis protocol
authentication: none             # No auth configured
connection_string: redis://falkordb:6379
```

### Alternative Configurations
```yaml
# Local development
host: localhost
port: 6379

# External access
host: 192.168.50.80
port: 6379
```

## Schema Definitions

### Node Labels and Properties

#### Entity Nodes (Topics/Concepts)
```cypher
Label: Entity
Required Properties:
  - uuid: string              # Unique identifier
  - name: string              # Entity/topic name
  - group_id: string          # Partition identifier
  - created_at: datetime      # Creation timestamp
  - labels: array[string]     # Entity type labels
Optional Properties:
  - summary: string           # Entity description
  - name_embedding: array[float]  # Name embedding vector (2560 dims)
  - attributes: dict          # Custom metadata
```

#### Episodic Nodes (Documents/Content)
```cypher
Label: Episodic
Required Properties:
  - uuid: string              # Unique identifier
  - name: string              # Document title
  - group_id: string          # Partition identifier
  - created_at: datetime      # Creation timestamp
  - content: string           # Raw document content
  - source: enum              # 'text', 'json', 'message'
  - source_description: string # Source information
  - valid_at: datetime        # Document creation date
Optional Properties:
  - summary: string           # Document summary
  - name_embedding: array[float]  # Title embedding vector
  - entity_edges: array[string]   # Referenced entity UUIDs
```

#### Community Nodes (Entity Clusters)
```cypher
Label: Community
Required Properties:
  - uuid: string              # Unique identifier
  - name: string              # Community name
  - group_id: string          # Partition identifier
  - created_at: datetime      # Creation timestamp
Optional Properties:
  - summary: string           # Community description
  - centrality_metrics: dict  # PageRank, betweenness, etc.
```

### Edge Labels and Properties

#### Entity-Entity Relationships
```cypher
Label: RELATES_TO
Required Properties:
  - uuid: string              # Unique identifier
  - name: string              # Relationship type/name
  - fact: string              # Relationship description
  - group_id: string          # Partition identifier
  - created_at: datetime      # Creation timestamp
Optional Properties:
  - fact_embedding: array[float]  # Fact embedding vector (2560 dims)
  - episodes: array[string]       # Source episode UUIDs
  - valid_at: datetime            # When relationship became true
  - invalid_at: datetime          # When relationship ended
  - expired_at: datetime          # When relationship was invalidated
```

#### Episode-Entity References
```cypher
Label: MENTIONS
Required Properties:
  - uuid: string              # Unique identifier
  - group_id: string          # Partition identifier
  - created_at: datetime      # Creation timestamp
```

#### Community Membership
```cypher
Label: HAS_MEMBER
Required Properties:
  - uuid: string              # Unique identifier
  - group_id: string          # Partition identifier
  - created_at: datetime      # Creation timestamp
```

## Embedding Configuration

### Model Specifications
```yaml
model_name: dengcao/Qwen3-Embedding-4B:Q4_K_M
dimension: 2560
base_url: http://192.168.50.80:11434/v1  # Ollama endpoint
api_key: ollama                          # Default API key
```

### Property Names
```yaml
node_embeddings: name_embedding          # For node name/title embeddings
edge_embeddings: fact_embedding          # For relationship fact embeddings
```

### Alternative Models
```yaml
# Other supported models with dimensions
mxbai-embed-large: 1024
nomic-embed-text: 768
text-embedding-3-small: 1536
text-embedding-3-large: 3072
```

## Database Constraints and Merge Keys

### Unique Constraints
```cypher
-- Node UUID uniqueness
GRAPH.CONSTRAINT CREATE {graph_key} UNIQUE NODE Entity PROPERTIES 1 uuid
GRAPH.CONSTRAINT CREATE {graph_key} UNIQUE NODE Episodic PROPERTIES 1 uuid
GRAPH.CONSTRAINT CREATE {graph_key} UNIQUE NODE Community PROPERTIES 1 uuid

-- Entity name+group_id uniqueness (for deduplication)
GRAPH.CONSTRAINT CREATE {graph_key} UNIQUE NODE Entity PROPERTIES 2 name group_id

-- Community membership uniqueness
GRAPH.CONSTRAINT CREATE {graph_key} UNIQUE RELATIONSHIP HAS_MEMBER PROPERTIES 1 uuid
```

### Merge Strategies
```cypher
-- Documents/Episodes: Always merge on UUID
MERGE (d:Episodic {uuid: $uuid})

-- Entities/Topics: Merge on name+group_id for deduplication
MERGE (e:Entity {name: $name, group_id: $group_id})

-- Relationships: Merge on UUID when available
MERGE (s)-[r:RELATES_TO {uuid: $uuid}]->(t)

-- Mentions: Create new (no unique constraint due to legitimate duplicates)
CREATE (d)-[m:MENTIONS {uuid: $uuid, group_id: $group_id, created_at: $timestamp}]->(e)
```

## BookStack Integration Mapping

### JSON Field Mapping
```json
{
  "bookstack_field": "graphiti_property",
  "id": "external_id",
  "title": "name",
  "slug": "metadata.slug",
  "url": "source_description",
  "updated_at": "valid_at",
  "body_html": "content",
  "tags": "extract_entities",
  "book": "group_id",
  "chapter": "metadata.chapter"
}
```

### Suggested BookStack Export Fields
```json
{
  "id": "page_id",
  "title": "page_title", 
  "slug": "page_slug",
  "url": "page_url",
  "updated_at": "2024-01-15T10:30:00Z",
  "body_html": "<p>Page content...</p>",
  "tags": ["tag1", "tag2"],
  "book": "book_name",
  "chapter": "chapter_name"
}
```

## CocoIndex Cypher Operations

### Document Creation
```cypher
// Create document node
MERGE (d:Episodic {uuid: $doc_uuid})
SET d.name = $title,
    d.content = $html_to_text_content,
    d.group_id = $book_name,
    d.created_at = datetime(),
    d.valid_at = datetime($updated_at),
    d.source = 'text',
    d.source_description = $url,
    d.name_embedding = $title_embedding
```

### Entity Extraction and Linking
```cypher
// Create/merge entity
MERGE (e:Entity {name: $entity_name, group_id: $group_id})
ON CREATE SET 
    e.uuid = $entity_uuid,
    e.created_at = datetime(),
    e.labels = ['Entity'],
    e.name_embedding = $entity_embedding

// Link document to entity
MATCH (d:Episodic {uuid: $doc_uuid})
MATCH (e:Entity {name: $entity_name, group_id: $group_id})
CREATE (d)-[m:MENTIONS {
    uuid: $mention_uuid,
    group_id: $group_id,
    created_at: datetime()
}]->(e)
```

### Relationship Creation
```cypher
// Create entity-entity relationship
MATCH (s:Entity {name: $source_entity, group_id: $group_id})
MATCH (t:Entity {name: $target_entity, group_id: $group_id})
MERGE (s)-[r:RELATES_TO {
    uuid: $relation_uuid,
    name: $relation_type,
    fact: $relation_description,
    group_id: $group_id,
    created_at: datetime(),
    fact_embedding: $fact_embedding,
    episodes: [$doc_uuid]
}]->(t)
```

## Edge Type Map Configuration

### Standard Edge Types
```python
edge_type_map = {
    ('Entity', 'Entity'): ['RELATES_TO'],
    ('Episodic', 'Entity'): ['MENTIONS'],
    ('Community', 'Entity'): ['HAS_MEMBER']
}
```

### Custom Relationship Types
```python
# Can be extended with domain-specific relationships
custom_edge_types = {
    ('Entity', 'Entity'): [
        'RELATES_TO',
        'PART_OF', 
        'SIMILAR_TO',
        'DEPENDS_ON',
        'CONTAINS'
    ]
}
```

## Implementation Notes

### Critical Requirements
1. **Group ID Consistency**: All nodes and edges must have consistent `group_id` values for proper partitioning
2. **UUID Generation**: Use deterministic UUIDs for entities based on `(name, group_id)` for deduplication
3. **Embedding Alignment**: Ensure embedding model and dimensions match Graphiti configuration (2560 for Qwen3-Embedding-4B)
4. **Temporal Fields**: Use ISO 8601 datetime format for all temporal properties

### Performance Considerations
1. **Batch Operations**: Use bulk MERGE operations for better performance
2. **Index Usage**: Leverage existing indexes on uuid, name, and group_id
3. **Embedding Storage**: Consider storing embeddings as separate operations if they're large

### Error Handling
1. **Constraint Violations**: Handle unique constraint violations gracefully
2. **Missing Embeddings**: Allow operations to proceed without embeddings if embedding service is unavailable
3. **Invalid Dates**: Validate and sanitize datetime fields before insertion

This configuration ensures full compatibility with Graphiti's existing schema while enabling efficient BookStack content ingestion through CocoIndex.
