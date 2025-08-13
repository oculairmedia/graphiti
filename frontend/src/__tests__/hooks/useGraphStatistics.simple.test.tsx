/**
 * Simple unit test for useGraphStatistics hook to verify basic functionality
 */

import { describe, it, expect } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useGraphStatistics, useSimpleGraphStatistics } from '../../hooks/useGraphStatistics';
import { GraphNode } from '../../api/types';
import { GraphLink } from '../../types/graph';

describe('useGraphStatistics - Basic', () => {
  it('should initialize with empty data', () => {
    const { result } = renderHook(() => 
      useGraphStatistics([], [])
    );

    expect(result.current.statistics.nodeCount).toBe(0);
    expect(result.current.statistics.edgeCount).toBe(0);
    expect(result.current.isEmpty).toBe(true);
  });

  it('should provide basic stats getter', () => {
    const nodes: GraphNode[] = [
      { id: 'node1', name: 'Node 1', node_type: 'person' },
      { id: 'node2', name: 'Node 2', node_type: 'organization' },
    ];
    const links: GraphLink[] = [
      { source: 'node1', target: 'node2', weight: 1 },
    ];

    const { result } = renderHook(() => 
      useGraphStatistics(nodes, links, { updateThrottle: 0 })
    );

    const basicStats = result.current.getBasicStats();
    expect(basicStats.nodeCount).toBe(2);
    expect(basicStats.edgeCount).toBe(1);
    expect(basicStats.lastUpdated).toBeDefined();
  });

  it('should identify empty graph', () => {
    const { result } = renderHook(() => 
      useGraphStatistics([], [])
    );

    expect(result.current.isEmpty).toBe(true);
  });
});

describe('useSimpleGraphStatistics', () => {
  it('should return basic statistics', () => {
    const nodes: GraphNode[] = [
      { id: 'node1', name: 'Node 1', node_type: 'person' },
      { id: 'node2', name: 'Node 2', node_type: 'organization' },
    ];
    const links: GraphLink[] = [
      { source: 'node1', target: 'node2', weight: 1 },
    ];

    const { result } = renderHook(() => 
      useSimpleGraphStatistics(nodes, links)
    );

    expect(result.current.nodeCount).toBe(2);
    expect(result.current.edgeCount).toBe(1);
    expect(result.current.lastUpdated).toBeDefined();
  });
});