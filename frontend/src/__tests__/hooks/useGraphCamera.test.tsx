/**
 * Unit tests for useGraphCamera hook
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useGraphCamera, useSimpleCamera } from '../../hooks/useGraphCamera';
import { GraphNode } from '../../api/types';

describe('useGraphCamera', () => {
  const mockNodes: GraphNode[] = [
    { id: 'node1', name: 'Node 1', node_type: 'person', x: 0, y: 0 },
    { id: 'node2', name: 'Node 2', node_type: 'organization', x: 100, y: 100 },
    { id: 'node3', name: 'Node 3', node_type: 'location', x: -50, y: 50 },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  describe('Initialization', () => {
    it('should initialize with default values', () => {
      const { result } = renderHook(() => useGraphCamera([]));
      
      expect(result.current.zoom).toBe(1);
      expect(result.current.position).toEqual({ x: 0, y: 0 });
      expect(result.current.rotation).toBe(0);
    });

    it('should initialize with custom values', () => {
      const { result } = renderHook(() => 
        useGraphCamera([], {
          initialZoom: 2,
          initialPosition: { x: 10, y: 20 },
          initialRotation: 45
        })
      );
      
      expect(result.current.zoom).toBe(2);
      expect(result.current.position).toEqual({ x: 10, y: 20 });
      expect(result.current.rotation).toBe(45);
    });

    it('should load persisted state', () => {
      const savedState = {
        zoom: 1.5,
        position: { x: 5, y: 10 },
        rotation: 30
      };
      localStorage.setItem('graph-camera', JSON.stringify(savedState));
      
      const { result } = renderHook(() => 
        useGraphCamera([], { persistState: true })
      );
      
      expect(result.current.zoom).toBe(1.5);
      expect(result.current.position).toEqual({ x: 5, y: 10 });
    });
  });

  describe('Zoom controls', () => {
    it('should zoom in', () => {
      const { result } = renderHook(() => useGraphCamera([]));
      
      act(() => {
        result.current.zoomIn();
      });
      
      expect(result.current.zoom).toBeGreaterThan(1);
    });

    it('should zoom out', () => {
      const { result } = renderHook(() => useGraphCamera([]));
      
      act(() => {
        result.current.zoomOut();
      });
      
      expect(result.current.zoom).toBeLessThan(1);
    });

    it('should zoom to specific level', () => {
      const { result } = renderHook(() => useGraphCamera([]));
      
      act(() => {
        result.current.zoomTo(2.5, false);
      });
      
      expect(result.current.zoom).toBe(2.5);
    });

    it('should respect zoom limits', () => {
      const { result } = renderHook(() => 
        useGraphCamera([], { minZoom: 0.5, maxZoom: 2 })
      );
      
      act(() => {
        result.current.zoomTo(3, false);
      });
      
      expect(result.current.zoom).toBe(2); // Clamped to maxZoom
      
      act(() => {
        result.current.zoomTo(0.1, false);
      });
      
      expect(result.current.zoom).toBe(0.5); // Clamped to minZoom
    });

    it('should trigger zoom change callback', () => {
      const onZoomChange = vi.fn();
      const { result } = renderHook(() => 
        useGraphCamera([], { onZoomChange })
      );
      
      act(() => {
        result.current.zoomTo(2, false);
      });
      
      expect(onZoomChange).toHaveBeenCalledWith(2);
    });
  });

  describe('Pan controls', () => {
    it('should pan camera', () => {
      const { result } = renderHook(() => useGraphCamera([]));
      
      act(() => {
        result.current.pan(10, 20);
      });
      
      expect(result.current.position).toEqual({ x: 10, y: 20 });
    });

    it('should pan to specific position', () => {
      const { result } = renderHook(() => useGraphCamera([]));
      
      act(() => {
        result.current.panTo(50, 75, false);
      });
      
      expect(result.current.position).toEqual({ x: 50, y: 75 });
    });

    it('should respect bounds when enabled', () => {
      const { result } = renderHook(() => 
        useGraphCamera([], {
          enableBounds: true,
          bounds: { minX: -100, maxX: 100, minY: -100, maxY: 100 }
        })
      );
      
      act(() => {
        result.current.panTo(200, 200, false);
      });
      
      expect(result.current.position.x).toBe(100); // Clamped to maxX
      expect(result.current.position.y).toBe(100); // Clamped to maxY
    });

    it('should trigger position change callback', () => {
      const onPositionChange = vi.fn();
      const { result } = renderHook(() => 
        useGraphCamera([], { onPositionChange })
      );
      
      act(() => {
        result.current.panTo(10, 20, false);
      });
      
      expect(onPositionChange).toHaveBeenCalledWith({ x: 10, y: 20 });
    });
  });

  describe('Rotation controls', () => {
    it('should rotate camera', () => {
      const { result } = renderHook(() => 
        useGraphCamera([], { enableRotation: true })
      );
      
      act(() => {
        result.current.rotate(45);
      });
      
      expect(result.current.rotation).toBe(45);
    });

    it('should rotate to specific angle', () => {
      const { result } = renderHook(() => 
        useGraphCamera([], { enableRotation: true })
      );
      
      act(() => {
        result.current.rotateTo(90, false);
      });
      
      expect(result.current.rotation).toBe(90);
    });

    it('should normalize rotation angle', () => {
      const { result } = renderHook(() => 
        useGraphCamera([], { enableRotation: true })
      );
      
      act(() => {
        result.current.rotateTo(450, false);
      });
      
      expect(result.current.rotation).toBe(90); // 450 % 360 = 90
    });
  });

  describe('Reset', () => {
    it('should reset to initial values', () => {
      const { result } = renderHook(() => 
        useGraphCamera([], {
          initialZoom: 1.5,
          initialPosition: { x: 10, y: 10 },
          initialRotation: 30
        })
      );
      
      act(() => {
        result.current.zoomTo(2, false);
        result.current.panTo(50, 50, false);
        result.current.reset(false);
      });
      
      expect(result.current.zoom).toBe(1.5);
      expect(result.current.position).toEqual({ x: 10, y: 10 });
      expect(result.current.rotation).toBe(30);
    });
  });

  describe('Node centering', () => {
    it('should center on a specific node', () => {
      const { result } = renderHook(() => useGraphCamera(mockNodes));
      
      act(() => {
        result.current.centerOnNode('node2', undefined, false);
      });
      
      expect(result.current.position).toEqual({ x: 100, y: 100 });
    });

    it('should center on multiple nodes', () => {
      const { result } = renderHook(() => useGraphCamera(mockNodes));
      
      act(() => {
        result.current.centerOnNodes(['node1', 'node2'], 0, false);
      });
      
      // Should center between node1 (0,0) and node2 (100,100)
      expect(result.current.position.x).toBeCloseTo(50);
      expect(result.current.position.y).toBeCloseTo(50);
    });

    it('should handle missing nodes gracefully', () => {
      const { result } = renderHook(() => useGraphCamera(mockNodes));
      
      const initialPosition = { ...result.current.position };
      
      act(() => {
        result.current.centerOnNode('nonexistent', undefined, false);
      });
      
      // Position should not change
      expect(result.current.position).toEqual(initialPosition);
    });
  });

  describe('Fit to view', () => {
    it('should fit all nodes in view', () => {
      const { result } = renderHook(() => useGraphCamera(mockNodes));
      
      act(() => {
        result.current.fitToView(0, false);
      });
      
      // Should center on all nodes
      // Center X: (0 + 100 + -50) / 3 = 16.67, but actual is (min + max) / 2 = (-50 + 100) / 2 = 25
      expect(result.current.position.x).toBeCloseTo(25, 1);
      expect(result.current.position.y).toBeCloseTo(50, 1);
    });

    it('should fit specific nodes in view', () => {
      const { result } = renderHook(() => useGraphCamera(mockNodes));
      
      act(() => {
        result.current.fitToNodes([mockNodes[0], mockNodes[1]], 0, false);
      });
      
      // Should center between node1 and node2
      expect(result.current.position.x).toBeCloseTo(50);
      expect(result.current.position.y).toBeCloseTo(50);
    });
  });

  describe('Presets', () => {
    it('should save and load presets', () => {
      const { result } = renderHook(() => useGraphCamera([]));
      
      act(() => {
        result.current.zoomTo(2, false);
        result.current.panTo(10, 20, false);
        result.current.savePreset('test');
      });
      
      // Verify preset was saved
      expect(result.current.presets).toHaveLength(1);
      expect(result.current.presets[0].name).toBe('test');
      
      act(() => {
        result.current.reset(false);
      });
      
      // Verify reset worked
      expect(result.current.zoom).toBe(1);
      expect(result.current.position).toEqual({ x: 0, y: 0 });
      
      act(() => {
        result.current.loadPreset('test', false);
      });
      
      expect(result.current.zoom).toBe(2);
      expect(result.current.position).toEqual({ x: 10, y: 20 });
    });

    it('should delete presets', () => {
      const { result } = renderHook(() => useGraphCamera([]));
      
      act(() => {
        result.current.savePreset('test');
        result.current.deletePreset('test');
        result.current.loadPreset('test', false);
      });
      
      // Should not change since preset was deleted
      expect(result.current.zoom).toBe(1);
    });
  });

  describe('Viewport utilities', () => {
    it('should get viewport info', () => {
      const { result } = renderHook(() => useGraphCamera([]));
      
      const viewport = result.current.getViewport();
      
      expect(viewport).toEqual({
        zoom: 1,
        position: { x: 0, y: 0 },
        rotation: 0,
        bounds: null,
        isAnimating: false
      });
    });

    it('should convert screen to world coordinates', () => {
      const { result } = renderHook(() => useGraphCamera([]));
      
      act(() => {
        result.current.zoomTo(2, false);
        result.current.panTo(10, 10, false);
      });
      
      const world = result.current.screenToWorld(500, 500, { width: 1000, height: 1000 });
      
      expect(world.x).toBeCloseTo(10);
      expect(world.y).toBeCloseTo(10);
    });

    it('should convert world to screen coordinates', () => {
      const { result } = renderHook(() => useGraphCamera([]));
      
      act(() => {
        result.current.zoomTo(2, false);
        result.current.panTo(10, 10, false);
      });
      
      const screen = result.current.worldToScreen(10, 10, { width: 1000, height: 1000 });
      
      expect(screen.x).toBeCloseTo(500);
      expect(screen.y).toBeCloseTo(500);
    });

    it('should get visible nodes', () => {
      const { result } = renderHook(() => useGraphCamera(mockNodes));
      
      const visible = result.current.getVisibleNodes({ width: 200, height: 200 });
      
      // With default zoom and position, all nodes should be visible
      expect(visible).toHaveLength(3);
    });
  });

  describe('Persistence', () => {
    it('should persist state changes', () => {
      const { result } = renderHook(() => 
        useGraphCamera([], { 
          persistState: true,
          storageKey: 'test-camera'
        })
      );
      
      act(() => {
        result.current.zoomTo(2, false);
      });
      
      const saved = localStorage.getItem('test-camera');
      expect(saved).toBeTruthy();
      
      const parsed = JSON.parse(saved!);
      expect(parsed.zoom).toBe(2);
    });
  });
});

describe('useSimpleCamera', () => {
  it('should provide basic camera controls', () => {
    const { result } = renderHook(() => useSimpleCamera(1));
    
    expect(result.current.zoom).toBe(1);
    expect(result.current.position).toEqual({ x: 0, y: 0 });
    
    act(() => {
      result.current.zoomIn();
    });
    
    expect(result.current.zoom).toBeGreaterThan(1);
    
    act(() => {
      result.current.pan(10, 20);
    });
    
    expect(result.current.position).toEqual({ x: 10, y: 20 });
    
    act(() => {
      result.current.reset();
    });
    
    expect(result.current.zoom).toBe(1);
    expect(result.current.position).toEqual({ x: 0, y: 0 });
  });
});