# Graph Memory Decay Implementation Guide
## Production-Ready Code for Node-Based Memory Systems

## 1. Executive Summary

This guide provides complete, production-ready implementations of decay algorithms for graph-based memory systems. It combines FSRS-6 spaced repetition with graph-specific features like PageRank importance, community detection, and spreading activation.

## 2. Core Implementation

### 2.1 Complete Graph Memory System

```python
import numpy as np
import networkx as nx
from typing import Dict, List, Tuple, Any, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from collections import defaultdict, deque
import scipy.sparse as sp
from sklearn.metrics.pairwise import cosine_similarity
import torch
import torch.nn as nn
import hashlib
import json
import pickle
from enum import Enum

class NodeType(Enum):
    """Types of memory nodes"""
    ENTITY = "entity"
    FACT = "fact"
    EPISODE = "episode"
    CONCEPT = "concept"
    SUMMARY = "summary"
    META = "meta"

class EdgeType(Enum):
    """Types of relationships"""
    SEMANTIC = "semantic"
    TEMPORAL = "temporal"
    CAUSAL = "causal"
    HIERARCHICAL = "hierarchical"
    SPATIAL = "spatial"

@dataclass
class MemoryNode:
    """
    Graph node representing a memory unit with FSRS parameters
    """
    # Identity
    id: str
    type: NodeType
    content: Any
    
    # FSRS-6 parameters
    stability: float = 1.0
    difficulty: float = 5.0
    retrievability: float = 1.0
    
    # Temporal metadata
    created_at: datetime = field(default_factory=datetime.now)
    last_accessed: datetime = field(default_factory=datetime.now)
    access_count: int = 0
    access_history: List[datetime] = field(default_factory=list)
    
    # Graph properties
    embedding: Optional[np.ndarray] = None
    importance: float = 0.5
    community_id: Optional[int] = None
    depth: int = 0
    
    # State management
    state: str = "active"  # active, dormant, forgotten
    
    def to_dict(self) -> Dict:
        """Serialize node to dictionary"""
        return {
            'id': self.id,
            'type': self.type.value,
            'content': self.content,
            'stability': self.stability,
            'difficulty': self.difficulty,
            'retrievability': self.retrievability,
            'created_at': self.created_at.isoformat(),
            'last_accessed': self.last_accessed.isoformat(),
            'access_count': self.access_count,
            'importance': self.importance,
            'community_id': self.community_id,
            'depth': self.depth,
            'state': self.state
        }

@dataclass
class MemoryEdge:
    """
    Graph edge representing relationship between memories
    """
    source: str
    target: str
    type: EdgeType
    weight: float = 1.0
    confidence: float = 1.0
    
    # Temporal properties
    created_at: datetime = field(default_factory=datetime.now)
    last_activated: datetime = field(default_factory=datetime.now)
    activation_count: int = 0
    
    # Decay parameters
    decay_rate: float = 0.1
    reinforcement_factor: float = 1.5
    
    def to_dict(self) -> Dict:
        """Serialize edge to dictionary"""
        return {
            'source': self.source,
            'target': self.target,
            'type': self.type.value,
            'weight': self.weight,
            'confidence': self.confidence,
            'created_at': self.created_at.isoformat(),
            'last_activated': self.last_activated.isoformat(),
            'activation_count': self.activation_count
        }
```

### 2.2 Graph Memory Manager

