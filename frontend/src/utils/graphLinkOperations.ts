/**
 * Graph Link Operations Utility Module
 * Pure functions for link manipulation and transformation
 */

import { GraphLink } from '../types/graph';

/**
 * Transform raw link for Cosmograph
 */
export function transformLinkForCosmograph(link: GraphLink, nodeIndexMap: Map<string, number>) {
  const sourceIndex = nodeIndexMap.get(String(link.source || link.from));
  const targetIndex = nodeIndexMap.get(String(link.target || link.to));
  
  return {
    source: String(link.source || link.from),
    sourceIndex: sourceIndex !== undefined ? sourceIndex : -1,
    target: String(link.target || link.to),
    targetIndex: targetIndex !== undefined ? targetIndex : -1,
    edge_type: String(link.edge_type || link.name || 'default'),
    weight: Number(link.weight || 1),
    created_at: link.created_at,
    updated_at: link.updated_at
  };
}

/**
 * Batch transform links for Cosmograph
 */
export function transformLinksForCosmograph(links: GraphLink[], nodeIndexMap: Map<string, number>): any[] {
  if (!links || links.length === 0) return [];
  
  return links.map(link => transformLinkForCosmograph(link, nodeIndexMap))
    .filter(link => link.sourceIndex !== -1 && link.targetIndex !== -1);
}

/**
 * Filter out invalid links (missing nodes)
 */
export function filterValidLinks(links: any[], nodeIds: Set<string>): any[] {
  return links.filter(link => {
    const source = String(link.source || link.from);
    const target = String(link.target || link.to);
    return nodeIds.has(source) && nodeIds.has(target);
  });
}

/**
 * Create link key for deduplication
 */
export function createLinkKey(link: GraphLink): string {
  const source = String(link.source || link.from);
  const target = String(link.target || link.to);
  return `${source}-${target}`;
}

/**
 * Create bidirectional link key (order-independent)
 */
export function createBidirectionalLinkKey(link: GraphLink): string {
  const source = String(link.source || link.from);
  const target = String(link.target || link.to);
  return source < target ? `${source}-${target}` : `${target}-${source}`;
}

/**
 * Deduplicate links (keep latest)
 */
export function deduplicateLinks(links: GraphLink[]): GraphLink[] {
  const linkMap = new Map<string, GraphLink>();
  
  links.forEach(link => {
    const key = createLinkKey(link);
    linkMap.set(key, link);
  });
  
  return Array.from(linkMap.values());
}

/**
 * Get links for a specific node
 */
export function getLinksForNode(links: GraphLink[], nodeId: string): {
  incoming: GraphLink[],
  outgoing: GraphLink[]
} {
  const incoming: GraphLink[] = [];
  const outgoing: GraphLink[] = [];
  
  links.forEach(link => {
    const source = String(link.source || link.from);
    const target = String(link.target || link.to);
    
    if (source === nodeId) {
      outgoing.push(link);
    }
    if (target === nodeId) {
      incoming.push(link);
    }
  });
  
  return { incoming, outgoing };
}

/**
 * Get all connected node IDs for a given node
 */
export function getConnectedNodeIds(links: GraphLink[], nodeId: string): Set<string> {
  const connected = new Set<string>();
  
  links.forEach(link => {
    const source = String(link.source || link.from);
    const target = String(link.target || link.to);
    
    if (source === nodeId) {
      connected.add(target);
    }
    if (target === nodeId) {
      connected.add(source);
    }
  });
  
  return connected;
}

/**
 * Find links between specific nodes
 */
export function findLinksBetweenNodes(links: GraphLink[], nodeIds: string[]): GraphLink[] {
  const nodeSet = new Set(nodeIds);
  
  return links.filter(link => {
    const source = String(link.source || link.from);
    const target = String(link.target || link.to);
    return nodeSet.has(source) && nodeSet.has(target);
  });
}

/**
 * Update link in array (immutable)
 */
export function updateLinkInArray(links: GraphLink[], updatedLink: GraphLink): GraphLink[] {
  const key = createLinkKey(updatedLink);
  
  return links.map(link => 
    createLinkKey(link) === key ? { ...link, ...updatedLink } : link
  );
}

/**
 * Update multiple links in array (immutable)
 */
export function updateLinksInArray(links: GraphLink[], updatedLinks: GraphLink[]): GraphLink[] {
  const updateMap = new Map(updatedLinks.map(l => [createLinkKey(l), l]));
  
  return links.map(link => {
    const key = createLinkKey(link);
    const update = updateMap.get(key);
    return update ? { ...link, ...update } : link;
  });
}

/**
 * Remove links from array (immutable)
 */
export function removeLinksFromArray(links: GraphLink[], linksToRemove: GraphLink[]): GraphLink[] {
  const removeKeys = new Set(linksToRemove.map(l => createLinkKey(l)));
  return links.filter(link => !removeKeys.has(createLinkKey(link)));
}

/**
 * Remove links by node IDs
 */
export function removeLinksByNodeIds(links: GraphLink[], nodeIdsToRemove: string[]): GraphLink[] {
  const removeSet = new Set(nodeIdsToRemove);
  
  return links.filter(link => {
    const source = String(link.source || link.from);
    const target = String(link.target || link.to);
    return !removeSet.has(source) && !removeSet.has(target);
  });
}

/**
 * Add links to array (immutable, with deduplication)
 */
export function addLinksToArray(links: GraphLink[], newLinks: GraphLink[]): GraphLink[] {
  const linkMap = new Map<string, GraphLink>();
  
  // Add existing links
  links.forEach(link => linkMap.set(createLinkKey(link), link));
  
  // Add/override with new links
  newLinks.forEach(link => linkMap.set(createLinkKey(link), link));
  
  return Array.from(linkMap.values());
}

