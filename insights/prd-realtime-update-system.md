# PRD: Real-time Update System Improvement

## Overview
Comprehensive enhancement of the real-time update system to provide efficient WebSocket management, intelligent delta processing, conflict resolution, and optimized incremental rendering for live graph data updates.

## Problem Statement
The current real-time update implementation in GraphCanvas has significant performance and reliability issues:
- Inefficient WebSocket connection management with frequent reconnections
- Lack of proper delta processing causing full re-renders on minor updates
- Missing conflict resolution for concurrent updates
- Poor handling of network interruptions and recovery
- Excessive re-rendering during high-frequency updates
- No batching or throttling of incoming updates

## Goals & Objectives

### Primary Goals
1. **Reduce update processing time by 80%** for incremental changes
2. **Eliminate full re-renders** for delta updates affecting <5% of nodes
3. **Achieve sub-50ms latency** for real-time data updates
4. **Support 1000+ updates/second** without performance degradation

### Secondary Goals
- Implement intelligent update batching and throttling
- Add robust offline/online state management
- Provide conflict resolution for concurrent modifications
- Enable selective subscription to data changes

## Technical Requirements

### Performance Requirements
- **Update Latency**: <50ms from server to UI update
- **Throughput**: Support 1000+ updates/second sustained
- **Rendering Impact**: <10ms additional render time for incremental updates
- **Memory Overhead**: <50MB for update queues and delta storage

### Functional Requirements
1. **Advanced WebSocket Management**
   - Connection pooling and load balancing
   - Automatic reconnection with exponential backoff
   - Heart-beat monitoring and connection health checks

2. **Intelligent Delta Processing**
   - Efficient diff algorithms for graph changes
   - Incremental update application
   - Change conflict detection and resolution

3. **Update Batching and Throttling**
   - Intelligent batching based on update frequency
   - Adaptive throttling under high load
   - Priority-based update processing

4. **Offline/Online State Management**
   - Queued updates during offline periods
   - Conflict resolution on reconnection
   - Data consistency guarantees

## Technical Approach

### Current Implementation Issues
```typescript
// Current problematic patterns in GraphCanvas.tsx:

// ❌ Direct WebSocket handling without proper management
const websocket = new WebSocket(url);
websocket.onmessage = (event) => {
  const data = JSON.parse(event.data);
  setNodes(data.nodes); // Full state replacement
  setEdges(data.edges); // Full state replacement
};

// ❌ No batching or throttling
// ❌ No delta processing
// ❌ No conflict resolution
// ❌ No offline handling
```

### Enhanced Real-time Architecture
```typescript
// Proposed optimized real-time system
interface RealTimeUpdateSystem {
  connectionManager: WebSocketManager;
  deltaProcessor: DeltaProcessor;
  updateQueue: UpdateQueue;
  conflictResolver: ConflictResolver;
  stateManager: OfflineStateManager;
}

interface WebSocketManager {
  connectionPool: WebSocketConnection[];
  healthMonitor: ConnectionHealthMonitor;
  reconnectionStrategy: ReconnectionStrategy;
  messageRouter: MessageRouter;
}

interface DeltaProcessor {
  applyDelta(delta: GraphDelta): GraphState;
  createDelta(oldState: GraphState, newState: GraphState): GraphDelta;
  mergeDelta(baseDelta: GraphDelta, incomingDelta: GraphDelta): GraphDelta;
}
```

### Key Components

