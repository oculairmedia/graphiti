// Offline queue manager with IndexedDB persistence

interface QueuedMessage {
  id: string;
  type: string;
  data: any;
  timestamp: number;
  retryCount: number;
  priority: number;
  metadata?: {
    source: string;
    version?: string;
    dependencies?: string[];
  };
}

interface SyncState {
  lastSyncTime: number;
  pendingChanges: number;
  syncInProgress: boolean;
  syncErrors: string[];
}

// IndexedDB wrapper for offline persistence
class OfflineStorage {
  private dbName = 'graphiti-offline-queue';
  private dbVersion = 1;
  private db: IDBDatabase | null = null;

  async initialize(): Promise<void> {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open(this.dbName, this.dbVersion);

      request.onerror = () => {
        reject(new Error('Failed to open IndexedDB'));
      };

      request.onsuccess = () => {
        this.db = request.result;
        resolve();
      };

      request.onupgradeneeded = (event) => {
        const db = (event.target as IDBOpenDBRequest).result;

        // Create object stores
        if (!db.objectStoreNames.contains('messages')) {
          const messageStore = db.createObjectStore('messages', { keyPath: 'id' });
          messageStore.createIndex('timestamp', 'timestamp', { unique: false });
          messageStore.createIndex('priority', 'priority', { unique: false });
          messageStore.createIndex('type', 'type', { unique: false });
        }

        if (!db.objectStoreNames.contains('syncState')) {
          db.createObjectStore('syncState', { keyPath: 'id' });
        }

        if (!db.objectStoreNames.contains('conflicts')) {
          const conflictStore = db.createObjectStore('conflicts', { keyPath: 'id' });
          conflictStore.createIndex('timestamp', 'timestamp', { unique: false });
        }
      };
    });
  }

  async addMessage(message: QueuedMessage): Promise<void> {
    if (!this.db) throw new Error('Database not initialized');

    return new Promise((resolve, reject) => {
      const transaction = this.db!.transaction(['messages'], 'readwrite');
      const store = transaction.objectStore('messages');
      const request = store.add(message);

      request.onsuccess = () => resolve();
      request.onerror = () => reject(new Error('Failed to add message'));
    });
  }

  async getMessages(limit?: number): Promise<QueuedMessage[]> {
    if (!this.db) throw new Error('Database not initialized');

    return new Promise((resolve, reject) => {
      const transaction = this.db!.transaction(['messages'], 'readonly');
      const store = transaction.objectStore('messages');
      const index = store.index('priority');
      const request = index.openCursor(null, 'prev'); // High priority first
      
      const messages: QueuedMessage[] = [];
      let count = 0;

      request.onsuccess = (event) => {
        const cursor = (event.target as IDBRequest).result;
        
        if (cursor && (!limit || count < limit)) {
          messages.push(cursor.value);
          count++;
          cursor.continue();
        } else {
          resolve(messages);
        }
      };

      request.onerror = () => reject(new Error('Failed to get messages'));
    });
  }

  async removeMessage(id: string): Promise<void> {
    if (!this.db) throw new Error('Database not initialized');

    return new Promise((resolve, reject) => {
      const transaction = this.db!.transaction(['messages'], 'readwrite');
      const store = transaction.objectStore('messages');
      const request = store.delete(id);

      request.onsuccess = () => resolve();
      request.onerror = () => reject(new Error('Failed to remove message'));
    });
  }

  async clearMessages(): Promise<void> {
    if (!this.db) throw new Error('Database not initialized');

    return new Promise((resolve, reject) => {
      const transaction = this.db!.transaction(['messages'], 'readwrite');
      const store = transaction.objectStore('messages');
      const request = store.clear();

      request.onsuccess = () => resolve();
      request.onerror = () => reject(new Error('Failed to clear messages'));
    });
  }

  async updateSyncState(state: SyncState): Promise<void> {
    if (!this.db) throw new Error('Database not initialized');

    return new Promise((resolve, reject) => {
      const transaction = this.db!.transaction(['syncState'], 'readwrite');
      const store = transaction.objectStore('syncState');
      const request = store.put({ ...state, id: 'main' });

      request.onsuccess = () => resolve();
      request.onerror = () => reject(new Error('Failed to update sync state'));
    });
  }

  async getSyncState(): Promise<SyncState | null> {
    if (!this.db) throw new Error('Database not initialized');

    return new Promise((resolve, reject) => {
      const transaction = this.db!.transaction(['syncState'], 'readonly');
      const store = transaction.objectStore('syncState');
      const request = store.get('main');

      request.onsuccess = () => {
        const result = request.result;
        resolve(result || null);
      };
      request.onerror = () => reject(new Error('Failed to get sync state'));
    });
  }

  async getMessageCount(): Promise<number> {
    if (!this.db) throw new Error('Database not initialized');

    return new Promise((resolve, reject) => {
      const transaction = this.db!.transaction(['messages'], 'readonly');
      const store = transaction.objectStore('messages');
      const request = store.count();

      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(new Error('Failed to count messages'));
    });
  }

  async getOldestMessage(): Promise<QueuedMessage | null> {
    if (!this.db) throw new Error('Database not initialized');

    return new Promise((resolve, reject) => {
      const transaction = this.db!.transaction(['messages'], 'readonly');
      const store = transaction.objectStore('messages');
      const index = store.index('timestamp');
      const request = index.openCursor();

      request.onsuccess = (event) => {
        const cursor = (event.target as IDBRequest).result;
        resolve(cursor ? cursor.value : null);
      };
      request.onerror = () => reject(new Error('Failed to get oldest message'));
    });
  }
}

