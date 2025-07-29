import React, { useRef, useEffect, useCallback, forwardRef, useImperativeHandle } from 'react';
import { Cosmograph } from '@cosmograph/react';
import type { GraphNode, GraphEdge } from '../types/graph';
import { useGraphData } from '../hooks/useGraphData';
import { useGraphMethods } from '../hooks/useGraphMethods';
import { useCosmographSetup } from '../hooks/useCosmographSetup';
import { useGraphControl } from '../contexts/GraphConfigProvider';
import { logger } from '../utils/logger';

interface GraphCanvasProps {
  nodes: GraphNode[];
  links: GraphEdge[];
  onNodeClick?: (node: GraphNode | null) => void;
  onNodesSelected?: (nodes: GraphNode[]) => void;
  className?: string;
}

export interface GraphCanvasRef {
  zoomIn: () => void;
  zoomOut: () => void;
  fitView: () => void;
  updateDataIncrementally: (nodes: GraphNode[], links: GraphEdge[], runSimulation?: boolean) => Promise<void>;
  addNode: (node: GraphNode, links?: GraphEdge[]) => Promise<void>;
  removeNode: (nodeId: string) => Promise<void>;
  removeNodes: (nodeIds: string[]) => Promise<void>;
  removeLinks: (linkIds: string[]) => Promise<void>;
}

