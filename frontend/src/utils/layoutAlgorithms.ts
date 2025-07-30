// Graph layout algorithms for Graphiti frontend
// Calculates actual node positions for different layout types

import type { GraphNode, GraphEdge } from '../types/graph';

export interface LayoutPosition {
  x: number;
  y: number;
}

export interface LayoutOptions {
  hierarchyDirection?: 'top-down' | 'bottom-up' | 'left-right' | 'right-left';
  radialCenter?: string;
  circularOrdering?: 'degree' | 'centrality' | 'type' | 'alphabetical';
  clusterBy?: 'type' | 'community' | 'centrality' | 'temporal';
  canvasWidth?: number;
  canvasHeight?: number;
}

// Default canvas dimensions for layout calculations
const DEFAULT_CANVAS_WIDTH = 1200;
const DEFAULT_CANVAS_HEIGHT = 800;

/**
 * Calculate positions for circular layout
 * Arranges nodes in a perfect circle with optional ordering
 */
export function calculateCircularLayout(
  nodes: GraphNode[],
  options: LayoutOptions = {}
): LayoutPosition[] {
  const { circularOrdering = 'degree', canvasWidth = DEFAULT_CANVAS_WIDTH, canvasHeight = DEFAULT_CANVAS_HEIGHT } = options;
  
  if (nodes.length === 0) return [];
  if (nodes.length === 1) return [{ x: canvasWidth / 2, y: canvasHeight / 2 }];
  
  // Sort nodes based on ordering criteria
  const sortedNodes = [...nodes].sort((a, b) => {
    switch (circularOrdering) {
      case 'degree': {
        const degreeA = a.properties?.degree_centrality || 0;
        const degreeB = b.properties?.degree_centrality || 0;
        return degreeB - degreeA;
      }
      case 'centrality': {
        const centralityA = a.properties?.pagerank_centrality || 0;
        const centralityB = b.properties?.pagerank_centrality || 0;
        return centralityB - centralityA;
      }
      case 'type': {
        return a.node_type.localeCompare(b.node_type);
      }
      case 'alphabetical': {
        const labelA = a.label || a.id;
        const labelB = b.label || b.id;
        return labelA.localeCompare(labelB);
      }
      default:
        return 0;
    }
  });
  
  const centerX = canvasWidth / 2;
  const centerY = canvasHeight / 2;
  const radius = Math.min(canvasWidth, canvasHeight) * 0.35; // 35% of smaller dimension
  
  const positions: LayoutPosition[] = [];
  // Protect against division by zero
  const angleStep = nodes.length > 0 ? (2 * Math.PI) / nodes.length : 0;
  
  // Create position lookup for original node order
  const nodeIndexMap = new Map(nodes.map((node, index) => [node.id, index]));
  
  sortedNodes.forEach((node, sortedIndex) => {
    const angle = sortedIndex * angleStep - Math.PI / 2; // Start from top
    const x = centerX + radius * Math.cos(angle);
    const y = centerY + radius * Math.sin(angle);
    
    const originalIndex = nodeIndexMap.get(node.id) || 0;
    positions[originalIndex] = { x, y };
  });
  
  return positions;
}

/**
 * Calculate positions for radial layout
 * Places nodes in concentric circles based on distance from center
 */
