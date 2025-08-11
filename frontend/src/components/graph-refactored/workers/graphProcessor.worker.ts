/**
 * Web Worker for heavy graph data processing
 * Offloads CPU-intensive tasks from the main thread
 */

import { GraphNode } from '../../../api/types';
import { GraphLink } from '../../../types/graph';

// Worker message types
export interface WorkerMessage {
  id: string;
  type: WorkerMessageType;
  payload: any;
}

export enum WorkerMessageType {
  // Data processing
  ProcessNodes = 'PROCESS_NODES',
  ProcessLinks = 'PROCESS_LINKS',
  CalculateLayout = 'CALCULATE_LAYOUT',
  CalculateCentrality = 'CALCULATE_CENTRALITY',
  CalculateClusters = 'CALCULATE_CLUSTERS',
  
  // Filtering and search
  FilterNodes = 'FILTER_NODES',
  FilterLinks = 'FILTER_LINKS',
  SearchNodes = 'SEARCH_NODES',
  FindPaths = 'FIND_PATHS',
  
  // Transformations
  TransformData = 'TRANSFORM_DATA',
  MergeDeltas = 'MERGE_DELTAS',
  ValidateData = 'VALIDATE_DATA',
  
  // Analysis
  CalculateStats = 'CALCULATE_STATS',
  DetectCommunities = 'DETECT_COMMUNITIES',
  AnalyzeSubgraph = 'ANALYZE_SUBGRAPH',
  
  // Control
  Cancel = 'CANCEL',
  Clear = 'CLEAR'
}

export interface WorkerResponse {
  id: string;
  type: WorkerMessageType;
  success: boolean;
  result?: any;
  error?: string;
  duration?: number;
}

// Processing state
let isProcessing = false;
let cancelRequested = false;

// Cache for intermediate results
const cache = new Map<string, any>();

/**
 * Main message handler
 */
self.addEventListener('message', async (event: MessageEvent<WorkerMessage>) => {
  const { id, type, payload } = event.data;
  const startTime = performance.now();
  
  try {
    if (type === WorkerMessageType.Cancel) {
      cancelRequested = true;
      sendResponse({ id, type, success: true });
      return;
    }
    
    if (type === WorkerMessageType.Clear) {
      cache.clear();
      sendResponse({ id, type, success: true });
      return;
    }
    
    isProcessing = true;
    cancelRequested = false;
    
    let result: any;
    
    switch (type) {
      case WorkerMessageType.ProcessNodes:
        result = await processNodes(payload);
        break;
        
      case WorkerMessageType.ProcessLinks:
        result = await processLinks(payload);
        break;
        
      case WorkerMessageType.CalculateLayout:
        result = await calculateLayout(payload);
        break;
        
      case WorkerMessageType.CalculateCentrality:
        result = await calculateCentrality(payload);
        break;
        
      case WorkerMessageType.CalculateClusters:
        result = await calculateClusters(payload);
        break;
        
      case WorkerMessageType.FilterNodes:
        result = await filterNodes(payload);
        break;
        
      case WorkerMessageType.FilterLinks:
        result = await filterLinks(payload);
        break;
        
      case WorkerMessageType.SearchNodes:
        result = await searchNodes(payload);
        break;
        
      case WorkerMessageType.FindPaths:
        result = await findPaths(payload);
        break;
        
      case WorkerMessageType.TransformData:
        result = await transformData(payload);
        break;
        
      case WorkerMessageType.MergeDeltas:
        result = await mergeDeltas(payload);
        break;
        
      case WorkerMessageType.ValidateData:
        result = await validateData(payload);
        break;
        
      case WorkerMessageType.CalculateStats:
        result = await calculateStats(payload);
        break;
        
      case WorkerMessageType.DetectCommunities:
        result = await detectCommunities(payload);
        break;
        
      case WorkerMessageType.AnalyzeSubgraph:
        result = await analyzeSubgraph(payload);
        break;
        
      default:
        throw new Error(`Unknown message type: ${type}`);
    }
    
    const duration = performance.now() - startTime;
    sendResponse({ id, type, success: true, result, duration });
    
  } catch (error) {
    const duration = performance.now() - startTime;
    sendResponse({
      id,
      type,
      success: false,
      error: error instanceof Error ? error.message : 'Unknown error',
      duration
    });
  } finally {
    isProcessing = false;
  }
});

/**
 * Send response back to main thread
 */
function sendResponse(response: WorkerResponse) {
  self.postMessage(response);
}

/**
 * Check if processing should be cancelled
 */
function shouldCancel(): boolean {
  return cancelRequested;
}

