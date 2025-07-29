import type { GraphNode, GraphEdge } from '../../types/graph';
import { LayoutPosition, LayoutOptions, DEFAULT_CANVAS_WIDTH, DEFAULT_CANVAS_HEIGHT } from './types';

/**
 * Calculate positions for temporal layout
 * Arranges nodes along timeline based on temporal properties
 */
export function calculateTemporalLayout(
  nodes: GraphNode[],
  edges: GraphEdge[],
  options: LayoutOptions = {}
): LayoutPosition[] {
  const { 
    canvasWidth = DEFAULT_CANVAS_WIDTH, 
    canvasHeight = DEFAULT_CANVAS_HEIGHT 
  } = options;
  
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
  
  // Sort groups by key to ensure temporal order
  const sortedGroups = Array.from(timeGroups.entries()).sort((a, b) => a[0] - b[0]);
  
  sortedGroups.forEach(([groupKey, groupNodes]) => {
    const timePosition = groupKey * groupSize;
    const x = (timePosition / timeRange) * canvasWidth * 0.8 + canvasWidth * 0.1;
    
    // Sort nodes within group by type for consistent vertical ordering
    groupNodes.sort((a, b) => a.node_type.localeCompare(b.node_type));
    
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