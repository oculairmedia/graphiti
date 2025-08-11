// CRDT-inspired conflict resolution for concurrent graph updates

export interface GraphDelta {
  id: string;
  timestamp: number;
  operations: DeltaOperation[];
  version: string;
  sourceId: string; // Client/server that created this delta
  dependencies: string[]; // IDs of deltas this one depends on
}

export interface DeltaOperation {
  type: 'add' | 'update' | 'remove';
  target: 'node' | 'edge';
  targetId: string;
  data?: any;
  path?: string[]; // For partial updates
  vector?: VectorClock; // For ordering operations
}

export interface VectorClock {
  [sourceId: string]: number;
}

export interface Conflict {
  id: string;
  type: 'write-write' | 'delete-update' | 'structural';
  localDelta: GraphDelta;
  remoteDelta: GraphDelta;
  affectedTargets: string[];
  timestamp: number;
}

export interface Resolution {
  acceptedChanges: GraphDelta[];
  rejectedChanges: GraphDelta[];
  mergedChanges: GraphDelta[];
  conflicts: Conflict[];
}

export type ResolutionStrategy = 
  | 'last-writer-wins'
  | 'first-writer-wins'
  | 'merge'
  | 'user-intervention'
  | 'operational-transform';

// Vector clock implementation for causality tracking
export class VectorClockManager {
  private clock: VectorClock = {};
  private sourceId: string;

  constructor(sourceId: string) {
    this.sourceId = sourceId;
    this.clock[sourceId] = 0;
  }

  increment(): VectorClock {
    this.clock[this.sourceId]++;
    return { ...this.clock };
  }

  update(otherClock: VectorClock): void {
    for (const [source, timestamp] of Object.entries(otherClock)) {
      if (source !== this.sourceId) {
        this.clock[source] = Math.max(this.clock[source] || 0, timestamp);
      }
    }
  }

  compare(a: VectorClock, b: VectorClock): 'before' | 'after' | 'concurrent' {
    let aGreater = false;
    let bGreater = false;

    const allSources = new Set([...Object.keys(a), ...Object.keys(b)]);

    for (const source of allSources) {
      const aTime = a[source] || 0;
      const bTime = b[source] || 0;

      if (aTime > bTime) aGreater = true;
      if (bTime > aTime) bGreater = true;
    }

    if (aGreater && !bGreater) return 'after';
    if (bGreater && !aGreater) return 'before';
    return 'concurrent';
  }

  happensBefore(a: VectorClock, b: VectorClock): boolean {
    return this.compare(a, b) === 'before';
  }
}

// Main conflict resolver
export class ConflictResolver {
  private vectorClock: VectorClockManager;
  private pendingDeltas = new Map<string, GraphDelta>();
  private appliedDeltas = new Set<string>();
  private conflictHistory: Conflict[] = [];

  constructor(
    private sourceId: string,
    private strategy: ResolutionStrategy = 'operational-transform'
  ) {
    this.vectorClock = new VectorClockManager(sourceId);
  }

  // Detect conflicts between deltas
  detectConflicts(localDeltas: GraphDelta[], remoteDeltas: GraphDelta[]): Conflict[] {
    const conflicts: Conflict[] = [];

    for (const local of localDeltas) {
      for (const remote of remoteDeltas) {
        const conflict = this.detectConflict(local, remote);
        if (conflict) {
          conflicts.push(conflict);
        }
      }
    }

    return conflicts;
  }

