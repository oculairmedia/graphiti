// Message deduplication and ordering service

export interface OrderedMessage {
  id: string;
  sequenceNumber: number;
  timestamp: number;
  type: string;
  data: any;
  hash: string;
  sourceId: string;
  acknowledgementRequired?: boolean;
}

export interface MessageWindow {
  startSequence: number;
  endSequence: number;
  messages: Map<number, OrderedMessage>;
  gaps: Set<number>;
  lastProcessedSequence: number;
}

export interface DeduplicationStats {
  totalReceived: number;
  duplicatesDetected: number;
  outOfOrderMessages: number;
  gapsDetected: number;
  messagesReordered: number;
}

// Circular buffer for efficient deduplication
class CircularBuffer<T> {
  private buffer: (T | undefined)[];
  private head = 0;
  private tail = 0;
  private count = 0;

  constructor(private capacity: number) {
    this.buffer = new Array(capacity);
  }

  add(item: T): boolean {
    if (this.count >= this.capacity) {
      // Buffer is full, remove oldest
      this.head = (this.head + 1) % this.capacity;
      this.count--;
    }

    this.buffer[this.tail] = item;
    this.tail = (this.tail + 1) % this.capacity;
    this.count++;
    
    return true;
  }

  contains(predicate: (item: T) => boolean): boolean {
    let index = this.head;
    
    for (let i = 0; i < this.count; i++) {
      const item = this.buffer[index];
      if (item && predicate(item)) {
        return true;
      }
      index = (index + 1) % this.capacity;
    }
    
    return false;
  }

  clear(): void {
    this.buffer = new Array(this.capacity);
    this.head = 0;
    this.tail = 0;
    this.count = 0;
  }

  size(): number {
    return this.count;
  }

  toArray(): T[] {
    const result: T[] = [];
    let index = this.head;
    
    for (let i = 0; i < this.count; i++) {
      const item = this.buffer[index];
      if (item) {
        result.push(item);
      }
      index = (index + 1) % this.capacity;
    }
    
    return result;
  }
}

// Bloom filter for space-efficient duplicate detection
class BloomFilter {
  private bitArray: Uint8Array;
  private hashCount: number;
  private size: number;

  constructor(expectedElements: number, falsePositiveRate = 0.01) {
    // Calculate optimal bit array size and hash count
    this.size = Math.ceil(-expectedElements * Math.log(falsePositiveRate) / (Math.log(2) ** 2));
    this.hashCount = Math.ceil(this.size / expectedElements * Math.log(2));
    this.bitArray = new Uint8Array(Math.ceil(this.size / 8));
  }

  add(item: string): void {
    const hashes = this.getHashes(item);
    
    for (const hash of hashes) {
      const index = hash % this.size;
      const byteIndex = Math.floor(index / 8);
      const bitIndex = index % 8;
      this.bitArray[byteIndex] |= (1 << bitIndex);
    }
  }

  contains(item: string): boolean {
    const hashes = this.getHashes(item);
    
    for (const hash of hashes) {
      const index = hash % this.size;
      const byteIndex = Math.floor(index / 8);
      const bitIndex = index % 8;
      
      if ((this.bitArray[byteIndex] & (1 << bitIndex)) === 0) {
        return false;
      }
    }
    
    return true;
  }

  private getHashes(item: string): number[] {
    const hashes: number[] = [];
    
    // Use multiple hash functions
    for (let i = 0; i < this.hashCount; i++) {
      const hash = this.hashFunction(item, i);
      hashes.push(Math.abs(hash));
    }
    
    return hashes;
  }

  private hashFunction(str: string, seed: number): number {
    let hash = seed;
    
    for (let i = 0; i < str.length; i++) {
      const char = str.charCodeAt(i);
      hash = ((hash << 5) - hash + char + seed) | 0;
    }
    
    return hash;
  }

  clear(): void {
    this.bitArray.fill(0);
  }

  getLoadFactor(): number {
    let setBits = 0;
    
    for (let i = 0; i < this.bitArray.length; i++) {
      let byte = this.bitArray[i];
      while (byte) {
        setBits += byte & 1;
        byte >>= 1;
      }
    }
    
    return setBits / this.size;
  }
}

// Main message deduplication and ordering service
export class MessageDeduplicator {
  private seenMessages: BloomFilter;
  private recentHashes: CircularBuffer<string>;
  private messageWindows = new Map<string, MessageWindow>();
  private stats: DeduplicationStats = {
    totalReceived: 0,
    duplicatesDetected: 0,
    outOfOrderMessages: 0,
    gapsDetected: 0,
    messagesReordered: 0
  };
  
  private windowSize = 1000;
  private maxGapSize = 100;
  private reorderTimeout = 5000; // 5 seconds
  private pendingAcks = new Map<string, NodeJS.Timeout>();

