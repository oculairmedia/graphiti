/**
 * Unit tests for useGraphInteractions hook
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useGraphInteractions, useSimpleInteractions } from '../../hooks/useGraphInteractions';
import { GraphNode } from '../../api/types';
import { GraphLink } from '../../types/graph';

describe('useGraphInteractions', () => {
  const mockNodes: GraphNode[] = [
    { id: 'node1', name: 'Node 1', node_type: 'person' },
    { id: 'node2', name: 'Node 2', node_type: 'organization' },
  ];

  const mockLinks: GraphLink[] = [
    { source: 'node1', target: 'node2', edge_type: 'knows' },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  describe('Node interactions', () => {
    it('should handle node click', () => {
      const onNodeClick = vi.fn();
      const { result } = renderHook(() => 
        useGraphInteractions(mockNodes, mockLinks, { 
          onNodeClick,
          enableDoubleClick: false // Disable to avoid delay
        })
      );

      act(() => {
        result.current.handleNodeClick('node1', { x: 10, y: 20 });
      });

      expect(onNodeClick).toHaveBeenCalledWith(
        'node1',
        expect.objectContaining({
          type: 'click',
          target: 'node',
          targetId: 'node1'
        })
      );
    });

    it('should handle node double-click', () => {
      const onNodeDoubleClick = vi.fn();
      const { result } = renderHook(() => 
        useGraphInteractions(mockNodes, mockLinks, { 
          onNodeDoubleClick,
          doubleClickDelay: 300
        })
      );

      act(() => {
        result.current.handleNodeClick('node1', { x: 10, y: 20 });
        result.current.handleNodeClick('node1', { x: 10, y: 20 });
      });

      expect(onNodeDoubleClick).toHaveBeenCalledWith(
        'node1',
        expect.objectContaining({
          type: 'double-click',
          target: 'node',
          targetId: 'node1'
        })
      );
    });

    it('should handle node right-click', () => {
      const onNodeRightClick = vi.fn();
      const preventDefault = vi.fn();
      const { result } = renderHook(() => 
        useGraphInteractions(mockNodes, mockLinks, { onNodeRightClick })
      );

      act(() => {
        result.current.handleNodeRightClick('node1', { x: 10, y: 20 }, { preventDefault } as any);
      });

      expect(onNodeRightClick).toHaveBeenCalled();
      expect(preventDefault).toHaveBeenCalled();
      expect(result.current.contextMenu.isOpen).toBe(true);
      expect(result.current.contextMenu.target?.id).toBe('node1');
    });

    it('should handle node hover', () => {
      const onNodeHover = vi.fn();
      const { result } = renderHook(() => 
        useGraphInteractions(mockNodes, mockLinks, { 
          onNodeHover,
          hoverDelay: 100
        })
      );

      act(() => {
        result.current.handleNodeHover('node1');
      });

      // Should not trigger immediately
      expect(result.current.hoveredNode).toBe(null);

      act(() => {
        vi.advanceTimersByTime(100);
      });

      expect(result.current.hoveredNode).toBe('node1');
      expect(onNodeHover).toHaveBeenCalledWith('node1');
    });
  });

  describe('Drag operations', () => {
    it('should start node drag', () => {
      const onNodeDragStart = vi.fn();
      const { result } = renderHook(() => 
        useGraphInteractions(mockNodes, mockLinks, { onNodeDragStart })
      );

      act(() => {
        result.current.startNodeDrag('node1', { x: 10, y: 20 });
      });

      expect(result.current.dragState.isDragging).toBe(true);
      expect(result.current.dragState.draggedNode).toBe('node1');
      expect(onNodeDragStart).toHaveBeenCalledWith('node1', { x: 10, y: 20 });
    });

    it('should update node drag', () => {
      const onNodeDrag = vi.fn();
      const { result } = renderHook(() => 
        useGraphInteractions(mockNodes, mockLinks, { 
          onNodeDrag,
          dragThreshold: 0 // Disable threshold for testing
        })
      );

      act(() => {
        result.current.startNodeDrag('node1', { x: 10, y: 20 });
        result.current.updateNodeDrag({ x: 20, y: 30 });
      });

      // Check that drag state is updated
      expect(result.current.dragState.dragCurrentPosition).toEqual({ x: 20, y: 30 });
      expect(result.current.dragState.dragDelta).toEqual({ x: 10, y: 10 });
      
      // Check callback was called
      expect(onNodeDrag).toHaveBeenCalled();
    });

    it('should end node drag', () => {
      const onNodeDragEnd = vi.fn();
      const { result } = renderHook(() => 
        useGraphInteractions(mockNodes, mockLinks, { 
          onNodeDragEnd,
          dragThreshold: 0
        })
      );

      act(() => {
        result.current.startNodeDrag('node1', { x: 10, y: 20 });
      });
      
      // Update drag position first
      act(() => {
        result.current.updateNodeDrag({ x: 30, y: 40 });
      });
      
      act(() => {
        result.current.endNodeDrag();
      });

      expect(result.current.dragState.isDragging).toBe(false);
      expect(result.current.dragState.draggedNode).toBe(null);
      expect(onNodeDragEnd).toHaveBeenCalledWith('node1', { x: 30, y: 40 });
    });

    it('should snap to grid when enabled', () => {
      const onNodeDrag = vi.fn();
      const { result } = renderHook(() => 
        useGraphInteractions(mockNodes, mockLinks, { 
          onNodeDrag,
          snapToGrid: true,
          gridSize: 10,
          dragThreshold: 0
        })
      );

      act(() => {
        result.current.startNodeDrag('node1', { x: 0, y: 0 });
      });
      
      act(() => {
        result.current.updateNodeDrag({ x: 17, y: 23 });
      });

      // Should snap to nearest grid point (20, 20)
      expect(result.current.dragState.dragCurrentPosition).toEqual({ x: 20, y: 20 });
    });
  });

  describe('Link interactions', () => {
    it('should handle link click', () => {
      const onLinkClick = vi.fn();
      const { result } = renderHook(() => 
        useGraphInteractions(mockNodes, mockLinks, { onLinkClick })
      );

      act(() => {
        result.current.handleLinkClick('link1', { x: 10, y: 20 });
      });

      expect(onLinkClick).toHaveBeenCalledWith(
        'link1',
        expect.objectContaining({
          type: 'click',
          target: 'link',
          targetId: 'link1'
        })
      );
    });

    it('should handle link hover', () => {
      const onLinkHover = vi.fn();
      const { result } = renderHook(() => 
        useGraphInteractions(mockNodes, mockLinks, { onLinkHover })
      );

      act(() => {
        result.current.handleLinkHover('link1');
      });

      expect(result.current.hoveredLink).toBe('link1');
      expect(onLinkHover).toHaveBeenCalledWith('link1');
    });
  });

  describe('Canvas interactions', () => {
    it('should handle canvas click', () => {
      const onCanvasClick = vi.fn();
      const { result } = renderHook(() => 
        useGraphInteractions(mockNodes, mockLinks, { onCanvasClick })
      );

      // Open context menu first
      act(() => {
        result.current.openContextMenu({ x: 10, y: 20 }, { type: 'node', id: 'node1' });
      });

      expect(result.current.contextMenu.isOpen).toBe(true);

      // Canvas click should close context menu
      act(() => {
        result.current.handleCanvasClick({ x: 50, y: 50 });
      });

      expect(result.current.contextMenu.isOpen).toBe(false);
      expect(onCanvasClick).toHaveBeenCalled();
    });
  });

  describe('Gestures', () => {
    it('should handle pinch gesture', () => {
      const onPinch = vi.fn();
      const { result } = renderHook(() => 
        useGraphInteractions(mockNodes, mockLinks, { 
          onPinch,
          pinchSensitivity: 1.5
        })
      );

      act(() => {
        result.current.handlePinch(2, { x: 50, y: 50 });
      });

      expect(result.current.gestureState.isPinching).toBe(true);
      expect(result.current.gestureState.pinchScale).toBe(3); // 2 * 1.5
      expect(onPinch).toHaveBeenCalledWith(3, { x: 50, y: 50 });
    });

    it('should handle pan gesture', () => {
      const onPan = vi.fn();
      const { result } = renderHook(() => 
        useGraphInteractions(mockNodes, mockLinks, { 
          onPan,
          panSensitivity: 2
        })
      );

      act(() => {
        result.current.handlePan({ x: 10, y: 20 });
      });

      expect(result.current.gestureState.isPanning).toBe(true);
      expect(result.current.gestureState.panDelta).toEqual({ x: 20, y: 40 });
      expect(onPan).toHaveBeenCalledWith({ x: 20, y: 40 });
    });
  });

  describe('Context menu', () => {
    it('should open and close context menu', () => {
      const { result } = renderHook(() => 
        useGraphInteractions(mockNodes, mockLinks)
      );

      act(() => {
        result.current.openContextMenu(
          { x: 100, y: 100 },
          { type: 'node', id: 'node1' }
        );
      });

      expect(result.current.contextMenu.isOpen).toBe(true);
      expect(result.current.contextMenu.position).toEqual({ x: 100, y: 100 });
      expect(result.current.contextMenu.target).toEqual({ type: 'node', id: 'node1' });

      act(() => {
        result.current.closeContextMenu();
      });

      expect(result.current.contextMenu.isOpen).toBe(false);
    });
  });

  describe('Interaction state', () => {
    it('should track interaction mode', () => {
      const { result } = renderHook(() => 
        useGraphInteractions(mockNodes, mockLinks)
      );

      expect(result.current.getInteractionMode()).toBe('idle');
      expect(result.current.isInteracting).toBe(false);

      act(() => {
        result.current.startNodeDrag('node1', { x: 10, y: 20 });
      });

      expect(result.current.getInteractionMode()).toBe('drag');
      expect(result.current.isInteracting).toBe(true);
    });

    it('should track interaction history', () => {
      const { result } = renderHook(() => 
        useGraphInteractions(mockNodes, mockLinks, {
          enableDoubleClick: false
        })
      );

      act(() => {
        result.current.handleNodeClick('node1', { x: 10, y: 20 });
        result.current.handleLinkClick('link1', { x: 30, y: 40 });
      });

      const history = result.current.getInteractionHistory();
      expect(history).toHaveLength(2);
      expect(history[0].event.target).toBe('link');
      expect(history[1].event.target).toBe('node');
    });

    it('should clear interaction history', () => {
      const { result } = renderHook(() => 
        useGraphInteractions(mockNodes, mockLinks, {
          enableDoubleClick: false
        })
      );

      act(() => {
        result.current.handleNodeClick('node1', { x: 10, y: 20 });
        result.current.clearInteractionHistory();
      });

      expect(result.current.getInteractionHistory()).toHaveLength(0);
    });
  });

  describe('Cancel interactions', () => {
    it('should cancel all interactions', () => {
      const { result } = renderHook(() => 
        useGraphInteractions(mockNodes, mockLinks)
      );

      act(() => {
        result.current.startNodeDrag('node1', { x: 10, y: 20 });
        result.current.openContextMenu({ x: 50, y: 50 }, { type: 'canvas' });
        result.current.handleNodeHover('node2');
      });

      expect(result.current.isInteracting).toBe(true);

      act(() => {
        result.current.cancelAllInteractions();
      });

      expect(result.current.dragState.isDragging).toBe(false);
      expect(result.current.contextMenu.isOpen).toBe(false);
      expect(result.current.hoveredNode).toBe(null);
      expect(result.current.isInteracting).toBe(false);
    });
  });
});

describe('useSimpleInteractions', () => {
  it('should handle basic interactions', () => {
    const onNodeClick = vi.fn();
    const onNodeHover = vi.fn();
    const { result } = renderHook(() => 
      useSimpleInteractions(onNodeClick, onNodeHover)
    );

    act(() => {
      result.current.handleClick('node1');
    });

    expect(onNodeClick).toHaveBeenCalledWith('node1');

    act(() => {
      result.current.handleHover('node2');
    });

    expect(result.current.hoveredNode).toBe('node2');
    expect(onNodeHover).toHaveBeenCalledWith('node2');
  });
});