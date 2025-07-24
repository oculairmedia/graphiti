import React, { useEffect, useRef, forwardRef, useState, useCallback } from 'react';
import { Cosmograph, useCosmograph } from '@cosmograph/react';
import { GraphNode } from '../api/types';
import type { GraphData } from '../types/graph';
import { useGraphConfig } from '../contexts/GraphConfigContext';
import { logger } from '../utils/logger';
import { hexToRgba, generateHSLColor } from '../utils/colorCache';

interface GraphLink {
  source: string;
  target: string;
  from: string;
  to: string;
  weight?: number;
  edge_type?: string;
  [key: string]: unknown;
}

interface GraphNodeWithPosition extends GraphNode {
  x?: number;
  y?: number;
}

interface GraphStats {
  total_nodes: number;
  total_edges: number;
  density?: number;
  [key: string]: unknown;
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

interface GraphCanvasHandle {
  clearSelection: () => void;
  selectNode: (node: GraphNode) => void;
  selectNodes: (nodes: GraphNode[]) => void;
  zoomIn: () => void;
  zoomOut: () => void;
  fitView: () => void;
  setData: (nodes: GraphNode[], links: GraphLink[], runSimulation?: boolean) => void;
  restart: () => void;
}

const GraphCanvasComponent = forwardRef<GraphCanvasHandle, GraphCanvasProps>(
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
    const animationFrameRef = useRef<number | null>(null);
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


    // Canvas readiness tracking with single polling mechanism
    const intervalRef = useRef<NodeJS.Timeout | null>(null);
    
    useEffect(() => {
      // Set up continuous polling to check for cosmographRef availability
      let checkCount = 0;
      const pollCosmographRef = () => {
        if (cosmographRef.current) {
          console.log('GraphCanvas: Setting cosmographRef in context');
          setCosmographRef(cosmographRef);
          setIsReady(true);
          
          // Start canvas polling
          const pollCanvas = () => {
            const hasCanvas = !!cosmographRef.current?._canvasElement;
            
            setIsCanvasReady(prevReady => {
              if (hasCanvas !== prevReady) {
                console.log('GraphCanvas: Canvas ready state changed to', hasCanvas);
              }
              return hasCanvas;
            });
            
            if (!hasCanvas && checkCount < 100) { // Max 5 seconds of polling
              checkCount++;
              // Aggressive polling for first 2 seconds, then slower
              const delay = checkCount < 40 ? 50 : 200;
              intervalRef.current = setTimeout(pollCanvas, delay);
            }
          };
          
          // Start canvas polling immediately
          pollCanvas();
        } else {
          // Keep polling for cosmographRef every 100ms for up to 10 seconds
          if (checkCount < 100) {
            checkCount++;
            setTimeout(pollCosmographRef, 100);
          } else {
            console.warn('GraphCanvas: cosmographRef never became available after 10 seconds');
          }
        }
      };
      
      // Start polling immediately
      pollCosmographRef();
      
      return () => {
        if (intervalRef.current) {
          clearTimeout(intervalRef.current);
          intervalRef.current = null;
        }
      };
    }, [setCosmographRef]);


    // Helper function to calculate size values for a given mapping
    const calculateSizeValues = useCallback((nodes: GraphNode[], mapping: string) => {
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


    // Calculate average link distance for dynamic curve adjustment
    const averageDistance = React.useMemo(() => {
      if (links.length === 0) return 200; // Default distance
      
      let totalDistance = 0;
      let validDistances = 0;
      
      links.forEach(link => {
        const sourceNode = nodes.find(n => n.id === link.source);
        const targetNode = nodes.find(n => n.id === link.target);
        
        if (sourceNode && targetNode) {
          // Try to get positions from node properties or use defaults
          const sourceWithPos = sourceNode as GraphNodeWithPosition;
          const targetWithPos = targetNode as GraphNodeWithPosition;
          const sx = sourceWithPos.x || sourceNode.properties?.x || 0;
          const sy = sourceWithPos.y || sourceNode.properties?.y || 0;
          const tx = targetWithPos.x || targetNode.properties?.x || 0;
          const ty = targetWithPos.y || targetNode.properties?.y || 0;
          
          const distance = Math.sqrt((sx - tx) ** 2 + (sy - ty) ** 2);
          if (distance > 0) {
            totalDistance += distance;
            validDistances++;
          }
        }
      });
      
      return validDistances > 0 ? totalDistance / validDistances : 200;
    }, [nodes, links]);

    // Calculate dynamic curve properties based on average distance
    const dynamicCurveWeight = React.useMemo(() => {
      const normalizedDistance = Math.min(averageDistance / 300, 2.0);
      return Math.max(0.1, config.curvedLinkWeight * (0.4 + normalizedDistance * 0.6));
    }, [averageDistance, config.curvedLinkWeight]);
    
    const dynamicControlPointDistance = React.useMemo(() => {
      const normalizedDistance = Math.min(averageDistance / 300, 2.0);
      return Math.max(0.1, config.curvedLinkControlPointDistance * (0.3 + normalizedDistance * 0.7));
    }, [averageDistance, config.curvedLinkControlPointDistance]);

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
        // Clear any existing animations
        if (tweenTimeoutRef.current) {
          clearTimeout(tweenTimeoutRef.current);
          tweenTimeoutRef.current = null;
        }
        if (animationFrameRef.current) {
          cancelAnimationFrame(animationFrameRef.current);
          animationFrameRef.current = null;
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
            animationFrameRef.current = requestAnimationFrame(animate);
          } else {
            // Animation complete
            setTweenState(prev => ({ ...prev, isActive: false }));
            setPrevSizeMapping(config.sizeMapping);
            animationFrameRef.current = null;
          }
        };
        
        animationFrameRef.current = requestAnimationFrame(animate);
      }
      
      return () => {
        // Clean up timeouts
        if (tweenTimeoutRef.current) {
          clearTimeout(tweenTimeoutRef.current);
          tweenTimeoutRef.current = null;
        }
        // Clean up animation frames
        if (animationFrameRef.current) {
          cancelAnimationFrame(animationFrameRef.current);
          animationFrameRef.current = null;
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
        const currentZoom = cosmographRef.current.getZoomLevel();
        const newZoom = Math.min(currentZoom * 1.5, 10);
        cosmographRef.current.setZoomLevel(newZoom, 300);
      } catch (error) {
        logger.warn('Zoom in failed:', error);
      }
    }, []);

