/**
 * Memory management utilities for preventing leaks and optimizing resource usage
 */

import { logger } from '../../../utils/logger';

// Object pool for frequently created/destroyed objects
export class ObjectPool<T> {
  private pool: T[] = [];
  private createFn: () => T;
  private resetFn: (obj: T) => void;
  private maxSize: number;
  
  constructor(
    createFn: () => T,
    resetFn: (obj: T) => void,
    maxSize: number = 100
  ) {
    this.createFn = createFn;
    this.resetFn = resetFn;
    this.maxSize = maxSize;
  }
  
  acquire(): T {
    if (this.pool.length > 0) {
      return this.pool.pop()!;
    }
    return this.createFn();
  }
  
  release(obj: T): void {
    if (this.pool.length < this.maxSize) {
      this.resetFn(obj);
      this.pool.push(obj);
    }
  }
  
  clear(): void {
    this.pool = [];
  }
  
  get size(): number {
    return this.pool.length;
  }
}

// WeakMap-based cache for object associations
export class WeakCache<K extends object, V> {
  private cache = new WeakMap<K, V>();
  
  get(key: K): V | undefined {
    return this.cache.get(key);
  }
  
  set(key: K, value: V): void {
    this.cache.set(key, value);
  }
  
  has(key: K): boolean {
    return this.cache.has(key);
  }
  
  delete(key: K): boolean {
    return this.cache.delete(key);
  }
}

// Cleanup tracker for managing disposable resources
export class CleanupTracker {
  private cleanupFns: Array<() => void> = [];
  
  add(cleanupFn: () => void): void {
    this.cleanupFns.push(cleanupFn);
  }
  
  cleanup(): void {
    // Execute cleanup functions in reverse order
    while (this.cleanupFns.length > 0) {
      const fn = this.cleanupFns.pop()!;
      try {
        fn();
      } catch (error) {
        logger.error('CleanupTracker: Error during cleanup:', error);
      }
    }
  }
}

// Memory usage monitor
export class MemoryMonitor {
  private static instance: MemoryMonitor | null = null;
  private interval: NodeJS.Timeout | null = null;
  private baseline: number = 0;
  
  static getInstance(): MemoryMonitor {
    if (!MemoryMonitor.instance) {
      MemoryMonitor.instance = new MemoryMonitor();
    }
    return MemoryMonitor.instance;
  }
  
  start(intervalMs: number = 10000): void {
    if (this.interval) return;
    
    // Set baseline
    this.baseline = this.getMemoryUsage();
    
    this.interval = setInterval(() => {
      const current = this.getMemoryUsage();
      const delta = current - this.baseline;
      
      if (delta > 50 * 1024 * 1024) { // 50MB growth
        logger.warn(`MemoryMonitor: High memory growth detected: ${this.formatBytes(delta)}`);
      }
      
      logger.debug(`MemoryMonitor: Current: ${this.formatBytes(current)}, Delta: ${this.formatBytes(delta)}`);
    }, intervalMs);
  }
  
  stop(): void {
    if (this.interval) {
      clearInterval(this.interval);
      this.interval = null;
    }
  }
  
  private getMemoryUsage(): number {
    if ('memory' in performance) {
      return (performance as any).memory.usedJSHeapSize;
    }
    return 0;
  }
  
  private formatBytes(bytes: number): string {
    const mb = bytes / (1024 * 1024);
    return `${mb.toFixed(2)} MB`;
  }
}

// Debounce with cleanup
export function debounceWithCleanup<T extends (...args: any[]) => any>(
  fn: T,
  delay: number
): [T, () => void] {
  let timeoutId: NodeJS.Timeout | null = null;
  
  const debounced = ((...args: Parameters<T>) => {
    if (timeoutId) {
      clearTimeout(timeoutId);
    }
    
    timeoutId = setTimeout(() => {
      fn(...args);
      timeoutId = null;
    }, delay);
  }) as T;
  
  const cleanup = () => {
    if (timeoutId) {
      clearTimeout(timeoutId);
      timeoutId = null;
    }
  };
  
  return [debounced, cleanup];
}

// Throttle with cleanup
export function throttleWithCleanup<T extends (...args: any[]) => any>(
  fn: T,
  limit: number
): [T, () => void] {
  let inThrottle = false;
  let timeoutId: NodeJS.Timeout | null = null;
  
  const throttled = ((...args: Parameters<T>) => {
    if (!inThrottle) {
      fn(...args);
      inThrottle = true;
      
      timeoutId = setTimeout(() => {
        inThrottle = false;
        timeoutId = null;
      }, limit);
    }
  }) as T;
  
  const cleanup = () => {
    if (timeoutId) {
      clearTimeout(timeoutId);
      timeoutId = null;
    }
    inThrottle = false;
  };
  
  return [throttled, cleanup];
}

// RAF-based batch processor
export class BatchProcessor<T> {
  private queue: T[] = [];
  private rafId: number | null = null;
  private processFn: (batch: T[]) => void;
  private maxBatchSize: number;
  
  constructor(processFn: (batch: T[]) => void, maxBatchSize: number = 100) {
    this.processFn = processFn;
    this.maxBatchSize = maxBatchSize;
  }
  
  add(item: T): void {
    this.queue.push(item);
    
    if (this.queue.length >= this.maxBatchSize) {
      this.flush();
    } else if (!this.rafId) {
      this.rafId = requestAnimationFrame(() => this.flush());
    }
  }
  
  flush(): void {
    if (this.rafId) {
      cancelAnimationFrame(this.rafId);
      this.rafId = null;
    }
    
    if (this.queue.length > 0) {
      const batch = this.queue.splice(0, this.maxBatchSize);
      this.processFn(batch);
      
      // Process remaining items
      if (this.queue.length > 0) {
        this.rafId = requestAnimationFrame(() => this.flush());
      }
    }
  }
  
  clear(): void {
    this.queue = [];
    if (this.rafId) {
      cancelAnimationFrame(this.rafId);
      this.rafId = null;
    }
  }
}

// Garbage collection helper
export function requestIdleGC(callback?: () => void): void {
  if ('requestIdleCallback' in window) {
    requestIdleCallback(() => {
      // Trigger GC if available (dev tools only)
      if ('gc' in window) {
        (window as any).gc();
      }
      callback?.();
    });
  } else {
    setTimeout(() => {
      callback?.();
    }, 0);
  }
}