import { useEffect, useState, useCallback, useRef } from 'react';
import { versionSync } from '@/services/version-sync';
import { GraphNode } from '@/api/types';
import { GraphLink } from '@/types/graph';
import { logger } from '@/utils/logger';

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

interface UseVersionSyncOptions {
  enabled?: boolean;
  pollingInterval?: number;
  onDelta?: (delta: GraphDelta) => void;
  onSyncComplete?: (deltas: GraphDelta[]) => void;
  onSyncError?: (error: Error) => void;
}

interface VersionSyncState {
  isInSync: boolean;
  isSyncing: boolean;
  currentSequence: number;
  serverSequence: number;
  pendingChanges: number;
  lastSyncTime: number;
  error: Error | null;
}

export function useVersionSync({
  enabled = true,
  onDelta,
  onSyncComplete,
  onSyncError,
}: UseVersionSyncOptions = {}) {
  const [state, setState] = useState<VersionSyncState>({
    isInSync: true,
    isSyncing: false,
    currentSequence: 0,
    serverSequence: 0,
    pendingChanges: 0,
    lastSyncTime: 0,
    error: null,
  });
  
  const unsubscribeRef = useRef<(() => void) | null>(null);
  const syncInProgressRef = useRef(false);

  // Check if we're in sync with the server
  const checkSync = useCallback(async () => {
    try {
      const serverVersion = await versionSync.getServerVersion();
      const currentSequence = versionSync.getCurrentSequence();
      const isInSync = serverVersion.sequence === currentSequence;
      
      setState(prev => ({
        ...prev,
        isInSync,
        currentSequence,
        serverSequence: serverVersion.sequence,
        pendingChanges: Math.max(0, serverVersion.sequence - currentSequence),
        error: null,
      }));
      
      return isInSync;
    } catch (error) {
      const err = error as Error;
      logger.error('Failed to check sync:', err);
      setState(prev => ({ ...prev, error: err }));
      onSyncError?.(err);
      return false;
    }
  }, [onSyncError]);

  // Perform synchronization
  const sync = useCallback(async () => {
    if (syncInProgressRef.current) {
      logger.log('Sync already in progress');
      return;
    }
    
    syncInProgressRef.current = true;
    setState(prev => ({ ...prev, isSyncing: true, error: null }));
    
    try {
      const deltas = await versionSync.sync();
      
      if (deltas.length > 0) {
        logger.log(`Synced ${deltas.length} deltas`);
        onSyncComplete?.(deltas);
      }
      
      // Update state after successful sync
      const syncState = versionSync.getSyncState();
      setState(prev => ({
        ...prev,
        isInSync: syncState.pendingChanges === 0,
        isSyncing: false,
        currentSequence: versionSync.getCurrentSequence(),
        pendingChanges: syncState.pendingChanges,
        lastSyncTime: syncState.lastSyncTime,
        error: null,
      }));
      
      return deltas;
    } catch (error) {
      const err = error as Error;
      logger.error('Sync failed:', err);
      setState(prev => ({ ...prev, isSyncing: false, error: err }));
      onSyncError?.(err);
      return [];
    } finally {
      syncInProgressRef.current = false;
    }
  }, [onSyncComplete, onSyncError]);

  // Force a manual sync
  const forceSync = useCallback(async () => {
    logger.log('Forcing manual sync...');
    return await sync();
  }, [sync]);

  // Reset sync state
  const reset = useCallback(() => {
    versionSync.reset();
    setState({
      isInSync: true,
      isSyncing: false,
      currentSequence: 0,
      serverSequence: 0,
      pendingChanges: 0,
      lastSyncTime: 0,
      error: null,
    });
  }, []);

  // Set up polling and delta callbacks
  useEffect(() => {
    if (!enabled) {
      versionSync.stopPolling();
      return;
    }

    // Register delta callback
    if (onDelta) {
      unsubscribeRef.current = versionSync.onDelta(onDelta);
    }

    // Start polling with internal callback
    versionSync.startPolling((delta) => {
      logger.log('Received delta from polling:', {
        sequence: delta.sequence,
        nodesAdded: delta.nodes_added.length,
        nodesUpdated: delta.nodes_updated.length,
        nodesRemoved: delta.nodes_removed.length,
      });
      
      // Update our state
      setState(prev => ({
        ...prev,
        currentSequence: delta.sequence,
        pendingChanges: 0,
        lastSyncTime: Date.now(),
      }));
    });

    // Cleanup
    return () => {
      versionSync.stopPolling();
      if (unsubscribeRef.current) {
        unsubscribeRef.current();
        unsubscribeRef.current = null;
      }
    };
  }, [enabled, onDelta]);

  return {
    ...state,
    checkSync,
    sync,
    forceSync,
    reset,
  };
}

/**
 * Apply a delta to existing graph data
 */
export function applyDeltaToGraph(
  nodes: GraphNode[],
  edges: GraphLink[],
  delta: GraphDelta
): { nodes: GraphNode[], edges: GraphLink[] } {
  // Create maps for efficient lookups
  const nodeMap = new Map(nodes.map(n => [n.id, n]));
  const edgeMap = new Map(edges.map(e => [`${e.source}-${e.target}`, e]));

  // Apply node removals
  delta.nodes_removed.forEach(id => {
    nodeMap.delete(id);
  });

  // Apply node additions
  delta.nodes_added.forEach(node => {
    nodeMap.set(node.id, node);
  });

  // Apply node updates
  delta.nodes_updated.forEach(node => {
    const existing = nodeMap.get(node.id);
    if (existing) {
      // Merge the update with existing node
      nodeMap.set(node.id, { ...existing, ...node });
    } else {
      // If node doesn't exist, add it
      nodeMap.set(node.id, node);
    }
  });

  // Apply edge removals
  delta.edges_removed.forEach(([source, target]) => {
    edgeMap.delete(`${source}-${target}`);
  });

  // Apply edge additions
  delta.edges_added.forEach(edge => {
    edgeMap.set(`${edge.source}-${edge.target}`, edge);
  });

  // Apply edge updates
  delta.edges_updated.forEach(edge => {
    const key = `${edge.source}-${edge.target}`;
    const existing = edgeMap.get(key);
    if (existing) {
      // Merge the update with existing edge
      edgeMap.set(key, { ...existing, ...edge });
    } else {
      // If edge doesn't exist, add it
      edgeMap.set(key, edge);
    }
  });

  return {
    nodes: Array.from(nodeMap.values()),
    edges: Array.from(edgeMap.values()),
  };
}

/**
 * Batch apply multiple deltas to graph data
 */
export function applyDeltasToGraph(
  nodes: GraphNode[],
  edges: GraphLink[],
  deltas: GraphDelta[]
): { nodes: GraphNode[], edges: GraphLink[] } {
  let currentNodes = nodes;
  let currentEdges = edges;
  
  for (const delta of deltas) {
    const result = applyDeltaToGraph(currentNodes, currentEdges, delta);
    currentNodes = result.nodes;
    currentEdges = result.edges;
  }
  
  return { nodes: currentNodes, edges: currentEdges };
}