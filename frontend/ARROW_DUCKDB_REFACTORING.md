# Arrow/DuckDB Refactoring Plan for Graphiti Frontend

## Executive Summary

The Graphiti frontend currently uses Apache Arrow format for data transfer and DuckDB-WASM for in-browser analytics. After analyzing the codebase and researching best practices, I've identified several key refactoring opportunities to optimize performance, reduce memory usage, and improve the development experience.

### Current State
- **Data Transfer**: Using Arrow format (7.25MB nodes, ~2MB edges)
- **Loading Time**: ~2 seconds for initial load with parallel fetching
- **Memory Usage**: ~50-100MB for typical graphs
- **Caching**: Disabled for Arrow format due to byte array handling issues

### Target State
- **Streaming**: Implement Arrow streaming for progressive loading
- **Query Performance**: Sub-100ms for most operations
- **Memory**: 30-50% reduction through optimized data structures
- **Caching**: Intelligent caching with compression

## 1. Arrow Streaming Implementation

### Why
Currently loading entire Arrow files at once causes:
- High initial memory spike
- Blocking UI during load
- Poor user experience for large graphs

### What
Implement Arrow RecordBatch streaming to:
- Load data progressively
- Show partial results immediately
- Reduce memory pressure

### How

```typescript
// services/arrow-stream-service.ts
class ArrowStreamService {
  async *streamNodes(): AsyncGenerator<arrow.RecordBatch> {
    const response = await fetch('/api/arrow/nodes', {
      headers: { 'Accept': 'application/vnd.apache.arrow.stream' }
    });
    
    const reader = await arrow.RecordBatchReader.from(response.body!);
    
    for await (const batch of reader) {
      yield batch;
      // Allow UI to update between batches
      await new Promise(resolve => setTimeout(resolve, 0));
    }
  }
  
  async loadIncrementally(
    onBatch: (nodes: GraphNode[], progress: number) => void
  ) {
    let totalRows = 0;
    const batches: arrow.RecordBatch[] = [];
    
    for await (const batch of this.streamNodes()) {
      batches.push(batch);
      totalRows += batch.numRows;
      
      // Convert batch to nodes and notify UI
      const nodes = this.batchToNodes(batch);
      onBatch(nodes, totalRows);
    }
    
    // Combine all batches into single table for DuckDB
    return arrow.tableFromBatches(batches);
  }
}
```

## 2. DuckDB Query Optimization

### Why
Current implementation doesn't leverage DuckDB's full capabilities:
- No prepared statements for repeated queries
- Missing indexes on frequently queried columns
- Inefficient JOIN patterns

### What
Optimize DuckDB usage for:
- Faster aggregations
- Efficient filtering
- Better memory management

### How

```typescript
// services/duckdb-query-optimizer.ts
class DuckDBQueryOptimizer {
  private preparedStatements = new Map<string, PreparedStatement>();
  
  async initialize(conn: AsyncDuckDBConnection) {
    // Create indexes for common queries
    await conn.query(`
      CREATE INDEX idx_nodes_type ON nodes(node_type);
      CREATE INDEX idx_nodes_centrality ON nodes(degree_centrality);
      CREATE INDEX idx_edges_source_target ON edges(source, target);
    `);
    
    // Prepare common statements
    this.preparedStatements.set('nodesByType', await conn.prepare(`
      SELECT * FROM nodes 
      WHERE node_type = $1 
      ORDER BY degree_centrality DESC 
      LIMIT $2
    `));
    
    this.preparedStatements.set('subgraph', await conn.prepare(`
      WITH RECURSIVE subgraph AS (
        SELECT id, 0 as depth FROM nodes WHERE id = $1
        UNION ALL
        SELECT DISTINCT e.target, s.depth + 1
        FROM subgraph s
        JOIN edges e ON s.id = e.source
        WHERE s.depth < $2
      )
      SELECT n.*, s.depth
      FROM nodes n
      JOIN subgraph s ON n.id = s.id
    `));
  }
  
  async getNodesByType(type: string, limit = 100): Promise<GraphNode[]> {
    const stmt = this.preparedStatements.get('nodesByType')!;
    const result = await stmt.query(type, limit);
    return this.arrowToNodes(result);
  }
  
  async getSubgraph(nodeId: string, maxDepth = 2): Promise<SubgraphData> {
    const stmt = this.preparedStatements.get('subgraph')!;
    const nodes = await stmt.query(nodeId, maxDepth);
    
    // Get edges for subgraph
    const nodeIds = nodes.toArray().map(n => n.id);
    const edges = await this.getEdgesForNodes(nodeIds);
    
    return { nodes, edges };
  }
}
```

