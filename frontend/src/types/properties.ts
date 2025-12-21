// Specific property types for nodes and edges

// Node centrality metrics
export interface NodeCentralityMetrics {
  degree_centrality?: number;
  betweenness_centrality?: number;
  closeness_centrality?: number;
  eigenvector_centrality?: number;
  pagerank_centrality?: number;
}

// Node temporal properties
export interface NodeTemporalProperties {
  created_at?: string;
  updated_at?: string;
  last_modified?: string;
  occurred_at?: string;
  valid_from?: string;
  valid_to?: string;
}

// Node metadata properties
export interface NodeMetadata {
  source?: string;
  confidence?: number;
  version?: number;
  tags?: string[];
  category?: string;
  subcategory?: string;
}

// Complete node properties interface
export interface NodeProperties extends NodeCentralityMetrics, NodeTemporalProperties, NodeMetadata {
  // Common properties
  name?: string;
  description?: string;
  summary?: string;
  content?: string;
  url?: string;
  source_description?: string;
  
  // Numeric properties
  weight?: number;
  score?: number;
  rank?: number;
  priority?: number;
  
  // Graph metric properties (computed)
  degree?: number;
  connections?: number;
  pagerank?: number;
  
  // Temporal fields (alternative names)
  created?: string;
  created_at_timestamp?: number;
  updated?: string;
  date?: string;
  
  // Relationship properties
  parent_id?: string;
  child_ids?: string[];
  related_ids?: string[];
  
  // Status properties
  status?: 'active' | 'inactive' | 'pending' | 'archived';
  visibility?: 'public' | 'private' | 'restricted';
  
  // Custom properties with strict typing
  custom?: {
    [key: string]: string | number | boolean | null;
  };
  
  // Index signature for dynamic properties - allows Record<string, unknown> compatibility
  [key: string]: unknown;
}

// Edge properties
export interface EdgeProperties {
  // Temporal properties
  created_at?: string;
  updated_at?: string;
  valid_from?: string;
  valid_to?: string;
  
  // Relationship strength
  weight?: number;
  confidence?: number;
  strength?: number;
  
  // Metadata
  source?: string;
  reason?: string;
  context?: string;
  
  // Custom properties
  custom?: {
    [key: string]: string | number | boolean | null;
  };
  
  // Index signature for dynamic properties - allows Record<string, unknown> compatibility
  [key: string]: unknown;
}

// Type guards
export function isNodeCentralityMetric(key: string): key is keyof NodeCentralityMetrics {
  return ['degree_centrality', 'betweenness_centrality', 'closeness_centrality', 
          'eigenvector_centrality', 'pagerank_centrality'].includes(key);
}

export function isNodeTemporalProperty(key: string): key is keyof NodeTemporalProperties {
  return ['created_at', 'updated_at', 'last_modified', 'occurred_at', 
          'valid_from', 'valid_to'].includes(key);
}

// List of valid node property keys for runtime checking
const NODE_PROPERTY_KEYS: ReadonlyArray<keyof NodeProperties> = [
  // Centrality metrics
  'degree_centrality', 'betweenness_centrality', 'closeness_centrality',
  'eigenvector_centrality', 'pagerank_centrality',
  // Temporal properties
  'created_at', 'updated_at', 'last_modified', 'occurred_at', 'valid_from', 'valid_to',
  // Metadata
  'source', 'confidence', 'version', 'tags', 'category', 'subcategory',
  // Common properties
  'name', 'description', 'summary', 'content', 'url',
  // Numeric properties
  'weight', 'score', 'rank', 'priority',
  // Relationship properties
  'parent_id', 'child_ids', 'related_ids',
  // Status properties
  'status', 'visibility',
  // Custom properties
  'custom',
];

// List of valid edge property keys for runtime checking
const EDGE_PROPERTY_KEYS: ReadonlyArray<keyof EdgeProperties> = [
  'created_at', 'updated_at', 'valid_from', 'valid_to',
  'weight', 'confidence', 'strength',
  'source', 'reason', 'context',
  'custom',
];

// Check if a key is a known NodeProperties key
export function isValidNodeProperty(key: string): boolean {
  return (NODE_PROPERTY_KEYS as readonly string[]).includes(key);
}

// Check if a key is a known EdgeProperties key
export function isValidEdgeProperty(key: string): boolean {
  return (EDGE_PROPERTY_KEYS as readonly string[]).includes(key);
}