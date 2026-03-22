import * as arrow from 'apache-arrow';
import { loadDuckDB } from './duckdb-lazy-loader';
import type * as duckdb from '@duckdb/duckdb-wasm';
import { graphCache, type CacheDataItem } from './graph-cache';
import { GraphNode, GraphLink } from '../types/graph';
import { useGraphStore } from '../stores/useGraphStore';

export interface DuckDBConfig {
  rustServerUrl: string;
}

// Update operation for graph changes
interface GraphUpdate {
  operation: 'add_nodes' | 'add_edges' | 'update_nodes' | 'delete_nodes' | 'delete_edges';
  nodes?: GraphNode[];
  edges?: GraphLink[];
}

// Row type from DuckDB queries
interface DuckDBRow {
  toJSON?: () => Record<string, unknown>;
  [key: string]: unknown;
}

export class DuckDBService {
  private db: duckdb.AsyncDuckDB | null = null;
  private conn: duckdb.AsyncDuckDBConnection | null = null;
  private rustServerUrl: string;
  private _initialized = false;
  public readonly nodesTableName = 'nodes';
  public readonly edgesTableName = 'edges';
  
  get initialized(): boolean {
    return this._initialized;
  }

  constructor(config: DuckDBConfig) {
    this.rustServerUrl = config.rustServerUrl;
  }

  async initialize(skipDataLoad: boolean = false): Promise<void> {
    if (this.initialized) {
      console.log('[DuckDB] Already initialized, skipping');
      return;
    }

    try {
      console.log('[DuckDB] Starting parallel initialization...');
      
      // Load DuckDB module lazily
      const duckdb = await loadDuckDB();
      
      // Parallel initialization - start all async operations simultaneously
      const [bundle, dataPromise] = await Promise.all([
        // 1. Select DuckDB bundle
        duckdb.selectBundle(duckdb.getJsDelivrBundles()),
        // 2. Start prefetching data while DuckDB initializes
        skipDataLoad ? Promise.resolve(null) : this.prefetchData()
      ]);
      
      const worker_url = URL.createObjectURL(
        new Blob([`importScripts("${bundle.mainWorker}");`], {
          type: 'application/javascript',
        })
      );

      // Create the worker and logger
      const logger = new duckdb.ConsoleLogger();
      const worker = new Worker(worker_url);
      
      // Instantiate the database
      this.db = new duckdb.AsyncDuckDB(logger, worker);
      await this.db.instantiate(bundle.mainModule, bundle.pthreadWorker);
      
      // Create connection
      this.conn = await this.db.connect();
      
      // Create tables to mirror Rust server structure
      await this.createTables();
      
      // Load the prefetched data if available
      let tablesReady = false;
      if (dataPromise) {
        const loadedFromPrefetch = await this.loadPrefetchedData(dataPromise);
        if (loadedFromPrefetch) {
          tablesReady = await this.ensureGraphTables();
        }
      }

      if (!tablesReady) {
        await this.loadInitialData();
        tablesReady = await this.ensureGraphTables();
      }

      if (!tablesReady) {
        throw new Error('DuckDB graph tables failed to load during initialization');
      }
      
      this._initialized = true;
      console.log('[DuckDB] Service initialized successfully with parallel loading');
    } catch (error) {
      console.error('Failed to initialize DuckDB:', error);
      throw error;
    }
  }
  
