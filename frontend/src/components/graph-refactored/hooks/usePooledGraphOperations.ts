/**
 * Hook for graph operations using object pools to minimize garbage collection
 */

import { useState, useCallback, useEffect, useRef } from 'react';
import { GraphNode } from '../../../api/types';
import { GraphLink } from '../../../types/graph';
import {
  Vector2DPool,
  BoundingBoxPool,
  EventPool,
  DeltaPool,
  GraphOperationResultPool,
  withVector2D,
  withBoundingBox,
  PoolManager,
  PooledBatch
} from '../utils/objectPools';
import { logger } from '../../../utils/logger';

interface UsePooledGraphOperationsOptions {
  enablePooling?: boolean;
  logStats?: boolean;
  statsInterval?: number;
}

/**
 * Hook for performing graph operations with object pooling
 */
export function usePooledGraphOperations(
  options: UsePooledGraphOperationsOptions = {}
) {
  const {
    enablePooling = true,
    logStats = false,
    statsInterval = 10000
  } = options;

  const poolManager = useRef(PoolManager.getInstance());
  
  // Log statistics periodically in development
  useEffect(() => {
    if (!logStats || process.env.NODE_ENV !== 'development') return;
    
    const interval = setInterval(() => {
      poolManager.current.logStats();
    }, statsInterval);
    
    return () => clearInterval(interval);
  }, [logStats, statsInterval]);

  /**
   * Calculate distance between two nodes using pooled vectors
   */
  const calculateDistance = useCallback((node1: GraphNode, node2: GraphNode): number => {
    if (!enablePooling) {
      const dx = node1.x! - node2.x!;
      const dy = node1.y! - node2.y!;
      return Math.sqrt(dx * dx + dy * dy);
    }

    return withVector2D(v => {
      v.x = node1.x! - node2.x!;
      v.y = node1.y! - node2.y!;
      return Math.sqrt(v.x * v.x + v.y * v.y);
    });
  }, [enablePooling]);

  /**
   * Calculate bounding box for nodes using pooling
   */
  const calculateBoundingBox = useCallback((nodes: GraphNode[]) => {
    if (nodes.length === 0) return null;

    if (!enablePooling) {
      const bounds = {
        minX: Infinity,
        minY: Infinity,
        maxX: -Infinity,
        maxY: -Infinity,
        width: 0,
        height: 0
      };

      nodes.forEach(node => {
        if (node.x !== undefined && node.y !== undefined) {
          bounds.minX = Math.min(bounds.minX, node.x);
          bounds.minY = Math.min(bounds.minY, node.y);
          bounds.maxX = Math.max(bounds.maxX, node.x);
          bounds.maxY = Math.max(bounds.maxY, node.y);
        }
      });

      bounds.width = bounds.maxX - bounds.minX;
      bounds.height = bounds.maxY - bounds.minY;
      return bounds;
    }

    return withBoundingBox(box => {
      box.minX = Infinity;
      box.minY = Infinity;
      box.maxX = -Infinity;
      box.maxY = -Infinity;

      nodes.forEach(node => {
        if (node.x !== undefined && node.y !== undefined) {
          box.minX = Math.min(box.minX, node.x);
          box.minY = Math.min(box.minY, node.y);
          box.maxX = Math.max(box.maxX, node.x);
          box.maxY = Math.max(box.maxY, node.y);
        }
      });

      box.width = box.maxX - box.minX;
      box.height = box.maxY - box.minY;

      // Return a copy since we're releasing the pooled object
      return {
        minX: box.minX,
        minY: box.minY,
        maxX: box.maxX,
        maxY: box.maxY,
        width: box.width,
        height: box.height
      };
    });
  }, [enablePooling]);

  /**
   * Process batch of delta updates using pooling
   */
  const processDeltaBatch = useCallback((
    deltas: any[],
    currentNodes: GraphNode[],
    currentLinks: GraphLink[]
  ) => {
    if (!enablePooling) {
      // Process without pooling
      const result = {
        nodes: [...currentNodes],
        links: [...currentLinks],
        operations: deltas.map(d => ({
          success: true,
          affected: [d.id],
          error: undefined,
          metadata: { type: d.type }
        }))
      };
      
      return result;
    }

    // Use pooled batch for operations
    const batch = new PooledBatch(DeltaPool);
    const resultBatch = new PooledBatch(GraphOperationResultPool);
    
    try {
      const operations: any[] = [];
      
      deltas.forEach(rawDelta => {
        const delta = batch.acquire();
        delta.id = rawDelta.id;
        delta.type = rawDelta.type;
        delta.entityType = rawDelta.entityType;
        delta.data = rawDelta.data;
        delta.timestamp = rawDelta.timestamp || Date.now();
        
        const result = resultBatch.acquire();
        result.success = true;
        result.affected = [delta.id];
        result.metadata = { type: delta.type };
        
        // Store copy of result
        operations.push({
          success: result.success,
          affected: [...result.affected],
          metadata: { ...result.metadata }
        });
      });
      
      return {
        nodes: currentNodes,
        links: currentLinks,
        operations
      };
    } finally {
      // Auto-release all pooled objects
      batch.releaseAll();
      resultBatch.releaseAll();
    }
  }, [enablePooling]);

  /**
   * Find nodes within radius using pooled vectors
   */
  const findNodesWithinRadius = useCallback((
    center: { x: number; y: number },
    radius: number,
    nodes: GraphNode[]
  ): GraphNode[] => {
    const radiusSquared = radius * radius;
    
    if (!enablePooling) {
      return nodes.filter(node => {
        if (node.x === undefined || node.y === undefined) return false;
        const dx = node.x - center.x;
        const dy = node.y - center.y;
        return (dx * dx + dy * dy) <= radiusSquared;
      });
    }

    const result: GraphNode[] = [];
    const vector = Vector2DPool.acquire();
    
    try {
      nodes.forEach(node => {
        if (node.x === undefined || node.y === undefined) return;
        
        vector.x = node.x - center.x;
        vector.y = node.y - center.y;
        
        if ((vector.x * vector.x + vector.y * vector.y) <= radiusSquared) {
          result.push(node);
        }
      });
    } finally {
      Vector2DPool.release(vector);
    }
    
    return result;
  }, [enablePooling]);

  /**
   * Calculate centroid of nodes using pooled vector
   */
  const calculateCentroid = useCallback((nodes: GraphNode[]): { x: number; y: number } | null => {
    if (nodes.length === 0) return null;
    
    if (!enablePooling) {
      let sumX = 0;
      let sumY = 0;
      let count = 0;
      
      nodes.forEach(node => {
        if (node.x !== undefined && node.y !== undefined) {
          sumX += node.x;
          sumY += node.y;
          count++;
        }
      });
      
      if (count === 0) return null;
      
      return {
        x: sumX / count,
        y: sumY / count
      };
    }

    return withVector2D(centroid => {
      let count = 0;
      
      nodes.forEach(node => {
        if (node.x !== undefined && node.y !== undefined) {
          centroid.x += node.x;
          centroid.y += node.y;
          count++;
        }
      });
      
      if (count === 0) return null;
      
      return {
        x: centroid.x / count,
        y: centroid.y / count
      };
    });
  }, [enablePooling]);

  /**
   * Batch process events using pooling
   */
  const processEventBatch = useCallback((events: any[]) => {
    if (!enablePooling) {
      return events.map(e => ({
        type: e.type,
        target: e.target,
        data: e.data,
        timestamp: e.timestamp || Date.now()
      }));
    }

    const batch = new PooledBatch(EventPool);
    const processed: any[] = [];
    
    try {
      events.forEach(rawEvent => {
        const event = batch.acquire();
        event.type = rawEvent.type;
        event.target = rawEvent.target;
        event.data = rawEvent.data;
        event.timestamp = rawEvent.timestamp || Date.now();
        
        // Store copy
        processed.push({
          type: event.type,
          target: event.target,
          data: event.data,
          timestamp: event.timestamp
        });
      });
    } finally {
      batch.releaseAll();
    }
    
    return processed;
  }, [enablePooling]);

  /**
   * Clear all pools
   */
  const clearPools = useCallback(() => {
    poolManager.current.clearAll();
    logger.log('usePooledGraphOperations: All pools cleared');
  }, []);

  /**
   * Get pool statistics
   */
  const getPoolStats = useCallback(() => {
    return poolManager.current.getAllStats();
  }, []);

  return {
    calculateDistance,
    calculateBoundingBox,
    processDeltaBatch,
    findNodesWithinRadius,
    calculateCentroid,
    processEventBatch,
    clearPools,
    getPoolStats
  };
}

export default usePooledGraphOperations;