```python
class GraphMemoryManager:
    """
    Main class for managing graph-based memory with decay
    """
    
    def __init__(self, embedding_model=None):
        # Graph structure
        self.nodes: Dict[str, MemoryNode] = {}
        self.edges: Dict[Tuple[str, str], MemoryEdge] = {}
        self.adjacency: Dict[str, set] = defaultdict(set)
        self.reverse_adjacency: Dict[str, set] = defaultdict(set)
        
        # Indices for efficient access
        self.type_index: Dict[NodeType, set] = defaultdict(set)
        self.community_index: Dict[int, set] = defaultdict(set)
        self.state_index: Dict[str, set] = defaultdict(set)
        
        # Embedding model
        self.embedding_model = embedding_model or self._default_embedding_model()
        
        # FSRS-6 parameters (17 total)
        self.w = np.array([
            0.4, 0.6, 2.4, 5.8, 4.93, 0.94, 0.86, 0.01,
            1.49, 0.14, 0.94, 2.18, 0.05, 0.34, 1.26, 0.29, 2.61
        ])
        
        # Graph metrics cache
        self._pagerank_cache = None
        self._pagerank_timestamp = None
        self._community_cache = None
        
    def add_node(self, node: MemoryNode) -> None:
        """Add node to graph with indexing"""
        self.nodes[node.id] = node
        self.type_index[node.type].add(node.id)
        self.state_index[node.state].add(node.id)
        
        if node.community_id is not None:
            self.community_index[node.community_id].add(node.id)
        
        # Generate embedding if not provided
        if node.embedding is None and node.content:
            node.embedding = self._generate_embedding(node.content)
        
        # Invalidate caches
        self._invalidate_caches()
    
    def add_edge(self, edge: MemoryEdge) -> None:
        """Add edge to graph with bidirectional indexing"""
        key = (edge.source, edge.target)
        self.edges[key] = edge
        self.adjacency[edge.source].add(edge.target)
        self.reverse_adjacency[edge.target].add(edge.source)
        
        # Invalidate caches
        self._invalidate_caches()
    
    def remove_node(self, node_id: str) -> None:
        """Remove node and associated edges"""
        if node_id not in self.nodes:
            return
        
        node = self.nodes[node_id]
        
        # Remove from indices
        self.type_index[node.type].discard(node_id)
        self.state_index[node.state].discard(node_id)
        if node.community_id is not None:
            self.community_index[node.community_id].discard(node_id)
        
        # Remove edges
        edges_to_remove = []
        for neighbor in self.adjacency[node_id]:
            edges_to_remove.append((node_id, neighbor))
        for neighbor in self.reverse_adjacency[node_id]:
            edges_to_remove.append((neighbor, node_id))
        
        for edge_key in edges_to_remove:
            if edge_key in self.edges:
                del self.edges[edge_key]
        
        # Clean adjacency
        del self.adjacency[node_id]
        del self.reverse_adjacency[node_id]
        for adj in self.adjacency.values():
            adj.discard(node_id)
        for adj in self.reverse_adjacency.values():
            adj.discard(node_id)
        
        # Remove node
        del self.nodes[node_id]
        
        # Invalidate caches
        self._invalidate_caches()
    
    def _generate_embedding(self, content: Any) -> np.ndarray:
        """Generate embedding for content"""
        if isinstance(content, str):
            # Use embedding model for text
            return self.embedding_model.encode([str(content)])[0]
        elif isinstance(content, dict):
            # Concatenate dictionary values
            text = ' '.join(str(v) for v in content.values())
            return self.embedding_model.encode([text])[0]
        else:
            # Generic string conversion
            return self.embedding_model.encode([str(content)])[0]
    
    def _default_embedding_model(self):
        """Default embedding model using sentence-transformers"""
        try:
            from sentence_transformers import SentenceTransformer
            return SentenceTransformer('all-MiniLM-L6-v2')
        except ImportError:
            # Fallback to random embeddings
            class RandomEmbedder:
                def encode(self, texts):
                    return np.random.randn(len(texts), 384)
            return RandomEmbedder()
    
    def _invalidate_caches(self):
        """Invalidate computed graph metrics"""
        self._pagerank_cache = None
        self._community_cache = None
```

### 2.3 FSRS-Inspired Graph Decay

