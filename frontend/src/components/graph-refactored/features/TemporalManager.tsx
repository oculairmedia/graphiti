import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { GraphNode, GraphEdge } from '../../../api/types';

interface TemporalRange {
  start: Date;
  end: Date;
}

interface TemporalWindow {
  range: TemporalRange;
  resolution: 'hour' | 'day' | 'week' | 'month' | 'year';
  playbackSpeed: number; // 1x, 2x, 4x, etc
  isPlaying: boolean;
}

interface TemporalConfig {
  enableTimeline?: boolean;
  enablePlayback?: boolean;
  enableHeatmap?: boolean;
  defaultResolution?: TemporalWindow['resolution'];
  defaultPlaybackSpeed?: number;
  animationDuration?: number; // ms
  showFuture?: boolean;
  showPast?: boolean;
  fadeOutDuration?: number; // ms for fading old data
}

interface TemporalManagerProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  config?: TemporalConfig;
  onTimeChange?: (window: TemporalWindow) => void;
  onFilteredData?: (nodes: GraphNode[], edges: GraphEdge[]) => void;
  onPlaybackStateChange?: (isPlaying: boolean) => void;
  children?: React.ReactNode;
}

interface TemporalState {
  currentWindow: TemporalWindow;
  dataRange: TemporalRange | null;
  filteredNodes: GraphNode[];
  filteredEdges: GraphEdge[];
  heatmapData: Map<string, number>;
  playbackPosition: number; // 0 to 1
  isAnimating: boolean;
}

/**
 * TemporalManager - Manages temporal data visualization and playback
 * Provides timeline controls, filtering, and temporal analysis
 */
