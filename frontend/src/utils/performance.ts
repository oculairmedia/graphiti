// Performance utilities for debouncing, throttling, and request optimization

export function debounce<T extends (...args: any[]) => any>(
  func: T,
  wait: number
): (...args: Parameters<T>) => void {
  let timeout: NodeJS.Timeout | null = null;
  
  return function(this: any, ...args: Parameters<T>) {
    const context = this;
    
    if (timeout) clearTimeout(timeout);
    
    timeout = setTimeout(() => {
      func.apply(context, args);
    }, wait);
  };
}

export function throttle<T extends (...args: any[]) => any>(
  func: T,
  limit: number
): (...args: Parameters<T>) => void {
  let inThrottle = false;
  let lastArgs: Parameters<T> | null = null;
  let lastContext: any = null;
  
  return function(this: any, ...args: Parameters<T>) {
    const context = this;
    
    if (!inThrottle) {
      func.apply(context, args);
      inThrottle = true;
      
      setTimeout(() => {
        inThrottle = false;
        
        if (lastArgs) {
          func.apply(lastContext, lastArgs);
          lastArgs = null;
          lastContext = null;
        }
      }, limit);
    } else {
      lastArgs = args;
      lastContext = context;
    }
  };
}

// Request queue with priority and deduplication
export class RequestQueue {
  private queue: Map<string, {
    request: () => Promise<any>,
    priority: number,
    timestamp: number,
    resolve: (value: any) => void,
    reject: (error: any) => void
  }> = new Map();
  
  private processing = false;
  private maxConcurrent: number;
  private activeRequests = 0;
  
  constructor(maxConcurrent = 3) {
    this.maxConcurrent = maxConcurrent;
  }
  
  async add<T>(
    key: string,
    request: () => Promise<T>,
    priority = 0
  ): Promise<T> {
    // Deduplicate by key
    if (this.queue.has(key)) {
      const existing = this.queue.get(key)!;
      // Update priority if higher
      if (priority > existing.priority) {
        existing.priority = priority;
      }
      return new Promise((resolve, reject) => {
        // Chain to existing promise
        const originalResolve = existing.resolve;
        existing.resolve = (value) => {
          originalResolve(value);
          resolve(value);
        };
      });
    }
    
    return new Promise((resolve, reject) => {
      this.queue.set(key, {
        request,
        priority,
        timestamp: Date.now(),
        resolve,
        reject
      });
      
      this.process();
    });
  }
  
  private async process() {
    if (this.processing || this.activeRequests >= this.maxConcurrent) {
      return;
    }
    
    this.processing = true;
    
    while (this.queue.size > 0 && this.activeRequests < this.maxConcurrent) {
      // Get highest priority item
      let nextItem: any = null;
      let nextKey: string = '';
      
      for (const [key, item] of this.queue) {
        if (!nextItem || item.priority > nextItem.priority ||
            (item.priority === nextItem.priority && item.timestamp < nextItem.timestamp)) {
          nextItem = item;
          nextKey = key;
        }
      }
      
      if (nextItem) {
        this.queue.delete(nextKey);
        this.activeRequests++;
        
        try {
          const result = await nextItem.request();
          nextItem.resolve(result);
        } catch (error) {
          nextItem.reject(error);
        } finally {
          this.activeRequests--;
        }
      }
    }
    
    this.processing = false;
    
    // Process more if available
    if (this.queue.size > 0) {
      this.process();
    }
  }
  
  clear() {
    for (const [_, item] of this.queue) {
      item.reject(new Error('Queue cleared'));
    }
    this.queue.clear();
  }
}

// Batch requests for efficiency
export class BatchProcessor<T, R> {
  private batch: Map<string, {
    item: T,
    resolve: (value: R) => void,
    reject: (error: any) => void
  }> = new Map();
  
  private timer: NodeJS.Timeout | null = null;
  private batchSize: number;
  private batchDelay: number;
  private processor: (items: T[]) => Promise<Map<string, R>>;
  
  constructor(
    processor: (items: T[]) => Promise<Map<string, R>>,
    batchSize = 50,
    batchDelay = 100
  ) {
    this.processor = processor;
    this.batchSize = batchSize;
    this.batchDelay = batchDelay;
  }
  