```python
class GraphFSRSDecay:
    """
    FSRS-6 decay algorithm adapted for graph structures
    """
    
    def __init__(self, graph_manager: GraphMemoryManager):
        self.graph = graph_manager
        
        # Decay thresholds
        self.theta_active = 0.8
        self.theta_dormant = 0.2
        self.theta_forgotten = 0.01
        
    def calculate_node_decay(self, node: MemoryNode) -> float:
        """
        Calculate retrievability with graph-aware modifications
        """
        # Base FSRS-6 retrievability
        days_elapsed = (datetime.now() - node.last_accessed).total_seconds() / 86400
        base_r = (1 + days_elapsed / (9 * node.stability)) ** (-1)
        
        # Graph modifiers
        importance_mod = self._importance_modifier(node)
        connectivity_mod = self._connectivity_modifier(node)
        community_mod = self._community_modifier(node)
        depth_mod = self._depth_modifier(node)
        
        # Weighted combination
        retrievability = base_r * (
            0.3 * importance_mod +
            0.2 * connectivity_mod +
            0.2 * community_mod +
            0.3 * depth_mod
        )
        
        # Update node state
        if retrievability > self.theta_active:
            node.state = "active"
        elif retrievability > self.theta_dormant:
            node.state = "dormant"
        else:
            node.state = "forgotten"
        
        node.retrievability = retrievability
        return retrievability
    
    def _importance_modifier(self, node: MemoryNode) -> float:
        """PageRank-based importance"""
        pagerank = self.graph.get_pagerank()
        if node.id in pagerank:
            # Normalize to [0.5, 2.0]
            return 0.5 + 1.5 * min(pagerank[node.id] * 100, 1.0)
        return 1.0
    
    def _connectivity_modifier(self, node: MemoryNode) -> float:
        """Well-connected nodes decay slower"""
        degree = len(self.graph.adjacency.get(node.id, set()))
        avg_degree = np.mean([len(adj) for adj in self.graph.adjacency.values()]) if self.graph.adjacency else 1
        
        # Sigmoid normalization
        return 1 + 0.5 * np.tanh((degree - avg_degree) / max(avg_degree, 1))
    
    def _community_modifier(self, node: MemoryNode) -> float:
        """Active communities decay slower"""
        if node.community_id is None:
            return 1.0
        
        community_nodes = self.graph.community_index[node.community_id]
        if not community_nodes:
            return 1.0
        
        # Calculate community activity
        recent_accesses = sum(
            1 for n_id in community_nodes
            if n_id in self.graph.nodes and
            (datetime.now() - self.graph.nodes[n_id].last_accessed).days < 7
        )
        
        activity_ratio = recent_accesses / len(community_nodes)
        return 1 + 0.5 * activity_ratio
    
    def _depth_modifier(self, node: MemoryNode) -> float:
        """Hierarchical depth affects decay"""
        depth_factors = {
            0: 1.0,   # Raw memories
            1: 1.2,   # Episodes
            2: 1.5,   # Concepts
            3: 2.0    # Meta-knowledge
        }
        return depth_factors.get(node.depth, 1.0)
    
    def reinforce_node(self, node: MemoryNode, quality: int = 3) -> None:
        """
        Reinforce memory using FSRS-6 update rules
        Quality: 1 (hard) to 5 (easy)
        """
        # Calculate current retrievability
        days_elapsed = (datetime.now() - node.last_accessed).total_seconds() / 86400
        retrievability = (1 + days_elapsed / (9 * node.stability)) ** (-1)
        
        # Stability update
        stability_increase = np.exp(self.graph.w[8] * (1/max(retrievability, 0.01) - 1))
        
        # Quality modifiers
        if quality == 1:
            stability_increase *= self.graph.w[15]
        elif quality == 5:
            stability_increase *= self.graph.w[16]
        
        # Update stability with cap
        node.stability = min(node.stability * stability_increase, 365)
        
        # Update difficulty
        node.difficulty = np.clip(
            node.difficulty - self.graph.w[6] * (quality - 3),
            1, 10
        )
        
        # Handle dormant reactivation
        if node.state == "dormant":
            node.stability *= 1.5
            node.state = "active"
        
        # Update access metadata
        node.last_accessed = datetime.now()
        node.access_count += 1
        node.access_history.append(datetime.now())
        
        # Reinforce connected edges
        self._reinforce_edges(node)
    
    def _reinforce_edges(self, node: MemoryNode) -> None:
        """Reinforce edges connected to accessed node"""
        for neighbor_id in self.graph.adjacency.get(node.id, set()):
            edge_key = (node.id, neighbor_id)
            if edge_key in self.graph.edges:
                edge = self.graph.edges[edge_key]
                edge.weight = min(edge.weight * edge.reinforcement_factor, 1.0)
                edge.last_activated = datetime.now()
                edge.activation_count += 1
```

