import React, { useEffect, useRef, forwardRef, useState, useCallback } from 'react';
import { Cosmograph, useCosmograph } from '@cosmograph/react';
import { GraphNode } from '../api/types';
import { useGraphConfig } from '../contexts/GraphConfigContext';
import { logger } from '../utils/logger';

interface GraphLink {
  source: string;
  target: string;
  from: string;
  to: string;
  [key: string]: any;
}

interface GraphStats {
  total_nodes: number;
  total_edges: number;
  density?: number;
  [key: string]: any;
}

interface CosmographRef {
  setZoomLevel: (level: number, duration?: number) => void;
  getZoomLevel: () => number;
  fitView: (duration?: number) => void;
  selectNode: (node: GraphNode) => void;
  selectNodes: (nodes: GraphNode[]) => void;
  unselectAll: () => void;
  unfocusNode: () => void;
  restart: () => void;
  start: () => void;
  _canvasElement?: HTMLCanvasElement;
}

interface GraphCanvasProps {
  onNodeClick: (node: GraphNode) => void;
  onNodeSelect: (nodeId: string) => void;
  onClearSelection?: () => void;
  selectedNodes: string[];
  highlightedNodes: string[];
  className?: string;
  stats?: GraphStats;
}

const GraphCanvasComponent = forwardRef<HTMLDivElement, GraphCanvasProps>(
  ({ onNodeClick, onNodeSelect, onClearSelection, selectedNodes, highlightedNodes, className, stats }, ref) => {
    const cosmographRef = useRef<CosmographRef | null>(null);
    const { nodes, links } = useCosmograph();
    const [isReady, setIsReady] = useState(false);
    const [isCanvasReady, setIsCanvasReady] = useState(false);
    const { config, setCosmographRef } = useGraphConfig();
    const [tweenProgress, setTweenProgress] = useState(1);
    
    // Double-click detection using refs to avoid re-renders
    const lastClickTimeRef = useRef<number>(0);
    const lastClickedNodeRef = useRef<GraphNode | null>(null);
    const doubleClickTimeoutRef = useRef<NodeJS.Timeout | null>(null);
    const criticalOperationRef = useRef(false);
    const [prevSizeMapping, setPrevSizeMapping] = useState(config.sizeMapping);
    const tweenTimeoutRef = useRef<NodeJS.Timeout | null>(null);
    const zoomCooldownRef = useRef<NodeJS.Timeout | null>(null);
    // Simplified tweening state for size mapping transitions
    const [tweenState, setTweenState] = useState<{
      isActive: boolean,
      oldMapping: string,
      oldValues: number[],
      newValues: number[],
      oldRange: { min: number, max: number, range: number },
      newRange: { min: number, max: number, range: number }
    }>({
      isActive: false,
      oldMapping: config.sizeMapping,
      oldValues: [],
      newValues: [],
      oldRange: { min: 0, max: 1, range: 1 },
      newRange: { min: 0, max: 1, range: 1 }
    });


    // Set the cosmograph ref in context when it's available
    useEffect(() => {
      if (cosmographRef.current) {
        setCosmographRef(cosmographRef);
        setIsReady(true);
        
        // Aggressive canvas readiness check for initial load
        let checkCount = 0;
        const checkCanvas = () => {
          if (cosmographRef.current?._canvasElement) {
            setIsCanvasReady(true);
            logger.log('Canvas ready after', checkCount * 50, 'ms');
          } else {
            checkCount++;
            // Aggressive polling for first 2 seconds, then slower
            const delay = checkCount < 40 ? 50 : 200;
            setTimeout(checkCanvas, delay);
          }
        };
        
        // Start checking immediately
        setTimeout(checkCanvas, 0);
      }
    }, [])

    // Monitor canvas state changes - removed circular dependency
    useEffect(() => {
      if (!cosmographRef.current) return;
      
      const interval = setInterval(() => {
        const hasCanvas = !!cosmographRef.current?._canvasElement;
        setIsCanvasReady(prevReady => {
          if (hasCanvas !== prevReady) {
            logger.log('Canvas state changed:', hasCanvas);
          }
          return hasCanvas;
        });
      }, 100); // Faster polling for better responsiveness
      
      return () => clearInterval(interval);
    }, []); // Remove isCanvasReady dependency to prevent recreation


    // Helper function to calculate size values for a given mapping
    const calculateSizeValues = useCallback((nodes: any[], mapping: string) => {
      return nodes.map(node => {
        switch (mapping) {
          case 'uniform':
            return 1;
          case 'degree':
            return node.properties?.degree_centrality || node.properties?.degree || node.size || 1;
          case 'betweenness':
            return node.properties?.betweenness_centrality || node.properties?.betweenness || node.size || 1;
          case 'pagerank':
            return node.properties?.pagerank_centrality || node.properties?.pagerank || node.size || 1;
          case 'importance':
            return node.properties?.importance_centrality || node.properties?.importance || node.size || 1;
          case 'connections':
            return node.properties?.degree_centrality || node.properties?.connections || node.size || 1;
          case 'custom':
            return node.size || 1;
          default:
            return node.size || 1;
        }
      });
    }, []);


    // Use provided data directly
    const transformedData = React.useMemo(() => {
      return { nodes, links };
    }, [nodes, links]);

    // Memoized node index map for O(1) lookups
    const nodeIndexMap = React.useMemo(() => {
      const map = new Map<string, number>();
      transformedData.nodes.forEach((node, index) => {
        map.set(node.id, index);
      });
      return map;
    }, [transformedData.nodes]);

    // Memoized calculation of current mapping's values and range for performance
    const currentMappingData = React.useMemo(() => {
      if (transformedData.nodes.length === 0) {
        return { values: [], min: 1, max: 1, range: 1, nodeIndexMap };
      }
      
      const values = calculateSizeValues(transformedData.nodes, config.sizeMapping);
      const min = Math.min(...values);
      const max = Math.max(...values);
      const range = max - min || 1;
      
      return { values, min, max, range, nodeIndexMap };
    }, [transformedData.nodes, config.sizeMapping, calculateSizeValues, nodeIndexMap]);

    // Handle size mapping changes with simple tweening
    useEffect(() => {
      if (config.sizeMapping !== prevSizeMapping && transformedData.nodes.length > 0) {
        // Clear any existing animation
        if (tweenTimeoutRef.current) {
          clearTimeout(tweenTimeoutRef.current);
        }
        
        // Calculate old and new values on-demand
        const oldValues = calculateSizeValues(transformedData.nodes, prevSizeMapping);
        const newValues = calculateSizeValues(transformedData.nodes, config.sizeMapping);
        
        const oldMin = Math.min(...oldValues);
        const oldMax = Math.max(...oldValues);
        const newMin = Math.min(...newValues);
        const newMax = Math.max(...newValues);
        
        // Set up tween state
        setTweenState({
          isActive: true,
          oldMapping: prevSizeMapping,
          oldValues,
          newValues,
          oldRange: { min: oldMin, max: oldMax, range: oldMax - oldMin || 1 },
          newRange: { min: newMin, max: newMax, range: newMax - newMin || 1 }
        });
        
        logger.log(`Switching from ${prevSizeMapping} to ${config.sizeMapping}`);
        
        // Start animation
        setTweenProgress(0);
        
        const duration = 2000; // ms
        const startTime = performance.now();
        let animationId: number;
        
        const animate = (currentTime: number) => {
          const elapsed = currentTime - startTime;
          const progress = Math.min(elapsed / duration, 1);
          
          // Ease-out function for smooth animation
          const easedProgress = 1 - Math.pow(1 - progress, 3);
          setTweenProgress(easedProgress);
          
          if (progress < 1) {
            animationId = requestAnimationFrame(animate);
          } else {
            // Animation complete
            setTweenState(prev => ({ ...prev, isActive: false }));
            setPrevSizeMapping(config.sizeMapping);
          }
        };
        
        animationId = requestAnimationFrame(animate);
        
        // Store animation ID for cleanup
        tweenTimeoutRef.current = animationId as any;
      }
      
      return () => {
        if (tweenTimeoutRef.current) {
          // Handle both timeout and animation frame cleanup
          if (typeof tweenTimeoutRef.current === 'number') {
            cancelAnimationFrame(tweenTimeoutRef.current);
          } else {
            clearTimeout(tweenTimeoutRef.current);
          }
          tweenTimeoutRef.current = null;
        }
        if (doubleClickTimeoutRef.current) {
          clearTimeout(doubleClickTimeoutRef.current);
          doubleClickTimeoutRef.current = null;
        }
      };
    }, [config.sizeMapping, prevSizeMapping, transformedData.nodes, calculateSizeValues]);

    // Method to select a single node in Cosmograph
    const selectCosmographNode = useCallback((node: GraphNode) => {
      if (cosmographRef.current) {
        try {
          if (typeof cosmographRef.current.selectNode === 'function') {
            cosmographRef.current.selectNode(node);
          } else if (typeof cosmographRef.current.selectNodes === 'function') {
            cosmographRef.current.selectNodes([node]);
          }
        } catch (error) {
          logger.error('Error selecting Cosmograph node:', error);
        }
      }
    }, []);

    // Method to select multiple nodes in Cosmograph
    const selectCosmographNodes = useCallback((nodes: GraphNode[]) => {
      if (cosmographRef.current) {
        try {
          if (typeof cosmographRef.current.selectNodes === 'function') {
            cosmographRef.current.selectNodes(nodes);
            logger.log('Selected Cosmograph nodes:', nodes.map(n => n.id));
          } else {
            logger.warn('No selectNodes method found on Cosmograph instance');
          }
        } catch (error) {
          logger.error('Error selecting Cosmograph nodes:', error);
        }
      }
    }, []);

    // Method to clear Cosmograph selection and return to default state
    const clearCosmographSelection = useCallback(() => {
      if (cosmographRef.current) {
        try {
          // Try multiple approaches to clear selection and return to default state
          if (typeof cosmographRef.current.unselectAll === 'function') {
            cosmographRef.current.unselectAll();
            logger.log('Cleared Cosmograph selection with unselectAll()');
          } else if (typeof cosmographRef.current.selectNodes === 'function') {
            cosmographRef.current.selectNodes([]);
            logger.log('Cleared Cosmograph selection with selectNodes([])');
          } else if (typeof cosmographRef.current.setSelectedNodes === 'function') {
            cosmographRef.current.setSelectedNodes([]);
            logger.log('Cleared Cosmograph selection with setSelectedNodes([])');
          } else {
            logger.warn('No clear selection method found on Cosmograph instance');
            logger.log('Available methods:', Object.getOwnPropertyNames(cosmographRef.current));
          }
          
          // Additional step: ensure we're in default state by calling unfocusNode if available
          if (typeof cosmographRef.current.unfocusNode === 'function') {
            cosmographRef.current.unfocusNode();
          }
        } catch (error) {
          logger.error('Error clearing Cosmograph selection:', error);
        }
      }
    }, []);

    const zoomIn = useCallback(() => {
      if (!cosmographRef.current?.setZoomLevel) return;
      
      try {
        requestAnimationFrame(() => {
          // Immediate canvas check - don't rely on state
          const hasCanvas = !!cosmographRef.current?._canvasElement;
          if (cosmographRef.current?.setZoomLevel && hasCanvas) {
            const currentZoom = cosmographRef.current.getZoomLevel();
            const newZoom = Math.min(currentZoom * 1.5, 10);
            cosmographRef.current.setZoomLevel(newZoom, 300);
          }
        });
      } catch (error) {
        logger.warn('Zoom in failed:', error);
      }
    }, []);

    const zoomOut = useCallback(() => {
      if (!cosmographRef.current?.setZoomLevel) return;
      
      try {
        requestAnimationFrame(() => {
          // Immediate canvas check - don't rely on state
          const hasCanvas = !!cosmographRef.current?._canvasElement;
          if (cosmographRef.current?.setZoomLevel && hasCanvas) {
            const currentZoom = cosmographRef.current.getZoomLevel();
            const newZoom = Math.max(currentZoom * 0.67, 0.1);
            cosmographRef.current.setZoomLevel(newZoom, 300);
          }
        });
      } catch (error) {
        logger.warn('Zoom out failed:', error);
      }
    }, []);

    const fitView = useCallback(() => {
      if (!cosmographRef.current?.fitView) return;
      
      try {
        requestAnimationFrame(() => {
          // Immediate canvas check - don't rely on state
          const hasCanvas = !!cosmographRef.current?._canvasElement;
          if (cosmographRef.current?.fitView && hasCanvas) {
            cosmographRef.current.fitView(500);
          }
        });
      } catch (error) {
        logger.warn('Fit view failed:', error);
      }
    }, []);

    // Expose methods to parent via ref
    React.useImperativeHandle(ref, () => ({
      clearSelection: clearCosmographSelection,
      selectNode: selectCosmographNode,
      selectNodes: selectCosmographNodes,
      zoomIn,
      zoomOut,
      fitView
    }), [clearCosmographSelection, selectCosmographNode, selectCosmographNodes, zoomIn, zoomOut, fitView]);

    // Handle Cosmograph events with double-click detection
    const handleClick = (node?: GraphNode) => {
      if (node) {
        const currentTime = Date.now();
        const timeDiff = currentTime - lastClickTimeRef.current;
        const isDoubleClick = timeDiff < 300 && lastClickedNodeRef.current?.id === node.id;
        
        // Clear any existing timeout
        if (doubleClickTimeoutRef.current) {
          clearTimeout(doubleClickTimeoutRef.current);
          doubleClickTimeoutRef.current = null;
        }
        
        if (isDoubleClick) {
          // Double-click detected - select node with Cosmograph visual effects
          selectCosmographNode(node);
          onNodeClick(node);
          onNodeSelect(node.id);
        } else {
          // Single click - immediate execution, show modal only (no visual selection)
          doubleClickTimeoutRef.current = setTimeout(() => {
            // Single click confirmed - show modal but keep graph in default state
            logger.log('Single-click detected on node:', node.id);
            onNodeClick(node); // Show modal only
            // Do NOT call selectCosmographNode() or onNodeSelect() to keep graph in default state
          }, 300);
        }
        
        // Update click tracking using refs (no re-render)
        lastClickTimeRef.current = currentTime;
        lastClickedNodeRef.current = node;
      } else {
        // Empty space was clicked - clear all selections and return to default state
        clearCosmographSelection();
        onClearSelection?.();
      }
    };

    return (
      <div 
        className={`relative overflow-hidden ${className}`}
      >
          <Cosmograph
            ref={cosmographRef}
            // Zoom and initialization
            fitViewOnInit={false}
            disableZoom={false}
            // Appearance
            backgroundColor={config.backgroundColor}
            nodeColor={(node: GraphNode) => {
              // Check if node is highlighted from search
              const isHighlighted = highlightedNodes.includes(node.id);
              
              if (isHighlighted) {
                // Use a bright highlight color for search results
                return 'rgba(255, 215, 0, 0.9)'; // Gold color with high opacity
              }
              
              // Always use context color mapping based on node type (ignore API colors)
              const nodeType = node.node_type as keyof typeof config.nodeTypeColors;
              const color = config.nodeTypeColors[nodeType] || '#b3b3b3';
              const opacity = config.nodeOpacity / 100; // Convert percentage to decimal
              
              // Convert hex to rgba with opacity
              if (color.startsWith('#')) {
                const hex = color.substring(1);
                // Handle both 3-char and 6-char hex codes
                let r, g, b;
                if (hex.length === 3) {
                  r = parseInt(hex.substring(0, 1).repeat(2), 16);
                  g = parseInt(hex.substring(1, 2).repeat(2), 16);
                  b = parseInt(hex.substring(2, 3).repeat(2), 16);
                } else if (hex.length === 6) {
                  r = parseInt(hex.substring(0, 2), 16);
                  g = parseInt(hex.substring(2, 4), 16);
                  b = parseInt(hex.substring(4, 6), 16);
                } else {
                  // Invalid hex, fallback to default
                  return color;
                }
                return `rgba(${r}, ${g}, ${b}, ${opacity})`;
              }
              return color; // Fallback for non-hex colors
            }}
            nodeSize={(node: GraphNode) => {
              let rawSize: number;
              let min: number;
              let max: number;
              let range: number;
              
              if (tweenState.isActive && tweenProgress < 1) {
                // During tweening, interpolate between old and new values
                const nodeIndex = currentMappingData.nodeIndexMap.get(node.id);
                
                if (nodeIndex !== undefined && 
                    nodeIndex < tweenState.oldValues.length && 
                    nodeIndex < tweenState.newValues.length) {
                  
                  const oldRawSize = tweenState.oldValues[nodeIndex];
                  const newRawSize = tweenState.newValues[nodeIndex];
                  
                  // Interpolate raw size values
                  rawSize = oldRawSize + (newRawSize - oldRawSize) * tweenProgress;
                  
                  // Interpolate range values
                  min = tweenState.oldRange.min + (tweenState.newRange.min - tweenState.oldRange.min) * tweenProgress;
                  max = tweenState.oldRange.max + (tweenState.newRange.max - tweenState.oldRange.max) * tweenProgress;
                  range = max - min || 1;
                } else {
                  // Fallback if index is invalid - use memoized data
                  rawSize = calculateSizeValues([node], config.sizeMapping)[0] || 1;
                  min = currentMappingData.min;
                  max = currentMappingData.max;
                  range = currentMappingData.range;
                }
              } else {
                // Normal operation - use memoized data for performance
                const nodeIndex = currentMappingData.nodeIndexMap.get(node.id);
                
                if (nodeIndex !== undefined && nodeIndex < currentMappingData.values.length) {
                  // Use pre-calculated value from memoized data
                  rawSize = currentMappingData.values[nodeIndex];
                } else {
                  // Fallback calculation
                  rawSize = calculateSizeValues([node], config.sizeMapping)[0] || 1;
                }
                
                min = currentMappingData.min;
                max = currentMappingData.max;
                range = currentMappingData.range;
              }
              
              // Normalize to config range
              const normalizedSize = min === max 
                ? config.minNodeSize 
                : config.minNodeSize + ((rawSize - min) / range) * (config.maxNodeSize - config.minNodeSize);
              
              const finalSize = normalizedSize * config.sizeMultiplier;
              
              // Make highlighted nodes 20% larger
              const isHighlighted = highlightedNodes.includes(node.id);
              return isHighlighted ? finalSize * 1.2 : finalSize;
            }}
            nodeLabelAccessor={(node: GraphNode) => node.label || node.id}
            linkColor={config.linkColor}
            linkWidth={config.linkWidth}
            linkArrows={true}
            linkArrowsSizeScale={0.5}
            linkGreyoutOpacity={1 - config.linkOpacity}
            
            // Curved Links
            curvedLinks={config.curvedLinks}
            curvedLinkSegments={config.curvedLinkSegments}
            curvedLinkWeight={config.curvedLinkWeight}
            curvedLinkControlPointDistance={config.curvedLinkControlPointDistance}
            
            // Labels
            showDynamicLabels={config.showLabels}
            showHoveredNodeLabel={config.showHoveredNodeLabel}
            nodeLabelColor={(node: GraphNode) => {
              // Apply label opacity by modifying the alpha channel
              const color = config.labelColor;
              const opacity = config.labelOpacity / 100; // Convert percentage to decimal
              
              // Convert hex to rgba with opacity
              if (color.startsWith('#')) {
                const hex = color.substring(1);
                // Handle both 3-char and 6-char hex codes
                let r, g, b;
                if (hex.length === 3) {
                  r = parseInt(hex.substring(0, 1).repeat(2), 16);
                  g = parseInt(hex.substring(1, 2).repeat(2), 16);
                  b = parseInt(hex.substring(2, 3).repeat(2), 16);
                } else if (hex.length === 6) {
                  r = parseInt(hex.substring(0, 2), 16);
                  g = parseInt(hex.substring(2, 4), 16);
                  b = parseInt(hex.substring(4, 6), 16);
                } else {
                  // Invalid hex, fallback to default
                  return color;
                }
                return `rgba(${r}, ${g}, ${b}, ${opacity})`;
              }
              return color; // Fallback for non-hex colors
            }}
            hoveredNodeLabelColor={config.hoveredLabelColor}
            nodeLabelClassName={(node: GraphNode) => {
              // Dynamic CSS classes based on label size and border width
              const sizeClass = `cosmograph-label-size-${config.labelSize}`;
              const borderClass = `cosmograph-border-${config.borderWidth.toString().replace('.', '-')}`;
              return `${sizeClass} ${borderClass}`;
            }}
            
            // Physics
            simulationFriction={config.friction}
            simulationLinkSpring={config.linkSpring}
            simulationLinkDistance={config.linkDistance}
            simulationRepulsion={config.repulsion}
            simulationGravity={config.gravity}
            simulationCenter={config.centerForce}
            simulationRepulsionFromMouse={config.mouseRepulsion}
            simulationDecay={config.simulationDecay}
            
            // Quadtree optimization (disabled due to performance issues)
            useQuadtree={false}
            
            // Interaction
            onClick={handleClick}
            renderHoveredNodeRing={true}
            hoveredNodeRingColor="#22d3ee"
            focusedNodeRingColor="#fbbf24"
            nodeGreyoutOpacity={selectedNodes.length > 0 || highlightedNodes.length > 0 ? 0.1 : 1} // Only grey out when something is actually selected
            
            // Performance
            pixelRatio={1} // Higher values break zoom functionality
            showFPSMonitor={false}
            
            // Selection
            showLabelsFor={selectedNodes.map(id => ({ id }))}
          />
        
        {/* Performance Overlay */}
        {stats && (
          <div className="absolute top-4 left-4 glass text-xs text-muted-foreground p-2 rounded">
            <div>Nodes: {stats.total_nodes.toLocaleString()}</div>
            <div>Edges: {stats.total_edges.toLocaleString()}</div>
            {stats.density !== undefined && (
              <div>Density: {stats.density.toFixed(4)}</div>
            )}
          </div>
        )}
      </div>
    );
  }
);

