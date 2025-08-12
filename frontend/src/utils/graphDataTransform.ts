import type { GraphNode, GraphEdge } from '../types/graph';
import { logger } from './logger';

export interface TransformedNode {
  id: string;
  index: number;
  label: string;
  node_type: string;
  summary?: string;
  created_at: string | null;
  created_at_timestamp: number | null;
  // Centrality metrics
  degree_centrality?: number;
  betweenness_centrality?: number;
  pagerank_centrality?: number;
  eigenvector_centrality?: number;
}

export interface TransformedLink {
  source: string;
  sourceIndex: number;
  target: string;
  targetIndex: number;
  edge_type: string;
  weight: number;
  created_at?: string;
  updated_at?: string;
}

/**
 * Transform nodes for Cosmograph v2.0
 * Creates properly indexed nodes with centrality metrics
 */
export function transformNodes(nodes: GraphNode[]): TransformedNode[] {
  return nodes.map((node, index) => {
    const createdAt = node.properties?.created_at || node.created_at || node.properties?.created || null;
    
    // Generate a fallback timestamp for nodes without dates (for timeline functionality)
    // Distribute randomly over the last 90 days
    const timestamp = createdAt 
      ? new Date(createdAt).getTime() 
      : Date.now() - Math.random() * 90 * 24 * 60 * 60 * 1000;
    
    const nodeData: TransformedNode = {
      id: String(node.id),
      index: index,
      label: String(node.label || node.id),
      node_type: String(node.node_type || 'Unknown'),
      summary: node.summary || node.properties?.summary,
      created_at: createdAt,
      created_at_timestamp: timestamp,
      // Include centrality metrics from properties
      degree_centrality: node.properties?.degree_centrality,
      betweenness_centrality: node.properties?.betweenness_centrality,
      pagerank_centrality: node.properties?.pagerank_centrality || node.properties?.pagerank,
      eigenvector_centrality: node.properties?.eigenvector_centrality
    };
    
    if (!nodeData.id || nodeData.id === 'undefined') {
      logger.warn('Invalid node ID found:', node);
    }
    
    return nodeData;
  }).filter(node => node.id && node.id !== 'undefined');
}

/**
 * Transform links for Cosmograph v2.0
 * Creates properly indexed links with source/target indices
 */
export function transformLinks(links: GraphEdge[], nodes: TransformedNode[]): TransformedLink[] {
  // Create node index map for quick lookup
  const nodeIndexMap = new Map<string, number>();
  nodes.forEach((node) => {
    nodeIndexMap.set(node.id, node.index);
  });
  
  logger.log('graphDataTransform: Processing links:', links.length, 'nodes in map:', nodeIndexMap.size);
  
  // Debug: Log first few node IDs and link source/targets
  if (nodes.length > 0) {
    logger.log('Sample node IDs:', nodes.slice(0, 3).map(n => n.id));
  }
  if (links.length > 0) {
    logger.log('Sample link sources:', links.slice(0, 3).map(l => l.source));
    logger.log('Sample link targets:', links.slice(0, 3).map(l => l.target));
    logger.log('Sample link data:', links.slice(0, 2).map(l => ({ 
      source: l.source, 
      target: l.target, 
      sourceIndex: l.sourceIndex,
      targetIndex: l.targetIndex,
      edge_type: l.edge_type 
    })));
  }
  
  const transformedLinks = links.map(link => {
    const sourceIndex = nodeIndexMap.get(String(link.source));
    const targetIndex = nodeIndexMap.get(String(link.target));
    
    const linkData: TransformedLink = {
      source: String(link.source),
      sourceIndex: sourceIndex !== undefined ? sourceIndex : -1,
      target: String(link.target),
      targetIndex: targetIndex !== undefined ? targetIndex : -1,
      edge_type: String(link.edge_type || 'default'),
      weight: Number(link.weight || 1),
      created_at: link.created_at,
      updated_at: link.updated_at
    };
    
    if (!linkData.source || !linkData.target || 
        linkData.source === 'undefined' || linkData.target === 'undefined' || 
        linkData.sourceIndex === -1 || linkData.targetIndex === -1) {
      logger.warn('Invalid link found:', link, 'indices:', linkData.sourceIndex, linkData.targetIndex);
    }
    
    return linkData;
  }).filter(link => {
    const isValid = link.source && link.target && 
      link.source !== 'undefined' && link.target !== 'undefined' && 
      link.sourceIndex !== -1 && link.targetIndex !== -1;
    
    if (!isValid) {
      logger.warn('Filtered out invalid link:', {
        source: link.source,
        target: link.target,
        sourceIndex: link.sourceIndex,
        targetIndex: link.targetIndex
      });
    }
    
    return isValid;
  });
  
  const filteredCount = links.length - transformedLinks.length;
  logger.log(`Link transformation complete: ${transformedLinks.length} valid links out of ${links.length} total links`);
  if (filteredCount > 0) {
    logger.warn(`Filtered out ${filteredCount} invalid links`);
  }
  
  return transformedLinks;
}

/**
 * Transform data for incremental updates
 * Ensures proper indexing for Cosmograph v2.0
 */
export function transformDataForUpdate(nodes: GraphNode[], links: GraphEdge[]) {
  const transformedNodes = transformNodes(nodes);
  const transformedLinks = transformLinks(links, transformedNodes);
  
  logger.log('graphDataTransform: Transformed data -', 
    'nodes:', transformedNodes.length, 
    'links:', transformedLinks.length
  );
  
  return { nodes: transformedNodes, links: transformedLinks };
}