// ============================================================================
// Processing Functions
// ============================================================================

/**
 * Process and enrich nodes with calculated properties
 */
async function processNodes(payload: {
  nodes: GraphNode[];
  options?: {
    calculateDegree?: boolean;
    calculateCentrality?: boolean;
    normalize?: boolean;
  };
}): Promise<GraphNode[]> {
  const { nodes, options = {} } = payload;
  const processed: GraphNode[] = [];
  
  for (let i = 0; i < nodes.length; i++) {
    if (shouldCancel()) break;
    
    const node = { ...nodes[i] };
    
    // Add calculated properties
    if (options.calculateDegree) {
      node.properties = {
        ...node.properties,
        degree: 0 // Would calculate from links
      };
    }
    
    if (options.normalize) {
      node.label = node.label || node.id;
      node.node_type = node.node_type || 'Unknown';
    }
    
    processed.push(node);
    
    // Yield to prevent blocking
    if (i % 1000 === 0) {
      await new Promise(resolve => setTimeout(resolve, 0));
    }
  }
  
  return processed;
}

/**
 * Process and validate links
 */
async function processLinks(payload: {
  links: GraphLink[];
  nodeIds: Set<string>;
}): Promise<GraphLink[]> {
  const { links, nodeIds } = payload;
  const processed: GraphLink[] = [];
  
  for (const link of links) {
    if (shouldCancel()) break;
    
    // Validate link endpoints exist
    if (nodeIds.has(link.source) && nodeIds.has(link.target)) {
      processed.push({
        ...link,
        weight: link.weight || 1
      });
    }
  }
  
  return processed;
}

/**
 * Calculate force-directed layout
 */
async function calculateLayout(payload: {
  nodes: GraphNode[];
  links: GraphLink[];
  iterations?: number;
}): Promise<{ nodes: Array<GraphNode & { x: number; y: number }> }> {
  const { nodes, links, iterations = 100 } = payload;
  
  // Initialize positions randomly
  const positioned = nodes.map(node => ({
    ...node,
    x: Math.random() * 1000,
    y: Math.random() * 1000,
    vx: 0,
    vy: 0
  }));
  
  // Simple force simulation
  for (let iter = 0; iter < iterations; iter++) {
    if (shouldCancel()) break;
    
    // Apply forces
    for (let i = 0; i < positioned.length; i++) {
      const node = positioned[i];
      
      // Repulsion between nodes
      for (let j = i + 1; j < positioned.length; j++) {
        const other = positioned[j];
        const dx = other.x - node.x;
        const dy = other.y - node.y;
        const dist = Math.sqrt(dx * dx + dy * dy) || 1;
        const force = 100 / (dist * dist);
        
        node.vx -= (dx / dist) * force;
        node.vy -= (dy / dist) * force;
        other.vx += (dx / dist) * force;
        other.vy += (dy / dist) * force;
      }
    }
    
    // Apply velocities
    for (const node of positioned) {
      node.x += node.vx * 0.1;
      node.y += node.vy * 0.1;
      node.vx *= 0.85; // Friction
      node.vy *= 0.85;
    }
    
    // Yield periodically
    if (iter % 10 === 0) {
      await new Promise(resolve => setTimeout(resolve, 0));
    }
  }
  
  return { nodes: positioned };
}

/**
 * Calculate node centrality metrics
 */
async function calculateCentrality(payload: {
  nodes: GraphNode[];
  links: GraphLink[];
  metric?: 'degree' | 'betweenness' | 'closeness' | 'eigenvector';
}): Promise<Map<string, number>> {
  const { nodes, links, metric = 'degree' } = payload;
  const centrality = new Map<string, number>();
  
  // Build adjacency list
  const adjacency = new Map<string, Set<string>>();
  for (const node of nodes) {
    adjacency.set(node.id, new Set());
  }
  for (const link of links) {
    adjacency.get(link.source)?.add(link.target);
    adjacency.get(link.target)?.add(link.source);
  }
  
  if (metric === 'degree') {
    // Degree centrality
    for (const [nodeId, neighbors] of adjacency) {
      centrality.set(nodeId, neighbors.size / (nodes.length - 1));
    }
  } else if (metric === 'betweenness') {
    // Simplified betweenness (would need full shortest path calculation)
    for (const node of nodes) {
      centrality.set(node.id, Math.random()); // Placeholder
    }
  }
  
  return centrality;
}

/**
 * Detect clusters using simple algorithm
 */