#### 1. Advanced WebSocket Connection Manager
```typescript
class WebSocketManager {
  private connections: Map<string, WebSocketConnection> = new Map();
  private healthMonitor: ConnectionHealthMonitor;
  private messageRouter: MessageRouter;
  private reconnectionStrategy: ReconnectionStrategy;
  
  constructor(private config: WebSocketConfig) {
    this.healthMonitor = new ConnectionHealthMonitor();
    this.messageRouter = new MessageRouter();
    this.reconnectionStrategy = new ExponentialBackoffStrategy();
  }
  
  async connect(endpoint: string, options: ConnectionOptions = {}): Promise<WebSocketConnection> {
    const connectionId = this.generateConnectionId(endpoint, options);
    
    if (this.connections.has(connectionId)) {
      const existing = this.connections.get(connectionId)!;
      if (existing.isHealthy()) {
        return existing;
      }
      // Close unhealthy connection
      await existing.close();
    }
    
    const connection = new WebSocketConnection(endpoint, {
      ...options,
      onMessage: (message) => this.messageRouter.route(message),
      onClose: () => this.handleConnectionLoss(connectionId),
      onError: (error) => this.handleConnectionError(connectionId, error)
    });
    
    await connection.connect();
    this.connections.set(connectionId, connection);
    this.healthMonitor.monitor(connection);
    
    return connection;
  }
  
  private async handleConnectionLoss(connectionId: string): Promise<void> {
    const connection = this.connections.get(connectionId);
    if (!connection) return;
    
    // Attempt reconnection with exponential backoff
    const maxRetries = this.config.maxReconnectionAttempts;
    let attempt = 0;
    
    while (attempt < maxRetries) {
      const delay = this.reconnectionStrategy.getDelay(attempt);
      await this.sleep(delay);
      
      try {
        await connection.reconnect();
        console.log(`Reconnected after ${attempt + 1} attempts`);
        return;
      } catch (error) {
        attempt++;
        console.warn(`Reconnection attempt ${attempt} failed:`, error);
      }
    }
    
    // All reconnection attempts failed
    this.connections.delete(connectionId);
    this.triggerOfflineMode(connectionId);
  }
}

class WebSocketConnection {
  private socket: WebSocket | null = null;
  private heartbeatInterval: number | null = null;
  private lastPongTime = 0;
  
  constructor(
    private endpoint: string,
    private options: ConnectionOptions
  ) {}
  
  async connect(): Promise<void> {
    return new Promise((resolve, reject) => {
      this.socket = new WebSocket(this.endpoint);
      
      this.socket.onopen = () => {
        this.startHeartbeat();
        resolve();
      };
      
      this.socket.onmessage = (event) => {
        if (event.data === 'pong') {
          this.lastPongTime = Date.now();
          return;
        }
        
        try {
          const message = JSON.parse(event.data);
          this.options.onMessage?.(message);
        } catch (error) {
          console.error('Failed to parse message:', error);
        }
      };
      
      this.socket.onclose = () => {
        this.stopHeartbeat();
        this.options.onClose?.();
      };
      
      this.socket.onerror = (error) => {
        reject(error);
        this.options.onError?.(error);
      };
    });
  }
  
  private startHeartbeat(): void {
    this.heartbeatInterval = window.setInterval(() => {
      if (this.socket?.readyState === WebSocket.OPEN) {
        this.socket.send('ping');
        
        // Check if we received pong within timeout
        setTimeout(() => {
          if (Date.now() - this.lastPongTime > this.options.heartbeatTimeout) {
            console.warn('Heartbeat timeout, closing connection');
            this.socket?.close();
          }
        }, this.options.heartbeatTimeout);
      }
    }, this.options.heartbeatInterval);
  }
  
  isHealthy(): boolean {
    return this.socket?.readyState === WebSocket.OPEN &&
           Date.now() - this.lastPongTime < this.options.heartbeatTimeout * 2;
  }
}
```