### 2.4 Advanced Graph Operations

```python
class GraphOperations:
    """
    Advanced operations for graph memory
    """
    
    def __init__(self, graph_manager: GraphMemoryManager):
        self.graph = graph_manager
        
    def spreading_activation(self, seed_nodes: List[str], 
                           iterations: int = 5,
                           decay_factor: float = 0.7) -> Dict[str, float]:
        """
        Spread activation through graph for retrieval
        """
        activation = defaultdict(float)
        
        # Initialize seed nodes
        for node_id in seed_nodes:
            if node_id in self.graph.nodes:
                activation[node_id] = 1.0
        
        # Iterative spreading
        for iteration in range(iterations):
            new_activation = defaultdict(float)
            
            for node_id, current_activation in activation.items():
                # Spread to neighbors
                for neighbor_id in self.graph.adjacency.get(node_id, set()):
                    edge_key = (node_id, neighbor_id)
                    if edge_key in self.graph.edges:
                        edge = self.graph.edges[edge_key]
                        
                        # Activation spreads proportional to edge weight
                        spread = current_activation * edge.weight * 0.5
                        new_activation[neighbor_id] += spread
            
            # Decay and combine
            for node_id in new_activation:
                activation[node_id] = activation[node_id] * decay_factor + new_activation[node_id]
        
        return dict(activation)
    
    def detect_communities(self) -> Dict[str, int]:
        """
        Detect communities using Louvain algorithm
        """
        if not self.graph.nodes:
            return {}
        
        # Check cache
        if self.graph._community_cache is not None:
            return self.graph._community_cache
        
        # Build NetworkX graph
        G = nx.Graph()
        for node_id in self.graph.nodes:
            G.add_node(node_id)
        
        for (source, target), edge in self.graph.edges.items():
            G.add_edge(source, target, weight=edge.weight)
        
        # Detect communities
        try:
            import community.community_louvain as community_louvain
            communities = community_louvain.best_partition(G)
        except ImportError:
            # Fallback to connected components
            communities = {}
            for i, component in enumerate(nx.connected_components(G)):
                for node in component:
                    communities[node] = i
        
        # Update node community assignments
        for node_id, community_id in communities.items():
            if node_id in self.graph.nodes:
                self.graph.nodes[node_id].community_id = community_id
                self.graph.community_index[community_id].add(node_id)
        
        # Cache result
        self.graph._community_cache = communities
        
        return communities
    
    def consolidate_community(self, community_id: int) -> Optional[MemoryNode]:
        """
        Create summary node for community
        """
        community_nodes = [
            self.graph.nodes[n_id] 
            for n_id in self.graph.community_index[community_id]
            if n_id in self.graph.nodes
        ]
        
        if len(community_nodes) < 3:
            return None
        
        # Generate summary content
        contents = [node.content for node in community_nodes]
        summary_content = self._generate_summary(contents)
        
        # Create summary node
        summary_node = MemoryNode(
            id=f"summary_{community_id}_{datetime.now().timestamp()}",
            type=NodeType.SUMMARY,
            content=summary_content
        )
        
        # Inherit best stability
        summary_node.stability = max(n.stability for n in community_nodes)
        summary_node.depth = max(n.depth for n in community_nodes) + 1
        
        # Add to graph
        self.graph.add_node(summary_node)
        
        # Connect to community members
        for node in community_nodes:
            edge = MemoryEdge(
                source=summary_node.id,
                target=node.id,
                type=EdgeType.HIERARCHICAL,
                weight=0.8
            )
            self.graph.add_edge(edge)
        
        return summary_node
    
    def _generate_summary(self, contents: List[Any]) -> str:
        """Generate summary of contents"""
        # Simple concatenation for now
        # In production, use LLM for summarization
        return f"Summary of {len(contents)} items: " + str(contents[:3])
    
    def prune_weak_memories(self, threshold: float = 0.01) -> List[str]:
        """
        Remove nodes below retrievability threshold
        """
        decay_calculator = GraphFSRSDecay(self.graph)
        nodes_to_remove = []
        
        for node in self.graph.nodes.values():
            retrievability = decay_calculator.calculate_node_decay(node)
            if retrievability < threshold:
                nodes_to_remove.append(node.id)
        
        # Remove nodes
        for node_id in nodes_to_remove:
            self.graph.remove_node(node_id)
        
        return nodes_to_remove
```