  constructor(
    private onOrderedMessage: (message: OrderedMessage) => void,
    private onGapDetected?: (sourceId: string, missingSequences: number[]) => void,
    private onAcknowledgement?: (messageId: string) => void
  ) {
    // Initialize bloom filter for 100k messages with 1% false positive rate
    this.seenMessages = new BloomFilter(100000, 0.01);
    
    // Keep recent hashes for exact duplicate checking
    this.recentHashes = new CircularBuffer(10000);
  }

  processMessage(message: Partial<OrderedMessage>): boolean {
    this.stats.totalReceived++;

    // Generate message hash if not provided
    const hash = message.hash || this.generateHash(message);
    
    // Check for duplicates
    if (this.isDuplicate(hash)) {
      this.stats.duplicatesDetected++;
      console.log(`[Deduplicator] Duplicate message detected: ${message.id}`);
      return false;
    }

    // Add to deduplication structures
    this.seenMessages.add(hash);
    this.recentHashes.add(hash);

    // Create ordered message
    const orderedMessage: OrderedMessage = {
      id: message.id || this.generateId(),
      sequenceNumber: message.sequenceNumber || 0,
      timestamp: message.timestamp || Date.now(),
      type: message.type || 'unknown',
      data: message.data,
      hash,
      sourceId: message.sourceId || 'default',
      acknowledgementRequired: message.acknowledgementRequired
    };

    // Process ordering if sequence number is provided
    if (orderedMessage.sequenceNumber > 0) {
      this.processOrderedMessage(orderedMessage);
    } else {
      // No ordering required, process immediately
      this.deliverMessage(orderedMessage);
    }

    return true;
  }

  private isDuplicate(hash: string): boolean {
    // Check bloom filter first (fast, may have false positives)
    if (!this.seenMessages.contains(hash)) {
      return false; // Definitely not a duplicate
    }

    // Check recent hashes for exact match (slower but accurate)
    return this.recentHashes.contains(h => h === hash);
  }

  private processOrderedMessage(message: OrderedMessage): void {
    const window = this.getOrCreateWindow(message.sourceId);
    
    // Check if message is in order
    if (message.sequenceNumber === window.lastProcessedSequence + 1) {
      // Message is in order
      this.deliverMessage(message);
      window.lastProcessedSequence = message.sequenceNumber;
      
      // Check if we can deliver any buffered messages
      this.deliverBufferedMessages(window, message.sourceId);
    } else if (message.sequenceNumber > window.lastProcessedSequence + 1) {
      // Message is out of order - buffer it
      this.bufferMessage(window, message);
      this.stats.outOfOrderMessages++;
      
      // Detect gaps
      this.detectGaps(window, message.sourceId);
      
      // Set timeout to force delivery if gap isn't filled
      this.scheduleGapTimeout(window, message.sourceId);
    } else {
      // Message is old (already processed)
      console.log(`[Deduplicator] Old message received: seq=${message.sequenceNumber}, last=${window.lastProcessedSequence}`);
    }
  }

  private getOrCreateWindow(sourceId: string): MessageWindow {
    let window = this.messageWindows.get(sourceId);
    
    if (!window) {
      window = {
        startSequence: 0,
        endSequence: 0,
        messages: new Map(),
        gaps: new Set(),
        lastProcessedSequence: 0
      };
      this.messageWindows.set(sourceId, window);
    }
    
    return window;
  }

  private bufferMessage(window: MessageWindow, message: OrderedMessage): void {
    window.messages.set(message.sequenceNumber, message);
    
    // Update window boundaries
    if (message.sequenceNumber > window.endSequence) {
      window.endSequence = message.sequenceNumber;
    }
    
    // Limit window size
    if (window.messages.size > this.windowSize) {
      this.trimWindow(window);
    }
  }

  private trimWindow(window: MessageWindow): void {
    const sortedSequences = Array.from(window.messages.keys()).sort((a, b) => a - b);
    const toRemove = sortedSequences.slice(0, sortedSequences.length - this.windowSize);
    
    for (const seq of toRemove) {
      window.messages.delete(seq);
    }
    
    if (toRemove.length > 0) {
      window.startSequence = sortedSequences[toRemove.length];
    }
  }

  private deliverBufferedMessages(window: MessageWindow, sourceId: string): void {
    let delivered = 0;
    let nextSequence = window.lastProcessedSequence + 1;
    
    while (window.messages.has(nextSequence)) {
      const message = window.messages.get(nextSequence)!;
      this.deliverMessage(message);
      window.messages.delete(nextSequence);
      window.lastProcessedSequence = nextSequence;
      window.gaps.delete(nextSequence);
      nextSequence++;
      delivered++;
    }
    
    if (delivered > 0) {
      this.stats.messagesReordered += delivered;
      console.log(`[Deduplicator] Delivered ${delivered} buffered messages for ${sourceId}`);
    }
  }

