# Node-Based Memory Systems
## Graph-Structured Memory with Decay Algorithms for LLMs

## 1. Introduction

Node-based memory systems represent knowledge as interconnected graphs rather than linear sequences, mirroring biological neural networks and enabling more sophisticated memory operations. This document explores how to implement decay algorithms, spaced repetition, and consolidation in graph-structured memory architectures.

## 2. Theoretical Foundation

### 2.1 Biological Inspiration

**Hippocampal Cognitive Maps**
The hippocampus creates cognitive maps using specialized cells:
- **Place Cells**: Fire when an organism is in specific locations
- **Grid Cells**: Provide coordinate system for spatial navigation
- **Time Cells**: Encode temporal relationships
- **Object Cells**: Respond to specific entities

These biological structures inspire graph memory architectures where:
- Nodes represent discrete memory units (places, concepts, facts)
- Edges encode relationships with temporal and spatial properties
- Communities form semantic clusters
- Hierarchies emerge from connection patterns

### 2.2 Graph Memory Advantages

**Structural Benefits**
1. **Relational Reasoning**: Natural representation of relationships
2. **Multi-hop Inference**: Traverse connections for complex queries
3. **Semantic Clustering**: Communities represent related concepts
4. **Hierarchical Organization**: Multiple abstraction levels
5. **Parallel Processing**: Independent decay of subgraphs

**Computational Benefits**
- Sparse representations reduce memory footprint
- Local updates without global recomputation
- Efficient similarity search through graph proximity
- Natural integration with GNNs and transformers

## 3. Node-Based Memory Architecture

### 3.1 Core Components

```python
class MemoryNode:
    """
    Individual memory unit in the graph
    """
    def __init__(self, node_id: str, content: Any, node_type: str):
        # Identity
        self.id = node_id
        self.type = node_type  # 'entity', 'fact', 'episode', 'concept'
        
        # Content
        self.content = content
        self.embedding = None  # Vector representation
        
        # FSRS-inspired parameters
        self.stability = 1.0  # Memory strength
        self.difficulty = 5.0  # Inherent difficulty
        self.retrievability = 1.0  # Current recall probability
        
        # Temporal metadata
        self.created_at = datetime.now()
        self.last_accessed = datetime.now()
        self.access_count = 0
        
        # Graph properties
        self.importance = 0.5  # PageRank-style importance
        self.community_id = None  # Cluster membership
        self.depth = 0  # Hierarchy level

class MemoryEdge:
    """
    Relationship between memory nodes
    """
    def __init__(self, source: str, target: str, edge_type: str):
        # Identity
        self.source = source
        self.target = target
        self.type = edge_type  # 'semantic', 'temporal', 'causal', 'hierarchical'
        
        # Relationship strength
        self.weight = 1.0  # Connection strength
        self.confidence = 1.0  # Certainty of relationship
        
        # Temporal properties
        self.created_at = datetime.now()
        self.last_activated = datetime.now()
        self.activation_count = 0
        
        # Decay parameters
        self.decay_rate = 0.1  # Edge-specific decay
        self.reinforcement_factor = 1.5
```

### 3.2 Graph Structure

```python
class GraphMemory:
    """
    Complete graph-based memory system
    """
    def __init__(self):
        self.nodes = {}  # node_id -> MemoryNode
        self.edges = {}  # (source, target) -> MemoryEdge
        self.adjacency = defaultdict(set)  # node -> connected nodes
        
        # Graph indices
        self.type_index = defaultdict(set)  # type -> node_ids
        self.community_index = defaultdict(set)  # community -> node_ids
        self.temporal_index = SortedDict()  # timestamp -> node_ids
        
        # Embeddings
        self.node_embeddings = None  # Matrix of node vectors
        self.edge_embeddings = None  # Matrix of edge vectors
```

## 4. Decay Algorithms for Graphs

### 4.1 Node-Level Decay