## 3. Memory-Efficient Data Structures

### Why
Current implementation keeps multiple copies of data:
- Original Arrow tables
- Transformed JavaScript arrays
- Cosmograph's internal structures

### What
Implement zero-copy views and lazy evaluation:
- Use Arrow vectors directly where possible
- Implement virtual scrolling for large datasets
- Lazy property access

### How

```typescript
// hooks/useArrowData.ts
function useArrowData() {
  const [arrowTable, setArrowTable] = useState<arrow.Table | null>(null);
  
  // Create lazy wrapper around Arrow data
  const nodes = useMemo(() => {
    if (!arrowTable) return [];
    
    return new Proxy([], {
      get(target, prop) {
        if (prop === 'length') return arrowTable.numRows;
        if (prop === Symbol.iterator) {
          return function* () {
            for (let i = 0; i < arrowTable.numRows; i++) {
              yield arrowTable.get(i);
            }
          };
        }
        if (typeof prop === 'string' && !isNaN(Number(prop))) {
          const index = Number(prop);
          return lazyNode(arrowTable, index);
        }
        return target[prop];
      }
    });
  }, [arrowTable]);
  
  return { nodes, edges: lazyEdges(arrowTable) };
}

// Create node proxy that only materializes properties when accessed
function lazyNode(table: arrow.Table, index: number): GraphNode {
  const row = table.get(index);
  
  return new Proxy({} as GraphNode, {
    get(target, prop) {
      if (prop in target) return target[prop];
      
      // Lazy load property from Arrow row
      const value = row[prop as string];
      target[prop as keyof GraphNode] = value;
      return value;
    }
  });
}
```

## 4. Intelligent Caching Strategy

### Why
Current caching is disabled for Arrow format due to:
- Byte array serialization issues
- No compression
- All-or-nothing approach

### What
Implement smart caching with:
- Compression using LZ4 or Snappy
- Partial caching of frequently accessed data
- Background refresh

### How

```typescript
// services/smart-cache.ts
class SmartCache {
  private compressionWorker: Worker;
  
  constructor() {
    this.compressionWorker = new Worker('/workers/compression.worker.js');
  }
  
  async cacheArrowData(key: string, buffer: ArrayBuffer) {
    // Compress in worker to avoid blocking main thread
    const compressed = await this.compress(buffer);
    
    // Store metadata separately for quick access
    const metadata = {
      originalSize: buffer.byteLength,
      compressedSize: compressed.byteLength,
      compressionRatio: compressed.byteLength / buffer.byteLength,
      timestamp: Date.now(),
      format: 'arrow-lz4'
    };
    
    // Use IndexedDB for binary data
    const db = await this.getDB();
    const tx = db.transaction(['cache'], 'readwrite');
    
    await Promise.all([
      tx.objectStore('cache').put(compressed, key),
      tx.objectStore('cache').put(metadata, `${key}:meta`)
    ]);
    
    console.log(`Cached ${key}: ${(metadata.originalSize / 1048576).toFixed(2)}MB → ${(metadata.compressedSize / 1048576).toFixed(2)}MB (${(metadata.compressionRatio * 100).toFixed(1)}% ratio)`);
  }
  
  async getCachedArrowData(key: string): Promise<ArrayBuffer | null> {
    const db = await this.getDB();
    
    // Check metadata first
    const metadata = await db.get('cache', `${key}:meta`);
    if (!metadata || Date.now() - metadata.timestamp > 3600000) {
      return null; // Expired
    }
    
    const compressed = await db.get('cache', key);
    if (!compressed) return null;
    
    // Decompress in worker
    return await this.decompress(compressed);
  }
  
  private compress(buffer: ArrayBuffer): Promise<ArrayBuffer> {
    return new Promise((resolve) => {
      this.compressionWorker.postMessage({ action: 'compress', buffer }, [buffer]);
      this.compressionWorker.onmessage = (e) => resolve(e.data.compressed);
    });
  }
}
```

