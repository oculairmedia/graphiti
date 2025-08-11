import React, { useState, useEffect, useCallback, useRef } from 'react';
import { GraphNode, GraphEdge } from '../../../api/types';

export interface LoadingPhase {
  name: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
  delay: number;
  priority: number;
  progress?: number;
}

export interface ProgressiveLoadingConfig {
  // Thresholds for different loading phases
  coreNodeThreshold?: number;      // Default: 0.5 eigenvector centrality
  secondaryThreshold?: number;      // Default: 0.2 eigenvector centrality
  degreeThreshold?: number;         // Default: 5 connections
  
  // Timing configuration
  phaseDelayMs?: number;            // Default: 50ms between phases
  chunkSize?: number;               // Default: 500 nodes per chunk
  
  // Visual configuration
  fadeInDuration?: number;          // Default: 500ms
  showPlaceholders?: boolean;       // Default: true
  
  // Performance configuration
  fpsThreshold?: number;            // Default: 30 fps minimum
  backpressureDelay?: number;      // Default: 50ms when FPS drops
  
  // Loading strategy
  strategy?: 'centrality' | 'viewport' | 'temporal' | 'custom';
}

interface ProgressiveLoaderProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  config?: ProgressiveLoadingConfig;
  onPhaseComplete?: (phase: LoadingPhase) => void;
  onLoadComplete?: () => void;
  onProgress?: (phase: string, loaded: number, total: number) => void;
  children?: (state: LoaderState) => React.ReactNode;
}

interface LoaderState {
  isLoading: boolean;
  currentPhase: string | null;
  progress: number;
  loadedNodes: GraphNode[];
  loadedEdges: GraphEdge[];
  phases: LoadingPhase[];
}

/**
 * ProgressiveLoader - React component for progressive graph loading
 * Supports multiple loading strategies and performance optimization
 */