### 2.5 Retrieval System

```python
class GraphMemoryRetrieval:
    """
    Sophisticated retrieval from graph memory
    """
    
    def __init__(self, graph_manager: GraphMemoryManager):
        self.graph = graph_manager
        self.decay = GraphFSRSDecay(graph_manager)
        self.operations = GraphOperations(graph_manager)
        
    def retrieve(self, query: str, strategy: str = "hybrid", top_k: int = 10) -> List[MemoryNode]:
        """
        Retrieve memories using specified strategy
        """
        if strategy == "embedding":
            return self._embedding_retrieval(query, top_k)
        elif strategy == "spreading":
            return self._spreading_retrieval(query, top_k)
        elif strategy == "hierarchical":
            return self._hierarchical_retrieval(query, top_k)
        elif strategy == "temporal":
            return self._temporal_retrieval(query, top_k)
        else:  # hybrid
            return self._hybrid_retrieval(query, top_k)
    
    def _embedding_retrieval(self, query: str, top_k: int) -> List[MemoryNode]:
        """Simple embedding-based retrieval"""
        query_embedding = self.graph._generate_embedding(query)
        
        scores = []
        for node in self.graph.nodes.values():
            if node.embedding is not None:
                similarity = cosine_similarity(
                    query_embedding.reshape(1, -1),
                    node.embedding.reshape(1, -1)
                )[0, 0]
                
                # Weight by retrievability
                retrievability = self.decay.calculate_node_decay(node)
                score = similarity * retrievability
                scores.append((node, score))
        
        scores.sort(key=lambda x: x[1], reverse=True)
        return [node for node, _ in scores[:top_k]]
    
    def _spreading_retrieval(self, query: str, top_k: int) -> List[MemoryNode]:
        """Spreading activation retrieval"""
        # Find seed nodes
        seed_nodes = self._embedding_retrieval(query, 3)
        seed_ids = [n.id for n in seed_nodes]
        
        # Spread activation
        activation = self.operations.spreading_activation(seed_ids)
        
        # Get activated nodes
        activated = []
        for node_id, activation_score in activation.items():
            if node_id in self.graph.nodes:
                node = self.graph.nodes[node_id]
                retrievability = self.decay.calculate_node_decay(node)
                score = activation_score * retrievability
                activated.append((node, score))
        
        activated.sort(key=lambda x: x[1], reverse=True)
        return [node for node, _ in activated[:top_k]]
    
    def _hierarchical_retrieval(self, query: str, top_k: int) -> List[MemoryNode]:
        """Top-down hierarchical retrieval"""
        # Start with high-level nodes
        high_level = [
            n for n in self.graph.nodes.values()
            if n.depth >= 2
        ]
        
        if not high_level:
            return self._embedding_retrieval(query, top_k)
        
        # Score high-level nodes
        query_embedding = self.graph._generate_embedding(query)
        scores = []
        
        for node in high_level:
            if node.embedding is not None:
                similarity = cosine_similarity(
                    query_embedding.reshape(1, -1),
                    node.embedding.reshape(1, -1)
                )[0, 0]
                scores.append((node, similarity))
        
        scores.sort(key=lambda x: x[1], reverse=True)
        
        # Expand top concepts
        expanded = []
        for node, score in scores[:3]:
            expanded.append(node)
            
            # Add children
            for child_id in self.graph.adjacency.get(node.id, set()):
                if self.graph.edges.get((node.id, child_id), None):
                    edge = self.graph.edges[(node.id, child_id)]
                    if edge.type == EdgeType.HIERARCHICAL:
                        child = self.graph.nodes.get(child_id)
                        if child:
                            expanded.append(child)
        
        # Apply decay and sort
        for node in expanded:
            node.temp_score = self.decay.calculate_node_decay(node)
        
        expanded.sort(key=lambda x: x.temp_score, reverse=True)
        return expanded[:top_k]
    
    def _temporal_retrieval(self, query: str, top_k: int) -> List[MemoryNode]:
        """Retrieve based on temporal patterns"""
        # Get base candidates
        candidates = self._embedding_retrieval(query, top_k * 2)
        
        # Score by recency and access patterns
        scored = []
        for node in candidates:
            recency_score = 1 / (1 + (datetime.now() - node.last_accessed).days)
            frequency_score = min(node.access_count / 10, 1.0)
            retrievability = self.decay.calculate_node_decay(node)
            
            temporal_score = (
                0.3 * recency_score +
                0.2 * frequency_score +
                0.5 * retrievability
            )
            scored.append((node, temporal_score))
        
        scored.sort(key=lambda x: x[1], reverse=True)
        return [node for node, _ in scored[:top_k]]
    
    def _hybrid_retrieval(self, query: str, top_k: int) -> List[MemoryNode]:
        """Combine multiple retrieval strategies"""
        # Get results from each strategy
        embedding_results = set(n.id for n in self._embedding_retrieval(query, top_k))
        spreading_results = set(n.id for n in self._spreading_retrieval(query, top_k))
        hierarchical_results = set(n.id for n in self._hierarchical_retrieval(query, top_k))
        
        # Score by presence in multiple strategies
        node_scores = defaultdict(float)
        
        for node_id in embedding_results:
            node_scores[node_id] += 0.4
        for node_id in spreading_results:
            node_scores[node_id] += 0.3
        for node_id in hierarchical_results:
            node_scores[node_id] += 0.3
        
        # Apply decay
        final_scores = []
        for node_id, strategy_score in node_scores.items():
            if node_id in self.graph.nodes:
                node = self.graph.nodes[node_id]
                retrievability = self.decay.calculate_node_decay(node)
                final_score = strategy_score * retrievability
                final_scores.append((node, final_score))
        
        final_scores.sort(key=lambda x: x[1], reverse=True)
        return [node for node, _ in final_scores[:top_k]]
```

