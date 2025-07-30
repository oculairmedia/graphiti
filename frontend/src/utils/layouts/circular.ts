import type { GraphNode, GraphEdge } from '../../types/graph';
import { LayoutPosition, LayoutOptions, DEFAULT_CANVAS_WIDTH, DEFAULT_CANVAS_HEIGHT } from './types';

/**
 * Calculate positions for circular layout
 * Arranges nodes in a perfect circle with optional ordering
 */
export function calculateCircularLayout(
  nodes: GraphNode[],
  edges: GraphEdge[],
  options: LayoutOptions = {}
): LayoutPosition[] {
  const { 
    circularOrdering = 'degree', 
    canvasWidth = DEFAULT_CANVAS_WIDTH, 
    canvasHeight = DEFAULT_CANVAS_HEIGHT 
  } = options;
  
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