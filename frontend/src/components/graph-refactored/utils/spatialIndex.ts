/**
 * Spatial indexing for efficient virtual rendering
 * Uses QuadTree for 2D spatial partitioning
 */

import { GraphNode } from '../../../api/types';
import { logger } from '../../../utils/logger';

export interface Bounds {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
}

export interface Point {
  x: number;
  y: number;
}

export interface IndexedNode extends GraphNode {
  x: number;
  y: number;
}

/**
 * QuadTree node for spatial partitioning
 */
class QuadTreeNode<T extends Point> {
  bounds: Bounds;
  points: T[] = [];
  children: QuadTreeNode<T>[] | null = null;
  
  constructor(
    public readonly maxPoints: number,
    public readonly maxDepth: number,
    bounds: Bounds,
    public readonly depth: number = 0
  ) {
    this.bounds = bounds;
  }
  
  /**
   * Insert a point into the quadtree
   */
  insert(point: T): boolean {
    // Check if point is within bounds
    if (!this.contains(point)) {
      return false;
    }
    
    // If node has room and no children, add point
    if (this.points.length < this.maxPoints && !this.children) {
      this.points.push(point);
      return true;
    }
    
    // Subdivide if needed
    if (!this.children && this.depth < this.maxDepth) {
      this.subdivide();
    }
    
    // If has children, insert into appropriate child
    if (this.children) {
      for (const child of this.children) {
        if (child.insert(point)) {
          return true;
        }
      }
    }
    
    // If can't subdivide further, add to this node
    this.points.push(point);
    return true;
  }
  
  /**
   * Query points within bounds
   */
  query(searchBounds: Bounds, results: T[] = []): T[] {
    // Check if search bounds intersect with this node
    if (!this.intersects(searchBounds)) {
      return results;
    }
    
    // Add points from this node
    for (const point of this.points) {
      if (this.pointInBounds(point, searchBounds)) {
        results.push(point);
      }
    }
    
    // Query children
    if (this.children) {
      for (const child of this.children) {
        child.query(searchBounds, results);
      }
    }
    
    return results;
  }
  
  /**
   * Find nearest neighbors
   */
  findNearest(point: Point, k: number, maxDistance?: number): T[] {
    const candidates: Array<{ point: T; distance: number }> = [];
    this.findNearestRecursive(point, k, maxDistance || Infinity, candidates);
    
    // Sort by distance and return k nearest
    candidates.sort((a, b) => a.distance - b.distance);
    return candidates.slice(0, k).map(c => c.point);
  }
  
  private findNearestRecursive(
    target: Point,
    k: number,
    maxDistance: number,
    candidates: Array<{ point: T; distance: number }>
  ): void {
    // Check points in this node
    for (const point of this.points) {
      const distance = this.distance(target, point);
      if (distance <= maxDistance) {
        candidates.push({ point, distance });
      }
    }
    
    // Check children
    if (this.children) {
      // Sort children by distance to target
      const childrenWithDistance = this.children.map(child => ({
        child,
        distance: this.distanceToBounds(target, child.bounds)
      }));
      childrenWithDistance.sort((a, b) => a.distance - b.distance);
      
      for (const { child, distance } of childrenWithDistance) {
        // Skip if child is too far
        if (distance > maxDistance) continue;
        
        // Skip if we have enough candidates and child is farther
        if (candidates.length >= k) {
          candidates.sort((a, b) => a.distance - b.distance);
          if (distance > candidates[k - 1].distance) continue;
        }
        
        child.findNearestRecursive(target, k, maxDistance, candidates);
      }
    }
  }
  
  /**
   * Clear all points
   */
  clear(): void {
    this.points = [];
    if (this.children) {
      for (const child of this.children) {
        child.clear();
      }
      this.children = null;
    }
  }
  
  /**
   * Get statistics
   */
  getStats(): { nodes: number; points: number; maxDepth: number } {
    let nodes = 1;
    let points = this.points.length;
    let maxDepth = this.depth;
    
    if (this.children) {
      for (const child of this.children) {
        const childStats = child.getStats();
        nodes += childStats.nodes;
        points += childStats.points;
        maxDepth = Math.max(maxDepth, childStats.maxDepth);
      }
    }
    
    return { nodes, points, maxDepth };
  }
  