export const TemporalManager: React.FC<TemporalManagerProps> = ({
  nodes,
  edges,
  config = {},
  onTimeChange,
  onFilteredData,
  onPlaybackStateChange,
  children
}) => {
  const [state, setState] = useState<TemporalState>({
    currentWindow: {
      range: { start: new Date(), end: new Date() },
      resolution: config.defaultResolution || 'day',
      playbackSpeed: config.defaultPlaybackSpeed || 1,
      isPlaying: false
    },
    dataRange: null,
    filteredNodes: nodes,
    filteredEdges: edges,
    heatmapData: new Map(),
    playbackPosition: 0,
    isAnimating: false
  });

  const playbackIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const animationFrameRef = useRef<number | null>(null);

  // Default configuration
  const fullConfig: Required<TemporalConfig> = {
    enableTimeline: config.enableTimeline ?? true,
    enablePlayback: config.enablePlayback ?? true,
    enableHeatmap: config.enableHeatmap ?? true,
    defaultResolution: config.defaultResolution ?? 'day',
    defaultPlaybackSpeed: config.defaultPlaybackSpeed ?? 1,
    animationDuration: config.animationDuration ?? 500,
    showFuture: config.showFuture ?? false,
    showPast: config.showPast ?? true,
    fadeOutDuration: config.fadeOutDuration ?? 1000
  };

  // Calculate data time range
  const calculateDataRange = useCallback((
    nodes: GraphNode[],
    edges: GraphEdge[]
  ): TemporalRange | null => {
    let minTime = Infinity;
    let maxTime = -Infinity;
    let hasTemporalData = false;

    // Check nodes
    nodes.forEach(node => {
      if (node.created_at) {
        hasTemporalData = true;
        const time = new Date(node.created_at).getTime();
        minTime = Math.min(minTime, time);
        maxTime = Math.max(maxTime, time);
      }
      if (node.updated_at) {
        const time = new Date(node.updated_at).getTime();
        maxTime = Math.max(maxTime, time);
      }
    });

    // Check edges
    edges.forEach(edge => {
      if (edge.created_at) {
        hasTemporalData = true;
        const time = new Date(edge.created_at).getTime();
        minTime = Math.min(minTime, time);
        maxTime = Math.max(maxTime, time);
      }
    });

    if (!hasTemporalData) return null;

    return {
      start: new Date(minTime),
      end: new Date(maxTime)
    };
  }, []);

  // Filter data by temporal window
  const filterByTimeWindow = useCallback((
    nodes: GraphNode[],
    edges: GraphEdge[],
    window: TemporalWindow
  ): { nodes: GraphNode[]; edges: GraphEdge[] } => {
    const startTime = window.range.start.getTime();
    const endTime = window.range.end.getTime();
    const now = Date.now();

    // Filter nodes
    const filteredNodes = nodes.filter(node => {
      if (!node.created_at) return fullConfig.showPast; // Include if no timestamp
      
      const nodeTime = new Date(node.created_at).getTime();
      
      // Check if in window
      if (nodeTime < startTime) return fullConfig.showPast;
      if (nodeTime > endTime) return fullConfig.showFuture;
      
      return true;
    }).map(node => {
      // Calculate fade based on age
      if (!fullConfig.fadeOutDuration || !node.created_at) return node;
      
      const nodeTime = new Date(node.created_at).getTime();
      const age = endTime - nodeTime;
      const fadeRatio = Math.max(0, 1 - (age / fullConfig.fadeOutDuration));
      
      return {
        ...node,
        opacity: fadeRatio,
        properties: {
          ...node.properties,
          temporal_fade: fadeRatio
        }
      };
    });

    // Get valid node IDs
    const validNodeIds = new Set(filteredNodes.map(n => n.id));

    // Filter edges
    const filteredEdges = edges.filter(edge => {
      // Edge must connect valid nodes
      if (!validNodeIds.has(edge.from) || !validNodeIds.has(edge.to)) {
        return false;
      }
      
      // Check edge timestamp if available
      if (edge.created_at) {
        const edgeTime = new Date(edge.created_at).getTime();
        if (edgeTime < startTime) return fullConfig.showPast;
        if (edgeTime > endTime) return fullConfig.showFuture;
      }
      
      return true;
    });

    return { nodes: filteredNodes, edges: filteredEdges };
  }, [fullConfig]);

  // Generate temporal heatmap
  const generateHeatmap = useCallback((
    nodes: GraphNode[],
    resolution: TemporalWindow['resolution']
  ): Map<string, number> => {
    const heatmap = new Map<string, number>();
    
    nodes.forEach(node => {
      if (!node.created_at) return;
      
      const date = new Date(node.created_at);
      const key = getTemporalKey(date, resolution);
      
      heatmap.set(key, (heatmap.get(key) || 0) + 1);
    });
    
    return heatmap;
  }, []);

  // Get temporal key based on resolution
  function getTemporalKey(date: Date, resolution: TemporalWindow['resolution']): string {
    switch (resolution) {
      case 'hour':
        return `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}-${date.getHours()}`;
      case 'day':
        return `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`;
      case 'week':
        const week = Math.floor(date.getDate() / 7);
        return `${date.getFullYear()}-${date.getMonth()}-W${week}`;
      case 'month':
        return `${date.getFullYear()}-${date.getMonth()}`;
      case 'year':
        return `${date.getFullYear()}`;
      default:
        return date.toISOString();
    }
  }

  // Update time window
  const setTimeWindow = useCallback((window: Partial<TemporalWindow>) => {
    setState(prev => {
      const newWindow = { ...prev.currentWindow, ...window };
      const filtered = filterByTimeWindow(nodes, edges, newWindow);
      
      return {
        ...prev,
        currentWindow: newWindow,
        filteredNodes: filtered.nodes,
        filteredEdges: filtered.edges
      };
    });
  }, [nodes, edges, filterByTimeWindow]);

  // Play/pause playback
  const togglePlayback = useCallback(() => {
    setState(prev => {
      const isPlaying = !prev.currentWindow.isPlaying;
      
      if (isPlaying) {
        startPlayback();
      } else {
        stopPlayback();
      }
      
      onPlaybackStateChange?.(isPlaying);
      
      return {
        ...prev,
        currentWindow: {
          ...prev.currentWindow,
          isPlaying
        }
      };
    });
  }, []);

  // Start playback animation
  const startPlayback = useCallback(() => {
    if (!state.dataRange) return;
    
    const duration = state.dataRange.end.getTime() - state.dataRange.start.getTime();
    const step = (100 / state.currentWindow.playbackSpeed); // ms per frame
    
    playbackIntervalRef.current = setInterval(() => {
      setState(prev => {
        const newPosition = prev.playbackPosition + (step / duration);
        
        if (newPosition >= 1) {
          stopPlayback();
          return { ...prev, playbackPosition: 0 };
        }
        
        // Update window based on position
        const currentTime = prev.dataRange!.start.getTime() + 
          (newPosition * (prev.dataRange!.end.getTime() - prev.dataRange!.start.getTime()));
        
        const windowSize = getWindowSize(prev.currentWindow.resolution);
        const newWindow: TemporalWindow = {
          ...prev.currentWindow,
          range: {
            start: new Date(currentTime),
            end: new Date(currentTime + windowSize)
          }
        };
        
        const filtered = filterByTimeWindow(nodes, edges, newWindow);
        
        onTimeChange?.(newWindow);
        onFilteredData?.(filtered.nodes, filtered.edges);
        
        return {
          ...prev,
          currentWindow: newWindow,
          filteredNodes: filtered.nodes,
          filteredEdges: filtered.edges,
          playbackPosition: newPosition
        };
      });
    }, step);
  }, [state.dataRange, state.currentWindow, nodes, edges, filterByTimeWindow, onTimeChange, onFilteredData]);

  // Stop playback
  const stopPlayback = useCallback(() => {
    if (playbackIntervalRef.current) {
      clearInterval(playbackIntervalRef.current);
      playbackIntervalRef.current = null;
    }
    
    setState(prev => ({
      ...prev,
      currentWindow: {
        ...prev.currentWindow,
        isPlaying: false
      }
    }));
    
    onPlaybackStateChange?.(false);
  }, [onPlaybackStateChange]);

  // Get window size based on resolution
  function getWindowSize(resolution: TemporalWindow['resolution']): number {
    switch (resolution) {
      case 'hour': return 60 * 60 * 1000;
      case 'day': return 24 * 60 * 60 * 1000;
      case 'week': return 7 * 24 * 60 * 60 * 1000;
      case 'month': return 30 * 24 * 60 * 60 * 1000;
      case 'year': return 365 * 24 * 60 * 60 * 1000;
      default: return 24 * 60 * 60 * 1000;
    }
  }

  // Jump to specific time
  const jumpToTime = useCallback((date: Date) => {
    const windowSize = getWindowSize(state.currentWindow.resolution);
    const newWindow: TemporalWindow = {
      ...state.currentWindow,
      range: {
        start: date,
        end: new Date(date.getTime() + windowSize)
      }
    };
    
    setTimeWindow(newWindow);
  }, [state.currentWindow.resolution, setTimeWindow]);

  // Change resolution
  const setResolution = useCallback((resolution: TemporalWindow['resolution']) => {
    setTimeWindow({ resolution });
  }, [setTimeWindow]);

  // Set playback speed
  const setPlaybackSpeed = useCallback((speed: number) => {
    setTimeWindow({ playbackSpeed: speed });
  }, [setTimeWindow]);

  // Analyze temporal patterns
  const analyzeTemporalPatterns = useCallback((): {
    peaks: Array<{ time: Date; count: number }>;
    trends: Array<{ period: string; trend: 'increasing' | 'decreasing' | 'stable' }>;
    clusters: Array<{ start: Date; end: Date; intensity: number }>;
  } => {
    const heatmap = generateHeatmap(nodes, state.currentWindow.resolution);
    
    // Find peaks
    const peaks: Array<{ time: Date; count: number }> = [];
    const avgCount = Array.from(heatmap.values()).reduce((a, b) => a + b, 0) / heatmap.size;
    
    heatmap.forEach((count, key) => {
      if (count > avgCount * 1.5) { // Peak if 50% above average
        // Parse key back to date (simplified)
        peaks.push({ time: new Date(), count });
      }
    });
    
    // Detect trends (simplified)
    const trends: Array<{ period: string; trend: 'increasing' | 'decreasing' | 'stable' }> = [];
    
    // Detect clusters (simplified)
    const clusters: Array<{ start: Date; end: Date; intensity: number }> = [];
    
    return { peaks, trends, clusters };
  }, [nodes, state.currentWindow.resolution, generateHeatmap]);

  // Initialize data range
  useEffect(() => {
    const range = calculateDataRange(nodes, edges);
    if (range) {
      setState(prev => ({
        ...prev,
        dataRange: range,
        currentWindow: {
          ...prev.currentWindow,
          range
        }
      }));
      
      // Generate initial heatmap
      const heatmap = generateHeatmap(nodes, state.currentWindow.resolution);
      setState(prev => ({ ...prev, heatmapData: heatmap }));
    }
  }, [nodes, edges, calculateDataRange, generateHeatmap, state.currentWindow.resolution]);

  // Filter data when window changes
  useEffect(() => {
    const filtered = filterByTimeWindow(nodes, edges, state.currentWindow);
    setState(prev => ({
      ...prev,
      filteredNodes: filtered.nodes,
      filteredEdges: filtered.edges
    }));
    
    onFilteredData?.(filtered.nodes, filtered.edges);
  }, [nodes, edges, state.currentWindow, filterByTimeWindow, onFilteredData]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      stopPlayback();
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
    };
  }, [stopPlayback]);

  // Context value
  const contextValue = useMemo(() => ({
    ...state,
    setTimeWindow,
    togglePlayback,
    jumpToTime,
    setResolution,
    setPlaybackSpeed,
    analyzeTemporalPatterns,
    config: fullConfig
  }), [state, setTimeWindow, togglePlayback, jumpToTime, setResolution, setPlaybackSpeed, analyzeTemporalPatterns, fullConfig]);

  return (
    <TemporalContext.Provider value={contextValue}>
      {children}
    </TemporalContext.Provider>
  );
};

