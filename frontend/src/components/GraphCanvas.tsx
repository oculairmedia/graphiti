import React, { useEffect, useRef, forwardRef, useState, useCallback } from 'react';
import { Cosmograph, prepareCosmographData } from '@cosmograph/react';
import { GraphNode } from '../api/types';
import type { GraphData } from '../types/graph';
import { useGraphConfig, generateNodeTypeColor } from '../contexts/GraphConfigContext';
import { logger } from '../utils/logger';
import { hexToRgba, generateHSLColor } from '../utils/colorCache';

// Global singleton to coordinate Data Kit usage across all component instances
class DataKitCoordinator {
  private static instance: DataKitCoordinator;
  private isBusy = false;
  private queue: Array<() => Promise<void>> = [];
  
  static getInstance(): DataKitCoordinator {
    if (!DataKitCoordinator.instance) {
      DataKitCoordinator.instance = new DataKitCoordinator();
    }
    return DataKitCoordinator.instance;
  }
  
  async executeDataKit(task: () => Promise<void>): Promise<void> {
    return new Promise((resolve, reject) => {
      this.queue.push(async () => {
        try {
          await task();
          resolve();
        } catch (error) {
          reject(error);
        }
      });
      
      this.processQueue();
    });
  }
  
  private async processQueue(): Promise<void> {
    if (this.isBusy || this.queue.length === 0) {
      return;
    }
    
    this.isBusy = true;
    const task = this.queue.shift()!;
    
    try {
      await task();
    } finally {
      this.isBusy = false;
      // Process next item in queue
      setTimeout(() => this.processQueue(), 10);
    }
  }
}

const dataKitCoordinator = DataKitCoordinator.getInstance();

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
  // Incremental update methods
  addIncrementalData: (newNodes: GraphNode[], newLinks: GraphLink[], runSimulation?: boolean) => void;
  updateNodes: (updatedNodes: GraphNode[]) => void;
  updateLinks: (updatedLinks: GraphLink[]) => void;
  removeNodes: (nodeIds: string[]) => void;
  removeLinks: (linkIds: string[]) => void;
  // Simulation control methods
  startSimulation: (alpha?: number) => void;
  pauseSimulation: () => void;
  resumeSimulation: () => void;
  keepSimulationRunning: (enable: boolean) => void;
  // External incremental flag control
  setIncrementalUpdateFlag: (enabled: boolean) => void;
}

interface GraphCanvasComponentProps extends GraphCanvasProps {
  nodes: GraphNode[];
  links: GraphLink[];
}

