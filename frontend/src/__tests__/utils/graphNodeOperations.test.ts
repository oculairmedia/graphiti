/**
 * Unit tests for graph node operations
 */

import { describe, it, expect } from 'vitest';
import {
  transformNodeForCosmograph,
  transformNodesForCosmograph,
  filterValidNodes,
  createNodeIndexMap,
  getNodeById,
  getNodesByIds,
  getNodesByType,
  updateNodeInArray,
  updateNodesInArray,
  removeNodesFromArray,
  addNodesToArray,
  mergeNodeArrays,
  calculateNodeStats,
  sortNodesByCentrality,
  getTopNodesByCentrality,
  findNodesInTimeRange,
  groupNodesByProperty,
  calculateNodeDegrees,
  findIsolatedNodes,
  validateNode,
  validateNodes
} from '../../utils/graphNodeOperations';
import { GraphNode } from '../../api/types';

describe('Graph Node Operations', () => {
  const mockNodes: GraphNode[] = [
    { id: 'node1', name: 'Node 1', node_type: 'person', created_at: '2024-01-01', properties: { degree_centrality: 0.8 } },
    { id: 'node2', name: 'Node 2', node_type: 'organization', created_at: '2024-01-02', properties: { degree_centrality: 0.6 } },
    { id: 'node3', name: 'Node 3', node_type: 'location', created_at: '2024-01-03', properties: { degree_centrality: 0.4 } },
  ];

  const mockLinks = [
    { source: 'node1', target: 'node2', weight: 1 },
    { source: 'node2', target: 'node3', weight: 2 },
  ];

  describe('transformNodeForCosmograph', () => {
    it('should transform a node for Cosmograph', () => {
      const result = transformNodeForCosmograph(mockNodes[0], 0);
      
      expect(result).toEqual({
        id: 'node1',
        index: 0,
        label: 'Node 1',
        node_type: 'person',
        centrality: 0.8,
        cluster: 'person',
        clusterStrength: 0.7,
        degree_centrality: 0.8,
        pagerank_centrality: 0,
        betweenness_centrality: 0,
        eigenvector_centrality: 0,
        created_at: '2024-01-01',
        created_at_timestamp: null
      });
    });

    it('should handle missing properties', () => {
      const node: GraphNode = { id: 'test', name: 'Test', node_type: 'unknown' };
      const result = transformNodeForCosmograph(node, 5);
      
      expect(result.id).toBe('test');
      expect(result.index).toBe(5);
      expect(result.centrality).toBe(1);
      expect(result.degree_centrality).toBe(0);
    });
  });

  describe('filterValidNodes', () => {
    it('should filter out invalid nodes', () => {
      const nodes = [
        { id: 'valid1', name: 'Valid 1' },
        { id: 'undefined', name: 'Invalid' },
        { id: '', name: 'Empty ID' },
        { id: 'valid2', name: 'Valid 2' },
      ];

      const result = filterValidNodes(nodes);
      expect(result).toHaveLength(2);
      expect(result[0].id).toBe('valid1');
      expect(result[1].id).toBe('valid2');
    });
  });

  describe('createNodeIndexMap', () => {
    it('should create a map of node IDs to indices', () => {
      const transformed = transformNodesForCosmograph(mockNodes);
      const map = createNodeIndexMap(transformed);
      
      expect(map.get('node1')).toBe(0);
      expect(map.get('node2')).toBe(1);
      expect(map.get('node3')).toBe(2);
      expect(map.size).toBe(3);
    });
  });

  describe('getNodeById', () => {
    it('should find a node by ID', () => {
      const result = getNodeById(mockNodes, 'node2');
      expect(result?.name).toBe('Node 2');
    });

    it('should return undefined for non-existent ID', () => {
      const result = getNodeById(mockNodes, 'nonexistent');
      expect(result).toBeUndefined();
    });
  });

  describe('getNodesByType', () => {
    it('should filter nodes by type', () => {
      const result = getNodesByType(mockNodes, 'person');
      expect(result).toHaveLength(1);
      expect(result[0].id).toBe('node1');
    });

    it('should return empty array for non-existent type', () => {
      const result = getNodesByType(mockNodes, 'nonexistent');
      expect(result).toHaveLength(0);
    });
  });

  describe('updateNodeInArray', () => {
    it('should update a node immutably', () => {
      const updated: GraphNode = { ...mockNodes[0], name: 'Updated Node 1' };
      const result = updateNodeInArray(mockNodes, updated);
      
      expect(result[0].name).toBe('Updated Node 1');
      expect(result).not.toBe(mockNodes); // New array
      expect(mockNodes[0].name).toBe('Node 1'); // Original unchanged
    });
  });

  describe('removeNodesFromArray', () => {
    it('should remove nodes by ID', () => {
      const result = removeNodesFromArray(mockNodes, ['node2']);
      
      expect(result).toHaveLength(2);
      expect(result.find(n => n.id === 'node2')).toBeUndefined();
    });

    it('should handle multiple removals', () => {
      const result = removeNodesFromArray(mockNodes, ['node1', 'node3']);
      
      expect(result).toHaveLength(1);
      expect(result[0].id).toBe('node2');
    });
  });

  describe('addNodesToArray', () => {
    it('should add new nodes without duplicates', () => {
      const newNodes: GraphNode[] = [
        { id: 'node4', name: 'Node 4', node_type: 'event' },
        { id: 'node1', name: 'Duplicate', node_type: 'person' }, // Duplicate ID
      ];

      const result = addNodesToArray(mockNodes, newNodes);
      
      expect(result).toHaveLength(4);
      expect(result[3].id).toBe('node4');
      expect(result.filter(n => n.id === 'node1')).toHaveLength(1);
    });
  });

  describe('calculateNodeStats', () => {
    it('should calculate comprehensive node statistics', () => {
      const stats = calculateNodeStats(mockNodes);
      
      expect(stats.total).toBe(3);
      expect(stats.uniqueTypes).toBe(3);
      expect(stats.byType.get('person')).toBe(1);
      expect(stats.avgCentrality).toBeCloseTo(0.6, 1);
      expect(stats.maxCentrality).toBe(0.8);
      expect(stats.minCentrality).toBe(0.4);
    });

    it('should handle empty array', () => {
      const stats = calculateNodeStats([]);
      
      expect(stats.total).toBe(0);
      expect(stats.avgCentrality).toBe(0);
      expect(stats.minCentrality).toBe(0);
    });
  });

  describe('sortNodesByCentrality', () => {
    it('should sort nodes by centrality in descending order', () => {
      const result = sortNodesByCentrality(mockNodes, 'degree');
      
      expect(result[0].id).toBe('node1'); // Highest centrality
      expect(result[2].id).toBe('node3'); // Lowest centrality
    });
  });

  describe('calculateNodeDegrees', () => {
    it('should calculate node degrees from links', () => {
      const degrees = calculateNodeDegrees(mockNodes, mockLinks);
      
      expect(degrees.get('node1')).toBe(1);
      expect(degrees.get('node2')).toBe(2); // Connected to both node1 and node3
      expect(degrees.get('node3')).toBe(1);
    });
  });

  describe('findIsolatedNodes', () => {
    it('should find nodes with no connections', () => {
      const nodesWithIsolated = [
        ...mockNodes,
        { id: 'isolated', name: 'Isolated Node', node_type: 'unknown' }
      ];

      const isolated = findIsolatedNodes(nodesWithIsolated, mockLinks);
      
      expect(isolated).toHaveLength(1);
      expect(isolated[0].id).toBe('isolated');
    });
  });

  describe('validateNode', () => {
    it('should validate correct nodes', () => {
      expect(validateNode({ id: 'valid', name: 'Test' })).toBe(true);
    });

    it('should reject invalid nodes', () => {
      expect(validateNode(null)).toBe(false);
      expect(validateNode({ id: undefined })).toBe(false);
      expect(validateNode({ id: 'undefined' })).toBe(false);
      expect(validateNode({ id: 123 })).toBe(false);
    });
  });

  describe('groupNodesByProperty', () => {
    it('should group nodes by a property', () => {
      const groups = groupNodesByProperty(mockNodes, 'node_type');
      
      expect(groups.size).toBe(3);
      expect(groups.get('person')).toHaveLength(1);
      expect(groups.get('organization')).toHaveLength(1);
      expect(groups.get('location')).toHaveLength(1);
    });
  });
});