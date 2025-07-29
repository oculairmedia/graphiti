import type { GraphNode, GraphEdge } from '../../types/graph';
import { LayoutPosition, LayoutOptions, DEFAULT_CANVAS_WIDTH, DEFAULT_CANVAS_HEIGHT } from './types';

/**
 * Build hierarchy levels using BFS from root
 */
function buildHierarchyLevels(
  nodes: GraphNode[],
  edges: GraphEdge[],
  rootId: string
): GraphNode[][] {
  const adjacencyList: Record<string, string[]> = {};
  const visited = new Set<string>();
  const levels: GraphNode[][] = [];
  
  // Build adjacency list (directed)
  nodes.forEach(node => {
    adjacencyList[node.id] = [];
  });
  
  edges.forEach(edge => {
    adjacencyList[edge.from]?.push(edge.to);
  });
  
  // BFS to build levels
  const queue: { node: GraphNode, level: number }[] = [];
  const nodeMap = new Map(nodes.map(node => [node.id, node]));
  const rootNode = nodeMap.get(rootId);
  
  if (rootNode) {
    queue.push({ node: rootNode, level: 0 });
    visited.add(rootId);
  }
  
  while (queue.length > 0) {
    const { node, level } = queue.shift()!;
    
    if (!levels[level]) {
      levels[level] = [];
    }
    levels[level].push(node);
    
    adjacencyList[node.id]?.forEach(childId => {
      if (!visited.has(childId)) {
        const childNode = nodeMap.get(childId);
        if (childNode) {
          visited.add(childId);
          queue.push({ node: childNode, level: level + 1 });
        }
      }
    });
  }
  
  // Handle disconnected nodes
  nodes.forEach(node => {
    if (!visited.has(node.id)) {
      if (!levels[0]) levels[0] = [];
      levels[0].push(node);
    }
  });
  
  return levels.filter(level => level.length > 0);
}

/**
 * Calculate positions for hierarchical layout
 * Creates tree-like structure with clear levels
 */
export function calculateHierarchicalLayout(
  nodes: GraphNode[],
  edges: GraphEdge[],
  options: LayoutOptions = {}
): LayoutPosition[] {
  const { 
    hierarchyDirection = 'top-down', 
    canvasWidth = DEFAULT_CANVAS_WIDTH, 
    canvasHeight = DEFAULT_CANVAS_HEIGHT 
  } = options;
  
  if (nodes.length === 0) return [];
  if (nodes.length === 1) return [{ x: canvasWidth / 2, y: canvasHeight / 2 }];
  
  // Find root nodes (nodes with high centrality and few incoming edges)
  const incomingEdges = new Map<string, number>();
  edges.forEach(edge => {
    incomingEdges.set(edge.to, (incomingEdges.get(edge.to) || 0) + 1);
  });
  
  const rootCandidates = nodes
    .filter(node => (incomingEdges.get(node.id) || 0) <= 1)
    .sort((a, b) => {
      const centralityA = a.properties?.degree_centrality || 0;
      const centralityB = b.properties?.degree_centrality || 0;
      return centralityB - centralityA;
    });
  
  const rootNode = rootCandidates[0] || nodes[0];
  
  // Build tree structure using BFS
  const levels = buildHierarchyLevels(nodes, edges, rootNode.id);
  const maxLevel = levels.length - 1;
  
  const positions: LayoutPosition[] = new Array(nodes.length);
  const nodeIndexMap = new Map(nodes.map((node, index) => [node.id, index]));
  
  levels.forEach((levelNodes, level) => {
    const levelCount = levelNodes.length;
    
    levelNodes.forEach((node, indexInLevel) => {
      let x, y;
      
      switch (hierarchyDirection) {
        case 'top-down':
          x = levelCount > 1 ? (indexInLevel / (levelCount - 1)) * canvasWidth * 0.8 + canvasWidth * 0.1 : canvasWidth / 2;
          y = (level / maxLevel) * canvasHeight * 0.8 + canvasHeight * 0.1;
          break;
        case 'bottom-up':
          x = levelCount > 1 ? (indexInLevel / (levelCount - 1)) * canvasWidth * 0.8 + canvasWidth * 0.1 : canvasWidth / 2;
          y = ((maxLevel - level) / maxLevel) * canvasHeight * 0.8 + canvasHeight * 0.1;
          break;
        case 'left-right':
          x = (level / maxLevel) * canvasWidth * 0.8 + canvasWidth * 0.1;
          y = levelCount > 1 ? (indexInLevel / (levelCount - 1)) * canvasHeight * 0.8 + canvasHeight * 0.1 : canvasHeight / 2;
          break;
        case 'right-left':
          x = ((maxLevel - level) / maxLevel) * canvasWidth * 0.8 + canvasWidth * 0.1;
          y = levelCount > 1 ? (indexInLevel / (levelCount - 1)) * canvasHeight * 0.8 + canvasHeight * 0.1 : canvasHeight / 2;
          break;
      }
      
      const originalIndex = nodeIndexMap.get(node.id) || 0;
      positions[originalIndex] = { x, y };
    });
  });
  
  return positions;
}