  private detectGaps(window: MessageWindow, sourceId: string): void {
    const missingSequences: number[] = [];
    
    for (let seq = window.lastProcessedSequence + 1; seq < window.endSequence; seq++) {
      if (!window.messages.has(seq) && !window.gaps.has(seq)) {
        window.gaps.add(seq);
        missingSequences.push(seq);
      }
    }
    
    if (missingSequences.length > 0) {
      this.stats.gapsDetected++;
      console.log(`[Deduplicator] Gap detected for ${sourceId}: ${missingSequences.join(', ')}`);
      
      if (this.onGapDetected) {
        this.onGapDetected(sourceId, missingSequences);
      }
    }
  }

  private scheduleGapTimeout(window: MessageWindow, sourceId: string): void {
    // Schedule forced delivery after timeout
    setTimeout(() => {
      const gaps = Array.from(window.gaps);
      
      if (gaps.length > 0 && gaps.length <= this.maxGapSize) {
        console.log(`[Deduplicator] Gap timeout reached for ${sourceId}, forcing delivery`);
        
        // Skip gaps and deliver what we have
        const minGap = Math.min(...gaps);
        window.lastProcessedSequence = minGap - 1;
        
        // Try to deliver buffered messages
        this.deliverBufferedMessages(window, sourceId);
        
        // Clear gaps that were skipped
        for (const gap of gaps) {
          if (gap <= window.lastProcessedSequence) {
            window.gaps.delete(gap);
          }
        }
      }
    }, this.reorderTimeout);
  }

  private deliverMessage(message: OrderedMessage): void {
    // Handle acknowledgement if required
    if (message.acknowledgementRequired && this.onAcknowledgement) {
      // Send acknowledgement after a short delay to batch them
      const ackTimeout = setTimeout(() => {
        this.onAcknowledgement!(message.id);
        this.pendingAcks.delete(message.id);
      }, 100);
      
      this.pendingAcks.set(message.id, ackTimeout);
    }

    // Deliver to handler
    this.onOrderedMessage(message);
  }

  private generateHash(message: Partial<OrderedMessage>): string {
    const content = JSON.stringify({
      type: message.type,
      data: message.data,
      sourceId: message.sourceId,
      sequenceNumber: message.sequenceNumber
    });
    
    return this.simpleHash(content);
  }

  private simpleHash(str: string): string {
    let hash = 0;
    
    for (let i = 0; i < str.length; i++) {
      const char = str.charCodeAt(i);
      hash = ((hash << 5) - hash) + char;
      hash = hash & hash; // Convert to 32-bit integer
    }
    
    return hash.toString(36);
  }

  private generateId(): string {
    return `msg-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  }

  // Force flush all buffered messages
  flush(sourceId?: string): void {
    const sources = sourceId ? [sourceId] : Array.from(this.messageWindows.keys());
    
    for (const source of sources) {
      const window = this.messageWindows.get(source);
      if (!window) continue;
      
      // Sort and deliver all buffered messages
      const sortedMessages = Array.from(window.messages.values())
        .sort((a, b) => a.sequenceNumber - b.sequenceNumber);
      
      for (const message of sortedMessages) {
        this.deliverMessage(message);
      }
      
      // Clear the window
      window.messages.clear();
      window.gaps.clear();
      
      if (sortedMessages.length > 0) {
        window.lastProcessedSequence = sortedMessages[sortedMessages.length - 1].sequenceNumber;
      }
    }
  }

  // Get deduplication statistics
  getStats(): DeduplicationStats & {
    bloomFilterLoad: number;
    windowSizes: Record<string, number>;
    pendingAcks: number;
  } {
    const windowSizes: Record<string, number> = {};
    
    for (const [sourceId, window] of this.messageWindows) {
      windowSizes[sourceId] = window.messages.size;
    }
    
    return {
      ...this.stats,
      bloomFilterLoad: this.seenMessages.getLoadFactor(),
      windowSizes,
      pendingAcks: this.pendingAcks.size
    };
  }

  // Reset statistics
  resetStats(): void {
    this.stats = {
      totalReceived: 0,
      duplicatesDetected: 0,
      outOfOrderMessages: 0,
      gapsDetected: 0,
      messagesReordered: 0
    };
  }

  // Clear all state
  clear(): void {
    this.seenMessages.clear();
    this.recentHashes.clear();
    this.messageWindows.clear();
    
    // Clear pending acknowledgements
    for (const timeout of this.pendingAcks.values()) {
      clearTimeout(timeout);
    }
    this.pendingAcks.clear();
    
    this.resetStats();
  }

  // Set configuration
  configure(options: {
    windowSize?: number;
    maxGapSize?: number;
    reorderTimeout?: number;
  }): void {
    if (options.windowSize) {
      this.windowSize = options.windowSize;
    }
    if (options.maxGapSize) {
      this.maxGapSize = options.maxGapSize;
    }
    if (options.reorderTimeout) {
      this.reorderTimeout = options.reorderTimeout;
    }
  }
}