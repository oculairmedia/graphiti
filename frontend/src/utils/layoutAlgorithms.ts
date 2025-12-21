/**
 * Layout Algorithms Re-export Module
 * 
 * This module provides the calculateLayoutPositions function that is used
 * by GraphConfigContext for applying layout algorithms to graph data.
 */

import type { GraphNode, GraphEdge } from '../types/graph';
import { applyLayout, type LayoutOptions as BaseLayoutOptions } from './layouts';

// Re-export types
export type { BaseLayoutOptions as LayoutOptions };

/**
 * Calculate layout positions for nodes based on the specified algorithm
 * 
 * @param layoutType - The layout algorithm to use
 * @param nodes - Array of graph nodes
 * @param edges - Array of graph edges
 * @param options - Layout options
 * @returns Array of positions { x, y } for each node
 */
export function calculateLayoutPositions(
  layoutType: string,
  nodes: GraphNode[],
  edges: GraphEdge[],
  options?: BaseLayoutOptions
): { x: number; y: number }[] {
  return applyLayout(layoutType, nodes, edges, options);
}

// Re-export other layout utilities
export { applyLayout, layoutAlgorithms } from './layouts';
