/**
 * Object pooling for frequently created/destroyed objects
 * Reduces garbage collection pressure and improves performance
 */

import { GraphNode } from '../../../api/types';
import { GraphLink } from '../../../types/graph';
import { logger } from '../../../utils/logger';

/**
 * Generic object pool implementation
 */
export class ObjectPool<T> {
  private pool: T[] = [];
  private inUse = new Set<T>();
  private createFn: () => T;
  private resetFn: (obj: T) => void;
  private maxSize: number;
  private created = 0;
  private reused = 0;
  
  constructor(
    createFn: () => T,
    resetFn: (obj: T) => void,
    initialSize: number = 10,
    maxSize: number = 1000
  ) {
    this.createFn = createFn;
    this.resetFn = resetFn;
    this.maxSize = maxSize;
    
    // Pre-populate pool
    for (let i = 0; i < initialSize; i++) {
      this.pool.push(createFn());
      this.created++;
    }
  }
  
  /**
   * Get an object from the pool
   */
  acquire(): T {
    let obj: T;
    
    if (this.pool.length > 0) {
      obj = this.pool.pop()!;
      this.reused++;
    } else {
      obj = this.createFn();
      this.created++;
    }
    
    this.inUse.add(obj);
    return obj;
  }
  
  /**
   * Return an object to the pool
   */
  release(obj: T): void {
    if (!this.inUse.has(obj)) {
      logger.warn('ObjectPool: Attempting to release object not from this pool');
      return;
    }
    
    this.inUse.delete(obj);
    
    if (this.pool.length < this.maxSize) {
      this.resetFn(obj);
      this.pool.push(obj);
    }
  }
  
  /**
   * Release multiple objects at once
   */
  releaseAll(objects: T[]): void {
    objects.forEach(obj => this.release(obj));
  }
  
  /**
   * Clear the pool
   */
  clear(): void {
    this.pool = [];
    this.inUse.clear();
  }
  
  /**
   * Get pool statistics
   */
  getStats(): {
    poolSize: number;
    inUse: number;
    created: number;
    reused: number;
    reuseRate: number;
  } {
    const total = this.created + this.reused;
    return {
      poolSize: this.pool.length,
      inUse: this.inUse.size,
      created: this.created,
      reused: this.reused,
      reuseRate: total > 0 ? (this.reused / total) * 100 : 0
    };
  }
}

/**
 * Vector2D pool for position/velocity calculations
 */
export interface Vector2D {
  x: number;
  y: number;
}

export const Vector2DPool = new ObjectPool<Vector2D>(
  () => ({ x: 0, y: 0 }),
  (v) => { v.x = 0; v.y = 0; },
  100,
  5000
);

/**
 * Event object pool
 */
export interface PooledEvent {
  type: string;
  target: any;
  data: any;
  timestamp: number;
}

export const EventPool = new ObjectPool<PooledEvent>(
  () => ({ type: '', target: null, data: null, timestamp: 0 }),
  (e) => {
    e.type = '';
    e.target = null;
    e.data = null;
    e.timestamp = 0;
  },
  50,
  500
);

/**
 * Delta update pool
 */
export interface PooledDelta {
  id: string;
  type: 'add' | 'update' | 'remove';
  entityType: 'node' | 'link';
  data: any;
  timestamp: number;
}

export const DeltaPool = new ObjectPool<PooledDelta>(
  () => ({ 
    id: '', 
    type: 'add', 
    entityType: 'node', 
    data: null, 
    timestamp: 0 
  }),
  (d) => {
    d.id = '';
    d.type = 'add';
    d.entityType = 'node';
    d.data = null;
    d.timestamp = 0;
  },
  100,
  1000
);

/**
 * Transform matrix pool for canvas operations
 */
export interface TransformMatrix {
  a: number; // scale x
  b: number; // skew y
  c: number; // skew x
  d: number; // scale y
  e: number; // translate x
  f: number; // translate y
}

export const TransformMatrixPool = new ObjectPool<TransformMatrix>(
  () => ({ a: 1, b: 0, c: 0, d: 1, e: 0, f: 0 }),
  (m) => {
    m.a = 1;
    m.b = 0;
    m.c = 0;
    m.d = 1;
    m.e = 0;
    m.f = 0;
  },
  20,
  100
);

/**
 * Bounding box pool
 */
export interface BoundingBox {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
  width: number;
  height: number;
}

export const BoundingBoxPool = new ObjectPool<BoundingBox>(
  () => ({ 
    minX: 0, 
    minY: 0, 
    maxX: 0, 
    maxY: 0, 
    width: 0, 
    height: 0 
  }),
  (b) => {
    b.minX = 0;
    b.minY = 0;
    b.maxX = 0;
    b.maxY = 0;
    b.width = 0;
    b.height = 0;
  },
  50,
  500
);