const GraphCanvasNew = forwardRef<GraphCanvasRef, GraphCanvasProps>(({
  nodes,
  links,
  onNodeClick,
  onNodesSelected,
  className = ''
}, ref) => {
  // Refs
  const cosmographRef = useRef<any>(null);
  const selectedNodesRef = useRef<string[]>([]);
  
  // Hooks
  const { setCosmographRef } = useGraphControl();
  const {
    cosmographData,
    currentNodes,
    currentLinks,
    isDataPreparing,
    dataKitError,
    setCurrentNodes,
    setCurrentLinks,
    isIncrementalUpdateRef
  } = useGraphData(nodes, links);
  
  const {
    updateDataIncrementally,
    addNode,
    removeNode,
    removeNodes,
    removeLinks
  } = useGraphMethods({
    cosmographRef,
    currentNodes,
    currentLinks,
    setCurrentNodes,
    setCurrentLinks,
    isIncrementalUpdateRef
  });
  
  const {
    config,
    stableConfig,
    dynamicConfig,
    pointColorStrategy,
    pointColorPalette,
    pointColorFn,
    pointSizeFn,
    cosmographOverrides
  } = useCosmographSetup();
  
  // Log data for debugging
  useEffect(() => {
    if (cosmographData) {
      logger.log('GraphCanvasNew: Data loaded', {
        points: cosmographData.points?.length || 0,
        links: cosmographData.links?.length || 0,
        cosmographConfig: cosmographData.cosmographConfig
      });
      
      // Log sample link to debug
      if (cosmographData.links?.length > 0) {
        logger.log('GraphCanvasNew: Sample link:', cosmographData.links[0]);
        logger.log('GraphCanvasNew: Link indices valid?', {
          sourceIndex: cosmographData.links[0].sourceIndex,
          targetIndex: cosmographData.links[0].targetIndex,
          sourceIndexType: typeof cosmographData.links[0].sourceIndex,
          targetIndexType: typeof cosmographData.links[0].targetIndex
        });
      }
    }
  }, [cosmographData]);
  
  // Set cosmograph ref in context
  useEffect(() => {
    if (cosmographRef.current) {
      setCosmographRef(cosmographRef);
    }
  }, [setCosmographRef]);
  
  // Node click handler
  const handleNodeClick = useCallback((clickedNode: any) => {
    if (!clickedNode) {
      selectedNodesRef.current = [];
      onNodeClick?.(null);
      onNodesSelected?.([]);
      return;
    }
    
    const node = currentNodes.find(n => n.id === clickedNode.id);
    if (!node) return;
    
    // Handle selection
    if (clickedNode.isSelected) {
      selectedNodesRef.current = selectedNodesRef.current.filter(id => id !== node.id);
    } else {
      selectedNodesRef.current = [...selectedNodesRef.current, node.id];
    }
    
    onNodeClick?.(node);
    onNodesSelected?.(currentNodes.filter(n => selectedNodesRef.current.includes(n.id)));
  }, [currentNodes, onNodeClick, onNodesSelected]);
  
  // Zoom methods
  const zoomIn = useCallback(() => {
    if (cosmographRef.current?.getZoomLevel) {
      const currentZoom = cosmographRef.current.getZoomLevel();
      cosmographRef.current.setZoomLevel(currentZoom * 1.5);
    }
  }, []);
  
  const zoomOut = useCallback(() => {
    if (cosmographRef.current?.getZoomLevel) {
      const currentZoom = cosmographRef.current.getZoomLevel();
      cosmographRef.current.setZoomLevel(currentZoom / 1.5);
    }
  }, []);
  
  const fitView = useCallback(() => {
    if (cosmographRef.current?.fitView) {
      cosmographRef.current.fitView();
    }
  }, []);
  
  // Expose methods via ref
  useImperativeHandle(ref, () => ({
    zoomIn,
    zoomOut,
    fitView,
    updateDataIncrementally,
    addNode,
    removeNode,
    removeNodes,
    removeLinks
  }), [zoomIn, zoomOut, fitView, updateDataIncrementally, addNode, removeNode, removeNodes, removeLinks]);
  
  // Loading or error state
  if (isDataPreparing || !cosmographData) {
    return (
      <div className={`flex items-center justify-center ${className}`}>
        <div className="text-center">
          <p className="text-sm text-muted-foreground">
            {isDataPreparing ? 'Preparing graph data...' : 'Loading graph...'}
          </p>
        </div>
      </div>
    );
  }
  
  if (dataKitError) {
    logger.error('GraphCanvas: Data Kit Error:', dataKitError);
  }
  
  if (!cosmographData.points || cosmographData.points.length === 0) {
    return (
      <div className={`flex items-center justify-center ${className}`}>
        <div className="text-center">
          <p className="text-sm">No graph data available</p>
        </div>
      </div>
    );
  }
  
  // Debug logging
  console.log('GraphCanvasNew rendering with:', {
    nodes: cosmographData.points.length,
    links: cosmographData.links.length,
    firstLink: cosmographData.links[0]
  });
  
  // Check if any nodes have x/y positions
  const nodesWithPositions = cosmographData.points.filter(p => p.x !== undefined || p.y !== undefined);
  if (nodesWithPositions.length > 0) {
    console.log('Nodes with positions:', nodesWithPositions.length, 'Sample:', nodesWithPositions[0]);
  }
  
  return (
    <div className={`relative overflow-hidden ${className}`}>
      <Cosmograph
        ref={cosmographRef}
        
        // Data - back to real data
        points={cosmographData.points}
        links={cosmographData.links}
        
        // Point configuration
        pointIdBy="id"
        pointIndexBy="index"
        pointLabelBy="label"
        pointColorBy="node_type"
        
        // Link configuration
        linkSourceBy="source"
        linkSourceIndexBy="sourceIndex"
        linkTargetBy="target"
        linkTargetIndexBy="targetIndex"
        
        // Appearance
        fitViewOnInit={false}
        fitViewDuration={config.fitViewDuration}
        fitViewPadding={config.fitViewPadding}
        backgroundColor={config.backgroundColor}
        
        // Color strategy - simple color for testing
        pointColor="#00FF00"  // Bright green nodes
        
        // Size
        pointSize={cosmographOverrides.pointSize}
        nodeOpacity={cosmographOverrides.nodeOpacity}
        
        // Physics overrides
        enableSimulation={true}  // Turn on physics with adjusted settings
        spaceSize={config.spaceSize}
        randomSeed={config.randomSeed}
        simulationRepulsion={cosmographOverrides.simulationRepulsion}
        simulationRepulsionTheta={config.simulationRepulsionTheta}
        simulationImpulse={config.simulationImpulse}
        simulationLinkSpring={config.linkSpring}
        simulationLinkDistance={cosmographOverrides.simulationLinkDistance}
        simulationLinkDistRandomVariationRange={config.linkDistRandomVariationRange}
        simulationGravity={cosmographOverrides.simulationGravity}
        simulationCenter={cosmographOverrides.simulationCenter}
        simulationFriction={config.friction}
        simulationDecay={config.simulationDecay}
        simulationRepulsionFromMouse={config.mouseRepulsion}
        
        // Simplified link properties - just color and width
        linkColor="#00FFFF"  // Bright cyan for better visibility
        linkOpacity={1.0}  // Full opacity
        linkWidth={3}  // Thicker for visibility
        linkArrows={false}  // No arrows for cleaner look
        renderLinks={true}  // Explicitly enable link rendering
        linkVisibilityDistanceRange={[0, Infinity]}  // Always show links regardless of distance
        linkVisibilityMinTransparency={1.0}  // Never fade
        linkGreyoutOpacity={1.0}  // No greying out
        scaleLinksOnZoom={false}  // Don't scale - keep consistent size
        curvedLinks={false}  // Straight lines for debugging
        useClassicQuadtree={false}  // Use modern rendering
        
        // Events
        onNodeClick={handleNodeClick}
        
        // Performance
        pixelRatio={2.5}
        showFPSMonitor={false}
      />
    </div>
  );
});

GraphCanvasNew.displayName = 'GraphCanvasNew';

export default GraphCanvasNew;
export { GraphCanvasNew };