```python
class GraphDecayAlgorithm:
    """
    FSRS-inspired decay for graph memories
    """
    
    def calculate_node_decay(self, node: MemoryNode, graph: GraphMemory) -> float:
        """
        Calculate decay considering graph structure
        """
        # Base FSRS decay
        time_elapsed = (datetime.now() - node.last_accessed).days
        base_retrievability = (1 + time_elapsed / (9 * node.stability)) ** (-1)
        
        # Graph-based modifiers
        importance_factor = self.calculate_importance_factor(node, graph)
        connectivity_factor = self.calculate_connectivity_factor(node, graph)
        community_factor = self.calculate_community_factor(node, graph)
        
        # Combined decay
        retrievability = (
            base_retrievability * 
            (0.4 * importance_factor +
             0.3 * connectivity_factor +
             0.3 * community_factor)
        )
        
        return retrievability
    
    def calculate_importance_factor(self, node: MemoryNode, graph: GraphMemory) -> float:
        """
        PageRank-inspired importance scoring
        """
        # Simplified PageRank
        damping = 0.85
        in_edges = self.get_incoming_edges(node, graph)
        
        importance = (1 - damping) + damping * sum(
            edge.weight * graph.nodes[edge.source].importance / 
            len(graph.adjacency[edge.source])
            for edge in in_edges
        )
        
        return min(importance, 2.0)  # Cap at 2x modifier
    
    def calculate_connectivity_factor(self, node: MemoryNode, graph: GraphMemory) -> float:
        """
        Well-connected nodes decay slower
        """
        degree = len(graph.adjacency[node.id])
        avg_degree = sum(len(adj) for adj in graph.adjacency.values()) / len(graph.nodes)
        
        # Normalize connectivity
        return 1 + 0.5 * math.tanh((degree - avg_degree) / avg_degree)
    
    def calculate_community_factor(self, node: MemoryNode, graph: GraphMemory) -> float:
        """
        Nodes in active communities decay slower
        """
        if not node.community_id:
            return 1.0
        
        community_nodes = graph.community_index[node.community_id]
        
        # Average recent access in community
        recent_accesses = sum(
            1 for n_id in community_nodes
            if (datetime.now() - graph.nodes[n_id].last_accessed).days < 7
        )
        
        activity_ratio = recent_accesses / len(community_nodes)
        return 1 + 0.3 * activity_ratio
```

### 4.2 Edge Decay

```python
class EdgeDecay:
    """
    Decay for relationships between nodes
    """
    
    def calculate_edge_decay(self, edge: MemoryEdge, graph: GraphMemory) -> float:
        """
        Edge strength decay based on usage and node states
        """
        # Time-based decay
        time_elapsed = (datetime.now() - edge.last_activated).days
        base_decay = math.exp(-time_elapsed * edge.decay_rate)
        
        # Node state influence
        source_retrievability = graph.nodes[edge.source].retrievability
        target_retrievability = graph.nodes[edge.target].retrievability
        node_factor = (source_retrievability + target_retrievability) / 2
        
        # Edge type modifier
        type_modifiers = {
            'semantic': 0.9,  # Semantic relationships decay slowly
            'temporal': 0.7,  # Temporal relationships decay moderately
            'causal': 0.95,  # Causal relationships are stable
            'hierarchical': 1.0  # Hierarchical relationships don't decay
        }
        type_factor = type_modifiers.get(edge.type, 0.8)
        
        # Combined edge strength
        edge.weight = base_decay * node_factor * type_factor * edge.confidence
        
        return edge.weight
```

### 4.3 Spreading Activation