  private async prefetchData(): Promise<{ nodes: ArrayBuffer; edges: ArrayBuffer } | null> {
    try {
      // First check if preloader has already fetched the data
      const { preloader } = await import('./preloader');
      const preloadedData = await preloader.getAllPreloadedData();

      // Debug: Log what preloader returned
      console.log('[DuckDB] Preloader data check:', {
        hasNodes: !!preloadedData.nodes,
        hasEdges: !!preloadedData.edges,
        nodesSize: preloadedData.nodes?.byteLength || 0,
        edgesSize: preloadedData.edges?.byteLength || 0,
        timestamp: preloadedData.timestamp
      });

      if (preloadedData.nodes && preloadedData.edges) {
        console.log('[DuckDB] Using preloaded data from preloader service');
        return {
          nodes: preloadedData.nodes,
          edges: preloadedData.edges
        };
      }
      
      // Check cache next
      const cached = await graphCache.getCachedData('arrow-data');
      if (cached && cached.nodes && cached.edges) {
        const isValidCache = cached.metadata?.format === 'arrow' 
          ? cached.nodes.length < 50000000 && cached.edges.length < 50000000
          : cached.nodes.length < 100000 && cached.edges.length < 200000;
        
        if (isValidCache) {
          console.log('[DuckDB] Using cached data');
          // Cast to number[] since we verified format is 'arrow' above
          return { 
            nodes: new Uint8Array(cached.nodes as number[]).buffer,
            edges: new Uint8Array(cached.edges as number[]).buffer
          };
        }
      }
      
      // Prefetch from server in parallel with cache-busting
      console.log('[DuckDB] Prefetching data from server:', this.rustServerUrl);
      const cacheBuster = `?t=${Date.now()}&r=${Math.random().toString(36).substr(2, 9)}&v=${Math.floor(Math.random() * 1000000)}`;
      const startTime = performance.now();

      const [nodesResponse, edgesResponse] = await Promise.all([
        fetch(`${this.rustServerUrl}/api/arrow/nodes${cacheBuster}`, {
          method: 'GET',
          mode: 'cors',
          cache: 'no-cache',
          credentials: 'omit',
          headers: {
            'Accept': 'application/octet-stream',
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'Pragma': 'no-cache',
            'Expires': '0',
            'If-None-Match': '*'
          }
        }),
        fetch(`${this.rustServerUrl}/api/arrow/edges${cacheBuster}`, {
          method: 'GET',
          mode: 'cors',
          cache: 'no-cache',
          credentials: 'omit',
          headers: {
            'Accept': 'application/octet-stream',
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'Pragma': 'no-cache',
            'Expires': '0',
            'If-None-Match': '*'
          }
        })
      ]);

      console.log('[DuckDB] Fetch responses received:', {
        nodesOk: nodesResponse.ok,
        nodesStatus: nodesResponse.status,
        edgesOk: edgesResponse.ok,
        edgesStatus: edgesResponse.status,
        elapsed: (performance.now() - startTime).toFixed(2) + 'ms'
      });

      if (!nodesResponse.ok || !edgesResponse.ok) {
        throw new Error(`Failed to fetch data: nodes=${nodesResponse.status}, edges=${edgesResponse.status}`);
      }

      const [nodesBuffer, edgesBuffer] = await Promise.all([
        nodesResponse.arrayBuffer(),
        edgesResponse.arrayBuffer()
      ]);

      console.log('[DuckDB] Prefetch completed successfully:', {
        nodesSize: (nodesBuffer.byteLength / 1024).toFixed(2) + 'KB',
        edgesSize: (edgesBuffer.byteLength / 1024).toFixed(2) + 'KB',
        totalElapsed: (performance.now() - startTime).toFixed(2) + 'ms'
      });

      return { nodes: nodesBuffer, edges: edgesBuffer };
    } catch (error) {
      console.error('[DuckDB] Prefetch failed:', error);
      return null;
    }
  }
  
  private async loadPrefetchedData(
    dataPromise: { nodes: ArrayBuffer; edges: ArrayBuffer } | null
  ): Promise<boolean> {
    if (!dataPromise || !this.conn) return false;
    
    try {
      const { nodes, edges } = dataPromise;
      
      // Convert to Arrow tables and insert
      const nodesTable = arrow.tableFromIPC(new Uint8Array(nodes));
      const edgesTable = arrow.tableFromIPC(new Uint8Array(edges));
      
      // Insert nodes first
      await this.conn.insertArrowTable(nodesTable, { name: 'nodes' });
      
      // Check how many edges have valid source/target nodes
      const edgeCount = edgesTable.numRows;
      console.log(`[DuckDB] Processing ${edgeCount} edges from Arrow data`);
      
      // Insert edges - the Arrow data should already have sourceidx/targetidx
      await this.conn.insertArrowTable(edgesTable, { name: 'edges' });
      
      // Verify edges with valid nodes
      const validEdges = await this.conn.query(`
        SELECT COUNT(*) as count FROM edges e
        WHERE EXISTS (SELECT 1 FROM nodes WHERE id = e.source)
        AND EXISTS (SELECT 1 FROM nodes WHERE id = e.target)
      `);
      console.log(`[DuckDB] Valid edges (both nodes exist): ${validEdges.get(0)?.count} out of ${edgeCount}`);
      
      // Also create Cosmograph-specific views/tables that map to our data
      // Cosmograph expects cosmograph_points and cosmograph_links tables
      // Map our 'idx' column to 'index' that Cosmograph expects
      // Include all possible columns, using NULL defaults for those that might not exist yet
      await this.conn.query(`CREATE OR REPLACE VIEW cosmograph_points AS
        SELECT
          idx as index,
          id,
          label,
          node_type,
          summary,
          degree_centrality,
          pagerank_centrality,
          betweenness_centrality,
          eigenvector_centrality,
          x,
          y,
          color,
          size,
          created_at_timestamp,
          cluster,
          clusterStrength
        FROM nodes`);
      await this.conn.query(`CREATE OR REPLACE VIEW cosmograph_links AS 
        SELECT 
          source, 
          sourceidx as sourceIndex, 
          target, 
          targetidx as targetIndex, 
          edge_type, 
          weight, 
          color,
          strength
        FROM edges`);
      
      console.log(`[DuckDB] Loaded ${nodesTable.numRows} nodes and ${edgesTable.numRows} edges`);
      
      // Skip caching ArrayBuffer data to avoid conversion issues
      // The preloader already handles caching in memory
      return true;
    } catch (error) {
      console.error('[DuckDB] Failed to load prefetched data:', error);
      return false;
    }
  }

