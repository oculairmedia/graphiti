import React, { useState, useCallback, useEffect, useRef } from 'react';
import { GraphNode } from '../../../api/types';
import { logger } from '../../../utils/logger';

interface GlowConfig {
  color: string;
  intensity: number;
  duration: number;
  pulseCount?: number;
}

interface NodeGlowManagerProps {
  nodes: GraphNode[];
  onGlowUpdate?: (glowingNodes: Map<string, GlowConfig>) => void;
  defaultGlowConfig?: GlowConfig;
  maxGlowingNodes?: number;
  autoClearAfter?: number;
}

/**
 * NodeGlowManager - Manages node highlighting and glowing effects
 * 
 * Features:
 * - Individual node glow control
 * - Batch glow operations
 * - Animated pulse effects
 * - Auto-clear functionality
 * - Memory-efficient state management
 */
export const NodeGlowManager: React.FC<NodeGlowManagerProps> = ({
  nodes,
  onGlowUpdate,
  defaultGlowConfig = {
    color: '#fbbf24',
    intensity: 1,
    duration: 500
  },
  maxGlowingNodes = 100,
  autoClearAfter = 5000
}) => {
  const [glowingNodes, setGlowingNodes] = useState<Map<string, GlowConfig>>(new Map());
  const clearTimersRef = useRef<Map<string, NodeJS.Timeout>>(new Map());

  // Notify parent of glow updates
  useEffect(() => {
    onGlowUpdate?.(glowingNodes);
    logger.debug('NodeGlowManager: Glow state updated', {
      count: glowingNodes.size
    });
  }, [glowingNodes, onGlowUpdate]);

  // Add glow to a single node
  const addGlow = useCallback((nodeId: string, config?: Partial<GlowConfig>) => {
    setGlowingNodes(prev => {
      const newMap = new Map(prev);
      
      // Check max limit
      if (!newMap.has(nodeId) && newMap.size >= maxGlowingNodes) {
        logger.warn('NodeGlowManager: Max glowing nodes reached');
        return prev;
      }

      // Clear existing timer if any
      const existingTimer = clearTimersRef.current.get(nodeId);
      if (existingTimer) {
        clearTimeout(existingTimer);
        clearTimersRef.current.delete(nodeId);
      }

      // Set new glow
      const glowConfig: GlowConfig = {
        ...defaultGlowConfig,
        ...config
      };
      newMap.set(nodeId, glowConfig);

      // Set auto-clear timer if configured
      if (autoClearAfter > 0) {
        const timer = setTimeout(() => {
          removeGlow(nodeId);
        }, autoClearAfter);
        clearTimersRef.current.set(nodeId, timer);
      }

      logger.log('NodeGlowManager: Added glow to node', { nodeId, config: glowConfig });
      return newMap;
    });
  }, [defaultGlowConfig, maxGlowingNodes, autoClearAfter]);

  // Remove glow from a single node
  const removeGlow = useCallback((nodeId: string) => {
    setGlowingNodes(prev => {
      const newMap = new Map(prev);
      newMap.delete(nodeId);
      
      // Clear timer if exists
      const timer = clearTimersRef.current.get(nodeId);
      if (timer) {
        clearTimeout(timer);
        clearTimersRef.current.delete(nodeId);
      }

      logger.log('NodeGlowManager: Removed glow from node', { nodeId });
      return newMap;
    });
  }, []);

  // Add glow to multiple nodes
  const addGlowBatch = useCallback((nodeIds: string[], config?: Partial<GlowConfig>) => {
    setGlowingNodes(prev => {
      const newMap = new Map(prev);
      const glowConfig: GlowConfig = {
        ...defaultGlowConfig,
        ...config
      };

      nodeIds.forEach(nodeId => {
        // Check max limit
        if (!newMap.has(nodeId) && newMap.size >= maxGlowingNodes) {
          return;
        }

        // Clear existing timer
        const existingTimer = clearTimersRef.current.get(nodeId);
        if (existingTimer) {
          clearTimeout(existingTimer);
        }

        newMap.set(nodeId, glowConfig);

        // Set auto-clear timer
        if (autoClearAfter > 0) {
          const timer = setTimeout(() => {
            removeGlow(nodeId);
          }, autoClearAfter);
          clearTimersRef.current.set(nodeId, timer);
        }
      });

      logger.log('NodeGlowManager: Added batch glow', {
        count: nodeIds.length,
        config: glowConfig
      });
      return newMap;
    });
  }, [defaultGlowConfig, maxGlowingNodes, autoClearAfter, removeGlow]);

  // Remove glow from multiple nodes
  const removeGlowBatch = useCallback((nodeIds: string[]) => {
    setGlowingNodes(prev => {
      const newMap = new Map(prev);
      
      nodeIds.forEach(nodeId => {
        newMap.delete(nodeId);
        
        // Clear timer
        const timer = clearTimersRef.current.get(nodeId);
        if (timer) {
          clearTimeout(timer);
          clearTimersRef.current.delete(nodeId);
        }
      });

      logger.log('NodeGlowManager: Removed batch glow', { count: nodeIds.length });
      return newMap;
    });
  }, []);

  // Clear all glows
  const clearAllGlows = useCallback(() => {
    // Clear all timers
    clearTimersRef.current.forEach(timer => clearTimeout(timer));
    clearTimersRef.current.clear();
    
    setGlowingNodes(new Map());
    logger.log('NodeGlowManager: Cleared all glows');
  }, []);

  // Toggle glow on a node
  const toggleGlow = useCallback((nodeId: string, config?: Partial<GlowConfig>) => {
    setGlowingNodes(prev => {
      const newMap = new Map(prev);
      
      if (newMap.has(nodeId)) {
        // Remove glow
        newMap.delete(nodeId);
        
        const timer = clearTimersRef.current.get(nodeId);
        if (timer) {
          clearTimeout(timer);
          clearTimersRef.current.delete(nodeId);
        }
      } else {
        // Add glow
        if (newMap.size < maxGlowingNodes) {
          const glowConfig: GlowConfig = {
            ...defaultGlowConfig,
            ...config
          };
          newMap.set(nodeId, glowConfig);

          if (autoClearAfter > 0) {
            const timer = setTimeout(() => {
              removeGlow(nodeId);
            }, autoClearAfter);
            clearTimersRef.current.set(nodeId, timer);
          }
        }
      }

      logger.log('NodeGlowManager: Toggled glow', { nodeId, hasGlow: newMap.has(nodeId) });
      return newMap;
    });
  }, [defaultGlowConfig, maxGlowingNodes, autoClearAfter, removeGlow]);

  // Pulse effect
  const pulseGlow = useCallback((nodeId: string, config?: Partial<GlowConfig>) => {
    const pulseConfig: GlowConfig = {
      ...defaultGlowConfig,
      ...config,
      pulseCount: config?.pulseCount || 3
    };

    let pulseCount = 0;
    const pulseInterval = setInterval(() => {
      if (pulseCount >= (pulseConfig.pulseCount || 3)) {
        clearInterval(pulseInterval);
        removeGlow(nodeId);
        return;
      }

      if (pulseCount % 2 === 0) {
        addGlow(nodeId, pulseConfig);
      } else {
        removeGlow(nodeId);
      }
      
      pulseCount++;
    }, pulseConfig.duration);

    logger.log('NodeGlowManager: Started pulse effect', { nodeId, config: pulseConfig });
  }, [defaultGlowConfig, addGlow, removeGlow]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      clearTimersRef.current.forEach(timer => clearTimeout(timer));
      clearTimersRef.current.clear();
      logger.log('NodeGlowManager: Cleanup on unmount');
    };
  }, []);

  // Public API could be exposed via context or ref
  // For now, just manage internal state

  return null; // This is a non-visual component
};

// Hook for using glow manager
export const useNodeGlow = () => {
  const [glowingNodes, setGlowingNodes] = useState<Set<string>>(new Set());

  const addGlow = useCallback((nodeId: string) => {
    setGlowingNodes(prev => new Set(prev).add(nodeId));
  }, []);

  const removeGlow = useCallback((nodeId: string) => {
    setGlowingNodes(prev => {
      const newSet = new Set(prev);
      newSet.delete(nodeId);
      return newSet;
    });
  }, []);

  const toggleGlow = useCallback((nodeId: string) => {
    setGlowingNodes(prev => {
      const newSet = new Set(prev);
      if (newSet.has(nodeId)) {
        newSet.delete(nodeId);
      } else {
        newSet.add(nodeId);
      }
      return newSet;
    });
  }, []);

  const clearAllGlows = useCallback(() => {
    setGlowingNodes(new Set());
  }, []);

  const isGlowing = useCallback((nodeId: string) => {
    return glowingNodes.has(nodeId);
  }, [glowingNodes]);

  return {
    glowingNodes,
    addGlow,
    removeGlow,
    toggleGlow,
    clearAllGlows,
    isGlowing
  };
};

export default NodeGlowManager;