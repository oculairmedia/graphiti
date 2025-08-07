import { DuckDBService } from './duckdb-service';
import { logger } from '../utils/logger';

interface CacheEntry<T> {
  data: T;
  timestamp: number;
  version?: string;
  etag?: string;
}

interface CacheOptions {
  ttl?: number; // Time to live in milliseconds
  maxSize?: number; // Maximum cache size
  enableVersioning?: boolean;
}

export class GraphCacheService {
  private cache = new Map<string, CacheEntry<any>>();
  private duckDBService: DuckDBService | null = null;
  private options: Required<CacheOptions>;
  private versions = new Map<string, string>();
  private accessLog = new Map<string, number[]>();
  
  constructor(options: CacheOptions = {}) {
    this.options = {
      ttl: options.ttl || 5 * 60 * 1000, // 5 minutes default
      maxSize: options.maxSize || 1000,
      enableVersioning: options.enableVersioning ?? true
    };
    
    // Start cleanup interval
    setInterval(() => this.cleanup(), 60000); // Clean every minute
  }
  
  setDuckDBService(service: DuckDBService) {
    this.duckDBService = service;
    logger.log('[GraphCache] DuckDB service connected');
  }
  
  // Get data with cache
  async get<T>(key: string, fetcher?: () => Promise<T>): Promise<T | null> {
    // Track access for LRU eviction
    this.trackAccess(key);
    
    // Check cache first
    const cached = this.cache.get(key);
    if (cached && !this.isExpired(cached)) {
      logger.log(`[GraphCache] Cache hit for ${key}`);
      return cached.data;
    }
    
    // If no fetcher provided, return null
    if (!fetcher) {
      logger.log(`[GraphCache] Cache miss for ${key}, no fetcher provided`);
      return null;
    }
    
    // Fetch new data
    logger.log(`[GraphCache] Cache miss for ${key}, fetching...`);
    try {
      const data = await fetcher();
      this.set(key, data);
      return data;
    } catch (error) {
      logger.error(`[GraphCache] Error fetching ${key}:`, error);
      // Return stale data if available
      if (cached) {
        logger.log(`[GraphCache] Returning stale data for ${key}`);
        return cached.data;
      }
      throw error;
    }
  }
  
  // Set cache entry
  set<T>(key: string, data: T, version?: string): void {
    // Enforce max size with LRU eviction
    if (this.cache.size >= this.options.maxSize) {
      this.evictLRU();
    }
    
    const entry: CacheEntry<T> = {
      data,
      timestamp: Date.now(),
      version: version || this.generateVersion(),
      etag: this.generateETag(data)
    };
    
    this.cache.set(key, entry);
    
    if (this.options.enableVersioning && entry.version) {
      this.versions.set(key, entry.version);
    }
    
    logger.log(`[GraphCache] Cached ${key} with version ${entry.version}`);
  }
  
  // Invalidate specific keys
  invalidate(keys: string | string[]): void {
    const keysArray = Array.isArray(keys) ? keys : [keys];
    
    keysArray.forEach(key => {
      if (key.includes('*')) {
        // Pattern matching
        const pattern = new RegExp('^' + key.replace(/\*/g, '.*') + '$');
        this.cache.forEach((_, cacheKey) => {
          if (pattern.test(cacheKey)) {
            this.cache.delete(cacheKey);
            this.versions.delete(cacheKey);
            logger.log(`[GraphCache] Invalidated ${cacheKey}`);
          }
        });
      } else {
        this.cache.delete(key);
        this.versions.delete(key);
        logger.log(`[GraphCache] Invalidated ${key}`);
      }
    });
  }
  
  // Clear entire cache
  clear(): void {
    const size = this.cache.size;
    this.cache.clear();
    this.versions.clear();
    this.accessLog.clear();
    logger.log(`[GraphCache] Cleared ${size} entries`);
  }
  