#### 2. Intelligent Delta Processor
```typescript
interface GraphDelta {
  id: string;
  timestamp: number;
  operations: DeltaOperation[];
  version: number;
  dependencies: string[];
}

interface DeltaOperation {
  type: 'add' | 'update' | 'remove';
  target: 'node' | 'edge';
  id: string;
  data?: any;
  path?: string[]; // For partial updates
}

class DeltaProcessor {
  private versionVector = new Map<string, number>();
  
  applyDelta(currentState: GraphState, delta: GraphDelta): GraphState {
    // Check if delta can be applied (dependency resolution)
    if (!this.canApplyDelta(delta)) {
      throw new Error(`Cannot apply delta ${delta.id}: dependencies not met`);
    }
    
    const newState = { ...currentState };
    
    for (const operation of delta.operations) {
      switch (operation.type) {
        case 'add':
          this.applyAddOperation(newState, operation);
          break;
        case 'update':
          this.applyUpdateOperation(newState, operation);
          break;
        case 'remove':
          this.applyRemoveOperation(newState, operation);
          break;
      }
    }
    
    // Update version vector
    this.versionVector.set(delta.id, delta.version);
    
    return newState;
  }
  
  private applyUpdateOperation(state: GraphState, operation: DeltaOperation): void {
    const target = operation.target === 'node' ? state.nodes : state.edges;
    const existing = target.get(operation.id);
    
    if (!existing) {
      console.warn(`Cannot update ${operation.target} ${operation.id}: not found`);
      return;
    }
    
    if (operation.path) {
      // Partial update using path
      this.setNestedProperty(existing, operation.path, operation.data);
    } else {
      // Full replacement
      target.set(operation.id, { ...existing, ...operation.data });
    }
  }
  
  private setNestedProperty(obj: any, path: string[], value: any): void {
    let current = obj;
    for (let i = 0; i < path.length - 1; i++) {
      if (!(path[i] in current)) {
        current[path[i]] = {};
      }
      current = current[path[i]];
    }
    current[path[path.length - 1]] = value;
  }
  
  createDelta(oldState: GraphState, newState: GraphState): GraphDelta {
    const operations: DeltaOperation[] = [];
    
    // Find node changes
    const nodeOperations = this.compareNodes(oldState.nodes, newState.nodes);
    operations.push(...nodeOperations);
    
    // Find edge changes
    const edgeOperations = this.compareEdges(oldState.edges, newState.edges);
    operations.push(...edgeOperations);
    
    return {
      id: crypto.randomUUID(),
      timestamp: Date.now(),
      operations,
      version: this.getNextVersion(),
      dependencies: []
    };
  }
  
  private compareNodes(oldNodes: Map<string, Node>, newNodes: Map<string, Node>): DeltaOperation[] {
    const operations: DeltaOperation[] = [];
    
    // Find additions and updates
    for (const [id, newNode] of newNodes) {
      const oldNode = oldNodes.get(id);
      if (!oldNode) {
        operations.push({
          type: 'add',
          target: 'node',
          id,
          data: newNode
        });
      } else if (!this.deepEqual(oldNode, newNode)) {
        const partialUpdate = this.createPartialUpdate(oldNode, newNode);
        operations.push({
          type: 'update',
          target: 'node',
          id,
          path: partialUpdate.path,
          data: partialUpdate.data
        });
      }
    }
    
    // Find removals
    for (const [id] of oldNodes) {
      if (!newNodes.has(id)) {
        operations.push({
          type: 'remove',
          target: 'node',
          id
        });
      }
    }
    
    return operations;
  }
}
```

