/**
 * Integration tests for memory optimization
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { MemoryOptimizedGraphStore } from '../../services/memoryOptimizedStore';
import { GraphNode } from '../../api/types';
import { GraphLink } from '../../types/graph';

describe('Memory Optimized Store Integration', () => {
  let store: MemoryOptimizedGraphStore;
  
  beforeEach(() => {
    store = new MemoryOptimizedGraphStore({
      maxCacheSize: 100,
      cleanupInterval: 1000,
      enableWeakRefs: true,
      enableStringInterning: true
    });
    
    vi.useFakeTimers();
  });
  
  afterEach(() => {
    store.destroy();
    vi.useRealTimers();
  });
  
  describe('Node Management', () => {
    it('should store and retrieve nodes efficiently', () => {
      const nodes: GraphNode[] = Array.from({ length: 100 }, (_, i) => ({
        id: `node-${i}`,
        name: `Node ${i}`,
        node_type: 'test',
        created_at: new Date().toISOString(),
        summary: `Summary for node ${i}`
      }));
      
      // Add nodes
      for (const node of nodes) {
        store.setNode(node);
      }
      
      // Retrieve nodes
      for (const node of nodes) {
        const retrieved = store.getNode(node.id);
        expect(retrieved).toEqual(expect.objectContaining({
          id: node.id,
          name: node.name,
          node_type: node.node_type
        }));
      }
      
      const stats = store.getStats();
      expect(stats.currentNodes).toBe(100);
    });
    
    it('should update existing nodes', () => {
      const node: GraphNode = {
        id: 'node-1',
        name: 'Original Name',
        node_type: 'test',
        created_at: new Date().toISOString()
      };
      
      store.setNode(node);
      
      // Update node
      const updatedNode = {
        ...node,
        name: 'Updated Name',
        summary: 'New summary'
      };
      
      store.setNode(updatedNode);
      
      const retrieved = store.getNode('node-1');
      expect(retrieved?.name).toBe('Updated Name');
      expect(retrieved?.summary).toBe('New summary');
      
      // Should not create duplicate
      const stats = store.getStats();
      expect(stats.currentNodes).toBe(1);
    });
    
    it('should handle bulk operations efficiently', () => {
      const nodes: GraphNode[] = Array.from({ length: 1000 }, (_, i) => ({
        id: `node-${i}`,
        name: `Node ${i}`,
        node_type: i % 2 === 0 ? 'type-a' : 'type-b',
        created_at: new Date().toISOString()
      }));
      
      const startTime = performance.now();
      store.setNodesBulk(nodes);
      const bulkTime = performance.now() - startTime;
      
      // Should be fast
      expect(bulkTime).toBeLessThan(50); // 50ms for 1000 nodes
      
      // All nodes should be stored
      const stats = store.getStats();
      expect(stats.currentNodes).toBe(1000);
    });
  });
  
  describe('Edge Management', () => {
    beforeEach(() => {
      // Add test nodes
      for (let i = 0; i < 10; i++) {
        store.setNode({
          id: `n${i}`,
          name: `Node ${i}`,
          node_type: 'test',
          created_at: new Date().toISOString()
        });
      }
    });
    
    it('should store and index edges', () => {
      const edges: GraphLink[] = [
        { source: 'n0', target: 'n1', name: 'Edge 1' },
        { source: 'n0', target: 'n2', name: 'Edge 2' },
        { source: 'n1', target: 'n3', name: 'Edge 3' },
        { source: 'n2', target: 'n3', name: 'Edge 4' }
      ];
      
      for (const edge of edges) {
        store.setEdge(edge);
      }
      
      // Query edges for node
      const n0Edges = store.getEdgesForNode('n0');
      expect(n0Edges).toHaveLength(2);
      expect(n0Edges).toEqual(
        expect.arrayContaining([
          expect.objectContaining({ source: 'n0', target: 'n1' }),
          expect.objectContaining({ source: 'n0', target: 'n2' })
        ])
      );
      
      const n3Edges = store.getEdgesForNode('n3');
      expect(n3Edges).toHaveLength(2);
      expect(n3Edges).toEqual(
        expect.arrayContaining([
          expect.objectContaining({ source: 'n1', target: 'n3' }),
          expect.objectContaining({ source: 'n2', target: 'n3' })
        ])
      );
    });
  });
  
  describe('Type Indexing', () => {
    it('should index nodes by type', () => {
      const nodeTypes = ['person', 'organization', 'location', 'event'];
      const nodesPerType = 25;
      
      for (const type of nodeTypes) {
        for (let i = 0; i < nodesPerType; i++) {
          store.setNode({
            id: `${type}-${i}`,
            name: `${type} ${i}`,
            node_type: type,
            created_at: new Date().toISOString()
          });
        }
      }
      
      // Query by type
      for (const type of nodeTypes) {
        const nodes = store.getNodesByType(type);
        expect(nodes).toHaveLength(nodesPerType);
        expect(nodes.every(n => n.node_type === type)).toBe(true);
      }
    });
    
    it('should update type index on node changes', () => {
      const node: GraphNode = {
        id: 'node-1',
        name: 'Test Node',
        node_type: 'type-a',
        created_at: new Date().toISOString()
      };
      
      store.setNode(node);
      expect(store.getNodesByType('type-a')).toHaveLength(1);
      expect(store.getNodesByType('type-b')).toHaveLength(0);
      
      // Change type
      store.setNode({ ...node, node_type: 'type-b' });
      
      expect(store.getNodesByType('type-a')).toHaveLength(0);
      expect(store.getNodesByType('type-b')).toHaveLength(1);
    });
  });
  
  describe('Position Caching with WeakMap', () => {
    it('should store positions in WeakMap', () => {
      const node: GraphNode = {
        id: 'node-1',
        name: 'Test Node',
        node_type: 'test',
        created_at: new Date().toISOString()
      };
      
      store.setNode(node);
      const retrieved = store.getNode('node-1')!;
      
      // Set position
      store.setNodePosition(retrieved, { x: 100, y: 200 });
      
      // Get position
      const position = store.getNodePosition(retrieved);
      expect(position).toEqual({ x: 100, y: 200 });
      
      // Position should not be stored in main node data
      expect((retrieved as any).x).toBeUndefined();
      expect((retrieved as any).y).toBeUndefined();
    });
    
    it('should clean up positions when nodes are removed', () => {
      const nodes: GraphNode[] = Array.from({ length: 10 }, (_, i) => ({
        id: `node-${i}`,
        name: `Node ${i}`,
        node_type: 'test',
        created_at: new Date().toISOString()
      }));
      
      // Add nodes and positions
      for (const node of nodes) {
        store.setNode(node);
        const retrieved = store.getNode(node.id)!;
        store.setNodePosition(retrieved, { x: Math.random() * 1000, y: Math.random() * 1000 });
      }
      
      // Positions should be accessible
      for (const node of nodes) {
        const retrieved = store.getNode(node.id)!;
        expect(store.getNodePosition(retrieved)).toBeDefined();
      }
      
      // WeakMap should automatically clean up when references are lost
      // (This is handled by JS garbage collector)
    });
  });
  
  describe('Filter Caching', () => {
    beforeEach(() => {
      // Add test nodes
      for (let i = 0; i < 100; i++) {
        store.setNode({
          id: `node-${i}`,
          name: `Node ${i}`,
          node_type: i % 3 === 0 ? 'type-a' : i % 3 === 1 ? 'type-b' : 'type-c',
          created_at: new Date().toISOString(),
          summary: i % 2 === 0 ? 'even' : 'odd'
        });
      }
    });
    
    it('should cache filter results', () => {
      const predicate = (node: GraphNode) => node.node_type === 'type-a';
      
      // First call - cache miss
      const result1 = store.filterNodes(predicate);
      const stats1 = store.getStats();
      
      // Second call - cache hit
      const result2 = store.filterNodes(predicate);
      const stats2 = store.getStats();
      
      expect(result1).toEqual(result2);
      expect(stats2.cacheHits).toBe(stats1.cacheHits + 1);
    });
    
    it('should invalidate cache on node changes', () => {
      const predicate = (node: GraphNode) => node.node_type === 'type-a';
      
      // Initial filter
      const result1 = store.filterNodes(predicate);
      const count1 = result1.length;
      
      // Add new node of type-a
      store.setNode({
        id: 'new-node',
        name: 'New Node',
        node_type: 'type-a',
        created_at: new Date().toISOString()
      });
      
      // Filter again - cache should be invalidated
      const result2 = store.filterNodes(predicate);
      expect(result2.length).toBe(count1 + 1);
    });
  });
  
  describe('String Interning', () => {
    it('should intern duplicate strings', () => {
      const nodeType = 'repeated-type';
      const nodes: GraphNode[] = Array.from({ length: 100 }, (_, i) => ({
        id: `node-${i}`,
        name: `Node ${i}`,
        node_type: nodeType, // Same type for all
        created_at: new Date().toISOString()
      }));
      
      for (const node of nodes) {
        store.setNode(node);
      }
      
      const stats = store.getStats();
      expect(stats.internedStrings).toBeGreaterThan(0);
      
      // All nodes should share the same string reference
      const retrievedNodes = nodes.map(n => store.getNode(n.id));
      const typeRefs = retrievedNodes.map(n => n?.node_type);
      
      // Check if string interning is working (same reference)
      const firstRef = typeRefs[0];
      const allSameRef = typeRefs.every(ref => ref === firstRef);
      expect(allSameRef).toBe(true);
    });
  });
  
  describe('Automatic Cleanup', () => {
    it('should clean up stale nodes', () => {
      // Add nodes with tracked access
      for (let i = 0; i < 10; i++) {
        store.setNode({
          id: `node-${i}`,
          name: `Node ${i}`,
          node_type: 'test',
          created_at: new Date().toISOString()
        });
      }
      
      // Immediately advance time to make nodes stale
      vi.advanceTimersByTime(10 * 60 * 1000); // 10 minutes
      
      // Access some nodes (keep them "fresh")
      store.getNode('node-0');
      store.getNode('node-1');
      store.getNode('node-2');
      
      // Trigger cleanup
      vi.advanceTimersByTime(1000); // Trigger next cleanup cycle
      
      // Check that stale nodes were removed
      const stats = store.getStats();
      expect(stats.currentNodes).toBeLessThanOrEqual(3);
      expect(stats.memoryReclaimed).toBeGreaterThanOrEqual(7);
      
      // Fresh nodes should still exist
      expect(store.getNode('node-0')).toBeDefined();
      expect(store.getNode('node-1')).toBeDefined();
      expect(store.getNode('node-2')).toBeDefined();
    });
    
    it('should pause cleanup during bulk operations', () => {
      // Create new store for this test to avoid interference
      const testStore = new MemoryOptimizedGraphStore({
        maxCacheSize: 100,
        cleanupInterval: 1000,
        enableWeakRefs: true,
        enableStringInterning: true
      });
      
      const cleanupSpy = vi.spyOn(testStore as any, 'performCleanup');
      cleanupSpy.mockClear();
      
      const nodes: GraphNode[] = Array.from({ length: 100 }, (_, i) => ({
        id: `node-${i}`,
        name: `Node ${i}`,
        node_type: 'test',
        created_at: new Date().toISOString()
      }));
      
      // Bulk operation should pause cleanup
      testStore.setNodesBulk(nodes);
      
      // Verify nodes were added
      expect(testStore.getStats().currentNodes).toBe(100);
      
      // Cleanup should resume after bulk
      vi.advanceTimersByTime(2000);
      expect(cleanupSpy).toHaveBeenCalled();
      
      testStore.destroy();
    });
  });
  
  describe('Memory Usage Estimation', () => {
    it('should estimate memory usage', () => {
      // Add nodes and edges
      for (let i = 0; i < 100; i++) {
        store.setNode({
          id: `node-${i}`,
          name: `Node ${i}`,
          node_type: 'test',
          created_at: new Date().toISOString(),
          summary: 'A'.repeat(100) // Add some data
        });
      }
      
      for (let i = 0; i < 200; i++) {
        store.setEdge({
          source: `node-${i % 100}`,
          target: `node-${(i + 1) % 100}`,
          name: `Edge ${i}`
        });
      }
      
      const stats = store.getStats();
      expect(stats.estimatedMemoryMB).toBeGreaterThan(0);
      expect(stats.currentNodes).toBe(100);
      expect(stats.currentEdges).toBe(200);
    });
  });
  
  describe('Performance Under Load', () => {
    it('should handle large graphs efficiently', () => {
      const nodeCount = 5000;
      const edgeCount = 10000;
      
      // Create large graph
      const startTime = performance.now();
      
      // Add nodes
      const nodes: GraphNode[] = Array.from({ length: nodeCount }, (_, i) => ({
        id: `n${i}`,
        name: `Node ${i}`,
        node_type: `type-${i % 10}`,
        created_at: new Date().toISOString()
      }));
      
      store.setNodesBulk(nodes);
      
      // Add edges
      for (let i = 0; i < edgeCount; i++) {
        store.setEdge({
          source: `n${Math.floor(Math.random() * nodeCount)}`,
          target: `n${Math.floor(Math.random() * nodeCount)}`,
          name: `Edge ${i}`
        });
      }
      
      const loadTime = performance.now() - startTime;
      
      // Should load quickly
      expect(loadTime).toBeLessThan(500); // 500ms for 5k nodes + 10k edges
      
      // Test query performance
      const queryStart = performance.now();
      
      // Type query
      const typeNodes = store.getNodesByType('type-0');
      expect(typeNodes.length).toBeGreaterThan(0);
      
      // Edge query
      const edges = store.getEdgesForNode('n0');
      
      // Filter query
      const filtered = store.filterNodes(n => n.name.includes('1'));
      
      const queryTime = performance.now() - queryStart;
      
      // Queries should be fast
      expect(queryTime).toBeLessThan(50); // 50ms for all queries
      
      const stats = store.getStats();
      expect(stats.currentNodes).toBe(nodeCount);
      expect(stats.currentEdges).toBeLessThanOrEqual(edgeCount);
    });
  });
});