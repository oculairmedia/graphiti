/**
 * useGraphGlowEffects Hook
 * Manages glowing node effects for real-time access highlighting
 * Extracted from GraphCanvasV2 for better separation of concerns (GRAPH-35)
 */

import { useState, useRef, useCallback, useEffect } from 'react';

interface GlowEffectsOptions {
  fadeDuration?: number;  // Duration in ms before glow fades
  cleanupDelay?: number;  // Delay after fade duration to clean up
}

interface GlowEffectsReturn {
  glowingNodes: Map<string, number>;
  setGlowingNodes: React.Dispatch<React.SetStateAction<Map<string, number>>>;
  addGlowingNode: (nodeId: string) => void;
  addGlowingNodes: (nodeIds: string[]) => void;
  clearGlowingNodes: () => void;
  isNodeGlowing: (nodeId: string) => boolean;
  glowTimeoutRef: React.MutableRefObject<NodeJS.Timeout | null>;
}

export function useGraphGlowEffects(options: GlowEffectsOptions = {}): GlowEffectsReturn {
  const { fadeDuration = 2000, cleanupDelay = 100 } = options;
  
  // Glowing nodes state - Map of nodeId -> timestamp when glow started
  const [glowingNodes, setGlowingNodes] = useState<Map<string, number>>(new Map());
  const glowTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  
  // Add a single glowing node
  // PERFORMANCE FIX (GRAPH-72): Only create new Map if node wasn't already glowing
  const addGlowingNode = useCallback((nodeId: string) => {
    setGlowingNodes(prev => {
      // Skip if node is already glowing with recent timestamp (within 100ms)
      const existingTime = prev.get(nodeId);
      if (existingTime && Date.now() - existingTime < 100) {
        return prev; // Return same reference to avoid re-render
      }
      // Only create new Map when actually adding/updating
      const updated = new Map(prev);
      updated.set(nodeId, Date.now());
      return updated;
    });
  }, []);
  
  // Add multiple glowing nodes
  const addGlowingNodes = useCallback((nodeIds: string[]) => {
    const now = Date.now();
    setGlowingNodes(() => {
      const updated = new Map<string, number>();
      nodeIds.forEach(nodeId => {
        updated.set(nodeId, now);
      });
      return updated;
    });
  }, []);
  
  // Clear all glowing nodes
  const clearGlowingNodes = useCallback(() => {
    setGlowingNodes(new Map());
  }, []);
  
  // Check if a node is currently glowing
  const isNodeGlowing = useCallback((nodeId: string): boolean => {
    return glowingNodes.has(nodeId);
  }, [glowingNodes]);
  
  // Clean up old glowing nodes after fade duration
  // PERFORMANCE FIX (GRAPH-72): Only create new Map when there are expired nodes
  useEffect(() => {
    if (glowingNodes.size === 0) return;
    
    const timeout = setTimeout(() => {
      const now = Date.now();
      
      // First pass: check if any nodes need removal (no allocation)
      let hasExpired = false;
      for (const [, startTime] of glowingNodes) {
        if (now - startTime >= fadeDuration) {
          hasExpired = true;
          break;
        }
      }
      
      // Only allocate new Map if we found expired nodes
      if (hasExpired) {
        const updatedGlowingNodes = new Map<string, number>();
        glowingNodes.forEach((startTime, nodeId) => {
          if (now - startTime < fadeDuration) {
            updatedGlowingNodes.set(nodeId, startTime);
          }
        });
        setGlowingNodes(updatedGlowingNodes);
      }
    }, fadeDuration + cleanupDelay);
    
    return () => clearTimeout(timeout);
  }, [glowingNodes, fadeDuration, cleanupDelay]);
  
  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (glowTimeoutRef.current) {
        clearTimeout(glowTimeoutRef.current);
      }
    };
  }, []);
  
  return {
    glowingNodes,
    setGlowingNodes,
    addGlowingNode,
    addGlowingNodes,
    clearGlowingNodes,
    isNodeGlowing,
    glowTimeoutRef
  };
}
