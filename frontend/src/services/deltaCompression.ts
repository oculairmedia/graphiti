// Delta compression and intelligent update batching

import { ConflictResolver, GraphDelta, DeltaOperation } from './conflictResolution';

export interface CompressedDelta {
  id: string;
  timestamp: number;
  compressed: boolean;
  encoding: 'json' | 'binary' | 'diff';
  data: string | ArrayBuffer;
  originalSize: number;
  compressedSize: number;
  checksum: string;
}

export interface UpdateBatch {
  id: string;
  priority: number;
  timestamp: number;
  updates: GraphDelta[];
  compressed?: CompressedDelta;
  dependencies: string[];
}

export interface BatchingOptions {
  maxBatchSize: number;
  maxBatchTime: number;
  priorityThreshold: number;
  compressionThreshold: number;
  enableDiffCompression: boolean;
}

// Priority queue for update batching
class PriorityQueue<T> {
  private items: { item: T; priority: number }[] = [];

  enqueue(item: T, priority: number): void {
    const newItem = { item, priority };
    let added = false;

    for (let i = 0; i < this.items.length; i++) {
      if (priority > this.items[i].priority) {
        this.items.splice(i, 0, newItem);
        added = true;
        break;
      }
    }

    if (!added) {
      this.items.push(newItem);
    }
  }

  dequeue(): T | undefined {
    const item = this.items.shift();
    return item?.item;
  }

  peek(): T | undefined {
    return this.items[0]?.item;
  }

  size(): number {
    return this.items.length;
  }

  clear(): void {
    this.items = [];
  }

  getItems(): T[] {
    return this.items.map(i => i.item);
  }
}

// Delta compression engine
export class DeltaCompressor {
  private compressionWorker: Worker | null = null;
  private previousStates = new Map<string, any>();

  constructor(private enableWorker = true) {
    if (enableWorker && typeof Worker !== 'undefined') {
      this.initializeWorker();
    }
  }

  private initializeWorker(): void {
    const workerCode = `
      self.onmessage = function(e) {
        const { type, data } = e.data;
        
        switch (type) {
          case 'compress':
            const compressed = compressData(data);
            self.postMessage({ type: 'compressed', data: compressed });
            break;
          case 'decompress':
            const decompressed = decompressData(data);
            self.postMessage({ type: 'decompressed', data: decompressed });
            break;
        }
      };
      
      function compressData(data) {
        // Simple compression using JSON minification
        // In production, use a proper compression library
        const json = JSON.stringify(data);
        const minified = json.replace(/\\s+/g, '');
        return {
          original: json,
          compressed: minified,
          ratio: minified.length / json.length
        };
      }
      
      function decompressData(data) {
        return JSON.parse(data.compressed || data.original);
      }
    `;

    const blob = new Blob([workerCode], { type: 'application/javascript' });
    const workerUrl = URL.createObjectURL(blob);
    this.compressionWorker = new Worker(workerUrl);
    // Clean up the object URL after creating the worker
    URL.revokeObjectURL(workerUrl);
  }

  async compressDelta(delta: GraphDelta): Promise<CompressedDelta> {
    const originalData = JSON.stringify(delta);
    const originalSize = originalData.length;

    // Try diff compression first if we have previous state
    if (this.previousStates.has(delta.sourceId)) {
      const diffCompressed = this.createDiff(delta);
      if (diffCompressed && diffCompressed.compressedSize < originalSize * 0.5) {
        return diffCompressed;
      }
    }

    // Fall back to standard compression
    if (this.compressionWorker) {
      return await this.compressWithWorker(delta, originalData, originalSize);
    } else {
      return this.compressSync(delta, originalData, originalSize);
    }
  }

  private createDiff(delta: GraphDelta): CompressedDelta | null {
    const previousState = this.previousStates.get(delta.sourceId);
    if (!previousState) return null;

    const diff = this.computeDiff(previousState, delta);
    const diffStr = JSON.stringify(diff);

    // Store current state for next diff
    this.previousStates.set(delta.sourceId, delta);

    return {
      id: delta.id,
      timestamp: delta.timestamp,
      compressed: true,
      encoding: 'diff',
      data: diffStr,
      originalSize: JSON.stringify(delta).length,
      compressedSize: diffStr.length,
      checksum: this.calculateChecksum(diffStr)
    };
  }

