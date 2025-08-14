/**
 * Fallback strategies for handling update failures in graph visualization
 * Implements multiple layers of recovery for robust real-time updates
 */

import { GraphNode, GraphLink } from '@/types/graph';

export interface UpdateAttempt {
  operation: string;
  data: any;
  error: Error;
  attemptNumber: number;
  timestamp: number;
}

export interface FallbackStrategy {
  name: string;
  priority: number;
  maxRetries: number;
  retryDelay: number;
  canHandle: (attempt: UpdateAttempt) => boolean;
  execute: (attempt: UpdateAttempt) => Promise<boolean>;
}

export interface FallbackConfig {
  enableRetries: boolean;
  maxGlobalRetries: number;
  enableQueueing: boolean;
  queueMaxSize: number;
  enableBatching: boolean;
  batchDelay: number;
  enableFullReload: boolean;
  onFallbackTriggered?: (strategy: string, attempt: UpdateAttempt) => void;
  onAllFallbacksFailed?: (attempt: UpdateAttempt) => void;
}

/**
 * Queue for failed updates to retry later
 */
export class UpdateQueue {
  private queue: UpdateAttempt[] = [];
  private maxSize: number;
  private processing = false;
  
  constructor(maxSize = 100) {
    this.maxSize = maxSize;
  }
  
  enqueue(attempt: UpdateAttempt): boolean {
    if (this.queue.length >= this.maxSize) {
      // Remove oldest item if queue is full
      this.queue.shift();
    }
    this.queue.push(attempt);
    return true;
  }
  
  async processQueue(
    handler: (attempt: UpdateAttempt) => Promise<boolean>,
    delay = 100
  ): Promise<void> {
    if (this.processing || this.queue.length === 0) {
      return;
    }
    
    this.processing = true;
    
    while (this.queue.length > 0) {
      const attempt = this.queue.shift()!;
      
      try {
        const success = await handler(attempt);
        if (!success) {
          // Re-queue if still failing
          if (attempt.attemptNumber < 3) {
            attempt.attemptNumber++;
            this.queue.push(attempt);
          }
        }
      } catch (error) {
        console.error('[UpdateQueue] Failed to process attempt:', error);
      }
      
      // Delay between processing attempts
      await new Promise(resolve => setTimeout(resolve, delay));
    }
    
    this.processing = false;
  }
  
  clear(): void {
    this.queue = [];
  }
  
  size(): number {
    return this.queue.length;
  }
}

/**
 * Batch accumulator for combining multiple updates
 */
export class UpdateBatcher {
  private pendingNodes: Map<string, GraphNode> = new Map();
  private pendingEdges: Map<string, GraphLink> = new Map();
  private pendingRemovals: {
    nodes: Set<string>;
    edges: Set<string>;
  } = { nodes: new Set(), edges: new Set() };
  
  private flushTimer?: NodeJS.Timeout;
  private batchDelay: number;
  private onFlush: (batch: any) => Promise<void>;
  
  constructor(
    batchDelay = 100,
    onFlush: (batch: any) => Promise<void> = async () => {}
  ) {
    this.batchDelay = batchDelay;
    this.onFlush = onFlush;
  }
  
  addNodes(nodes: GraphNode[]): void {
    nodes.forEach(node => {
      this.pendingNodes.set(node.id, node);
      // Remove from pending removals if present
      this.pendingRemovals.nodes.delete(node.id);
    });
    this.scheduleFlush();
  }
  
  addEdges(edges: GraphLink[]): void {
    edges.forEach(edge => {
      const edgeId = `${edge.source}-${edge.target}`;
      this.pendingEdges.set(edgeId, edge);
      // Remove from pending removals if present
      this.pendingRemovals.edges.delete(edgeId);
    });
    this.scheduleFlush();
  }
  
  removeNodes(nodeIds: string[]): void {
    nodeIds.forEach(id => {
      this.pendingNodes.delete(id);
      this.pendingRemovals.nodes.add(id);
    });
    this.scheduleFlush();
  }
  
