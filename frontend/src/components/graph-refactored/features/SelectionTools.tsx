import React, { useState, useCallback, useRef, useEffect, useMemo } from 'react';
import { GraphNode } from '../../../api/types';

type SelectionMode = 'single' | 'rect' | 'lasso' | 'polygon' | 'radial' | 'path';
type SelectionAction = 'add' | 'remove' | 'toggle' | 'replace';

interface SelectionConfig {
  mode: SelectionMode;
  action: SelectionAction;
  multiSelect: boolean;
  selectConnected: boolean;
  selectDepth?: number;
  highlightSelection?: boolean;
  persistSelection?: boolean;
}

interface SelectionToolsProps {
  nodes: GraphNode[];
  viewportRef?: React.RefObject<HTMLElement>;
  config?: Partial<SelectionConfig>;
  onSelectionChange?: (selectedNodes: GraphNode[], selectionBounds?: SelectionBounds) => void;
  onSelectionComplete?: (selectedNodes: GraphNode[]) => void;
  children?: React.ReactNode;
}

interface SelectionBounds {
  type: 'rect' | 'polygon' | 'circle';
  bounds: { x: number; y: number; width?: number; height?: number; radius?: number };
  points?: Array<{ x: number; y: number }>;
}

interface SelectionState {
  selectedNodes: Set<string>;
  isSelecting: boolean;
  selectionStart: { x: number; y: number } | null;
  selectionEnd: { x: number; y: number } | null;
  selectionPoints: Array<{ x: number; y: number }>;
  selectionBounds: SelectionBounds | null;
  hoveredNode: string | null;
}

/**
 * SelectionTools - Advanced selection system for graph nodes
 * Supports rectangular, lasso, polygonal, and radial selection
 */
