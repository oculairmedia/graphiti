/**
 * Unit tests for useGraphDataManagement hook
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useGraphDataManagement, useSimpleGraphData } from '../../hooks/useGraphDataManagement';
import { GraphNode } from '../../api/types';
import { GraphLink } from '../../types/graph';

describe('useGraphDataManagement', () => {
  const mockNodes: GraphNode[] = [
    { id: 'node1', name: 'Node 1', node_type: 'person' },
    { id: 'node2', name: 'Node 2', node_type: 'organization' },
  ];

  const mockLinks: GraphLink[] = [
    { source: 'node1', target: 'node2', edge_type: 'knows', weight: 1 },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Initialization', () => {
    it('should initialize with provided data', () => {
      const { result } = renderHook(() => 
        useGraphDataManagement({
          initialNodes: mockNodes,
          initialLinks: mockLinks
        })
      );

      expect(result.current.nodes).toEqual(mockNodes);
      expect(result.current.links).toEqual(mockLinks);
      expect(result.current.loading).toBe(false);
      expect(result.current.error).toBe(null);
    });

    it('should initialize with empty data', () => {
      const { result } = renderHook(() => useGraphDataManagement());

      expect(result.current.nodes).toEqual([]);
      expect(result.current.links).toEqual([]);
    });
  });

  describe('Node operations', () => {
    it('should add nodes', () => {
      const { result } = renderHook(() => useGraphDataManagement());

      act(() => {
        result.current.addNodes(mockNodes);
      });

      expect(result.current.nodes).toEqual(mockNodes);
      expect(result.current.updateCount).toBe(1);
    });

    it('should deduplicate nodes when autoDedup is enabled', () => {
      const { result } = renderHook(() => 
        useGraphDataManagement({
          initialNodes: [mockNodes[0]],
          autoDedup: true
        })
      );

      act(() => {
        result.current.addNodes(mockNodes);
      });

      expect(result.current.nodes).toHaveLength(2);
    });

    it('should update existing nodes', () => {
      const { result } = renderHook(() => 
        useGraphDataManagement({ initialNodes: mockNodes })
      );

      const updatedNode: GraphNode = { ...mockNodes[0], name: 'Updated Node 1' };

      act(() => {
        result.current.updateNodes([updatedNode]);
      });

      expect(result.current.nodes[0].name).toBe('Updated Node 1');
    });

    it('should remove nodes and their links', () => {
      const { result } = renderHook(() => 
        useGraphDataManagement({
          initialNodes: mockNodes,
          initialLinks: mockLinks
        })
      );

      act(() => {
        result.current.removeNodes(['node1']);
      });

      expect(result.current.nodes).toHaveLength(1);
      expect(result.current.nodes[0].id).toBe('node2');
      expect(result.current.links).toHaveLength(0); // Link should be removed
    });
  });

  describe('Link operations', () => {
    it('should add links', () => {
      const { result } = renderHook(() => 
        useGraphDataManagement({ initialNodes: mockNodes })
      );

      act(() => {
        result.current.addLinks(mockLinks);
      });

      expect(result.current.links).toEqual(mockLinks);
    });

    it('should filter invalid links', () => {
      const { result } = renderHook(() => 
        useGraphDataManagement({ initialNodes: [mockNodes[0]] })
      );

      act(() => {
        result.current.addLinks(mockLinks);
      });

      // Should filter out link because node2 doesn't exist
      expect(result.current.links).toHaveLength(0);
    });

    it('should update existing links', () => {
      const { result } = renderHook(() => 
        useGraphDataManagement({
          initialNodes: mockNodes,
          initialLinks: mockLinks
        })
      );

      const updatedLink: GraphLink = { ...mockLinks[0], weight: 5 };

      act(() => {
        result.current.updateLinks([updatedLink]);
      });

      expect(result.current.links[0].weight).toBe(5);
    });

    it('should remove links', () => {
      const { result } = renderHook(() => 
        useGraphDataManagement({
          initialNodes: mockNodes,
          initialLinks: mockLinks
        })
      );

      act(() => {
        result.current.removeLinks(mockLinks);
      });

      expect(result.current.links).toHaveLength(0);
    });
  });

  describe('Data management', () => {
    it('should reset data', () => {
      const { result } = renderHook(() => 
        useGraphDataManagement({
          initialNodes: mockNodes,
          initialLinks: mockLinks
        })
      );

      const newNodes: GraphNode[] = [
        { id: 'node3', name: 'Node 3', node_type: 'location' }
      ];
      const newLinks: GraphLink[] = [];

      act(() => {
        result.current.resetData(newNodes, newLinks);
      });

      expect(result.current.nodes).toEqual(newNodes);
      expect(result.current.links).toEqual(newLinks);
    });

    it('should clear all data', () => {
      const { result } = renderHook(() => 
        useGraphDataManagement({
          initialNodes: mockNodes,
          initialLinks: mockLinks
        })
      );

      act(() => {
        result.current.clearData();
      });

      expect(result.current.nodes).toHaveLength(0);
      expect(result.current.links).toHaveLength(0);
    });

    it('should handle batch updates', () => {
      const { result } = renderHook(() => 
        useGraphDataManagement({
          initialNodes: [mockNodes[0]]
        })
      );

      act(() => {
        result.current.batchUpdate([
          { type: 'add', target: 'nodes', data: [mockNodes[1]] },
          { type: 'add', target: 'links', data: mockLinks }
        ]);
      });

      expect(result.current.nodes).toHaveLength(2);
      expect(result.current.links).toHaveLength(1);
    });
  });

  describe('Callbacks', () => {
    it('should trigger onDataUpdate callback', () => {
      const onDataUpdate = vi.fn();
      const { result } = renderHook(() => 
        useGraphDataManagement({ onDataUpdate })
      );

      act(() => {
        result.current.addNodes(mockNodes);
      });

      expect(onDataUpdate).toHaveBeenCalledWith(
        expect.objectContaining({
          type: 'add',
          nodes: mockNodes,
          source: 'manual'
        })
      );
    });

    it('should trigger onError callback', async () => {
      const onError = vi.fn();
      global.fetch = vi.fn(() => Promise.reject(new Error('Network error')));

      const { result } = renderHook(() => 
        useGraphDataManagement({
          dataSource: { endpoint: 'http://test.com/data' },
          onError
        })
      );

      await act(async () => {
        await result.current.fetchData();
      });

      expect(onError).toHaveBeenCalledWith(expect.any(Error));
    });
  });

  describe('Statistics', () => {
    it('should return data statistics', () => {
      const { result } = renderHook(() => 
        useGraphDataManagement({
          initialNodes: mockNodes,
          initialLinks: mockLinks
        })
      );

      const stats = result.current.getDataStats();

      expect(stats.nodeCount).toBe(2);
      expect(stats.linkCount).toBe(1);
      expect(stats.updateCount).toBe(0);
      expect(stats.cacheSize).toBe(0);
      expect(stats.pendingOps).toBe(0);
    });
  });
});

describe('useSimpleGraphData', () => {
  const mockNodes: GraphNode[] = [
    { id: 'node1', name: 'Node 1', node_type: 'person' },
  ];

  const mockLinks: GraphLink[] = [
    { source: 'node1', target: 'node2', weight: 1 },
  ];

  it('should initialize with provided data', () => {
    const { result } = renderHook(() => 
      useSimpleGraphData(mockNodes, mockLinks)
    );

    expect(result.current.nodes).toEqual(mockNodes);
    expect(result.current.links).toEqual(mockLinks);
  });

  it('should update data', () => {
    const { result } = renderHook(() => useSimpleGraphData());

    act(() => {
      result.current.updateData(mockNodes, mockLinks);
    });

    expect(result.current.nodes).toEqual(mockNodes);
    expect(result.current.links).toEqual(mockLinks);
  });
});