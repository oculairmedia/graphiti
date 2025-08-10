import React, { forwardRef, useImperativeHandle, useRef, useEffect, useCallback } from 'react';
import { GraphNode } from '../../api/types';
import { GraphLink } from '../../hooks/graph/useGraphData';

export interface GraphViewportProps {
  nodes: GraphNode[];
  links: GraphLink[];
  width?: number;
  height?: number;
  className?: string;
  
  // Visual config
  backgroundColor?: string;
  nodeColor?: string | ((node: GraphNode) => string);
  linkColor?: string | ((link: GraphLink) => string);
  nodeSize?: number;
  linkWidth?: number;
  
  // Selection state
  selectedNodes?: Set<string>;
  highlightedNodes?: Set<string>;
  hoveredNode?: GraphNode | null;
  
  // Event handlers
  onNodeClick?: (node: GraphNode, event: React.MouseEvent) => void;
  onNodeDoubleClick?: (node: GraphNode, event: React.MouseEvent) => void;
  onNodeHover?: (node: GraphNode | null) => void;
  onBackgroundClick?: (event: React.MouseEvent) => void;
  onViewportChange?: (viewport: ViewportInfo) => void;
  
  // Render options
  enablePanning?: boolean;
  enableZooming?: boolean;
  showLabels?: boolean;
  labelVisibilityZoom?: number;
}

export interface ViewportInfo {
  x: number;
  y: number;
  zoom: number;
  width: number;
  height: number;
}

export interface GraphViewportHandle {
  // Canvas access
  getCanvas: () => HTMLCanvasElement | null;
  getContext: () => CanvasRenderingContext2D | null;
  
  // Viewport control
  panTo: (x: number, y: number, duration?: number) => void;
  zoomTo: (level: number, centerX?: number, centerY?: number, duration?: number) => void;
  fitToNodes: (nodeIds?: string[], padding?: number) => void;
  resetViewport: () => void;
  getViewport: () => ViewportInfo;
  
  // Rendering control
  render: () => void;
  pauseRendering: () => void;
  resumeRendering: () => void;
  
  // Export
  exportImage: (format?: 'png' | 'jpeg') => Promise<Blob>;
  getVisibleNodes: () => GraphNode[];
  getVisibleLinks: () => GraphLink[];
}

/**
 * Pure UI component for rendering the graph canvas
 * This component only handles rendering and basic interactions
 * All business logic should be handled by the parent component
 */
