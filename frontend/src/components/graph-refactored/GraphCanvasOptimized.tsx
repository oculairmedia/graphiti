import React, { useRef, useEffect, useCallback, useState, useMemo } from 'react';
import { GraphNode } from '../../api/types';
import { GraphLink } from '../../types/graph';

// Core components
import GraphRenderer, { GraphRendererRef } from './core/GraphRenderer';

// Hooks
import useGraphData from './hooks/useGraphData';
import useGraphDelta from './hooks/useGraphDelta';

// Utils
import { getNodeColorByType } from './utils/colorUtils';
import { mergeGraphData } from './utils/transformUtils';
import { ResourceManager, useLeakSafe, SafeRAF } from './utils/leakDetector';
import { 
  MemoryMonitor, 
  CleanupTracker, 
  BatchProcessor,
  debounceWithCleanup,
  throttleWithCleanup
} from './utils/memoryUtils';
import { PerformanceMetrics, AdaptiveQuality } from './utils/performanceUtils';
import { logger } from '../../utils/logger';

interface GraphCanvasOptimizedProps {
  wsUrl?: string;
  showFPSMonitor?: boolean;
  enableDelta?: boolean;
  onNodeClick?: (node: GraphNode) => void;
  onSelectionChange?: (nodes: GraphNode[]) => void;
  maxNodes?: number;
  maxLinks?: number;
}

/**
 * GraphCanvasOptimized - Memory-leak-free version with optimizations
 * 
 * Features:
 * - Automatic resource cleanup
 * - Memory leak detection
 * - Batched updates
 * - Adaptive quality
 * - Performance monitoring
 */
