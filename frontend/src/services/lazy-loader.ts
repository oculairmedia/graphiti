// Lazy loading service for progressive graph data loading
import * as arrow from 'apache-arrow';

export interface LazyLoadConfig {
  initialChunkSize: number;
  chunkSize: number;
  loadThreshold: number; // Distance from viewport edge to trigger load
  maxConcurrentLoads: number;
}

export class LazyLoader {
  private config: LazyLoadConfig;
  private loadingChunks = new Set<string>();
  private loadedChunks = new Map<string, any>();
  private pendingLoads: Promise<void>[] = [];

  constructor(config: Partial<LazyLoadConfig> = {}) {
    this.config = {
      initialChunkSize: 500,
      chunkSize: 250,
      loadThreshold: 100,
      maxConcurrentLoads: 2,
      ...config
    };
  }

  async loadInitialChunk(
    rustServerUrl: string,
    conn: any
  ): Promise<{ nodes: number; edges: number }> {
    console.log('[LazyLoader] Loading initial chunk...');
    
    // Load first chunk with highest centrality nodes
    const response = await fetch(
      `${rustServerUrl}/api/arrow/nodes?limit=${this.config.initialChunkSize}&sort=centrality`
    );
    
    if (!response.ok) {
      throw new Error(`Failed to fetch initial chunk: ${response.statusText}`);
    }
    
    const arrayBuffer = await response.arrayBuffer();
    const nodesTable = arrow.tableFromIPC(new Uint8Array(arrayBuffer));
    
    // Insert into DuckDB
    await conn.insertArrowTable(nodesTable, { name: 'nodes' });
    
    // Get node IDs for edge loading
    const nodeIds: string[] = [];
    for (const batch of nodesTable.batches) {
      const idColumn = batch.getChild('id');
      if (idColumn) {
        for (let i = 0; i < idColumn.length; i++) {
          nodeIds.push(idColumn.get(i));
        }
      }
    }
    
    // Load edges for initial nodes
    const edgesResponse = await fetch(
      `${rustServerUrl}/api/arrow/edges`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ node_ids: nodeIds, limit: this.config.initialChunkSize * 3 })
      }
    );
    
    if (edgesResponse.ok) {
      const edgesBuffer = await edgesResponse.arrayBuffer();
      const edgesTable = arrow.tableFromIPC(new Uint8Array(edgesBuffer));
      await conn.insertArrowTable(edgesTable, { name: 'edges' });
    }
    
    this.loadedChunks.set('initial', { nodeIds });
    
    return {
      nodes: nodeIds.length,
      edges: this.config.initialChunkSize * 3
    };
  }

  async loadChunkByViewport(
    viewport: { x: number; y: number; width: number; height: number; zoom: number },
    rustServerUrl: string,
    conn: any
  ): Promise<boolean> {
    // Calculate chunk ID based on viewport
    const chunkId = this.getChunkId(viewport);
    
    if (this.loadedChunks.has(chunkId) || this.loadingChunks.has(chunkId)) {
      return false; // Already loaded or loading
    }
    
    if (this.loadingChunks.size >= this.config.maxConcurrentLoads) {
      return false; // Too many concurrent loads
    }
    
    this.loadingChunks.add(chunkId);
    
    try {
      // Load nodes in viewport area
      const response = await fetch(
        `${rustServerUrl}/api/arrow/nodes/viewport`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            viewport,
            limit: this.config.chunkSize,
            exclude_loaded: Array.from(this.loadedChunks.values()).flatMap(c => c.nodeIds)
          })
        }
      );
      
      if (response.ok) {
        const arrayBuffer = await response.arrayBuffer();
        const nodesTable = arrow.tableFromIPC(new Uint8Array(arrayBuffer));
        
        // Insert new nodes
        await conn.query(`
          INSERT INTO nodes 
          SELECT * FROM arrow_scan(?)
          WHERE id NOT IN (SELECT id FROM nodes)
        `, [nodesTable]);
        
        // Extract node IDs
        const nodeIds: string[] = [];
        for (const batch of nodesTable.batches) {
          const idColumn = batch.getChild('id');
          if (idColumn) {
            for (let i = 0; i < idColumn.length; i++) {
              nodeIds.push(idColumn.get(i));
            }
          }
        }
        
        this.loadedChunks.set(chunkId, { nodeIds, viewport });
        console.log(`[LazyLoader] Loaded chunk ${chunkId} with ${nodeIds.length} nodes`);
        
        return true;
      }
    } catch (error) {
      console.error(`[LazyLoader] Failed to load chunk ${chunkId}:`, error);
    } finally {
      this.loadingChunks.delete(chunkId);
    }
    
    return false;
  }

  private getChunkId(viewport: { x: number; y: number; width: number; height: number; zoom: number }): string {
    // Create a unique ID based on viewport grid position
    const gridSize = 1000; // Grid cell size
    const gridX = Math.floor(viewport.x / gridSize);
    const gridY = Math.floor(viewport.y / gridSize);
    const zoomLevel = Math.floor(Math.log2(viewport.zoom));
    return `${gridX}_${gridY}_${zoomLevel}`;
  }

  async loadNodeDetails(nodeIds: string[], rustServerUrl: string): Promise<any[]> {
    const response = await fetch(
      `${rustServerUrl}/api/nodes/details`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ node_ids: nodeIds })
      }
    );
    
    if (!response.ok) {
      throw new Error('Failed to load node details');
    }
    
    return response.json();
  }

  clearCache() {
    this.loadedChunks.clear();
    this.loadingChunks.clear();
    this.pendingLoads = [];
  }

  getLoadedNodeCount(): number {
    return Array.from(this.loadedChunks.values())
      .reduce((sum, chunk) => sum + chunk.nodeIds.length, 0);
  }

  isLoading(): boolean {
    return this.loadingChunks.size > 0;
  }
}

export const lazyLoader = new LazyLoader();