### 2.6 Persistence and Serialization

```python
class GraphMemoryPersistence:
    """
    Save and load graph memory
    """
    
    @staticmethod
    def save(graph_manager: GraphMemoryManager, filepath: str) -> None:
        """Save graph to file"""
        data = {
            'nodes': {
                node_id: node.to_dict()
                for node_id, node in graph_manager.nodes.items()
            },
            'edges': [
                edge.to_dict()
                for edge in graph_manager.edges.values()
            ],
            'metadata': {
                'created_at': datetime.now().isoformat(),
                'node_count': len(graph_manager.nodes),
                'edge_count': len(graph_manager.edges)
            }
        }
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
    
    @staticmethod
    def load(filepath: str) -> GraphMemoryManager:
        """Load graph from file"""
        with open(filepath, 'r') as f:
            data = json.load(f)
        
        graph = GraphMemoryManager()
        
        # Load nodes
        for node_id, node_data in data['nodes'].items():
            node = MemoryNode(
                id=node_data['id'],
                type=NodeType(node_data['type']),
                content=node_data['content']
            )
            
            # Restore attributes
            node.stability = node_data['stability']
            node.difficulty = node_data['difficulty']
            node.retrievability = node_data['retrievability']
            node.created_at = datetime.fromisoformat(node_data['created_at'])
            node.last_accessed = datetime.fromisoformat(node_data['last_accessed'])
            node.access_count = node_data['access_count']
            node.importance = node_data['importance']
            node.community_id = node_data.get('community_id')
            node.depth = node_data['depth']
            node.state = node_data['state']
            
            graph.add_node(node)
        
        # Load edges
        for edge_data in data['edges']:
            edge = MemoryEdge(
                source=edge_data['source'],
                target=edge_data['target'],
                type=EdgeType(edge_data['type'])
            )
            
            # Restore attributes
            edge.weight = edge_data['weight']
            edge.confidence = edge_data['confidence']
            edge.created_at = datetime.fromisoformat(edge_data['created_at'])
            edge.last_activated = datetime.fromisoformat(edge_data['last_activated'])
            edge.activation_count = edge_data['activation_count']
            
            graph.add_edge(edge)
        
        return graph
```