```python
class SpreadingActivation:
    """
    Propagate activation through graph for retrieval
    """
    
    def activate(self, start_nodes: List[str], graph: GraphMemory, 
                 max_iterations: int = 5) -> Dict[str, float]:
        """
        Spread activation from starting nodes
        """
        activation = defaultdict(float)
        
        # Initialize starting nodes
        for node_id in start_nodes:
            activation[node_id] = 1.0
        
        # Iterative spreading
        for iteration in range(max_iterations):
            new_activation = defaultdict(float)
            
            for node_id, current_activation in activation.items():
                # Spread to neighbors
                for neighbor_id in graph.adjacency[node_id]:
                    edge = graph.edges[(node_id, neighbor_id)]
                    
                    # Activation spreads proportional to edge weight
                    spread = current_activation * edge.weight * 0.5
                    new_activation[neighbor_id] += spread
            
            # Decay and update
            for node_id in new_activation:
                activation[node_id] = activation[node_id] * 0.7 + new_activation[node_id]
        
        return activation
```

## 5. Graph-Specific Memory Operations

### 5.1 Community-Based Consolidation

```python
class CommunityConsolidation:
    """
    Consolidate memories within semantic communities
    """
    
    def detect_communities(self, graph: GraphMemory) -> Dict[str, int]:
        """
        Louvain community detection
        """
        import networkx as nx
        from community import community_louvain
        
        # Convert to NetworkX graph
        G = nx.Graph()
        for node_id in graph.nodes:
            G.add_node(node_id)
        for (source, target), edge in graph.edges.items():
            G.add_edge(source, target, weight=edge.weight)
        
        # Detect communities
        communities = community_louvain.best_partition(G)
        
        # Update node community assignments
        for node_id, community_id in communities.items():
            graph.nodes[node_id].community_id = community_id
            graph.community_index[community_id].add(node_id)
        
        return communities
    
    def consolidate_community(self, community_id: int, graph: GraphMemory) -> MemoryNode:
        """
        Create summary node for community
        """
        community_nodes = [graph.nodes[n_id] for n_id in graph.community_index[community_id]]
        
        # Generate summary content
        summary_content = self.generate_summary(community_nodes)
        
        # Create summary node
        summary_node = MemoryNode(
            node_id=f"summary_{community_id}",
            content=summary_content,
            node_type='summary'
        )
        
        # Inherit stability from strongest node
        summary_node.stability = max(n.stability for n in community_nodes)
        
        # Connect to community members
        for node in community_nodes:
            graph.add_edge(summary_node.id, node.id, edge_type='hierarchical')
        
        return summary_node
```

### 5.2 Hierarchical Memory Organization

```python
class HierarchicalMemory:
    """
    Multi-level memory hierarchy
    """
    
    def build_hierarchy(self, graph: GraphMemory) -> None:
        """
        Construct hierarchical levels
        """
        # Level 0: Raw memories
        level_0 = [n for n in graph.nodes.values() if n.type in ['entity', 'fact']]
        
        # Level 1: Episode summaries
        level_1 = self.create_episode_summaries(level_0, graph)
        
        # Level 2: Concept abstractions
        level_2 = self.create_concept_abstractions(level_1, graph)
        
        # Level 3: Meta-knowledge
        level_3 = self.create_meta_knowledge(level_2, graph)
        
        # Assign depth levels
        for node in level_0:
            node.depth = 0
        for node in level_1:
            node.depth = 1
        for node in level_2:
            node.depth = 2
        for node in level_3:
            node.depth = 3
    
    def hierarchical_decay(self, node: MemoryNode) -> float:
        """
        Decay rate based on hierarchy level
        """
        depth_modifiers = {
            0: 1.0,   # Raw memories decay normally
            1: 0.7,   # Episodes decay slower
            2: 0.4,   # Concepts decay much slower
            3: 0.1    # Meta-knowledge barely decays
        }
        
        return depth_modifiers.get(node.depth, 1.0)
```

## 6. Integration with Modern Frameworks

### 6.1 GraphRAG Integration