// Main offline queue manager
export class OfflineQueueManager {
  private storage: OfflineStorage;
  private syncInProgress = false;
  private syncInterval: number | null = null;
  private onlineListener: (() => void) | null = null;
  private offlineListener: (() => void) | null = null;
  private maxRetries = 3;
  private syncBatchSize = 50;
  private syncIntervalMs = 30000; // 30 seconds

  constructor(
    private onSync: (messages: QueuedMessage[]) => Promise<void>,
    private onConflict?: (conflict: any) => void
  ) {
    this.storage = new OfflineStorage();
  }

  async initialize(): Promise<void> {
    await this.storage.initialize();
    
    // Set up online/offline listeners
    this.onlineListener = () => this.handleOnline();
    this.offlineListener = () => this.handleOffline();
    
    window.addEventListener('online', this.onlineListener);
    window.addEventListener('offline', this.offlineListener);
    
    // Start sync interval if online
    if (navigator.onLine) {
      this.startSyncInterval();
    }
    
    // Check for pending messages on initialization
    await this.checkPendingMessages();
  }

  async destroy(): Promise<void> {
    this.stopSyncInterval();
    
    if (this.onlineListener) {
      window.removeEventListener('online', this.onlineListener);
    }
    if (this.offlineListener) {
      window.removeEventListener('offline', this.offlineListener);
    }
  }

  private handleOnline(): void {
    console.log('[OfflineQueue] Connection restored, starting sync');
    this.startSyncInterval();
    this.sync(); // Immediate sync
  }

  private handleOffline(): void {
    console.log('[OfflineQueue] Connection lost, stopping sync');
    this.stopSyncInterval();
  }

  private startSyncInterval(): void {
    if (this.syncInterval) return;
    
    this.syncInterval = window.setInterval(() => {
      this.sync();
    }, this.syncIntervalMs);
  }

  private stopSyncInterval(): void {
    if (this.syncInterval) {
      clearInterval(this.syncInterval);
      this.syncInterval = null;
    }
  }