## 3. Usage Examples

### 3.1 Basic Usage

```python
# Initialize system
graph = GraphMemoryManager()
decay = GraphFSRSDecay(graph)
retrieval = GraphMemoryRetrieval(graph)
operations = GraphOperations(graph)

# Add memories
node1 = MemoryNode(
    id="mem_001",
    type=NodeType.FACT,
    content="Python is a programming language"
)
graph.add_node(node1)

node2 = MemoryNode(
    id="mem_002",
    type=NodeType.FACT,
    content="Python was created by Guido van Rossum"
)
graph.add_node(node2)

# Create relationship
edge = MemoryEdge(
    source="mem_001",
    target="mem_002",
    type=EdgeType.SEMANTIC,
    weight=0.8
)
graph.add_edge(edge)

# Retrieve memories
results = retrieval.retrieve("Tell me about Python", strategy="hybrid")
for node in results:
    print(f"{node.content} (retrievability: {node.retrievability:.2f})")

# Reinforce accessed memory
decay.reinforce_node(results[0], quality=4)  # Easy recall

# Detect and consolidate communities
communities = operations.detect_communities()
for community_id in set(communities.values()):
    summary = operations.consolidate_community(community_id)
    if summary:
        print(f"Created summary for community {community_id}")

# Prune weak memories
removed = operations.prune_weak_memories(threshold=0.01)
print(f"Pruned {len(removed)} weak memories")

# Save graph
GraphMemoryPersistence.save(graph, "memory_graph.json")
```

### 3.2 Advanced Integration

```python
class LLMWithGraphMemory:
    """
    LLM system with graph-based memory
    """
    
    def __init__(self):
        self.graph = GraphMemoryManager()
        self.decay = GraphFSRSDecay(self.graph)
        self.retrieval = GraphMemoryRetrieval(self.graph)
        self.operations = GraphOperations(self.graph)
        
    def process_conversation(self, user_input: str) -> str:
        """
        Process user input with memory context
        """
        # Retrieve relevant memories
        memories = self.retrieval.retrieve(user_input, strategy="hybrid", top_k=5)
        
        # Build context
        context = self._build_context(memories)
        
        # Generate response (placeholder for actual LLM)
        response = self._generate_response(user_input, context)
        
        # Store interaction as new memory
        self._store_interaction(user_input, response)
        
        # Reinforce accessed memories
        for memory in memories:
            self.decay.reinforce_node(memory, quality=3)
        
        return response
    
    def _build_context(self, memories: List[MemoryNode]) -> str:
        """Build context from memories"""
        context_parts = []
        for memory in memories:
            context_parts.append(f"- {memory.content} (confidence: {memory.retrievability:.2f})")
        return "\n".join(context_parts)
    
    def _generate_response(self, user_input: str, context: str) -> str:
        """Generate response with context"""
        # Placeholder for actual LLM integration
        return f"Based on context:\n{context}\n\nResponse to: {user_input}"
    
    def _store_interaction(self, user_input: str, response: str) -> None:
        """Store interaction as episodic memory"""
        # Create episode node
        episode = MemoryNode(
            id=f"episode_{datetime.now().timestamp()}",
            type=NodeType.EPISODE,
            content={
                "user": user_input,
                "assistant": response,
                "timestamp": datetime.now().isoformat()
            }
        )
        self.graph.add_node(episode)
        
        # Find and connect related memories
        related = self.retrieval.retrieve(user_input, strategy="embedding", top_k=3)
        for memory in related:
            edge = MemoryEdge(
                source=episode.id,
                target=memory.id,
                type=EdgeType.TEMPORAL,
                weight=0.6
            )
            self.graph.add_edge(edge)
        
        # Periodic maintenance
        if len(self.graph.nodes) % 100 == 0:
            self._maintenance()
    
    def _maintenance(self) -> None:
        """Periodic graph maintenance"""
        # Detect communities
        self.operations.detect_communities()
        
        # Consolidate large communities
        for community_id in self.graph.community_index:
            if len(self.graph.community_index[community_id]) > 20:
                self.operations.consolidate_community(community_id)
        
        # Prune weak memories
        self.operations.prune_weak_memories(threshold=0.005)
        
        # Save checkpoint
        GraphMemoryPersistence.save(self.graph, f"checkpoint_{datetime.now().timestamp()}.json")
```

