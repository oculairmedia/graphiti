/**
 * Spatial indexing for efficient viewport-based node culling
 * Uses a quadtree data structure for O(log n) queries
 */

import { GraphNode } from '../api/types';

interface Bounds {
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
}

interface QuadTreeNode {
  bounds: Bounds;
  nodes: GraphNode[];
  children: QuadTreeNode[] | null;
  depth: number;
}

export class SpatialIndex {
  private root: QuadTreeNode | null = null;
  private maxDepth = 8;
  private maxNodesPerQuad = 100;
  private nodePositions = new Map<string, { x: number; y: number }>();

  constructor(maxDepth = 8, maxNodesPerQuad = 100) {
    this.maxDepth = maxDepth;
    this.maxNodesPerQuad = maxNodesPerQuad;
  }

  /**
   * Build spatial index from nodes with positions
   */
  build(nodes: GraphNode[], positions: Map<string, { x: number; y: number }>): void {
    this.nodePositions = positions;
    
    if (nodes.length === 0) {
      this.root = null;
      return;
    }

    // Calculate bounds
    let minX = Infinity, maxX = -Infinity;
    let minY = Infinity, maxY = -Infinity;

    nodes.forEach(node => {
      const pos = positions.get(node.id);
      if (pos) {
        minX = Math.min(minX, pos.x);
        maxX = Math.max(maxX, pos.x);
        minY = Math.min(minY, pos.y);
        maxY = Math.max(maxY, pos.y);
      }
    });

    // Add padding
    const padding = Math.max(maxX - minX, maxY - minY) * 0.1;
    
    this.root = {
      bounds: {
        minX: minX - padding,
        maxX: maxX + padding,
        minY: minY - padding,
        maxY: maxY + padding
      },
      nodes: [],
      children: null,
      depth: 0
    };

    // Insert all nodes
    nodes.forEach(node => {
      const pos = positions.get(node.id);
      if (pos) {
        this.insert(this.root!, node, pos);
      }
    });
  }

  /**
   * Query nodes within viewport bounds
   */
  query(viewport: Bounds): GraphNode[] {
    if (!this.root) return [];
    
    const results: GraphNode[] = [];
    this.queryRecursive(this.root, viewport, results);
    return results;
  }

  /**
   * Query nodes within radius of a point
   */
  queryRadius(x: number, y: number, radius: number): GraphNode[] {
    const bounds: Bounds = {
      minX: x - radius,
      maxX: x + radius,
      minY: y - radius,
      maxY: y + radius
    };
    
    const candidates = this.query(bounds);
    
    // Filter by actual distance
    return candidates.filter(node => {
      const pos = this.nodePositions.get(node.id);
      if (!pos) return false;
      
      const dx = pos.x - x;
      const dy = pos.y - y;
      return Math.sqrt(dx * dx + dy * dy) <= radius;
    });
  }

  /**
   * Get k nearest neighbors to a point
   */
  knn(x: number, y: number, k: number): GraphNode[] {
    if (!this.root) return [];
    
    // Start with a small radius and expand
    let radius = 100;
    let results: GraphNode[] = [];
    
    while (results.length < k && radius < 10000) {
      results = this.queryRadius(x, y, radius);
      radius *= 2;
    }
    
    // Sort by distance and take k closest
    results.sort((a, b) => {
      const posA = this.nodePositions.get(a.id)!;
      const posB = this.nodePositions.get(b.id)!;
      
      const distA = Math.sqrt((posA.x - x) ** 2 + (posA.y - y) ** 2);
      const distB = Math.sqrt((posB.x - x) ** 2 + (posB.y - y) ** 2);
      
      return distA - distB;
    });
    
    return results.slice(0, k);
  }

  /**
   * Update node position
   */
  updatePosition(nodeId: string, x: number, y: number): void {
    this.nodePositions.set(nodeId, { x, y });
    // Note: Full rebuild might be needed for optimal performance
    // For now, we'll rely on periodic rebuilds
  }