export const SelectionTools: React.FC<SelectionToolsProps> = React.memo(({
  nodes,
  viewportRef,
  config = {},
  onSelectionChange,
  onSelectionComplete,
  children
}) => {
  const [state, setState] = useState<SelectionState>({
    selectedNodes: new Set(),
    isSelecting: false,
    selectionStart: null,
    selectionEnd: null,
    selectionPoints: [],
    selectionBounds: null,
    hoveredNode: null
  });

  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const overlayRef = useRef<HTMLDivElement | null>(null);
  const animationFrameRef = useRef<number | null>(null);

  // Default configuration
  const fullConfig: SelectionConfig = {
    mode: config.mode || 'rect',
    action: config.action || 'replace',
    multiSelect: config.multiSelect ?? true,
    selectConnected: config.selectConnected ?? false,
    selectDepth: config.selectDepth ?? 1,
    highlightSelection: config.highlightSelection ?? true,
    persistSelection: config.persistSelection ?? false
  };

  // Start selection
  const startSelection = useCallback((event: MouseEvent | TouchEvent) => {
    const point = getEventPoint(event);
    
    setState(prev => ({
      ...prev,
      isSelecting: true,
      selectionStart: point,
      selectionEnd: point,
      selectionPoints: [point],
      selectionBounds: null
    }));

    if (fullConfig.mode === 'polygon' || fullConfig.mode === 'lasso') {
      // Start recording points for polygon/lasso
      setState(prev => ({
        ...prev,
        selectionPoints: [point]
      }));
    }
  }, [fullConfig.mode]);

  // Update selection
  const updateSelection = useCallback((event: MouseEvent | TouchEvent) => {
    if (!state.isSelecting || !state.selectionStart) return;

    const point = getEventPoint(event);
    
    setState(prev => ({
      ...prev,
      selectionEnd: point
    }));

    if (fullConfig.mode === 'lasso') {
      // Add point to lasso path
      setState(prev => ({
        ...prev,
        selectionPoints: [...prev.selectionPoints, point]
      }));
    }

    // Update selection bounds
    const bounds = calculateSelectionBounds(
      state.selectionStart,
      point,
      state.selectionPoints,
      fullConfig.mode
    );
    
    setState(prev => ({
      ...prev,
      selectionBounds: bounds
    }));

    // Select nodes within bounds
    const selected = selectNodesInBounds(nodes, bounds);
    updateSelectedNodes(selected);
  }, [state.isSelecting, state.selectionStart, state.selectionPoints, fullConfig.mode, nodes]);

  // End selection
  const endSelection = useCallback((event?: MouseEvent | TouchEvent) => {
    if (!state.isSelecting) return;

    if (fullConfig.mode === 'polygon' && event) {
      // Add final point for polygon
      const point = getEventPoint(event);
      setState(prev => ({
        ...prev,
        selectionPoints: [...prev.selectionPoints, point]
      }));
    }

    // Finalize selection
    const selected = Array.from(state.selectedNodes)
      .map(id => nodes.find(n => n.id === id))
      .filter(Boolean) as GraphNode[];

    onSelectionComplete?.(selected);

    // Clear selection visualization unless persistent
    if (!fullConfig.persistSelection) {
      setState(prev => ({
        ...prev,
        isSelecting: false,
        selectionStart: null,
        selectionEnd: null,
        selectionPoints: [],
        selectionBounds: null
      }));
    } else {
      setState(prev => ({
        ...prev,
        isSelecting: false
      }));
    }
  }, [state.isSelecting, state.selectedNodes, fullConfig.mode, fullConfig.persistSelection, nodes, onSelectionComplete]);

  // Get event point
  function getEventPoint(event: MouseEvent | TouchEvent): { x: number; y: number } {
    if ('touches' in event && event.touches.length > 0) {
      return { x: event.touches[0].clientX, y: event.touches[0].clientY };
    }
    return { x: (event as MouseEvent).clientX, y: (event as MouseEvent).clientY };
  }

  // Calculate selection bounds
  function calculateSelectionBounds(
    start: { x: number; y: number },
    end: { x: number; y: number },
    points: Array<{ x: number; y: number }>,
    mode: SelectionMode
  ): SelectionBounds {
    switch (mode) {
      case 'rect':
        return {
          type: 'rect',
          bounds: {
            x: Math.min(start.x, end.x),
            y: Math.min(start.y, end.y),
            width: Math.abs(end.x - start.x),
            height: Math.abs(end.y - start.y)
          }
        };
      
      case 'radial':
        const radius = Math.sqrt(
          Math.pow(end.x - start.x, 2) + Math.pow(end.y - start.y, 2)
        );
        return {
          type: 'circle',
          bounds: {
            x: start.x,
            y: start.y,
            radius
          }
        };
      
      case 'polygon':
      case 'lasso':
        return {
          type: 'polygon',
          bounds: {
            x: Math.min(...points.map(p => p.x)),
            y: Math.min(...points.map(p => p.y))
          },
          points
        };
      
      default:
        return {
          type: 'rect',
          bounds: { x: 0, y: 0, width: 0, height: 0 }
        };
    }
  }

  // Select nodes within bounds
  function selectNodesInBounds(nodes: GraphNode[], bounds: SelectionBounds): Set<string> {
    const selected = new Set<string>();
    
    nodes.forEach(node => {
      if (isNodeInBounds(node, bounds)) {
        selected.add(node.id);
      }
    });
    
    return selected;
  }

  // Check if node is within bounds
  function isNodeInBounds(node: GraphNode, bounds: SelectionBounds): boolean {
    const nodeX = node.x || 0;
    const nodeY = node.y || 0;
    
    switch (bounds.type) {
      case 'rect':
        return nodeX >= bounds.bounds.x &&
               nodeX <= bounds.bounds.x + (bounds.bounds.width || 0) &&
               nodeY >= bounds.bounds.y &&
               nodeY <= bounds.bounds.y + (bounds.bounds.height || 0);
      
      case 'circle':
        const dx = nodeX - bounds.bounds.x;
        const dy = nodeY - bounds.bounds.y;
        return Math.sqrt(dx * dx + dy * dy) <= (bounds.bounds.radius || 0);
      
      case 'polygon':
        return bounds.points ? isPointInPolygon({ x: nodeX, y: nodeY }, bounds.points) : false;
      
      default:
        return false;
    }
  }

  // Check if point is in polygon
  function isPointInPolygon(point: { x: number; y: number }, polygon: Array<{ x: number; y: number }>): boolean {
    let inside = false;
    
    for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
      const xi = polygon[i].x, yi = polygon[i].y;
      const xj = polygon[j].x, yj = polygon[j].y;
      
      const intersect = ((yi > point.y) !== (yj > point.y)) &&
        (point.x < (xj - xi) * (point.y - yi) / (yj - yi) + xi);
      
      if (intersect) inside = !inside;
    }
    
    return inside;
  }

  // Update selected nodes based on action
  const updateSelectedNodes = useCallback((newSelection: Set<string>) => {
    setState(prev => {
      let updated: Set<string>;
      
      switch (fullConfig.action) {
        case 'replace':
          updated = newSelection;
          break;
        
        case 'add':
          updated = new Set([...prev.selectedNodes, ...newSelection]);
          break;
        
        case 'remove':
          updated = new Set([...prev.selectedNodes].filter(id => !newSelection.has(id)));
          break;
        
        case 'toggle':
          updated = new Set(prev.selectedNodes);
          newSelection.forEach(id => {
            if (updated.has(id)) {
              updated.delete(id);
            } else {
              updated.add(id);
            }
          });
          break;
        
        default:
          updated = newSelection;
      }
      
      // Select connected nodes if enabled
      if (fullConfig.selectConnected) {
        updated = expandSelection(updated, fullConfig.selectDepth || 1);
      }
      
      // Notify parent
      const selectedNodes = Array.from(updated)
        .map(id => nodes.find(n => n.id === id))
        .filter(Boolean) as GraphNode[];
      
      onSelectionChange?.(selectedNodes, prev.selectionBounds || undefined);
      
      return { ...prev, selectedNodes: updated };
    });
  }, [fullConfig.action, fullConfig.selectConnected, fullConfig.selectDepth, nodes, onSelectionChange]);

  // Expand selection to connected nodes
  function expandSelection(selected: Set<string>, depth: number): Set<string> {
    // This would need edge information to properly expand
    // For now, returning as-is
    return selected;
  }

  // Select single node
  const selectNode = useCallback((nodeId: string) => {
    const newSelection = new Set<string>([nodeId]);
    updateSelectedNodes(newSelection);
  }, [updateSelectedNodes]);

  // Clear selection
  const clearSelection = useCallback(() => {
    setState(prev => ({
      ...prev,
      selectedNodes: new Set(),
      selectionBounds: null
    }));
    onSelectionChange?.([], undefined);
  }, [onSelectionChange]);

  // Select all nodes
  const selectAll = useCallback(() => {
    const allNodeIds = new Set(nodes.map(n => n.id));
    updateSelectedNodes(allNodeIds);
  }, [nodes, updateSelectedNodes]);

  // Invert selection
  const invertSelection = useCallback(() => {
    const inverted = new Set(
      nodes.filter(n => !state.selectedNodes.has(n.id)).map(n => n.id)
    );
    updateSelectedNodes(inverted);
  }, [nodes, state.selectedNodes, updateSelectedNodes]);

  // Draw selection visualization
  const drawSelection = useCallback(() => {
    if (!canvasRef.current || !state.isSelecting) return;
    
    const ctx = canvasRef.current.getContext('2d');
    if (!ctx) return;
    
    // Clear canvas
    ctx.clearRect(0, 0, canvasRef.current.width, canvasRef.current.height);
    
    // Set style
    ctx.strokeStyle = '#4F46E5';
    ctx.fillStyle = 'rgba(79, 70, 229, 0.1)';
    ctx.lineWidth = 2;
    ctx.setLineDash([5, 5]);
    
    if (!state.selectionStart) return;
    
    switch (fullConfig.mode) {
      case 'rect':
        if (state.selectionEnd) {
          const x = Math.min(state.selectionStart.x, state.selectionEnd.x);
          const y = Math.min(state.selectionStart.y, state.selectionEnd.y);
          const width = Math.abs(state.selectionEnd.x - state.selectionStart.x);
          const height = Math.abs(state.selectionEnd.y - state.selectionStart.y);
          
          ctx.fillRect(x, y, width, height);
          ctx.strokeRect(x, y, width, height);
        }
        break;
      
      case 'radial':
        if (state.selectionEnd) {
          const radius = Math.sqrt(
            Math.pow(state.selectionEnd.x - state.selectionStart.x, 2) +
            Math.pow(state.selectionEnd.y - state.selectionStart.y, 2)
          );
          
          ctx.beginPath();
          ctx.arc(state.selectionStart.x, state.selectionStart.y, radius, 0, 2 * Math.PI);
          ctx.fill();
          ctx.stroke();
        }
        break;
      
      case 'lasso':
      case 'polygon':
        if (state.selectionPoints.length > 1) {
          ctx.beginPath();
          ctx.moveTo(state.selectionPoints[0].x, state.selectionPoints[0].y);
          
          state.selectionPoints.forEach((point, i) => {
            if (i > 0) ctx.lineTo(point.x, point.y);
          });
          
          if (fullConfig.mode === 'polygon' && !state.isSelecting) {
            ctx.closePath();
          }
          
          ctx.fill();
          ctx.stroke();
        }
        break;
    }
  }, [state, fullConfig.mode]);

  // Animation loop for selection visualization
  useEffect(() => {
    if (state.isSelecting) {
      const animate = () => {
        drawSelection();
        animationFrameRef.current = requestAnimationFrame(animate);
      };
      animate();
    } else {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
        animationFrameRef.current = null;
      }
    }
    
    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
    };
  }, [state.isSelecting, drawSelection]);

  // Context value
  const contextValue = useMemo(() => ({
    ...state,
    config: fullConfig,
    startSelection,
    updateSelection,
    endSelection,
    selectNode,
    clearSelection,
    selectAll,
    invertSelection,
    isNodeSelected: (nodeId: string) => state.selectedNodes.has(nodeId),
    getSelectedNodes: () => Array.from(state.selectedNodes)
      .map(id => nodes.find(n => n.id === id))
      .filter(Boolean) as GraphNode[]
  }), [state, fullConfig, startSelection, updateSelection, endSelection, selectNode, clearSelection, selectAll, invertSelection, nodes]);

  return (
    <SelectionContext.Provider value={contextValue}>
      {children}
    </SelectionContext.Provider>
  );
}, (prevProps, nextProps) => {
  // Custom comparison to prevent unnecessary re-renders
  return (
    prevProps.nodes === nextProps.nodes &&
    prevProps.viewportRef === nextProps.viewportRef &&
    prevProps.config === nextProps.config &&
    prevProps.children === nextProps.children &&
    prevProps.onSelectionChange === nextProps.onSelectionChange &&
    prevProps.onSelectionComplete === nextProps.onSelectionComplete
  );
});

// Context
const SelectionContext = React.createContext<any>({});

export const useSelection = () => React.useContext(SelectionContext);