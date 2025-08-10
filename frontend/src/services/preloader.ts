/**
 * Preloader Service - Starts fetching critical resources before React initialization
 * This reduces perceived load time by parallelizing network requests with JS parsing
 */

interface PreloadedData {
  nodes: ArrayBuffer | null;
  edges: ArrayBuffer | null;
  config: any | null;
  timestamp: number;
}

class PreloaderService {
  private static instance: PreloaderService;
  private preloadPromises: Map<string, Promise<any>> = new Map();
  private preloadedData: PreloadedData = {
    nodes: null,
    edges: null,
    config: null,
    timestamp: 0
  };
  private rustServerUrl: string;
  
  private constructor() {
    // Get server URL from meta tag or environment
    this.rustServerUrl = this.getServerUrl();
  }
  
  static getInstance(): PreloaderService {
    if (!PreloaderService.instance) {
      PreloaderService.instance = new PreloaderService();
    }
    return PreloaderService.instance;
  }
  
  private getServerUrl(): string {
    // Try to get from meta tag first (can be set in index.html)
    const metaTag = document.querySelector('meta[name="rust-server-url"]');
    if (metaTag) {
      return metaTag.getAttribute('content') || 'http://localhost:3000';
    }
    
    // Fallback to environment variable or default
    return import.meta.env?.VITE_RUST_SERVER_URL || 'http://192.168.50.90:3000';
  }
  
  /**
   * Start preloading critical resources
   * Call this as early as possible (e.g., in index.html)
   */
  startPreloading(): void {
    // Check if data was already preloaded in HTML
    if ((window as any).__PRELOAD_CACHE__) {
      const cache = (window as any).__PRELOAD_CACHE__;
      
      // If we have cached data, use it directly
      if (cache.nodes) {
        console.log('[Preloader] Using early-preloaded nodes data');
        this.preloadedData.nodes = cache.nodes;
        this.preloadPromises.set('nodes', Promise.resolve(cache.nodes));
      } else if (cache.nodesPromise) {
        console.log('[Preloader] Waiting for early-preloaded nodes promise');
        this.preloadPromises.set('nodes', cache.nodesPromise);
        cache.nodesPromise.then((data: ArrayBuffer) => {
          if (data) this.preloadedData.nodes = data;
        });
      }
      
      if (cache.edges) {
        console.log('[Preloader] Using early-preloaded edges data');
        this.preloadedData.edges = cache.edges;
        this.preloadPromises.set('edges', Promise.resolve(cache.edges));
      } else if (cache.edgesPromise) {
        console.log('[Preloader] Waiting for early-preloaded edges promise');
        this.preloadPromises.set('edges', cache.edgesPromise);
        cache.edgesPromise.then((data: ArrayBuffer) => {
          if (data) this.preloadedData.edges = data;
        });
      }
      
      // If we have both promises, we're done
      if (this.preloadPromises.size >= 2) {
        console.log('[Preloader] Using early-preloaded data, skipping network requests');
        this.preloadedData.timestamp = Date.now();
        return;
      }
    }
    
    // Prevent duplicate preloading
    if (this.preloadPromises.size > 0) {
      console.log('[Preloader] Already preloading, skipping duplicate call');
      return;
    }
    
    console.log('[Preloader] Starting resource preloading...');
    const startTime = performance.now();
    
    // Preload graph data (nodes and edges) in parallel
    const nodesPromise = this.preloadResource(
      'nodes',
      `${this.rustServerUrl}/api/arrow/nodes`,
      'arrayBuffer'
    );
    
    const edgesPromise = this.preloadResource(
      'edges', 
      `${this.rustServerUrl}/api/arrow/edges`,
      'arrayBuffer'
    );
    
    // Skip config preload as endpoint doesn't exist
    // Can be re-enabled when config endpoint is implemented
    const configPromise = Promise.resolve({ defaultConfig: true });
    
    // Store promises for later retrieval
    this.preloadPromises.set('nodes', nodesPromise);
    this.preloadPromises.set('edges', edgesPromise);
    this.preloadPromises.set('config', configPromise);
    
    // Log when all preloading completes
    Promise.all([nodesPromise, edgesPromise, configPromise]).then(() => {
      const duration = performance.now() - startTime;
      console.log(`[Preloader] All resources preloaded in ${duration.toFixed(2)}ms`);
    }).catch(error => {
      console.error('[Preloader] Preloading failed:', error);
    });
  }
  
