import type { GraphNode, GraphEdge } from '../../types/graph';
import { LayoutPosition, LayoutOptions, DEFAULT_CANVAS_WIDTH, DEFAULT_CANVAS_HEIGHT } from './types';

/**
 * Calculate distances from center node using BFS
 */
function calculateDistancesFromCenter(
  nodes: GraphNode[],
  edges: GraphEdge[],
  centerNodeId: string
): Record<string, number> {
  const distances: Record<string, number> = {};
  const adjacencyList: Record<string, string[]> = {};
  
  // Build adjacency list
  nodes.forEach(node => {
    adjacencyList[node.id] = [];
  });
  
  edges.forEach(edge => {
    adjacencyList[edge.from]?.push(edge.to);
    adjacencyList[edge.to]?.push(edge.from);
  });
  
  // BFS from center
  const queue: string[] = [centerNodeId];
  distances[centerNodeId] = 0;
  
  while (queue.length > 0) {
    const current = queue.shift()!;
    const currentDistance = distances[current];
    
    adjacencyList[current]?.forEach(neighbor => {
      if (distances[neighbor] === undefined) {
        distances[neighbor] = currentDistance + 1;
        queue.push(neighbor);
      }
    });
  }
  
  // Handle disconnected nodes
  const maxFoundDistance = Math.max(...Object.values(distances));
  nodes.forEach(node => {
    if (distances[node.id] === undefined) {
      distances[node.id] = maxFoundDistance + 1;
    }
  });
  
  return distances;
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
  const { 
    radialCenter, 
    canvasWidth = DEFAULT_CANVAS_WIDTH, 
    canvasHeight = DEFAULT_CANVAS_HEIGHT 
  } = options;
  
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