```python
class GraphRAGMemory:
    """
    Integration with Microsoft GraphRAG
    """
    
    def __init__(self):
        self.graph_memory = GraphMemory()
        self.decay_algorithm = GraphDecayAlgorithm()
        
    def query_with_decay(self, query: str, top_k: int = 10) -> List[MemoryNode]:
        """
        Retrieve memories considering decay
        """
        # Get query embedding
        query_embedding = self.encode(query)
        
        # Calculate similarities with decay weighting
        scores = []
        for node in self.graph_memory.nodes.values():
            similarity = cosine_similarity(query_embedding, node.embedding)
            retrievability = self.decay_algorithm.calculate_node_decay(node, self.graph_memory)
            
            # Combined score
            score = similarity * retrievability
            scores.append((node, score))
        
        # Return top-k
        scores.sort(key=lambda x: x[1], reverse=True)
        return [node for node, _ in scores[:top_k]]
```

### 6.2 Temporal Knowledge Graphs (Graphiti)

```python
class TemporalGraphMemory:
    """
    Temporal-aware graph memory inspired by Zep Graphiti
    """
    
    def __init__(self):
        self.episodes = []  # List of episodic memories
        self.temporal_graph = GraphMemory()
        
    def add_episode(self, episode: Dict) -> None:
        """
        Process episodic information into graph
        """
        # Extract entities and relationships
        entities = self.extract_entities(episode)
        relationships = self.extract_relationships(episode)
        
        # Create temporal nodes
        for entity in entities:
            node = MemoryNode(
                node_id=f"{entity['id']}_{episode['timestamp']}",
                content=entity['content'],
                node_type='entity'
            )
            node.temporal_validity = episode['timestamp']
            self.temporal_graph.add_node(node)
        
        # Create temporal edges
        for rel in relationships:
            edge = MemoryEdge(
                source=rel['source'],
                target=rel['target'],
                edge_type=rel['type']
            )
            edge.temporal_range = (episode['timestamp'], None)  # Open-ended initially
            self.temporal_graph.add_edge(edge)
    
    def point_in_time_query(self, query: str, timestamp: datetime) -> List[MemoryNode]:
        """
        Query graph state at specific time
        """
        # Filter nodes valid at timestamp
        valid_nodes = [
            node for node in self.temporal_graph.nodes.values()
            if node.created_at <= timestamp and 
            (not hasattr(node, 'deleted_at') or node.deleted_at > timestamp)
        ]
        
        # Apply temporal decay
        for node in valid_nodes:
            time_delta = (timestamp - node.created_at).days
            node.temporal_retrievability = math.exp(-time_delta * 0.01)
        
        return self.query_with_temporal_decay(query, valid_nodes)
```

## 7. Biological-Inspired Features

### 7.1 Place Cell Implementation

```python
class PlaceCellMemory:
    """
    Spatial memory inspired by hippocampal place cells
    """
    
    def __init__(self, space_dimensions: int = 3):
        self.place_cells = {}  # location -> MemoryNode
        self.grid_cells = {}   # grid coordinates -> set of nodes
        self.dimensions = space_dimensions
        
    def create_place_cell(self, location: Tuple[float, ...], content: Any) -> MemoryNode:
        """
        Create spatially-anchored memory
        """
        node = MemoryNode(
            node_id=f"place_{hash(location)}",
            content=content,
            node_type='place'
        )
        
        # Spatial properties
        node.location = location
        node.receptive_field = 1.0  # Spatial extent
        
        # Grid cell mapping
        grid_coord = self.location_to_grid(location)
        self.grid_cells[grid_coord].add(node.id)
        
        return node
    
    def spatial_retrieval(self, current_location: Tuple[float, ...], 
                         radius: float = 2.0) -> List[MemoryNode]:
        """
        Retrieve memories near current location
        """
        nearby_memories = []
        
        for node in self.place_cells.values():
            distance = self.calculate_distance(current_location, node.location)
            
            if distance < radius:
                # Spatial decay based on distance
                node.spatial_activation = math.exp(-distance / node.receptive_field)
                nearby_memories.append(node)
        
        return sorted(nearby_memories, key=lambda n: n.spatial_activation, reverse=True)
```

### 7.2 Cognitive Map Construction