  removeEdges(edgeIds: string[]): void {
    edgeIds.forEach(id => {
      this.pendingEdges.delete(id);
      this.pendingRemovals.edges.add(id);
    });
    this.scheduleFlush();
  }
  
  private scheduleFlush(): void {
    if (this.flushTimer) {
      clearTimeout(this.flushTimer);
    }
    
    this.flushTimer = setTimeout(() => {
      this.flush();
    }, this.batchDelay);
  }
  
  async flush(): Promise<void> {
    if (this.flushTimer) {
      clearTimeout(this.flushTimer);
      this.flushTimer = undefined;
    }
    
    const batch = {
      addNodes: Array.from(this.pendingNodes.values()),
      addEdges: Array.from(this.pendingEdges.values()),
      removeNodes: Array.from(this.pendingRemovals.nodes),
      removeEdges: Array.from(this.pendingRemovals.edges)
    };
    
    // Clear pending data
    this.pendingNodes.clear();
    this.pendingEdges.clear();
    this.pendingRemovals.nodes.clear();
    this.pendingRemovals.edges.clear();
    
    // Execute flush callback if there's data
    if (batch.addNodes.length > 0 || batch.addEdges.length > 0 ||
        batch.removeNodes.length > 0 || batch.removeEdges.length > 0) {
      await this.onFlush(batch);
    }
  }
  
  clear(): void {
    if (this.flushTimer) {
      clearTimeout(this.flushTimer);
      this.flushTimer = undefined;
    }
    this.pendingNodes.clear();
    this.pendingEdges.clear();
    this.pendingRemovals.nodes.clear();
    this.pendingRemovals.edges.clear();
  }
}

/**
 * Strategy 1: Simple retry with exponential backoff
 */
export class RetryStrategy implements FallbackStrategy {
  name = 'retry-with-backoff';
  priority = 1;
  maxRetries = 3;
  retryDelay = 100;
  
  private attemptHandler?: (attempt: UpdateAttempt) => Promise<boolean>;
  
  constructor(handler?: (attempt: UpdateAttempt) => Promise<boolean>) {
    this.attemptHandler = handler;
  }
  
  canHandle(attempt: UpdateAttempt): boolean {
    // Can handle any error if we haven't exceeded retry limit
    return attempt.attemptNumber <= this.maxRetries;
  }
  
  async execute(attempt: UpdateAttempt): Promise<boolean> {
    const delay = this.retryDelay * Math.pow(2, attempt.attemptNumber - 1);
    
    console.log(`[RetryStrategy] Retrying ${attempt.operation} after ${delay}ms (attempt ${attempt.attemptNumber}/${this.maxRetries})`);
    
    await new Promise(resolve => setTimeout(resolve, delay));
    
    if (this.attemptHandler) {
      return await this.attemptHandler(attempt);
    }
    
    return false;
  }
}

/**
 * Strategy 2: Queue failed updates for later processing
 */
export class QueueStrategy implements FallbackStrategy {
  name = 'queue-for-later';
  priority = 2;
  maxRetries = 1;
  retryDelay = 0;
  
  private queue: UpdateQueue;
  
  constructor(queue: UpdateQueue) {
    this.queue = queue;
  }
  
  canHandle(attempt: UpdateAttempt): boolean {
    // Queue any failed update
    return true;
  }
  
  async execute(attempt: UpdateAttempt): Promise<boolean> {
    console.log(`[QueueStrategy] Queueing ${attempt.operation} for later processing`);
    return this.queue.enqueue(attempt);
  }
}

/**
 * Strategy 3: Batch updates together
 */
export class BatchStrategy implements FallbackStrategy {
  name = 'batch-updates';
  priority = 3;
  maxRetries = 1;
  retryDelay = 0;
  
  private batcher: UpdateBatcher;
  
