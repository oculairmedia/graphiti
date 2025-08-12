/**
 * Optimized Incremental Update Pipeline
 * 
 * Features:
 * - Efficient delta batching with priority queuing
 * - Deduplication of redundant updates
 * - Smart merging of consecutive updates
 * - Minimal React re-renders
 * - Memory-efficient processing
 */

import { GraphNode } from '@/api/types';
import { GraphLink } from '@/types/graph';
import { logger } from '@/utils/logger';

export interface GraphDelta {
  operation: 'initial' | 'update' | 'refresh';
  nodes_added: GraphNode[];
  nodes_updated: GraphNode[];
  nodes_removed: string[];
  edges_added: GraphLink[];
  edges_updated: GraphLink[];
  edges_removed: [string, string][];
  timestamp: number;
  sequence: number;
}

interface UpdateOperation {
  id: string;
  type: 'add' | 'update' | 'remove';
  entityType: 'node' | 'edge';
  data: any;
  sequence: number;
  timestamp: number;
  priority: number; // Higher priority updates processed first
}

interface PipelineConfig {
  batchSize: number;
  batchDelay: number;
  maxQueueSize: number;
  enableDeduplication: boolean;
  enableMerging: boolean;
  priorityMode: 'fifo' | 'priority' | 'smart';
}

interface PipelineStats {
  totalProcessed: number;
  totalDeduplicated: number;
  totalMerged: number;
  avgBatchSize: number;
  avgProcessingTime: number;
  queueSize: number;
  lastProcessedSequence: number;
}

export class IncrementalUpdatePipeline {
  private queue: UpdateOperation[] = [];
  private processingTimer: NodeJS.Timeout | null = null;
  private isProcessing = false;
  private lastSequence = 0;
  
  // Deduplication tracking
  private pendingUpdates = new Map<string, UpdateOperation>();
  private processedIds = new Set<string>();
  
  // Statistics
  private stats: PipelineStats = {
    totalProcessed: 0,
    totalDeduplicated: 0,
    totalMerged: 0,
    avgBatchSize: 0,
    avgProcessingTime: 0,
    queueSize: 0,
    lastProcessedSequence: 0,
  };
  
  // Callbacks
  private onBatchProcessed?: (delta: GraphDelta) => void;
  private onError?: (error: Error) => void;
  
  constructor(
    private config: PipelineConfig = {
      batchSize: 100,
      batchDelay: 50,
      maxQueueSize: 1000,
      enableDeduplication: true,
      enableMerging: true,
      priorityMode: 'smart',
    }
  ) {}
  
  /**
   * Add a delta to the processing queue
   */
  addDelta(delta: GraphDelta): void {
    // Convert delta to individual operations
    const operations: UpdateOperation[] = [];
    
    // Process node additions
    delta.nodes_added.forEach(node => {
      operations.push({
        id: `node-${node.id}`,
        type: 'add',
        entityType: 'node',
        data: node,
        sequence: delta.sequence,
        timestamp: delta.timestamp,
        priority: this.calculatePriority('add', 'node', node),
      });
    });
    
    // Process node updates
    delta.nodes_updated.forEach(node => {
      operations.push({
        id: `node-${node.id}`,
        type: 'update',
        entityType: 'node',
        data: node,
        sequence: delta.sequence,
        timestamp: delta.timestamp,
        priority: this.calculatePriority('update', 'node', node),
      });
    });
    
    // Process node removals
    delta.nodes_removed.forEach(nodeId => {
      operations.push({
        id: `node-${nodeId}`,
        type: 'remove',
        entityType: 'node',
        data: { id: nodeId },
        sequence: delta.sequence,
        timestamp: delta.timestamp,
        priority: this.calculatePriority('remove', 'node', { id: nodeId }),
      });
    });
    
    // Process edge additions
    delta.edges_added.forEach(edge => {
      operations.push({
        id: `edge-${edge.source}-${edge.target}`,
        type: 'add',
        entityType: 'edge',
        data: edge,
        sequence: delta.sequence,
        timestamp: delta.timestamp,
        priority: this.calculatePriority('add', 'edge', edge),
      });
    });
    
    // Process edge updates
    delta.edges_updated.forEach(edge => {
      operations.push({
        id: `edge-${edge.source}-${edge.target}`,
        type: 'update',
        entityType: 'edge',
        data: edge,
        sequence: delta.sequence,
        timestamp: delta.timestamp,
        priority: this.calculatePriority('update', 'edge', edge),
      });
    });
    
    // Process edge removals
    delta.edges_removed.forEach(([source, target]) => {
      operations.push({
        id: `edge-${source}-${target}`,
        type: 'remove',
        entityType: 'edge',
        data: { source, target },
        sequence: delta.sequence,
        timestamp: delta.timestamp,
        priority: this.calculatePriority('remove', 'edge', { source, target }),
      });
    });
    
    // Add operations to queue with deduplication
    this.enqueueOperations(operations);
    
    // Schedule processing
    this.scheduleProcessing();
  }
  