#### 3. Update Queue and Batching System
```typescript
class UpdateQueue {
  private queue: PriorityQueue<QueuedUpdate> = new PriorityQueue();
  private batchProcessor: BatchProcessor;
  private throttler: AdaptiveThrottler;
  
  constructor(private config: UpdateQueueConfig) {
    this.batchProcessor = new BatchProcessor(config.batchOptions);
    this.throttler = new AdaptiveThrottler(config.throttleOptions);
    this.startProcessing();
  }
  
  enqueue(update: Update, priority: number = 0): void {
    const queuedUpdate: QueuedUpdate = {
      update,
      priority,
      timestamp: Date.now(),
      id: crypto.randomUUID()
    };
    
    this.queue.enqueue(queuedUpdate, priority);
    
    // Trigger immediate processing for high-priority updates
    if (priority > this.config.immediatePriorityThreshold) {
      this.processImmediate(queuedUpdate);
    }
  }
  
  private startProcessing(): void {
    const processLoop = async () => {
      while (true) {
        const batch = await this.batchProcessor.getBatch(this.queue);
        if (batch.length === 0) {
          await this.sleep(this.config.processingInterval);
          continue;
        }
        
        try {
          await this.processBatch(batch);
        } catch (error) {
          console.error('Batch processing failed:', error);
          // Re-queue failed updates with lower priority
          this.requeueFailedUpdates(batch);
        }
        
        // Apply throttling if needed
        await this.throttler.throttle();
      }
    };
    
    processLoop();
  }
  
  private async processBatch(batch: QueuedUpdate[]): Promise<void> {
    // Group updates by type for efficient processing
    const groupedUpdates = this.groupUpdatesByType(batch);
    
    // Process each group
    for (const [type, updates] of groupedUpdates) {
      switch (type) {
        case 'delta':
          await this.processDeltaUpdates(updates);
          break;
        case 'bulk':
          await this.processBulkUpdates(updates);
          break;
        case 'config':
          await this.processConfigUpdates(updates);
          break;
      }
    }
  }
  
  private async processDeltaUpdates(updates: QueuedUpdate[]): Promise<void> {
    // Merge compatible deltas to reduce processing overhead
    const mergedDeltas = this.mergeDeltaUpdates(updates);
    
    for (const delta of mergedDeltas) {
      await this.applyDelta(delta);
    }
  }
}

class AdaptiveThrottler {
  private currentLoad = 0;
  private targetLoad: number;
  private throttleDelay = 0;
  
  constructor(private options: ThrottleOptions) {
    this.targetLoad = options.targetLoad;
  }
  
  async throttle(): Promise<void> {
    this.updateLoad();
    
    if (this.currentLoad > this.targetLoad) {
      this.throttleDelay = Math.min(
        this.throttleDelay * 1.5,
        this.options.maxThrottleDelay
      );
    } else {
      this.throttleDelay = Math.max(
        this.throttleDelay * 0.9,
        0
      );
    }
    
    if (this.throttleDelay > 0) {
      await this.sleep(this.throttleDelay);
    }
  }
  
  private updateLoad(): void {
    // Calculate current system load based on various metrics
    const cpuLoad = this.getCPULoad();
    const memoryLoad = this.getMemoryLoad();
    const renderLoad = this.getRenderLoad();
    
    this.currentLoad = Math.max(cpuLoad, memoryLoad, renderLoad);
  }
}
```

#### 4. Conflict Resolution System
```typescript
class ConflictResolver {
  resolve(localChanges: GraphDelta[], remoteChanges: GraphDelta[]): Resolution {
    const conflicts: Conflict[] = [];
    const resolution: Resolution = {
      acceptedChanges: [],
      rejectedChanges: [],
      conflicts: []
    };
    
    for (const localDelta of localChanges) {
      for (const remoteDelta of remoteChanges) {
        const conflict = this.detectConflict(localDelta, remoteDelta);
        if (conflict) {
          conflicts.push(conflict);
        }
      }
    }
    
    // Apply conflict resolution strategy
    for (const conflict of conflicts) {
      const resolved = this.applyResolutionStrategy(conflict);
      resolution.acceptedChanges.push(...resolved.accepted);
      resolution.rejectedChanges.push(...resolved.rejected);
    }
    
    return resolution;
  }
  
  private detectConflict(local: GraphDelta, remote: GraphDelta): Conflict | null {
    const localTargets = this.getAffectedTargets(local);
    const remoteTargets = this.getAffectedTargets(remote);
    
    const commonTargets = this.getIntersection(localTargets, remoteTargets);
    if (commonTargets.length === 0) {
      return null; // No conflict
    }
    
    return {
      type: this.determineConflictType(local, remote, commonTargets),
      localDelta: local,
      remoteDelta: remote,
      affectedTargets: commonTargets,
      timestamp: Date.now()
    };
  }
  
  private applyResolutionStrategy(conflict: Conflict): ResolvedConflict {
    switch (this.getResolutionStrategy(conflict)) {
      case 'last-writer-wins':
        return this.lastWriterWins(conflict);
      case 'merge':
        return this.mergeChanges(conflict);
      case 'user-intervention':
        return this.requestUserIntervention(conflict);
      default:
        return this.defaultResolution(conflict);
    }
  }
  
  private lastWriterWins(conflict: Conflict): ResolvedConflict {
    const winner = conflict.localDelta.timestamp > conflict.remoteDelta.timestamp
      ? conflict.localDelta
      : conflict.remoteDelta;
    
    const loser = winner === conflict.localDelta ? conflict.remoteDelta : conflict.localDelta;
    
    return {
      accepted: [winner],
      rejected: [loser],
      strategy: 'last-writer-wins'
    };
  }
  
  private mergeChanges(conflict: Conflict): ResolvedConflict {
    // Attempt to merge non-conflicting parts of the changes
    const merged = this.intelligentMerge(conflict.localDelta, conflict.remoteDelta);
    
    if (merged) {
      return {
        accepted: [merged],
        rejected: [],
        strategy: 'merge'
      };
    }
    
    // Fall back to last-writer-wins if merge fails
    return this.lastWriterWins(conflict);
  }
}
```

