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
  private initialized = false;
  public readonly nodesTableName = 'nodes';
  public readonly edgesTableName = 'edges';

  constructor(config: DuckDBConfig) {
    this.rustServerUrl = config.rustServerUrl;
  }

  async initialize(): Promise<void> {
    if (this.initialized) return;

    try {
      // Initialize DuckDB-WASM
      const JSDELIVR_BUNDLES = duckdb.getJsDelivrBundles();
      
      // Select a bundle based on browser checks
      const bundle = await duckdb.selectBundle(JSDELIVR_BUNDLES);
      
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
      
      // Load initial data from Rust server
      await this.loadInitialData();
      
      this.initialized = true;
      console.log('DuckDB service initialized successfully');
    } catch (error) {
      console.error('Failed to initialize DuckDB:', error);
      throw error;
    }
  }

  private async createTables(): Promise<void> {
    if (!this.conn) throw new Error('DuckDB connection not initialized');

    // Drop existing tables if they exist to ensure clean state
    await this.conn.query(`DROP TABLE IF EXISTS edges`);
    await this.conn.query(`DROP TABLE IF EXISTS nodes`);
    
    // Note: We don't create the tables here anymore
    // They will be created automatically when we insert Arrow data
  }

  private async loadInitialData(): Promise<void> {
    if (!this.conn) throw new Error('DuckDB connection not initialized');

    try {
      // Check cache first
      const cached = await graphCache.getCachedData('arrow-data');
      
      if (cached && cached.nodes && cached.edges) {
        // Validate cache size to prevent corruption
        if (cached.nodes.length > 1000000 || cached.edges.length > 1000000) {
          console.warn('[DuckDB] Cache appears corrupted (too large), clearing and fetching fresh data');
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
      
      // Fetch from server
      console.log('[DuckDB] Cache miss or cleared, fetching from server...');
      
      // Fetch nodes data from Rust server
      const nodesResponse = await fetch(`${this.rustServerUrl}/api/arrow/nodes`);
      if (!nodesResponse.ok) {
        throw new Error(`Failed to fetch nodes: ${nodesResponse.statusText}`);
      }
      
      const nodesArrayBuffer = await nodesResponse.arrayBuffer();
      const nodesTable = arrow.tableFromIPC(new Uint8Array(nodesArrayBuffer));
      
      // Insert nodes into DuckDB
      await this.conn.insertArrowTable(nodesTable, { name: 'nodes' });

      // Fetch edges data from Rust server
      const edgesResponse = await fetch(`${this.rustServerUrl}/api/arrow/edges`);
      if (!edgesResponse.ok) {
        throw new Error(`Failed to fetch edges: ${edgesResponse.statusText}`);
      }
      
      const edgesArrayBuffer = await edgesResponse.arrayBuffer();
      const edgesTable = arrow.tableFromIPC(new Uint8Array(edgesArrayBuffer));
      
      // Insert edges into DuckDB
      await this.conn.insertArrowTable(edgesTable, { name: 'edges' });
      
      // Cache the data for next time - store as ArrayBuffer, not array
      // Only cache if size is reasonable
      if (nodesArrayBuffer.byteLength < 10000000 && edgesArrayBuffer.byteLength < 10000000) {
        await graphCache.setCachedData(
          Array.from(new Uint8Array(nodesArrayBuffer)) as any,
          Array.from(new Uint8Array(edgesArrayBuffer)) as any,
          'arrow-data'
        );
      } else {
        console.log('[DuckDB] Data too large to cache, skipping cache storage');
      }

      // Get stats
      const nodeCount = await this.conn.query('SELECT COUNT(*) as count FROM nodes');
      const edgeCount = await this.conn.query('SELECT COUNT(*) as count FROM edges');
      
      console.log(`Loaded ${nodeCount.get(0)?.count} nodes and ${edgeCount.get(0)?.count} edges into DuckDB`);
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

  async close(): Promise<void> {
    if (this.conn) {
      await this.conn.close();
      this.conn = null;
    }
    if (this.db) {
      await this.db.terminate();
      this.db = null;
    }
    this.initialized = false;
  }
}