  /**
   * Enqueue operations with deduplication and merging
   */
  private enqueueOperations(operations: UpdateOperation[]): void {
    for (const op of operations) {
      if (this.config.enableDeduplication) {
        const existing = this.pendingUpdates.get(op.id);
        
        if (existing) {
          // Merge or replace based on operation types
          if (this.config.enableMerging && this.canMerge(existing, op)) {
            const merged = this.mergeOperations(existing, op);
            this.pendingUpdates.set(op.id, merged);
            this.stats.totalMerged++;
          } else {
            // Replace with newer operation
            this.pendingUpdates.set(op.id, op);
            this.stats.totalDeduplicated++;
          }
        } else {
          this.pendingUpdates.set(op.id, op);
        }
      } else {
        this.queue.push(op);
      }
    }
    
    // Enforce max queue size
    if (this.queue.length > this.config.maxQueueSize) {
      const removed = this.queue.splice(0, this.queue.length - this.config.maxQueueSize);
      logger.warn(`Pipeline queue overflow: dropped ${removed.length} operations`);
    }
    
    this.stats.queueSize = this.queue.length + this.pendingUpdates.size;
  }
  
  /**
   * Check if two operations can be merged
   */
  private canMerge(existing: UpdateOperation, incoming: UpdateOperation): boolean {
    // Can't merge different entities
    if (existing.id !== incoming.id) return false;
    
    // Merge rules:
    // - add + update = add (with updated data)
    // - update + update = update (with latest data)
    // - add + remove = skip both
    // - update + remove = remove
    
    if (existing.type === 'add' && incoming.type === 'update') return true;
    if (existing.type === 'update' && incoming.type === 'update') return true;
    if (existing.type === 'update' && incoming.type === 'remove') return true;
    
    return false;
  }
  
  /**
   * Merge two operations
   */
  private mergeOperations(existing: UpdateOperation, incoming: UpdateOperation): UpdateOperation {
    // Keep the original operation type but update data
    if (existing.type === 'add' && incoming.type === 'update') {
      return {
        ...existing,
        data: { ...existing.data, ...incoming.data },
        timestamp: incoming.timestamp,
        sequence: incoming.sequence,
      };
    }
    
    // Update with latest data
    if (existing.type === 'update' && incoming.type === 'update') {
      return {
        ...existing,
        data: { ...existing.data, ...incoming.data },
        timestamp: incoming.timestamp,
        sequence: incoming.sequence,
      };
    }
    
    // Convert to remove
    if (existing.type === 'update' && incoming.type === 'remove') {
      return {
        ...incoming,
        priority: Math.max(existing.priority, incoming.priority),
      };
    }
    
    return incoming;
  }
  
  /**
   * Calculate priority for an operation
   */
  private calculatePriority(
    type: 'add' | 'update' | 'remove',
    entityType: 'node' | 'edge',
    data: any
  ): number {
    if (this.config.priorityMode === 'fifo') {
      return 0; // All same priority
    }
    
    let priority = 0;
    
    // Priority based on operation type
    if (type === 'remove') priority += 100; // Process removes first
    if (type === 'add') priority += 50; // Then adds
    if (type === 'update') priority += 10; // Updates last
    
    // Priority based on entity type
    if (entityType === 'node') priority += 5; // Nodes before edges
    
    // Smart priority based on data
    if (this.config.priorityMode === 'smart') {
      // High-degree nodes get higher priority
      if (data.degree_centrality && data.degree_centrality > 0.5) {
        priority += 20;
      }
      
      // Recent updates get higher priority
      const age = Date.now() - (data.timestamp || 0);
      if (age < 1000) priority += 10; // Less than 1 second old
    }
    
    return priority;
  }
  
