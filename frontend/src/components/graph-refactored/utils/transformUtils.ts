/**
 * Data transformation utilities for graph operations
 */

import { GraphNode } from '../../../api/types';
import { GraphLink } from '../../../types/graph';

// Transform raw node data to GraphNode
export function transformNode(rawNode: any): GraphNode {
  return {
    id: String(rawNode.id || rawNode.uuid || ''),
    label: rawNode.label || rawNode.name || rawNode.id || '',
    node_type: rawNode.node_type || rawNode.type || 'Unknown',
    created_at: rawNode.created_at || new Date().toISOString(),
    updated_at: rawNode.updated_at || new Date().toISOString(),
    properties: rawNode.properties || {},
    summary: rawNode.summary || '',
    name: rawNode.name || rawNode.label || rawNode.id || ''
  };
}

// Transform raw link data to GraphLink
export function transformLink(rawLink: any): GraphLink {
  return {
    source: String(rawLink.source || rawLink.from || ''),
    target: String(rawLink.target || rawLink.to || ''),
    from: String(rawLink.from || rawLink.source || ''),
    to: String(rawLink.to || rawLink.target || ''),
    weight: rawLink.weight || rawLink.strength || 1,
    edge_type: rawLink.edge_type || rawLink.type || 'RELATED_TO'
  };
}

// Batch transform nodes
export function transformNodes(rawNodes: any[]): GraphNode[] {
  return rawNodes.map(transformNode);
}

// Batch transform links
export function transformLinks(rawLinks: any[]): GraphLink[] {
  return rawLinks.map(transformLink);
}

// Filter nodes by type
export function filterNodesByType(nodes: GraphNode[], types: string[]): GraphNode[] {
  const typeSet = new Set(types);
  return nodes.filter(node => typeSet.has(node.node_type));
}

// Filter links by type
export function filterLinksByType(links: GraphLink[], types: string[]): GraphLink[] {
  const typeSet = new Set(types);
  return links.filter(link => typeSet.has(link.edge_type));
}

// Get node neighbors
export function getNodeNeighbors(
  nodeId: string,
  links: GraphLink[],
  nodes: GraphNode[]
): GraphNode[] {
  const neighborIds = new Set<string>();
  
  links.forEach(link => {
    if (link.source === nodeId) {
      neighborIds.add(link.target);
    } else if (link.target === nodeId) {
      neighborIds.add(link.source);
    }
  });
  
  return nodes.filter(node => neighborIds.has(node.id));
}

// Get subgraph around node
export function getSubgraph(
  centerNodeId: string,
  nodes: GraphNode[],
  links: GraphLink[],
  depth: number = 1
): { nodes: GraphNode[]; links: GraphLink[] } {
  const includedNodeIds = new Set<string>([centerNodeId]);
  const includedLinks: GraphLink[] = [];
  
  for (let d = 0; d < depth; d++) {
    const currentNodes = Array.from(includedNodeIds);
    
    currentNodes.forEach(nodeId => {
      links.forEach(link => {
        if (link.source === nodeId) {
          includedNodeIds.add(link.target);
          if (!includedLinks.includes(link)) {
            includedLinks.push(link);
          }
        } else if (link.target === nodeId) {
          includedNodeIds.add(link.source);
          if (!includedLinks.includes(link)) {
            includedLinks.push(link);
          }
        }
      });
    });
  }
  
  const includedNodes = nodes.filter(node => includedNodeIds.has(node.id));
  
  return {
    nodes: includedNodes,
    links: includedLinks
  };
}

// Calculate node degree
export function calculateNodeDegree(
  nodeId: string,
  links: GraphLink[]
): { in: number; out: number; total: number } {
  let inDegree = 0;
  let outDegree = 0;
  
  links.forEach(link => {
    if (link.target === nodeId) inDegree++;
    if (link.source === nodeId) outDegree++;
  });
  
  return {
    in: inDegree,
    out: outDegree,
    total: inDegree + outDegree
  };
}

// Calculate graph density
export function calculateGraphDensity(
  nodeCount: number,
  linkCount: number,
  directed: boolean = false
): number {
  if (nodeCount <= 1) return 0;
  
  const maxPossibleLinks = directed
    ? nodeCount * (nodeCount - 1)
    : (nodeCount * (nodeCount - 1)) / 2;
  
  return linkCount / maxPossibleLinks;
}

// Group nodes by type
export function groupNodesByType(nodes: GraphNode[]): Map<string, GraphNode[]> {
  const groups = new Map<string, GraphNode[]>();
  
  nodes.forEach(node => {
    const type = node.node_type;
    if (!groups.has(type)) {
      groups.set(type, []);
    }
    groups.get(type)!.push(node);
  });
  
  return groups;
}

// Deduplicate nodes by ID
export function deduplicateNodes(nodes: GraphNode[]): GraphNode[] {
  const seen = new Set<string>();
  return nodes.filter(node => {
    if (seen.has(node.id)) {
      return false;
    }
    seen.add(node.id);
    return true;
  });
}

// Deduplicate links
export function deduplicateLinks(links: GraphLink[]): GraphLink[] {
  const seen = new Set<string>();
  return links.filter(link => {
    const key = `${link.source}-${link.target}`;
    if (seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}

// Merge graph data (for delta updates)
export function mergeGraphData(
  current: { nodes: GraphNode[]; links: GraphLink[] },
  updates: { 
    nodesAdded?: GraphNode[];
    nodesUpdated?: GraphNode[];
    nodesRemoved?: string[];
    linksAdded?: GraphLink[];
    linksRemoved?: string[];
  }
): { nodes: GraphNode[]; links: GraphLink[] } {
  // Start with current data
  let nodes = [...current.nodes];
  let links = [...current.links];
  
  // Remove nodes
  if (updates.nodesRemoved?.length) {
    const removedSet = new Set(updates.nodesRemoved);
    nodes = nodes.filter(n => !removedSet.has(n.id));
    // Also remove connected links
    links = links.filter(l => 
      !removedSet.has(l.source) && !removedSet.has(l.target)
    );
  }
  
  // Update nodes
  if (updates.nodesUpdated?.length) {
    const updateMap = new Map(updates.nodesUpdated.map(n => [n.id, n]));
    nodes = nodes.map(n => updateMap.get(n.id) || n);
  }
  
  // Add nodes
  if (updates.nodesAdded?.length) {
    const existingIds = new Set(nodes.map(n => n.id));
    const newNodes = updates.nodesAdded.filter(n => !existingIds.has(n.id));
    nodes = [...nodes, ...newNodes];
  }
  
  // Remove links
  if (updates.linksRemoved?.length) {
    const removedSet = new Set(updates.linksRemoved);
    links = links.filter(l => {
      const key = `${l.source}-${l.target}`;
      return !removedSet.has(key);
    });
  }
  
  // Add links
  if (updates.linksAdded?.length) {
    const existingKeys = new Set(links.map(l => `${l.source}-${l.target}`));
    const newLinks = updates.linksAdded.filter(l => {
      const key = `${l.source}-${l.target}`;
      return !existingKeys.has(key);
    });
    links = [...links, ...newLinks];
  }
  
  return {
    nodes: deduplicateNodes(nodes),
    links: deduplicateLinks(links)
  };
}