# Graphiti System Architecture Insights

## Overview

This document provides comprehensive insights into the Graphiti graph visualization system, focusing on the refactored architecture and its integration with Cosmograph, WebSocket-based real-time updates, and performance optimizations.

## System Architecture

### Core Components

#### 1. Graph Rendering Layer
- **Location**: `frontend/src/components/graph-refactored/core/`
- **Primary Component**: `GraphRenderer.tsx` - Pure Cosmograph wrapper
- **Responsibilities**: 
  - Direct Cosmograph integration
  - Canvas rendering management
  - Basic interaction handling

<augment_code_snippet path="frontend/src/components/graph-refactored/core/GraphRenderer.tsx" mode="EXCERPT">
````typescript
export const GraphRenderer = forwardRef<GraphRendererRef, GraphRendererProps>(
  (
    {
      nodes,
      links,
      nodeColor = '#6366f1',
      nodeSize = 4,
      nodeLabel = (node) => node.label || node.id,
      linkColor = '#94a3b8',
      linkWidth = 1,
      onNodeClick,
      onNodeHover,
      onNodeDoubleClick,
      onZoom,
      showFPSMonitor = false,
      simulationGravity = 0,
      simulationRepulsion = 0.5,
      simulationFriction = 0.85,
      pixelRatio = 2,
      initialZoomLevel = 1,
      fitViewOnInit = true
    },
    ref
  ) => {
    const cosmographRef = useRef<CosmographRef>(null);
````
</augment_code_snippet>

#### 2. Data Management Layer
- **Location**: `frontend/src/components/graph-refactored/core/GraphDataManager.tsx`
- **Responsibilities**:
  - Graph data state management
  - Data validation and normalization
  - DuckDB integration for analytics
  - Memory-efficient data updates

<augment_code_snippet path="frontend/src/components/graph-refactored/core/GraphDataManager.tsx" mode="EXCERPT">
````typescript
export const GraphDataManager: React.FC<GraphDataManagerProps> = ({
  children,
  onDataUpdate,
  enableDuckDB = true
}) => {
  const [data, setData] = useState<GraphData | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  
  // Use refs to prevent memory leaks
  const dataRef = useRef<GraphData | null>(null);
  const updateCallbackRef = useRef(onDataUpdate);
````
</augment_code_snippet>

#### 3. Event Management Layer
- **Location**: `frontend/src/components/graph-refactored/core/GraphEventManager.tsx`
- **Features**:
  - Unified event handling
  - Click vs double-click detection
  - Drag threshold detection
  - Memory-efficient listeners

### Feature Components

#### 1. Real-time Delta Processing
- **Location**: `frontend/src/components/graph-refactored/features/DeltaProcessor.tsx`
- **Key Features**:
  - WebSocket connection management
  - Delta queue with batching
  - Automatic reconnection with exponential backoff
  - Conflict resolution

<augment_code_snippet path="frontend/src/components/graph-refactored/features/DeltaProcessor.tsx" mode="EXCERPT">
````typescript
export const DeltaProcessor: React.FC<DeltaProcessorProps> = ({
  wsUrl = 'ws://localhost:3000/ws',
  onDeltaReceived,
  onNodesAdded,
  onNodesUpdated,
  onNodesRemoved,
  onLinksAdded,
  onLinksUpdated,
  onLinksRemoved,
  batchSize = 100,
  batchDelay = 50,
  maxQueueSize = 1000,
  enableAutoReconnect = true
}) => {
````
</augment_code_snippet>

#### 2. Rust WebSocket Integration
- **Location**: `frontend/src/components/graph-refactored/features/RustWebSocketManager.tsx`
- **Features**:
  - High-performance Rust backend integration
  - Batched delta processing
  - Connection health monitoring
  - Latency tracking

#### 3. Performance Monitoring
- **Location**: `frontend/src/components/graph-refactored/features/PerformanceMonitor.tsx`
- **Capabilities**:
  - FPS monitoring
  - Memory usage tracking
  - Adaptive quality adjustment
  - Performance metrics collection

### Utility Systems

#### 1. Memory Management
- **Location**: `frontend/src/components/graph-refactored/utils/memoryUtils.ts`
- **Components**:
  - `MemoryMonitor`: Tracks memory usage and detects leaks
  - `CleanupTracker`: Manages resource cleanup
  - `BatchProcessor`: Batches operations for efficiency

<augment_code_snippet path="frontend/src/components/graph-refactored/utils/memoryUtils.ts" mode="EXCERPT">
````typescript
export class MemoryMonitor {
  private interval: NodeJS.Timeout | null = null;
  private baseline: number = 0;
  
  start(intervalMs: number = 10000): void {
    if (this.interval) return;
    
    // Set baseline
    this.baseline = this.getMemoryUsage();
    
    this.interval = setInterval(() => {
      const current = this.getMemoryUsage();
      const delta = current - this.baseline;
      
      if (delta > 50 * 1024 * 1024) { // 50MB growth
        logger.warn(`MemoryMonitor: High memory growth detected: ${this.formatBytes(delta)}`);
      }
````
</augment_code_snippet>

#### 2. Data Transformation
- **Location**: `frontend/src/components/graph-refactored/utils/transformUtils.ts`
- **Functions**:
  - Node/link data transformation
  - Batch processing utilities
  - Graph data merging for delta updates

<augment_code_snippet path="frontend/src/components/graph-refactored/utils/transformUtils.ts" mode="EXCERPT">
````typescript
// Merge graph data (for delta updates)
export function mergeGraphData(
  current: { nodes: GraphNode[]; links: GraphLink[] },
  updates: { 
    nodesAdded?: GraphNode[];
    nodesUpdated?: GraphNode[];
    nodesRemoved?: string[];
    linksAdded?: GraphLink[];
    linksRemoved?: string[];
  }
): { nodes: GraphNode[]; links: GraphLink[] } {
````
</augment_code_snippet>

## Data Flow Architecture

### 1. Initial Data Loading
```
DuckDB/API → GraphDataManager → transformUtils → GraphRenderer → Cosmograph
```

### 2. Real-time Updates
```
WebSocket → DeltaProcessor → BatchProcessor → mergeGraphData → GraphRenderer
```

### 3. User Interactions
```
Cosmograph Events → GraphEventManager → Feature Components → State Updates
```

## Key Integration Points

### 1. Cosmograph Integration
- **Package**: `@cosmograph/react`
- **Configuration**: Centralized in `GraphRenderer.tsx`
- **Data Format**: Transformed via `transformUtils.ts`

### 2. WebSocket Systems
- **Python WebSocket**: Legacy system (being phased out)
- **Rust WebSocket**: High-performance backend
- **Delta Processing**: Batched updates with conflict resolution

### 3. DuckDB Integration
- **Context**: `DuckDBProvider`
- **Usage**: Analytics and data querying
- **Integration**: Via `GraphDataManager`

## Performance Optimizations

### 1. Memory Management
- Automatic cleanup tracking
- Memory leak detection
- Garbage collection helpers
- Resource pooling

### 2. Rendering Optimizations
- Adaptive quality based on FPS
- Batched updates
- Virtual rendering for large datasets
- Progressive loading

### 3. Data Processing
- Worker pool for heavy computations
- Spatial indexing for collision detection
- Object pooling for frequent allocations

## Current Issues & Solutions

### 1. Cosmograph Incremental Updates
**Problem**: Vector type inference errors and DuckDB schema mismatches
**Location**: Referenced in `COSMOGRAPH_DEBUG_QUERIES.md`
**Solution Approach**: 
- Use refactored `DeltaProcessor` for proper data transformation
- Implement schema validation in `GraphDataManager`

### 2. Memory Leaks
**Solution**: Comprehensive cleanup system in `memoryUtils.ts`
**Features**: 
- Automatic resource tracking
- Cleanup on component unmount
- Memory usage monitoring

### 3. Performance Degradation
**Solution**: Adaptive quality system in `performanceUtils.ts`
**Features**:
- FPS-based quality adjustment
- Automatic simulation pausing
- Progressive rendering

## Development Patterns

### 1. Component Structure
- **Core**: Pure rendering and data management
- **Features**: Specific functionality (selection, clustering, etc.)
- **Utils**: Shared utilities and helpers
- **Hooks**: Reusable state logic

### 2. Error Handling
- Centralized error boundaries
- Graceful degradation
- Comprehensive logging

### 3. Testing Strategy
- Unit tests for utilities
- Integration tests for components
- Performance benchmarks
- Memory leak detection

## Migration Notes

The system has been refactored from a monolithic `GraphCanvas.tsx` to a modular architecture:

- **Old**: Single 3000+ line component
- **New**: Modular components averaging ~120 lines each
- **Benefits**: Better maintainability, testability, and performance
- **Migration**: Gradual replacement with backward compatibility

## Detailed System Analysis

### WebSocket Message Flow

#### 1. Rust WebSocket Manager
<augment_code_snippet path="frontend/src/components/graph-refactored/features/RustWebSocketManager.tsx" mode="EXCERPT">
````typescript
switch (message.type) {
  case 'delta':
    if (fullConfig.batchUpdates) {
      pendingDeltasRef.current.push(message.data as RustDelta);

      // Clear existing batch timeout
      if (batchTimeoutRef.current) {
        clearTimeout(batchTimeoutRef.current);
      }

      // Set new batch timeout
      batchTimeoutRef.current = setTimeout(() => {
        processBatchedDeltas();
      }, fullConfig.batchInterval);
    } else {
      onDelta?.(message.data as RustDelta);
    }
    break;
````
</augment_code_snippet>

#### 2. Delta Processing Pipeline
- **Batching**: Configurable batch size and delay
- **Conflict Resolution**: Timestamp-based ordering
- **Memory Management**: Queue size limits and cleanup

### Data Transformation Pipeline

#### 1. Node Transformation
<augment_code_snippet path="frontend/src/utils/graphDataTransform.ts" mode="EXCERPT">
````typescript
export function transformNodes(nodes: GraphNode[]): TransformedNode[] {
  return nodes.map((node, index) => {
    const createdAt = node.properties?.created_at || node.created_at || node.properties?.created || null;

    // Generate a fallback timestamp for nodes without dates (for timeline functionality)
    // Distribute randomly over the last 90 days
    const timestamp = createdAt
      ? new Date(createdAt).getTime()
      : Date.now() - Math.random() * 90 * 24 * 60 * 60 * 1000;

    const nodeData: TransformedNode = {
      id: String(node.id),
      index: index,
      label: String(node.label || node.id),
      node_type: String(node.node_type || 'Unknown'),
      summary: node.summary || node.properties?.summary,
      created_at: createdAt,
      created_at_timestamp: timestamp,
      // Include centrality metrics from properties
      degree_centrality: node.properties?.degree_centrality,
      betweenness_centrality: node.properties?.betweenness_centrality,
      pagerank_centrality: node.properties?.pagerank_centrality || node.properties?.pagerank,
      eigenvector_centrality: node.properties?.eigenvector_centrality
    };
````
</augment_code_snippet>

#### 2. Link Transformation
<augment_code_snippet path="frontend/src/components/graph-refactored/utils/transformUtils.ts" mode="EXCERPT">
````typescript
// Transform raw link data to GraphLink
export function transformLink(rawLink: any): GraphLink {
  return {
    source: String(rawLink.source || rawLink.from || ''),
    target: String(rawLink.target || rawLink.to || ''),
    from: String(rawLink.from || rawLink.source || ''),
    to: String(rawLink.to || rawLink.target || ''),
    weight: rawLink.weight || rawLink.strength || 1,
    edge_type: rawLink.edge_type || rawLink.type || 'RELATED_TO'
  };
}
````
</augment_code_snippet>

### Performance Monitoring System

#### 1. Adaptive Quality Management
<augment_code_snippet path="frontend/src/components/graph-refactored/GraphCanvasOptimized.tsx" mode="EXCERPT">
````typescript
// Debounced quality adjustment
const [adjustQuality, cleanupQualityDebounce] = debounceWithCleanup((fps: number) => {
  if (!isMounted.current) return;

  const newQuality = adaptiveQuality.current.update(fps);
  setQuality(newQuality);

  if (graphRef.current) {
    // Adjust graph renderer settings based on quality
    if (newQuality < 0.5) {
      graphRef.current.pauseSimulation();
    } else {
      graphRef.current.resumeSimulation();
    }
  }
}, 1000);
````
</augment_code_snippet>

#### 2. Memory Leak Detection
<augment_code_snippet path="frontend/src/components/graph-refactored/utils/memoryUtils.ts" mode="EXCERPT">
````typescript
// Garbage collection helper
export function requestIdleGC(callback?: () => void): void {
  if ('requestIdleCallback' in window) {
    requestIdleCallback(() => {
      // Trigger GC if available (dev tools only)
      if ('gc' in window) {
        (window as any).gc();
      }
      callback?.();
    });
  } else {
    setTimeout(() => {
      callback?.();
    }, 0);
  }
}
````
</augment_code_snippet>

### Integration Patterns

#### 1. Hook-based Data Management
<augment_code_snippet path="frontend/src/hooks/graph/useGraphData.ts" mode="EXCERPT">
````typescript
const applyDelta = useCallback((delta: GraphDelta) => {
  if (!enableDeltaProcessing) return;

  // Store delta in history
  deltaHistoryRef.current.push(delta);
  if (deltaHistoryRef.current.length > maxHistorySize) {
    deltaHistoryRef.current.shift();
  }

  // Apply delta operations in order
  if (delta.removedNodeIds?.length) {
    removeNodes(delta.removedNodeIds);
  }

  if (delta.removedLinkIds?.length) {
    removeLinks(delta.removedLinkIds);
  }

  if (delta.updatedNodes?.size) {
    updateNodes(delta.updatedNodes);
  }

  if (delta.addedNodes?.length) {
    addNodes(delta.addedNodes);
  }

  if (delta.addedLinks?.length) {
    addLinks(delta.addedLinks);
  }
}, [
  enableDeltaProcessing,
  maxHistorySize,
  removeNodes,
  removeLinks,
  updateNodes,
  addNodes,
  addLinks
]);
````
</augment_code_snippet>

#### 2. Context-based State Management
- **DuckDBProvider**: Database integration context
- **RustWebSocketProvider**: WebSocket connection management
- **GraphConfigProvider**: Configuration state management

### Critical System Dependencies

#### 1. External Libraries
- **@cosmograph/react**: Core graph rendering
- **@duckdb/duckdb-wasm**: In-browser analytics database
- **React 18**: Component framework with concurrent features

#### 2. Internal Dependencies
- **Logger System**: Centralized logging with levels
- **Error Boundaries**: Graceful error handling
- **Memory Monitoring**: Leak detection and cleanup

## Technical Challenges & Solutions

### 1. Cosmograph Incremental Update Issues

#### Problem Analysis
The original system faced two critical errors:
- **Vector Type Inference Error**: When calling `addPoints()`
- **DuckDB Schema Mismatch**: When calling `addLinks()` (15 columns expected vs 6 provided)

#### Cosmograph API Methods Available
Based on the official documentation, Cosmograph provides these incremental update methods:

**Adding Data:**
- `addPoints(points): Promise<void>` - Adds new points to the graph
- `addLinks(links): Promise<void>` - Adds new links to the graph

**Removing Data:**
- `removePointsByIndices(indices): Promise<void>` - Remove points by their indices
- `removeLinksByPointIndicesPairs(pairs): Promise<void>` - Remove links by point index pairs
- `removeLinksByPointIdPairs(pairs): Promise<void>` - Remove links by point ID pairs

**Full Data Replacement:**
- `setConfig({ points, links, ...config })` - Replace entire dataset

#### Key Insights from Cosmograph Team
From Discord conversation with Dasha (Cosmograph team):

1. **Data Structure Consistency**: "Adding methods require new data structure to be the same"
2. **Query-based Updates**: For search/filter operations that don't change graph structure, use add/remove methods
3. **Full Replacement**: For structural changes, use `prepareCosmographData()` + `setConfig()`
4. **Performance**: Pre-prepare datasets when possible for faster switching

#### Recommended Implementation Patterns

**Pattern 1: Search/Filter Operations (Incremental)**
```typescript
// For search results that add/remove nodes without changing structure
const handleSearchResults = async (newNodes: GraphNode[], newLinks: GraphLink[]) => {
  // Remove old search results first
  if (currentSearchNodeIndices.length > 0) {
    await cosmographRef.current?.removePointsByIndices(currentSearchNodeIndices);
  }

  // Add new search results
  if (newNodes.length > 0) {
    await cosmographRef.current?.addPoints(newNodes);
    await cosmographRef.current?.addLinks(newLinks);
  }
};
```

**Pattern 2: Full Dataset Replacement (Structural Changes)**
```typescript
// For major data changes or different query types
const handleDatasetChange = async (newData: GraphData) => {
  const { points, links, cosmographConfig } = await prepareCosmographData(
    dataConfig,
    newData.nodes,
    newData.links
  );

  await cosmographRef.current?.setConfig({
    points,
    links,
    ...cosmographConfig
  });
};
```

**Pattern 3: Real-time Delta Updates**
<augment_code_snippet path="frontend/src/components/graph-refactored/features/DeltaProcessor.tsx" mode="EXCERPT">
````typescript
// Process batch of deltas
const processDeltaBatch = useCallback(() => {
  if (isProcessingRef.current || deltaQueueRef.current.length === 0) {
    return;
  }

  isProcessingRef.current = true;

  try {
    const batch = deltaQueueRef.current.splice(0, batchSize);

    // Group deltas by type for efficient processing
    const groupedDeltas = {
      nodesAdded: [] as GraphNode[],
      nodesUpdated: [] as GraphNode[],
      nodesRemoved: [] as string[],
      linksAdded: [] as GraphLink[],
      linksUpdated: [] as GraphLink[],
      linksRemoved: [] as string[]
    };

    // Apply operations in correct order
    if (groupedDeltas.nodesRemoved.length > 0) {
      await cosmographRef.current?.removePointsByIndices(
        groupedDeltas.nodesRemoved.map(id => nodeIndexMap.get(id)).filter(Boolean)
      );
    }

    if (groupedDeltas.nodesAdded.length > 0) {
      await cosmographRef.current?.addPoints(groupedDeltas.nodesAdded);
    }

    if (groupedDeltas.linksAdded.length > 0) {
      await cosmographRef.current?.addLinks(groupedDeltas.linksAdded);
    }
````
</augment_code_snippet>

#### Key Improvements
1. **Proper Data Transformation**: Ensures schema compatibility with `prepareCosmographData()`
2. **Batched Processing**: Reduces API call overhead and improves performance
3. **Type Safety**: TypeScript validation prevents runtime errors
4. **Error Recovery**: Graceful handling of malformed data
5. **Pattern-based Approach**: Different strategies for different use cases

#### Data Preparation Requirements

**Critical Schema Consistency Rule**:
> "Adding methods require new data structure to be the same" - Cosmograph Team

**Proper Data Preparation Workflow:**
```typescript
// 1. Use prepareCosmographData for schema validation
const prepareIncrementalData = async (rawNodes: any[], rawLinks: any[]) => {
  // Transform to consistent format first
  const transformedNodes = transformNodes(rawNodes);
  const transformedLinks = transformLinks(rawLinks);

  // Use Cosmograph's preparation function
  const { points, links, cosmographConfig } = await prepareCosmographData(
    currentDataConfig, // Must match existing config
    transformedNodes,
    transformedLinks
  );

  return { points, links, cosmographConfig };
};

// 2. Validate schema compatibility before adding
const validateSchemaCompatibility = (newPoints: any[], existingConfig: any) => {
  if (!existingConfig.pointIdBy || !existingConfig.linkSourceBy) {
    throw new Error('Missing required configuration for incremental updates');
  }

  // Check that new points have required fields
  const requiredFields = [existingConfig.pointIdBy];
  const hasRequiredFields = newPoints.every(point =>
    requiredFields.every(field => point.hasOwnProperty(field))
  );

  if (!hasRequiredFields) {
    throw new Error('New points missing required fields for current configuration');
  }
};
```

**Schema Debugging Queries** (from original debug document):
```typescript
// Query Cosmograph's internal schema
const debugCosmographSchema = async () => {
  // Points schema
  const pointsSchema = await cosmographRef.current?._duckdb?.query(
    "DESCRIBE cosmograph_points"
  );

  // Links schema
  const linksSchema = await cosmographRef.current?._duckdb?.query(
    "DESCRIBE cosmograph_links"
  );

  // Current configuration
  const config = {
    pointIdBy: cosmographRef.current?.config?.pointIdBy,
    pointIndexBy: cosmographRef.current?.config?.pointIndexBy,
    linkSourceBy: cosmographRef.current?.config?.linkSourceBy,
    linkTargetBy: cosmographRef.current?.config?.linkTargetBy,
  };

  console.log('Schema Debug Info:', {
    pointsSchema,
    linksSchema,
    config
  });
};
```

### 2. Memory Management Challenges

#### Problem
Large graph datasets causing memory leaks and performance degradation.

#### Solution Architecture
<augment_code_snippet path="frontend/src/components/graph-refactored/utils/memoryUtils.ts" mode="EXCERPT">
````typescript
export class CleanupTracker {
  private cleanupFunctions: (() => void)[] = [];
  private isDestroyed = false;

  add(cleanup: () => void): void {
    if (this.isDestroyed) {
      cleanup(); // Execute immediately if already destroyed
      return;
    }
    this.cleanupFunctions.push(cleanup);
  }

  cleanup(): void {
    if (this.isDestroyed) return;

    this.cleanupFunctions.forEach(fn => {
      try {
        fn();
      } catch (error) {
        logger.error('CleanupTracker: Error during cleanup:', error);
      }
    });

    this.cleanupFunctions = [];
    this.isDestroyed = true;
  }
}
````
</augment_code_snippet>

### 3. Real-time Performance Optimization

#### Adaptive Quality System
<augment_code_snippet path="frontend/src/components/graph-refactored/utils/performanceUtils.ts" mode="EXCERPT">
````typescript
export class AdaptiveQuality {
  private fpsHistory: number[] = [];
  private currentQuality = 1.0;
  private readonly maxHistory = 10;
  private readonly targetFPS = 60;

  update(currentFPS: number): number {
    this.fpsHistory.push(currentFPS);
    if (this.fpsHistory.length > this.maxHistory) {
      this.fpsHistory.shift();
    }

    const avgFPS = this.fpsHistory.reduce((a, b) => a + b, 0) / this.fpsHistory.length;

    if (avgFPS < this.targetFPS * 0.8) {
      this.currentQuality = Math.max(0.1, this.currentQuality - 0.1);
    } else if (avgFPS > this.targetFPS * 0.95) {
      this.currentQuality = Math.min(1.0, this.currentQuality + 0.05);
    }

    return this.currentQuality;
  }
}
````
</augment_code_snippet>

### 4. WebSocket Connection Reliability

#### Exponential Backoff Reconnection
<augment_code_snippet path="frontend/src/components/graph-refactored/features/DeltaProcessor.tsx" mode="EXCERPT">
````typescript
// Schedule reconnection with exponential backoff
const scheduleReconnect = useCallback(() => {
  if (reconnectTimerRef.current) {
    clearTimeout(reconnectTimerRef.current);
  }

  const delay = Math.min(1000 * Math.pow(2, reconnectAttemptsRef.current), 30000);
  reconnectAttemptsRef.current++;

  logger.log(`DeltaProcessor: Reconnecting in ${delay}ms (attempt ${reconnectAttemptsRef.current})`);

  reconnectTimerRef.current = setTimeout(() => {
    connect();
  }, delay);
}, [connect]);
````
</augment_code_snippet>

## System Monitoring & Debugging

### 1. Performance Metrics Collection
- **FPS Monitoring**: Real-time frame rate tracking
- **Memory Usage**: Heap size monitoring with alerts
- **WebSocket Health**: Connection status and latency tracking
- **Delta Processing**: Queue size and processing time metrics

### 2. Error Handling Strategy
- **Error Boundaries**: Component-level error isolation
- **Graceful Degradation**: Fallback rendering modes
- **Comprehensive Logging**: Structured logging with context
- **User Feedback**: Non-intrusive error notifications

### 3. Development Tools Integration
- **React DevTools**: Component inspection and profiling
- **Performance API**: Browser performance metrics
- **Memory Profiling**: Heap snapshots and leak detection
- **WebSocket Inspector**: Message flow debugging

## Production Considerations

### 1. Scalability Limits
- **Max Nodes**: 50,000 (configurable)
- **Max Links**: 100,000 (configurable)
- **Batch Size**: 100 deltas per batch
- **Memory Threshold**: 50MB growth triggers warnings

### 2. Browser Compatibility
- **WebGL Support**: Required for Cosmograph rendering
- **WebSocket Support**: Required for real-time updates
- **Performance API**: Optional, graceful degradation
- **RequestIdleCallback**: Optional, setTimeout fallback

### 3. Security Considerations
- **WebSocket Authentication**: Token-based authentication
- **Data Validation**: Input sanitization and type checking
- **Error Information**: Sanitized error messages in production
- **Resource Limits**: Configurable limits to prevent DoS

## Practical Implementation Guide

### 1. Implementing Search-based Graph Updates

Based on the Discord conversation, here's how to implement search functionality:

```typescript
// GraphSearchManager.tsx - New component for search-based updates
export const GraphSearchManager: React.FC<{
  cosmographRef: React.RefObject<CosmographRef>;
  onSearchResults: (results: SearchResults) => void;
}> = ({ cosmographRef, onSearchResults }) => {
  const [currentSearchResults, setCurrentSearchResults] = useState<{
    nodeIndices: number[];
    linkPairs: [number, number][];
  }>({ nodeIndices: [], linkPairs: [] });

  const handleSearch = useCallback(async (query: string) => {
    try {
      // 1. Clear previous search results
      if (currentSearchResults.nodeIndices.length > 0) {
        await cosmographRef.current?.removePointsByIndices(
          currentSearchResults.nodeIndices
        );
      }

      if (currentSearchResults.linkPairs.length > 0) {
        await cosmographRef.current?.removeLinksByPointIndicesPairs(
          currentSearchResults.linkPairs
        );
      }

      // 2. Fetch new search results
      const searchResults = await fetchSearchResults(query);

      // 3. Prepare data with consistent schema
      const { points, links } = await prepareCosmographData(
        getCurrentDataConfig(),
        searchResults.nodes,
        searchResults.links
      );

      // 4. Add new results
      const addedPoints = await cosmographRef.current?.addPoints(points);
      const addedLinks = await cosmographRef.current?.addLinks(links);

      // 5. Track for future cleanup
      setCurrentSearchResults({
        nodeIndices: points.map((_, index) => index), // Track indices
        linkPairs: links.map(link => [link.sourceIndex, link.targetIndex])
      });

      onSearchResults(searchResults);

    } catch (error) {
      logger.error('Search update failed:', error);
      // Fallback: full dataset reload
      await handleFullDatasetReload();
    }
  }, [currentSearchResults, cosmographRef, onSearchResults]);

  return null; // This is a logic-only component
};
```

### 2. Context-based Data Management

Addressing the question about React context usage:

```typescript
// GraphDataContext.tsx - Context for managing graph state
interface GraphDataContextValue {
  currentDataset: GraphData | null;
  searchResults: GraphData | null;
  updateStrategy: 'incremental' | 'full-replace';

  // Methods
  setBaseDataset: (data: GraphData) => Promise<void>;
  applySearchFilter: (query: string) => Promise<void>;
  clearSearch: () => Promise<void>;
  switchDataset: (newData: GraphData) => Promise<void>;
}

export const GraphDataProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [currentDataset, setCurrentDataset] = useState<GraphData | null>(null);
  const [searchResults, setSearchResults] = useState<GraphData | null>(null);
  const cosmographRef = useRef<CosmographRef>(null);

  // Strategy: Use incremental updates for search, full replace for dataset changes
  const applySearchFilter = useCallback(async (query: string) => {
    if (!currentDataset) return;

    try {
      const results = await searchInDataset(currentDataset, query);

      // Use incremental updates for search (same structure)
      await updateGraphIncremental(results);
      setSearchResults(results);

    } catch (error) {
      logger.error('Search filter failed:', error);
    }
  }, [currentDataset]);

  const switchDataset = useCallback(async (newData: GraphData) => {
    try {
      // Use full replacement for dataset changes (structure may differ)
      await updateGraphFullReplace(newData);
      setCurrentDataset(newData);
      setSearchResults(null); // Clear search when switching datasets

    } catch (error) {
      logger.error('Dataset switch failed:', error);
    }
  }, []);

  const value: GraphDataContextValue = {
    currentDataset,
    searchResults,
    updateStrategy: searchResults ? 'incremental' : 'full-replace',
    setBaseDataset: switchDataset,
    applySearchFilter,
    clearSearch: () => applySearchFilter(''), // Reset to full dataset
    switchDataset
  };

  return (
    <GraphDataContext.Provider value={value}>
      {children}
    </GraphDataContext.Provider>
  );
};
```

### 3. Error Recovery and Fallback Strategies

```typescript
// GraphUpdateManager.tsx - Robust update handling
export class GraphUpdateManager {
  private cosmographRef: React.RefObject<CosmographRef>;
  private fallbackStrategy: 'retry' | 'full-reload' | 'graceful-degrade';

  async updateWithFallback(
    updateFn: () => Promise<void>,
    fallbackData?: GraphData
  ): Promise<void> {
    try {
      await updateFn();
    } catch (error) {
      logger.warn('Primary update failed, attempting fallback:', error);

      switch (this.fallbackStrategy) {
        case 'retry':
          await this.retryWithBackoff(updateFn);
          break;

        case 'full-reload':
          if (fallbackData) {
            await this.fullDatasetReload(fallbackData);
          }
          break;

        case 'graceful-degrade':
          // Continue with current data, show user notification
          this.notifyUpdateFailed();
          break;
      }
    }
  }

  private async retryWithBackoff(
    updateFn: () => Promise<void>,
    maxRetries: number = 3
  ): Promise<void> {
    for (let i = 0; i < maxRetries; i++) {
      try {
        await new Promise(resolve => setTimeout(resolve, Math.pow(2, i) * 1000));
        await updateFn();
        return;
      } catch (error) {
        if (i === maxRetries - 1) throw error;
      }
    }
  }
}
```

## Next Steps

1. **Complete Cosmograph Integration**: Implement the patterns above using refactored DeltaProcessor
2. **Schema Validation**: Add runtime schema validation before incremental updates
3. **Performance Optimization**: Implement remaining adaptive features and worker pool optimizations
4. **Testing Coverage**: Expand test suite for all components with focus on memory leak detection
5. **Documentation**: Complete API documentation for all modules and integration patterns
6. **Monitoring**: Implement production monitoring dashboard for system health metrics