```python
class CognitiveMap:
    """
    Build cognitive maps like hippocampus
    """
    
    def __init__(self):
        self.spatial_graph = GraphMemory()
        self.place_cells = PlaceCellMemory()
        self.path_integrator = PathIntegrator()
        
    def build_map_from_experience(self, trajectory: List[Tuple]) -> None:
        """
        Construct map from experienced trajectory
        """
        previous_location = None
        
        for step in trajectory:
            location, observation = step
            
            # Create place cell for location
            place_node = self.place_cells.create_place_cell(location, observation)
            self.spatial_graph.add_node(place_node)
            
            # Connect sequential locations
            if previous_location:
                edge = MemoryEdge(
                    source=previous_location.id,
                    target=place_node.id,
                    edge_type='spatial_transition'
                )
                
                # Edge weight based on transition frequency
                edge.weight = 1.0
                self.spatial_graph.add_edge(edge)
            
            previous_location = place_node
        
        # Detect shortcuts and create additional edges
        self.detect_spatial_shortcuts()
    
    def navigate(self, start: Tuple, goal: Tuple) -> List[MemoryNode]:
        """
        Plan path using cognitive map
        """
        # Find nearest place cells
        start_node = self.find_nearest_place_cell(start)
        goal_node = self.find_nearest_place_cell(goal)
        
        # A* search on spatial graph
        path = self.astar_search(start_node, goal_node)
        
        return path
```

## 8. Performance Optimizations

### 8.1 Sparse Matrix Operations

```python
class SparseGraphOperations:
    """
    Efficient operations for large graphs
    """
    
    def __init__(self, graph: GraphMemory):
        # Convert to sparse matrix
        self.adjacency_matrix = self.build_sparse_adjacency(graph)
        self.decay_matrix = self.build_sparse_decay(graph)
        
    def batch_decay_update(self) -> scipy.sparse.csr_matrix:
        """
        Update all node decays in parallel
        """
        # Matrix multiplication for decay propagation
        decay_propagation = self.adjacency_matrix @ self.decay_matrix
        
        # Element-wise operations for time decay
        time_decay = scipy.sparse.diags(self.calculate_time_decays())
        
        # Combined update
        updated_decay = decay_propagation.multiply(time_decay)
        
        return updated_decay
    
    def parallel_pagerank(self, damping: float = 0.85, 
                         iterations: int = 30) -> np.ndarray:
        """
        Parallel PageRank for importance scoring
        """
        n = self.adjacency_matrix.shape[0]
        
        # Initialize scores
        scores = np.ones(n) / n
        
        # Power iteration
        for _ in range(iterations):
            scores = (1 - damping) / n + damping * self.adjacency_matrix.T @ scores
        
        return scores
```

### 8.2 Incremental Updates

```python
class IncrementalGraphUpdate:
    """
    Update graph without full recomputation
    """
    
    def __init__(self, graph: GraphMemory):
        self.graph = graph
        self.update_queue = deque()
        self.affected_nodes = set()
        
    def add_node_incremental(self, node: MemoryNode, connections: List[str]) -> None:
        """
        Add node and update only affected regions
        """
        # Add to graph
        self.graph.add_node(node)
        
        # Track affected nodes
        self.affected_nodes.add(node.id)
        self.affected_nodes.update(connections)
        
        # Queue updates
        for conn_id in connections:
            self.update_queue.append(('edge', node.id, conn_id))
        
        # Process updates in batch
        if len(self.update_queue) > 100:
            self.process_updates()
    
    def process_updates(self) -> None:
        """
        Batch process queued updates
        """
        # Update PageRank for affected nodes only
        subgraph = self.extract_subgraph(self.affected_nodes)
        local_pagerank = self.calculate_local_pagerank(subgraph)
        
        # Update decay for affected communities
        affected_communities = set(
            self.graph.nodes[n_id].community_id 
            for n_id in self.affected_nodes
        )
        
        for community_id in affected_communities:
            self.update_community_decay(community_id)
        
        # Clear queue
        self.update_queue.clear()
        self.affected_nodes.clear()
```

## 9. Practical Implementation Example