export const GraphCanvasRenderer = forwardRef<GraphViewportHandle, GraphViewportProps>((props, ref) => {
  const {
    nodes = [],
    links = [],
    width = 800,
    height = 600,
    className = '',
    backgroundColor = '#000000',
    nodeSize = 5,
    linkWidth = 1,
    selectedNodes = new Set(),
    highlightedNodes = new Set(),
    hoveredNode = null,
    enablePanning = true,
    enableZooming = true,
    showLabels = true,
    labelVisibilityZoom = 0.5,
    onNodeClick,
    onNodeDoubleClick,
    onNodeHover,
    onBackgroundClick,
    onViewportChange,
  } = props;

  // Refs
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animationFrameRef = useRef<number | null>(null);
  const isRenderingRef = useRef(true);
  
  // Viewport state
  const viewportRef = useRef<ViewportInfo>({
    x: 0,
    y: 0,
    zoom: 1,
    width,
    height
  });

  // Node positions (would normally come from layout algorithm)
  const nodePositionsRef = useRef<Map<string, { x: number; y: number }>>(new Map());

  // Mouse interaction state
  const isDraggingRef = useRef(false);
  const dragStartRef = useRef({ x: 0, y: 0 });
  const lastMousePosRef = useRef({ x: 0, y: 0 });

  // Initialize node positions (simple layout for demo)
  useEffect(() => {
    const positions = new Map<string, { x: number; y: number }>();
    nodes.forEach((node, index) => {
      // Use existing position if available, otherwise calculate
      const angle = (index / nodes.length) * Math.PI * 2;
      const radius = Math.min(width, height) / 3;
      positions.set(node.id, {
        x: width / 2 + Math.cos(angle) * radius,
        y: height / 2 + Math.sin(angle) * radius
      });
    });
    nodePositionsRef.current = positions;
  }, [nodes, width, height]);

  // Render function
  const render = useCallback(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext('2d');
    if (!canvas || !ctx || !isRenderingRef.current) return;

    const viewport = viewportRef.current;

    // Clear canvas
    ctx.fillStyle = backgroundColor;
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    // Save context state
    ctx.save();

    // Apply viewport transform
    ctx.translate(-viewport.x, -viewport.y);
    ctx.scale(viewport.zoom, viewport.zoom);

    // Render links
    ctx.strokeStyle = typeof props.linkColor === 'string' ? props.linkColor : '#666666';
    ctx.lineWidth = linkWidth / viewport.zoom;
    ctx.globalAlpha = 0.3;

    links.forEach(link => {
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
    ctx.globalAlpha = 0.9;
    
    nodes.forEach(node => {
      const pos = nodePositionsRef.current.get(node.id);
      if (!pos) return;

      // Determine node appearance
      const isSelected = selectedNodes.has(node.id);
      const isHighlighted = highlightedNodes.has(node.id);
      const isHovered = hoveredNode?.id === node.id;

      // Set node size based on state
      let radius = nodeSize / viewport.zoom;
      if (isHovered) radius *= 1.5;
      else if (isSelected) radius *= 1.3;
      else if (isHighlighted) radius *= 1.2;

      // Set node color
      if (typeof props.nodeColor === 'function') {
        ctx.fillStyle = props.nodeColor(node);
      } else if (isSelected) {
        ctx.fillStyle = '#FFD700';
      } else if (isHighlighted) {
        ctx.fillStyle = '#FF6B6B';
      } else if (isHovered) {
        ctx.fillStyle = '#4FC3F7';
      } else {
        ctx.fillStyle = props.nodeColor || '#4A90E2';
      }

      // Draw node
      ctx.beginPath();
      ctx.arc(pos.x, pos.y, radius, 0, Math.PI * 2);
      ctx.fill();

      // Draw node border if selected or hovered
      if (isSelected || isHovered) {
        ctx.strokeStyle = isSelected ? '#FFD700' : '#FFFFFF';
        ctx.lineWidth = 2 / viewport.zoom;
        ctx.stroke();
      }

      // Draw label if conditions are met
      if (showLabels && viewport.zoom > labelVisibilityZoom && (isHovered || isSelected)) {
        ctx.fillStyle = '#FFFFFF';
        ctx.font = `${12 / viewport.zoom}px Arial`;
        ctx.globalAlpha = 0.8;
        ctx.fillText(
          node.name || node.label || node.id,
          pos.x + radius + 5 / viewport.zoom,
          pos.y
        );
        ctx.globalAlpha = 0.9;
      }
    });

    // Restore context state
    ctx.restore();

    // Continue render loop
    if (isRenderingRef.current) {
      animationFrameRef.current = requestAnimationFrame(render);
    }
  }, [
    nodes,
    links,
    backgroundColor,
    nodeSize,
    linkWidth,
    selectedNodes,
    highlightedNodes,
    hoveredNode,
    showLabels,
    labelVisibilityZoom,
    props.nodeColor,
    props.linkColor
  ]);

  // Start render loop
  useEffect(() => {
    if (isRenderingRef.current) {
      render();
    }
    
    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
    };
  }, [render]);

  // Handle mouse down
  const handleMouseDown = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;

    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;
    
    // Transform to world coordinates
    const viewport = viewportRef.current;
    const worldX = (mouseX + viewport.x) / viewport.zoom;
    const worldY = (mouseY + viewport.y) / viewport.zoom;

    // Check if clicking on a node
    let clickedNode: GraphNode | null = null;
    for (const node of nodes) {
      const pos = nodePositionsRef.current.get(node.id);
      if (!pos) continue;

      const distance = Math.sqrt(
        Math.pow(worldX - pos.x, 2) + Math.pow(worldY - pos.y, 2)
      );

      if (distance < nodeSize) {
        clickedNode = node;
        break;
      }
    }

    if (clickedNode) {
      onNodeClick?.(clickedNode, e);
    } else {
      onBackgroundClick?.(e);
      
      // Start panning if enabled
      if (enablePanning) {
        isDraggingRef.current = true;
        dragStartRef.current = { x: mouseX, y: mouseY };
        lastMousePosRef.current = { x: mouseX, y: mouseY };
      }
    }
  }, [nodes, nodeSize, enablePanning, onNodeClick, onBackgroundClick]);

  // Handle mouse move
  const handleMouseMove = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;

    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    // Handle panning
    if (isDraggingRef.current && enablePanning) {
      const viewport = viewportRef.current;
      const deltaX = (lastMousePosRef.current.x - mouseX) / viewport.zoom;
      const deltaY = (lastMousePosRef.current.y - mouseY) / viewport.zoom;
      
      viewport.x += deltaX;
      viewport.y += deltaY;
      
      lastMousePosRef.current = { x: mouseX, y: mouseY };
      onViewportChange?.(viewport);
      return;
    }

    // Check for hover
    const viewport = viewportRef.current;
    const worldX = (mouseX + viewport.x) / viewport.zoom;
    const worldY = (mouseY + viewport.y) / viewport.zoom;

    let hoveredNode: GraphNode | null = null;
    for (const node of nodes) {
      const pos = nodePositionsRef.current.get(node.id);
      if (!pos) continue;

      const distance = Math.sqrt(
        Math.pow(worldX - pos.x, 2) + Math.pow(worldY - pos.y, 2)
      );

      if (distance < nodeSize * 1.5) {
        hoveredNode = node;
        break;
      }
    }

    onNodeHover?.(hoveredNode);
  }, [nodes, nodeSize, enablePanning, onNodeHover, onViewportChange]);

  // Handle mouse up
  const handleMouseUp = useCallback(() => {
    isDraggingRef.current = false;
  }, []);

  // Handle wheel (zoom)
  const handleWheel = useCallback((e: React.WheelEvent<HTMLCanvasElement>) => {
    if (!enableZooming) return;
    
    e.preventDefault();
    
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;

    const viewport = viewportRef.current;
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;
    
    // Calculate zoom
    const zoomDelta = e.deltaY > 0 ? 0.9 : 1.1;
    const newZoom = Math.max(0.1, Math.min(10, viewport.zoom * zoomDelta));
    
    // Adjust viewport to zoom towards mouse position
    const worldX = (mouseX + viewport.x) / viewport.zoom;
    const worldY = (mouseY + viewport.y) / viewport.zoom;
    
    viewport.zoom = newZoom;
    viewport.x = worldX * newZoom - mouseX;
    viewport.y = worldY * newZoom - mouseY;
    
    onViewportChange?.(viewport);
  }, [enableZooming, onViewportChange]);

  // Handle double click
  const handleDoubleClick = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;

    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;
    
    const viewport = viewportRef.current;
    const worldX = (mouseX + viewport.x) / viewport.zoom;
    const worldY = (mouseY + viewport.y) / viewport.zoom;

    for (const node of nodes) {
      const pos = nodePositionsRef.current.get(node.id);
      if (!pos) continue;

      const distance = Math.sqrt(
        Math.pow(worldX - pos.x, 2) + Math.pow(worldY - pos.y, 2)
      );

      if (distance < nodeSize) {
        onNodeDoubleClick?.(node, e);
        break;
      }
    }
  }, [nodes, nodeSize, onNodeDoubleClick]);

  // Imperative handle
  useImperativeHandle(ref, () => ({
    getCanvas: () => canvasRef.current,
    getContext: () => canvasRef.current?.getContext('2d') || null,
    
    panTo: (x: number, y: number, duration = 300) => {
      // Implement smooth panning
      const viewport = viewportRef.current;
      const startX = viewport.x;
      const startY = viewport.y;
      const deltaX = x - startX;
      const deltaY = y - startY;
      const startTime = performance.now();

      const animate = () => {
        const elapsed = performance.now() - startTime;
        const progress = Math.min(elapsed / duration, 1);
        const eased = 1 - Math.pow(1 - progress, 3);

        viewport.x = startX + deltaX * eased;
        viewport.y = startY + deltaY * eased;
        
        if (progress < 1) {
          requestAnimationFrame(animate);
        }
        onViewportChange?.(viewport);
      };

      animate();
    },

    zoomTo: (level: number, centerX?: number, centerY?: number, duration = 300) => {
      const viewport = viewportRef.current;
      const startZoom = viewport.zoom;
      const deltaZoom = level - startZoom;
      const startTime = performance.now();

      const animate = () => {
        const elapsed = performance.now() - startTime;
        const progress = Math.min(elapsed / duration, 1);
        const eased = 1 - Math.pow(1 - progress, 3);

        viewport.zoom = startZoom + deltaZoom * eased;
        
        if (progress < 1) {
          requestAnimationFrame(animate);
        }
        onViewportChange?.(viewport);
      };

      animate();
    },

    fitToNodes: (nodeIds?: string[], padding = 50) => {
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

      const boundsWidth = maxX - minX;
      const boundsHeight = maxY - minY;
      const centerX = (minX + maxX) / 2;
      const centerY = (minY + maxY) / 2;

      const canvas = canvasRef.current;
      if (!canvas) return;

      const scaleX = (canvas.width - padding * 2) / boundsWidth;
      const scaleY = (canvas.height - padding * 2) / boundsHeight;
      const scale = Math.min(scaleX, scaleY, 2);

      const viewport = viewportRef.current;
      viewport.zoom = scale;
      viewport.x = centerX * scale - canvas.width / 2;
      viewport.y = centerY * scale - canvas.height / 2;
      
      onViewportChange?.(viewport);
    },

    resetViewport: () => {
      const viewport = viewportRef.current;
      viewport.x = 0;
      viewport.y = 0;
      viewport.zoom = 1;
      onViewportChange?.(viewport);
    },

    getViewport: () => ({ ...viewportRef.current }),

    render: () => render(),
    
    pauseRendering: () => {
      isRenderingRef.current = false;
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
    },
    
    resumeRendering: () => {
      isRenderingRef.current = true;
      render();
    },

    exportImage: async (format: 'png' | 'jpeg' = 'png'): Promise<Blob> => {
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
    },

    getVisibleNodes: () => {
      const viewport = viewportRef.current;
      const padding = 100;
      
      return nodes.filter(node => {
        const pos = nodePositionsRef.current.get(node.id);
        if (!pos) return false;
        
        return pos.x >= (viewport.x - padding) / viewport.zoom &&
               pos.x <= (viewport.x + viewport.width + padding) / viewport.zoom &&
               pos.y >= (viewport.y - padding) / viewport.zoom &&
               pos.y <= (viewport.y + viewport.height + padding) / viewport.zoom;
      });
    },

    getVisibleLinks: () => {
      const visibleNodeIds = new Set(
        nodes
          .filter(node => {
            const pos = nodePositionsRef.current.get(node.id);
            if (!pos) return false;
            
            const viewport = viewportRef.current;
            const padding = 100;
            
            return pos.x >= (viewport.x - padding) / viewport.zoom &&
                   pos.x <= (viewport.x + viewport.width + padding) / viewport.zoom &&
                   pos.y >= (viewport.y - padding) / viewport.zoom &&
                   pos.y <= (viewport.y + viewport.height + padding) / viewport.zoom;
          })
          .map(n => n.id)
      );
      
      return links.filter(link => 
        visibleNodeIds.has(link.source) || visibleNodeIds.has(link.target)
      );
    }
  }), [nodes, links, render, onViewportChange]);

  return (
    <canvas
      ref={canvasRef}
      width={width}
      height={height}
      className={className}
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseUp}
      onWheel={handleWheel}
      onDoubleClick={handleDoubleClick}
      style={{
        cursor: isDraggingRef.current ? 'grabbing' : hoveredNode ? 'pointer' : 'grab',
        touchAction: 'none'
      }}
    />
  );
});

GraphCanvasRenderer.displayName = 'GraphCanvasRenderer';