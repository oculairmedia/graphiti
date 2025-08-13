/**
 * Unit tests for useGraphSelection hook
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useGraphSelection, useSimpleSelection } from '../../hooks/useGraphSelection';
import { GraphNode } from '../../api/types';
import { GraphLink } from '../../types/graph';

describe('useGraphSelection', () => {
  const mockNodes: GraphNode[] = [
    { id: 'node1', name: 'Node 1', node_type: 'person' },
    { id: 'node2', name: 'Node 2', node_type: 'organization' },
    { id: 'node3', name: 'Node 3', node_type: 'location' },
  ];

  const mockLinks: GraphLink[] = [
    { source: 'node1', target: 'node2', edge_type: 'knows' },
    { source: 'node2', target: 'node3', edge_type: 'located_at' },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  describe('Basic selection', () => {
    it('should initialize with empty selection', () => {
      const { result } = renderHook(() => 
        useGraphSelection(mockNodes, mockLinks)
      );

      expect(result.current.selectedNodes.size).toBe(0);
      expect(result.current.selectedLinks.size).toBe(0);
      expect(result.current.hoveredNode).toBe(null);
    });

    it('should select a single node', () => {
      const { result } = renderHook(() => 
        useGraphSelection(mockNodes, mockLinks)
      );

      act(() => {
        result.current.selectNode('node1');
      });

      expect(result.current.selectedNodes.has('node1')).toBe(true);
      expect(result.current.selectedNodes.size).toBe(1);
    });

    it('should select multiple nodes in multiple mode', () => {
      const { result } = renderHook(() => 
        useGraphSelection(mockNodes, mockLinks, { mode: 'multiple' })
      );

      act(() => {
        result.current.selectNode('node1', true);
        result.current.selectNode('node2', true);
      });

      expect(result.current.selectedNodes.size).toBe(2);
      expect(result.current.selectedNodes.has('node1')).toBe(true);
      expect(result.current.selectedNodes.has('node2')).toBe(true);
    });

    it('should replace selection in single mode', () => {
      const { result } = renderHook(() => 
        useGraphSelection(mockNodes, mockLinks, { mode: 'single' })
      );

      act(() => {
        result.current.selectNode('node1');
        result.current.selectNode('node2');
      });

      expect(result.current.selectedNodes.size).toBe(1);
      expect(result.current.selectedNodes.has('node2')).toBe(true);
      expect(result.current.selectedNodes.has('node1')).toBe(false);
    });

    it('should respect max selection limit', () => {
      const { result } = renderHook(() => 
        useGraphSelection(mockNodes, mockLinks, { maxSelection: 2 })
      );

      act(() => {
        result.current.selectNodes(['node1', 'node2', 'node3']);
      });

      expect(result.current.selectedNodes.size).toBe(2);
    });
  });

  describe('Deselection', () => {
    it('should deselect a node', () => {
      const { result } = renderHook(() => 
        useGraphSelection(mockNodes, mockLinks)
      );

      act(() => {
        result.current.selectNodes(['node1', 'node2']);
        result.current.deselectNode('node1');
      });

      expect(result.current.selectedNodes.has('node1')).toBe(false);
      expect(result.current.selectedNodes.has('node2')).toBe(true);
    });

    it('should deselect multiple nodes', () => {
      const { result } = renderHook(() => 
        useGraphSelection(mockNodes, mockLinks)
      );

      act(() => {
        result.current.selectNodes(['node1', 'node2', 'node3']);
        result.current.deselectNodes(['node1', 'node3']);
      });

      expect(result.current.selectedNodes.size).toBe(1);
      expect(result.current.selectedNodes.has('node2')).toBe(true);
    });
  });

  describe('Toggle selection', () => {
    it('should toggle node selection', () => {
      const { result } = renderHook(() => 
        useGraphSelection(mockNodes, mockLinks)
      );

      act(() => {
        result.current.toggleNodeSelection('node1');
      });

      expect(result.current.selectedNodes.has('node1')).toBe(true);

      act(() => {
        result.current.toggleNodeSelection('node1');
      });

      expect(result.current.selectedNodes.has('node1')).toBe(false);
    });
  });

  describe('Clear selection', () => {
    it('should clear all selections', () => {
      const { result } = renderHook(() => 
        useGraphSelection(mockNodes, mockLinks)
      );

      act(() => {
        result.current.selectNodes(['node1', 'node2']);
        result.current.selectLink('link1');
        result.current.clearSelection();
      });

      expect(result.current.selectedNodes.size).toBe(0);
      expect(result.current.selectedLinks.size).toBe(0);
    });
  });

  describe('Select all', () => {
    it('should select all nodes', () => {
      const { result } = renderHook(() => 
        useGraphSelection(mockNodes, mockLinks)
      );

      act(() => {
        result.current.selectAllNodes();
      });

      expect(result.current.selectedNodes.size).toBe(3);
    });

    it('should respect max selection when selecting all', () => {
      const { result } = renderHook(() => 
        useGraphSelection(mockNodes, mockLinks, { maxSelection: 2 })
      );

      act(() => {
        result.current.selectAllNodes();
      });

      expect(result.current.selectedNodes.size).toBe(2);
    });
  });

  describe('Invert selection', () => {
    it('should invert node selection', () => {
      const { result } = renderHook(() => 
        useGraphSelection(mockNodes, mockLinks)
      );

      act(() => {
        result.current.selectNode('node1');
      });
      
      // Verify initial selection
      expect(result.current.selectedNodes.has('node1')).toBe(true);
      expect(result.current.selectedNodes.size).toBe(1);

      act(() => {
        result.current.invertSelection();
      });

      // After inversion, node1 should be deselected, node2 and node3 selected
      expect(result.current.selectedNodes.has('node1')).toBe(false);
      expect(result.current.selectedNodes.has('node2')).toBe(true);
      expect(result.current.selectedNodes.has('node3')).toBe(true);
      expect(result.current.selectedNodes.size).toBe(2);
    });
  });

  describe('Connected nodes selection', () => {
    it('should select connected nodes', () => {
      const { result } = renderHook(() => 
        useGraphSelection(mockNodes, mockLinks)
      );

      act(() => {
        result.current.selectConnectedNodes('node2', 1);
      });

      // node2 is connected to node1 and node3
      expect(result.current.selectedNodes.size).toBe(3);
      expect(result.current.selectedNodes.has('node1')).toBe(true);
      expect(result.current.selectedNodes.has('node2')).toBe(true);
      expect(result.current.selectedNodes.has('node3')).toBe(true);
    });
  });

  describe('Select by type', () => {
    it('should select nodes by type', () => {
      const { result } = renderHook(() => 
        useGraphSelection(mockNodes, mockLinks)
      );

      act(() => {
        result.current.selectNodesByType('person');
      });

      expect(result.current.selectedNodes.size).toBe(1);
      expect(result.current.selectedNodes.has('node1')).toBe(true);
    });
  });

  describe('Hover state', () => {
    it('should set hovered node', () => {
      const { result } = renderHook(() => 
        useGraphSelection(mockNodes, mockLinks)
      );

      act(() => {
        result.current.setHoveredNode('node1');
      });

      expect(result.current.hoveredNode).toBe('node1');
    });

    it('should trigger hover change callback', () => {
      const onHoverChange = vi.fn();
      const { result } = renderHook(() => 
        useGraphSelection(mockNodes, mockLinks, { onHoverChange })
      );

      act(() => {
        result.current.setHoveredNode('node1');
      });

      expect(onHoverChange).toHaveBeenCalledWith('node1', null);
    });
  });

  describe('Utility functions', () => {
    it('should check if node is selected', () => {
      const { result } = renderHook(() => 
        useGraphSelection(mockNodes, mockLinks)
      );

      act(() => {
        result.current.selectNode('node1');
      });

      expect(result.current.isNodeSelected('node1')).toBe(true);
      expect(result.current.isNodeSelected('node2')).toBe(false);
    });

    it('should get selected nodes', () => {
      const { result } = renderHook(() => 
        useGraphSelection(mockNodes, mockLinks)
      );

      act(() => {
        result.current.selectNodes(['node1', 'node3']);
      });

      const selected = result.current.getSelectedNodes();
      expect(selected).toHaveLength(2);
      expect(selected[0].id).toBe('node1');
      expect(selected[1].id).toBe('node3');
    });

    it('should get selection statistics', () => {
      const { result } = renderHook(() => 
        useGraphSelection(mockNodes, mockLinks)
      );

      act(() => {
        result.current.selectNodes(['node1', 'node2']);
      });

      const stats = result.current.getSelectionStats();
      expect(stats.selectedNodeCount).toBe(2);
      expect(stats.hasSelection).toBe(true);
      expect(stats.isMaxed).toBe(false);
    });
  });

  describe('Persistence', () => {
    it('should persist selection to localStorage', () => {
      const { result } = renderHook(() => 
        useGraphSelection(mockNodes, mockLinks, { 
          persistSelection: true,
          storageKey: 'test-selection'
        })
      );

      act(() => {
        result.current.selectNode('node1');
      });

      const saved = localStorage.getItem('test-selection');
      expect(saved).toBeTruthy();
      const parsed = JSON.parse(saved!);
      expect(parsed.selectedNodes).toContain('node1');
    });
  });

  describe('Callbacks', () => {
    it('should trigger selection change callback', () => {
      const onSelectionChange = vi.fn();
      const { result } = renderHook(() => 
        useGraphSelection(mockNodes, mockLinks, { onSelectionChange })
      );

      act(() => {
        result.current.selectNode('node1');
      });

      expect(onSelectionChange).toHaveBeenCalledWith(
        expect.objectContaining({
          type: 'select',
          target: 'node',
          ids: ['node1']
        })
      );
    });
  });
});

describe('useSimpleSelection', () => {
  it('should handle basic selection operations', () => {
    const { result } = renderHook(() => useSimpleSelection());

    expect(result.current.selectedIds.size).toBe(0);

    act(() => {
      result.current.select('item1');
    });

    expect(result.current.isSelected('item1')).toBe(true);

    act(() => {
      result.current.toggle('item2');
    });

    expect(result.current.isSelected('item2')).toBe(true);

    act(() => {
      result.current.toggle('item2');
    });

    expect(result.current.isSelected('item2')).toBe(false);

    act(() => {
      result.current.deselect('item1');
    });

    expect(result.current.isSelected('item1')).toBe(false);

    act(() => {
      result.current.select('item3');
      result.current.clear();
    });

    expect(result.current.selectedIds.size).toBe(0);
  });
});