  private async createTables(): Promise<void> {
    if (!this.conn) throw new Error('DuckDB connection not initialized');

    // Drop existing tables in parallel to ensure clean state
    await Promise.all([
      this.conn.query(`DROP TABLE IF EXISTS edges`),
      this.conn.query(`DROP TABLE IF EXISTS nodes`),
      // Also drop Cosmograph-specific tables if they exist
      this.conn.query(`DROP TABLE IF EXISTS cosmograph_points`),
      this.conn.query(`DROP TABLE IF EXISTS cosmograph_links`)
    ]);
    
    // Note: We don't create the tables here anymore
    // They will be created automatically when we insert Arrow data
  }

  private async ensureGraphTables(): Promise<boolean> {
    if (!this.conn) return false;

    try {
      const result = await this.conn.query(`
        SELECT LOWER(table_name) as name
        FROM information_schema.tables
        WHERE LOWER(table_name) IN ('nodes', 'edges')
      `);

      const tableNames = new Set<string>();
      for (let i = 0; i < result.numRows; i++) {
        const name = result.get(i)?.name;
        if (typeof name === 'string') {
          tableNames.add(name);
        }
      }

      return tableNames.has('nodes') && tableNames.has('edges');
    } catch (error) {
      console.error('[DuckDB] Failed to verify graph tables:', error);
      return false;
    }
  }

  private async loadInitialData(): Promise<void> {
    if (!this.conn) throw new Error('DuckDB connection not initialized');

    try {
      // Check cache first
      const cached = await graphCache.getCachedData('arrow-data');
      
      if (cached && cached.nodes && cached.edges) {
        // For Arrow format cache, nodes and edges are byte arrays
        // Don't validate based on array length, that's byte count not node count
        const isValidCache = cached.metadata?.format === 'arrow' 
          ? cached.nodes.length < 50000000 && cached.edges.length < 50000000  // 50MB limit for arrow data
          : cached.nodes.length < 100000 && cached.edges.length < 200000;      // Node/edge count limit for JSON
        
        if (!isValidCache) {
          console.warn('[DuckDB] Cache appears invalid, clearing and fetching fresh data');
          await graphCache.clearCache();
        } else {
          // Load from cache
          console.log('[DuckDB] Loading from cache...');
          
          // Convert cached data back to Arrow tables and insert
          // Cast to number[] since we verified format is 'arrow' above
          const nodesTable = arrow.tableFromIPC(new Uint8Array(cached.nodes as number[]));
          await this.conn.insertArrowTable(nodesTable, { name: 'nodes' });
          
          const edgesTable = arrow.tableFromIPC(new Uint8Array(cached.edges as number[]));
          await this.conn.insertArrowTable(edgesTable, { name: 'edges' });
          
          // Also create Cosmograph-specific views/tables that map to our data
          // Cosmograph expects cosmograph_points and cosmograph_links tables
          // Map our 'idx' column to 'index' that Cosmograph expects
          // Include all possible columns, using NULL defaults for those that might not exist yet
          await this.conn.query(`CREATE OR REPLACE VIEW cosmograph_points AS
            SELECT
              idx as index,
              id,
              label,
              node_type,
              summary,
              degree_centrality,
              pagerank_centrality,
              betweenness_centrality,
              eigenvector_centrality,
              x,
              y,
              color,
              size,
              created_at_timestamp,
              cluster,
              clusterStrength
            FROM nodes`);
          await this.conn.query(`CREATE OR REPLACE VIEW cosmograph_links AS 
            SELECT 
              source, 
              sourceidx as sourceIndex, 
              target, 
              targetidx as targetIndex, 
              edge_type, 
              weight, 
              color,
              CASE 
                WHEN edge_type IN ('entity_entity', 'relates_to') THEN 1.5
                WHEN edge_type IN ('episodic', 'temporal', 'mentioned_in') THEN 0.5
                ELSE 1.0
              END as strength
            FROM edges`);
          
          console.log('[DuckDB] Loaded from cache successfully');
          
          // Get stats to verify
          const nodeCount = await this.conn.query('SELECT COUNT(*) as count FROM nodes');
          const edgeCount = await this.conn.query('SELECT COUNT(*) as count FROM edges');
          console.log(`[DuckDB] Verified: ${nodeCount.get(0)?.count} nodes and ${edgeCount.get(0)?.count} edges`);
          
          // If counts are suspicious, clear cache
          if (nodeCount.get(0)?.count > 50000 || edgeCount.get(0)?.count > 100000) {
            console.warn('[DuckDB] Suspicious data size detected, clearing cache');
            await graphCache.clearCache();
            // Reload
            await this.loadInitialData();
            return;
          }
          return;
        }
      }
      
      console.log('[DuckDB] Cache miss or cleared, fetching from server (streaming)...');
      await this.loadInitialDataStreaming();
    } catch (error) {
      console.error('Failed to load initial data:', error);
      throw error;
    }
  }