    const zoomOut = useCallback(() => {
      if (!cosmographRef.current?.setZoomLevel) return;
      
      try {
        const currentZoom = cosmographRef.current.getZoomLevel();
        const newZoom = Math.max(currentZoom * 0.67, 0.1);
        cosmographRef.current.setZoomLevel(newZoom, 300);
      } catch (error) {
        logger.warn('Zoom out failed:', error);
      }
    }, []);

    const fitView = useCallback(() => {
      if (!cosmographRef.current?.fitView) return;
      
      try {
        cosmographRef.current.fitView(500);
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
      fitView,
      setData: (nodes: GraphNode[], links: GraphLink[], runSimulation = true) => {
        if (cosmographRef.current && typeof cosmographRef.current.setData === 'function') {
          cosmographRef.current.setData(nodes, links, runSimulation);
        }
      },
      restart: () => {
        if (cosmographRef.current && typeof cosmographRef.current.restart === 'function') {
          cosmographRef.current.restart();
        }
      }
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
          // Single click - show modal and maintain visual selection
          doubleClickTimeoutRef.current = setTimeout(() => {
            // Single click confirmed - show modal and keep node visually selected
            logger.log('Single-click detected on node:', node.id);
            selectCosmographNode(node); // Keep visual selection circle
            onNodeClick(node); // Show modal
            onNodeSelect(node.id); // Update selection state
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
            fitViewOnInit={true}
            initialZoomLevel={1.5}
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

              // Use cached color utilities for performance

              const opacity = config.nodeOpacity / 100;

              // Apply color scheme
              switch (config.colorScheme) {
                case 'by-type': {
                  // Use individual type colors (original behavior)
                  const nodeType = node.node_type as keyof typeof config.nodeTypeColors;
                  const typeColor = config.nodeTypeColors[nodeType] || '#b3b3b3';
                  return hexToRgba(typeColor, opacity);
                }

                case 'by-centrality': {
                  // Color by degree centrality using cached calculation
                  const centrality = node.properties?.degree_centrality || 0;
                  const maxCentrality = 100;
                  const centralityFactor = Math.min(centrality / maxCentrality, 1);
                  return generateHSLColor('centrality', centralityFactor, opacity);
                }

                case 'by-pagerank': {
                  // Color by PageRank score using cached calculation
                  const pagerank = node.properties?.pagerank_centrality || node.properties?.pagerank || 0;
                  const maxPagerank = 0.1;
                  const pagerankFactor = Math.min(pagerank / maxPagerank, 1);
                  return generateHSLColor('pagerank', pagerankFactor, opacity);
                }

                case 'by-degree': {
                  // Color by connection count using cached calculation
                  const degree = node.properties?.degree || node.properties?.degree_centrality || 0;
                  const maxDegree = 50;
                  const degreeFactor = Math.min(degree / maxDegree, 1);
                  return generateHSLColor('degree', degreeFactor, opacity);
                }

                case 'by-community': {
                  // Color by detected community (using node type as proxy)
                  const communityColors = [
                    '#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', 
                    '#FFEAA7', '#DDA0DD', '#98D8C8', '#F7DC6F',
                    '#BB8FCE', '#85C1E9', '#F8C471', '#82E0AA'
                  ];
                  const communityType = node.node_type;
                  const communityIndex = ['Entity', 'Episodic', 'Agent', 'Community'].indexOf(communityType);
                  const communityColor = communityColors[communityIndex] || communityColors[0];
                  return hexToRgba(communityColor, opacity);
                }

                case 'custom': {
                  // Use custom property-based coloring
                  const customValue = node.properties?.importance_centrality || node.properties?.custom_score || 0;
                  const customFactor = Math.min(customValue / 10, 1);
                  return hexToRgba(
                    customFactor > 0.5 ? config.gradientHighColor : config.gradientLowColor, 
                    opacity
                  );
                }

                default: {
                  // Fallback to type-based coloring
                  const fallbackType = node.node_type as keyof typeof config.nodeTypeColors;
                  const fallbackColor = config.nodeTypeColors[fallbackType] || '#b3b3b3';
                  return hexToRgba(fallbackColor, opacity);
                }
              }
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
            linkColor={(link: GraphLink) => {
              switch (config.linkColorScheme) {
                case 'uniform':
                  return config.linkColor;
                
                case 'by-weight': {
                  // Color intensity based on weight (darker = stronger)
                  const weight = link.weight || 1;
                  const intensity = Math.min(weight / 5, 1); // Normalize to 0-1
                  return `rgba(102, 102, 102, ${0.3 + intensity * 0.7})`;
                }
                
                case 'by-type': {
                  // Different colors for different edge types
                  const typeColors: Record<string, string> = {
                    'RELATES_TO': '#4ECDC4',
                    'MENTIONS': '#45B7D1', 
                    'CONTAINS': '#96CEB4',
                    'CONNECTED': '#FFEAA7',
                    'SIMILAR': '#DDA0DD',
                    'default': config.linkColor
                  };
                  return typeColors[link.edge_type] || typeColors.default;
                }
                
                case 'by-distance': {
                  // Color based on link length (shorter = warmer)
                  const sourceNode = transformedData.nodes.find(n => n.id === link.source);
                  const targetNode = transformedData.nodes.find(n => n.id === link.target);
                  if (sourceNode && targetNode) {
                    // Simple distance approximation based on degree difference
                    const sourceDegree = sourceNode.properties?.degree_centrality || 0;
                    const targetDegree = targetNode.properties?.degree_centrality || 0;
                    const distance = Math.abs(sourceDegree - targetDegree);
                    const hue = Math.max(0, 240 - distance * 40); // Blue to red gradient
                    return `hsl(${hue}, 70%, 50%)`;
                  }
                  return config.linkColor;
                }
                
                case 'gradient': {
                  // Gradient between connected node colors
                  const srcNode = transformedData.nodes.find(n => n.id === link.source);
                  const tgtNode = transformedData.nodes.find(n => n.id === link.target);
                  if (srcNode && tgtNode) {
                    const srcType = srcNode.node_type as keyof typeof config.nodeTypeColors;
                    const tgtType = tgtNode.node_type as keyof typeof config.nodeTypeColors;
                    const srcColor = config.nodeTypeColors[srcType] || '#b3b3b3';
                    const tgtColor = config.nodeTypeColors[tgtType] || '#b3b3b3';
                    
                    // If same type, use that color; otherwise blend
                    if (srcType === tgtType) {
                      return srcColor;
                    } else {
                      // Simple blend by making it semi-transparent
                      return `${srcColor}80`; // Add alpha
                    }
                  }
                  return config.linkColor;
                }
                
                case 'community': {
                  // Highlight inter-community connections
                  const srcCommunityNode = transformedData.nodes.find(n => n.id === link.source);
                  const tgtCommunityNode = transformedData.nodes.find(n => n.id === link.target);
                  if (srcCommunityNode && tgtCommunityNode) {
                    const srcCommunity = srcCommunityNode.node_type;
                    const tgtCommunity = tgtCommunityNode.node_type;
                    
                    if (srcCommunity !== tgtCommunity) {
                      // Inter-community link - make it bright
                      return '#FFD700'; // Gold for bridges
                    } else {
                      // Intra-community link - make it subtle
                      return '#666666';
                    }
                  }
                  return config.linkColor;
                }
                
                default:
                  return config.linkColor;
              }
            }}
            linkWidth={config.linkWidth}
            linkArrows={config.linkArrows}
            linkArrowsSizeScale={config.linkArrowsSizeScale}
            linkGreyoutOpacity={1 - config.linkOpacity}
            linkVisibilityDistance={config.linkVisibilityDistance}
            linkVisibilityMinTransparency={config.linkVisibilityMinTransparency}
            
            // Curved Links
            curvedLinks={config.curvedLinks}
            curvedLinkSegments={config.curvedLinkSegments}
            curvedLinkWeight={dynamicCurveWeight}
            curvedLinkControlPointDistance={dynamicControlPointDistance}
            
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
            
            // Quadtree optimization  
            useQuadtree={config.useQuadtree}
            quadtreeLevels={config.quadtreeLevels}
            
            // Interaction
            onClick={handleClick}
            renderHoveredNodeRing={true}
            hoveredNodeRingColor="#22d3ee"
            focusedNodeRingColor="#fbbf24"
            nodeGreyoutOpacity={selectedNodes.length > 0 || highlightedNodes.length > 0 ? 0.1 : 1} // Only grey out when something is actually selected
            
            // Performance
            pixelRatio={2.5} // 250% resolution
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
  
  // Check callback functions by reference (they should be stable with useCallback)
  const callbacksChanged = prevProps.onNodeClick !== nextProps.onNodeClick ||
                           prevProps.onNodeSelect !== nextProps.onNodeSelect ||
                           prevProps.onClearSelection !== nextProps.onClearSelection;
  
  // Proper deep comparison for selection arrays
  const selectedNodesChanged = prevProps.selectedNodes !== nextProps.selectedNodes ||
                              prevProps.selectedNodes.length !== nextProps.selectedNodes.length ||
                              !prevProps.selectedNodes.every((id, index) => id === nextProps.selectedNodes[index]);
                               
  const highlightedNodesChanged = prevProps.highlightedNodes !== nextProps.highlightedNodes ||
                                 prevProps.highlightedNodes.length !== nextProps.highlightedNodes.length ||
                                 !prevProps.highlightedNodes.every((id, index) => id === nextProps.highlightedNodes[index]);
  
  // Only re-render if stats actually changed
  const statsChanged = prevProps.stats !== nextProps.stats;
  
  // ClassName changes
  const classNameChanged = prevProps.className !== nextProps.className;
  
  const shouldRerender = callbacksChanged || selectedNodesChanged || highlightedNodesChanged || statsChanged || classNameChanged;
  
  // Return true to skip re-render, false to re-render
  return !shouldRerender;
});

GraphCanvas.displayName = 'GraphCanvas';