  private computeDiff(oldObj: any, newObj: any): any {
    const diff: any = {};

    // Find additions and modifications
    for (const key in newObj) {
      if (!(key in oldObj)) {
        diff['+' + key] = newObj[key];
      } else if (JSON.stringify(oldObj[key]) !== JSON.stringify(newObj[key])) {
        if (typeof newObj[key] === 'object' && typeof oldObj[key] === 'object') {
          diff['~' + key] = this.computeDiff(oldObj[key], newObj[key]);
        } else {
          diff['~' + key] = newObj[key];
        }
      }
    }

    // Find deletions
    for (const key in oldObj) {
      if (!(key in newObj)) {
        diff['-' + key] = null;
      }
    }

    return diff;
  }

  private async compressWithWorker(
    delta: GraphDelta,
    originalData: string,
    originalSize: number
  ): Promise<CompressedDelta> {
    return new Promise((resolve) => {
      const handler = (e: MessageEvent) => {
        if (e.data.type === 'compressed') {
          this.compressionWorker?.removeEventListener('message', handler);
          
          resolve({
            id: delta.id,
            timestamp: delta.timestamp,
            compressed: true,
            encoding: 'json',
            data: e.data.data.compressed,
            originalSize,
            compressedSize: e.data.data.compressed.length,
            checksum: this.calculateChecksum(e.data.data.compressed)
          });
        }
      };

      this.compressionWorker?.addEventListener('message', handler);
      this.compressionWorker?.postMessage({ type: 'compress', data: delta });
    });
  }

  private compressSync(
    delta: GraphDelta,
    originalData: string,
    originalSize: number
  ): CompressedDelta {
    // Simple compression: remove whitespace and use shorter keys
    const compressed = this.minifyJson(delta);
    const compressedStr = JSON.stringify(compressed);

    return {
      id: delta.id,
      timestamp: delta.timestamp,
      compressed: true,
      encoding: 'json',
      data: compressedStr,
      originalSize,
      compressedSize: compressedStr.length,
      checksum: this.calculateChecksum(compressedStr)
    };
  }

  private minifyJson(obj: any): any {
    // Map long keys to short ones
    const keyMap: Record<string, string> = {
      'operations': 'o',
      'timestamp': 't',
      'version': 'v',
      'sourceId': 's',
      'dependencies': 'd',
      'type': 'ty',
      'target': 'tg',
      'targetId': 'ti',
      'data': 'dt'
    };

    if (Array.isArray(obj)) {
      return obj.map(item => this.minifyJson(item));
    }

    if (typeof obj === 'object' && obj !== null) {
      const minified: any = {};
      
      for (const [key, value] of Object.entries(obj)) {
        const newKey = keyMap[key] || key;
        minified[newKey] = this.minifyJson(value);
      }
      
      return minified;
    }

    return obj;
  }

  async decompressDelta(compressed: CompressedDelta): Promise<GraphDelta> {
    if (!compressed.compressed) {
      return JSON.parse(compressed.data as string);
    }

    // Verify checksum
    const checksum = this.calculateChecksum(compressed.data as string);
    if (checksum !== compressed.checksum) {
      throw new Error('Checksum mismatch - data may be corrupted');
    }

    switch (compressed.encoding) {
      case 'diff':
        return this.applyDiff(compressed);
      
      case 'binary':
        return this.decompressBinary(compressed);
      
      case 'json':
      default:
        return this.decompressJson(compressed);
    }
  }

  private applyDiff(compressed: CompressedDelta): GraphDelta {
    const diff = JSON.parse(compressed.data as string);
    const previousState = this.previousStates.get(compressed.id) || {};
    
    return this.mergeDiff(previousState, diff);
  }

  private mergeDiff(base: any, diff: any): any {
    const result = { ...base };

    for (const key in diff) {
      const operation = key[0];
      const actualKey = key.substring(1);

      switch (operation) {
        case '+': // Addition
          result[actualKey] = diff[key];
          break;
        case '~': // Modification
          if (typeof diff[key] === 'object' && typeof result[actualKey] === 'object') {
            result[actualKey] = this.mergeDiff(result[actualKey], diff[key]);
          } else {
            result[actualKey] = diff[key];
          }
          break;
        case '-': // Deletion
          delete result[actualKey];
          break;
        default:
          result[key] = diff[key]; // No operation prefix
      }
    }

    return result;
  }