  private async loadInitialDataStreaming(): Promise<void> {
    if (!this.conn) throw new Error('DuckDB connection not initialized');

    const BATCH_SIZE = 10000;
    const startTime = performance.now();

    try {
      let cursor = 0;
      let hasMore = true;
      let totalNodes = 0;
      let isFirstNodeChunk = true;

      console.log('[DuckDB] Starting streaming node load...');

      while (hasMore) {
        const url = `${this.rustServerUrl}/api/arrow/nodes?limit=${BATCH_SIZE}&cursor=${cursor}`;
        const response = await fetch(url, {
          cache: 'no-cache',
          headers: { 'Cache-Control': 'no-cache', 'Pragma': 'no-cache' }
        });

        if (!response.ok) {
          throw new Error(`Failed to fetch nodes chunk at cursor=${cursor}: ${response.statusText}`);
        }

        totalNodes = parseInt(response.headers.get('X-Total-Count') || '0', 10);
        hasMore = response.headers.get('X-Has-More') === 'true';
        const nextCursor = response.headers.get('X-Next-Cursor');

        const buffer = await response.arrayBuffer();
        const table = arrow.tableFromIPC(new Uint8Array(buffer));

        await this.conn.insertArrowTable(table, {
          name: 'nodes',
          create: isFirstNodeChunk
        });
        isFirstNodeChunk = false;

        const loaded = Math.min(cursor + BATCH_SIZE, totalNodes);
        console.log(`[DuckDB] Nodes: ${loaded.toLocaleString()} / ${totalNodes.toLocaleString()}`);
        useGraphStore.getState().setStreamingProgress(loaded, totalNodes, 'nodes');

        cursor = nextCursor ? parseInt(nextCursor, 10) : cursor + BATCH_SIZE;

        await new Promise(resolve => setTimeout(resolve, 0));
      }

      cursor = 0;
      hasMore = true;
      let totalEdges = 0;
      let isFirstEdgeChunk = true;

      console.log('[DuckDB] Starting streaming edge load...');

      while (hasMore) {
        const url = `${this.rustServerUrl}/api/arrow/edges?limit=${BATCH_SIZE}&cursor=${cursor}`;
        const response = await fetch(url, {
          cache: 'no-cache',
          headers: { 'Cache-Control': 'no-cache', 'Pragma': 'no-cache' }
        });

        if (!response.ok) {
          throw new Error(`Failed to fetch edges chunk at cursor=${cursor}: ${response.statusText}`);
        }

        totalEdges = parseInt(response.headers.get('X-Total-Count') || '0', 10);
        hasMore = response.headers.get('X-Has-More') === 'true';
        const nextCursor = response.headers.get('X-Next-Cursor');

        const buffer = await response.arrayBuffer();
        const table = arrow.tableFromIPC(new Uint8Array(buffer));

        await this.conn.insertArrowTable(table, {
          name: 'edges',
          create: isFirstEdgeChunk
        });
        isFirstEdgeChunk = false;

        const loaded = Math.min(cursor + BATCH_SIZE, totalEdges);
        console.log(`[DuckDB] Edges: ${loaded.toLocaleString()} / ${totalEdges.toLocaleString()}`);
        useGraphStore.getState().setStreamingProgress(loaded, totalEdges, 'edges');

        cursor = nextCursor ? parseInt(nextCursor, 10) : cursor + BATCH_SIZE;

        await new Promise(resolve => setTimeout(resolve, 0));
      }

      await this.conn.query(`CREATE OR REPLACE VIEW cosmograph_points AS
        SELECT
          idx as index,
          id,
          label,
          node_type,
          summary,
          degree_centrality,
          pagerank_centrality,
          betweenness_centrality,
          eigenvector_centrality,
          x,
          y,
          color,
          size,
          created_at_timestamp,
          cluster,
          clusterStrength
        FROM nodes`);
      await this.conn.query(`CREATE OR REPLACE VIEW cosmograph_links AS 
        SELECT 
          source, 
          sourceidx as sourceIndex, 
          target, 
          targetidx as targetIndex, 
          edge_type, 
          weight, 
          color,
          strength
        FROM edges`);

      useGraphStore.getState().clearStreamingProgress();

      const elapsed = ((performance.now() - startTime) / 1000).toFixed(2);
      console.log(`[DuckDB] Streaming load complete: ${totalNodes} nodes, ${totalEdges} edges in ${elapsed}s`);

    } catch (error) {
      useGraphStore.getState().clearStreamingProgress();
      console.error('[DuckDB] Streaming load failed:', error);
      throw error;
    }
  }