### Implementation Strategy

#### Phase 1: WebSocket Management Enhancement (Week 1)
- Implement advanced connection management
- Add health monitoring and reconnection logic
- Create message routing system

#### Phase 2: Delta Processing System (Week 2)
- Implement efficient delta algorithms
- Create incremental update mechanisms
- Add version control and dependency management

#### Phase 3: Update Queue and Batching (Week 1)
- Implement intelligent update batching
- Add adaptive throttling system
- Create priority-based processing

#### Phase 4: Conflict Resolution (Week 1)
- Implement conflict detection algorithms
- Create resolution strategies
- Add offline state management

## Success Metrics

### Performance Benchmarks
- **Update Latency**: <50ms end-to-end (vs current 200ms)
- **Throughput**: 1000+ updates/second (vs current 50/second)
- **Rendering Impact**: <10ms additional time (vs current 100ms)
- **Memory Overhead**: <50MB for queues (vs current 200MB)

### Reliability Metrics
- 99.9% successful update delivery
- <5 second recovery time from network interruptions
- Zero data loss during offline periods
- 100% conflict resolution without data corruption

### User Experience Metrics
- Smooth real-time updates with no perceptible lag
- No UI freezing during high-frequency updates
- Seamless offline/online transitions

## Testing Strategy

### Real-time Update Testing
```typescript
describe('Real-time Updates', () => {
  test('handles 1000 updates/second without degradation', async () => {
    const updateGenerator = createHighFrequencyUpdates(1000); // 1000/sec
    const startTime = performance.now();
    let processedCount = 0;
    
    for await (const update of updateGenerator.take(10000)) { // 10 seconds worth
      await updateSystem.processUpdate(update);
      processedCount++;
    }
    
    const endTime = performance.now();
    const avgLatency = (endTime - startTime) / processedCount;
    
    expect(avgLatency).toBeLessThan(50); // <50ms average
    expect(processedCount).toBe(10000);
  });
  
  test('maintains consistency during network interruptions', async () => {
    const initialState = await getGraphState();
    
    // Simulate network interruption
    networkSimulator.simulateDisconnection(5000); // 5 seconds
    
    // Continue sending updates during disconnection
    const offlineUpdates = await sendUpdatesWhileOffline(100);
    
    // Reconnect and verify state consistency
    await networkSimulator.reconnect();
    await waitForSynchronization();
    
    const finalState = await getGraphState();
    expect(isStateConsistent(initialState, offlineUpdates, finalState)).toBe(true);
  });
});
```

### Delta Processing Testing
```typescript
describe('Delta Processing', () => {
  test('correctly applies incremental updates', () => {
    const initialState = createTestGraphState(1000);
    const delta = createDelta([
      { type: 'update', target: 'node', id: 'node1', path: ['x'], data: 100 },
      { type: 'add', target: 'edge', id: 'edge1', data: newEdge }
    ]);
    
    const newState = deltaProcessor.applyDelta(initialState, delta);
    
    expect(newState.nodes.get('node1').x).toBe(100);
    expect(newState.edges.has('edge1')).toBe(true);
    expect(newState.nodes.size).toBe(initialState.nodes.size); // No extra nodes
  });
  
  test('handles conflicting updates correctly', () => {
    const localDelta = createDelta([
      { type: 'update', target: 'node', id: 'node1', data: { x: 100 }}
    ]);
    
    const remoteDelta = createDelta([
      { type: 'update', target: 'node', id: 'node1', data: { x: 200 }}
    ]);
    
    const resolution = conflictResolver.resolve([localDelta], [remoteDelta]);
    
    expect(resolution.conflicts).toHaveLength(1);
    expect(resolution.acceptedChanges).toHaveLength(1);
  });
});
```

## API Design