  private subdivide(): void {
    const { minX, minY, maxX, maxY } = this.bounds;
    const midX = (minX + maxX) / 2;
    const midY = (minY + maxY) / 2;
    
    this.children = [
      // Top-left
      new QuadTreeNode<T>(
        this.maxPoints,
        this.maxDepth,
        { minX, minY, maxX: midX, maxY: midY },
        this.depth + 1
      ),
      // Top-right
      new QuadTreeNode<T>(
        this.maxPoints,
        this.maxDepth,
        { minX: midX, minY, maxX, maxY: midY },
        this.depth + 1
      ),
      // Bottom-left
      new QuadTreeNode<T>(
        this.maxPoints,
        this.maxDepth,
        { minX, minY: midY, maxX: midX, maxY },
        this.depth + 1
      ),
      // Bottom-right
      new QuadTreeNode<T>(
        this.maxPoints,
        this.maxDepth,
        { minX: midX, minY: midY, maxX, maxY },
        this.depth + 1
      )
    ];
    
    // Move existing points to children
    const existingPoints = [...this.points];
    this.points = [];
    
    for (const point of existingPoints) {
      let inserted = false;
      for (const child of this.children) {
        if (child.insert(point)) {
          inserted = true;
          break;
        }
      }
      if (!inserted) {
        this.points.push(point);
      }
    }
  }
  
  private contains(point: Point): boolean {
    return this.pointInBounds(point, this.bounds);
  }
  
  private pointInBounds(point: Point, bounds: Bounds): boolean {
    return point.x >= bounds.minX &&
           point.x <= bounds.maxX &&
           point.y >= bounds.minY &&
           point.y <= bounds.maxY;
  }
  
  private intersects(bounds: Bounds): boolean {
    return !(bounds.maxX < this.bounds.minX ||
             bounds.minX > this.bounds.maxX ||
             bounds.maxY < this.bounds.minY ||
             bounds.minY > this.bounds.maxY);
  }
  
  private distance(p1: Point, p2: Point): number {
    const dx = p1.x - p2.x;
    const dy = p1.y - p2.y;
    return Math.sqrt(dx * dx + dy * dy);
  }
  
  private distanceToBounds(point: Point, bounds: Bounds): number {
    let dx = 0;
    let dy = 0;
    
    if (point.x < bounds.minX) {
      dx = bounds.minX - point.x;
    } else if (point.x > bounds.maxX) {
      dx = point.x - bounds.maxX;
    }
    
    if (point.y < bounds.minY) {
      dy = bounds.minY - point.y;
    } else if (point.y > bounds.maxY) {
      dy = point.y - bounds.maxY;
    }
    
    return Math.sqrt(dx * dx + dy * dy);
  }
}

/**
 * SpatialIndex - Main spatial indexing class
 */
export class SpatialIndex {
  private quadTree: QuadTreeNode<IndexedNode> | null = null;
  private bounds: Bounds = { minX: 0, minY: 0, maxX: 0, maxY: 0 };
  private nodeCount = 0;
  
  constructor(
    private readonly maxPointsPerNode: number = 10,
    private readonly maxDepth: number = 10
  ) {}
  
  /**
   * Build index from nodes
   */
  build(nodes: IndexedNode[]): void {
    if (nodes.length === 0) {
      this.clear();
      return;
    }
    
    // Calculate bounds
    this.bounds = this.calculateBounds(nodes);
    
    // Create quadtree
    this.quadTree = new QuadTreeNode<IndexedNode>(
      this.maxPointsPerNode,
      this.maxDepth,
      this.bounds
    );
    
    // Insert all nodes
    for (const node of nodes) {
      if (node.x !== undefined && node.y !== undefined) {
        this.quadTree.insert(node);
        this.nodeCount++;
      }
    }
    
    logger.log('SpatialIndex: Built index', {
      nodes: this.nodeCount,
      bounds: this.bounds,
      stats: this.quadTree.getStats()
    });
  }
  
  /**
   * Query nodes within viewport bounds
   */
  queryViewport(viewport: Bounds): IndexedNode[] {
    if (!this.quadTree) return [];
    return this.quadTree.query(viewport);
  }
  
  /**
   * Query nodes within radius
   */
  queryRadius(center: Point, radius: number): IndexedNode[] {
    if (!this.quadTree) return [];
    
    // Convert to bounds for initial filtering
    const bounds: Bounds = {
      minX: center.x - radius,
      minY: center.y - radius,
      maxX: center.x + radius,
      maxY: center.y + radius
    };
    
    // Get candidates from quadtree
    const candidates = this.quadTree.query(bounds);
    
    // Filter by actual radius
    const radiusSquared = radius * radius;
    return candidates.filter(node => {
      const dx = node.x - center.x;
      const dy = node.y - center.y;
      return (dx * dx + dy * dy) <= radiusSquared;
    });
  }
  