  async applyUpdate(update: GraphUpdate): Promise<void> {
    if (!this.conn) throw new Error('DuckDB connection not initialized');

    const { operation, nodes, edges } = update;

    switch (operation) {
      case 'add_nodes':
        if (nodes && nodes.length > 0) {
          // Get current max index
          const maxIdxResult = await this.conn.query('SELECT COALESCE(MAX(idx), -1) as max_idx FROM nodes');
          let currentIdx = (maxIdxResult.get(0)?.max_idx || -1) + 1;
          
          // Insert new nodes using individual INSERT statements
          for (const node of nodes) {
            const id = String(node.id).replace(/'/g, "''");
            const label = String(node.label || '').replace(/'/g, "''");
            const nodeType = String(node.node_type || '').replace(/'/g, "''");
            const summary = node.summary ? String(node.summary).replace(/'/g, "''") : null;
            const degreeCentrality = node.properties?.degree_centrality || 0;
            const color = String(node.properties?.color || this.getNodeColor(node.node_type)).replace(/'/g, "''");
            const size = node.properties?.size || 10;
            
            await this.conn.query(`
              INSERT INTO nodes (id, idx, label, node_type, summary, degree_centrality, x, y, color, size)
              VALUES ('${id}', ${currentIdx++}, '${label}', '${nodeType}', ${summary ? `'${summary}'` : 'NULL'}, ${degreeCentrality}, NULL, NULL, '${color}', ${size})
            `);
          }
        }
        break;

      case 'add_edges':
        if (edges && edges.length > 0) {
          for (const edge of edges) {
            // Get indices for source and target
            const fromId = String(edge.from).replace(/'/g, "''");
            const toId = String(edge.to).replace(/'/g, "''");
            
            const sourceResult = await this.conn.query(`SELECT idx FROM nodes WHERE id = '${fromId}'`);
            const targetResult = await this.conn.query(`SELECT idx FROM nodes WHERE id = '${toId}'`);
            
            const sourceIdx = sourceResult.get(0)?.idx;
            const targetIdx = targetResult.get(0)?.idx;
            
            if (sourceIdx !== undefined && targetIdx !== undefined) {
              const edgeType = String(edge.edge_type || '').replace(/'/g, "''");
              const weight = edge.weight || 1.0;
              const color = String(this.getEdgeColor(edge.edge_type)).replace(/'/g, "''");
              
              await this.conn.query(`
                INSERT OR IGNORE INTO edges (source, sourceidx, target, targetidx, edge_type, weight, color)
                VALUES ('${fromId}', ${sourceIdx}, '${toId}', ${targetIdx}, '${edgeType}', ${weight}, '${color}')
              `);
            }
          }
        }
        break;

      case 'update_nodes':
        if (nodes && nodes.length > 0) {
          for (const node of nodes) {
            const id = String(node.id).replace(/'/g, "''");
            const label = String(node.label || '').replace(/'/g, "''");
            const summary = node.summary ? String(node.summary).replace(/'/g, "''") : null;
            
            await this.conn.query(`
              UPDATE nodes SET label = '${label}', summary = ${summary ? `'${summary}'` : 'NULL'} WHERE id = '${id}'
            `);
          }
        }
        break;
    }
  }

  async getNodesTable(): Promise<arrow.Table | null> {
    if (!this.conn) throw new Error('DuckDB connection not initialized');
    
    const result = await this.conn.query('SELECT * FROM nodes ORDER BY idx');
    return result;
  }

  async getEdgesTable(): Promise<arrow.Table | null> {
    if (!this.conn) throw new Error('DuckDB connection not initialized');
    
    const result = await this.conn.query('SELECT * FROM edges ORDER BY sourceidx, targetidx');
    return result;
  }

  async updateClusterData(clusterAssignments: (string | number)[], clusterStrengths: number[]): Promise<void> {
    if (!this.conn) throw new Error('DuckDB connection not initialized');
    
    try {
      // First check if cluster columns exist, if not add them
      const tableInfo = await this.conn.query(`PRAGMA table_info('nodes')`);
      const columns = new Set<string>();
      for (let i = 0; i < tableInfo.numRows; i++) {
        columns.add(tableInfo.get(i)?.name as string);
      }
      
      // Add cluster columns if they don't exist
      if (!columns.has('cluster')) {
        console.log('[DuckDB] Adding cluster column to nodes table');
        await this.conn.query(`ALTER TABLE nodes ADD COLUMN cluster VARCHAR`);
      }
      if (!columns.has('clusterStrength')) {
        console.log('[DuckDB] Adding clusterStrength column to nodes table');
        await this.conn.query(`ALTER TABLE nodes ADD COLUMN clusterStrength DOUBLE`);
      }
      
      // Update cluster data for each node
      for (let i = 0; i < clusterAssignments.length; i++) {
        const cluster = String(clusterAssignments[i]).replace(/'/g, "''");
        const strength = clusterStrengths[i];
        
        await this.conn.query(`UPDATE nodes SET cluster = '${cluster}', clusterStrength = ${strength} WHERE idx = ${i}`);
      }
      
      console.log(`[DuckDB] Updated cluster data for ${clusterAssignments.length} nodes`);
    } catch (error) {
      console.error('[DuckDB] Failed to update cluster data:', error);
      throw error;
    }
  }

  async getStats(): Promise<{ nodes: number; edges: number }> {
    if (!this.conn) throw new Error('DuckDB connection not initialized');

    const tablesReady = await this.ensureGraphTables();
    if (!tablesReady) {
      console.warn('[DuckDB] getStats called before graph tables were ready, returning zeros');
      return { nodes: 0, edges: 0 };
    }

    try {
      const nodeResult = await this.conn.query('SELECT COUNT(*) as count FROM nodes');
      const edgeResult = await this.conn.query('SELECT COUNT(*) as count FROM edges');
      
      return {
        nodes: nodeResult.get(0)?.count || 0,
        edges: edgeResult.get(0)?.count || 0,
      };
    } catch (error) {
      console.error('[DuckDB] Failed to read stats:', error);
      return { nodes: 0, edges: 0 };
    }
  }

  async getNodesForUI(limit?: number): Promise<DuckDBRow[]> {
    if (!this.conn) throw new Error('DuckDB connection not initialized');
    
    try {
      const query = limit 
        ? `SELECT * FROM nodes ORDER BY degree_centrality DESC LIMIT ${limit}`
        : 'SELECT * FROM nodes';
      const result = await this.conn.query(query);
      return result ? result.toArray() : [];
    } catch (error) {
      console.error('Failed to get nodes for UI:', error);
      return [];
    }
  }
  
  async getEdgesForUI(nodeIds?: string[]): Promise<DuckDBRow[]> {
    if (!this.conn) throw new Error('DuckDB connection not initialized');
    
    try {
      let query = 'SELECT * FROM edges';
      if (nodeIds && nodeIds.length > 0) {
        const nodeIdList = nodeIds.map(id => `'${id}'`).join(',');
        query = `SELECT * FROM edges WHERE source IN (${nodeIdList}) AND target IN (${nodeIdList})`;
      }
      const result = await this.conn.query(query);
      return result ? result.toArray() : [];
    } catch (error) {
      console.error('Failed to get edges for UI:', error);
      return [];
    }
  }
  
  async searchNodes(searchTerm: string, limit: number = 100): Promise<DuckDBRow[]> {
    if (!this.conn) throw new Error('DuckDB connection not initialized');
    
    try {
      const query = `
        SELECT * FROM nodes 
        WHERE LOWER(label) LIKE LOWER('%${searchTerm}%') 
        OR LOWER(id) LIKE LOWER('%${searchTerm}%')
        LIMIT ${limit}
      `;
      const result = await this.conn.query(query);
      return result ? result.toArray() : [];
    } catch (error) {
      console.error('Failed to search nodes:', error);
      return [];
    }
  }

  getDuckDBConnection(): { duckdb: duckdb.AsyncDuckDB; connection: duckdb.AsyncDuckDBConnection } | null {
    if (!this.db || !this.conn) return null;
    return { duckdb: this.db, connection: this.conn };
  }

  private getNodeColor(nodeType: string): string {
    switch (nodeType) {
      case 'EntityNode':
        return '#4CAF50';
      case 'EpisodicNode':
        return '#2196F3';
      case 'GroupNode':
        return '#FF9800';
      default:
        return '#9E9E9E';
    }
  }

  private getEdgeColor(edgeType: string): string {
    switch (edgeType) {
      case 'RELATES_TO':
        return '#666666';
      case 'MENTIONS':
        return '#999999';
      case 'HAS_MEMBER':
        return '#FF9800';
      default:
        return '#CCCCCC';
    }
  }

  /**
   * Stream query results for progressive loading
   */
  async streamQuery(query: string, onChunk: (chunk: DuckDBRow[]) => void, batchSize = 1000): Promise<void> {
    if (!this.db || !this.conn) {
      throw new Error('Database not initialized');
    }

    try {
      console.log('[DuckDBService] Starting streaming query:', query);
      
      // Execute query and get result
      const result = await this.conn.query(query);
      
      if (!result) {
        console.warn('[DuckDBService] Query returned no results');
        return;
      }

      // Process in batches
      const totalRows = result.numRows;
      let processedRows = 0;
      
      while (processedRows < totalRows) {
        const endRow = Math.min(processedRows + batchSize, totalRows);
        const batch: DuckDBRow[] = [];
        
        // Extract batch of rows
        for (let i = processedRows; i < endRow; i++) {
          const row = result.get(i) as DuckDBRow | null;
          if (row) {
            batch.push(row.toJSON ? row.toJSON() as DuckDBRow : row);
          }
        }
        
        // Send batch to callback
        if (batch.length > 0) {
          onChunk(batch);
        }
        
        processedRows = endRow;
        
        // Yield to prevent blocking
        await new Promise(resolve => setTimeout(resolve, 0));
      }
      
      console.log('[DuckDBService] Streaming completed:', processedRows, 'rows processed');
    } catch (error) {
      console.error('[DuckDBService] Streaming query failed:', error);
      throw error;
    }
  }

  /**
   * Get Arrow buffer for streaming
   */
  async getArrowBuffer(query: string): Promise<ArrayBuffer | null> {
    if (!this.db || !this.conn) {
      console.error('[DuckDBService] Database not initialized');
      return null;
    }

    try {
      console.log('[DuckDBService] Getting Arrow buffer for:', query);
      const result = await this.conn.query(query);
      
      if (!result) {
        return null;
      }

      // Convert to Arrow IPC format using arrow.tableToIPC
      const ipcBuffer = arrow.tableToIPC(result);
      
      console.log('[DuckDBService] Arrow buffer size:', ipcBuffer.byteLength);
      // Cast ArrayBufferLike to ArrayBuffer - safe because Uint8Array.buffer is always a proper ArrayBuffer
      return ipcBuffer.buffer as ArrayBuffer;
    } catch (error) {
      console.error('[DuckDBService] Failed to get Arrow buffer:', error);
      return null;
    }
  }

  async close(): Promise<void> {
    if (this.conn) {
      await this.conn.close();
      this.conn = null;
    }
    if (this.db) {
      await this.db.terminate();
      this.db = null;
    }
    this._initialized = false;
  }
}