// Context
const TemporalContext = React.createContext<{
  currentWindow: TemporalWindow;
  dataRange: TemporalRange | null;
  filteredNodes: GraphNode[];
  filteredEdges: GraphEdge[];
  heatmapData: Map<string, number>;
  playbackPosition: number;
  isAnimating: boolean;
  setTimeWindow: (window: Partial<TemporalWindow>) => void;
  togglePlayback: () => void;
  jumpToTime: (date: Date) => void;
  setResolution: (resolution: TemporalWindow['resolution']) => void;
  setPlaybackSpeed: (speed: number) => void;
  analyzeTemporalPatterns: () => any;
  config: Required<TemporalConfig>;
}>({
  currentWindow: {
    range: { start: new Date(), end: new Date() },
    resolution: 'day',
    playbackSpeed: 1,
    isPlaying: false
  },
  dataRange: null,
  filteredNodes: [],
  filteredEdges: [],
  heatmapData: new Map(),
  playbackPosition: 0,
  isAnimating: false,
  setTimeWindow: () => {},
  togglePlayback: () => {},
  jumpToTime: () => {},
  setResolution: () => {},
  setPlaybackSpeed: () => {},
  analyzeTemporalPatterns: () => ({}),
  config: {
    enableTimeline: true,
    enablePlayback: true,
    enableHeatmap: true,
    defaultResolution: 'day',
    defaultPlaybackSpeed: 1,
    animationDuration: 500,
    showFuture: false,
    showPast: true,
    fadeOutDuration: 1000
  }
});

export const useTemporal = () => React.useContext(TemporalContext);