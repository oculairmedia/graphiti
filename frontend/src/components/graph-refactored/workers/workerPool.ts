/**
 * Worker pool manager for efficient parallel processing
 * Manages multiple workers and distributes tasks
 */

import { logger } from '../../../utils/logger';
import type { WorkerMessage, WorkerResponse, WorkerMessageType } from './graphProcessor.worker';

export interface WorkerTask {
  id: string;
  type: WorkerMessageType;
  payload: any;
  priority?: number;
  timeout?: number;
}

export interface WorkerPoolOptions {
  maxWorkers?: number;
  workerPath?: string;
  autoScale?: boolean;
  idleTimeout?: number;
  taskTimeout?: number;
}

interface PooledWorker {
  id: string;
  worker: Worker;
  busy: boolean;
  currentTask: WorkerTask | null;
  taskCount: number;
  errors: number;
  lastUsed: number;
}

interface PendingTask {
  task: WorkerTask;
  resolve: (result: any) => void;
  reject: (error: Error) => void;
  startTime: number;
  timeoutId?: NodeJS.Timeout;
}

/**
 * WorkerPool - Manages a pool of Web Workers for parallel processing
 */
export class WorkerPool {
  private workers: Map<string, PooledWorker> = new Map();
  private taskQueue: PendingTask[] = [];
  private pendingTasks: Map<string, PendingTask> = new Map();
  private options: Required<WorkerPoolOptions>;
  private isTerminated = false;
  private idleCheckInterval?: NodeJS.Timeout;
  private stats = {
    tasksCompleted: 0,
    tasksFailed: 0,
    totalProcessingTime: 0,
    averageProcessingTime: 0
  };

  constructor(options: WorkerPoolOptions = {}) {
    this.options = {
      maxWorkers: options.maxWorkers || navigator.hardwareConcurrency || 4,
      workerPath: options.workerPath || '/workers/graphProcessor.worker.js',
      autoScale: options.autoScale ?? true,
      idleTimeout: options.idleTimeout || 30000,
      taskTimeout: options.taskTimeout || 60000
    };

    // Initialize minimum workers
    this.initializeWorkers(Math.min(2, this.options.maxWorkers));

    // Start idle check
    if (this.options.autoScale) {
      this.startIdleCheck();
    }

    logger.log('WorkerPool: Initialized', {
      maxWorkers: this.options.maxWorkers,
      autoScale: this.options.autoScale
    });
  }

  /**
   * Initialize workers
   */
  private initializeWorkers(count: number): void {
    for (let i = 0; i < count; i++) {
      this.createWorker();
    }
  }