async function calculateClusters(payload: {
  nodes: GraphNode[];
  links: GraphLink[];
  resolution?: number;
}): Promise<Map<string, number>> {
  const { nodes, links, resolution = 1 } = payload;
  const clusters = new Map<string, number>();
  
  // Simple connected components for now
  const visited = new Set<string>();
  let clusterId = 0;
  
  for (const node of nodes) {
    if (visited.has(node.id)) continue;
    
    // BFS to find connected component
    const queue = [node.id];
    visited.add(node.id);
    
    while (queue.length > 0) {
      const current = queue.shift()!;
      clusters.set(current, clusterId);
      
      // Find neighbors
      for (const link of links) {
        let neighbor: string | null = null;
        if (link.source === current) neighbor = link.target;
        if (link.target === current) neighbor = link.source;
        
        if (neighbor && !visited.has(neighbor)) {
          visited.add(neighbor);
          queue.push(neighbor);
        }
      }
    }
    
    clusterId++;
  }
  
  return clusters;
}

/**
 * Filter nodes based on criteria
 */
async function filterNodes(payload: {
  nodes: GraphNode[];
  criteria: {
    types?: string[];
    search?: string;
    minDegree?: number;
    properties?: Record<string, any>;
  };
}): Promise<GraphNode[]> {
  const { nodes, criteria } = payload;
  
  return nodes.filter(node => {
    if (shouldCancel()) return false;
    
    if (criteria.types && !criteria.types.includes(node.node_type)) {
      return false;
    }
    
    if (criteria.search) {
      const searchLower = criteria.search.toLowerCase();
      if (!node.label.toLowerCase().includes(searchLower) &&
          !node.summary?.toLowerCase().includes(searchLower)) {
        return false;
      }
    }
    
    if (criteria.properties) {
      for (const [key, value] of Object.entries(criteria.properties)) {
        if (node.properties[key] !== value) {
          return false;
        }
      }
    }
    
    return true;
  });
}

/**
 * Filter links based on criteria
 */
async function filterLinks(payload: {
  links: GraphLink[];
  nodeIds?: Set<string>;
  types?: string[];
  minWeight?: number;
}): Promise<GraphLink[]> {
  const { links, nodeIds, types, minWeight = 0 } = payload;
  
  return links.filter(link => {
    if (nodeIds && (!nodeIds.has(link.source) || !nodeIds.has(link.target))) {
      return false;
    }
    
    if (types && !types.includes(link.edge_type)) {
      return false;
    }
    
    if (link.weight < minWeight) {
      return false;
    }
    
    return true;
  });
}

/**
 * Search nodes with fuzzy matching
 */
async function searchNodes(payload: {
  nodes: GraphNode[];
  query: string;
  fields?: string[];
  fuzzy?: boolean;
}): Promise<Array<{ node: GraphNode; score: number }>> {
  const { nodes, query, fields = ['label', 'summary'], fuzzy = true } = payload;
  const results: Array<{ node: GraphNode; score: number }> = [];
  const queryLower = query.toLowerCase();
  
  for (const node of nodes) {
    if (shouldCancel()) break;
    
    let score = 0;
    
    for (const field of fields) {
      const value = (node as any)[field];
      if (typeof value === 'string') {
        const valueLower = value.toLowerCase();
        
        if (valueLower === queryLower) {
          score += 10; // Exact match
        } else if (valueLower.includes(queryLower)) {
          score += 5; // Contains
        } else if (fuzzy) {
          // Simple fuzzy matching
          const similarity = calculateSimilarity(queryLower, valueLower);
          score += similarity * 3;
        }
      }
    }
    
    if (score > 0) {
      results.push({ node, score });
    }
  }
  
  // Sort by score
  results.sort((a, b) => b.score - a.score);
  
  return results;
}

/**
 * Find shortest paths between nodes
 */
async function findPaths(payload: {
  nodes: GraphNode[];
  links: GraphLink[];
  source: string;
  target: string;
  maxPaths?: number;
}): Promise<string[][]> {
  const { nodes, links, source, target, maxPaths = 1 } = payload;
  
  // Build adjacency list
  const adjacency = new Map<string, string[]>();
  for (const node of nodes) {
    adjacency.set(node.id, []);
  }
  for (const link of links) {
    adjacency.get(link.source)?.push(link.target);
    adjacency.get(link.target)?.push(link.source);
  }
  
  // BFS for shortest path
  const queue: Array<{ node: string; path: string[] }> = [
    { node: source, path: [source] }
  ];
  const visited = new Set<string>();
  const paths: string[][] = [];
  
  while (queue.length > 0 && paths.length < maxPaths) {
    if (shouldCancel()) break;
    
    const { node, path } = queue.shift()!;
    
    if (node === target) {
      paths.push(path);
      continue;
    }
    
    if (visited.has(node)) continue;
    visited.add(node);
    
    const neighbors = adjacency.get(node) || [];
    for (const neighbor of neighbors) {
      if (!path.includes(neighbor)) {
        queue.push({
          node: neighbor,
          path: [...path, neighbor]
        });
      }
    }
  }
  
  return paths;
}

