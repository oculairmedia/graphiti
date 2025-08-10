import { useRef, useCallback, useEffect, useMemo, useState } from 'react';
import { GraphNode } from '../../api/types';
import { GraphLink } from './useGraphData';

export interface RenderConfig {
  // Performance
  enableVirtualization?: boolean;
  virtualizeThreshold?: number;
  viewportPadding?: number;
  
  // Visual
  nodeSize?: number;
  linkWidth?: number;
  linkOpacity?: number;
  nodeOpacity?: number;
  labelSize?: number;
  labelOpacity?: number;
  
  // Colors
  backgroundColor?: string;
  nodeColor?: string | ((node: GraphNode) => string);
  linkColor?: string | ((link: GraphLink) => string);
  labelColor?: string;
  
  // Interaction
  hoverScale?: number;
  selectedScale?: number;
  highlightOpacity?: number;
  
  // Physics
  enableSimulation?: boolean;
  simulationStrength?: number;
  linkDistance?: number;
  chargeStrength?: number;
  
  // Layout
  layoutType?: 'force' | 'circular' | 'hierarchical' | 'radial';
}

export interface ViewportState {
  x: number;
  y: number;
  zoom: number;
  width: number;
  height: number;
}

export interface RenderStats {
  fps: number;
  renderTime: number;
  visibleNodes: number;
  visibleLinks: number;
  culledNodes: number;
  culledLinks: number;
}

export interface GraphRendererState {
  isRendering: boolean;
  viewport: ViewportState;
  renderStats: RenderStats;
  hoveredNode: GraphNode | null;
  selectedNodes: Set<string>;
  highlightedNodes: Set<string>;
  visibleBounds: {
    minX: number;
    maxX: number;
    minY: number;
    maxY: number;
  };
}

export interface GraphRendererActions {
  // Viewport
  setViewport: (viewport: Partial<ViewportState>) => void;
  panTo: (x: number, y: number, duration?: number) => void;
  zoomTo: (zoom: number, centerX?: number, centerY?: number, duration?: number) => void;
  fitToNodes: (nodeIds?: string[], padding?: number) => void;
  resetViewport: () => void;
  
  // Selection
  selectNode: (nodeId: string, multi?: boolean) => void;
  deselectNode: (nodeId: string) => void;
  clearSelection: () => void;
  highlightNodes: (nodeIds: string[]) => void;
  clearHighlights: () => void;
  
  // Rendering
  forceRender: () => void;
  pauseRendering: () => void;
  resumeRendering: () => void;
  
  // Export
  exportImage: (format?: 'png' | 'jpeg' | 'svg') => Promise<Blob>;
  exportData: () => { nodes: GraphNode[]; links: GraphLink[] };
}

/**
 * Custom hook for managing graph rendering with virtual viewport culling
 */
