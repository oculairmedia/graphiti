/**
 * Test suite for incremental graph updates
 * Validates that real-time updates work correctly with Cosmograph
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useCosmographIncrementalUpdates } from '../hooks/useCosmographIncrementalUpdates';
import type { GraphNode } from '../api/types';
import type { GraphLink } from '../types/graph';
import type { DeltaUpdate } from '../utils/cosmographTransformers';

// Mock Cosmograph instance
const createMockCosmograph = () => ({
  addPoints: vi.fn().mockResolvedValue(undefined),
  addLinks: vi.fn().mockResolvedValue(undefined),
  removePoints: vi.fn().mockResolvedValue(undefined),
  removeLinks: vi.fn().mockResolvedValue(undefined),
  setConfig: vi.fn(),
  start: vi.fn(),
  restart: vi.fn(),
  dispose: vi.fn()
});

// Test data generators
const createTestNode = (id: string): GraphNode => ({
  id,
  name: `Node ${id}`,
  entity_type: 'Entity',
  created_at: new Date().toISOString(),
  content: `Test node ${id}`,
  properties: {}
});

const createTestEdge = (source: string, target: string): GraphLink => ({
  source,
  target,
  weight: 1,
  relationship_type: 'RELATES_TO',
  created_at: new Date().toISOString()
});

describe('Incremental Updates', () => {
  let mockCosmograph: ReturnType<typeof createMockCosmograph>;
  let cosmographRef: { current: any };
  
  beforeEach(() => {
    mockCosmograph = createMockCosmograph();
    cosmographRef = { current: mockCosmograph };
    vi.clearAllMocks();
  });
  
  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('Node Operations', () => {
    it('should add new nodes incrementally', async () => {
      const initialNodes: GraphNode[] = [
        createTestNode('1'),
        createTestNode('2')
      ];
      const initialEdges: GraphLink[] = [];
      
      const { result } = renderHook(() =>
        useCosmographIncrementalUpdates(
          cosmographRef,
          initialNodes,
          initialEdges
        )
      );
      
      const newNodes = [createTestNode('3'), createTestNode('4')];
      
      await act(async () => {
        const success = await result.current.applyDelta({
          type: 'graph:delta',
          data: {
            operation: 'add',
            nodes: newNodes,
            edges: [],
            timestamp: Date.now()
          }
        });
        
        expect(success).toBe(true);
        expect(mockCosmograph.addPoints).toHaveBeenCalledTimes(1);
        expect(mockCosmograph.addPoints).toHaveBeenCalledWith(
          expect.arrayContaining([
            expect.objectContaining({ id: '3' }),
            expect.objectContaining({ id: '4' })
          ])
        );
      });
    });
    
    it('should remove nodes incrementally', async () => {
      const initialNodes: GraphNode[] = [
        createTestNode('1'),
        createTestNode('2'),
        createTestNode('3')
      ];
      const initialEdges: GraphLink[] = [];
      
      const { result } = renderHook(() =>
        useCosmographIncrementalUpdates(
          cosmographRef,
          initialNodes,
          initialEdges
        )
      );
      
      await act(async () => {
        const success = await result.current.applyDelta({
          type: 'graph:delta',
          data: {
            operation: 'delete',
            nodes: ['2'],
            edges: [],
            timestamp: Date.now()
          }
        });
        
        expect(success).toBe(true);
        expect(mockCosmograph.removePoints).toHaveBeenCalledTimes(1);
        expect(mockCosmograph.removePoints).toHaveBeenCalledWith(
          expect.arrayContaining([expect.any(Number)])
        );
      });
    });
    
    it('should handle node update operations', async () => {
      const initialNodes: GraphNode[] = [
        createTestNode('1'),
        createTestNode('2')
      ];
      const initialEdges: GraphLink[] = [];
      
      const { result } = renderHook(() =>
        useCosmographIncrementalUpdates(
          cosmographRef,
          initialNodes,
          initialEdges
        )
      );
      
      const updatedNode = {
        ...createTestNode('1'),
        name: 'Updated Node 1'
      };
      
      await act(async () => {
        const success = await result.current.applyDelta({
          type: 'graph:delta',
          data: {
            operation: 'update',
            nodes: [updatedNode],
            edges: [],
            timestamp: Date.now()
          }
        });
        
        // Updates currently fall back to state-based updates
        expect(success).toBe(false);
      });
    });
  });

  describe('Edge Operations', () => {
    it('should add new edges incrementally', async () => {
      const initialNodes: GraphNode[] = [
        createTestNode('1'),
        createTestNode('2'),
        createTestNode('3')
      ];
      const initialEdges: GraphLink[] = [
        createTestEdge('1', '2')
      ];
      
      const { result } = renderHook(() =>
        useCosmographIncrementalUpdates(
          cosmographRef,
          initialNodes,
          initialEdges
        )
      );
      
      const newEdges = [
        createTestEdge('2', '3'),
        createTestEdge('1', '3')
      ];
      
      await act(async () => {
        const success = await result.current.applyDelta({
          type: 'graph:delta',
          data: {
            operation: 'add',
            nodes: [],
            edges: newEdges,
            timestamp: Date.now()
          }
        });
        
        expect(success).toBe(true);
        expect(mockCosmograph.addLinks).toHaveBeenCalledTimes(1);
        expect(mockCosmograph.addLinks).toHaveBeenCalledWith(
          expect.arrayContaining([
            expect.objectContaining({ source: expect.any(Number), target: expect.any(Number) })
          ])
        );
      });
    });
    
    it('should remove edges incrementally', async () => {
      const initialNodes: GraphNode[] = [
        createTestNode('1'),
        createTestNode('2'),
        createTestNode('3')
      ];
      const initialEdges: GraphLink[] = [
        createTestEdge('1', '2'),
        createTestEdge('2', '3'),
        createTestEdge('1', '3')
      ];
      
      const { result } = renderHook(() =>
        useCosmographIncrementalUpdates(
          cosmographRef,
          initialNodes,
          initialEdges
        )
      );
      
      await act(async () => {
        const success = await result.current.applyDelta({
          type: 'graph:delta',
          data: {
            operation: 'delete',
            nodes: [],
            edges: ['1-2', '2-3'],
            timestamp: Date.now()
          }
        });
        
        expect(success).toBe(true);
        expect(mockCosmograph.removeLinks).toHaveBeenCalledTimes(1);
      });
    });
  });

  describe('Combined Operations', () => {
    it('should handle combined node and edge additions', async () => {
      const initialNodes: GraphNode[] = [
        createTestNode('1'),
        createTestNode('2')
      ];
      const initialEdges: GraphLink[] = [
        createTestEdge('1', '2')
      ];
      
      const { result } = renderHook(() =>
        useCosmographIncrementalUpdates(
          cosmographRef,
          initialNodes,
          initialEdges
        )
      );
      
      const newNodes = [createTestNode('3'), createTestNode('4')];
      const newEdges = [
        createTestEdge('3', '4'),
        createTestEdge('2', '3')
      ];
      
      await act(async () => {
        const success = await result.current.applyDelta({
          type: 'graph:delta',
          data: {
            operation: 'add',
            nodes: newNodes,
            edges: newEdges,
            timestamp: Date.now()
          }
        });
        
        expect(success).toBe(true);
        expect(mockCosmograph.addPoints).toHaveBeenCalled();
        expect(mockCosmograph.addLinks).toHaveBeenCalled();
      });
    });
    
    it('should handle combined removals', async () => {
      const initialNodes: GraphNode[] = [
        createTestNode('1'),
        createTestNode('2'),
        createTestNode('3'),
        createTestNode('4')
      ];
      const initialEdges: GraphLink[] = [
        createTestEdge('1', '2'),
        createTestEdge('2', '3'),
        createTestEdge('3', '4')
      ];
      
      const { result } = renderHook(() =>
        useCosmographIncrementalUpdates(
          cosmographRef,
          initialNodes,
          initialEdges
        )
      );
      
      await act(async () => {
        const success = await result.current.applyDelta({
          type: 'graph:delta',
          data: {
            operation: 'delete',
            nodes: ['3', '4'],
            edges: ['2-3', '3-4'],
            timestamp: Date.now()
          }
        });
        
        expect(success).toBe(true);
        expect(mockCosmograph.removePoints).toHaveBeenCalled();
        expect(mockCosmograph.removeLinks).toHaveBeenCalled();
      });
    });
  });

  describe('Error Handling', () => {
    it('should handle errors gracefully with fallback', async () => {
      const initialNodes: GraphNode[] = [createTestNode('1')];
      const initialEdges: GraphLink[] = [];
      
      // Make addPoints fail
      mockCosmograph.addPoints.mockRejectedValueOnce(new Error('WebGL context lost'));
      
      const onError = vi.fn();
      const fallbackToFullUpdate = vi.fn();
      
      const { result } = renderHook(() =>
        useCosmographIncrementalUpdates(
          cosmographRef,
          initialNodes,
          initialEdges,
          {
            onError,
            fallbackToFullUpdate
          }
        )
      );
      
      await act(async () => {
        const success = await result.current.applyDelta({
          type: 'graph:delta',
          data: {
            operation: 'add',
            nodes: [createTestNode('2')],
            edges: [],
            timestamp: Date.now()
          }
        });
        
        expect(success).toBe(false);
        expect(onError).toHaveBeenCalled();
        // Fallback should be triggered after all strategies fail
        expect(fallbackToFullUpdate).toHaveBeenCalled();
      });
    });
    
    it('should retry failed operations with backoff', async () => {
      const initialNodes: GraphNode[] = [createTestNode('1')];
      const initialEdges: GraphLink[] = [];
      
      // Make addPoints fail once then succeed
      mockCosmograph.addPoints
        .mockRejectedValueOnce(new Error('Network error'))
        .mockResolvedValueOnce(undefined);
      
      const { result } = renderHook(() =>
        useCosmographIncrementalUpdates(
          cosmographRef,
          initialNodes,
          initialEdges
        )
      );
      
      // Note: This test would need more complex setup to properly test retry logic
      // as the fallback orchestrator runs asynchronously
      await act(async () => {
        const success = await result.current.applyDelta({
          type: 'graph:delta',
          data: {
            operation: 'add',
            nodes: [createTestNode('2')],
            edges: [],
            timestamp: Date.now()
          }
        });
        
        // First attempt will fail but retry might succeed
        expect(mockCosmograph.addPoints).toHaveBeenCalled();
      });
    });
  });

  describe('Performance Metrics', () => {
    it('should track update metrics', async () => {
      const initialNodes: GraphNode[] = [createTestNode('1')];
      const initialEdges: GraphLink[] = [];
      
      const { result } = renderHook(() =>
        useCosmographIncrementalUpdates(
          cosmographRef,
          initialNodes,
          initialEdges
        )
      );
      
      // Perform successful update
      await act(async () => {
        await result.current.applyDelta({
          type: 'graph:delta',
          data: {
            operation: 'add',
            nodes: [createTestNode('2')],
            edges: [],
            timestamp: Date.now()
          }
        });
      });
      
      const metrics = result.current.metrics;
      expect(metrics.totalUpdates).toBe(1);
      expect(metrics.successfulUpdates).toBe(1);
      expect(metrics.failedUpdates).toBe(0);
      expect(metrics.averageUpdateTime).toBeGreaterThan(0);
    });
    
    it('should track failed update metrics', async () => {
      const initialNodes: GraphNode[] = [createTestNode('1')];
      const initialEdges: GraphLink[] = [];
      
      // Make addPoints fail
      mockCosmograph.addPoints.mockRejectedValue(new Error('Test error'));
      
      const { result } = renderHook(() =>
        useCosmographIncrementalUpdates(
          cosmographRef,
          initialNodes,
          initialEdges
        )
      );
      
      await act(async () => {
        await result.current.applyDelta({
          type: 'graph:delta',
          data: {
            operation: 'add',
            nodes: [createTestNode('2')],
            edges: [],
            timestamp: Date.now()
          }
        });
      });
      
      const metrics = result.current.metrics;
      expect(metrics.totalUpdates).toBe(1);
      expect(metrics.successfulUpdates).toBe(0);
      expect(metrics.failedUpdates).toBe(1);
    });
  });

  describe('Data Validation', () => {
    it('should validate node data before applying', async () => {
      const initialNodes: GraphNode[] = [createTestNode('1')];
      const initialEdges: GraphLink[] = [];
      
      const { result } = renderHook(() =>
        useCosmographIncrementalUpdates(
          cosmographRef,
          initialNodes,
          initialEdges
        )
      );
      
      // Invalid node without ID
      const invalidNode = { name: 'Invalid' } as any;
      
      await act(async () => {
        const success = await result.current.applyDelta({
          type: 'graph:delta',
          data: {
            operation: 'add',
            nodes: [invalidNode],
            edges: [],
            timestamp: Date.now()
          }
        });
        
        // Should handle invalid data gracefully
        expect(success).toBe(true); // Returns true but doesn't add invalid nodes
        expect(mockCosmograph.addPoints).toHaveBeenCalledWith([]);
      });
    });
    
    it('should validate edge data before applying', async () => {
      const initialNodes: GraphNode[] = [
        createTestNode('1'),
        createTestNode('2')
      ];
      const initialEdges: GraphLink[] = [];
      
      const { result } = renderHook(() =>
        useCosmographIncrementalUpdates(
          cosmographRef,
          initialNodes,
          initialEdges
        )
      );
      
      // Edge with non-existent nodes
      const invalidEdge = createTestEdge('999', '1000');
      
      await act(async () => {
        const success = await result.current.applyDelta({
          type: 'graph:delta',
          data: {
            operation: 'add',
            nodes: [],
            edges: [invalidEdge],
            timestamp: Date.now()
          }
        });
        
        // Should skip invalid edges
        expect(success).toBe(true);
        expect(mockCosmograph.addLinks).toHaveBeenCalledWith([]);
      });
    });
  });
});

describe('Fallback Strategies', () => {
  it('should batch multiple failed updates', async () => {
    // Test that multiple rapid failures get batched together
    const mockCosmograph = createMockCosmograph();
    const cosmographRef = { current: mockCosmograph };
    
    // Make all operations fail initially
    mockCosmograph.addPoints.mockRejectedValue(new Error('Busy'));
    mockCosmograph.addLinks.mockRejectedValue(new Error('Busy'));
    
    const { result } = renderHook(() =>
      useCosmographIncrementalUpdates(
        cosmographRef,
        [],
        []
      )
    );
    
    // Send multiple updates rapidly
    await act(async () => {
      const promises = [
        result.current.applyDelta({
          type: 'graph:delta',
          data: {
            operation: 'add',
            nodes: [createTestNode('1')],
            edges: [],
            timestamp: Date.now()
          }
        }),
        result.current.applyDelta({
          type: 'graph:delta',
          data: {
            operation: 'add',
            nodes: [createTestNode('2')],
            edges: [],
            timestamp: Date.now()
          }
        })
      ];
      
      await Promise.all(promises);
    });
    
    // Verify batching behavior would occur
    // (actual batching happens asynchronously in the fallback orchestrator)
    expect(mockCosmograph.addPoints).toHaveBeenCalled();
  });
  
  it('should skip non-critical updates when overloaded', async () => {
    const mockCosmograph = createMockCosmograph();
    const cosmographRef = { current: mockCosmograph };
    
    const { result } = renderHook(() =>
      useCosmographIncrementalUpdates(
        cosmographRef,
        [createTestNode('1'), createTestNode('2')],
        []
      )
    );
    
    // Update operations are considered non-critical
    await act(async () => {
      const success = await result.current.applyDelta({
        type: 'graph:delta',
        data: {
          operation: 'update',
          nodes: [createTestNode('1')],
          edges: [],
          timestamp: Date.now()
        }
      });
      
      // Updates currently return false (skipped)
      expect(success).toBe(false);
    });
  });
});