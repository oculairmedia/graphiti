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
const CACHE_VERSION = 'v2'; // Increment when schema changes

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
        await this.clearCache();
        return null;
      }
      
      // Check TTL
      const age = Date.now() - cached.timestamp;
      if (age > CACHE_TTL) {
        await this.clearCache();
        return null;
      }
      
      console.log(`[GraphCache] Loaded cached data: ${cached.nodes.length} nodes, ${cached.edges.length} edges (age: ${Math.round(age / 1000)}s)`);
      return cached;
    } catch (error) {
      console.error('Failed to get cached data:', error);
      return null;
    }
  }

  async setCachedData(nodes: any[], edges: any[], key: string = 'default') {
    if (!this.db) await this.initialize();
    if (!this.db) return;

    try {
      await this.db.put('graphData', {
        nodes,
        edges,
        timestamp: Date.now(),
        version: CACHE_VERSION
      }, key);
      
      console.log(`[GraphCache] Cached ${nodes.length} nodes and ${edges.length} edges`);
    } catch (error) {
      console.error('Failed to cache data:', error);
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