  /**
   * Create a new worker
   */
  private createWorker(): PooledWorker {
    const workerId = `worker-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    
    const worker = new Worker(
      new URL('./graphProcessor.worker.ts', import.meta.url),
      { type: 'module' }
    );

    const pooledWorker: PooledWorker = {
      id: workerId,
      worker,
      busy: false,
      currentTask: null,
      taskCount: 0,
      errors: 0,
      lastUsed: Date.now()
    };

    // Handle worker messages
    worker.addEventListener('message', (event: MessageEvent<WorkerResponse>) => {
      this.handleWorkerResponse(pooledWorker, event.data);
    });

    // Handle worker errors
    worker.addEventListener('error', (error) => {
      logger.error(`WorkerPool: Worker ${workerId} error:`, error);
      pooledWorker.errors++;
      
      // Restart worker if too many errors
      if (pooledWorker.errors > 3) {
        this.restartWorker(pooledWorker);
      }
    });

    this.workers.set(workerId, pooledWorker);
    logger.debug(`WorkerPool: Created worker ${workerId}`);
    
    return pooledWorker;
  }

  /**
   * Restart a failed worker
   */
  private restartWorker(pooledWorker: PooledWorker): void {
    logger.log(`WorkerPool: Restarting worker ${pooledWorker.id}`);
    
    // Terminate old worker
    pooledWorker.worker.terminate();
    
    // Requeue current task if any
    if (pooledWorker.currentTask) {
      const pending = this.pendingTasks.get(pooledWorker.currentTask.id);
      if (pending) {
        this.taskQueue.unshift(pending);
        this.pendingTasks.delete(pooledWorker.currentTask.id);
      }
    }
    
    // Remove from pool
    this.workers.delete(pooledWorker.id);
    
    // Create replacement
    this.createWorker();
    this.processQueue();
  }

  /**
   * Handle worker response
   */
  private handleWorkerResponse(pooledWorker: PooledWorker, response: WorkerResponse): void {
    const pending = this.pendingTasks.get(response.id);
    
    if (!pending) {
      logger.warn(`WorkerPool: Received response for unknown task ${response.id}`);
      return;
    }

    // Clear timeout
    if (pending.timeoutId) {
      clearTimeout(pending.timeoutId);
    }

    // Update stats
    const processingTime = Date.now() - pending.startTime;
    this.stats.totalProcessingTime += processingTime;
    
    if (response.success) {
      this.stats.tasksCompleted++;
      pending.resolve(response.result);
    } else {
      this.stats.tasksFailed++;
      pending.reject(new Error(response.error || 'Unknown error'));
    }
    
    this.stats.averageProcessingTime = 
      this.stats.totalProcessingTime / (this.stats.tasksCompleted + this.stats.tasksFailed);

    // Clean up
    this.pendingTasks.delete(response.id);
    pooledWorker.busy = false;
    pooledWorker.currentTask = null;
    pooledWorker.taskCount++;
    pooledWorker.lastUsed = Date.now();

    logger.debug(`WorkerPool: Task ${response.id} completed`, {
      worker: pooledWorker.id,
      duration: response.duration,
      success: response.success
    });

    // Process next task
    this.processQueue();
  }

  /**
   * Execute a task
   */
  async execute<T = any>(task: WorkerTask): Promise<T> {
    if (this.isTerminated) {
      throw new Error('WorkerPool has been terminated');
    }

    return new Promise((resolve, reject) => {
      const pendingTask: PendingTask = {
        task,
        resolve,
        reject,
        startTime: Date.now()
      };

      // Set timeout
      if (this.options.taskTimeout > 0) {
        pendingTask.timeoutId = setTimeout(() => {
          this.pendingTasks.delete(task.id);
          reject(new Error(`Task ${task.id} timed out after ${this.options.taskTimeout}ms`));
        }, this.options.taskTimeout);
      }

      // Add to queue
      this.pendingTasks.set(task.id, pendingTask);
      
      if (task.priority !== undefined) {
        // Insert based on priority
        const index = this.taskQueue.findIndex(t => 
          (t.task.priority || 0) < (task.priority || 0)
        );
        if (index === -1) {
          this.taskQueue.push(pendingTask);
        } else {
          this.taskQueue.splice(index, 0, pendingTask);
        }
      } else {
        this.taskQueue.push(pendingTask);
      }

      // Scale up if needed
      if (this.options.autoScale && this.shouldScaleUp()) {
        this.scaleUp();
      }

      // Process queue
      this.processQueue();
    });
  }

  /**
   * Execute multiple tasks in parallel
   */
  async executeMany<T = any>(tasks: WorkerTask[]): Promise<T[]> {
    const promises = tasks.map(task => this.execute<T>(task));
    return Promise.all(promises);
  }

  /**
   * Execute tasks with map-reduce pattern
   */
  async mapReduce<T, R>(
    data: T[],
    mapFn: (item: T) => WorkerTask,
    reduceFn: (results: any[]) => R
  ): Promise<R> {
    // Create map tasks
    const tasks = data.map((item, index) => ({
      ...mapFn(item),
      id: `map-${index}-${Date.now()}`
    }));

    // Execute in parallel
    const results = await this.executeMany(tasks);

    // Reduce results
    return reduceFn(results);
  }

  /**
   * Process task queue
   */
  private processQueue(): void {
    if (this.taskQueue.length === 0) return;

    // Find available worker
    const availableWorker = Array.from(this.workers.values()).find(w => !w.busy);
    
    if (!availableWorker) {
      // All workers busy
      if (this.options.autoScale && this.shouldScaleUp()) {
        this.scaleUp();
      }
      return;
    }

    // Get next task
    const pending = this.taskQueue.shift();
    if (!pending) return;

    // Assign task to worker
    availableWorker.busy = true;
    availableWorker.currentTask = pending.task;
    availableWorker.lastUsed = Date.now();

    // Send task to worker
    const message: WorkerMessage = {
      id: pending.task.id,
      type: pending.task.type,
      payload: pending.task.payload
    };

    availableWorker.worker.postMessage(message);

    logger.debug(`WorkerPool: Task ${pending.task.id} assigned to ${availableWorker.id}`);

    // Continue processing
    if (this.taskQueue.length > 0) {
      this.processQueue();
    }
  }

  /**
   * Check if should scale up
   */
  private shouldScaleUp(): boolean {
    if (this.workers.size >= this.options.maxWorkers) return false;
    
    const busyWorkers = Array.from(this.workers.values()).filter(w => w.busy).length;
    const queueLength = this.taskQueue.length;
    
    // Scale up if all workers busy and queue is growing
    return busyWorkers === this.workers.size && queueLength > 0;
  }

  /**
   * Scale up worker pool
   */
  private scaleUp(): void {
    if (this.workers.size >= this.options.maxWorkers) return;
    
    const newWorker = this.createWorker();
    logger.log(`WorkerPool: Scaled up to ${this.workers.size} workers`);
    
    // Immediately assign task if available
    this.processQueue();
  }

  /**
   * Scale down worker pool
   */
  private scaleDown(): void {
    if (this.workers.size <= 2) return; // Keep minimum workers
    
    // Find least used idle worker
    const idleWorkers = Array.from(this.workers.values())
      .filter(w => !w.busy)
      .sort((a, b) => a.lastUsed - b.lastUsed);
    
    if (idleWorkers.length === 0) return;
    
    const workerToRemove = idleWorkers[0];
    const now = Date.now();
    
    if (now - workerToRemove.lastUsed > this.options.idleTimeout) {
      workerToRemove.worker.terminate();
      this.workers.delete(workerToRemove.id);
      logger.log(`WorkerPool: Scaled down to ${this.workers.size} workers`);
    }
  }

  /**
   * Start idle check interval
   */
  private startIdleCheck(): void {
    this.idleCheckInterval = setInterval(() => {
      this.scaleDown();
    }, 10000); // Check every 10 seconds
  }

  /**
   * Cancel a task
   */
  cancel(taskId: string): boolean {
    // Remove from queue
    const queueIndex = this.taskQueue.findIndex(t => t.task.id === taskId);
    if (queueIndex >= 0) {
      const pending = this.taskQueue.splice(queueIndex, 1)[0];
      if (pending.timeoutId) {
        clearTimeout(pending.timeoutId);
      }
      pending.reject(new Error('Task cancelled'));
      this.pendingTasks.delete(taskId);
      return true;
    }

    // Cancel if running
    const pending = this.pendingTasks.get(taskId);
    if (pending) {
      // Send cancel message to worker
      const worker = Array.from(this.workers.values()).find(
        w => w.currentTask?.id === taskId
      );
      if (worker) {
        worker.worker.postMessage({
          id: `cancel-${taskId}`,
          type: 'CANCEL',
          payload: { taskId }
        });
      }
      
      if (pending.timeoutId) {
        clearTimeout(pending.timeoutId);
      }
      pending.reject(new Error('Task cancelled'));
      this.pendingTasks.delete(taskId);
      return true;
    }

    return false;
  }

  /**
   * Cancel all tasks
   */
  cancelAll(): void {
    // Clear queue
    this.taskQueue.forEach(pending => {
      if (pending.timeoutId) {
        clearTimeout(pending.timeoutId);
      }
      pending.reject(new Error('All tasks cancelled'));
    });
    this.taskQueue = [];

    // Cancel running tasks
    this.pendingTasks.forEach((pending, taskId) => {
      this.cancel(taskId);
    });
  }

  /**
   * Get pool statistics
   */
  getStats(): {
    workers: number;
    busyWorkers: number;
    queueLength: number;
    tasksCompleted: number;
    tasksFailed: number;
    averageProcessingTime: number;
  } {
    const busyWorkers = Array.from(this.workers.values()).filter(w => w.busy).length;
    
    return {
      workers: this.workers.size,
      busyWorkers,
      queueLength: this.taskQueue.length,
      ...this.stats
    };
  }

  /**
   * Terminate all workers
   */
  terminate(): void {
    this.isTerminated = true;
    
    // Stop idle check
    if (this.idleCheckInterval) {
      clearInterval(this.idleCheckInterval);
    }

    // Cancel all tasks
    this.cancelAll();

    // Terminate workers
    this.workers.forEach(worker => {
      worker.worker.terminate();
    });
    this.workers.clear();

    logger.log('WorkerPool: Terminated');
  }
}

// Singleton instance
let defaultPool: WorkerPool | null = null;

/**
 * Get default worker pool instance
 */
export function getDefaultWorkerPool(): WorkerPool {
  if (!defaultPool) {
    defaultPool = new WorkerPool();
  }
  return defaultPool;
}

/**
 * Terminate default worker pool
 */
export function terminateDefaultWorkerPool(): void {
  if (defaultPool) {
    defaultPool.terminate();
    defaultPool = null;
  }
}