  constructor(batcher: UpdateBatcher) {
    this.batcher = batcher;
  }
  
  canHandle(attempt: UpdateAttempt): boolean {
    // Can batch node and edge operations
    return ['addNodes', 'addEdges', 'removeNodes', 'removeEdges'].includes(attempt.operation);
  }
  
  async execute(attempt: UpdateAttempt): Promise<boolean> {
    console.log(`[BatchStrategy] Batching ${attempt.operation} for combined update`);
    
    switch (attempt.operation) {
      case 'addNodes':
        this.batcher.addNodes(attempt.data.nodes || []);
        return true;
      case 'addEdges':
        this.batcher.addEdges(attempt.data.edges || []);
        return true;
      case 'removeNodes':
        this.batcher.removeNodes(attempt.data.nodeIds || []);
        return true;
      case 'removeEdges':
        this.batcher.removeEdges(attempt.data.edgeIds || []);
        return true;
      default:
        return false;
    }
  }
}

/**
 * Strategy 4: Skip non-critical updates
 */
export class SkipStrategy implements FallbackStrategy {
  name = 'skip-non-critical';
  priority = 4;
  maxRetries = 0;
  retryDelay = 0;
  
  canHandle(attempt: UpdateAttempt): boolean {
    // Skip update operations (not add/remove)
    return attempt.operation === 'updateNodes' || attempt.operation === 'updateEdges';
  }
  
  async execute(attempt: UpdateAttempt): Promise<boolean> {
    console.log(`[SkipStrategy] Skipping non-critical ${attempt.operation}`);
    return true; // Return true to indicate "handled" by skipping
  }
}

/**
 * Strategy 5: Request full reload as last resort
 */
export class FullReloadStrategy implements FallbackStrategy {
  name = 'full-reload';
  priority = 10; // Lowest priority (last resort)
  maxRetries = 1;
  retryDelay = 0;
  
  private reloadHandler?: () => Promise<boolean>;
  
  constructor(handler?: () => Promise<boolean>) {
    this.reloadHandler = handler;
  }
  
  canHandle(attempt: UpdateAttempt): boolean {
    // Last resort for any error after other strategies failed
    return attempt.attemptNumber > 3;
  }
  
  async execute(attempt: UpdateAttempt): Promise<boolean> {
    console.log(`[FullReloadStrategy] Requesting full graph reload after failed ${attempt.operation}`);
    
    if (this.reloadHandler) {
      return await this.reloadHandler();
    }
    
    return false;
  }
}

/**
 * Main fallback orchestrator
 */
export class FallbackOrchestrator {
  private strategies: FallbackStrategy[] = [];
  private config: FallbackConfig;
  private queue: UpdateQueue;
  private batcher: UpdateBatcher;
  
  constructor(config: Partial<FallbackConfig> = {}) {
    this.config = {
      enableRetries: true,
      maxGlobalRetries: 5,
      enableQueueing: true,
      queueMaxSize: 100,
      enableBatching: true,
      batchDelay: 100,
      enableFullReload: true,
      ...config
    };
    
    this.queue = new UpdateQueue(this.config.queueMaxSize);
    this.batcher = new UpdateBatcher(
      this.config.batchDelay,
      async (batch) => this.handleBatchFlush(batch)
    );
    
    this.initializeStrategies();
  }
  
  private initializeStrategies(): void {
    if (this.config.enableRetries) {
      this.addStrategy(new RetryStrategy());
    }
    
    if (this.config.enableQueueing) {
      this.addStrategy(new QueueStrategy(this.queue));
    }
    
    if (this.config.enableBatching) {
      this.addStrategy(new BatchStrategy(this.batcher));
    }
    
    // Always add skip strategy for non-critical updates
    this.addStrategy(new SkipStrategy());
    
    if (this.config.enableFullReload) {
      this.addStrategy(new FullReloadStrategy());
    }
    
    // Sort strategies by priority
    this.strategies.sort((a, b) => a.priority - b.priority);
  }
  