const GraphCanvasComponent = forwardRef<GraphCanvasHandle, GraphCanvasComponentProps>(
  ({ onNodeClick, onNodeSelect, onClearSelection, selectedNodes, highlightedNodes, className, stats, nodes, links }, ref) => {
    const cosmographRef = useRef<CosmographRef | null>(null);
    const [isReady, setIsReady] = useState(false);
    const [isCanvasReady, setIsCanvasReady] = useState(false);
    const [cosmographData, setCosmographData] = useState<any>(null);
    const [dataKitError, setDataKitError] = useState<string | null>(null);
    const [isDataPreparing, setIsDataPreparing] = useState(false);
    const { config, setCosmographRef } = useGraphConfig();
    
    // Track current data for incremental updates
    const [currentNodes, setCurrentNodes] = useState<GraphNode[]>([]);
    const [currentLinks, setCurrentLinks] = useState<GraphLink[]>([]);
    
    // Simulation control state
    const [keepRunning, setKeepRunning] = useState(false);
    const simulationTimerRef = useRef<NodeJS.Timeout | null>(null);
    
    // Track simulation state for debugging incremental updates
    const [isSimulationActive, setIsSimulationActive] = useState(false);
    const lastResumeTimeRef = useRef<number>(0);
    
    // Flag to prevent Data Kit reprocessing during incremental updates
    const isIncrementalUpdateRef = useRef(false);
    
    // Add component ID for debugging multiple instances
    const componentId = useRef(Math.random().toString(36).substr(2, 9));
    
    // Update current data tracking when props change
    useEffect(() => {
      setCurrentNodes(nodes);
      setCurrentLinks(links);
    }, [nodes, links]);
    
    // Double-click detection using refs to avoid re-renders
    const lastClickTimeRef = useRef<number>(0);
    const lastClickedNodeRef = useRef<GraphNode | null>(null);
    const doubleClickTimeoutRef = useRef<NodeJS.Timeout | null>(null);


    // Data Kit configuration for Cosmograph v2.0
    const dataKitConfig = React.useMemo(() => ({
      points: {
        pointIdBy: 'id',              // Required: unique identifier field
        pointLabelBy: 'label',        // Node display labels
        pointColorBy: 'node_type',    // Color by entity type
        pointSizeBy: 'centrality',    // Size by centrality metrics
        pointIncludeColumns: ['degree_centrality', 'pagerank_centrality', 'betweenness_centrality', 'eigenvector_centrality'] // Include additional columns
      },
      links: {
        linkSourceBy: 'source',       // Source node ID field
        linkTargetsBy: ['target'],    // Target node ID field (note: array format as per docs)
        linkColorBy: 'edge_type',     // Link color by type
        linkWidthBy: config.linkWidthBy         // Link width by configured column
      }
    }), [config.linkWidthBy]);

    // Data Kit preparation effect
    useEffect(() => {
      // Skip reprocessing if we're in the middle of an incremental update
      if (isIncrementalUpdateRef.current) {
        return;
      }
      
      
      if (!nodes || !links || nodes.length === 0) {
        setCosmographData(null);
        setDataKitError(null);
        return;
      }

      let cancelled = false;
      
      const prepareData = async () => {
        await dataKitCoordinator.executeDataKit(async () => {
          try {
            setIsDataPreparing(true);
            setDataKitError(null);
            
          
          // Transform data to match Data Kit expectations with consistent types
          const transformedNodes = nodes.map(node => {
            const nodeData = {
              id: String(node.id), // Ensure string type
              label: String(node.label || node.id), // Ensure string type
              node_type: String(node.node_type || 'Unknown'), // Ensure string type
              centrality: Number(node.properties?.degree_centrality || node.properties?.pagerank_centrality || node.size || 1), // Ensure number type
              // Add other commonly used properties with type safety
              degree_centrality: Number(node.properties?.degree_centrality || 0),
              pagerank_centrality: Number(node.properties?.pagerank_centrality || 0),
              betweenness_centrality: Number(node.properties?.betweenness_centrality || 0),
              eigenvector_centrality: Number(node.properties?.eigenvector_centrality || 0)
            };
            
            // Validate that all required fields are present and valid
            if (!nodeData.id || nodeData.id === 'undefined') {
              logger.warn('Invalid node ID found:', node);
            }
            
            return nodeData;
          }).filter(node => node.id && node.id !== 'undefined'); // Remove invalid nodes

          const transformedLinks = links.map(link => {
            const linkData = {
              source: String(link.source), // Ensure string type
              target: String(link.target), // Ensure string type
              edge_type: String(link.edge_type || 'default'), // Ensure string type
              weight: Number(link.weight || 1) // Ensure number type
            };
            
            // Validate that source and target exist
            if (!linkData.source || !linkData.target || linkData.source === 'undefined' || linkData.target === 'undefined') {
              logger.warn('Invalid link found:', link);
            }
            
            return linkData;
          }).filter(link => link.source && link.target && link.source !== 'undefined' && link.target !== 'undefined'); // Remove invalid links

          
          // Log node type distribution for color mapping debugging
          const nodeTypeDistribution = transformedNodes.reduce((acc, node) => {
            acc[node.node_type] = (acc[node.node_type] || 0) + 1;
            return acc;
          }, {} as Record<string, number>);
          
          // Validate we have valid data before proceeding
          if (transformedNodes.length === 0) {
            throw new Error('No valid nodes found after transformation');
          }
          
          const result = await prepareCosmographData(
            dataKitConfig,
            transformedNodes,
            transformedLinks
          );
          
          if (!cancelled && result) {
            // Extract the correct structure from Data Kit result
            const { points, links, cosmographConfig } = result;
            setCosmographData({
              points,
              links,
              cosmographConfig
            });
          }
        } catch (error) {
          if (!cancelled) {
            const errorMessage = error instanceof Error ? error.message : 'Unknown error';
            logger.error('GraphCanvas: Data Kit preparation failed:', errorMessage);
            setDataKitError(errorMessage);
            
            // Fallback to direct data passing
            setCosmographData({
              points: transformedNodes,
              links: transformedLinks,
              cosmographConfig: {}
            });
          }
          } finally {
            if (!cancelled) {
              setIsDataPreparing(false);
            }
          }
        });
      };

      prepareData();
      
      return () => {
        cancelled = true;
      };
    }, [nodes, links, dataKitConfig]);

    // Canvas readiness tracking with single polling mechanism and WebGL context loss recovery
    const intervalRef = useRef<NodeJS.Timeout | null>(null);
    const [webglContextLost, setWebglContextLost] = useState(false);
    
    // WebGL context loss recovery
    const setupWebGLContextRecovery = useCallback(() => {
      const canvas = cosmographRef.current?._canvasElement;
      if (!canvas) return;

      const handleContextLost = (event: Event) => {
        event.preventDefault();
        setWebglContextLost(true);
      };

      const handleContextRestored = () => {
        setWebglContextLost(false);
        
        // Trigger re-render by restarting the simulation
        try {
          cosmographRef.current?.restart();
        } catch (error) {
        }
      };

      canvas.addEventListener('webglcontextlost', handleContextLost);
      canvas.addEventListener('webglcontextrestored', handleContextRestored);

      return () => {
        canvas.removeEventListener('webglcontextlost', handleContextLost);
        canvas.removeEventListener('webglcontextrestored', handleContextRestored);
      };
    }, []);
    
    useEffect(() => {
      // Set up continuous polling to check for cosmographRef availability
      let checkCount = 0;
      let webglCleanup: (() => void) | undefined;
      
      const pollCosmographRef = () => {
        
        if (cosmographRef.current) {
          try {
            setCosmographRef(cosmographRef);
            setIsReady(true);
            
            // Set up WebGL context loss recovery
            webglCleanup = setupWebGLContextRecovery();
            
            // Start canvas polling
            const pollCanvas = () => {
              const hasCanvas = !!cosmographRef.current?._canvasElement;
              
              setIsCanvasReady(prevReady => {
                if (hasCanvas !== prevReady) {
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
          } catch (error) {
          }
        } else {
          // Keep polling for cosmographRef with exponential backoff for up to 3 seconds
          if (checkCount < 30) {
            checkCount++;
            // Exponential backoff: 50ms, 100ms, 150ms, 200ms, etc.
            const delay = Math.min(50 + (checkCount * 10), 200);
            setTimeout(pollCosmographRef, delay);
          } else {
            // Set a fallback timeout to prevent permanent blocking
            setIsReady(false);
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
        if (webglCleanup) {
          webglCleanup();
        }
      };
    }, [setCosmographRef, setupWebGLContextRecovery]);


    // Simplified data transformation for legacy compatibility
    const transformedData = React.useMemo(() => {
      return { nodes, links };
    }, [nodes, links]);

    // Method to select a single node in Cosmograph
    const selectCosmographNode = useCallback((node: GraphNode) => {
      if (cosmographRef.current) {
        try {
          // For Cosmograph v2.0 with Data Kit, we need to use point indices
          if (typeof cosmographRef.current.selectPoint === 'function') {
            // Try to find the node index from the transformed data
            const nodeIndex = transformedData.nodes.findIndex(n => n.id === node.id);
            if (nodeIndex >= 0) {
              cosmographRef.current.selectPoint(nodeIndex);
            } else {
              logger.warn('Could not find node index for selection:', node.id);
            }
          } else if (typeof cosmographRef.current.selectPoints === 'function') {
            const nodeIndex = transformedData.nodes.findIndex(n => n.id === node.id);
            if (nodeIndex >= 0) {
              cosmographRef.current.selectPoints([nodeIndex]);
            }
          }
        } catch (error) {
          logger.error('Error selecting Cosmograph node:', error);
        }
      }
    }, [transformedData.nodes]);

    // Method to select multiple nodes in Cosmograph
    const selectCosmographNodes = useCallback((nodes: GraphNode[]) => {
      if (cosmographRef.current) {
        try {
          if (typeof cosmographRef.current.selectPoints === 'function') {
            // Convert node IDs to indices
            const nodeIndices = nodes.map(node => {
              return transformedData.nodes.findIndex(n => n.id === node.id);
            }).filter(index => index >= 0); // Remove invalid indices
            
            if (nodeIndices.length > 0) {
              cosmographRef.current.selectPoints(nodeIndices);
            } else {
              logger.warn('No valid node indices found for selection');
            }
          } else {
            logger.warn('No selectPoints method found on Cosmograph instance');
          }
        } catch (error) {
          logger.error('Error selecting Cosmograph nodes:', error);
        }
      }
    }, [transformedData.nodes]);

    // Method to clear Cosmograph selection and return to default state
    const clearCosmographSelection = useCallback(() => {
      if (cosmographRef.current) {
        try {
          // For Cosmograph v2.0, use the proper methods
          if (typeof cosmographRef.current.unselectAllPoints === 'function') {
            cosmographRef.current.unselectAllPoints();
          } else if (typeof cosmographRef.current.selectPoints === 'function') {
            cosmographRef.current.selectPoints([]);
          } else {
            logger.warn('No clear selection method found on Cosmograph instance');
          }
          
          // Additional step: clear focused point
          if (typeof cosmographRef.current.setFocusedPoint === 'function') {
            cosmographRef.current.setFocusedPoint();
          }
        } catch (error) {
          logger.error('Error clearing Cosmograph selection:', error);
        }
      }
    }, []);

    const zoomIn = useCallback(() => {
      if (!cosmographRef.current) return;
      
      try {
        // Use the official Cosmograph v2.0 API method with proper error handling
        const currentZoom = cosmographRef.current.getZoomLevel();
        if (currentZoom !== undefined) {
          const newZoom = Math.min(currentZoom * 1.5, 10);
          cosmographRef.current.setZoomLevel(newZoom);
        } else {
          logger.warn('Could not get current zoom level for zoom in');
        }
      } catch (error) {
        logger.warn('Zoom in failed:', error);
      }
    }, []);

    const zoomOut = useCallback(() => {
      if (!cosmographRef.current) return;
      
      try {
        // Use the official Cosmograph v2.0 API method with proper error handling
        const currentZoom = cosmographRef.current.getZoomLevel();
        if (currentZoom !== undefined) {
          cosmographRef.current.setZoomLevel(newZoom);
        } else {
          logger.warn('Could not get current zoom level for zoom out');
        }
      } catch (error) {
        logger.warn('Zoom out failed:', error);
      }
    }, []);

    const fitView = useCallback(() => {
      if (!cosmographRef.current) return;
      
      try {
        // fitView method only accepts duration parameter, padding is set during initialization
        cosmographRef.current.fitView(config.fitViewDuration);
      } catch (error) {
        logger.warn('Fit view failed:', error);
      }
    }, [config.fitViewDuration]);

    // Incremental update methods
    const addIncrementalData = useCallback(async (newNodes: GraphNode[], newLinks: GraphLink[], runSimulation = false) => {
      if (!cosmographRef.current) return;
      
      try {
        // Set flag to prevent main Data Kit effect from running
        isIncrementalUpdateRef.current = true;
        
        // Merge new data with existing data
        const updatedNodes = [...currentNodes, ...newNodes];
        const updatedLinks = [...currentLinks, ...newLinks];
        
        // Update internal state
        setCurrentNodes(updatedNodes);
        setCurrentLinks(updatedLinks);
        
        // Transform and use Cosmograph's setData directly for efficiency
        if (cosmographRef.current.setData && updatedNodes.length > 0) {
          const transformedNodes = updatedNodes.map(node => ({
            id: String(node.id),
            label: String(node.label || node.id),
            node_type: String(node.node_type || 'Unknown'),
            centrality: Number(node.properties?.degree_centrality || node.properties?.pagerank_centrality || node.size || 1),
            degree_centrality: Number(node.properties?.degree_centrality || 0),
            pagerank_centrality: Number(node.properties?.pagerank_centrality || 0),
            betweenness_centrality: Number(node.properties?.betweenness_centrality || 0),
            eigenvector_centrality: Number(node.properties?.eigenvector_centrality || 0)
          }));
          
          const transformedLinks = updatedLinks.map(link => ({
            source: String(link.source),
            target: String(link.target),
            edge_type: String(link.edge_type || 'default'),
            weight: Number(link.weight || 1)
          }));
          
          // Use direct setData without Data Kit reprocessing for better performance
          cosmographRef.current.setData(transformedNodes, transformedLinks, runSimulation);
        }
      } catch (error) {
        logger.error('Incremental data update failed:', error);
      } finally {
        // Reset flag after a brief delay
        setTimeout(() => {
          isIncrementalUpdateRef.current = false;
        }, 100);
      }
    }, [currentNodes, currentLinks]);
    
    const updateNodes = useCallback(async (updatedNodes: GraphNode[]) => {
      if (!cosmographRef.current?.setData) return;
      
      try {
        isIncrementalUpdateRef.current = true;
        
        // Create a map for quick lookup
        const updateMap = new Map(updatedNodes.map(node => [node.id, node]));
        
        // Update existing nodes
        const newCurrentNodes = currentNodes.map(node => 
          updateMap.has(node.id) ? updateMap.get(node.id)! : node
        );
        
        setCurrentNodes(newCurrentNodes);
        
        // Transform and update directly
        const transformedNodes = newCurrentNodes.map(node => ({
          id: String(node.id),
          label: String(node.label || node.id),
          node_type: String(node.node_type || 'Unknown'),
          centrality: Number(node.properties?.degree_centrality || node.properties?.pagerank_centrality || node.size || 1),
          degree_centrality: Number(node.properties?.degree_centrality || 0),
          pagerank_centrality: Number(node.properties?.pagerank_centrality || 0),
          betweenness_centrality: Number(node.properties?.betweenness_centrality || 0),
          eigenvector_centrality: Number(node.properties?.eigenvector_centrality || 0)
        }));
        
        const transformedLinks = currentLinks.map(link => ({
          source: String(link.source),
          target: String(link.target),
          edge_type: String(link.edge_type || 'default'),
          weight: Number(link.weight || 1)
        }));
        
        cosmographRef.current.setData(transformedNodes, transformedLinks, false);
      } catch (error) {
        logger.error('Node update failed:', error);
      } finally {
        setTimeout(() => {
          isIncrementalUpdateRef.current = false;
        }, 100);
      }
    }, [currentNodes, currentLinks]);
    
    const updateLinks = useCallback(async (updatedLinks: GraphLink[]) => {
      if (!cosmographRef.current?.setData) return;
      
      try {
        isIncrementalUpdateRef.current = true;
        
        // Create a map for quick lookup by source-target pair
        const updateMap = new Map(updatedLinks.map(link => [`${link.source}-${link.target}`, link]));
        
        // Update existing links
        const newCurrentLinks = currentLinks.map(link => {
          const key = `${link.source}-${link.target}`;
          return updateMap.has(key) ? updateMap.get(key)! : link;
        });
        
        setCurrentLinks(newCurrentLinks);
        
        // Transform and update directly
        const transformedNodes = currentNodes.map(node => ({
          id: String(node.id),
          label: String(node.label || node.id),
          node_type: String(node.node_type || 'Unknown'),
          centrality: Number(node.properties?.degree_centrality || node.properties?.pagerank_centrality || node.size || 1),
          degree_centrality: Number(node.properties?.degree_centrality || 0),
          pagerank_centrality: Number(node.properties?.pagerank_centrality || 0),
          betweenness_centrality: Number(node.properties?.betweenness_centrality || 0),
          eigenvector_centrality: Number(node.properties?.eigenvector_centrality || 0)
        }));
        
        const transformedLinks = newCurrentLinks.map(link => ({
          source: String(link.source),
          target: String(link.target),
          edge_type: String(link.edge_type || 'default'),
          weight: Number(link.weight || 1)
        }));
        
        cosmographRef.current.setData(transformedNodes, transformedLinks, false);
      } catch (error) {
        logger.error('Link update failed:', error);
      } finally {
        setTimeout(() => {
          isIncrementalUpdateRef.current = false;
        }, 100);
      }
    }, [currentLinks, currentNodes]);
    
    const removeNodes = useCallback(async (nodeIds: string[]) => {
      if (!cosmographRef.current?.setData) return;
      
      try {
        isIncrementalUpdateRef.current = true;
        
        const nodeIdSet = new Set(nodeIds);
        
        // Remove nodes
        const filteredNodes = currentNodes.filter(node => !nodeIdSet.has(node.id));
        
        // Remove links connected to removed nodes
        const filteredLinks = currentLinks.filter(link => 
          !nodeIdSet.has(link.source) && !nodeIdSet.has(link.target)
        );
        
        setCurrentNodes(filteredNodes);
        setCurrentLinks(filteredLinks);
        
        // Transform and update directly
        const transformedNodes = filteredNodes.map(node => ({
          id: String(node.id),
          label: String(node.label || node.id),
          node_type: String(node.node_type || 'Unknown'),
          centrality: Number(node.properties?.degree_centrality || node.properties?.pagerank_centrality || node.size || 1),
          degree_centrality: Number(node.properties?.degree_centrality || 0),
          pagerank_centrality: Number(node.properties?.pagerank_centrality || 0),
          betweenness_centrality: Number(node.properties?.betweenness_centrality || 0),
          eigenvector_centrality: Number(node.properties?.eigenvector_centrality || 0)
        }));
        
        const transformedLinks = filteredLinks.map(link => ({
          source: String(link.source),
          target: String(link.target),
          edge_type: String(link.edge_type || 'default'),
          weight: Number(link.weight || 1)
        }));
        
        cosmographRef.current.setData(transformedNodes, transformedLinks, false);
      } catch (error) {
        logger.error('Node removal failed:', error);
      } finally {
        setTimeout(() => {
          isIncrementalUpdateRef.current = false;
        }, 100);
      }
    }, [currentNodes, currentLinks]);
    
    const removeLinks = useCallback(async (linkIds: string[]) => {
      if (!cosmographRef.current?.setData) return;
      
      try {
        isIncrementalUpdateRef.current = true;
        
        const linkIdSet = new Set(linkIds);
        
        // Remove links (assuming linkIds are in "source-target" format)
        const filteredLinks = currentLinks.filter(link => {
          const linkId = `${link.source}-${link.target}`;
          return !linkIdSet.has(linkId);
        });
        
        setCurrentLinks(filteredLinks);
        
        // Transform and update directly
        const transformedNodes = currentNodes.map(node => ({
          id: String(node.id),
          label: String(node.label || node.id),
          node_type: String(node.node_type || 'Unknown'),
          centrality: Number(node.properties?.degree_centrality || node.properties?.pagerank_centrality || node.size || 1),
          degree_centrality: Number(node.properties?.degree_centrality || 0),
          pagerank_centrality: Number(node.properties?.pagerank_centrality || 0),
          betweenness_centrality: Number(node.properties?.betweenness_centrality || 0),
          eigenvector_centrality: Number(node.properties?.eigenvector_centrality || 0)
        }));
        
        const transformedLinks = filteredLinks.map(link => ({
          source: String(link.source),
          target: String(link.target),
          edge_type: String(link.edge_type || 'default'),
          weight: Number(link.weight || 1)
        }));
        
        cosmographRef.current.setData(transformedNodes, transformedLinks, false);
      } catch (error) {
        logger.error('Link removal failed:', error);
      } finally {
        setTimeout(() => {
          isIncrementalUpdateRef.current = false;
        }, 100);
      }
    }, [currentLinks, currentNodes]);

    // Simulation control methods
    const startSimulation = useCallback((alpha = 1.0) => {
      if (cosmographRef.current && typeof cosmographRef.current.start === 'function') {
        cosmographRef.current.start(alpha);
      }
    }, []);
    
    const pauseSimulation = useCallback(() => {
      if (cosmographRef.current && typeof cosmographRef.current.pause === 'function') {
        cosmographRef.current.pause();
      }
      
      // Clear the keep-running timer
      if (simulationTimerRef.current) {
        clearInterval(simulationTimerRef.current);
        simulationTimerRef.current = null;
      }
    }, []);
    
    const resumeSimulation = useCallback(() => {
      if (cosmographRef.current && typeof cosmographRef.current.start === 'function') {
        const currentTime = Date.now();
        lastResumeTimeRef.current = currentTime;
        
        cosmographRef.current.start(0.3); // Resume with moderate energy
        setIsSimulationActive(true);
        
        
        // Use requestAnimationFrame to ensure the simulation state is properly propagated
        requestAnimationFrame(() => {
        });
      }
    }, []);
    
    const keepSimulationRunning = useCallback((enable: boolean) => {
      setKeepRunning(enable);
      
      if (enable) {
        // Start periodic simulation restarts to keep it alive
        if (simulationTimerRef.current) {
          clearInterval(simulationTimerRef.current);
        }
        
        simulationTimerRef.current = setInterval(() => {
          if (cosmographRef.current && typeof cosmographRef.current.start === 'function') {
            // Restart with low energy to keep nodes moving gently
            cosmographRef.current.start(0.1);
          }
        }, 5000); // Restart every 5 seconds
        
      } else {
        // Stop the periodic restarts
        if (simulationTimerRef.current) {
          clearInterval(simulationTimerRef.current);
          simulationTimerRef.current = null;
        }
      }
    }, []);
    
    // Cleanup simulation timer on unmount
    useEffect(() => {
      return () => {
        if (simulationTimerRef.current) {
          clearInterval(simulationTimerRef.current);
        }
      };
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
      },
      // Incremental update methods
      addIncrementalData,
      updateNodes,
      updateLinks,
      removeNodes,
      removeLinks,
      // Simulation control methods
      startSimulation,
      pauseSimulation,
      resumeSimulation,
      keepSimulationRunning,
      // External incremental flag control
      setIncrementalUpdateFlag: (enabled: boolean) => {
        isIncrementalUpdateRef.current = enabled;
      }
    }), [clearCosmographSelection, selectCosmographNode, selectCosmographNodes, zoomIn, zoomOut, fitView, addIncrementalData, updateNodes, updateLinks, removeNodes, removeLinks, startSimulation, pauseSimulation, resumeSimulation, keepSimulationRunning]);

    // Handle Cosmograph events with double-click detection
    // Cosmograph v2.0 onClick signature: (index: number | undefined, pointPosition: [number, number] | undefined, event: MouseEvent) => void
    const handleClick = async (index?: number, pointPosition?: [number, number], event?: MouseEvent) => {
      
      if (typeof index === 'number') {
        
        // Get the original node data using the index
        let originalNode: GraphNode | undefined;
        
        // Try to get the node from our transformed data using the index
        if (index >= 0 && index < transformedData.nodes.length) {
          const nodeData = transformedData.nodes[index];
          originalNode = nodeData;
        }
        
        // If we can't find the original node by index, try to query it from Cosmograph
        if (!originalNode && cosmographRef.current && typeof cosmographRef.current.getPointsByIndices === 'function') {
          try {
            const pointData = await cosmographRef.current.getPointsByIndices([index]);
            
            if (pointData && pointData.numRows && pointData.numRows > 0) {
              // Convert the point data to GraphNode format
              const pointArray = cosmographRef.current.convertCosmographDataToObject(pointData);
              if (pointArray && pointArray.length > 0) {
                const point = pointArray[0];
                originalNode = {
                  id: String(point.id || index),
                  label: String(point.label || point.id || index),
                  node_type: String(point.node_type || 'Unknown'),
                  size: Number(point.centrality || 1),
                  properties: {
                    degree_centrality: Number(point.degree_centrality || 0),
                    pagerank_centrality: Number(point.pagerank_centrality || 0),
                    betweenness_centrality: Number(point.betweenness_centrality || 0),
                    eigenvector_centrality: Number(point.eigenvector_centrality || 0),
                    centrality: Number(point.centrality || 0),
                    ...point // Include all other properties
                  }
                } as GraphNode;
              }
            }
          } catch (error) {
            logger.error('Failed to retrieve point data from Cosmograph:', error);
          }
        }
        
        if (originalNode) {
          const currentTime = Date.now();
          const timeDiff = currentTime - lastClickTimeRef.current;
          const isDoubleClick = timeDiff < 300 && lastClickedNodeRef.current?.id === originalNode.id;
          
          // Clear any existing timeout
          if (doubleClickTimeoutRef.current) {
            clearTimeout(doubleClickTimeoutRef.current);
            doubleClickTimeoutRef.current = null;
          }
          
          if (isDoubleClick) {
            // Double-click detected - select node with Cosmograph visual effects
            selectCosmographNode(originalNode);
            onNodeClick(originalNode);
            onNodeSelect(originalNode.id);
            
            // Set focus on the clicked node to show focused ring color
            if (cosmographRef.current && typeof cosmographRef.current.setFocusedPoint === 'function') {
              cosmographRef.current.setFocusedPoint(index);
            }
          } else {
            // Single click - show modal and maintain visual selection
            doubleClickTimeoutRef.current = setTimeout(() => {
              // Single click confirmed - show modal and keep node visually selected
              selectCosmographNode(originalNode!); // Keep visual selection circle
              onNodeClick(originalNode!); // Show modal
              onNodeSelect(originalNode!.id); // Update selection state
              
              // Set focus on the clicked node to show focused ring color
              if (cosmographRef.current && typeof cosmographRef.current.setFocusedPoint === 'function') {
                cosmographRef.current.setFocusedPoint(index);
              }
            }, 300);
          }
          
          // Update click tracking using refs (no re-render)
          lastClickTimeRef.current = currentTime;
          lastClickedNodeRef.current = originalNode;
        } else {
          logger.warn('Could not find or create node data for index:', index);
        }
      } else {
        // Empty space was clicked - clear all selections and return to default state
        clearCosmographSelection();
        onClearSelection?.();
      }
    };

    // Show loading state while data is being prepared
    if (isDataPreparing) {
      return (
        <div className={`relative overflow-hidden ${className} flex items-center justify-center`}>
          <div className="text-muted-foreground text-center">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mb-2 mx-auto"></div>
            <p className="text-sm">Preparing graph data...</p>
          </div>
        </div>
      );
    }

    // Show error state if Data Kit failed (with fallback)
    if (dataKitError && !cosmographData) {
      return (
        <div className={`relative overflow-hidden ${className} flex items-center justify-center`}>
          <div className="text-destructive text-center">
            <p className="text-sm">Data preparation failed: {dataKitError}</p>
            <p className="text-xs text-muted-foreground mt-1">Using fallback rendering</p>
          </div>
        </div>
      );
    }

    // Don't render if no data is available
    if (!cosmographData) {
      return (
        <div className={`relative overflow-hidden ${className} flex items-center justify-center`}>
          <div className="text-muted-foreground text-center">
            <p className="text-sm">No graph data available</p>
          </div>
        </div>
      );
    }

    return (
      <div 
        className={`relative overflow-hidden ${className}`}
      >
          <Cosmograph
            ref={cosmographRef}
            // Use Data Kit prepared data and configuration
            points={cosmographData.points}
            links={cosmographData.links}
            {...cosmographData.cosmographConfig}
            
            // Override with UI-specific configurations
            fitViewOnInit={true}
            fitViewDelay={1500} // Let nodes settle before fitting view
            fitViewDuration={config.fitViewDuration} // Use configurable duration
            fitViewPadding={config.fitViewPadding} // Use configurable padding
            initialZoomLevel={1.5}
            disableZoom={false}
            backgroundColor={config.backgroundColor}
            
            // Use Cosmograph v2.0 built-in color strategies
            pointColorStrategy={(() => {
              switch (config.colorScheme) {
                case 'by-type': return 'direct'; // Use direct strategy to ensure pointColor is used
                case 'by-centrality': 
                case 'by-pagerank': 
                case 'by-degree': return 'interpolatePalette';
                case 'by-community': return 'palette';
                default: return 'direct';
              }
            })()}
            pointColorPalette={(() => {
              switch (config.colorScheme) {
                case 'by-centrality': return ['#1e3a8a', '#3b82f6', '#60a5fa', '#93c5fd', '#dbeafe']; // Blue gradient
                case 'by-pagerank': return ['#7c2d12', '#ea580c', '#f97316', '#fb923c', '#fed7aa']; // Orange gradient  
                case 'by-degree': return ['#166534', '#16a34a', '#22c55e', '#4ade80', '#bbf7d0']; // Green gradient
                case 'by-community': return ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7', '#DDA0DD'];
                case 'by-type': 
                default: 
                  // Provide fallback colors that Cosmograph can use if our custom function returns undefined
                  return ['#4ECDC4', '#B794F6', '#F6AD55', '#90CDF4', '#FF6B6B', '#4ADE80'];
              }
            })()}
            
            // Use Cosmograph v2.0 built-in size strategies  
            pointSizeStrategy={'auto'}
            pointSizeRange={[config.minNodeSize * config.sizeMultiplier, config.maxNodeSize * config.sizeMultiplier]}
            
            // Use pointColorBy to specify which column contains the color data
            pointColorBy={config.colorScheme === 'by-type' ? 'node_type' : undefined}
            
            // Use pointColorByFn to transform node_type values into actual colors
            pointColorByFn={config.colorScheme === 'by-type' ? (nodeType: string) => {
              // Use configured color for this type
              const typeColor = config.nodeTypeColors[nodeType];
              if (typeColor) {
                return typeColor;
              }
              
              // Generate color if not configured
              const allNodeTypes = [...new Set(nodes.map(n => n.node_type).filter(Boolean))].sort();
              const typeIndex = allNodeTypes.indexOf(nodeType);
              const generatedColor = generateNodeTypeColor(nodeType, typeIndex);
              return generatedColor;
            } : undefined}
            
            // Use pointColor only for highlighting
            pointColor={(node: any) => {
              // Check if highlighted
              const isHighlighted = highlightedNodes.includes(node.id);
              if (isHighlighted) {
                return 'rgba(255, 215, 0, 0.9)'; // Gold highlight
              }
              
              // For non-type color schemes, return undefined
              if (config.colorScheme !== 'by-type') {
                return undefined;
              }
              
              // For by-type, we shouldn't reach here as pointColorByFn handles it
              return undefined;
            }}
            
            pointSize={(node: any) => {
              const isHighlighted = highlightedNodes.includes(node.id);
              if (isHighlighted) {
                // Make highlighted nodes 20% larger than strategy-calculated size
                return undefined; // Let strategy calculate, then we'll handle in CSS/other way
              }
              return undefined; // Let strategy handle sizing
            }}
            
            // Interaction
            enableDrag={true}
            enableRightClickRepulsion={true}
            onClick={handleClick}
            
            // Hover and focus styling from config
            hoveredPointCursor={config.hoveredPointCursor}
            renderHoveredPointRing={config.renderHoveredPointRing}
            hoveredPointRingColor={config.hoveredPointRingColor}
            focusedPointRingColor={config.focusedPointRingColor}
            focusedPointIndex={config.focusedPointIndex}
            renderLinks={config.renderLinks}
            
            nodeGreyoutOpacity={selectedNodes.length > 0 || highlightedNodes.length > 0 ? 0.1 : 1}
            
            // Performance
            pixelRatio={2.5}
            showFPSMonitor={false}
            
            // Zoom behavior
            enableSimulationDuringZoom={true}
            
            // Simulation - Cosmograph v2.0 API
            disableSimulation={config.disableSimulation}
            spaceSize={config.spaceSize}
            randomSeed={config.randomSeed}
            simulationRepulsion={config.repulsion}
            simulationRepulsionTheta={config.simulationRepulsionTheta}
            simulationLinkSpring={config.linkSpring}
            simulationLinkDistance={config.linkDistance}
            simulationGravity={config.gravity}
            simulationCenter={config.centerForce}
            simulationFriction={config.friction}
            simulationDecay={config.simulationDecay}
            simulationRepulsionFromMouse={config.mouseRepulsion}
            
            // Link Properties
            linkColor={config.linkColor}
            linkOpacity={config.linkOpacity}
            linkGreyoutOpacity={config.linkGreyoutOpacity}
            linkWidth={1}
            linkWidthBy={config.linkWidthBy}
            linkWidthScale={config.linkWidth}
            scaleLinksOnZoom={config.scaleLinksOnZoom}
            linkArrows={config.linkArrows}
            linkArrowsSizeScale={config.linkArrowsSizeScale}
            curvedLinks={config.curvedLinks}
            curvedLinkSegments={config.curvedLinkSegments}
            curvedLinkWeight={config.curvedLinkWeight}
            curvedLinkControlPointDistance={config.curvedLinkControlPointDistance}
            linkVisibilityDistanceRange={config.linkVisibilityDistance}
            linkVisibilityMinTransparency={config.linkVisibilityMinTransparency}
            useClassicQuadtree={config.useClassicQuadtree}
            
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
  // Optimized comparison - only re-render for essential changes
  
  // Most important: check if data references changed (should be stable during incremental updates)
  const dataChanged = prevProps.nodes !== nextProps.nodes || prevProps.links !== nextProps.links;
  
  // Check callback functions by reference (they should be stable with useCallback)
  const callbacksChanged = prevProps.onNodeClick !== nextProps.onNodeClick ||
                           prevProps.onNodeSelect !== nextProps.onNodeSelect ||
                           prevProps.onClearSelection !== nextProps.onClearSelection;
  
  // Simple reference comparison for selection arrays (should be stable)
  const selectedNodesChanged = prevProps.selectedNodes !== nextProps.selectedNodes;
  const highlightedNodesChanged = prevProps.highlightedNodes !== nextProps.highlightedNodes;
  
  // Stats and className changes
  const statsChanged = prevProps.stats !== nextProps.stats;
  const classNameChanged = prevProps.className !== nextProps.className;
  
  const shouldRerender = dataChanged || callbacksChanged || selectedNodesChanged || 
                        highlightedNodesChanged || statsChanged || classNameChanged;
  
  // Return true to skip re-render, false to re-render
  return !shouldRerender;
});

GraphCanvas.displayName = 'GraphCanvas';