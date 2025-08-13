/**
 * Graph Metrics Calculation Utilities
 */

import { GraphNode } from '../api/types';
import { GraphLink } from '../types/graph';

/**
 * Calculate basic graph metrics
 */
export function calculateGraphMetrics(nodes: GraphNode[], links: GraphLink[]) {
  const nodeCount = nodes.length;
  const linkCount = links.length;
  
  // Calculate degrees
  const degrees = new Map<string, number>();
  nodes.forEach(node => degrees.set(node.id, 0));
  
  links.forEach(link => {
    const source = String(link.source || link.from);
    const target = String(link.target || link.to);
    
    degrees.set(source, (degrees.get(source) || 0) + 1);
    degrees.set(target, (degrees.get(target) || 0) + 1);
  });
  
  const degreeValues = Array.from(degrees.values());
  const totalDegree = degreeValues.reduce((sum, d) => sum + d, 0);
  
  // Calculate density (for undirected graph)
  // density = 2 * edges / (nodes * (nodes - 1))
  const maxPossibleEdges = nodeCount * (nodeCount - 1) / 2;
  const density = maxPossibleEdges > 0 ? linkCount / maxPossibleEdges : 0;
  
  return {
    density,
    avgDegree: nodeCount > 0 ? totalDegree / nodeCount : 0,
    maxDegree: degreeValues.length > 0 ? Math.max(...degreeValues) : 0,
    minDegree: degreeValues.length > 0 ? Math.min(...degreeValues) : 0
  };
}