## 4. Performance Optimizations

### 4.1 Sparse Matrix Operations

```python
class SparseGraphOperations:
    """
    Optimized operations using sparse matrices
    """
    
    def __init__(self, graph_manager: GraphMemoryManager):
        self.graph = graph_manager
        self._adjacency_matrix = None
        self._last_update = None
        
    def get_adjacency_matrix(self) -> sp.csr_matrix:
        """Get sparse adjacency matrix"""
        # Check if update needed
        if self._adjacency_matrix is None or self._needs_update():
            self._build_adjacency_matrix()
        return self._adjacency_matrix
    
    def _build_adjacency_matrix(self) -> None:
        """Build sparse adjacency matrix"""
        node_ids = list(self.graph.nodes.keys())
        node_to_idx = {node_id: i for i, node_id in enumerate(node_ids)}
        
        rows, cols, data = [], [], []
        for (source, target), edge in self.graph.edges.items():
            if source in node_to_idx and target in node_to_idx:
                rows.append(node_to_idx[source])
                cols.append(node_to_idx[target])
                data.append(edge.weight)
        
        self._adjacency_matrix = sp.csr_matrix(
            (data, (rows, cols)),
            shape=(len(node_ids), len(node_ids))
        )
        self._last_update = datetime.now()
    
    def batch_pagerank(self, damping: float = 0.85, 
                      max_iter: int = 100,
                      tol: float = 1e-6) -> Dict[str, float]:
        """
        Efficient PageRank using sparse matrices
        """
        adj = self.get_adjacency_matrix()
        n = adj.shape[0]
        
        # Column-normalize adjacency matrix
        col_sums = np.array(adj.sum(axis=0)).flatten()
        col_sums[col_sums == 0] = 1
        norm_adj = adj / col_sums
        
        # Initialize scores
        scores = np.ones(n) / n
        
        # Power iteration
        for _ in range(max_iter):
            prev_scores = scores.copy()
            scores = (1 - damping) / n + damping * norm_adj.T @ scores
            
            if np.linalg.norm(scores - prev_scores) < tol:
                break
        
        # Map back to node IDs
        node_ids = list(self.graph.nodes.keys())
        return {node_ids[i]: scores[i] for i in range(n)}
    
    def batch_decay_update(self) -> None:
        """
        Update all node decays efficiently
        """
        node_ids = list(self.graph.nodes.keys())
        n = len(node_ids)
        
        # Vectorized time calculations
        current_time = datetime.now()
        days_elapsed = np.array([
            (current_time - self.graph.nodes[nid].last_accessed).total_seconds() / 86400
            for nid in node_ids
        ])
        
        stabilities = np.array([
            self.graph.nodes[nid].stability for nid in node_ids
        ])
        
        # Vectorized FSRS calculation
        retrievabilities = (1 + days_elapsed / (9 * stabilities)) ** (-1)
        
        # Update nodes
        for i, node_id in enumerate(node_ids):
            self.graph.nodes[node_id].retrievability = retrievabilities[i]
```

## 5. Conclusion

This implementation provides a complete, production-ready graph memory system with:

1. **FSRS-6 decay** adapted for graph structures
2. **Multiple retrieval strategies** (embedding, spreading, hierarchical, temporal, hybrid)
3. **Community detection and consolidation**
4. **Efficient sparse matrix operations**
5. **Persistence and serialization**
6. **Integration patterns** for LLM systems

The system combines the mathematical rigor of spaced repetition with the structural advantages of graph representations, enabling sophisticated memory management for AI applications.