/**
 * Color object pool
 */
export interface PooledColor {
  r: number;
  g: number;
  b: number;
  a: number;
  hex: string;
}

export const ColorPool = new ObjectPool<PooledColor>(
  () => ({ r: 0, g: 0, b: 0, a: 1, hex: '#000000' }),
  (c) => {
    c.r = 0;
    c.g = 0;
    c.b = 0;
    c.a = 1;
    c.hex = '#000000';
  },
  100,
  1000
);

/**
 * Animation frame data pool
 */
export interface AnimationFrame {
  timestamp: number;
  deltaTime: number;
  progress: number;
  value: number;
}

export const AnimationFramePool = new ObjectPool<AnimationFrame>(
  () => ({ timestamp: 0, deltaTime: 0, progress: 0, value: 0 }),
  (f) => {
    f.timestamp = 0;
    f.deltaTime = 0;
    f.progress = 0;
    f.value = 0;
  },
  60,
  300
);

/**
 * Graph operation result pool
 */
export interface GraphOperationResult {
  success: boolean;
  affected: string[];
  error?: string;
  metadata?: any;
}

export const GraphOperationResultPool = new ObjectPool<GraphOperationResult>(
  () => ({ 
    success: false, 
    affected: [], 
    error: undefined, 
    metadata: undefined 
  }),
  (r) => {
    r.success = false;
    r.affected = [];
    r.error = undefined;
    r.metadata = undefined;
  },
  20,
  100
);

/**
 * Pool manager singleton
 */
export class PoolManager {
  private static instance: PoolManager | null = null;
  private pools = new Map<string, ObjectPool<any>>();
  
  static getInstance(): PoolManager {
    if (!PoolManager.instance) {
      PoolManager.instance = new PoolManager();
    }
    return PoolManager.instance;
  }
  
  constructor() {
    // Register default pools
    this.pools.set('vector2d', Vector2DPool);
    this.pools.set('event', EventPool);
    this.pools.set('delta', DeltaPool);
    this.pools.set('transform', TransformMatrixPool);
    this.pools.set('boundingBox', BoundingBoxPool);
    this.pools.set('color', ColorPool);
    this.pools.set('animationFrame', AnimationFramePool);
    this.pools.set('graphOperation', GraphOperationResultPool);
  }
  
  /**
   * Register a custom pool
   */
  registerPool<T>(name: string, pool: ObjectPool<T>): void {
    this.pools.set(name, pool);
  }
  
  /**
   * Get a pool by name
   */
  getPool<T>(name: string): ObjectPool<T> | undefined {
    return this.pools.get(name);
  }
  
  /**
   * Clear all pools
   */
  clearAll(): void {
    this.pools.forEach(pool => pool.clear());
  }
  
  /**
   * Get statistics for all pools
   */
  getAllStats(): Map<string, any> {
    const stats = new Map<string, any>();
    this.pools.forEach((pool, name) => {
      stats.set(name, pool.getStats());
    });
    return stats;
  }
  
  /**
   * Log pool statistics
   */
  logStats(): void {
    console.group('Object Pool Statistics');
    this.pools.forEach((pool, name) => {
      const stats = pool.getStats();
      console.log(`${name}:`, {
        ...stats,
        reuseRate: `${stats.reuseRate.toFixed(2)}%`
      });
    });
    console.groupEnd();
  }
}

/**
 * Helper functions for common pool operations
 */

export function withVector2D<T>(
  fn: (v: Vector2D) => T
): T {
  const vector = Vector2DPool.acquire();
  try {
    return fn(vector);
  } finally {
    Vector2DPool.release(vector);
  }
}

export function withBoundingBox<T>(
  fn: (b: BoundingBox) => T
): T {
  const box = BoundingBoxPool.acquire();
  try {
    return fn(box);
  } finally {
    BoundingBoxPool.release(box);
  }
}

export function withColor<T>(
  fn: (c: PooledColor) => T
): T {
  const color = ColorPool.acquire();
  try {
    return fn(color);
  } finally {
    ColorPool.release(color);
  }
}

/**
 * Auto-release wrapper for batch operations
 */
export class PooledBatch<T> {
  private items: T[] = [];
  private pool: ObjectPool<T>;
  
  constructor(pool: ObjectPool<T>) {
    this.pool = pool;
  }
  
  acquire(): T {
    const item = this.pool.acquire();
    this.items.push(item);
    return item;
  }
  
  releaseAll(): void {
    this.pool.releaseAll(this.items);
    this.items = [];
  }
  
  // Auto-release on garbage collection
  [Symbol.dispose](): void {
    this.releaseAll();
  }
}