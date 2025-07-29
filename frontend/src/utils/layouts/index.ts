import { calculateCircularLayout } from './circular';
import { calculateRadialLayout } from './radial';
import { calculateHierarchicalLayout } from './hierarchical';
import { calculateClusterLayout } from './cluster';
import { calculateTemporalLayout } from './temporal';
import type { LayoutAlgorithm } from './types';

// Export all layout algorithms
export * from './types';
export { calculateCircularLayout } from './circular';
export { calculateRadialLayout } from './radial';
export { calculateHierarchicalLayout } from './hierarchical';
export { calculateClusterLayout } from './cluster';
export { calculateTemporalLayout } from './temporal';

// Layout algorithm registry
export const layoutAlgorithms: Record<string, LayoutAlgorithm> = {
  circular: {
    name: 'Circular',
    calculate: calculateCircularLayout,
  },
  radial: {
    name: 'Radial',
    calculate: calculateRadialLayout,
  },
  hierarchical: {
    name: 'Hierarchical',
    calculate: calculateHierarchicalLayout,
  },
  cluster: {
    name: 'Cluster',
    calculate: calculateClusterLayout,
  },
  temporal: {
    name: 'Temporal',
    calculate: calculateTemporalLayout,
  },
};

/**
 * Apply a layout algorithm by name
 */
export function applyLayout(
  layoutName: string,
  nodes: any[],
  edges: any[],
  options?: any
): any[] {
  const algorithm = layoutAlgorithms[layoutName];
  if (!algorithm) {
    console.warn(`Unknown layout algorithm: ${layoutName}`);
    return nodes.map(() => ({ x: 0, y: 0 }));
  }
  
  return algorithm.calculate(nodes, edges, options);
}