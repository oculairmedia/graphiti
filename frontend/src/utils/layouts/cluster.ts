import type { GraphNode, GraphEdge } from '../../types/graph';
import { LayoutPosition, LayoutOptions, DEFAULT_CANVAS_WIDTH, DEFAULT_CANVAS_HEIGHT } from './types';

/**
 * Calculate positions for cluster layout
 * Groups nodes by specified criteria and arranges clusters
 */
export function calculateClusterLayout(
  nodes: GraphNode[],
  edges: GraphEdge[],
  options: LayoutOptions = {}
): LayoutPosition[] {
  const { 
    clusterBy = 'type', 
    canvasWidth = DEFAULT_CANVAS_WIDTH, 
    canvasHeight = DEFAULT_CANVAS_HEIGHT 
  } = options;
  
  if (nodes.length === 0) return [];
  if (nodes.length === 1) return [{ x: canvasWidth / 2, y: canvasHeight / 2 }];
  
  // Group nodes by clustering criteria
  const clusters = new Map<string, GraphNode[]>();
  
  nodes.forEach(node => {
    let clusterKey: string;
    
    switch (clusterBy) {
      case 'type':
        clusterKey = node.node_type;
        break;
      case 'community':
        // Use type as proxy for community detection
        // In a real implementation, you'd run community detection algorithms
        clusterKey = node.node_type;
        break;
      case 'centrality':
        const centrality = node.properties?.degree_centrality || 0;
        clusterKey = centrality > 50 ? 'high' : centrality > 20 ? 'medium' : 'low';
        break;
      case 'temporal':
        const date = node.created_at || node.properties?.created || node.properties?.date;
        clusterKey = date ? new Date(date).getFullYear().toString() : 'unknown';
        break;
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
  
  // Arrange clusters in a grid or circle based on count
  const useGrid = clusterCount > 6;
  
  if (useGrid) {
    // Grid layout for many clusters
    const cols = Math.ceil(Math.sqrt(clusterCount));
    const rows = Math.ceil(clusterCount / cols);
    const cellWidth = canvasWidth * 0.8 / cols;
    const cellHeight = canvasHeight * 0.8 / rows;
    
    clusterArray.forEach(([clusterKey, clusterNodes], clusterIndex) => {
      const row = Math.floor(clusterIndex / cols);
      const col = clusterIndex % cols;
      
      const clusterCenterX = canvasWidth * 0.1 + (col + 0.5) * cellWidth;
      const clusterCenterY = canvasHeight * 0.1 + (row + 0.5) * cellHeight;
      const clusterRadius = Math.min(cellWidth, cellHeight) * 0.35;
      
      arrangeNodesInCluster(
        clusterNodes, 
        clusterCenterX, 
        clusterCenterY, 
        clusterRadius, 
        positions, 
        nodeIndexMap
      );
    });
  } else {
    // Circular arrangement for few clusters
    const arrangementRadius = Math.min(canvasWidth, canvasHeight) * 0.3;
    const clusterRadius = Math.min(canvasWidth, canvasHeight) * 0.15;
    
    clusterArray.forEach(([clusterKey, clusterNodes], clusterIndex) => {
      const angle = clusterCount > 0 ? (clusterIndex / clusterCount) * 2 * Math.PI : 0;
      const clusterCenterX = canvasWidth / 2 + arrangementRadius * Math.cos(angle);
      const clusterCenterY = canvasHeight / 2 + arrangementRadius * Math.sin(angle);
      
      arrangeNodesInCluster(
        clusterNodes, 
        clusterCenterX, 
        clusterCenterY, 
        clusterRadius, 
        positions, 
        nodeIndexMap
      );
    });
  }
  
  return positions;
}

/**
 * Arrange nodes within a single cluster
 */
function arrangeNodesInCluster(
  clusterNodes: GraphNode[],
  centerX: number,
  centerY: number,
  radius: number,
  positions: LayoutPosition[],
  nodeIndexMap: Map<string, number>
): void {
  if (clusterNodes.length === 1) {
    const originalIndex = nodeIndexMap.get(clusterNodes[0].id) || 0;
    positions[originalIndex] = { x: centerX, y: centerY };
    return;
  }
  
  // Use spiral arrangement for nodes within cluster
  const goldenAngle = Math.PI * (3 - Math.sqrt(5)); // Golden angle in radians
  
  clusterNodes.forEach((node, nodeIndex) => {
    const t = nodeIndex / Math.max(1, clusterNodes.length - 1);
    const angle = nodeIndex * goldenAngle;
    const spiralRadius = radius * Math.sqrt(t);
    
    const x = centerX + spiralRadius * Math.cos(angle);
    const y = centerY + spiralRadius * Math.sin(angle);
    
    const originalIndex = nodeIndexMap.get(node.id) || 0;
    positions[originalIndex] = { x, y };
  });
}