export function calculateRadialLayout(
  nodes: GraphNode[],
  edges: GraphEdge[],
  options: LayoutOptions = {}
): LayoutPosition[] {
  const { radialCenter, canvasWidth = DEFAULT_CANVAS_WIDTH, canvasHeight = DEFAULT_CANVAS_HEIGHT } = options;
  
  if (nodes.length === 0) return [];
  if (nodes.length === 1) return [{ x: canvasWidth / 2, y: canvasHeight / 2 }];
  
  // Find center node
  let centerNodeId = radialCenter;
  if (!centerNodeId || !nodes.find(n => n.id === centerNodeId)) {
    // Use node with highest degree centrality as center
    centerNodeId = nodes.reduce((max, node) => {
      const degree = node.properties?.degree_centrality || 0;
      const maxDegree = max.properties?.degree_centrality || 0;
      return degree > maxDegree ? node : max;
    }).id;
  }
  
  // Calculate distances from center using BFS
  const distances = calculateDistancesFromCenter(nodes, edges, centerNodeId);
  const maxDistance = Math.max(...Object.values(distances));
  
  // Group nodes by distance
  const levels: GraphNode[][] = [];
  for (let i = 0; i <= maxDistance; i++) {
    levels[i] = [];
  }
  
  nodes.forEach(node => {
    const distance = distances[node.id] || maxDistance;
    levels[distance].push(node);
  });
  
  const centerX = canvasWidth / 2;
  const centerY = canvasHeight / 2;
  const maxRadius = Math.min(canvasWidth, canvasHeight) * 0.4;
  
  const positions: LayoutPosition[] = new Array(nodes.length);
  const nodeIndexMap = new Map(nodes.map((node, index) => [node.id, index]));
  
  levels.forEach((levelNodes, distance) => {
    if (levelNodes.length === 0) return;
    
    const radius = distance === 0 ? 0 : (distance / maxDistance) * maxRadius;
    const angleStep = levelNodes.length > 1 ? (2 * Math.PI) / levelNodes.length : 0;
    
    levelNodes.forEach((node, indexInLevel) => {
      let x, y;
      
      if (distance === 0) {
        // Center node
        x = centerX;
        y = centerY;
      } else {
        const angle = indexInLevel * angleStep;
        x = centerX + radius * Math.cos(angle);
        y = centerY + radius * Math.sin(angle);
      }
      
      const originalIndex = nodeIndexMap.get(node.id) || 0;
      positions[originalIndex] = { x, y };
    });
  });
  
  return positions;
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
  const { hierarchyDirection = 'top-down', canvasWidth = DEFAULT_CANVAS_WIDTH, canvasHeight = DEFAULT_CANVAS_HEIGHT } = options;
  
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

/**
 * Calculate positions for cluster layout
 * Groups nodes by specified criteria and arranges clusters
 */
export function calculateClusterLayout(
  nodes: GraphNode[],
  edges: GraphEdge[],
  options: LayoutOptions = {}
): LayoutPosition[] {
  const { clusterBy = 'type', canvasWidth = DEFAULT_CANVAS_WIDTH, canvasHeight = DEFAULT_CANVAS_HEIGHT } = options;
  
  if (nodes.length === 0) return [];
  if (nodes.length === 1) return [{ x: canvasWidth / 2, y: canvasHeight / 2 }];
  
  // Group nodes by clustering criteria
  const clusters = new Map<string, GraphNode[]>();
  
  nodes.forEach(node => {
    let clusterKey: string;
    
    switch (clusterBy) {
      case 'type': {
        clusterKey = node.node_type;
        break;
      }
      case 'community': {
        clusterKey = node.node_type; // Use type as proxy for community
        break;
      }
      case 'centrality': {
        const centrality = node.properties?.degree_centrality || 0;
        clusterKey = centrality > 50 ? 'high' : centrality > 20 ? 'medium' : 'low';
        break;
      }
      case 'temporal': {
        const date = node.created_at || node.properties?.created || node.properties?.date;
        clusterKey = date ? new Date(date).getFullYear().toString() : 'unknown';
        break;
      }
      default:
        clusterKey = 'default';
    }
    
    if (!clusters.has(clusterKey)) {
      clusters.set(clusterKey, []);
    }
    clusters.get(clusterKey)!.push(node);
  });
  
  const clusterArray = Array.from(clusters.entries());
  const clusterCount = clusterArray.length;
  
  const positions: LayoutPosition[] = new Array(nodes.length);
  const nodeIndexMap = new Map(nodes.map((node, index) => [node.id, index]));
  
  // Arrange clusters in a grid or circle
  const clusterRadius = Math.min(canvasWidth, canvasHeight) * 0.15;
  const arrangementRadius = Math.min(canvasWidth, canvasHeight) * 0.25;
  
  clusterArray.forEach(([clusterKey, clusterNodes], clusterIndex) => {
    // Position cluster center
    const angle = clusterCount > 0 ? (clusterIndex / clusterCount) * 2 * Math.PI : 0;
    const clusterCenterX = canvasWidth / 2 + arrangementRadius * Math.cos(angle);
    const clusterCenterY = canvasHeight / 2 + arrangementRadius * Math.sin(angle);
    
    // Arrange nodes within cluster
    clusterNodes.forEach((node, nodeIndex) => {
      let x, y;
      
      if (clusterNodes.length === 1) {
        x = clusterCenterX;
        y = clusterCenterY;
      } else {
        const nodeAngle = clusterNodes.length > 0 ? (nodeIndex / clusterNodes.length) * 2 * Math.PI : 0;
        const nodeRadius = clusterNodes.length > 0 ? clusterRadius * Math.sqrt(nodeIndex / clusterNodes.length) : 0;
        x = clusterCenterX + nodeRadius * Math.cos(nodeAngle);
        y = clusterCenterY + nodeRadius * Math.sin(nodeAngle);
      }
      
      const originalIndex = nodeIndexMap.get(node.id) || 0;
      positions[originalIndex] = { x, y };
    });
  });
  
  return positions;
}

/**
 * Calculate positions for temporal layout
 * Arranges nodes along timeline based on temporal properties
 */
export function calculateTemporalLayout(
  nodes: GraphNode[],
  edges: GraphEdge[],
  options: LayoutOptions = {}
): LayoutPosition[] {
  const { canvasWidth = DEFAULT_CANVAS_WIDTH, canvasHeight = DEFAULT_CANVAS_HEIGHT } = options;
  
  if (nodes.length === 0) return [];
  if (nodes.length === 1) return [{ x: canvasWidth / 2, y: canvasHeight / 2 }];
  
  // Extract temporal information
  const nodesWithTime = nodes.map(node => {
    const dateStr = node.created_at || node.properties?.created || node.properties?.date;
    const date = dateStr ? new Date(dateStr) : new Date();
    return { node, date, timestamp: date.getTime() };
  });
  
  // Sort by time
  nodesWithTime.sort((a, b) => a.timestamp - b.timestamp);
  
  const minTime = nodesWithTime[0].timestamp;
  const maxTime = nodesWithTime[nodesWithTime.length - 1].timestamp;
  const timeRange = maxTime - minTime || 1;
  
  const positions: LayoutPosition[] = new Array(nodes.length);
  const nodeIndexMap = new Map(nodes.map((node, index) => [node.id, index]));
  
  // Group nodes by time periods to avoid overlap
  const timeGroups = new Map<number, GraphNode[]>();
  const groupSize = timeRange / Math.min(nodes.length, 20); // Max 20 time groups
  
  nodesWithTime.forEach(({ node, timestamp }) => {
    const groupKey = Math.floor((timestamp - minTime) / groupSize);
    if (!timeGroups.has(groupKey)) {
      timeGroups.set(groupKey, []);
    }
    timeGroups.get(groupKey)!.push(node);
  });
  
  Array.from(timeGroups.entries()).forEach(([groupKey, groupNodes]) => {
    const timePosition = groupKey * groupSize;
    const x = (timePosition / timeRange) * canvasWidth * 0.8 + canvasWidth * 0.1;
    
    groupNodes.forEach((node, indexInGroup) => {
      const y = groupNodes.length > 1 
        ? (indexInGroup / (groupNodes.length - 1)) * canvasHeight * 0.6 + canvasHeight * 0.2
        : canvasHeight / 2;
      
      const originalIndex = nodeIndexMap.get(node.id) || 0;
      positions[originalIndex] = { x, y };
    });
  });
  
  return positions;
}

// Helper function to calculate distances from center node using BFS
function calculateDistancesFromCenter(
  nodes: GraphNode[],
  edges: GraphEdge[],
  centerNodeId: string
): Record<string, number> {
  const distances: Record<string, number> = {};
  const adjacency = new Map<string, string[]>();
  
  // Build adjacency list
  nodes.forEach(node => adjacency.set(node.id, []));
  edges.forEach(edge => {
    adjacency.get(edge.from)?.push(edge.to);
    adjacency.get(edge.to)?.push(edge.from);
  });
  
  // BFS to calculate distances
  const queue = [centerNodeId];
  distances[centerNodeId] = 0;
  
  while (queue.length > 0) {
    const currentId = queue.shift()!;
    const currentDistance = distances[currentId];
    
    adjacency.get(currentId)?.forEach(neighborId => {
      if (!(neighborId in distances)) {
        distances[neighborId] = currentDistance + 1;
        queue.push(neighborId);
      }
    });
  }
  
  // Set unconnected nodes to max distance + 1
  const maxDistance = Math.max(...Object.values(distances));
  nodes.forEach(node => {
    if (!(node.id in distances)) {
      distances[node.id] = maxDistance + 1;
    }
  });
  
  return distances;
}

// Helper function to build hierarchy levels using BFS
function buildHierarchyLevels(
  nodes: GraphNode[],
  edges: GraphEdge[],
  rootNodeId: string
): GraphNode[][] {
  const levels: GraphNode[][] = [];
  const visited = new Set<string>();
  const adjacency = new Map<string, string[]>();
  
  // Build adjacency list (directed from higher to lower centrality)
  nodes.forEach(node => adjacency.set(node.id, []));
  edges.forEach(edge => {
    adjacency.get(edge.from)?.push(edge.to);
  });
  
  // BFS to build levels
  let currentLevel = [nodes.find(n => n.id === rootNodeId)!];
  visited.add(rootNodeId);
  
  while (currentLevel.length > 0) {
    levels.push([...currentLevel]);
    const nextLevel: GraphNode[] = [];
    
    currentLevel.forEach(node => {
      adjacency.get(node.id)?.forEach(neighborId => {
        if (!visited.has(neighborId)) {
          const neighborNode = nodes.find(n => n.id === neighborId);
          if (neighborNode) {
            nextLevel.push(neighborNode);
            visited.add(neighborId);
          }
        }
      });
    });
    
    currentLevel = nextLevel;
  }
  
  // Add any remaining unconnected nodes to the last level
  const unvisited = nodes.filter(node => !visited.has(node.id));
  if (unvisited.length > 0) {
    if (levels.length === 0) {
      levels.push(unvisited);
    } else {
      levels[levels.length - 1].push(...unvisited);
    }
  }
  
  return levels;
}

/**
 * Main layout calculation function
 * Routes to appropriate algorithm based on layout type
 */
export function calculateLayoutPositions(
  layoutType: string,
  nodes: GraphNode[],
  edges: GraphEdge[],
  options: LayoutOptions = {}
): LayoutPosition[] {
  switch (layoutType) {
    case 'circular':
      return calculateCircularLayout(nodes, options);
    case 'radial':
      return calculateRadialLayout(nodes, edges, options);
    case 'hierarchical':
      return calculateHierarchicalLayout(nodes, edges, options);
    case 'cluster':
      return calculateClusterLayout(nodes, edges, options);
    case 'temporal':
      return calculateTemporalLayout(nodes, edges, options);
    case 'force-directed':
    default: {
      // For force-directed, return random positions and let physics handle it
      const centerX = (options.canvasWidth || DEFAULT_CANVAS_WIDTH) / 2;
      const centerY = (options.canvasHeight || DEFAULT_CANVAS_HEIGHT) / 2;
      return nodes.map(() => ({
        x: centerX + (Math.random() - 0.5) * 200,
        y: centerY + (Math.random() - 0.5) * 200
      }));
    }
  }
}