export function useGraphRenderer(
  nodes: GraphNode[],
  links: GraphLink[],
  canvasRef: React.RefObject<HTMLCanvasElement>,
  config: RenderConfig = {}
): [GraphRendererState, GraphRendererActions] {
  const {
    enableVirtualization = true,
    virtualizeThreshold = 1000,
    viewportPadding = 100,
    nodeSize = 5,
    linkWidth = 1,
    linkOpacity = 0.3,
    nodeOpacity = 0.9,
    backgroundColor = '#000000',
    enableSimulation = true,
  } = config;

  // State
  const [isRendering, setIsRendering] = useState(true);
  const [viewport, setViewportState] = useState<ViewportState>({
    x: 0,
    y: 0,
    zoom: 1,
    width: 800,
    height: 600
  });
  const [hoveredNode, setHoveredNode] = useState<GraphNode | null>(null);
  const [selectedNodes, setSelectedNodes] = useState<Set<string>>(new Set());
  const [highlightedNodes, setHighlightedNodes] = useState<Set<string>>(new Set());
  const [renderStats, setRenderStats] = useState<RenderStats>({
    fps: 0,
    renderTime: 0,
    visibleNodes: 0,
    visibleLinks: 0,
    culledNodes: 0,
    culledLinks: 0
  });

  // Refs for performance
  const animationFrameRef = useRef<number | null>(null);
  const lastFrameTimeRef = useRef(0);
  const fpsHistoryRef = useRef<number[]>([]);
  const nodePositionsRef = useRef<Map<string, { x: number; y: number }>>(new Map());
  const spatialIndexRef = useRef<SpatialIndex | null>(null);

  // Calculate visible bounds
  const visibleBounds = useMemo(() => {
    const padding = viewportPadding / viewport.zoom;
    return {
      minX: (viewport.x - padding) / viewport.zoom,
      maxX: (viewport.x + viewport.width + padding) / viewport.zoom,
      minY: (viewport.y - padding) / viewport.zoom,
      maxY: (viewport.y + viewport.height + padding) / viewport.zoom
    };
  }, [viewport, viewportPadding]);

  // Filter visible nodes and links
  const { visibleNodes, visibleLinks } = useMemo(() => {
    if (!enableVirtualization || nodes.length < virtualizeThreshold) {
      return { visibleNodes: nodes, visibleLinks: links };
    }

    // Use spatial index for efficient culling
    const visibleNodeIds = new Set<string>();
    const filteredNodes = nodes.filter(node => {
      const pos = nodePositionsRef.current.get(node.id);
      if (!pos) return false;
      
      const isVisible = 
        pos.x >= visibleBounds.minX &&
        pos.x <= visibleBounds.maxX &&
        pos.y >= visibleBounds.minY &&
        pos.y <= visibleBounds.maxY;
      
      if (isVisible) {
        visibleNodeIds.add(node.id);
      }
      return isVisible;
    });

    const filteredLinks = links.filter(link => 
      visibleNodeIds.has(link.source) || visibleNodeIds.has(link.target)
    );

    return {
      visibleNodes: filteredNodes,
      visibleLinks: filteredLinks
    };
  }, [nodes, links, enableVirtualization, virtualizeThreshold, visibleBounds]);

  // Update render stats
  useEffect(() => {
    setRenderStats(prev => ({
      ...prev,
      visibleNodes: visibleNodes.length,
      visibleLinks: visibleLinks.length,
      culledNodes: nodes.length - visibleNodes.length,
      culledLinks: links.length - visibleLinks.length
    }));
  }, [visibleNodes, visibleLinks, nodes.length, links.length]);

  // Render loop
  const render = useCallback(() => {
    if (!canvasRef.current || !isRendering) return;
    
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const startTime = performance.now();

    // Clear canvas
    ctx.fillStyle = backgroundColor;
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    // Apply viewport transform
    ctx.save();
    ctx.translate(-viewport.x, -viewport.y);
    ctx.scale(viewport.zoom, viewport.zoom);

    // Render links
    ctx.globalAlpha = linkOpacity;
    ctx.strokeStyle = typeof config.linkColor === 'string' ? config.linkColor : '#666';
    ctx.lineWidth = linkWidth / viewport.zoom;
    
    visibleLinks.forEach(link => {
      const sourcePos = nodePositionsRef.current.get(link.source);
      const targetPos = nodePositionsRef.current.get(link.target);
      
      if (sourcePos && targetPos) {
        ctx.beginPath();
        ctx.moveTo(sourcePos.x, sourcePos.y);
        ctx.lineTo(targetPos.x, targetPos.y);
        ctx.stroke();
      }
    });

    // Render nodes
    ctx.globalAlpha = nodeOpacity;
    visibleNodes.forEach(node => {
      const pos = nodePositionsRef.current.get(node.id);
      if (!pos) return;

      // Determine node appearance
      const isSelected = selectedNodes.has(node.id);
      const isHighlighted = highlightedNodes.has(node.id);
      const isHovered = hoveredNode?.id === node.id;
      
      let scale = 1;
      if (isHovered) scale = config.hoverScale || 1.5;
      else if (isSelected) scale = config.selectedScale || 1.3;
      else if (isHighlighted) scale = 1.2;

      const radius = (nodeSize * scale) / viewport.zoom;
      
      // Set node color
      if (typeof config.nodeColor === 'function') {
        ctx.fillStyle = config.nodeColor(node);
      } else {
        ctx.fillStyle = config.nodeColor || '#4FC3F7';
      }

      // Draw node
      ctx.beginPath();
      ctx.arc(pos.x, pos.y, radius, 0, Math.PI * 2);
      ctx.fill();

      // Draw label if zoomed in enough
      if (viewport.zoom > 0.5 && (isHovered || isSelected)) {
        ctx.fillStyle = config.labelColor || '#FFFFFF';
        ctx.font = `${config.labelSize || 12}px Arial`;
        ctx.globalAlpha = config.labelOpacity || 0.8;
        ctx.fillText(node.name || node.id, pos.x + radius + 5, pos.y);
      }
    });

    ctx.restore();

    // Calculate FPS
    const renderTime = performance.now() - startTime;
    const currentTime = performance.now();
    const deltaTime = currentTime - lastFrameTimeRef.current;
    const fps = 1000 / deltaTime;
    
    fpsHistoryRef.current.push(fps);
    if (fpsHistoryRef.current.length > 60) {
      fpsHistoryRef.current.shift();
    }
    
    const avgFps = fpsHistoryRef.current.reduce((a, b) => a + b, 0) / fpsHistoryRef.current.length;
    
    setRenderStats(prev => ({
      ...prev,
      fps: Math.round(avgFps),
      renderTime: Math.round(renderTime * 100) / 100
    }));
    
    lastFrameTimeRef.current = currentTime;

    // Continue render loop
    if (isRendering) {
      animationFrameRef.current = requestAnimationFrame(render);
    }
  }, [
    canvasRef,
    isRendering,
    viewport,
    visibleNodes,
    visibleLinks,
    hoveredNode,
    selectedNodes,
    highlightedNodes,
    backgroundColor,
    linkOpacity,
    linkWidth,
    nodeOpacity,
    nodeSize,
    config
  ]);

  // Start/stop render loop
  useEffect(() => {
    if (isRendering) {
      animationFrameRef.current = requestAnimationFrame(render);
    } else if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current);
    }

    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
    };
  }, [isRendering, render]);

  // Viewport actions
  const setViewport = useCallback((updates: Partial<ViewportState>) => {
    setViewportState(prev => ({ ...prev, ...updates }));
  }, []);

  const panTo = useCallback((x: number, y: number, duration = 300) => {
    // Implement smooth panning animation
    const startX = viewport.x;
    const startY = viewport.y;
    const deltaX = x - startX;
    const deltaY = y - startY;
    const startTime = performance.now();

    const animate = () => {
      const elapsed = performance.now() - startTime;
      const progress = Math.min(elapsed / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3); // Ease out cubic

      setViewport({
        x: startX + deltaX * eased,
        y: startY + deltaY * eased
      });

      if (progress < 1) {
        requestAnimationFrame(animate);
      }
    };

    animate();
  }, [viewport, setViewport]);

  const zoomTo = useCallback((zoom: number, centerX?: number, centerY?: number, duration = 300) => {
    const startZoom = viewport.zoom;
    const deltaZoom = zoom - startZoom;
    const startTime = performance.now();

    const animate = () => {
      const elapsed = performance.now() - startTime;
      const progress = Math.min(elapsed / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);

      setViewport({
        zoom: startZoom + deltaZoom * eased
      });

      if (progress < 1) {
        requestAnimationFrame(animate);
      }
    };

    animate();
  }, [viewport, setViewport]);

  const fitToNodes = useCallback((nodeIds?: string[], padding = 50) => {
    const targetNodes = nodeIds 
      ? nodes.filter(n => nodeIds.includes(n.id))
      : nodes;

    if (targetNodes.length === 0) return;

    let minX = Infinity, minY = Infinity;
    let maxX = -Infinity, maxY = -Infinity;

    targetNodes.forEach(node => {
      const pos = nodePositionsRef.current.get(node.id);
      if (pos) {
        minX = Math.min(minX, pos.x);
        minY = Math.min(minY, pos.y);
        maxX = Math.max(maxX, pos.x);
        maxY = Math.max(maxY, pos.y);
      }
    });

    const width = maxX - minX;
    const height = maxY - minY;
    const centerX = (minX + maxX) / 2;
    const centerY = (minY + maxY) / 2;

    const canvas = canvasRef.current;
    if (!canvas) return;

    const scaleX = (canvas.width - padding * 2) / width;
    const scaleY = (canvas.height - padding * 2) / height;
    const scale = Math.min(scaleX, scaleY, 2); // Max zoom 2x

    setViewport({
      x: centerX - canvas.width / (2 * scale),
      y: centerY - canvas.height / (2 * scale),
      zoom: scale
    });
  }, [nodes, canvasRef, setViewport]);

  const resetViewport = useCallback(() => {
    fitToNodes();
  }, [fitToNodes]);

  // Selection actions
  const selectNode = useCallback((nodeId: string, multi = false) => {
    setSelectedNodes(prev => {
      const newSet = multi ? new Set(prev) : new Set<string>();
      newSet.add(nodeId);
      return newSet;
    });
  }, []);

  const deselectNode = useCallback((nodeId: string) => {
    setSelectedNodes(prev => {
      const newSet = new Set(prev);
      newSet.delete(nodeId);
      return newSet;
    });
  }, []);

  const clearSelection = useCallback(() => {
    setSelectedNodes(new Set());
  }, []);

  const highlightNodes = useCallback((nodeIds: string[]) => {
    setHighlightedNodes(new Set(nodeIds));
  }, []);

  const clearHighlights = useCallback(() => {
    setHighlightedNodes(new Set());
  }, []);

  // Rendering control
  const forceRender = useCallback(() => {
    render();
  }, [render]);

  const pauseRendering = useCallback(() => {
    setIsRendering(false);
  }, []);

  const resumeRendering = useCallback(() => {
    setIsRendering(true);
  }, []);

  // Export functions
  const exportImage = useCallback(async (format: 'png' | 'jpeg' | 'svg' = 'png'): Promise<Blob> => {
    const canvas = canvasRef.current;
    if (!canvas) throw new Error('Canvas not available');

    return new Promise((resolve, reject) => {
      canvas.toBlob((blob) => {
        if (blob) {
          resolve(blob);
        } else {
          reject(new Error('Failed to export image'));
        }
      }, `image/${format}`);
    });
  }, [canvasRef]);

  const exportData = useCallback(() => {
    return { nodes: visibleNodes, links: visibleLinks };
  }, [visibleNodes, visibleLinks]);

  // Create state object
  const state: GraphRendererState = {
    isRendering,
    viewport,
    renderStats,
    hoveredNode,
    selectedNodes,
    highlightedNodes,
    visibleBounds
  };

  // Create actions object
  const actions: GraphRendererActions = {
    setViewport,
    panTo,
    zoomTo,
    fitToNodes,
    resetViewport,
    selectNode,
    deselectNode,
    clearSelection,
    highlightNodes,
    clearHighlights,
    forceRender,
    pauseRendering,
    resumeRendering,
    exportImage,
    exportData
  };

  return [state, actions];
}