  private detectConflict(local: GraphDelta, remote: GraphDelta): Conflict | null {
    // Skip if deltas are causally related
    if (local.dependencies.includes(remote.id) || remote.dependencies.includes(local.id)) {
      return null;
    }

    const localTargets = this.getAffectedTargets(local);
    const remoteTargets = this.getAffectedTargets(remote);
    
    const commonTargets = localTargets.filter(t => remoteTargets.includes(t));
    
    if (commonTargets.length === 0) {
      return null; // No conflict
    }

    // Determine conflict type
    const conflictType = this.determineConflictType(local, remote, commonTargets);

    return {
      id: `conflict-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      type: conflictType,
      localDelta: local,
      remoteDelta: remote,
      affectedTargets: commonTargets,
      timestamp: Date.now()
    };
  }

  private getAffectedTargets(delta: GraphDelta): string[] {
    return delta.operations.map(op => `${op.target}:${op.targetId}`);
  }

  private determineConflictType(
    local: GraphDelta,
    remote: GraphDelta,
    commonTargets: string[]
  ): Conflict['type'] {
    for (const target of commonTargets) {
      const localOp = local.operations.find(op => `${op.target}:${op.targetId}` === target);
      const remoteOp = remote.operations.find(op => `${op.target}:${op.targetId}` === target);

      if (localOp && remoteOp) {
        if (localOp.type === 'remove' && remoteOp.type === 'update') {
          return 'delete-update';
        }
        if (localOp.type === 'update' && remoteOp.type === 'remove') {
          return 'delete-update';
        }
        if (localOp.type === 'update' && remoteOp.type === 'update') {
          return 'write-write';
        }
      }
    }

    return 'structural';
  }

  // Resolve conflicts based on strategy
  resolve(conflicts: Conflict[]): Resolution {
    const resolution: Resolution = {
      acceptedChanges: [],
      rejectedChanges: [],
      mergedChanges: [],
      conflicts: []
    };

    for (const conflict of conflicts) {
      const resolved = this.applyResolutionStrategy(conflict);
      
      resolution.acceptedChanges.push(...resolved.accepted);
      resolution.rejectedChanges.push(...resolved.rejected);
      
      if (resolved.merged) {
        resolution.mergedChanges.push(resolved.merged);
      }
      
      if (resolved.unresolved) {
        resolution.conflicts.push(conflict);
      }
    }

    // Store conflict history for analysis
    this.conflictHistory.push(...conflicts);

    return resolution;
  }

  private applyResolutionStrategy(conflict: Conflict): {
    accepted: GraphDelta[];
    rejected: GraphDelta[];
    merged?: GraphDelta;
    unresolved?: boolean;
  } {
    switch (this.strategy) {
      case 'last-writer-wins':
        return this.lastWriterWins(conflict);
      
      case 'first-writer-wins':
        return this.firstWriterWins(conflict);
      
      case 'merge':
        return this.mergeChanges(conflict);
      
      case 'operational-transform':
        return this.operationalTransform(conflict);
      
      case 'user-intervention':
        return { accepted: [], rejected: [], unresolved: true };
      
      default:
        return this.lastWriterWins(conflict);
    }
  }

  private lastWriterWins(conflict: Conflict): {
    accepted: GraphDelta[];
    rejected: GraphDelta[];
  } {
    const winner = conflict.localDelta.timestamp > conflict.remoteDelta.timestamp
      ? conflict.localDelta
      : conflict.remoteDelta;
    
    const loser = winner === conflict.localDelta 
      ? conflict.remoteDelta 
      : conflict.localDelta;

    return {
      accepted: [winner],
      rejected: [loser]
    };
  }

  private firstWriterWins(conflict: Conflict): {
    accepted: GraphDelta[];
    rejected: GraphDelta[];
  } {
    const winner = conflict.localDelta.timestamp < conflict.remoteDelta.timestamp
      ? conflict.localDelta
      : conflict.remoteDelta;
    
    const loser = winner === conflict.localDelta 
      ? conflict.remoteDelta 
      : conflict.localDelta;

    return {
      accepted: [winner],
      rejected: [loser]
    };
  }

  private mergeChanges(conflict: Conflict): {
    accepted: GraphDelta[];
    rejected: GraphDelta[];
    merged?: GraphDelta;
  } {
    // Attempt to merge non-conflicting operations
    const merged = this.intelligentMerge(conflict.localDelta, conflict.remoteDelta);
    
    if (merged) {
      return {
        accepted: [],
        rejected: [],
        merged
      };
    }

    // Fall back to last-writer-wins if merge fails
    return this.lastWriterWins(conflict);
  }

  private operationalTransform(conflict: Conflict): {
    accepted: GraphDelta[];
    rejected: GraphDelta[];
    merged?: GraphDelta;
  } {
    // Transform operations to make them commutative
    const transformed = this.transformOperations(
      conflict.localDelta,
      conflict.remoteDelta
    );

    if (transformed) {
      return {
        accepted: transformed,
        rejected: []
      };
    }

    // Fall back to merge strategy
    return this.mergeChanges(conflict);
  }

  private intelligentMerge(local: GraphDelta, remote: GraphDelta): GraphDelta | null {
    const mergedOperations: DeltaOperation[] = [];
    const processedTargets = new Set<string>();

    // Process local operations first
    for (const localOp of local.operations) {
      const targetKey = `${localOp.target}:${localOp.targetId}`;
      const remoteOp = remote.operations.find(
        op => `${op.target}:${op.targetId}` === targetKey
      );

      if (!remoteOp) {
        // No conflict for this operation
        mergedOperations.push(localOp);
        processedTargets.add(targetKey);
      } else {
        // Try to merge the operations
        const merged = this.mergeOperations(localOp, remoteOp);
        if (merged) {
          mergedOperations.push(merged);
          processedTargets.add(targetKey);
        } else {
          // Cannot merge, abort
          return null;
        }
      }
    }

    // Add remaining remote operations
    for (const remoteOp of remote.operations) {
      const targetKey = `${remoteOp.target}:${remoteOp.targetId}`;
      if (!processedTargets.has(targetKey)) {
        mergedOperations.push(remoteOp);
      }
    }

    return {
      id: `merged-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      timestamp: Math.max(local.timestamp, remote.timestamp),
      operations: mergedOperations,
      version: `${local.version}-${remote.version}`,
      sourceId: this.sourceId,
      dependencies: [local.id, remote.id]
    };
  }