  /**
   * Get statistics about the index
   */
  getStats(): { totalNodes: number; treeDepth: number; quadrants: number } {
    if (!this.root) {
      return { totalNodes: 0, treeDepth: 0, quadrants: 0 };
    }

    let quadrants = 0;
    let maxDepth = 0;
    let totalNodes = 0;

    const traverse = (node: QuadTreeNode) => {
      quadrants++;
      maxDepth = Math.max(maxDepth, node.depth);
      totalNodes += node.nodes.length;
      
      if (node.children) {
        node.children.forEach(child => traverse(child));
      }
    };

    traverse(this.root);

    return { totalNodes, treeDepth: maxDepth, quadrants };
  }

  private insert(quad: QuadTreeNode, node: GraphNode, pos: { x: number; y: number }): void {
    // Check if point is within bounds
    if (!this.containsPoint(quad.bounds, pos)) {
      return;
    }

    // If no children and below capacity, add to this quad
    if (!quad.children && quad.nodes.length < this.maxNodesPerQuad) {
      quad.nodes.push(node);
      return;
    }

    // If at max depth, add to this quad anyway
    if (quad.depth >= this.maxDepth) {
      quad.nodes.push(node);
      return;
    }

    // Need to subdivide
    if (!quad.children) {
      this.subdivide(quad);
      
      // Move existing nodes to children
      const existingNodes = quad.nodes;
      quad.nodes = [];
      
      existingNodes.forEach(existingNode => {
        const existingPos = this.nodePositions.get(existingNode.id);
        if (existingPos) {
          this.insertIntoChildren(quad, existingNode, existingPos);
        }
      });
    }

    // Insert into appropriate child
    this.insertIntoChildren(quad, node, pos);
  }

  private insertIntoChildren(quad: QuadTreeNode, node: GraphNode, pos: { x: number; y: number }): void {
    if (!quad.children) return;
    
    for (const child of quad.children) {
      if (this.containsPoint(child.bounds, pos)) {
        this.insert(child, node, pos);
        return;
      }
    }
  }

  private subdivide(quad: QuadTreeNode): void {
    const { minX, maxX, minY, maxY } = quad.bounds;
    const midX = (minX + maxX) / 2;
    const midY = (minY + maxY) / 2;
    
    quad.children = [
      // Top-left
      {
        bounds: { minX, maxX: midX, minY, maxY: midY },
        nodes: [],
        children: null,
        depth: quad.depth + 1
      },
      // Top-right
      {
        bounds: { minX: midX, maxX, minY, maxY: midY },
        nodes: [],
        children: null,
        depth: quad.depth + 1
      },
      // Bottom-left
      {
        bounds: { minX, maxX: midX, minY: midY, maxY },
        nodes: [],
        children: null,
        depth: quad.depth + 1
      },
      // Bottom-right
      {
        bounds: { minX: midX, maxX, minY: midY, maxY },
        nodes: [],
        children: null,
        depth: quad.depth + 1
      }
    ];
  }

  private queryRecursive(quad: QuadTreeNode, viewport: Bounds, results: GraphNode[]): void {
    // Check if quad intersects viewport
    if (!this.boundsIntersect(quad.bounds, viewport)) {
      return;
    }

    // Add all nodes in this quad that are within viewport
    quad.nodes.forEach(node => {
      const pos = this.nodePositions.get(node.id);
      if (pos && this.containsPoint(viewport, pos)) {
        results.push(node);
      }
    });

    // Recursively check children
    if (quad.children) {
      quad.children.forEach(child => {
        this.queryRecursive(child, viewport, results);
      });
    }
  }

  private containsPoint(bounds: Bounds, point: { x: number; y: number }): boolean {
    return point.x >= bounds.minX && point.x <= bounds.maxX &&
           point.y >= bounds.minY && point.y <= bounds.maxY;
  }

  private boundsIntersect(a: Bounds, b: Bounds): boolean {
    return !(a.maxX < b.minX || a.minX > b.maxX ||
             a.maxY < b.minY || a.minY > b.maxY);
  }
}

// Singleton instance for global use
export const spatialIndex = new SpatialIndex();