/**
 * Transform raw data to graph format
 */
async function transformData(payload: {
  raw: any[];
  nodeMapping?: Record<string, string>;
  linkMapping?: Record<string, string>;
}): Promise<{ nodes: GraphNode[]; links: GraphLink[] }> {
  const { raw, nodeMapping = {}, linkMapping = {} } = payload;
  const nodes: GraphNode[] = [];
  const links: GraphLink[] = [];
  
  // Transform based on data structure
  for (const item of raw) {
    if (shouldCancel()) break;
    
    // Detect if it's a node or link
    if ('source' in item && 'target' in item) {
      // It's a link
      links.push({
        source: item[linkMapping.source || 'source'],
        target: item[linkMapping.target || 'target'],
        from: item[linkMapping.source || 'source'],
        to: item[linkMapping.target || 'target'],
        weight: item[linkMapping.weight || 'weight'] || 1,
        edge_type: item[linkMapping.type || 'type'] || 'RELATED_TO'
      });
    } else if ('id' in item) {
      // It's a node
      nodes.push({
        id: item[nodeMapping.id || 'id'],
        label: item[nodeMapping.label || 'label'] || item.id,
        node_type: item[nodeMapping.type || 'type'] || 'Unknown',
        created_at: item.created_at || new Date().toISOString(),
        updated_at: item.updated_at || new Date().toISOString(),
        properties: item.properties || {},
        summary: item.summary || '',
        name: item.name || item.label || item.id
      });
    }
  }
  
  return { nodes, links };
}

/**
 * Merge delta updates into existing data
 */
async function mergeDeltas(payload: {
  current: { nodes: GraphNode[]; links: GraphLink[] };
  deltas: Array<{
    type: 'add' | 'update' | 'remove';
    entity: 'node' | 'link';
    data: any;
  }>;
}): Promise<{ nodes: GraphNode[]; links: GraphLink[] }> {
  const { current, deltas } = payload;
  let nodes = [...current.nodes];
  let links = [...current.links];
  
  for (const delta of deltas) {
    if (shouldCancel()) break;
    
    if (delta.entity === 'node') {
      switch (delta.type) {
        case 'add':
          nodes.push(delta.data);
          break;
        case 'update':
          const nodeIndex = nodes.findIndex(n => n.id === delta.data.id);
          if (nodeIndex >= 0) {
            nodes[nodeIndex] = { ...nodes[nodeIndex], ...delta.data };
          }
          break;
        case 'remove':
          nodes = nodes.filter(n => n.id !== delta.data.id);
          // Also remove connected links
          links = links.filter(l => 
            l.source !== delta.data.id && l.target !== delta.data.id
          );
          break;
      }
    } else if (delta.entity === 'link') {
      switch (delta.type) {
        case 'add':
          links.push(delta.data);
          break;
        case 'remove':
          links = links.filter(l => 
            !(l.source === delta.data.source && l.target === delta.data.target)
          );
          break;
      }
    }
  }
  
  return { nodes, links };
}

/**
 * Validate graph data integrity
 */
async function validateData(payload: {
  nodes: GraphNode[];
  links: GraphLink[];
}): Promise<{
  valid: boolean;
  errors: string[];
  warnings: string[];
}> {
  const { nodes, links } = payload;
  const errors: string[] = [];
  const warnings: string[] = [];
  
  // Check for duplicate node IDs
  const nodeIds = new Set<string>();
  for (const node of nodes) {
    if (nodeIds.has(node.id)) {
      errors.push(`Duplicate node ID: ${node.id}`);
    }
    nodeIds.add(node.id);
    
    // Validate required fields
    if (!node.label) {
      warnings.push(`Node ${node.id} missing label`);
    }
  }
  
  // Validate links
  for (const link of links) {
    if (!nodeIds.has(link.source)) {
      errors.push(`Link source not found: ${link.source}`);
    }
    if (!nodeIds.has(link.target)) {
      errors.push(`Link target not found: ${link.target}`);
    }
    if (link.weight < 0) {
      warnings.push(`Negative link weight: ${link.source} -> ${link.target}`);
    }
  }
  
  return {
    valid: errors.length === 0,
    errors,
    warnings
  };
}