  /**
   * Schedule batch processing
   */
  private scheduleProcessing(): void {
    if (this.processingTimer) return;
    
    this.processingTimer = setTimeout(() => {
      this.processingTimer = null;
      this.processBatch();
    }, this.config.batchDelay);
  }
  
  /**
   * Process a batch of operations
   */
  private async processBatch(): Promise<void> {
    if (this.isProcessing) return;
    
    this.isProcessing = true;
    const startTime = performance.now();
    
    try {
      // Move pending updates to queue
      if (this.config.enableDeduplication) {
        this.queue.push(...this.pendingUpdates.values());
        this.pendingUpdates.clear();
      }
      
      if (this.queue.length === 0) {
        this.isProcessing = false;
        return;
      }
      
      // Sort by priority if needed
      if (this.config.priorityMode !== 'fifo') {
        this.queue.sort((a, b) => b.priority - a.priority);
      }
      
      // Extract batch
      const batch = this.queue.splice(0, this.config.batchSize);
      
      // Convert to delta format
      const delta: GraphDelta = {
        operation: 'update',
        nodes_added: [],
        nodes_updated: [],
        nodes_removed: [],
        edges_added: [],
        edges_updated: [],
        edges_removed: [],
        timestamp: Date.now(),
        sequence: Math.max(...batch.map(op => op.sequence), this.lastSequence + 1),
      };
      
      // Group operations by type
      for (const op of batch) {
        if (op.entityType === 'node') {
          switch (op.type) {
            case 'add':
              delta.nodes_added.push(op.data);
              break;
            case 'update':
              delta.nodes_updated.push(op.data);
              break;
            case 'remove':
              delta.nodes_removed.push(op.data.id);
              break;
          }
        } else if (op.entityType === 'edge') {
          switch (op.type) {
            case 'add':
              delta.edges_added.push(op.data);
              break;
            case 'update':
              delta.edges_updated.push(op.data);
              break;
            case 'remove':
              delta.edges_removed.push([op.data.source, op.data.target]);
              break;
          }
        }
      }
      
      // Update statistics
      const processingTime = performance.now() - startTime;
      this.stats.totalProcessed += batch.length;
      this.stats.avgBatchSize = 
        (this.stats.avgBatchSize * 0.9) + (batch.length * 0.1);
      this.stats.avgProcessingTime = 
        (this.stats.avgProcessingTime * 0.9) + (processingTime * 0.1);
      this.stats.queueSize = this.queue.length;
      this.stats.lastProcessedSequence = delta.sequence;
      this.lastSequence = delta.sequence;
      
      // Notify callback
      this.onBatchProcessed?.(delta);
      
      logger.log('Pipeline: Processed batch', {
        batchSize: batch.length,
        processingTime: processingTime.toFixed(2),
        remainingQueue: this.queue.length,
      });
      
      // Schedule next batch if queue not empty
      if (this.queue.length > 0) {
        this.scheduleProcessing();
      }
      
    } catch (error) {
      logger.error('Pipeline: Error processing batch:', error);
      this.onError?.(error as Error);
    } finally {
      this.isProcessing = false;
    }
  }
  
  /**
   * Set callbacks
   */
  onBatch(callback: (delta: GraphDelta) => void): void {
    this.onBatchProcessed = callback;
  }
  
  onErrorOccurred(callback: (error: Error) => void): void {
    this.onError = callback;
  }
  
  /**
   * Get pipeline statistics
   */
  getStats(): PipelineStats {
    return { ...this.stats };
  }
  
  /**
   * Clear the queue
   */
  clear(): void {
    this.queue = [];
    this.pendingUpdates.clear();
    this.processedIds.clear();
    if (this.processingTimer) {
      clearTimeout(this.processingTimer);
      this.processingTimer = null;
    }
    this.stats.queueSize = 0;
  }
  
  /**
   * Destroy the pipeline
   */
  destroy(): void {
    this.clear();
    this.onBatchProcessed = undefined;
    this.onError = undefined;
  }
}

// Create singleton instance with optimized defaults
export const updatePipeline = new IncrementalUpdatePipeline({
  batchSize: 100,
  batchDelay: 50,
  maxQueueSize: 5000,
  enableDeduplication: true,
  enableMerging: true,
  priorityMode: 'smart',
});