export const ProgressiveLoader: React.FC<ProgressiveLoaderProps> = ({
  nodes,
  edges,
  config = {},
  onPhaseComplete,
  onLoadComplete,
  onProgress,
  children
}) => {
  const [state, setState] = useState<LoaderState>({
    isLoading: false,
    currentPhase: null,
    progress: 0,
    loadedNodes: [],
    loadedEdges: [],
    phases: []
  });

  const abortControllerRef = useRef<AbortController | null>(null);
  const animationFrameRef = useRef<number | null>(null);

  // Default configuration
  const fullConfig: Required<ProgressiveLoadingConfig> = {
    coreNodeThreshold: config.coreNodeThreshold ?? 0.5,
    secondaryThreshold: config.secondaryThreshold ?? 0.2,
    degreeThreshold: config.degreeThreshold ?? 5,
    phaseDelayMs: config.phaseDelayMs ?? 50,
    chunkSize: config.chunkSize ?? 500,
    fadeInDuration: config.fadeInDuration ?? 500,
    showPlaceholders: config.showPlaceholders ?? true,
    fpsThreshold: config.fpsThreshold ?? 30,
    backpressureDelay: config.backpressureDelay ?? 50,
    strategy: config.strategy ?? 'centrality'
  };

  // Prepare loading phases based on strategy
  const prepareLoadingPhases = useCallback((
    nodes: GraphNode[],
    edges: GraphEdge[]
  ): LoadingPhase[] => {
    switch (fullConfig.strategy) {
      case 'centrality':
        return prepareCentralityPhases(nodes, edges, fullConfig);
      case 'viewport':
        return prepareViewportPhases(nodes, edges, fullConfig);
      case 'temporal':
        return prepareTemporalPhases(nodes, edges, fullConfig);
      default:
        return prepareCentralityPhases(nodes, edges, fullConfig);
    }
  }, [fullConfig]);

  // Centrality-based loading phases
  const prepareCentralityPhases = (
    nodes: GraphNode[],
    edges: GraphEdge[],
    config: Required<ProgressiveLoadingConfig>
  ): LoadingPhase[] => {
    const coreNodeIds = new Set<string>();
    const secondaryNodeIds = new Set<string>();
    
    // Phase 1: Core nodes
    const coreNodes = nodes.filter(node => {
      const eigenvector = node.properties?.eigenvector_centrality || 0;
      const degree = node.properties?.degree_centrality || 0;
      
      if (eigenvector > config.coreNodeThreshold || degree > 30) {
        coreNodeIds.add(node.id);
        return true;
      }
      return false;
    });
    
    // Phase 2: Secondary nodes
    const secondaryNodes = nodes.filter(node => {
      if (coreNodeIds.has(node.id)) return false;
      
      const eigenvector = node.properties?.eigenvector_centrality || 0;
      const degree = node.properties?.degree_centrality || 0;
      
      if (eigenvector > config.secondaryThreshold || degree > config.degreeThreshold) {
        secondaryNodeIds.add(node.id);
        return true;
      }
      return false;
    });
    
    // Phase 3: Peripheral nodes
    const peripheralNodes = nodes.filter(node => 
      !coreNodeIds.has(node.id) && !secondaryNodeIds.has(node.id)
    );
    
    // Filter edges for each phase
    const coreEdges = edges.filter(edge => 
      coreNodeIds.has(edge.from) && coreNodeIds.has(edge.to)
    );
    
    const secondaryEdges = edges.filter(edge => {
      const combinedIds = new Set([...coreNodeIds, ...secondaryNodeIds]);
      return combinedIds.has(edge.from) && combinedIds.has(edge.to);
    });
    
    const peripheralEdges = edges; // All edges in final phase
    
    return [
      {
        name: 'core',
        nodes: coreNodes,
        edges: coreEdges,
        delay: 0,
        priority: 1
      },
      {
        name: 'secondary',
        nodes: secondaryNodes,
        edges: secondaryEdges,
        delay: config.phaseDelayMs,
        priority: 2
      },
      {
        name: 'peripheral',
        nodes: peripheralNodes,
        edges: peripheralEdges,
        delay: config.phaseDelayMs * 2,
        priority: 3
      }
    ].filter(phase => phase.nodes.length > 0);
  };

  // Viewport-based loading phases
  const prepareViewportPhases = (
    nodes: GraphNode[],
    edges: GraphEdge[],
    config: Required<ProgressiveLoadingConfig>
  ): LoadingPhase[] => {
    // Group nodes by distance from center
    const center = { x: 0, y: 0 };
    const nodesWithDistance = nodes.map(node => ({
      node,
      distance: Math.sqrt(
        Math.pow((node.x || 0) - center.x, 2) + 
        Math.pow((node.y || 0) - center.y, 2)
      )
    }));
    
    nodesWithDistance.sort((a, b) => a.distance - b.distance);
    
    // Create 3 distance-based phases
    const third = Math.floor(nodes.length / 3);
    const phases: LoadingPhase[] = [];
    
    for (let i = 0; i < 3; i++) {
      const start = i * third;
      const end = i === 2 ? nodes.length : (i + 1) * third;
      const phaseNodes = nodesWithDistance.slice(start, end).map(n => n.node);
      const nodeIds = new Set(phaseNodes.map(n => n.id));
      
      phases.push({
        name: `viewport-${i}`,
        nodes: phaseNodes,
        edges: edges.filter(e => nodeIds.has(e.from) && nodeIds.has(e.to)),
        delay: i * config.phaseDelayMs,
        priority: i + 1
      });
    }
    
    return phases;
  };

  // Temporal-based loading phases
  const prepareTemporalPhases = (
    nodes: GraphNode[],
    edges: GraphEdge[],
    config: Required<ProgressiveLoadingConfig>
  ): LoadingPhase[] => {
    // Sort nodes by creation time
    const sortedNodes = [...nodes].sort((a, b) => {
      const aTime = a.created_at ? new Date(a.created_at).getTime() : 0;
      const bTime = b.created_at ? new Date(b.created_at).getTime() : 0;
      return aTime - bTime;
    });
    
    // Create 3 temporal phases
    const third = Math.floor(nodes.length / 3);
    const phases: LoadingPhase[] = [];
    
    for (let i = 0; i < 3; i++) {
      const start = i * third;
      const end = i === 2 ? nodes.length : (i + 1) * third;
      const phaseNodes = sortedNodes.slice(start, end);
      const nodeIds = new Set(phaseNodes.map(n => n.id));
      
      phases.push({
        name: `temporal-${i}`,
        nodes: phaseNodes,
        edges: edges.filter(e => nodeIds.has(e.from) && nodeIds.has(e.to)),
        delay: i * config.phaseDelayMs,
        priority: i + 1
      });
    }
    
    return phases;
  };

  // Load phases progressively
  const loadPhases = useCallback(async (phases: LoadingPhase[]) => {
    setState(prev => ({ ...prev, isLoading: true }));
    abortControllerRef.current = new AbortController();
    
    const allLoadedNodes: GraphNode[] = [];
    const allLoadedEdges: GraphEdge[] = [];
    
    try {
      for (let i = 0; i < phases.length; i++) {
        if (abortControllerRef.current.signal.aborted) break;
        
        const phase = phases[i];
        setState(prev => ({ 
          ...prev, 
          currentPhase: phase.name,
          progress: (i / phases.length) * 100
        }));
        
        // Wait for phase delay
        if (phase.delay > 0) {
          await new Promise(resolve => setTimeout(resolve, phase.delay));
        }
        
        // Load phase in chunks if needed
        if (phase.nodes.length > fullConfig.chunkSize) {
          await loadPhaseInChunks(phase, allLoadedNodes, allLoadedEdges);
        } else {
          // Load entire phase
          allLoadedNodes.push(...phase.nodes);
          allLoadedEdges.push(...phase.edges);
          
          setState(prev => ({
            ...prev,
            loadedNodes: [...allLoadedNodes],
            loadedEdges: [...allLoadedEdges]
          }));
          
          onProgress?.(phase.name, phase.nodes.length, phase.nodes.length);
          onPhaseComplete?.(phase);
        }
      }
      
      setState(prev => ({ 
        ...prev, 
        isLoading: false,
        currentPhase: null,
        progress: 100
      }));
      
      onLoadComplete?.();
      
    } catch (error) {
      console.error('Progressive loading error:', error);
      setState(prev => ({ ...prev, isLoading: false }));
    }
  }, [fullConfig.chunkSize, onPhaseComplete, onLoadComplete, onProgress]);

  // Load phase in chunks
  const loadPhaseInChunks = async (
    phase: LoadingPhase,
    allLoadedNodes: GraphNode[],
    allLoadedEdges: GraphEdge[]
  ) => {
    const chunks = Math.ceil(phase.nodes.length / fullConfig.chunkSize);
    
    for (let i = 0; i < chunks; i++) {
      if (abortControllerRef.current?.signal.aborted) break;
      
      const start = i * fullConfig.chunkSize;
      const end = Math.min(start + fullConfig.chunkSize, phase.nodes.length);
      const chunkNodes = phase.nodes.slice(start, end);
      const nodeIds = new Set(chunkNodes.map(n => n.id));
      const chunkEdges = phase.edges.filter(e => 
        nodeIds.has(e.from) || nodeIds.has(e.to)
      );
      
      allLoadedNodes.push(...chunkNodes);
      allLoadedEdges.push(...chunkEdges);
      
      // Use requestAnimationFrame for smooth updates
      await new Promise(resolve => {
        animationFrameRef.current = requestAnimationFrame(() => {
          setState(prev => ({
            ...prev,
            loadedNodes: [...allLoadedNodes],
            loadedEdges: [...allLoadedEdges]
          }));
          resolve(undefined);
        });
      });
      
      onProgress?.(phase.name, end, phase.nodes.length);
      
      // Small delay between chunks
      if (i < chunks - 1) {
        await new Promise(resolve => setTimeout(resolve, 10));
      }
    }
    
    onPhaseComplete?.(phase);
  };

  // Abort loading
  const abort = useCallback(() => {
    abortControllerRef.current?.abort();
    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current);
    }
    setState(prev => ({ ...prev, isLoading: false }));
  }, []);

  // Start loading when nodes/edges change
  useEffect(() => {
    if (nodes.length === 0 || state.isLoading) return;
    
    const phases = prepareLoadingPhases(nodes, edges);
    setState(prev => ({ ...prev, phases }));
    loadPhases(phases);
    
    return () => {
      abort();
    };
  }, [nodes.length, edges.length]); // Only depend on lengths to prevent re-runs

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      abort();
    };
  }, [abort]);

  return <>{children?.(state)}</>;
};

// Hook for using progressive loader
export const useProgressiveLoader = (
  nodes: GraphNode[],
  edges: GraphEdge[],
  config?: ProgressiveLoadingConfig
) => {
  const [state, setState] = useState<LoaderState>({
    isLoading: false,
    currentPhase: null,
    progress: 0,
    loadedNodes: [],
    loadedEdges: [],
    phases: []
  });

  useEffect(() => {
    // Create internal loader instance
    const loader = document.createElement('div');
    
    // Use ProgressiveLoader internally
    // This is a simplified version - in production, use proper React rendering
    
    return () => {
      // Cleanup
    };
  }, [nodes, edges, config]);

  return state;
};