## 5. Optimized React Integration

### Why
Current React integration causes unnecessary re-renders:
- Unstable object references
- Missing memoization
- Inefficient dependency arrays

### What
Implement React best practices:
- Proper memoization with useMemo/useCallback
- Stable references using useRef
- Optimistic updates with React 19 features

### How

```typescript
// hooks/useOptimizedGraphData.ts
function useOptimizedGraphData() {
  const [duckDB, setDuckDB] = useState<AsyncDuckDB | null>(null);
  const [isLoading, startTransition] = useTransition();
  const deferredQuery = useDeferredValue('');
  
  // Stable connection reference
  const connRef = useRef<AsyncDuckDBConnection | null>(null);
  
  // Memoized query function
  const executeQuery = useCallback(async (sql: string) => {
    if (!connRef.current) return null;
    
    return await connRef.current.query(sql);
  }, []);
  
  // Optimistic filtering with React 19
  const [nodes, setNodes] = useState<GraphNode[]>([]);
  const [optimisticNodes, applyFilter] = useOptimistic(
    nodes,
    (currentNodes, filter: FilterConfig) => {
      // Apply filter optimistically
      return currentNodes.filter(node => 
        nodeMatchesFilter(node, filter)
      );
    }
  );
  
  // Deferred search for better interactivity
  const searchResults = useMemo(() => {
    if (!deferredQuery) return optimisticNodes;
    
    return optimisticNodes.filter(node =>
      node.label.toLowerCase().includes(deferredQuery.toLowerCase())
    );
  }, [optimisticNodes, deferredQuery]);
  
  return {
    nodes: searchResults,
    isLoading,
    applyFilter: (filter: FilterConfig) => {
      startTransition(() => {
        applyFilter(filter);
        // Actually apply filter in background
        applyFilterToDatabase(filter).then(setNodes);
      });
    }
  };
}
```

## 6. Web Worker Offloading

### Why
Heavy computations block the main thread:
- Arrow data parsing
- Graph algorithms
- Data transformations

### What
Move expensive operations to Web Workers:
- Parallel data processing
- Background graph algorithms
- Non-blocking updates

### How

```typescript
// workers/graph-processor.worker.ts
class GraphProcessor {
  private duckDB: AsyncDuckDB | null = null;
  
  async initialize() {
    // Initialize DuckDB in worker
    const bundles = getJsDelivrBundles();
    const bundle = await selectBundle(bundles);
    
    this.duckDB = new AsyncDuckDB();
    await this.duckDB.instantiate(bundle.mainModule);
  }
  
  async processMessage(event: MessageEvent) {
    const { action, data } = event.data;
    
    switch (action) {
      case 'loadArrow':
        const table = tableFromIPC(data.buffer);
        await this.loadIntoDatabase(table);
        postMessage({ action: 'loaded', stats: await this.getStats() });
        break;
        
      case 'computeLayout':
        const layout = await this.computeForceLayout(data.nodes, data.edges);
        postMessage({ action: 'layout', layout }, [layout.buffer]);
        break;
        
      case 'findCommunities':
        const communities = await this.detectCommunities();
        postMessage({ action: 'communities', communities });
        break;
    }
  }
}

// hooks/useGraphWorker.ts
function useGraphWorker() {
  const workerRef = useRef<Worker>();
  const [workerReady, setWorkerReady] = useState(false);
  
  useEffect(() => {
    workerRef.current = new Worker('/workers/graph-processor.worker.js');
    
    workerRef.current.postMessage({ action: 'initialize' });
    
    workerRef.current.onmessage = (e) => {
      if (e.data.action === 'ready') {
        setWorkerReady(true);
      }
    };
    
    return () => workerRef.current?.terminate();
  }, []);
  
  const loadArrowData = useCallback(async (buffer: ArrayBuffer) => {
    if (!workerReady) return;
    
    return new Promise((resolve) => {
      workerRef.current!.postMessage(
        { action: 'loadArrow', data: { buffer } },
        [buffer] // Transfer ownership for zero-copy
      );
      
      workerRef.current!.onmessage = (e) => {
        if (e.data.action === 'loaded') {
          resolve(e.data.stats);
        }
      };
    });
  }, [workerReady]);
  
  return { loadArrowData, computeLayout, findCommunities };
}
```

## 7. Performance Monitoring