  /**
   * Find k nearest neighbors
   */
  findNearest(point: Point, k: number, maxDistance?: number): IndexedNode[] {
    if (!this.quadTree) return [];
    return this.quadTree.findNearest(point, k, maxDistance);
  }
  
  /**
   * Update node position
   */
  updateNode(nodeId: string, newPosition: Point): boolean {
    if (!this.quadTree) return false;
    
    // This is inefficient - in production, maintain a separate map
    // For now, rebuild the index
    logger.warn('SpatialIndex: Update requires rebuild (not optimized)');
    return false;
  }
  
  /**
   * Clear the index
   */
  clear(): void {
    if (this.quadTree) {
      this.quadTree.clear();
    }
    this.quadTree = null;
    this.nodeCount = 0;
  }
  
  /**
   * Get index statistics
   */
  getStats(): any {
    if (!this.quadTree) {
      return { nodes: 0, points: 0, maxDepth: 0 };
    }
    return this.quadTree.getStats();
  }
  
  /**
   * Calculate bounding box from nodes
   */
  private calculateBounds(nodes: IndexedNode[]): Bounds {
    let minX = Infinity;
    let minY = Infinity;
    let maxX = -Infinity;
    let maxY = -Infinity;
    
    for (const node of nodes) {
      if (node.x !== undefined && node.y !== undefined) {
        minX = Math.min(minX, node.x);
        minY = Math.min(minY, node.y);
        maxX = Math.max(maxX, node.x);
        maxY = Math.max(maxY, node.y);
      }
    }
    
    // Add padding
    const padding = 100;
    return {
      minX: minX - padding,
      minY: minY - padding,
      maxX: maxX + padding,
      maxY: maxY + padding
    };
  }
}

/**
 * RTree implementation for more efficient updates
 * (Placeholder - would use a library like rbush in production)
 */
export class RTreeIndex {
  // This would use a proper R-tree library
  private index: SpatialIndex;
  
  constructor() {
    this.index = new SpatialIndex();
  }
  
  insert(node: IndexedNode): void {
    // R-tree insert
  }
  
  remove(nodeId: string): void {
    // R-tree remove
  }
  
  update(nodeId: string, newPosition: Point): void {
    // R-tree update (remove + insert)
  }
  
  query(bounds: Bounds): IndexedNode[] {
    return this.index.queryViewport(bounds);
  }
}

/**
 * Grid-based spatial index for uniform distributions
 */
export class GridIndex {
  private grid: Map<string, IndexedNode[]> = new Map();
  private cellSize: number;
  private bounds: Bounds;
  
  constructor(bounds: Bounds, cellSize: number = 100) {
    this.bounds = bounds;
    this.cellSize = cellSize;
  }
  
  private getCellKey(x: number, y: number): string {
    const col = Math.floor((x - this.bounds.minX) / this.cellSize);
    const row = Math.floor((y - this.bounds.minY) / this.cellSize);
    return `${col},${row}`;
  }
  
  insert(node: IndexedNode): void {
    const key = this.getCellKey(node.x, node.y);
    if (!this.grid.has(key)) {
      this.grid.set(key, []);
    }
    this.grid.get(key)!.push(node);
  }
  
  query(bounds: Bounds): IndexedNode[] {
    const results: IndexedNode[] = [];
    
    const minCol = Math.floor((bounds.minX - this.bounds.minX) / this.cellSize);
    const maxCol = Math.ceil((bounds.maxX - this.bounds.minX) / this.cellSize);
    const minRow = Math.floor((bounds.minY - this.bounds.minY) / this.cellSize);
    const maxRow = Math.ceil((bounds.maxY - this.bounds.minY) / this.cellSize);
    
    for (let col = minCol; col <= maxCol; col++) {
      for (let row = minRow; row <= maxRow; row++) {
        const key = `${col},${row}`;
        const nodes = this.grid.get(key) || [];
        
        // Filter nodes within exact bounds
        for (const node of nodes) {
          if (node.x >= bounds.minX && node.x <= bounds.maxX &&
              node.y >= bounds.minY && node.y <= bounds.maxY) {
            results.push(node);
          }
        }
      }
    }
    
    return results;
  }
  
  clear(): void {
    this.grid.clear();
  }
}