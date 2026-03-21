/**
 * useGraphLiveCounts Hook
 * Tracks live node and edge counts from WebSocket delta updates
 * Extracted from GraphCanvasV2 for better separation of concerns (GRAPH-35)
 */

import { useState, useEffect, useCallback } from 'react';
import { useWebSocketContext } from '../contexts/WebSocketProvider';

interface LiveCountsOptions {
  initialNodeCount?: number;
  initialEdgeCount?: number;
  debug?: boolean;
}

interface LiveCountsReturn {
  liveNodeCount: number;
  liveEdgeCount: number;
  setLiveNodeCount: React.Dispatch<React.SetStateAction<number>>;
  setLiveEdgeCount: React.Dispatch<React.SetStateAction<number>>;
  resetCounts: (nodeCount: number, edgeCount: number) => void;
}

export function useGraphLiveCounts(options: LiveCountsOptions = {}): LiveCountsReturn {
  const { initialNodeCount = 0, initialEdgeCount = 0, debug = false } = options;
  
  const [liveNodeCount, setLiveNodeCount] = useState<number>(initialNodeCount);
  const [liveEdgeCount, setLiveEdgeCount] = useState<number>(initialEdgeCount);
  const { subscribe: subscribeToWebSocket } = useWebSocketContext();
  
  // Reset counts (useful when data is reloaded)
  const resetCounts = useCallback((nodeCount: number, edgeCount: number) => {
    setLiveNodeCount(nodeCount);
    setLiveEdgeCount(edgeCount);
  }, []);
  
  // Subscribe to WebSocket delta events for live count updates
  useEffect(() => {
    const unsubscribe = subscribeToWebSocket((event) => {
      if (event.type === 'graph:delta' && 'data' in event && event.data) {
        const deltaData = event.data as { added_nodes?: unknown[]; removed_nodes?: unknown[]; added_edges?: unknown[]; removed_edges?: unknown[] };
        
        // Update node count
        if (deltaData.added_nodes?.length > 0 || deltaData.removed_nodes?.length > 0) {
          setLiveNodeCount(prev => {
            const newCount = prev + 
              (deltaData.added_nodes?.length || 0) - 
              (deltaData.removed_nodes?.length || 0);
            if (debug) {
              console.log('[useGraphLiveCounts] Node count updated:', newCount);
            }
            return newCount;
          });
        }
        
        // Update edge count
        if (deltaData.added_edges?.length > 0 || deltaData.removed_edges?.length > 0) {
          setLiveEdgeCount(prev => {
            const newCount = prev + 
              (deltaData.added_edges?.length || 0) - 
              (deltaData.removed_edges?.length || 0);
            if (debug) {
              console.log('[useGraphLiveCounts] Edge count updated:', newCount);
            }
            return newCount;
          });
        }
      }
    });
    
    return unsubscribe;
  }, [subscribeToWebSocket, debug]);
  
  return {
    liveNodeCount,
    liveEdgeCount,
    setLiveNodeCount,
    setLiveEdgeCount,
    resetCounts
  };
}
