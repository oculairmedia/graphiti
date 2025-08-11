import React, { useRef, useEffect, useCallback, useState } from 'react';
import { GraphNode } from '../../api/types';
import { GraphLink } from '../../types/graph';

// Core components
import GraphRenderer, { GraphRendererRef } from './core/GraphRenderer';
import GraphDataManager from './core/GraphDataManager';
import GraphEventManager from './core/GraphEventManager';

// Feature components
import DeltaProcessor from './features/DeltaProcessor';
import SelectionManager from './features/SelectionManager';
import NodeGlowManager from './features/NodeGlowManager';
import SimulationManager from './features/SimulationManager';
import PopupManager from './features/PopupManager';

// Hooks
import useGraphData from './hooks/useGraphData';
import useGraphDelta from './hooks/useGraphDelta';

// Utils
import { getNodeColorByType, getColorByCentrality } from './utils/colorUtils';
import { mergeGraphData } from './utils/transformUtils';
import { CleanupTracker, MemoryMonitor } from './utils/memoryUtils';
import { PerformanceMetrics } from './utils/performanceUtils';
import { logger } from '../../utils/logger';

interface GraphCanvasProps {
  wsUrl?: string;
  showFPSMonitor?: boolean;
  enableDelta?: boolean;
  enableSelection?: boolean;
  enableGlow?: boolean;
  enableSimulation?: boolean;
  enablePopups?: boolean;
  onNodeClick?: (node: GraphNode) => void;
  onSelectionChange?: (nodes: GraphNode[]) => void;
}

/**
 * GraphCanvas - Thin orchestration layer for the refactored graph components
 * 
 * This component coordinates all the individual pieces without containing
 * any business logic itself. All functionality is delegated to specialized components.
 */
export const GraphCanvas: React.FC<GraphCanvasProps> = ({
  wsUrl = 'ws://localhost:3000/ws',
  showFPSMonitor = false,
  enableDelta = true,
  enableSelection = true,
  enableGlow = true,
  enableSimulation = true,
  enablePopups = true,
  onNodeClick,
  onSelectionChange
}) => {
  const graphRef = useRef<GraphRendererRef>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const cleanupTracker = useRef(new CleanupTracker());
  const performanceMetrics = useRef(new PerformanceMetrics());

  // State
  const [graphData, setGraphData] = useState<{ nodes: GraphNode[]; links: GraphLink[] }>({
    nodes: [],
    links: []
  });

  // Data fetching
  const {
    data: fetchedData,
    isLoading,
    error,
    refresh,
    addNode,
    addLink,
    removeNode
  } = useGraphData({
    autoLoad: true,
    onSuccess: (data) => {
      performanceMetrics.current.startMeasure('dataLoad');
      setGraphData(data);
      performanceMetrics.current.endMeasure('dataLoad');
      logger.log('GraphCanvas: Data loaded', {
        nodes: data.nodes.length,
        links: data.links.length
      });
    }
  });

  // WebSocket delta updates
  const { subscribe: subscribeToDelta } = useGraphDelta({
    wsUrl,
    autoConnect: enableDelta
  });

  // Handle delta updates
  const handleDeltaUpdate = useCallback((updates: any) => {
    performanceMetrics.current.startMeasure('deltaUpdate');
    
    setGraphData(prev => {
      const merged = mergeGraphData(prev, updates);
      performanceMetrics.current.endMeasure('deltaUpdate');
      return merged;
    });
  }, []);

  // Node coloring function
  const getNodeColor = useCallback((node: GraphNode) => {
    return getNodeColorByType(node.node_type);
  }, []);

  // Node sizing function
  const getNodeSize = useCallback((node: GraphNode) => {
    const centrality = (node.properties?.centrality as number) || 0.5;
    return 2 + centrality * 8; // Size between 2-10 based on centrality
  }, []);

  // Initialize components
  useEffect(() => {
    // Start memory monitoring in development
    if (process.env.NODE_ENV === 'development') {
      const memoryMonitor = MemoryMonitor.getInstance();
      memoryMonitor.start();
      cleanupTracker.current.add(() => memoryMonitor.stop());
    }

    // Subscribe to delta updates
    if (enableDelta) {
      const unsubscribe = subscribeToDelta(handleDeltaUpdate);
      cleanupTracker.current.add(unsubscribe);
    }

    return () => {
      cleanupTracker.current.cleanup();
    };
  }, [enableDelta, subscribeToDelta, handleDeltaUpdate]);

  // Handle node click from event manager
  const handleNodeClickInternal = useCallback((node: GraphNode | null) => {
    if (node) {
      onNodeClick?.(node);
      logger.debug('GraphCanvas: Node clicked', { id: node.id });
    }
  }, [onNodeClick]);

  return (
    <div ref={containerRef} className="relative w-full h-full">
      {/* Data Manager */}
      <GraphDataManager
        onDataUpdate={setGraphData}
        enableDuckDB={true}
      >
        {({ data, isLoading: dataLoading }) => (
          <>
            {/* Main Graph Renderer */}
            <GraphRenderer
              ref={graphRef}
              nodes={graphData.nodes}
              links={graphData.links}
              nodeColor={getNodeColor}
              nodeSize={getNodeSize}
              onNodeClick={handleNodeClickInternal}
              showFPSMonitor={showFPSMonitor}
              fitViewOnInit={true}
            />

            {/* Event Management */}
            {containerRef.current && (
              <GraphEventManager
                targetElement={containerRef.current}
                onNodeClick={handleNodeClickInternal}
              />
            )}

            {/* Delta Processing */}
            {enableDelta && (
              <DeltaProcessor
                wsUrl={wsUrl}
                onNodesAdded={(nodes) => nodes.forEach(addNode)}
                onLinksAdded={(links) => links.forEach(addLink)}
                onNodesRemoved={(ids) => ids.forEach(removeNode)}
              />
            )}

            {/* Selection Management */}
            {enableSelection && (
              <SelectionManager
                nodes={graphData.nodes}
                onSelectionChange={onSelectionChange}
                enableKeyboardShortcuts={true}
                persistSelection={true}
              />
            )}

            {/* Node Glow Effects */}
            {enableGlow && (
              <NodeGlowManager
                nodes={graphData.nodes}
                onGlowUpdate={(glowingNodes) => {
                  // Could update renderer with glowing nodes
                  logger.debug('GraphCanvas: Glow update', {
                    count: glowingNodes.size
                  });
                }}
              />
            )}

            {/* Physics Simulation */}
            {enableSimulation && (
              <SimulationManager
                onConfigChange={(config) => {
                  // Could update renderer with new physics config
                  logger.debug('GraphCanvas: Simulation config changed', config);
                }}
                autoStart={true}
              />
            )}

            {/* Popup Management */}
            {enablePopups && (
              <PopupManager
                onPopupShow={(popup) => {
                  logger.debug('GraphCanvas: Popup shown', popup);
                }}
                showDelay={500}
                autoHide={true}
              />
            )}

            {/* Loading Overlay */}
            {(isLoading || dataLoading) && (
              <div className="absolute inset-0 flex items-center justify-center bg-black/50">
                <div className="text-white">Loading graph data...</div>
              </div>
            )}

            {/* Error Display */}
            {error && (
              <div className="absolute top-4 left-4 bg-red-500 text-white p-2 rounded">
                Error: {error.message}
              </div>
            )}
          </>
        )}
      </GraphDataManager>
    </div>
  );
};

export default GraphCanvas;