/**
 * Merge link arrays (newer links override older)
 */
export function mergeLinkArrays(existingLinks: GraphLink[], newLinks: GraphLink[]): GraphLink[] {
  return addLinksToArray(existingLinks, newLinks);
}

/**
 * Calculate link statistics
 */
export function calculateLinkStats(links: GraphLink[]) {
  const stats = {
    total: links.length,
    byType: new Map<string, number>(),
    avgWeight: 0,
    maxWeight: 0,
    minWeight: Infinity,
    withTimestamps: 0,
    uniqueTypes: 0,
    selfLoops: 0
  };
  
  let totalWeight = 0;
  
  links.forEach(link => {
    // Count by type
    const type = link.edge_type || link.name || 'default';
    stats.byType.set(type, (stats.byType.get(type) || 0) + 1);
    
    // Calculate weight stats
    const weight = Number(link.weight || 1);
    totalWeight += weight;
    stats.maxWeight = Math.max(stats.maxWeight, weight);
    stats.minWeight = Math.min(stats.minWeight, weight);
    
    // Count links with timestamps
    if (link.created_at || link.updated_at) {
      stats.withTimestamps++;
    }
    
    // Count self-loops
    const source = String(link.source || link.from);
    const target = String(link.target || link.to);
    if (source === target) {
      stats.selfLoops++;
    }
  });
  
  stats.avgWeight = links.length > 0 ? totalWeight / links.length : 0;
  stats.uniqueTypes = stats.byType.size;
  
  if (links.length === 0) {
    stats.minWeight = 0;
  }
  
  return stats;
}

/**
 * Sort links by weight
 */
export function sortLinksByWeight(links: GraphLink[], descending: boolean = true): GraphLink[] {
  return [...links].sort((a, b) => {
    const aWeight = Number(a.weight || 1);
    const bWeight = Number(b.weight || 1);
    return descending ? bWeight - aWeight : aWeight - bWeight;
  });
}

/**
 * Get top N links by weight
 */
export function getTopLinksByWeight(links: GraphLink[], n: number): GraphLink[] {
  return sortLinksByWeight(links, true).slice(0, n);
}

/**
 * Find links within time range
 */
export function findLinksInTimeRange(links: GraphLink[], startTime: number, endTime: number): GraphLink[] {
  return links.filter(link => {
    const createdAt = link.created_at ? new Date(link.created_at).getTime() : null;
    const updatedAt = link.updated_at ? new Date(link.updated_at).getTime() : null;
    
    const timestamp = updatedAt || createdAt;
    if (!timestamp) return false;
    
    return timestamp >= startTime && timestamp <= endTime;
  });
}

/**
 * Group links by property
 */
export function groupLinksByProperty(links: GraphLink[], property: string): Map<any, GraphLink[]> {
  const groups = new Map<any, GraphLink[]>();
  
  links.forEach(link => {
    const value = (link as any)[property] || 'Unknown';
    if (!groups.has(value)) {
      groups.set(value, []);
    }
    groups.get(value)!.push(link);
  });
  
  return groups;
}

/**
 * Create adjacency list from links
 */
export function createAdjacencyList(links: GraphLink[]): Map<string, Set<string>> {
  const adjacencyList = new Map<string, Set<string>>();
  
  links.forEach(link => {
    const source = String(link.source || link.from);
    const target = String(link.target || link.to);
    
    if (!adjacencyList.has(source)) {
      adjacencyList.set(source, new Set());
    }
    adjacencyList.get(source)!.add(target);
    
    // For undirected graphs, add reverse edge
    // Comment out if graph is directed
    // if (!adjacencyList.has(target)) {
    //   adjacencyList.set(target, new Set());
    // }
    // adjacencyList.get(target)!.add(source);
  });
  
  return adjacencyList;
}

/**
 * Validate link data
 */
export function validateLink(link: any): boolean {
  const source = link?.source || link?.from;
  const target = link?.target || link?.to;
  
  return !!(
    link &&
    source &&
    target &&
    source !== 'undefined' &&
    target !== 'undefined' &&
    source !== 'null' &&
    target !== 'null' &&
    typeof source === 'string' &&
    typeof target === 'string'
  );
}

/**
 * Batch validate links
 */
export function validateLinks(links: any[]): { valid: any[], invalid: any[] } {
  const valid: any[] = [];
  const invalid: any[] = [];
  
  links.forEach(link => {
    if (validateLink(link)) {
      valid.push(link);
    } else {
      invalid.push(link);
    }
  });
  
  return { valid, invalid };
}

/**
 * Convert links to edge list format
 */
export function linksToEdgeList(links: GraphLink[]): Array<[string, string, number]> {
  return links.map(link => [
    String(link.source || link.from),
    String(link.target || link.to),
    Number(link.weight || 1)
  ]);
}

/**
 * Find strongly connected components (for directed graphs)
 * Uses Tarjan's algorithm
 */
export function findStronglyConnectedComponents(links: GraphLink[]): Map<string, number> {
  const adjacencyList = createAdjacencyList(links);
  const nodeIds = new Set<string>();
  
  // Collect all node IDs
  links.forEach(link => {
    nodeIds.add(String(link.source || link.from));
    nodeIds.add(String(link.target || link.to));
  });
  
  // Tarjan's algorithm implementation would go here
  // For now, return a simple placeholder
  const componentMap = new Map<string, number>();
  let componentId = 0;
  
  nodeIds.forEach(nodeId => {
    componentMap.set(nodeId, componentId++);
  });
  
  return componentMap;
}