/**
 * Calculate graph statistics
 */
async function calculateStats(payload: {
  nodes: GraphNode[];
  links: GraphLink[];
}): Promise<any> {
  const { nodes, links } = payload;
  
  // Node type distribution
  const nodeTypes = new Map<string, number>();
  for (const node of nodes) {
    const type = node.node_type;
    nodeTypes.set(type, (nodeTypes.get(type) || 0) + 1);
  }
  
  // Link type distribution
  const linkTypes = new Map<string, number>();
  for (const link of links) {
    const type = link.edge_type;
    linkTypes.set(type, (linkTypes.get(type) || 0) + 1);
  }
  
  // Degree distribution
  const degrees = new Map<string, number>();
  for (const node of nodes) {
    degrees.set(node.id, 0);
  }
  for (const link of links) {
    degrees.set(link.source, (degrees.get(link.source) || 0) + 1);
    degrees.set(link.target, (degrees.get(link.target) || 0) + 1);
  }
  
  const degreeValues = Array.from(degrees.values());
  const avgDegree = degreeValues.reduce((a, b) => a + b, 0) / degreeValues.length;
  const maxDegree = Math.max(...degreeValues);
  const minDegree = Math.min(...degreeValues);
  
  // Graph density
  const maxPossibleLinks = nodes.length * (nodes.length - 1) / 2;
  const density = links.length / maxPossibleLinks;
  
  return {
    nodeCount: nodes.length,
    linkCount: links.length,
    nodeTypes: Object.fromEntries(nodeTypes),
    linkTypes: Object.fromEntries(linkTypes),
    density,
    degree: {
      average: avgDegree,
      max: maxDegree,
      min: minDegree
    }
  };
}

/**
 * Detect communities using simple algorithm
 */
async function detectCommunities(payload: {
  nodes: GraphNode[];
  links: GraphLink[];
  algorithm?: 'louvain' | 'label-propagation';
}): Promise<Map<string, number>> {
  // Simplified community detection
  return calculateClusters(payload);
}

/**
 * Analyze a subgraph around specific nodes
 */
async function analyzeSubgraph(payload: {
  nodes: GraphNode[];
  links: GraphLink[];
  centerNodes: string[];
  depth?: number;
}): Promise<{
  nodes: GraphNode[];
  links: GraphLink[];
  stats: any;
}> {
  const { nodes, links, centerNodes, depth = 1 } = payload;
  
  // Find nodes within depth
  const includedNodes = new Set<string>(centerNodes);
  
  for (let d = 0; d < depth; d++) {
    const currentNodes = Array.from(includedNodes);
    
    for (const nodeId of currentNodes) {
      for (const link of links) {
        if (link.source === nodeId) {
          includedNodes.add(link.target);
        } else if (link.target === nodeId) {
          includedNodes.add(link.source);
        }
      }
    }
  }
  
  // Filter nodes and links
  const subgraphNodes = nodes.filter(n => includedNodes.has(n.id));
  const subgraphLinks = links.filter(l => 
    includedNodes.has(l.source) && includedNodes.has(l.target)
  );
  
  // Calculate stats for subgraph
  const stats = await calculateStats({ nodes: subgraphNodes, links: subgraphLinks });
  
  return {
    nodes: subgraphNodes,
    links: subgraphLinks,
    stats
  };
}

/**
 * Simple string similarity calculation
 */
function calculateSimilarity(str1: string, str2: string): number {
  const longer = str1.length > str2.length ? str1 : str2;
  const shorter = str1.length > str2.length ? str2 : str1;
  
  if (longer.length === 0) return 1.0;
  
  const editDistance = levenshteinDistance(longer, shorter);
  return (longer.length - editDistance) / longer.length;
}

/**
 * Levenshtein distance for fuzzy matching
 */
function levenshteinDistance(str1: string, str2: string): number {
  const matrix: number[][] = [];
  
  for (let i = 0; i <= str2.length; i++) {
    matrix[i] = [i];
  }
  
  for (let j = 0; j <= str1.length; j++) {
    matrix[0][j] = j;
  }
  
  for (let i = 1; i <= str2.length; i++) {
    for (let j = 1; j <= str1.length; j++) {
      if (str2.charAt(i - 1) === str1.charAt(j - 1)) {
        matrix[i][j] = matrix[i - 1][j - 1];
      } else {
        matrix[i][j] = Math.min(
          matrix[i - 1][j - 1] + 1,
          matrix[i][j - 1] + 1,
          matrix[i - 1][j] + 1
        );
      }
    }
  }
  
  return matrix[str2.length][str1.length];
}