  addStrategy(strategy: FallbackStrategy): void {
    this.strategies.push(strategy);
    this.strategies.sort((a, b) => a.priority - b.priority);
  }
  
  async handleFailure(attempt: UpdateAttempt): Promise<boolean> {
    console.log(`[FallbackOrchestrator] Handling failure for ${attempt.operation} (attempt ${attempt.attemptNumber})`);
    
    // Try each strategy in priority order
    for (const strategy of this.strategies) {
      if (strategy.canHandle(attempt)) {
        console.log(`[FallbackOrchestrator] Trying strategy: ${strategy.name}`);
        this.config.onFallbackTriggered?.(strategy.name, attempt);
        
        try {
          const success = await strategy.execute(attempt);
          if (success) {
            console.log(`[FallbackOrchestrator] Strategy ${strategy.name} succeeded`);
            return true;
          }
        } catch (error) {
          console.error(`[FallbackOrchestrator] Strategy ${strategy.name} failed:`, error);
        }
      }
    }
    
    // All strategies failed
    console.error(`[FallbackOrchestrator] All fallback strategies failed for ${attempt.operation}`);
    this.config.onAllFallbacksFailed?.(attempt);
    return false;
  }
  
  private async handleBatchFlush(batch: any): Promise<void> {
    // This would be connected to the actual update handler
    console.log('[FallbackOrchestrator] Flushing batch:', {
      nodes: batch.addNodes.length,
      edges: batch.addEdges.length,
      removeNodes: batch.removeNodes.length,
      removeEdges: batch.removeEdges.length
    });
  }
  
  async processQueue(
    handler: (attempt: UpdateAttempt) => Promise<boolean>
  ): Promise<void> {
    await this.queue.processQueue(handler);
  }
  
  async flushBatch(): Promise<void> {
    await this.batcher.flush();
  }
  
  clear(): void {
    this.queue.clear();
    this.batcher.clear();
  }
  
  getMetrics(): {
    queueSize: number;
    strategiesCount: number;
  } {
    return {
      queueSize: this.queue.size(),
      strategiesCount: this.strategies.length
    };
  }
}

/**
 * Error classifier to determine error severity and recovery approach
 */
export class ErrorClassifier {
  static classify(error: Error): {
    severity: 'low' | 'medium' | 'high' | 'critical';
    recoverable: boolean;
    suggestedStrategy: string;
  } {
    const errorMessage = error.message.toLowerCase();
    
    // Network errors - usually recoverable with retry
    if (errorMessage.includes('network') || errorMessage.includes('fetch')) {
      return {
        severity: 'medium',
        recoverable: true,
        suggestedStrategy: 'retry-with-backoff'
      };
    }
    
    // Timeout errors - may need batching or queueing
    if (errorMessage.includes('timeout')) {
      return {
        severity: 'medium',
        recoverable: true,
        suggestedStrategy: 'queue-for-later'
      };
    }
    
    // Memory errors - need full reload
    if (errorMessage.includes('memory') || errorMessage.includes('heap')) {
      return {
        severity: 'critical',
        recoverable: false,
        suggestedStrategy: 'full-reload'
      };
    }
    
    // Data validation errors - skip update
    if (errorMessage.includes('invalid') || errorMessage.includes('validation')) {
      return {
        severity: 'low',
        recoverable: false,
        suggestedStrategy: 'skip-non-critical'
      };
    }
    
    // WebGL/rendering errors - may need reload
    if (errorMessage.includes('webgl') || errorMessage.includes('context')) {
      return {
        severity: 'high',
        recoverable: false,
        suggestedStrategy: 'full-reload'
      };
    }
    
    // Default classification
    return {
      severity: 'medium',
      recoverable: true,
      suggestedStrategy: 'retry-with-backoff'
    };
  }
}

export default FallbackOrchestrator;