// Simple spatial index for efficient culling
class SpatialIndex {
  private cells: Map<string, Set<string>> = new Map();
  private cellSize: number;

  constructor(cellSize = 100) {
    this.cellSize = cellSize;
  }

  clear() {
    this.cells.clear();
  }

  add(id: string, x: number, y: number) {
    const cellX = Math.floor(x / this.cellSize);
    const cellY = Math.floor(y / this.cellSize);
    const key = `${cellX},${cellY}`;
    
    if (!this.cells.has(key)) {
      this.cells.set(key, new Set());
    }
    this.cells.get(key)!.add(id);
  }

  getInRegion(minX: number, minY: number, maxX: number, maxY: number): Set<string> {
    const result = new Set<string>();
    
    const minCellX = Math.floor(minX / this.cellSize);
    const minCellY = Math.floor(minY / this.cellSize);
    const maxCellX = Math.floor(maxX / this.cellSize);
    const maxCellY = Math.floor(maxY / this.cellSize);
    
    for (let x = minCellX; x <= maxCellX; x++) {
      for (let y = minCellY; y <= maxCellY; y++) {
        const key = `${x},${y}`;
        const cell = this.cells.get(key);
        if (cell) {
          cell.forEach(id => result.add(id));
        }
      }
    }
    
    return result;
  }
}