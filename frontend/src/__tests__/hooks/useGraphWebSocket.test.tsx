/**
 * Unit tests for useGraphWebSocket hook
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useGraphWebSocket, useSimpleGraphUpdates } from '../../hooks/useGraphWebSocket';
import { GraphNode } from '../../api/types';
import { GraphLink } from '../../types/graph';

// Mock the WebSocket contexts
vi.mock('../../contexts/WebSocketProvider', () => ({
  useWebSocketContext: vi.fn()
}));

vi.mock('../../contexts/RustWebSocketProvider', () => ({
  useRustWebSocket: vi.fn()
}));

import { useWebSocketContext } from '../../contexts/WebSocketProvider';
import { useRustWebSocket } from '../../contexts/RustWebSocketProvider';

describe('useGraphWebSocket', () => {
  const mockNodes: GraphNode[] = [
    { id: 'node1', name: 'Node 1', node_type: 'person' },
    { id: 'node2', name: 'Node 2', node_type: 'organization' },
  ];

  const mockLinks: GraphLink[] = [
    { source: 'node1', target: 'node2', edge_type: 'knows', weight: 1 },
  ];

  const mockPythonWs = {
    isConnected: true,
    connectionQuality: 'good' as const,
    latency: 50,
    subscribe: vi.fn(() => vi.fn()),
    subscribeToNodeAccess: vi.fn(() => vi.fn()),
    subscribeToGraphUpdate: vi.fn(() => vi.fn()),
    subscribeToDeltaUpdate: vi.fn(() => vi.fn()),
    subscribeToCacheInvalidate: vi.fn(() => vi.fn())
  };

  const mockRustWs = {
    isConnected: true,
    subscribe: vi.fn(() => vi.fn()),
    sendMessage: vi.fn()
  };

  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
    (useWebSocketContext as any).mockReturnValue(mockPythonWs);
    (useRustWebSocket as any).mockReturnValue(mockRustWs);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  describe('Connection status', () => {
    it('should initialize with disconnected status when contexts are null', () => {
      (useWebSocketContext as any).mockReturnValue(null);
      (useRustWebSocket as any).mockReturnValue(null);
      
      const { result } = renderHook(() => useGraphWebSocket());
      
      expect(result.current.connectionStatus.overall).toBe('disconnected');
      expect(result.current.isConnected).toBe(false);
    });

    it('should show connected when both WebSockets are connected', () => {
      const { result } = renderHook(() => useGraphWebSocket());
      
      expect(result.current.connectionStatus.python.connected).toBe(true);
      expect(result.current.connectionStatus.rust.connected).toBe(true);
      expect(result.current.connectionStatus.overall).toBe('connected');
    });

    it('should show partial connection when only one is connected', () => {
      (useRustWebSocket as any).mockReturnValue({ ...mockRustWs, isConnected: false });
      
      const { result } = renderHook(() => useGraphWebSocket());
      
      expect(result.current.connectionStatus.overall).toBe('partial');
    });

    it('should trigger connection change callback', () => {
      const onConnectionChange = vi.fn();
      renderHook(() => useGraphWebSocket({ onConnectionChange }));
      
      expect(onConnectionChange).toHaveBeenCalledWith(
        expect.objectContaining({
          overall: expect.any(String)
        })
      );
    });
  });

  describe('Event handling', () => {
    it('should handle node access events', () => {
      const onNodeAccess = vi.fn();
      const { result } = renderHook(() => 
        useGraphWebSocket({ onNodeAccess })
      );
      
      act(() => {
        result.current.triggerNodeAccess(['node1', 'node2']);
      });
      
      expect(onNodeAccess).toHaveBeenCalledWith(
        expect.objectContaining({
          type: 'node_access',
          node_ids: ['node1', 'node2']
        })
      );
      
      expect(result.current.statistics.nodeAccessEvents).toBe(1);
    });

    it('should handle graph update events', () => {
      const onGraphUpdate = vi.fn();
      const { result } = renderHook(() => 
        useGraphWebSocket({ onGraphUpdate })
      );
      
      act(() => {
        result.current.triggerGraphUpdate(mockNodes, mockLinks);
      });
      
      expect(onGraphUpdate).toHaveBeenCalledWith(
        expect.objectContaining({
          type: 'graph_update',
          nodes: mockNodes,
          edges: mockLinks
        })
      );
      
      expect(result.current.statistics.totalUpdates).toBe(1);
    });

    it('should handle cache invalidate events', () => {
      const onCacheInvalidate = vi.fn();
      const { result } = renderHook(() => 
        useGraphWebSocket({ onCacheInvalidate })
      );
      
      act(() => {
        result.current.triggerCacheInvalidate(['key1', 'key2']);
      });
      
      expect(onCacheInvalidate).toHaveBeenCalledWith(
        expect.objectContaining({
          type: 'cache_invalidate',
          keys: ['key1', 'key2']
        })
      );
      
      expect(result.current.statistics.cacheInvalidations).toBe(1);
    });
  });

  describe('Batching', () => {
    it('should batch delta updates', () => {
      const onDeltaUpdate = vi.fn();
      let deltaCallback: any;
      
      mockRustWs.subscribe.mockImplementation((cb) => {
        deltaCallback = cb;
        return vi.fn();
      });
      
      renderHook(() => 
        useGraphWebSocket({ 
          onDeltaUpdate,
          batchInterval: 100,
          maxBatchSize: 5
        })
      );
      
      // Send multiple updates
      act(() => {
        deltaCallback({
          type: 'graph:delta',
          data: {
            operation: 'add',
            nodes: [mockNodes[0]],
            timestamp: Date.now()
          }
        });
        
        deltaCallback({
          type: 'graph:delta',
          data: {
            operation: 'add',
            nodes: [mockNodes[1]],
            timestamp: Date.now()
          }
        });
      });
      
      // Should not trigger immediately
      expect(onDeltaUpdate).not.toHaveBeenCalled();
      
      // Advance timers to trigger batch
      act(() => {
        vi.advanceTimersByTime(100);
      });
      
      expect(onDeltaUpdate).toHaveBeenCalledWith(
        expect.objectContaining({
          type: 'delta_update',
          nodes: expect.arrayContaining([mockNodes[0], mockNodes[1]])
        })
      );
    });

    it('should flush batch when max size is reached', () => {
      const onDeltaUpdate = vi.fn();
      let deltaCallback: any;
      
      mockRustWs.subscribe.mockImplementation((cb) => {
        deltaCallback = cb;
        return vi.fn();
      });
      
      renderHook(() => 
        useGraphWebSocket({ 
          onDeltaUpdate,
          batchInterval: 1000,
          maxBatchSize: 2
        })
      );
      
      // Send updates to exceed max batch size
      act(() => {
        deltaCallback({
          type: 'graph:delta',
          data: {
            operation: 'add',
            nodes: [mockNodes[0]],
            timestamp: Date.now()
          }
        });
        
        deltaCallback({
          type: 'graph:delta',
          data: {
            operation: 'add',
            nodes: [mockNodes[1]],
            timestamp: Date.now()
          }
        });
      });
      
      // Should trigger immediately when max size is reached
      expect(onDeltaUpdate).toHaveBeenCalled();
    });

    it('should manually flush batch', () => {
      const onDeltaUpdate = vi.fn();
      let deltaCallback: any;
      
      mockRustWs.subscribe.mockImplementation((cb) => {
        deltaCallback = cb;
        return vi.fn();
      });
      
      const { result } = renderHook(() => 
        useGraphWebSocket({ 
          onDeltaUpdate,
          batchInterval: 1000
        })
      );
      
      // Add update to batch
      act(() => {
        deltaCallback({
          type: 'graph:delta',
          data: {
            operation: 'add',
            nodes: [mockNodes[0]],
            timestamp: Date.now()
          }
        });
      });
      
      // Manually flush
      act(() => {
        result.current.flushBatch();
      });
      
      expect(onDeltaUpdate).toHaveBeenCalled();
    });
  });

  describe('Statistics', () => {
    it('should track update statistics', () => {
      const { result } = renderHook(() => useGraphWebSocket());
      
      act(() => {
        result.current.triggerNodeAccess(['node1']);
        result.current.triggerGraphUpdate(mockNodes, mockLinks);
        result.current.triggerCacheInvalidate();
      });
      
      expect(result.current.statistics.totalUpdates).toBe(3);
      expect(result.current.statistics.nodeAccessEvents).toBe(1);
      expect(result.current.statistics.cacheInvalidations).toBe(1);
    });

    it('should calculate update rate', () => {
      const { result } = renderHook(() => useGraphWebSocket());
      
      // Trigger multiple updates quickly
      act(() => {
        for (let i = 0; i < 5; i++) {
          result.current.triggerNodeAccess([`node${i}`]);
        }
      });
      
      // Update rate should reflect recent updates
      expect(result.current.statistics.updateRate).toBeGreaterThan(0);
    });

    it('should clear statistics', () => {
      const { result } = renderHook(() => useGraphWebSocket());
      
      act(() => {
        result.current.triggerNodeAccess(['node1']);
        result.current.clearStatistics();
      });
      
      expect(result.current.statistics.totalUpdates).toBe(0);
      expect(result.current.statistics.nodeAccessEvents).toBe(0);
    });
  });

  describe('Recent events', () => {
    it('should track recent events', () => {
      const { result } = renderHook(() => useGraphWebSocket());
      
      act(() => {
        result.current.triggerNodeAccess(['node1']);
        result.current.triggerNodeAccess(['node2']);
        result.current.triggerGraphUpdate(mockNodes, []);
      });
      
      const recentEvents = result.current.getRecentEvents();
      expect(recentEvents).toHaveLength(3);
      
      const nodeAccessEvents = result.current.getRecentEvents('nodeAccess');
      expect(nodeAccessEvents).toHaveLength(2);
    });

    it('should limit recent events', () => {
      const { result } = renderHook(() => useGraphWebSocket());
      
      // Trigger more than 10 events
      act(() => {
        for (let i = 0; i < 15; i++) {
          result.current.triggerNodeAccess([`node${i}`]);
        }
      });
      
      const recentEvents = result.current.getRecentEvents('nodeAccess');
      expect(recentEvents).toHaveLength(10); // Limited to 10
    });
  });

  describe('WebSocket subscriptions', () => {
    it('should subscribe to Python WebSocket events', () => {
      renderHook(() => useGraphWebSocket({ enablePython: true }));
      
      expect(mockPythonWs.subscribeToNodeAccess).toHaveBeenCalled();
      expect(mockPythonWs.subscribeToGraphUpdate).toHaveBeenCalled();
      expect(mockPythonWs.subscribeToDeltaUpdate).toHaveBeenCalled();
      expect(mockPythonWs.subscribeToCacheInvalidate).toHaveBeenCalled();
    });

    it('should subscribe to Rust WebSocket events', () => {
      renderHook(() => useGraphWebSocket({ enableRust: true }));
      
      expect(mockRustWs.subscribe).toHaveBeenCalled();
    });

    it('should skip subscriptions when disabled', () => {
      vi.clearAllMocks();
      
      renderHook(() => useGraphWebSocket({ 
        enablePython: false,
        enableRust: false 
      }));
      
      expect(mockPythonWs.subscribeToNodeAccess).not.toHaveBeenCalled();
      expect(mockRustWs.subscribe).not.toHaveBeenCalled();
    });
  });
});

describe('useSimpleGraphUpdates', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (useWebSocketContext as any).mockReturnValue(null);
    (useRustWebSocket as any).mockReturnValue(null);
  });

  it('should handle simple updates', () => {
    const onUpdate = vi.fn();
    const { result } = renderHook(() => useSimpleGraphUpdates(onUpdate));
    
    expect(result.current.updateCount).toBe(0);
    expect(result.current.updateRate).toBe(0);
  });
});