  // Apply delta update from WebSocket
  async applyDeltaUpdate(delta: {
    operation: 'add' | 'update' | 'delete';
    nodes?: any[];
    edges?: any[];
    version?: string;
  }): Promise<void> {
    logger.log(`[GraphCache] Applying delta update: ${delta.operation}`);
    
    // Invalidate affected cache entries
    const affectedKeys: string[] = [];
    
    if (delta.nodes && delta.nodes.length > 0) {
      affectedKeys.push('nodes:*', 'graph:*', 'stats:*');
      delta.nodes.forEach(node => {
        if (node.id) {
          affectedKeys.push(`node:${node.id}`);
        }
      });
    }
    
    if (delta.edges && delta.edges.length > 0) {
      affectedKeys.push('edges:*', 'graph:*', 'stats:*');
      delta.edges.forEach(edge => {
        if (edge.id) {
          affectedKeys.push(`edge:${edge.id}`);
        }
      });
    }
    
    this.invalidate(affectedKeys);
    
    // Apply update to DuckDB if connected
    if (this.duckDBService) {
      await this.duckDBService.applyUpdate({
        operation: delta.operation,
        nodes: delta.nodes,
        edges: delta.edges,
        timestamp: Date.now()
      });
    }
    
    // Update version
    if (delta.version) {
      this.versions.set('global', delta.version);
    }
  }
  
  // Check cache stats
  getStats() {
    const now = Date.now();
    let validEntries = 0;
    let expiredEntries = 0;
    let totalSize = 0;
    
    this.cache.forEach(entry => {
      if (this.isExpired(entry)) {
        expiredEntries++;
      } else {
        validEntries++;
      }
      totalSize += JSON.stringify(entry.data).length;
    });
    
    return {
      totalEntries: this.cache.size,
      validEntries,
      expiredEntries,
      totalSizeBytes: totalSize,
      hitRate: this.calculateHitRate(),
      versions: this.versions.size
    };
  }
  
  // Private methods
  private isExpired(entry: CacheEntry<any>): boolean {
    return Date.now() - entry.timestamp > this.options.ttl;
  }
  
  private cleanup(): void {
    let removed = 0;
    this.cache.forEach((entry, key) => {
      if (this.isExpired(entry)) {
        this.cache.delete(key);
        this.versions.delete(key);
        removed++;
      }
    });
    
    if (removed > 0) {
      logger.log(`[GraphCache] Cleanup removed ${removed} expired entries`);
    }
  }
  
  private evictLRU(): void {
    // Find least recently used key
    let lruKey: string | null = null;
    let oldestAccess = Date.now();
    
    this.cache.forEach((_, key) => {
      const accesses = this.accessLog.get(key) || [];
      const lastAccess = accesses[accesses.length - 1] || 0;
      
      if (lastAccess < oldestAccess) {
        oldestAccess = lastAccess;
        lruKey = key;
      }
    });
    
    if (lruKey) {
      this.cache.delete(lruKey);
      this.versions.delete(lruKey);
      this.accessLog.delete(lruKey);
      logger.log(`[GraphCache] Evicted LRU entry: ${lruKey}`);
    }
  }
  
  private trackAccess(key: string): void {
    const accesses = this.accessLog.get(key) || [];
    accesses.push(Date.now());
    
    // Keep only last 10 accesses
    if (accesses.length > 10) {
      accesses.shift();
    }
    
    this.accessLog.set(key, accesses);
  }
  
  private generateVersion(): string {
    return `v${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  }
  
  private generateETag(data: any): string {
    const str = JSON.stringify(data);
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
      const char = str.charCodeAt(i);
      hash = ((hash << 5) - hash) + char;
      hash = hash & hash; // Convert to 32-bit integer
    }
    return `"${hash.toString(16)}"`;
  }
  
  private calculateHitRate(): number {
    // Simple hit rate calculation based on recent accesses
    let totalAccesses = 0;
    let recentHits = 0;
    
    this.accessLog.forEach(accesses => {
      totalAccesses += accesses.length;
      if (accesses.length > 1) {
        recentHits += accesses.length - 1;
      }
    });
    
    return totalAccesses > 0 ? (recentHits / totalAccesses) * 100 : 0;
  }
}