  async enqueue(message: Omit<QueuedMessage, 'id' | 'timestamp' | 'retryCount'>): Promise<void> {
    const queuedMessage: QueuedMessage = {
      ...message,
      id: `msg-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      timestamp: Date.now(),
      retryCount: 0
    };

    await this.storage.addMessage(queuedMessage);
    
    // Try immediate sync if online
    if (navigator.onLine && !this.syncInProgress) {
      this.sync();
    }
  }

  async sync(): Promise<void> {
    if (this.syncInProgress || !navigator.onLine) return;
    
    this.syncInProgress = true;
    const startTime = Date.now();
    const errors: string[] = [];
    
    try {
      // Get messages to sync
      const messages = await this.storage.getMessages(this.syncBatchSize);
      
      if (messages.length === 0) {
        return; // Nothing to sync
      }
      
      console.log(`[OfflineQueue] Syncing ${messages.length} messages`);
      
      // Group messages by type for efficient batching
      const groupedMessages = this.groupMessagesByType(messages);
      
      // Process each group
      for (const [type, group] of Object.entries(groupedMessages)) {
        try {
          await this.syncMessageGroup(group);
        } catch (error) {
          const errorMsg = `Failed to sync ${type} messages: ${error}`;
          errors.push(errorMsg);
          console.error('[OfflineQueue]', errorMsg);
        }
      }
      
      // Update sync state
      const pendingCount = await this.storage.getMessageCount();
      await this.storage.updateSyncState({
        lastSyncTime: Date.now(),
        pendingChanges: pendingCount,
        syncInProgress: false,
        syncErrors: errors
      });
      
      const duration = Date.now() - startTime;
      console.log(`[OfflineQueue] Sync completed in ${duration}ms, ${pendingCount} messages remaining`);
      
    } catch (error) {
      console.error('[OfflineQueue] Sync failed:', error);
      errors.push(String(error));
    } finally {
      this.syncInProgress = false;
    }
  }

  private groupMessagesByType(messages: QueuedMessage[]): Record<string, QueuedMessage[]> {
    const groups: Record<string, QueuedMessage[]> = {};
    
    for (const message of messages) {
      if (!groups[message.type]) {
        groups[message.type] = [];
      }
      groups[message.type].push(message);
    }
    
    return groups;
  }

  private async syncMessageGroup(messages: QueuedMessage[]): Promise<void> {
    const successfulIds: string[] = [];
    const failedMessages: QueuedMessage[] = [];
    
    try {
      // Send batch to server
      await this.onSync(messages);
      
      // All successful, remove from queue
      for (const message of messages) {
        successfulIds.push(message.id);
      }
    } catch (error) {
      // Handle partial failures
      if ((error as any).partialSuccess) {
        const { successful, failed } = (error as any);
        
        for (const id of successful) {
          successfulIds.push(id);
        }
        
        for (const id of failed) {
          const message = messages.find(m => m.id === id);
          if (message) {
            failedMessages.push(message);
          }
        }
      } else {
        // Complete failure, all messages failed
        failedMessages.push(...messages);
      }
    }
    
    // Remove successful messages
    for (const id of successfulIds) {
      await this.storage.removeMessage(id);
    }
    
    // Handle failed messages
    for (const message of failedMessages) {
      await this.handleFailedMessage(message);
    }
  }

  private async handleFailedMessage(message: QueuedMessage): Promise<void> {
    message.retryCount++;
    
    if (message.retryCount >= this.maxRetries) {
      console.error(`[OfflineQueue] Message ${message.id} exceeded max retries, moving to DLQ`);
      
      // Move to dead letter queue or handle as conflict
      if (this.onConflict) {
        this.onConflict({
          type: 'sync-failure',
          message,
          reason: 'max-retries-exceeded'
        });
      }
      
      // Remove from queue
      await this.storage.removeMessage(message.id);
    } else {
      // Update retry count and re-queue
      await this.storage.removeMessage(message.id);
      await this.storage.addMessage(message);
    }
  }

  async checkPendingMessages(): Promise<void> {
    const count = await this.storage.getMessageCount();
    
    if (count > 0) {
      console.log(`[OfflineQueue] Found ${count} pending messages`);
      
      // Get oldest message to check staleness
      const oldest = await this.storage.getOldestMessage();
      if (oldest) {
        const age = Date.now() - oldest.timestamp;
        const ageMinutes = Math.floor(age / 60000);
        
        if (ageMinutes > 60) {
          console.warn(`[OfflineQueue] Oldest message is ${ageMinutes} minutes old`);
        }
      }
      
      // Trigger sync if online
      if (navigator.onLine) {
        this.sync();
      }
    }
  }

  async getQueueStatus(): Promise<{
    queueSize: number;
    oldestMessageAge: number | null;
    syncState: SyncState | null;
    isOnline: boolean;
    isSyncing: boolean;
  }> {
    const count = await this.storage.getMessageCount();
    const oldest = await this.storage.getOldestMessage();
    const syncState = await this.storage.getSyncState();
    
    return {
      queueSize: count,
      oldestMessageAge: oldest ? Date.now() - oldest.timestamp : null,
      syncState,
      isOnline: navigator.onLine,
      isSyncing: this.syncInProgress
    };
  }

  async clearQueue(): Promise<void> {
    await this.storage.clearMessages();
    console.log('[OfflineQueue] Queue cleared');
  }

  // Manual retry for specific message types
  async retryFailedMessages(type?: string): Promise<void> {
    const messages = await this.storage.getMessages();
    const toRetry = type 
      ? messages.filter(m => m.type === type && m.retryCount > 0)
      : messages.filter(m => m.retryCount > 0);
    
    if (toRetry.length > 0) {
      console.log(`[OfflineQueue] Retrying ${toRetry.length} failed messages`);
      
      // Reset retry count
      for (const message of toRetry) {
        message.retryCount = 0;
        await this.storage.removeMessage(message.id);
        await this.storage.addMessage(message);
      }
      
      // Trigger sync
      if (navigator.onLine) {
        this.sync();
      }
    }
  }
}