export const GraphCanvasOptimized: React.FC<GraphCanvasOptimizedProps> = ({
  wsUrl = 'ws://localhost:3000/ws',
  showFPSMonitor = false,
  enableDelta = true,
  onNodeClick,
  onSelectionChange,
  maxNodes = 50000,
  maxLinks = 100000
}) => {
  // Refs for components and cleanup
  const graphRef = useRef<GraphRendererRef>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const resourceManager = useRef(new ResourceManager());
  const cleanupTracker = useRef(new CleanupTracker());
  const performanceMetrics = useRef(new PerformanceMetrics());
  const adaptiveQuality = useRef(new AdaptiveQuality(30));
  const safeRAF = useRef(new SafeRAF());
  const isMounted = useRef(true);
  
  // Leak-safe lifecycle
  const leakSafe = useLeakSafe('GraphCanvasOptimized');

  // State with proper cleanup
  const [graphData, setGraphData] = useState<{ 
    nodes: GraphNode[]; 
    links: GraphLink[] 
  }>({
    nodes: [],
    links: []
  });
  
  const [quality, setQuality] = useState(1);

  // Batch processor for delta updates
  const deltaProcessor = useMemo(
    () => new BatchProcessor<any>((batch) => {
      if (!isMounted.current) return;
      
      performanceMetrics.current.startMeasure('batchDelta');
      
      setGraphData(prev => {
        // Process all deltas in batch
        let result = prev;
        batch.forEach(delta => {
          result = mergeGraphData(result, delta);
        });
        
        // Enforce limits
        if (result.nodes.length > maxNodes) {
          result.nodes = result.nodes.slice(-maxNodes);
        }
        if (result.links.length > maxLinks) {
          result.links = result.links.slice(-maxLinks);
        }
        
        performanceMetrics.current.endMeasure('batchDelta');
        return result;
      });
    }, 50),
    [maxNodes, maxLinks]
  );

  // Cleanup batch processor
  useEffect(() => {
    return () => {
      deltaProcessor.clear();
    };
  }, [deltaProcessor]);

  // Data fetching with cleanup
  const {
    data: fetchedData,
    isLoading,
    error,
    refresh,
    clearCache
  } = useGraphData({
    autoLoad: true,
    onSuccess: (data) => {
      if (!isMounted.current) return;
      
      performanceMetrics.current.startMeasure('dataLoad');
      setGraphData({
        nodes: data.nodes.slice(0, maxNodes),
        links: data.links.slice(0, maxLinks)
      });
      performanceMetrics.current.endMeasure('dataLoad');
      
      logger.log('GraphCanvasOptimized: Data loaded', {
        nodes: data.nodes.length,
        links: data.links.length
      });
    },
    onError: (err) => {
      logger.error('GraphCanvasOptimized: Data fetch error:', err);
    }
  });

  // WebSocket with proper cleanup
  const { 
    isConnected,
    subscribe: subscribeToDelta,
    disconnect: disconnectWS 
  } = useGraphDelta({
    wsUrl,
    autoConnect: enableDelta,
    onError: (err) => {
      logger.error('GraphCanvasOptimized: WebSocket error:', err);
    }
  });

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

  // Cleanup quality adjustment
  useEffect(() => {
    cleanupTracker.current.add(cleanupQualityDebounce);
  }, [cleanupQualityDebounce]);

  // Throttled node click handler
  const [handleNodeClick, cleanupClickThrottle] = throttleWithCleanup(
    (node: GraphNode | null) => {
      if (!isMounted.current || !node) return;
      
      performanceMetrics.current.startMeasure('nodeClick');
      onNodeClick?.(node);
      performanceMetrics.current.endMeasure('nodeClick');
      
      logger.debug('GraphCanvasOptimized: Node clicked', { id: node.id });
    },
    200
  );

  // Cleanup click handler
  useEffect(() => {
    cleanupTracker.current.add(cleanupClickThrottle);
  }, [cleanupClickThrottle]);

  // Handle delta updates with batching
  const handleDeltaUpdate = useCallback((delta: any) => {
    if (!isMounted.current) return;
    deltaProcessor.add(delta);
  }, [deltaProcessor]);

  // Node coloring with memoization
  const getNodeColor = useCallback((node: GraphNode) => {
    return getNodeColorByType(node.node_type);
  }, []);

  // Node sizing with quality adjustment
  const getNodeSize = useCallback((node: GraphNode) => {
    const baseSize = 4;
    if (quality < 0.5) return baseSize; // Fixed size for low quality
    
    const centrality = (node.properties?.centrality as number) || 0.5;
    return baseSize + centrality * 4 * quality;
  }, [quality]);

  // Initialize with proper cleanup
  useEffect(() => {
    logger.log('GraphCanvasOptimized: Initializing');
    
    // Start memory monitoring in development
    if (process.env.NODE_ENV === 'development') {
      const memoryMonitor = MemoryMonitor.getInstance();
      memoryMonitor.start(5000);
      resourceManager.current.register('memory-monitor', () => {
        memoryMonitor.stop();
      });
    }

    // Subscribe to delta updates
    if (enableDelta) {
      const unsubscribe = subscribeToDelta(handleDeltaUpdate);
      resourceManager.current.register('delta-subscription', unsubscribe);
    }

    // Monitor FPS
    if (showFPSMonitor) {
      let frameCount = 0;
      let lastTime = performance.now();
      
      const measureFPS = () => {
        if (!isMounted.current) return;
        
        const currentTime = performance.now();
        frameCount++;
        
        if (currentTime >= lastTime + 1000) {
          const fps = frameCount;
          frameCount = 0;
          lastTime = currentTime;
          adjustQuality(fps);
        }
        
        safeRAF.current.request(measureFPS);
      };
      
      safeRAF.current.request(measureFPS);
      resourceManager.current.register('fps-monitor', () => {
        safeRAF.current.cancel();
      });
    }

    // Periodic performance report
    const reportInterval = leakSafe.trackInterval(() => {
      if (process.env.NODE_ENV === 'development') {
        logger.debug('GraphCanvasOptimized: Performance Report');
        performanceMetrics.current.logSummary();
      }
    }, 30000);

    return () => {
      logger.log('GraphCanvasOptimized: Cleaning up');
      isMounted.current = false;
      
      // Clean up all resources
      resourceManager.current.cleanup();
      cleanupTracker.current.cleanup();
      deltaProcessor.clear();
      safeRAF.current.cancel();
      leakSafe.cleanup();
      
      // Clear data cache
      clearCache();
      
      // Disconnect WebSocket
      if (isConnected) {
        disconnectWS();
      }
    };
  }, []); // Only run on mount/unmount

  // Memoized graph data to prevent unnecessary re-renders
  const memoizedGraphData = useMemo(
    () => ({
      nodes: graphData.nodes,
      links: graphData.links
    }),
    [graphData.nodes, graphData.links]
  );

  return (
    <div ref={containerRef} className="relative w-full h-full">
      {/* Main Graph Renderer */}
      <GraphRenderer
        ref={graphRef}
        nodes={memoizedGraphData.nodes}
        links={memoizedGraphData.links}
        nodeColor={getNodeColor}
        nodeSize={getNodeSize}
        onNodeClick={handleNodeClick}
        showFPSMonitor={showFPSMonitor}
        fitViewOnInit={true}
        pixelRatio={quality > 0.7 ? 2 : 1}
        simulationFriction={0.85 * quality}
      />

      {/* Loading Overlay */}
      {isLoading && (
        <div className="absolute inset-0 flex items-center justify-center bg-black/50 pointer-events-none">
          <div className="text-white bg-black/80 px-4 py-2 rounded">
            Loading graph data...
          </div>
        </div>
      )}

      {/* Error Display */}
      {error && (
        <div className="absolute top-4 left-4 bg-red-500 text-white p-2 rounded">
          Error: {error.message}
        </div>
      )}

      {/* Performance Indicator */}
      {showFPSMonitor && (
        <div className="absolute bottom-4 right-4 bg-black/80 text-white px-2 py-1 rounded text-xs">
          Quality: {(quality * 100).toFixed(0)}%
          {isConnected && <span className="ml-2 text-green-400">● Live</span>}
        </div>
      )}

      {/* Debug Info in Development */}
      {process.env.NODE_ENV === 'development' && (
        <div className="absolute top-4 right-4 bg-black/80 text-white p-2 rounded text-xs space-y-1">
          <div>Nodes: {memoizedGraphData.nodes.length}</div>
          <div>Links: {memoizedGraphData.links.length}</div>
          <div>Resources: {resourceManager.current.getActiveResources().length}</div>
        </div>
      )}
    </div>
  );
};

export default GraphCanvasOptimized;