// Export with React.memo to prevent unnecessary re-renders
export const GraphCanvas = React.memo(GraphCanvasComponent, (prevProps, nextProps) => {
  // Ultra-restrictive comparison - only re-render for essential changes
  
  // Only re-render if data references actually changed (not just array contents)
  const dataChanged = prevProps.nodes !== nextProps.nodes || 
                     prevProps.links !== nextProps.links;
  
  // Proper deep comparison for selection arrays
  const selectedNodesChanged = prevProps.selectedNodes !== nextProps.selectedNodes &&
                              (prevProps.selectedNodes.length !== nextProps.selectedNodes.length ||
                               !prevProps.selectedNodes.every((id, index) => id === nextProps.selectedNodes[index]));
                               
  const highlightedNodesChanged = prevProps.highlightedNodes !== nextProps.highlightedNodes &&
                                 (prevProps.highlightedNodes.length !== nextProps.highlightedNodes.length ||
                                  !prevProps.highlightedNodes.every((id, index) => id === nextProps.highlightedNodes[index]));
  
  // Only re-render if stats actually changed
  const statsChanged = prevProps.stats !== nextProps.stats;
  
  const shouldRerender = dataChanged || selectedNodesChanged || highlightedNodesChanged || statsChanged;
  
  // Return true to skip re-render, false to re-render
  return !shouldRerender;
});

GraphCanvas.displayName = 'GraphCanvas';