  /**
   * Preload a single resource
   */
  private async preloadResource(
    key: string,
    url: string,
    responseType: 'arrayBuffer' | 'json' | 'text'
  ): Promise<any> {
    try {
      const response = await fetch(url, {
        method: 'GET',
        headers: {
          'Accept': responseType === 'arrayBuffer' 
            ? 'application/octet-stream' 
            : 'application/json'
        },
        // Use high priority for critical resources
        priority: 'high' as any
      });
      
      if (!response.ok) {
        throw new Error(`Failed to fetch ${key}: ${response.statusText}`);
      }
      
      let data: any;
      switch (responseType) {
        case 'arrayBuffer':
          data = await response.arrayBuffer();
          break;
        case 'json':
          data = await response.json();
          break;
        case 'text':
          data = await response.text();
          break;
      }
      
      // Store in preloaded data
      if (key === 'nodes' || key === 'edges') {
        (this.preloadedData as any)[key] = data;
      } else if (key === 'config') {
        this.preloadedData.config = data;
      }
      
      this.preloadedData.timestamp = Date.now();
      
      console.log(`[Preloader] Successfully preloaded ${key}`);
      return data;
    } catch (error) {
      console.error(`[Preloader] Failed to preload ${key}:`, error);
      throw error;
    }
  }
  
  /**
   * Get preloaded data (returns promise that resolves when data is ready)
   */
  async getPreloadedData(key: 'nodes' | 'edges' | 'config'): Promise<any> {
    const promise = this.preloadPromises.get(key);
    if (promise) {
      try {
        return await promise;
      } catch (error) {
        console.warn(`[Preloader] Failed to get preloaded ${key}, will fetch on demand`);
        return null;
      }
    }
    return null;
  }
  
  /**
   * Get all preloaded data at once
   */
  async getAllPreloadedData(): Promise<PreloadedData> {
    try {
      const [nodes, edges, config] = await Promise.all([
        this.getPreloadedData('nodes'),
        this.getPreloadedData('edges'),
        this.getPreloadedData('config')
      ]);
      
      return {
        nodes,
        edges,
        config,
        timestamp: this.preloadedData.timestamp
      };
    } catch (error) {
      console.error('[Preloader] Failed to get all preloaded data:', error);
      return this.preloadedData;
    }
  }
  
  /**
   * Check if data is already preloaded
   */
  isPreloaded(key: 'nodes' | 'edges' | 'config'): boolean {
    return this.preloadPromises.has(key);
  }
  
  /**
   * Clear preloaded data to free memory
   */
  clearPreloadedData(): void {
    this.preloadedData = {
      nodes: null,
      edges: null,
      config: null,
      timestamp: 0
    };
    this.preloadPromises.clear();
    console.log('[Preloader] Cleared preloaded data');
  }
  
  /**
   * Get preload statistics
   */
  getStats(): {
    hasNodes: boolean;
    hasEdges: boolean;
    hasConfig: boolean;
    nodesSize: number;
    edgesSize: number;
    age: number;
  } {
    const now = Date.now();
    return {
      hasNodes: !!this.preloadedData.nodes,
      hasEdges: !!this.preloadedData.edges,
      hasConfig: !!this.preloadedData.config,
      nodesSize: this.preloadedData.nodes?.byteLength || 0,
      edgesSize: this.preloadedData.edges?.byteLength || 0,
      age: this.preloadedData.timestamp ? now - this.preloadedData.timestamp : 0
    };
  }
}

// Export singleton instance
export const preloader = PreloaderService.getInstance();

// Auto-start preloading only once when script is first loaded
if (typeof window !== 'undefined' && !preloader.isPreloaded('nodes')) {
  if (document.readyState === 'loading') {
    // Start preloading immediately if document is still loading
    preloader.startPreloading();
  } else {
    // If document is already loaded, start on next tick
    // This helps even if React hasn't initialized yet
    setTimeout(() => {
      if (!preloader.isPreloaded('nodes')) {
        preloader.startPreloading();
      }
    }, 0);
  }
}