  private decompressBinary(compressed: CompressedDelta): GraphDelta {
    // Decode binary data (placeholder - implement actual binary decoding)
    const decoder = new TextDecoder();
    const json = decoder.decode(compressed.data as ArrayBuffer);
    return JSON.parse(json);
  }

  private decompressJson(compressed: CompressedDelta): GraphDelta {
    const minified = JSON.parse(compressed.data as string);
    return this.expandJson(minified);
  }

  private expandJson(obj: any): any {
    // Reverse the minification
    const keyMap: Record<string, string> = {
      'o': 'operations',
      't': 'timestamp',
      'v': 'version',
      's': 'sourceId',
      'd': 'dependencies',
      'ty': 'type',
      'tg': 'target',
      'ti': 'targetId',
      'dt': 'data'
    };

    if (Array.isArray(obj)) {
      return obj.map(item => this.expandJson(item));
    }

    if (typeof obj === 'object' && obj !== null) {
      const expanded: any = {};
      
      for (const [key, value] of Object.entries(obj)) {
        const newKey = keyMap[key] || key;
        expanded[newKey] = this.expandJson(value);
      }
      
      return expanded;
    }

    return obj;
  }

  private calculateChecksum(data: string): string {
    // Simple checksum using hash
    let hash = 0;
    
    for (let i = 0; i < data.length; i++) {
      const char = data.charCodeAt(i);
      hash = ((hash << 5) - hash) + char;
      hash = hash & hash; // Convert to 32-bit integer
    }
    
    return hash.toString(16);
  }

  destroy(): void {
    if (this.compressionWorker) {
      this.compressionWorker.terminate();
      this.compressionWorker = null;
    }
    this.previousStates.clear();
  }
}

// Intelligent update batcher
export class UpdateBatcher {
  private queue = new PriorityQueue<GraphDelta>();
  private batchTimer: number | null = null;
  private currentBatch: GraphDelta[] = [];
  private compressor: DeltaCompressor;
  private conflictResolver: ConflictResolver;

  constructor(
    private options: BatchingOptions,
    private onBatchReady: (batch: UpdateBatch) => void
  ) {
    this.compressor = new DeltaCompressor();
    this.conflictResolver = new ConflictResolver('batcher', 'operational-transform');
  }

  addUpdate(delta: GraphDelta, priority: number = 0): void {
    // Check for duplicates
    if (this.isDuplicate(delta)) {
      console.log(`[Batcher] Skipping duplicate update ${delta.id}`);
      return;
    }

    // Add to priority queue
    this.queue.enqueue(delta, priority);

    // Check if we should process immediately
    if (priority >= this.options.priorityThreshold) {
      this.processBatch();
    } else if (!this.batchTimer) {
      // Start batch timer
      this.batchTimer = window.setTimeout(() => {
        this.processBatch();
      }, this.options.maxBatchTime);
    }

    // Check batch size limit
    if (this.queue.size() >= this.options.maxBatchSize) {
      this.processBatch();
    }
  }

  private isDuplicate(delta: GraphDelta): boolean {
    // Check current batch
    if (this.currentBatch.some(d => d.id === delta.id)) {
      return true;
    }

    // Check queue
    const queueItems = this.queue.getItems();
    return queueItems.some(d => d.id === delta.id);
  }

