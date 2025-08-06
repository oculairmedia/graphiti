import * as duckdb from '@duckdb/duckdb-wasm';
import * as arrow from 'apache-arrow';
import { graphCache } from './graph-cache';

export interface DuckDBConfig {
  rustServerUrl: string;
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
      if (dataPromise) {
        await this.loadPrefetchedData(dataPromise);
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
          return { 
            nodes: new Uint8Array(cached.nodes).buffer,
            edges: new Uint8Array(cached.edges).buffer
          };
        }
      }
      
      // Prefetch from server in parallel
      console.log('[DuckDB] Prefetching data from server...');
      const [nodesResponse, edgesResponse] = await Promise.all([
        fetch(`${this.rustServerUrl}/api/arrow/nodes`),
        fetch(`${this.rustServerUrl}/api/arrow/edges`)
      ]);
      
      if (!nodesResponse.ok || !edgesResponse.ok) {
        throw new Error('Failed to fetch data');
      }
      
      const [nodesBuffer, edgesBuffer] = await Promise.all([
        nodesResponse.arrayBuffer(),
        edgesResponse.arrayBuffer()
      ]);
      
      return { nodes: nodesBuffer, edges: edgesBuffer };
    } catch (error) {
      console.error('[DuckDB] Prefetch failed:', error);
      return null;
    }
  }
  
  private async loadPrefetchedData(dataPromise: { nodes: ArrayBuffer; edges: ArrayBuffer } | null): Promise<void> {
    if (!dataPromise || !this.conn) return;
    
    try {
      const { nodes, edges } = dataPromise;
      
      // Convert to Arrow tables and insert
      const nodesTable = arrow.tableFromIPC(new Uint8Array(nodes));
      const edgesTable = arrow.tableFromIPC(new Uint8Array(edges));
      
      await Promise.all([
        this.conn.insertArrowTable(nodesTable, { name: 'nodes' }),
        this.conn.insertArrowTable(edgesTable, { name: 'edges' })
      ]);
      
      console.log(`[DuckDB] Loaded ${nodesTable.numRows} nodes and ${edgesTable.numRows} edges`);
      
      // Cache for next time
      await graphCache.setCachedData('arrow-data', {
        nodes: Array.from(new Uint8Array(nodes)),
        edges: Array.from(new Uint8Array(edges)),
        metadata: { format: 'arrow', timestamp: Date.now() }
      });
    } catch (error) {
      console.error('[DuckDB] Failed to load prefetched data:', error);
    }
  }

  private async createTables(): Promise<void> {
    if (!this.conn) throw new Error('DuckDB connection not initialized');

    // Drop existing tables in parallel to ensure clean state
    await Promise.all([
      this.conn.query(`DROP TABLE IF EXISTS edges`),
      this.conn.query(`DROP TABLE IF EXISTS nodes`)
    ]);
    
    // Note: We don't create the tables here anymore
    // They will be created automatically when we insert Arrow data
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
          const nodesTable = arrow.tableFromIPC(new Uint8Array(cached.nodes));
          await this.conn.insertArrowTable(nodesTable, { name: 'nodes' });
          
          const edgesTable = arrow.tableFromIPC(new Uint8Array(cached.edges));
          await this.conn.insertArrowTable(edgesTable, { name: 'edges' });
          
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
      
      // Fetch from server - PARALLEL loading for speed
      console.log('[DuckDB] Cache miss or cleared, fetching from server (parallel)...');
      
      // Fetch nodes and edges in PARALLEL
      const [nodesResponse, edgesResponse] = await Promise.all([
        fetch(`${this.rustServerUrl}/api/arrow/nodes`),
        fetch(`${this.rustServerUrl}/api/arrow/edges`)
      ]);
      
      if (!nodesResponse.ok) {
        throw new Error(`Failed to fetch nodes: ${nodesResponse.statusText}`);
      }
      if (!edgesResponse.ok) {
        throw new Error(`Failed to fetch edges: ${edgesResponse.statusText}`);
      }
      
      // Process responses in PARALLEL
      const [nodesArrayBuffer, edgesArrayBuffer] = await Promise.all([
        nodesResponse.arrayBuffer(),
        edgesResponse.arrayBuffer()
      ]);
      
      // Convert to Arrow tables
      const nodesTable = arrow.tableFromIPC(new Uint8Array(nodesArrayBuffer));
      const edgesTable = arrow.tableFromIPC(new Uint8Array(edgesArrayBuffer));
      
      // Insert both tables (can't parallelize DuckDB inserts)
      await this.conn.insertArrowTable(nodesTable, { name: 'nodes' });
      await this.conn.insertArrowTable(edgesTable, { name: 'edges' });
      
      // Get stats
      const nodeCount = await this.conn.query('SELECT COUNT(*) as count FROM nodes');
      const edgeCount = await this.conn.query('SELECT COUNT(*) as count FROM edges');
      
      console.log(`Loaded ${nodeCount.get(0)?.count} nodes and ${edgeCount.get(0)?.count} edges into DuckDB`);
      
      // For now, skip caching Arrow format data to avoid the byte array issue
      // TODO: Implement proper binary data caching if needed
      console.log(`[DuckDB] Arrow format data (${(nodesArrayBuffer.byteLength / 1048576).toFixed(2)}MB nodes, ${(edgesArrayBuffer.byteLength / 1048576).toFixed(2)}MB edges) - caching disabled for binary format`);
      
      // Note: We could implement binary caching in the future by:
      // 1. Storing ArrayBuffers directly in IndexedDB (supported)
      // 2. Or parsing Arrow format to JavaScript objects before caching
      // For now, we rely on the browser's disk cache for the Arrow files
    } catch (error) {
      console.error('Failed to load initial data:', error);
      throw error;
    }
  }

  async applyUpdate(update: any): Promise<void> {
    if (!this.conn) throw new Error('DuckDB connection not initialized');

    const { operation, nodes, edges } = update;

    switch (operation) {
      case 'add_nodes':
        if (nodes && nodes.length > 0) {
          // Get current max index
          const maxIdxResult = await this.conn.query('SELECT COALESCE(MAX(idx), -1) as max_idx FROM nodes');
          let currentIdx = (maxIdxResult.get(0)?.max_idx || -1) + 1;
          
          // Insert new nodes
          const stmt = await this.conn.prepare(`
            INSERT INTO nodes (id, idx, label, node_type, summary, degree_centrality, x, y, color, size)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
          `);
          
          for (const node of nodes) {
            await stmt.run(
              node.id,
              currentIdx++,
              node.label,
              node.node_type,
              node.summary || null,
              node.properties?.degree_centrality || 0,
              null, // x
              null, // y
              node.properties?.color || this.getNodeColor(node.node_type),
              node.properties?.size || 10
            );
          }
        }
        break;

      case 'add_edges':
        if (edges && edges.length > 0) {
          const stmt = await this.conn.prepare(`
            INSERT OR IGNORE INTO edges (source, sourceidx, target, targetidx, edge_type, weight, color)
            VALUES (?, ?, ?, ?, ?, ?, ?)
          `);
          
          for (const edge of edges) {
            // Get indices for source and target
            const sourceResult = await this.conn.query(
              'SELECT idx FROM nodes WHERE id = ?',
              edge.from
            );
            const targetResult = await this.conn.query(
              'SELECT idx FROM nodes WHERE id = ?',
              edge.to
            );
            
            const sourceIdx = sourceResult.get(0)?.idx;
            const targetIdx = targetResult.get(0)?.idx;
            
            if (sourceIdx !== undefined && targetIdx !== undefined) {
              await stmt.run(
                edge.from,
                sourceIdx,
                edge.to,
                targetIdx,
                edge.edge_type,
                edge.weight || 1.0,
                this.getEdgeColor(edge.edge_type)
              );
            }
          }
        }
        break;

      case 'update_nodes':
        if (nodes && nodes.length > 0) {
          const stmt = await this.conn.prepare(`
            UPDATE nodes SET label = ?, summary = ? WHERE id = ?
          `);
          
          for (const node of nodes) {
            await stmt.run(node.label, node.summary || null, node.id);
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

  async getStats(): Promise<{ nodes: number; edges: number }> {
    if (!this.conn) throw new Error('DuckDB connection not initialized');
    
    const nodeResult = await this.conn.query('SELECT COUNT(*) as count FROM nodes');
    const edgeResult = await this.conn.query('SELECT COUNT(*) as count FROM edges');
    
    return {
      nodes: nodeResult.get(0)?.count || 0,
      edges: edgeResult.get(0)?.count || 0,
    };
  }

  async getNodesForUI(limit?: number): Promise<any[]> {
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
  
  async getEdgesForUI(nodeIds?: string[]): Promise<any[]> {
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
  
  async searchNodes(searchTerm: string, limit: number = 100): Promise<any[]> {
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
  async streamQuery(query: string, onChunk: (chunk: any[]) => void, batchSize = 1000): Promise<void> {
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
        const batch: any[] = [];
        
        // Extract batch of rows
        for (let i = processedRows; i < endRow; i++) {
          const row = result.get(i);
          if (row) {
            batch.push(row.toJSON ? row.toJSON() : row);
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

      // Convert to Arrow IPC format
      const table = result;
      const buffer = table.serialize();
      
      console.log('[DuckDBService] Arrow buffer size:', buffer.byteLength);
      return buffer;
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