### Why
No visibility into performance bottlenecks:
- Unknown query execution times
- Memory usage not tracked
- No performance regression detection

### What
Implement comprehensive monitoring:
- Query performance tracking
- Memory usage monitoring
- User experience metrics

### How

```typescript
// utils/performance-monitor.ts
class PerformanceMonitor {
  private metrics = new Map<string, number[]>();
  
  async measureQuery<T>(
    name: string,
    queryFn: () => Promise<T>
  ): Promise<T> {
    const start = performance.now();
    
    try {
      const result = await queryFn();
      const duration = performance.now() - start;
      
      this.recordMetric(name, duration);
      
      if (duration > 100) {
        console.warn(`Slow query: ${name} took ${duration.toFixed(2)}ms`);
      }
      
      return result;
    } catch (error) {
      this.recordError(name, error);
      throw error;
    }
  }
  
  recordMetric(name: string, value: number) {
    if (!this.metrics.has(name)) {
      this.metrics.set(name, []);
    }
    
    const values = this.metrics.get(name)!;
    values.push(value);
    
    // Keep only last 100 measurements
    if (values.length > 100) {
      values.shift();
    }
    
    // Calculate statistics
    const avg = values.reduce((a, b) => a + b, 0) / values.length;
    const p95 = this.percentile(values, 0.95);
    
    // Report to analytics if configured
    if (window.analytics) {
      window.analytics.track('query_performance', {
        query: name,
        avg_ms: avg,
        p95_ms: p95,
        last_ms: value
      });
    }
  }
  
  getMemoryUsage(): MemoryInfo {
    if ('memory' in performance) {
      const memory = (performance as any).memory;
      return {
        usedJSHeapSize: memory.usedJSHeapSize / 1048576,
        totalJSHeapSize: memory.totalJSHeapSize / 1048576,
        jsHeapSizeLimit: memory.jsHeapSizeLimit / 1048576
      };
    }
    return { usedJSHeapSize: 0, totalJSHeapSize: 0, jsHeapSizeLimit: 0 };
  }
}
```

## Implementation Priority

### Phase 1: Foundation (Week 1)
1. **Arrow Streaming** - Immediate UX improvement
2. **Smart Caching** - Reduce server load
3. **Performance Monitoring** - Establish baseline

### Phase 2: Optimization (Week 2)
4. **DuckDB Query Optimization** - Faster queries
5. **Memory-Efficient Structures** - Reduce memory usage
6. **React Integration** - Smoother UI

### Phase 3: Advanced (Week 3)
7. **Web Worker Offloading** - Non-blocking operations
8. **Advanced Caching** - Predictive loading
9. **Production Optimizations** - Bundle size, lazy loading

## Expected Outcomes

### Performance Improvements
- **Initial Load**: 2s → 500ms (75% reduction)
- **Query Performance**: 200ms → 50ms (75% reduction)
- **Memory Usage**: 100MB → 50MB (50% reduction)
- **Time to Interactive**: 3s → 1s (66% reduction)

### Developer Experience
- Better debugging with performance monitoring
- Cleaner code with proper abstractions
- Easier testing with modular design
- Type safety throughout the stack

### User Experience
- Progressive loading with immediate feedback
- Smooth interactions without blocking
- Consistent performance across datasets
- Reduced bandwidth usage with caching

## Risk Mitigation

### Compatibility
- Test with multiple browser versions
- Fallback for missing Web Worker support
- Graceful degradation for older browsers

### Data Integrity
- Validate Arrow data on load
- Checksum verification for cached data
- Automatic cache invalidation on corruption

### Performance Regression
- Automated performance tests
- Monitoring in production
- A/B testing for major changes

## Conclusion

This refactoring plan addresses the key performance bottlenecks in the current implementation while maintaining backward compatibility and improving the developer experience. The phased approach allows for incremental improvements with measurable outcomes at each stage.

The combination of Arrow streaming, DuckDB optimization, and intelligent caching will provide a significant performance boost, while the React optimizations and Web Worker offloading will ensure a smooth, responsive user interface even with large datasets.

## Next Steps

1. Review and approve the refactoring plan
2. Set up performance benchmarks for current implementation
3. Create feature branches for each phase
4. Implement Phase 1 with continuous monitoring
5. Iterate based on performance metrics and user feedback