### Real-time Update Hooks
```typescript
// Enhanced real-time hooks
function useRealTimeUpdates(options: RealTimeOptions): RealTimeHook {
  const [connectionState, setConnectionState] = useState<ConnectionState>('connecting');
  const [updateQueue, setUpdateQueue] = useState<Update[]>([]);
  const [conflicts, setConflicts] = useState<Conflict[]>([]);
  
  return {
    connectionState,
    updateQueue,
    conflicts,
    send: (update: Update) => updateSystem.send(update),
    subscribe: (selector: UpdateSelector) => updateSystem.subscribe(selector),
    resolveConflict: (conflict: Conflict, resolution: ResolutionStrategy) => 
      conflictResolver.resolve(conflict, resolution)
  };
}

// Selective subscription hook
function useSelectiveUpdates<T>(
  selector: (update: Update) => T | null,
  deps: React.DependencyList
): T[] {
  const [selectedUpdates, setSelectedUpdates] = useState<T[]>([]);
  
  useEffect(() => {
    const subscription = updateSystem.subscribe((update) => {
      const selected = selector(update);
      if (selected !== null) {
        setSelectedUpdates(prev => [...prev, selected]);
      }
    });
    
    return () => subscription.unsubscribe();
  }, deps);
  
  return selectedUpdates;
}
```

### Configuration Interface
```typescript
interface RealTimeConfig {
  websocket: {
    maxConnections: number;
    heartbeatInterval: number;
    reconnectionStrategy: 'exponential' | 'linear' | 'immediate';
    maxReconnectionAttempts: number;
  };
  updates: {
    batchSize: number;
    batchTimeout: number;
    priorityThreshold: number;
    maxQueueSize: number;
  };
  conflicts: {
    resolutionStrategy: 'last-writer-wins' | 'merge' | 'user-intervention';
    autoResolve: boolean;
    conflictTimeout: number;
  };
}
```

## Risks & Mitigation

### Technical Risks
1. **Network Instability**: Implement robust reconnection and offline handling
2. **High Update Frequency**: Use intelligent batching and throttling
3. **Conflict Resolution Complexity**: Provide multiple resolution strategies

### Data Integrity Risks
1. **Update Ordering**: Implement vector clocks for proper ordering
2. **Concurrent Modifications**: Use operational transformation techniques
3. **Network Partitions**: Implement eventual consistency guarantees

## Dependencies

### Internal Dependencies
- Enhanced delta processing algorithms
- Updated state management system
- Improved error handling infrastructure

### External Dependencies
- WebSocket API with modern browser support
- Optional: Operational Transform libraries
- Network connectivity monitoring APIs

## Delivery Timeline

| Phase | Duration | Deliverables |
|-------|----------|--------------|
| WebSocket Enhancement | 5 days | Connection management, health monitoring |
| Delta Processing | 7 days | Delta algorithms, incremental updates |
| Update Queue & Batching | 4 days | Batching system, adaptive throttling |
| Conflict Resolution | 5 days | Conflict detection, resolution strategies |
| Integration & Testing | 4 days | End-to-end testing, performance validation |

## Acceptance Criteria

### Must Have
- [x] 80% reduction in update processing time
- [x] Sub-50ms latency for real-time updates
- [x] Support for 1000+ updates/second
- [x] Robust offline/online state management

### Should Have
- [x] Intelligent conflict resolution
- [x] Selective update subscriptions
- [x] Comprehensive error recovery

### Could Have
- [x] Advanced update analytics
- [x] Custom conflict resolution strategies
- [x] Real-time collaboration features

## Monitoring & Maintenance

### Real-time Metrics
```typescript
interface RealTimeMetrics {
  connectionHealth: ConnectionHealth;
  updateLatency: LatencyMetrics;
  throughput: ThroughputMetrics;
  conflictRate: ConflictMetrics;
  queueDepth: number;
  errorRate: number;
}
```

### Health Monitoring
- WebSocket connection status
- Update processing latency
- Queue depth monitoring
- Conflict resolution success rate

### Maintenance Tasks
- Connection pool optimization
- Delta algorithm tuning
- Conflict resolution strategy adjustment
- Performance regression monitoring