```python
class LLMGraphMemory:
    """
    Complete implementation for LLM memory system
    """
    
    def __init__(self):
        # Core components
        self.graph = GraphMemory()
        self.decay = GraphDecayAlgorithm()
        self.consolidation = CommunityConsolidation()
        self.hierarchy = HierarchicalMemory()
        
        # Biological features
        self.cognitive_map = CognitiveMap()
        
        # Optimization
        self.sparse_ops = None  # Initialized when graph is large
        self.incremental = IncrementalGraphUpdate(self.graph)
        
    def memorize(self, content: str, context: Dict) -> MemoryNode:
        """
        Store new memory with context
        """
        # Create node
        node = MemoryNode(
            node_id=str(uuid.uuid4()),
            content=content,
            node_type=context.get('type', 'fact')
        )
        
        # Generate embedding
        node.embedding = self.encode(content)
        
        # Find related memories
        related = self.find_similar_nodes(node.embedding, top_k=5)
        
        # Add to graph with connections
        self.graph.add_node(node)
        for related_node in related:
            similarity = cosine_similarity(node.embedding, related_node.embedding)
            edge = MemoryEdge(node.id, related_node.id, 'semantic')
            edge.weight = similarity
            self.graph.add_edge(edge)
        
        # Update graph properties
        self.incremental.add_node_incremental(node, [r.id for r in related])
        
        return node
    
    def recall(self, query: str, strategy: str = 'hybrid') -> List[MemoryNode]:
        """
        Retrieve memories using specified strategy
        """
        if strategy == 'spreading':
            # Find entry points
            query_embedding = self.encode(query)
            seeds = self.find_similar_nodes(query_embedding, top_k=3)
            
            # Spread activation
            activation = SpreadingActivation().activate(
                [s.id for s in seeds], 
                self.graph
            )
            
            # Return activated nodes
            activated_nodes = [
                self.graph.nodes[node_id] 
                for node_id, score in activation.items()
                if score > 0.1
            ]
            
        elif strategy == 'hierarchical':
            # Start from high-level concepts
            activated_nodes = self.hierarchy.query_hierarchy(query)
            
        else:  # hybrid
            spreading = self.recall(query, 'spreading')
            hierarchical = self.recall(query, 'hierarchical')
            
            # Combine and deduplicate
            activated_nodes = list(set(spreading + hierarchical))
        
        # Apply decay
        for node in activated_nodes:
            node.current_retrievability = self.decay.calculate_node_decay(node, self.graph)
        
        # Sort by retrievability
        activated_nodes.sort(key=lambda n: n.current_retrievability, reverse=True)
        
        return activated_nodes[:10]
    
    def consolidate_memories(self) -> None:
        """
        Periodic consolidation process
        """
        # Detect communities
        self.consolidation.detect_communities(self.graph)
        
        # Consolidate each community
        for community_id in self.graph.community_index:
            if len(self.graph.community_index[community_id]) > 10:
                summary = self.consolidation.consolidate_community(community_id, self.graph)
                self.graph.add_node(summary)
        
        # Build hierarchy
        self.hierarchy.build_hierarchy(self.graph)
        
        # Prune weak edges
        weak_edges = [
            (s, t) for (s, t), edge in self.graph.edges.items()
            if edge.weight < 0.1
        ]
        for s, t in weak_edges:
            self.graph.remove_edge(s, t)
```

## 10. Conclusion

Node-based memory systems offer significant advantages over linear memory architectures:

1. **Natural Relationship Representation**: Graph structure mirrors how knowledge is interconnected
2. **Efficient Decay Propagation**: Community and importance-based decay
3. **Biological Plausibility**: Inspired by hippocampal cognitive maps
4. **Scalability**: Sparse operations and incremental updates
5. **Flexible Retrieval**: Multiple strategies (spreading activation, hierarchical, hybrid)

The integration of FSRS decay algorithms with graph structures enables sophisticated memory management that combines the mathematical rigor of spaced repetition with the structural advantages of knowledge graphs, creating more intelligent and efficient memory systems for LLMs.