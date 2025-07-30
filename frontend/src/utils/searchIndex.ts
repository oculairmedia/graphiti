import { GraphNode } from '../api/types';

interface SearchIndex {
  // Inverted index for text search
  textIndex: Map<string, Set<string>>; // term -> node IDs
  // Node lookup
  nodeMap: Map<string, GraphNode>;
  // Pre-computed lowercase labels for exact matching
  labelIndex: Map<string, Set<string>>; // lowercase label -> node IDs
  // Type index for filtering
  typeIndex: Map<string, Set<string>>; // node type -> node IDs
}

export class GraphSearchIndex {
  private index: SearchIndex = {
    textIndex: new Map(),
    nodeMap: new Map(),
    labelIndex: new Map(),
    typeIndex: new Map(),
  };
  
  private tokenizeText(text: string): string[] {
    // Simple tokenization - split on non-alphanumeric characters
    return text.toLowerCase()
      .split(/[^a-z0-9]+/)
      .filter(token => token.length > 2); // Ignore very short tokens
  }
  
  // Build index from nodes
  buildIndex(nodes: GraphNode[]): void {
    // Clear existing index
    this.index.textIndex.clear();
    this.index.nodeMap.clear();
    this.index.labelIndex.clear();
    this.index.typeIndex.clear();
    
    nodes.forEach((node) => {
      // Store node in map
      this.index.nodeMap.set(node.id, node);
      
      // Index by type
      if (!this.index.typeIndex.has(node.node_type)) {
        this.index.typeIndex.set(node.node_type, new Set());
      }
      this.index.typeIndex.get(node.node_type)!.add(node.id);
      
      // Index label
      const labelLower = (node.label || node.id).toLowerCase();
      if (!this.index.labelIndex.has(labelLower)) {
        this.index.labelIndex.set(labelLower, new Set());
      }
      this.index.labelIndex.get(labelLower)!.add(node.id);
      
      // Build text index from various fields
      const textFields = [
        node.label || '',
        node.id || '',
        node.node_type || '',
        node.properties?.description || '',
        node.properties?.summary || '',
        node.properties?.content || '',
      ];
      
      const allText = textFields.join(' ');
      const tokens = this.tokenizeText(allText);
      
      tokens.forEach((token) => {
        if (!this.index.textIndex.has(token)) {
          this.index.textIndex.set(token, new Set());
        }
        this.index.textIndex.get(token)!.add(node.id);
      });
    });
  }
  
  // Search nodes with various strategies
  search(query: string, options?: {
    nodeTypes?: string[];
    limit?: number;
    fuzzy?: boolean;
  }): GraphNode[] {
    const { nodeTypes, limit = 100, fuzzy = false } = options || {};
    
    if (!query || query.trim() === '') {
      return [];
    }
    
    let matchingNodeIds: Set<string>;
    
    // Check if it's a regex search
    const isRegex = query.startsWith('/') && query.endsWith('/');
    if (isRegex) {
      matchingNodeIds = this.regexSearch(query.slice(1, -1));
    } else if (fuzzy) {
      matchingNodeIds = this.fuzzySearch(query);
    } else {
      matchingNodeIds = this.exactSearch(query);
    }
    
    // Filter by node types if specified
    if (nodeTypes && nodeTypes.length > 0) {
      const typeFilteredIds = new Set<string>();
      nodeTypes.forEach((type) => {
        const typeNodes = this.index.typeIndex.get(type);
        if (typeNodes) {
          typeNodes.forEach((id) => {
            if (matchingNodeIds.has(id)) {
              typeFilteredIds.add(id);
            }
          });
        }
      });
      matchingNodeIds = typeFilteredIds;
    }
    
    // Convert IDs to nodes and apply limit
    const results: GraphNode[] = [];
    for (const nodeId of matchingNodeIds) {
      const node = this.index.nodeMap.get(nodeId);
      if (node) {
        results.push(node);
        if (results.length >= limit) {
          break;
        }
      }
    }
    
    return results;
  }
  
