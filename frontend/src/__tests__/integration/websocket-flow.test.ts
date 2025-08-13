/**
 * Integration tests for WebSocket notification flow
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { GraphDelta, DeltaType } from '../../types/delta';

// Mock implementations for testing
class WebSocketManager {
  private ws: MockWebSocket | null = null;
  private listeners = new Map<string, Set<Function>>();
  private connected = false;
  
  constructor(private url: string) {}
  
  connect() {
    this.ws = new MockWebSocket(this.url) as any;
    this.ws.onopen = () => {
      this.connected = true;
      this.emit('connected');
    };
    this.ws.onclose = () => {
      this.connected = false;
      this.emit('disconnected');
      // Auto-reconnect after delay
      setTimeout(() => {
        this.connect();
        this.emit('reconnected');
      }, 2000);
    };
    this.ws.onmessage = (event: MessageEvent) => {
      const data = JSON.parse(event.data);
      this.emit('notification', data);
    };
  }
  
  disconnect() {
    this.ws?.close();
    this.connected = false;
  }
  
  isConnected() {
    return this.connected;
  }
  
  on(event: string, callback: Function) {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, new Set());
    }
    this.listeners.get(event)!.add(callback);
  }
  
  private emit(event: string, data?: any) {
    const callbacks = this.listeners.get(event);
    if (callbacks) {
      callbacks.forEach(cb => cb(data));
    }
  }
}

class VersionSyncManager {
  constructor(private apiUrl: string) {}
  
  async fetchChangesSince(sinceSequence: number): Promise<GraphDelta[]> {
    const response = await fetch(
      `${this.apiUrl}/api/graph/changes?since=${sinceSequence}&limit=100`
    );
    return response.json();
  }
}

class IncrementalUpdatePipeline {
  private subscribers = new Set<Function>();
  private pendingOps = new Map<string, any>();
  private flushTimer: NodeJS.Timeout | null = null;
  
  subscribe(callback: Function) {
    this.subscribers.add(callback);
  }
  
  processDelta(delta: GraphDelta) {
    // Process added nodes
    if (delta.added_nodes) {
      for (const node of delta.added_nodes) {
        this.pendingOps.set(`node-${node.id}`, {
          type: 'add',
          entity: 'node',
          data: node
        });
      }
    }
    
    // Process updated nodes
    if (delta.updated_nodes) {
      for (const node of delta.updated_nodes) {
        const existing = this.pendingOps.get(`node-${node.id}`);
        if (existing && existing.type === 'add') {
          // Merge update into add
          existing.data = { ...existing.data, ...node };
        } else {
          this.pendingOps.set(`node-${node.id}`, {
            type: 'update',
            entity: 'node',
            data: node
          });
        }
      }
    }
    
    // Process removed nodes
    if (delta.removed_nodes) {
      for (const nodeId of delta.removed_nodes) {
        const existing = this.pendingOps.get(`node-${nodeId}`);
        if (existing) {
          // Remove any pending ops for this node
          this.pendingOps.delete(`node-${nodeId}`);
        }
        this.pendingOps.set(`node-${nodeId}`, {
          type: 'remove',
          entity: 'node',
          data: nodeId
        });
      }
    }
    
    // Process edges similarly
    if (delta.added_edges) {
      for (const edge of delta.added_edges) {
        this.pendingOps.set(`edge-${edge.source}-${edge.target}`, {
          type: 'add',
          entity: 'edge',
          data: edge
        });
      }
    }
    
    // Schedule flush
    if (!this.flushTimer) {
      this.flushTimer = setTimeout(() => this.flush(), 50);
    }
  }
  
  private flush() {
    const update = {
      nodes: {
        added: [] as any[],
        updated: [] as any[],
        removed: [] as string[]
      },
      edges: {
        added: [] as any[],
        updated: [] as any[],
        removed: [] as string[]
      }
    };
    
    for (const op of this.pendingOps.values()) {
      if (op.entity === 'node') {
        if (op.type === 'add') {
          update.nodes.added.push(op.data);
        } else if (op.type === 'update') {
          update.nodes.updated.push(op.data);
        } else if (op.type === 'remove') {
          update.nodes.removed.push(op.data);
        }
      } else if (op.entity === 'edge') {
        if (op.type === 'add') {
          update.edges.added.push(op.data);
        } else if (op.type === 'update') {
          update.edges.updated.push(op.data);
        } else if (op.type === 'remove') {
          update.edges.removed.push(op.data);
        }
      }
    }
    
    this.pendingOps.clear();
    this.flushTimer = null;
    
    for (const subscriber of this.subscribers) {
      subscriber(update);
    }
  }
  
  destroy() {
    if (this.flushTimer) {
      clearTimeout(this.flushTimer);
    }
    this.pendingOps.clear();
    this.subscribers.clear();
  }
}

// Mock WebSocket
class MockWebSocket {
  url: string;
  readyState: number = 0;
  onopen?: (event: Event) => void;
  onmessage?: (event: MessageEvent) => void;
  onclose?: (event: CloseEvent) => void;
  onerror?: (event: Event) => void;
  
  constructor(url: string) {
    this.url = url;
    setTimeout(() => {
      this.readyState = 1;
      this.onopen?.(new Event('open'));
    }, 0);
  }
  
  send(data: string) {
    // Mock send
  }
  
  close() {
    this.readyState = 3;
    this.onclose?.(new CloseEvent('close'));
  }
  
  simulateMessage(data: any) {
    this.onmessage?.(new MessageEvent('message', { data: JSON.stringify(data) }));
  }
}

// Mock fetch
const mockFetch = vi.fn();
global.fetch = mockFetch;

describe('WebSocket Integration Flow', () => {
  let wsManager: WebSocketManager;
  let versionSync: VersionSyncManager;
  let pipeline: IncrementalUpdatePipeline;
  let mockWs: MockWebSocket;
  
  beforeEach(() => {
    // @ts-ignore
    global.WebSocket = MockWebSocket;
    
    wsManager = new WebSocketManager('ws://localhost:3000');
    versionSync = new VersionSyncManager('http://localhost:3000');
    pipeline = new IncrementalUpdatePipeline();
    
    // Reset mocks
    mockFetch.mockReset();
    vi.clearAllTimers();
    vi.useFakeTimers();
  });
  
  afterEach(() => {
    wsManager.disconnect();
    pipeline.destroy();
    vi.useRealTimers();
  });
  
  describe('Connection and Initialization', () => {
    it('should establish WebSocket connection', async () => {
      const onConnect = vi.fn();
      wsManager.on('connected', onConnect);
      
      wsManager.connect();
      await vi.runOnlyPendingTimersAsync();
      
      expect(onConnect).toHaveBeenCalled();
      expect(wsManager.isConnected()).toBe(true);
    });
    
    it('should sync initial version on connection', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ sequence: 100, timestamp: Date.now() })
      });
      
      wsManager.connect();
      await vi.runOnlyPendingTimersAsync();
      
      // Should fetch current version
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/graph/version')
      );
    });
    
    it('should handle reconnection with version sync', async () => {
      const onReconnect = vi.fn();
      wsManager.on('reconnected', onReconnect);
      
      wsManager.connect();
      await vi.runOnlyPendingTimersAsync();
      
      // Simulate disconnect
      mockWs = wsManager['ws'] as any;
      mockWs.close();
      
      // Mock version for reconnect
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ sequence: 150, timestamp: Date.now() })
      });
      
      // Wait for reconnect
      await vi.advanceTimersByTimeAsync(2000);
      
      expect(onReconnect).toHaveBeenCalled();
      expect(mockFetch).toHaveBeenCalledTimes(2); // Initial + reconnect
    });
  });
  
  describe('Notification Processing', () => {
    beforeEach(async () => {
      wsManager.connect();
      await vi.runOnlyPendingTimersAsync();
      mockWs = wsManager['ws'] as any;
    });
    
    it('should trigger data fetch on graph_updated notification', async () => {
      const onNotification = vi.fn();
      wsManager.on('notification', onNotification);
      
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ([
          {
            sequence: 101,
            timestamp: Date.now(),
            type: 'incremental' as DeltaType,
            added_nodes: [{ id: 'node1', name: 'Node 1' }],
            added_edges: [],
            updated_nodes: [],
            updated_edges: [],
            removed_nodes: [],
            removed_edges: []
          }
        ])
      });
      
      // Simulate notification
      mockWs.simulateMessage({
        type: 'graph_updated',
        data: { sequence: 101, timestamp: Date.now() }
      });
      
      await vi.runOnlyPendingTimersAsync();
      
      expect(onNotification).toHaveBeenCalledWith(
        expect.objectContaining({ type: 'graph_updated' })
      );
      
      // Should fetch changes
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/graph/changes')
      );
    });
    
    it('should batch multiple notifications', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: async () => ([])
      });
      
      // Send multiple notifications quickly
      for (let i = 1; i <= 5; i++) {
        mockWs.simulateMessage({
          type: 'graph_updated',
          data: { sequence: 100 + i, timestamp: Date.now() }
        });
      }
      
      await vi.runOnlyPendingTimersAsync();
      
      // Should batch into single fetch
      expect(mockFetch).toHaveBeenCalledTimes(1);
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('since=100')
      );
    });
    
    it('should handle out-of-order notifications', async () => {
      const sequences: number[] = [];
      
      mockFetch.mockImplementation(async (url: string) => {
        const match = url.match(/since=(\d+)/);
        if (match) {
          sequences.push(parseInt(match[1]));
        }
        return {
          ok: true,
          json: async () => ([])
        };
      });
      
      // Send out-of-order notifications
      mockWs.simulateMessage({
        type: 'graph_updated',
        data: { sequence: 105, timestamp: Date.now() }
      });
      
      mockWs.simulateMessage({
        type: 'graph_updated',
        data: { sequence: 103, timestamp: Date.now() }
      });
      
      mockWs.simulateMessage({
        type: 'graph_updated',
        data: { sequence: 107, timestamp: Date.now() }
      });
      
      await vi.runOnlyPendingTimersAsync();
      
      // Should process in order
      expect(sequences[0]).toBeLessThanOrEqual(103);
    });
  });
  
  describe('Incremental Update Pipeline', () => {
    beforeEach(async () => {
      wsManager.connect();
      await vi.runOnlyPendingTimersAsync();
      mockWs = wsManager['ws'] as any;
    });
    
    it('should process deltas through pipeline', async () => {
      const onUpdate = vi.fn();
      pipeline.subscribe(onUpdate);
      
      const delta: GraphDelta = {
        sequence: 101,
        timestamp: Date.now(),
        type: 'incremental',
        added_nodes: [
          { id: 'n1', name: 'Node 1', node_type: 'test' },
          { id: 'n2', name: 'Node 2', node_type: 'test' }
        ],
        added_edges: [
          { source: 'n1', target: 'n2', name: 'Edge 1' }
        ],
        updated_nodes: [],
        updated_edges: [],
        removed_nodes: [],
        removed_edges: []
      };
      
      pipeline.processDelta(delta);
      await vi.runOnlyPendingTimersAsync();
      
      expect(onUpdate).toHaveBeenCalledWith(
        expect.objectContaining({
          nodes: expect.objectContaining({
            added: expect.arrayContaining([
              expect.objectContaining({ id: 'n1' }),
              expect.objectContaining({ id: 'n2' })
            ])
          }),
          edges: expect.objectContaining({
            added: expect.arrayContaining([
              expect.objectContaining({ source: 'n1', target: 'n2' })
            ])
          })
        })
      );
    });
    
    it('should deduplicate updates', async () => {
      const onUpdate = vi.fn();
      pipeline.subscribe(onUpdate);
      
      // Add same node multiple times
      for (let i = 0; i < 3; i++) {
        pipeline.processDelta({
          sequence: 100 + i,
          timestamp: Date.now(),
          type: 'incremental',
          added_nodes: [{ id: 'n1', name: `Name ${i}`, node_type: 'test' }],
          added_edges: [],
          updated_nodes: [],
          updated_edges: [],
          removed_nodes: [],
          removed_edges: []
        });
      }
      
      await vi.runOnlyPendingTimersAsync();
      
      // Should only add once with latest data
      expect(onUpdate).toHaveBeenCalledTimes(1);
      expect(onUpdate).toHaveBeenCalledWith(
        expect.objectContaining({
          nodes: expect.objectContaining({
            added: expect.arrayContaining([
              expect.objectContaining({ id: 'n1', name: 'Name 2' })
            ])
          })
        })
      );
    });
    
    it('should merge add + update operations', async () => {
      const onUpdate = vi.fn();
      pipeline.subscribe(onUpdate);
      
      // Add node
      pipeline.processDelta({
        sequence: 100,
        timestamp: Date.now(),
        type: 'incremental',
        added_nodes: [{ id: 'n1', name: 'Initial', node_type: 'test' }],
        added_edges: [],
        updated_nodes: [],
        updated_edges: [],
        removed_nodes: [],
        removed_edges: []
      });
      
      // Update same node before flush
      pipeline.processDelta({
        sequence: 101,
        timestamp: Date.now(),
        type: 'incremental',
        added_nodes: [],
        added_edges: [],
        updated_nodes: [{ id: 'n1', name: 'Updated', node_type: 'test' }],
        updated_edges: [],
        removed_nodes: [],
        removed_edges: []
      });
      
      await vi.runOnlyPendingTimersAsync();
      
      // Should merge into single add with updated data
      expect(onUpdate).toHaveBeenCalledTimes(1);
      expect(onUpdate).toHaveBeenCalledWith(
        expect.objectContaining({
          nodes: expect.objectContaining({
            added: expect.arrayContaining([
              expect.objectContaining({ id: 'n1', name: 'Updated' })
            ]),
            updated: []
          })
        })
      );
    });
    
    it('should handle update + remove operations', async () => {
      const onUpdate = vi.fn();
      pipeline.subscribe(onUpdate);
      
      // Update node
      pipeline.processDelta({
        sequence: 100,
        timestamp: Date.now(),
        type: 'incremental',
        added_nodes: [],
        added_edges: [],
        updated_nodes: [{ id: 'n1', name: 'Updated', node_type: 'test' }],
        updated_edges: [],
        removed_nodes: [],
        removed_edges: []
      });
      
      // Remove same node
      pipeline.processDelta({
        sequence: 101,
        timestamp: Date.now(),
        type: 'incremental',
        added_nodes: [],
        added_edges: [],
        updated_nodes: [],
        updated_edges: [],
        removed_nodes: ['n1'],
        removed_edges: []
      });
      
      await vi.runOnlyPendingTimersAsync();
      
      // Should only have remove, no update
      expect(onUpdate).toHaveBeenCalledWith(
        expect.objectContaining({
          nodes: expect.objectContaining({
            added: [],
            updated: [],
            removed: ['n1']
          })
        })
      );
    });
  });
  
  describe('Error Handling', () => {
    beforeEach(async () => {
      wsManager.connect();
      await vi.runOnlyPendingTimersAsync();
      mockWs = wsManager['ws'] as any;
    });
    
    it('should retry failed fetches', async () => {
      const onError = vi.fn();
      wsManager.on('error', onError);
      
      // First fetch fails
      mockFetch.mockRejectedValueOnce(new Error('Network error'));
      
      // Second fetch succeeds
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ([])
      });
      
      mockWs.simulateMessage({
        type: 'graph_updated',
        data: { sequence: 101, timestamp: Date.now() }
      });
      
      await vi.runOnlyPendingTimersAsync();
      
      // Should retry
      expect(mockFetch).toHaveBeenCalledTimes(2);
      expect(onError).toHaveBeenCalled();
    });
    
    it('should handle malformed notifications', async () => {
      const onError = vi.fn();
      wsManager.on('error', onError);
      
      // Send malformed notification
      mockWs.simulateMessage({
        type: 'graph_updated'
        // Missing data field
      });
      
      await vi.runOnlyPendingTimersAsync();
      
      expect(onError).toHaveBeenCalledWith(
        expect.objectContaining({
          message: expect.stringContaining('Invalid notification')
        })
      );
    });
    
    it('should recover from version mismatch', async () => {
      // Simulate version mismatch
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 409,
        json: async () => ({ error: 'Version mismatch' })
      });
      
      // Full sync response
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          nodes: [],
          edges: [],
          sequence: 200
        })
      });
      
      mockWs.simulateMessage({
        type: 'graph_updated',
        data: { sequence: 201, timestamp: Date.now() }
      });
      
      await vi.runOnlyPendingTimersAsync();
      
      // Should trigger full sync
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/graph/full')
      );
    });
  });
  
  describe('Performance', () => {
    it('should handle large deltas efficiently', async () => {
      const startTime = performance.now();
      
      // Create large delta
      const largeDelta: GraphDelta = {
        sequence: 100,
        timestamp: Date.now(),
        type: 'incremental',
        added_nodes: Array.from({ length: 1000 }, (_, i) => ({
          id: `n${i}`,
          name: `Node ${i}`,
          node_type: 'test'
        })),
        added_edges: Array.from({ length: 2000 }, (_, i) => ({
          source: `n${i % 1000}`,
          target: `n${(i + 1) % 1000}`,
          name: `Edge ${i}`
        })),
        updated_nodes: [],
        updated_edges: [],
        removed_nodes: [],
        removed_edges: []
      };
      
      pipeline.processDelta(largeDelta);
      await vi.runOnlyPendingTimersAsync();
      
      const processingTime = performance.now() - startTime;
      
      // Should process within reasonable time
      expect(processingTime).toBeLessThan(100); // 100ms
    });
    
    it('should batch updates within time window', async () => {
      const onUpdate = vi.fn();
      pipeline.subscribe(onUpdate);
      
      // Send multiple deltas quickly
      for (let i = 0; i < 10; i++) {
        pipeline.processDelta({
          sequence: 100 + i,
          timestamp: Date.now(),
          type: 'incremental',
          added_nodes: [{ id: `n${i}`, name: `Node ${i}`, node_type: 'test' }],
          added_edges: [],
          updated_nodes: [],
          updated_edges: [],
          removed_nodes: [],
          removed_edges: []
        });
      }
      
      // Should batch within flush interval
      await vi.advanceTimersByTimeAsync(50);
      
      // Should have single batched update
      expect(onUpdate).toHaveBeenCalledTimes(1);
      expect(onUpdate).toHaveBeenCalledWith(
        expect.objectContaining({
          nodes: expect.objectContaining({
            added: expect.arrayContaining(
              Array.from({ length: 10 }, (_, i) => 
                expect.objectContaining({ id: `n${i}` })
              )
            )
          })
        })
      );
    });
  });
});