  private mergeOperations(local: DeltaOperation, remote: DeltaOperation): DeltaOperation | null {
    // Handle different operation type combinations
    if (local.type === 'remove' || remote.type === 'remove') {
      // Cannot merge if either is a remove
      return null;
    }

    if (local.type === 'add' && remote.type === 'add') {
      // Use the one with more data
      const localDataSize = JSON.stringify(local.data).length;
      const remoteDataSize = JSON.stringify(remote.data).length;
      return localDataSize >= remoteDataSize ? local : remote;
    }

    if (local.type === 'update' && remote.type === 'update') {
      // Merge update operations
      if (local.path && remote.path) {
        // Check if paths conflict
        const pathsConflict = this.doPathsConflict(local.path, remote.path);
        if (!pathsConflict) {
          // Can apply both updates
          return {
            ...local,
            data: { ...remote.data, ...local.data } // Local wins for same fields
          };
        }
      }
      
      // Deep merge the data
      const mergedData = this.deepMerge(remote.data, local.data);
      return {
        ...local,
        data: mergedData
      };
    }

    return null;
  }

  private doPathsConflict(path1: string[], path2: string[]): boolean {
    const minLength = Math.min(path1.length, path2.length);
    
    for (let i = 0; i < minLength; i++) {
      if (path1[i] !== path2[i]) {
        return false; // Paths diverge, no conflict
      }
    }
    
    return true; // One path is prefix of the other
  }

  private deepMerge(target: any, source: any): any {
    if (!target || typeof target !== 'object') return source;
    if (!source || typeof source !== 'object') return source;

    const result = { ...target };

    for (const key in source) {
      if (source.hasOwnProperty(key)) {
        if (typeof source[key] === 'object' && !Array.isArray(source[key])) {
          result[key] = this.deepMerge(result[key], source[key]);
        } else {
          result[key] = source[key];
        }
      }
    }

    return result;
  }

  private transformOperations(local: GraphDelta, remote: GraphDelta): GraphDelta[] | null {
    // Simple operational transformation
    // This is a simplified version - real OT is much more complex
    
    const transformedLocal: DeltaOperation[] = [];
    const transformedRemote: DeltaOperation[] = [];

    for (const localOp of local.operations) {
      let transformed = localOp;
      
      for (const remoteOp of remote.operations) {
        if (this.operationsConflict(localOp, remoteOp)) {
          transformed = this.transformOperation(localOp, remoteOp);
          if (!transformed) return null; // Cannot transform
        }
      }
      
      transformedLocal.push(transformed);
    }

    for (const remoteOp of remote.operations) {
      let transformed = remoteOp;
      
      for (const localOp of local.operations) {
        if (this.operationsConflict(remoteOp, localOp)) {
          transformed = this.transformOperation(remoteOp, localOp);
          if (!transformed) return null; // Cannot transform
        }
      }
      
      transformedRemote.push(transformed);
    }

    return [
      { ...local, operations: transformedLocal },
      { ...remote, operations: transformedRemote }
    ];
  }

  private operationsConflict(op1: DeltaOperation, op2: DeltaOperation): boolean {
    return op1.target === op2.target && op1.targetId === op2.targetId;
  }

  private transformOperation(op: DeltaOperation, against: DeltaOperation): DeltaOperation | null {
    // Simple transformation rules
    if (against.type === 'remove') {
      // Cannot transform against a remove
      return null;
    }

    if (op.type === 'update' && against.type === 'update') {
      // Transform update against update
      if (op.path && against.path) {
        if (!this.doPathsConflict(op.path, against.path)) {
          // No conflict, operation remains the same
          return op;
        }
      }
      
      // Merge the updates
      return {
        ...op,
        data: this.deepMerge(against.data, op.data)
      };
    }

    return op;
  }

  // Apply a resolved delta to the state
  applyDelta(delta: GraphDelta): void {
    if (this.appliedDeltas.has(delta.id)) {
      return; // Already applied
    }

    // Check dependencies
    for (const dep of delta.dependencies) {
      if (!this.appliedDeltas.has(dep)) {
        // Queue for later application
        this.pendingDeltas.set(delta.id, delta);
        return;
      }
    }

    // Apply the delta
    this.appliedDeltas.add(delta.id);
    
    // Update vector clock
    if (delta.operations.length > 0 && delta.operations[0].vector) {
      this.vectorClock.update(delta.operations[0].vector);
    }

    // Check if any pending deltas can now be applied
    const toApply: GraphDelta[] = [];
    
    for (const [id, pending] of this.pendingDeltas) {
      const canApply = pending.dependencies.every(dep => this.appliedDeltas.has(dep));
      if (canApply) {
        toApply.push(pending);
      }
    }

    for (const pending of toApply) {
      this.pendingDeltas.delete(pending.id);
      this.applyDelta(pending);
    }
  }

  // Get conflict statistics
  getConflictStats(): {
    total: number;
    byType: Record<Conflict['type'], number>;
    resolutionSuccessRate: number;
  } {
    const byType: Record<Conflict['type'], number> = {
      'write-write': 0,
      'delete-update': 0,
      'structural': 0
    };

    for (const conflict of this.conflictHistory) {
      byType[conflict.type]++;
    }

    return {
      total: this.conflictHistory.length,
      byType,
      resolutionSuccessRate: this.appliedDeltas.size / (this.appliedDeltas.size + this.pendingDeltas.size)
    };
  }
}