  private async processBatch(): Promise<void> {
    // Clear timer
    if (this.batchTimer) {
      clearTimeout(this.batchTimer);
      this.batchTimer = null;
    }

    // Get all updates from queue
    const updates: GraphDelta[] = [];
    while (this.queue.size() > 0) {
      const update = this.queue.dequeue();
      if (update) {
        updates.push(update);
      }
    }

    if (updates.length === 0) return;

    // Merge compatible updates
    const merged = this.mergeUpdates(updates);

    // Resolve conflicts
    const conflicts = this.conflictResolver.detectConflicts(merged, []);
    const resolution = this.conflictResolver.resolve(conflicts);

    // Apply resolved updates
    const finalUpdates = [
      ...resolution.acceptedChanges,
      ...resolution.mergedChanges
    ];

    // Create batch
    const batch: UpdateBatch = {
      id: `batch-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      priority: this.calculateBatchPriority(finalUpdates),
      timestamp: Date.now(),
      updates: finalUpdates,
      dependencies: this.extractDependencies(finalUpdates)
    };

    // Compress if beneficial
    if (this.shouldCompress(batch)) {
      batch.compressed = await this.compressBatch(batch);
    }

    // Clear current batch
    this.currentBatch = [];

    // Send batch
    this.onBatchReady(batch);
  }

  private mergeUpdates(updates: GraphDelta[]): GraphDelta[] {
    const merged: GraphDelta[] = [];
    const processed = new Set<string>();

    for (const update of updates) {
      if (processed.has(update.id)) continue;

      // Find other updates that can be merged
      const mergeable = updates.filter(u => 
        !processed.has(u.id) &&
        u.id !== update.id &&
        this.canMerge(update, u)
      );

      if (mergeable.length > 0) {
        const mergedUpdate = this.performMerge(update, mergeable);
        merged.push(mergedUpdate);
        
        processed.add(update.id);
        mergeable.forEach(u => processed.add(u.id));
      } else {
        merged.push(update);
        processed.add(update.id);
      }
    }

    return merged;
  }

  private canMerge(a: GraphDelta, b: GraphDelta): boolean {
    // Can merge if:
    // 1. Same source
    // 2. No conflicting operations
    // 3. Within time window
    
    if (a.sourceId !== b.sourceId) return false;
    
    const timeDiff = Math.abs(a.timestamp - b.timestamp);
    if (timeDiff > 1000) return false; // 1 second window
    
    // Check for conflicting operations
    const aTargets = new Set(a.operations.map(op => `${op.target}:${op.targetId}`));
    const bTargets = new Set(b.operations.map(op => `${op.target}:${op.targetId}`));
    
    for (const target of aTargets) {
      if (bTargets.has(target)) {
        return false; // Conflict
      }
    }
    
    return true;
  }

  private performMerge(base: GraphDelta, others: GraphDelta[]): GraphDelta {
    const allOperations = [...base.operations];
    const allDependencies = [...base.dependencies];
    
    for (const other of others) {
      allOperations.push(...other.operations);
      allDependencies.push(...other.dependencies);
    }
    
    return {
      id: `merged-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      timestamp: base.timestamp,
      operations: allOperations,
      version: base.version,
      sourceId: base.sourceId,
      dependencies: [...new Set(allDependencies)] // Remove duplicates
    };
  }

  private calculateBatchPriority(updates: GraphDelta[]): number {
    if (updates.length === 0) return 0;
    
    // Use highest priority from updates
    return Math.max(...updates.map(u => {
      // Calculate priority based on operation types
      const hasRemove = u.operations.some(op => op.type === 'remove');
      const hasAdd = u.operations.some(op => op.type === 'add');
      
      if (hasRemove) return 10; // High priority for deletions
      if (hasAdd) return 5; // Medium priority for additions
      return 1; // Low priority for updates
    }));
  }

  private extractDependencies(updates: GraphDelta[]): string[] {
    const deps = new Set<string>();
    
    for (const update of updates) {
      update.dependencies.forEach(d => deps.add(d));
    }
    
    return Array.from(deps);
  }

  private shouldCompress(batch: UpdateBatch): boolean {
    const dataSize = JSON.stringify(batch.updates).length;
    return dataSize > this.options.compressionThreshold;
  }

  private async compressBatch(batch: UpdateBatch): Promise<CompressedDelta> {
    // Compress the entire batch as one unit
    const combinedDelta: GraphDelta = {
      id: batch.id,
      timestamp: batch.timestamp,
      operations: batch.updates.flatMap(u => u.operations),
      version: `batch-${batch.updates.map(u => u.version).join('-')}`,
      sourceId: 'batcher',
      dependencies: batch.dependencies
    };
    
    return await this.compressor.compressDelta(combinedDelta);
  }

  flush(): void {
    if (this.queue.size() > 0 || this.currentBatch.length > 0) {
      this.processBatch();
    }
  }

  destroy(): void {
    if (this.batchTimer) {
      clearTimeout(this.batchTimer);
      this.batchTimer = null;
    }
    
    this.queue.clear();
    this.currentBatch = [];
    this.compressor.destroy();
  }

  getStats(): {
    queueSize: number;
    batchSize: number;
    compressionRatio: number;
  } {
    return {
      queueSize: this.queue.size(),
      batchSize: this.currentBatch.length,
      compressionRatio: 0 // TODO: Track compression ratio
    };
  }
}