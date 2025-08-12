/**
 * Version synchronization manager for tracking graph data updates
 * Manages sequence numbers and fetches only changed data since last sync
 */

import { GraphNode } from '@/api/types';
import { GraphLink } from '@/types/graph';
import { logger } from '@/utils/logger';

interface VersionInfo {
  sequence: number;
  timestamp: number;
  nodeCount: number;
  edgeCount: number;
}

interface SyncState {
  lastSyncSequence: number;
  lastSyncTime: number;
  pendingChanges: number;
  syncing: boolean;
}

interface GraphDelta {
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

export class VersionSyncManager {
  private currentSequence: number = 0;
  private syncState: SyncState = {
    lastSyncSequence: 0,
    lastSyncTime: 0,
    pendingChanges: 0,
    syncing: false,
  };
  private apiBaseUrl: string;
  private syncCallbacks: Set<(delta: GraphDelta) => void> = new Set();
  private pollingInterval: number | null = null;
  private readonly POLLING_INTERVAL_MS = 5000; // Poll every 5 seconds
  private readonly MAX_DELTA_FETCH = 100; // Max deltas to fetch at once

  constructor(apiBaseUrl: string = 'http://localhost:3000') {
    this.apiBaseUrl = apiBaseUrl;
  }

  /**
   * Get current version info from the server
   */
  async getServerVersion(): Promise<VersionInfo> {
    try {
      const response = await fetch(`${this.apiBaseUrl}/api/graph/sequence`);
      if (!response.ok) {
        throw new Error(`Failed to get server version: ${response.statusText}`);
      }
      
      const data = await response.json();
      return {
        sequence: data.sequence,
        timestamp: data.timestamp || Date.now(),
        nodeCount: data.node_count || 0,
        edgeCount: data.edge_count || 0,
      };
    } catch (error) {
      logger.error('Failed to get server version:', error);
      throw error;
    }
  }

  /**
   * Check if we're in sync with the server
   */
  async checkSync(): Promise<boolean> {
    try {
      const serverVersion = await this.getServerVersion();
      const isInSync = serverVersion.sequence === this.currentSequence;
      
      if (!isInSync) {
        this.syncState.pendingChanges = serverVersion.sequence - this.currentSequence;
        logger.log(`Version mismatch: local=${this.currentSequence}, server=${serverVersion.sequence}, pending=${this.syncState.pendingChanges}`);
      }
      
      return isInSync;
    } catch (error) {
      logger.error('Failed to check sync status:', error);
      return false;
    }
  }

  /**
   * Fetch changes since a specific sequence number
   */
  async fetchChangesSince(sinceSequence: number): Promise<GraphDelta[]> {
    try {
      const response = await fetch(
        `${this.apiBaseUrl}/api/graph/changes?since=${sinceSequence}&limit=${this.MAX_DELTA_FETCH}`
      );
      
      if (!response.ok) {
        throw new Error(`Failed to fetch changes: ${response.statusText}`);
      }
      
      const deltas = await response.json();
      logger.log(`Fetched ${deltas.length} deltas since sequence ${sinceSequence}`);
      
      return deltas;
    } catch (error) {
      logger.error('Failed to fetch changes:', error);
      throw error;
    }
  }

  /**
   * Synchronize with the server and fetch any missing updates
   */
  async sync(): Promise<GraphDelta[]> {
    if (this.syncState.syncing) {
      logger.log('Sync already in progress, skipping...');
      return [];
    }

    this.syncState.syncing = true;
    const allDeltas: GraphDelta[] = [];

    try {
      // Get server version
      const serverVersion = await this.getServerVersion();
      
      if (serverVersion.sequence === this.currentSequence) {
        logger.log('Already in sync with server');
        return [];
      }

      // Fetch changes since our last sequence
      let fetchedSequence = this.currentSequence;
      
      while (fetchedSequence < serverVersion.sequence) {
        const deltas = await this.fetchChangesSince(fetchedSequence);
        
        if (deltas.length === 0) {
          break; // No more changes
        }
        
        allDeltas.push(...deltas);
        
        // Update our sequence to the last delta we received
        const lastDelta = deltas[deltas.length - 1];
        fetchedSequence = lastDelta.sequence;
        
        // Notify callbacks for each delta
        for (const delta of deltas) {
          this.notifyCallbacks(delta);
        }
        
        // If we fetched the max number of deltas, there might be more
        if (deltas.length < this.MAX_DELTA_FETCH) {
          break;
        }
      }
      
      // Update our state
      this.currentSequence = fetchedSequence;
      this.syncState.lastSyncSequence = fetchedSequence;
      this.syncState.lastSyncTime = Date.now();
      this.syncState.pendingChanges = Math.max(0, serverVersion.sequence - fetchedSequence);
      
      logger.log(`Sync complete: fetched ${allDeltas.length} deltas, now at sequence ${this.currentSequence}`);
      
      return allDeltas;
    } catch (error) {
      logger.error('Sync failed:', error);
      throw error;
    } finally {
      this.syncState.syncing = false;
    }
  }

  /**
   * Start polling for version changes
   */
  startPolling(callback?: (delta: GraphDelta) => void): void {
    if (this.pollingInterval) {
      logger.log('Polling already started');
      return;
    }

    if (callback) {
      this.syncCallbacks.add(callback);
    }

    logger.log('Starting version polling...');
    
    // Initial sync
    this.sync().catch(error => {
      logger.error('Initial sync failed:', error);
    });

    // Set up polling interval
    this.pollingInterval = window.setInterval(async () => {
      try {
        const isInSync = await this.checkSync();
        if (!isInSync) {
          logger.log('Version mismatch detected, syncing...');
          await this.sync();
        }
      } catch (error) {
        logger.error('Polling check failed:', error);
      }
    }, this.POLLING_INTERVAL_MS);
  }

  /**
   * Stop polling for version changes
   */
  stopPolling(): void {
    if (this.pollingInterval) {
      window.clearInterval(this.pollingInterval);
      this.pollingInterval = null;
      logger.log('Version polling stopped');
    }
  }

  /**
   * Register a callback for delta updates
   */
  onDelta(callback: (delta: GraphDelta) => void): () => void {
    this.syncCallbacks.add(callback);
    
    // Return unsubscribe function
    return () => {
      this.syncCallbacks.delete(callback);
    };
  }

  /**
   * Notify all registered callbacks
   */
  private notifyCallbacks(delta: GraphDelta): void {
    this.syncCallbacks.forEach(callback => {
      try {
        callback(delta);
      } catch (error) {
        logger.error('Delta callback error:', error);
      }
    });
  }

  /**
   * Reset sync state (useful when switching graphs or on errors)
   */
  reset(): void {
    this.currentSequence = 0;
    this.syncState = {
      lastSyncSequence: 0,
      lastSyncTime: 0,
      pendingChanges: 0,
      syncing: false,
    };
    logger.log('Version sync state reset');
  }

  /**
   * Get current sync state
   */
  getSyncState(): SyncState {
    return { ...this.syncState };
  }

  /**
   * Get current sequence number
   */
  getCurrentSequence(): number {
    return this.currentSequence;
  }

  /**
   * Set the current sequence (useful for initialization)
   */
  setCurrentSequence(sequence: number): void {
    this.currentSequence = sequence;
    this.syncState.lastSyncSequence = sequence;
    logger.log(`Current sequence set to ${sequence}`);
  }
}

// Create singleton instance
export const versionSync = new VersionSyncManager(
  import.meta.env.VITE_API_BASE_URL || 'http://localhost:3000'
);