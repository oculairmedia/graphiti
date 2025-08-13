/**
 * Unit tests for useGraphStatistics hook
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useGraphStatistics, useSimpleGraphStatistics } from '../../hooks/useGraphStatistics';
import { GraphNode } from '../../api/types';
import { GraphLink } from '../../types/graph';

// Mock the utility functions
vi.mock('../../utils/graphNodeOperations', () => ({
  calculateNodeStats: vi.fn(() => ({
    total: 3,
    byType: new Map([['person', 1], ['organization', 1], ['location', 1]]),
    avgCentrality: 0.6,
    maxCentrality: 0.8,
    minCentrality: 0.4,
    withTimestamps: 3,
    uniqueTypes: 3
  })),
  calculateNodeDegrees: vi.fn(() => new Map([
    ['node1', 1],
    ['node2', 2],
    ['node3', 1]
  ]))
}));

vi.mock('../../utils/graphLinkOperations', () => ({
  calculateLinkStats: vi.fn(() => ({
    total: 2,
    byType: new Map([['knows', 1], ['works_with', 1]]),
    avgWeight: 1.5,
    maxWeight: 2,
    minWeight: 1,
    withTimestamps: 2,
    uniqueTypes: 2,
    selfLoops: 0
  }))
}));

vi.mock('../../utils/graphMetrics', () => ({
  calculateGraphMetrics: vi.fn(() => ({
    density: 0.33,
    avgDegree: 1.33,
    maxDegree: 2,
    minDegree: 1
  }))
}));

describe('useGraphStatistics', () => {
  const mockNodes: GraphNode[] = [
    { id: 'node1', name: 'Node 1', node_type: 'person', properties: { degree_centrality: 0.8 } },
    { id: 'node2', name: 'Node 2', node_type: 'organization', properties: { degree_centrality: 0.6 } },
    { id: 'node3', name: 'Node 3', node_type: 'location', properties: { degree_centrality: 0.4 } },
  ];

  const mockLinks: GraphLink[] = [
    { source: 'node1', target: 'node2', edge_type: 'knows', weight: 1 },
    { source: 'node2', target: 'node3', edge_type: 'works_with', weight: 2 },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  describe('Basic functionality', () => {
    it('should initialize with correct default statistics', () => {
      const { result } = renderHook(() => 
        useGraphStatistics([], [])
      );

      expect(result.current.statistics.nodeCount).toBe(0);
      expect(result.current.statistics.edgeCount).toBe(0);
      expect(result.current.isEmpty).toBe(true);
    });

    it('should update statistics when data changes', async () => {
      const { result } = renderHook(() => 
        useGraphStatistics(mockNodes, mockLinks)
      );

      // Wait for throttled update
      act(() => {
        vi.advanceTimersByTime(100);
      });

      await waitFor(() => {
        expect(result.current.statistics.nodeCount).toBe(3);
        expect(result.current.statistics.edgeCount).toBe(2);
      });
    });

    it('should calculate detailed statistics when enabled', async () => {
      const { result } = renderHook(() => 
        useGraphStatistics(mockNodes, mockLinks, { detailed: true })
      );

      act(() => {
        vi.advanceTimersByTime(100);
      });

      await waitFor(() => {
        expect(result.current.statistics.avgCentrality).toBe(0.6);
        expect(result.current.statistics.maxCentrality).toBe(0.8);
        expect(result.current.statistics.density).toBe(0.33);
      });
    });
  });

  describe('Throttling', () => {
    it('should throttle updates', async () => {
      const onStatsUpdate = vi.fn();
      const { rerender } = renderHook(
        ({ nodes, links }) => useGraphStatistics(nodes, links, { 
          onStatsUpdate,
          updateThrottle: 200 
        }),
        { initialProps: { nodes: [], links: [] } }
      );

      // Rapid updates
      rerender({ nodes: mockNodes.slice(0, 1), links: [] });
      rerender({ nodes: mockNodes.slice(0, 2), links: [] });
      rerender({ nodes: mockNodes, links: mockLinks });

      // Should not update immediately
      expect(onStatsUpdate).toHaveBeenCalledTimes(1); // Initial empty state

      // Wait for throttle
      act(() => {
        vi.advanceTimersByTime(200);
      });

      await waitFor(() => {
        // Should batch updates
        expect(onStatsUpdate).toHaveBeenCalledTimes(2);
      });
    });

    it('should allow immediate updates when throttle is 0', async () => {
      const onStatsUpdate = vi.fn();
      const { rerender } = renderHook(
        ({ nodes }) => useGraphStatistics(nodes, [], { 
          onStatsUpdate,
          updateThrottle: 0 
        }),
        { initialProps: { nodes: [] } }
      );

      rerender({ nodes: mockNodes.slice(0, 1) });
      rerender({ nodes: mockNodes.slice(0, 2) });

      await waitFor(() => {
        expect(onStatsUpdate.mock.calls.length).toBeGreaterThan(2);
      });
    });
  });

  describe('Callbacks', () => {
    it('should trigger onSignificantChange for large changes', async () => {
      const onSignificantChange = vi.fn();
      const { rerender } = renderHook(
        ({ nodes }) => useGraphStatistics(nodes, [], { 
          onSignificantChange,
          detailed: false 
        }),
        { initialProps: { nodes: mockNodes.slice(0, 1) } }
      );

      act(() => {
        vi.advanceTimersByTime(100);
      });

      // Add many nodes (> 10% change)
      rerender({ nodes: mockNodes });

      act(() => {
        vi.advanceTimersByTime(100);
      });

      await waitFor(() => {
        expect(onSignificantChange).toHaveBeenCalled();
      });
    });

    it('should call onStatsUpdate when statistics change', async () => {
      const onStatsUpdate = vi.fn();
      const { result } = renderHook(() => 
        useGraphStatistics(mockNodes, mockLinks, { onStatsUpdate })
      );

      act(() => {
        vi.advanceTimersByTime(100);
      });

      await waitFor(() => {
        expect(onStatsUpdate).toHaveBeenCalledWith(
          expect.objectContaining({
            nodeCount: 3,
            edgeCount: 2
          })
        );
      });
    });
  });

  describe('Performance tracking', () => {
    it('should track performance metrics when enabled', async () => {
      const { result } = renderHook(() => 
        useGraphStatistics(mockNodes, mockLinks, { 
          trackPerformance: true,
          detailed: true 
        })
      );

      act(() => {
        vi.advanceTimersByTime(100);
      });

      await waitFor(() => {
        const metrics = result.current.getPerformanceMetrics();
        expect(metrics).not.toBeNull();
        expect(metrics?.updateCount).toBeGreaterThan(0);
      });
    });

    it('should return null performance metrics when disabled', () => {
      const { result } = renderHook(() => 
        useGraphStatistics(mockNodes, mockLinks, { trackPerformance: false })
      );

      const metrics = result.current.getPerformanceMetrics();
      expect(metrics).toBeNull();
    });
  });

  describe('Utility methods', () => {
    it('should get node count by type', async () => {
      const { result } = renderHook(() => 
        useGraphStatistics(mockNodes, mockLinks, { detailed: true })
      );

      act(() => {
        vi.advanceTimersByTime(100);
      });

      await waitFor(() => {
        expect(result.current.getNodeCountByType('person')).toBe(1);
        expect(result.current.getNodeCountByType('nonexistent')).toBe(0);
      });
    });

    it('should get link count by type', async () => {
      const { result } = renderHook(() => 
        useGraphStatistics(mockNodes, mockLinks, { detailed: true })
      );

      act(() => {
        vi.advanceTimersByTime(100);
      });

      await waitFor(() => {
        expect(result.current.getLinkCountByType('knows')).toBe(1);
        expect(result.current.getLinkCountByType('nonexistent')).toBe(0);
      });
    });

    it('should get basic stats efficiently', async () => {
      const { result } = renderHook(() => 
        useGraphStatistics(mockNodes, mockLinks)
      );

      act(() => {
        vi.advanceTimersByTime(100);
      });

      const basicStats = result.current.getBasicStats();
      expect(basicStats).toEqual({
        nodeCount: 3,
        edgeCount: 2,
        lastUpdated: expect.any(Number)
      });
    });

    it('should force immediate update', async () => {
      const onStatsUpdate = vi.fn();
      const { result } = renderHook(() => 
        useGraphStatistics(mockNodes, mockLinks, { 
          onStatsUpdate,
          updateThrottle: 1000 
        })
      );

      // Force update should bypass throttle
      act(() => {
        result.current.forceUpdate();
      });

      await waitFor(() => {
        expect(onStatsUpdate).toHaveBeenCalledWith(
          expect.objectContaining({
            nodeCount: 3,
            edgeCount: 2
          })
        );
      });
    });
  });

  describe('State checks', () => {
    it('should correctly identify empty graph', () => {
      const { result } = renderHook(() => 
        useGraphStatistics([], [])
      );

      expect(result.current.isEmpty).toBe(true);
    });

    it('should correctly identify non-empty graph', async () => {
      const { result } = renderHook(() => 
        useGraphStatistics(mockNodes, mockLinks)
      );

      act(() => {
        vi.advanceTimersByTime(100);
      });

      await waitFor(() => {
        expect(result.current.isEmpty).toBe(false);
      });
    });

    it('should correctly identify dense graph', async () => {
      const { result } = renderHook(() => 
        useGraphStatistics(mockNodes, mockLinks, { detailed: true })
      );

      act(() => {
        vi.advanceTimersByTime(100);
      });

      await waitFor(() => {
        // Mocked density is 0.33, so not dense
        expect(result.current.isDense).toBe(false);
      });
    });

    it('should correctly identify sparse graph', async () => {
      const { result } = renderHook(() => 
        useGraphStatistics(mockNodes, mockLinks, { detailed: true })
      );

      act(() => {
        vi.advanceTimersByTime(100);
      });

      await waitFor(() => {
        // Mocked density is 0.33, so not sparse (< 0.1)
        expect(result.current.isSparse).toBe(false);
      });
    });
  });

  describe('Cleanup', () => {
    it('should cleanup timeouts on unmount', () => {
      const { unmount } = renderHook(() => 
        useGraphStatistics(mockNodes, mockLinks, { updateThrottle: 1000 })
      );

      const clearTimeoutSpy = vi.spyOn(global, 'clearTimeout');
      unmount();

      expect(clearTimeoutSpy).toHaveBeenCalled();
    });
  });
});

describe('useSimpleGraphStatistics', () => {
  const mockNodes: GraphNode[] = [
    { id: 'node1', name: 'Node 1', node_type: 'person' },
    { id: 'node2', name: 'Node 2', node_type: 'organization' },
  ];

  const mockLinks: GraphLink[] = [
    { source: 'node1', target: 'node2', weight: 1 },
  ];

  it('should return basic statistics', () => {
    const { result } = renderHook(() => 
      useSimpleGraphStatistics(mockNodes, mockLinks)
    );

    expect(result.current).toEqual({
      nodeCount: 2,
      edgeCount: 1,
      lastUpdated: expect.any(Number)
    });
  });

  it('should update when data changes', () => {
    const { result, rerender } = renderHook(
      ({ nodes, links }) => useSimpleGraphStatistics(nodes, links),
      { initialProps: { nodes: [], links: [] } }
    );

    expect(result.current.nodeCount).toBe(0);

    rerender({ nodes: mockNodes, links: mockLinks });

    expect(result.current.nodeCount).toBe(2);
    expect(result.current.edgeCount).toBe(1);
  });

  it('should call onUpdate callback', () => {
    const onUpdate = vi.fn();
    renderHook(() => 
      useSimpleGraphStatistics(mockNodes, mockLinks, onUpdate)
    );

    expect(onUpdate).toHaveBeenCalledWith({
      nodeCount: 2,
      edgeCount: 1,
      lastUpdated: expect.any(Number)
    });
  });
});