  private exactSearch(query: string): Set<string> {
    const queryLower = query.toLowerCase();
    const tokens = this.tokenizeText(query);
    const matchingNodeIds = new Set<string>();
    
    // Check exact label matches first
    const exactLabelMatches = this.index.labelIndex.get(queryLower);
    if (exactLabelMatches) {
      exactLabelMatches.forEach((id) => matchingNodeIds.add(id));
    }
    
    // Check substring matches in labels
    for (const [label, nodeIds] of this.index.labelIndex) {
      if (label.includes(queryLower)) {
        nodeIds.forEach((id) => matchingNodeIds.add(id));
      }
    }
    
    // Token-based search for longer queries
    if (tokens.length > 0) {
      // Find nodes that contain ALL tokens (AND search)
      let candidateNodes: Set<string> | null = null;
      
      for (const token of tokens) {
        const tokenMatches = this.index.textIndex.get(token);
        if (!tokenMatches || tokenMatches.size === 0) {
          // If any token has no matches, result is empty
          return new Set();
        }
        
        if (candidateNodes === null) {
          candidateNodes = new Set(tokenMatches);
        } else {
          // Intersection with previous results
          const intersection = new Set<string>();
          for (const id of candidateNodes) {
            if (tokenMatches.has(id)) {
              intersection.add(id);
            }
          }
          candidateNodes = intersection;
        }
      }
      
      if (candidateNodes) {
        candidateNodes.forEach((id) => matchingNodeIds.add(id));
      }
    }
    
    return matchingNodeIds;
  }
  
  private fuzzySearch(query: string): Set<string> {
    const queryLower = query.toLowerCase();
    const tokens = this.tokenizeText(query);
    const nodeScores = new Map<string, number>();
    
    // Score based on token matches (OR search with scoring)
    tokens.forEach((token) => {
      const tokenMatches = this.index.textIndex.get(token);
      if (tokenMatches) {
        tokenMatches.forEach((nodeId) => {
          nodeScores.set(nodeId, (nodeScores.get(nodeId) || 0) + 1);
        });
      }
      
      // Also check partial token matches
      for (const [indexToken, nodeIds] of this.index.textIndex) {
        if (indexToken.includes(token) || token.includes(indexToken)) {
          nodeIds.forEach((nodeId) => {
            nodeScores.set(nodeId, (nodeScores.get(nodeId) || 0) + 0.5);
          });
        }
      }
    });
    
    // Sort by score and return top matches
    const sortedNodes = Array.from(nodeScores.entries())
      .sort((a, b) => b[1] - a[1])
      .map(([nodeId]) => nodeId);
    
    return new Set(sortedNodes);
  }
  
  private regexSearch(pattern: string): Set<string> {
    const matchingNodeIds = new Set<string>();
    
    try {
      const regex = new RegExp(pattern, 'i');
      
      // Search through all nodes
      for (const [nodeId, node] of this.index.nodeMap) {
        const searchableText = [
          node.label || '',
          node.id || '',
          node.node_type || '',
          node.properties?.description || '',
          node.properties?.summary || '',
        ].join(' ');
        
        if (regex.test(searchableText)) {
          matchingNodeIds.add(nodeId);
        }
      }
    } catch (e) {
      // Invalid regex, return empty set
      return new Set();
    }
    
    return matchingNodeIds;
  }
  
  // Get nodes by type
  getNodesByType(nodeType: string): GraphNode[] {
    const nodeIds = this.index.typeIndex.get(nodeType);
    if (!nodeIds) return [];
    
    const nodes: GraphNode[] = [];
    nodeIds.forEach((id) => {
      const node = this.index.nodeMap.get(id);
      if (node) nodes.push(node);
    });
    
    return nodes;
  }
  
  // Get all indexed node types
  getNodeTypes(): string[] {
    return Array.from(this.index.typeIndex.keys());
  }
  
  // Get index statistics
  getStats() {
    return {
      totalNodes: this.index.nodeMap.size,
      totalTerms: this.index.textIndex.size,
      totalTypes: this.index.typeIndex.size,
      avgTermsPerNode: this.index.textIndex.size / Math.max(1, this.index.nodeMap.size),
    };
  }
}

// Singleton instance
export const searchIndex = new GraphSearchIndex();