  async add(key: string, item: T): Promise<R> {
    return new Promise((resolve, reject) => {
      this.batch.set(key, { item, resolve, reject });
      
      // Process if batch is full
      if (this.batch.size >= this.batchSize) {
        this.processBatch();
      } else {
        // Schedule batch processing
        if (!this.timer) {
          this.timer = setTimeout(() => this.processBatch(), this.batchDelay);
        }
      }
    });
  }
  
  private async processBatch() {
    if (this.timer) {
      clearTimeout(this.timer);
      this.timer = null;
    }
    
    if (this.batch.size === 0) return;
    
    const currentBatch = new Map(this.batch);
    this.batch.clear();
    
    try {
      const items = Array.from(currentBatch.values()).map(v => v.item);
      const results = await this.processor(items);
      
      for (const [key, { resolve }] of currentBatch) {
        const result = results.get(key);
        if (result !== undefined) {
          resolve(result);
        } else {
          resolve(null as any);
        }
      }
    } catch (error) {
      for (const [_, { reject }] of currentBatch) {
        reject(error);
      }
    }
  }
}

// Frame-based rendering throttle
export class FrameThrottler {
  private rafId: number | null = null;
  private lastTime = 0;
  private targetFPS: number;
  
  constructor(targetFPS = 60) {
    this.targetFPS = targetFPS;
  }
  
  throttle(callback: (deltaTime: number) => void): void {
    const frameInterval = 1000 / this.targetFPS;
    const now = performance.now();
    const deltaTime = now - this.lastTime;
    
    if (deltaTime >= frameInterval) {
      callback(deltaTime);
      this.lastTime = now - (deltaTime % frameInterval);
    }
    
    this.rafId = requestAnimationFrame(() => this.throttle(callback));
  }
  
  start(callback: (deltaTime: number) => void): void {
    this.stop();
    this.lastTime = performance.now();
    this.throttle(callback);
  }
  
  stop(): void {
    if (this.rafId !== null) {
      cancelAnimationFrame(this.rafId);
      this.rafId = null;
    }
  }
}

// Memory-aware cache
export class MemoryCache<T> {
  private cache = new Map<string, { data: T, size: number, timestamp: number }>();
  private totalSize = 0;
  private maxSize: number;
  private ttl: number;
  
  constructor(maxSizeMB = 50, ttlMs = 300000) {
    this.maxSize = maxSizeMB * 1024 * 1024; // Convert to bytes
    this.ttl = ttlMs;
  }
  
  set(key: string, data: T): void {
    const size = this.estimateSize(data);
    
    // Remove old entry if exists
    if (this.cache.has(key)) {
      const old = this.cache.get(key)!;
      this.totalSize -= old.size;
    }
    
    // Evict if necessary
    while (this.totalSize + size > this.maxSize && this.cache.size > 0) {
      this.evictOldest();
    }
    
    this.cache.set(key, { data, size, timestamp: Date.now() });
    this.totalSize += size;
  }
  
  get(key: string): T | null {
    const entry = this.cache.get(key);
    
    if (!entry) return null;
    
    // Check TTL
    if (Date.now() - entry.timestamp > this.ttl) {
      this.delete(key);
      return null;
    }
    
    return entry.data;
  }
  
  delete(key: string): void {
    const entry = this.cache.get(key);
    if (entry) {
      this.totalSize -= entry.size;
      this.cache.delete(key);
    }
  }
  
  clear(): void {
    this.cache.clear();
    this.totalSize = 0;
  }
  
  private evictOldest(): void {
    let oldest: string | null = null;
    let oldestTime = Infinity;
    
    for (const [key, entry] of this.cache) {
      if (entry.timestamp < oldestTime) {
        oldest = key;
        oldestTime = entry.timestamp;
      }
    }
    
    if (oldest) {
      this.delete(oldest);
    }
  }
  
  private estimateSize(data: any): number {
    // Rough estimation
    return JSON.stringify(data).length * 2; // 2 bytes per character
  }
}