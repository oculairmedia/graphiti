// IndexedDB caching for graph data
import { openDB, DBSchema, IDBPDatabase } from 'idb';

interface GraphCacheDB extends DBSchema {
  graphData: {
    key: string;
    value: {
      nodes: any[];
      edges: any[];
      timestamp: number;
      version: string;
    };
  };
}

const DB_NAME = 'GraphitiCache';
const DB_VERSION = 1;
const CACHE_TTL = 3600000; // 1 hour
const CACHE_VERSION = 'v3'; // Increment when schema changes - v3 fixes corruption

class GraphCache {
  private db: IDBPDatabase<GraphCacheDB> | null = null;

  async initialize() {
    try {
      this.db = await openDB<GraphCacheDB>(DB_NAME, DB_VERSION, {
        upgrade(db) {
          if (!db.objectStoreNames.contains('graphData')) {
            db.createObjectStore('graphData');
          }
        },
      });
    } catch (error) {
      console.error('Failed to initialize IndexedDB:', error);
    }
  }

  async getCachedData(key: string = 'default') {
    if (!this.db) await this.initialize();
    if (!this.db) return null;

    try {
      const cached = await this.db.get('graphData', key);
      
      if (!cached) return null;
      
      // Check version
      if (cached.version !== CACHE_VERSION) {
        console.log('[GraphCache] Cache version mismatch, clearing cache');
        await this.clearCache();
        return null;
      }
      
      // Check TTL
      const age = Date.now() - cached.timestamp;
      if (age > CACHE_TTL) {
        console.log('[GraphCache] Cache expired, clearing cache');
        await this.clearCache();
        return null;
      }
      
      // Validate cache size - detect corruption
      if (!Array.isArray(cached.nodes) || !Array.isArray(cached.edges)) {
        console.error('[GraphCache] Cache data is not in expected format, clearing cache');
        await this.clearCache();
        return null;
      }
      
      // Check for suspiciously large cache (corruption indicator)
      if (cached.nodes.length > 100000 || cached.edges.length > 200000) {
        console.error(`[GraphCache] Cache appears corrupted: ${cached.nodes.length} nodes, ${cached.edges.length} edges. Clearing cache.`);
        await this.clearCache();
        return null;
      }
      
      console.log(`[GraphCache] Loaded cached data: ${cached.nodes.length} nodes, ${cached.edges.length} edges (age: ${Math.round(age / 1000)}s)`);
      return cached;
    } catch (error) {
      console.error('Failed to get cached data:', error);
      // Clear cache on error to prevent recurring issues
      await this.clearCache();
      return null;
    }
  }

  async setCachedData(nodes: any[], edges: any[], key: string = 'default') {
    if (!this.db) await this.initialize();
    if (!this.db) return;

    try {
      // Validate data before caching
      if (!Array.isArray(nodes) || !Array.isArray(edges)) {
        console.error('[GraphCache] Invalid data format, not caching');
        return;
      }
      
      // Don't cache suspiciously large data
      if (nodes.length > 50000 || edges.length > 100000) {
        // Check if this is actually byte length being passed as array length
        if (nodes.length > 1000000 || edges.length > 1000000) {
          console.warn(`[GraphCache] Data appears to be byte array, not nodes/edges array: ${(nodes.length / 1048576).toFixed(2)}MB nodes, ${(edges.length / 1048576).toFixed(2)}MB edges`);
        } else {
          console.warn(`[GraphCache] Data too large to cache: ${nodes.length} items in nodes array, ${edges.length} items in edges array`);
        }
        return;
      }
      
      // Check individual item size (rough estimate)
      const sampleSize = JSON.stringify(nodes.slice(0, 10)).length;
      const estimatedSize = (sampleSize / 10) * nodes.length;
      if (estimatedSize > 50000000) { // 50MB limit
        console.warn('[GraphCache] Estimated cache size too large, not caching');
        return;
      }
      
      await this.db.put('graphData', {
        nodes,
        edges,
        timestamp: Date.now(),
        version: CACHE_VERSION
      }, key);
      
      console.log(`[GraphCache] Cached ${nodes.length} nodes and ${edges.length} edges`);
    } catch (error) {
      console.error('Failed to cache data:', error);
      // Don't clear cache here, just skip this cache operation
    }
  }

  async clearCache() {
    if (!this.db) await this.initialize();
    if (!this.db) return;

    try {
      const tx = this.db.transaction('graphData', 'readwrite');
      await tx.objectStore('graphData').clear();
      console.log('[GraphCache] Cache cleared');
    } catch (error) {
      console.error('Failed to clear cache:', error);
    }
  }
}

export const graphCache = new GraphCache();