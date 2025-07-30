import { useRef, useCallback, useEffect } from 'react';
import type { GraphConfig } from '../contexts/configTypes';

interface DebouncedConfigOptions {
  delay?: number;
  immediate?: boolean;
}

export function useDebouncedConfig(
  updateConfig: (updates: Partial<GraphConfig>) => void,
  options: DebouncedConfigOptions = {}
) {
  const { delay = 100, immediate = false } = options;
  const timeoutRef = useRef<NodeJS.Timeout | null>(null);
  const pendingUpdatesRef = useRef<Partial<GraphConfig>>({});
  const lastUpdateTimeRef = useRef<number>(0);
  
  // Clear pending updates on unmount
  useEffect(() => {
    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, []);
  
  const debouncedUpdate = useCallback((updates: Partial<GraphConfig>) => {
    const now = Date.now();
    
    // Merge with pending updates
    pendingUpdatesRef.current = {
      ...pendingUpdatesRef.current,
      ...updates
    };
    
    // Immediate update for first call
    if (immediate && now - lastUpdateTimeRef.current > delay * 2) {
      updateConfig(pendingUpdatesRef.current);
      pendingUpdatesRef.current = {};
      lastUpdateTimeRef.current = now;
      return;
    }
    
    // Clear existing timeout
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
    }
    
    // Schedule debounced update
    timeoutRef.current = setTimeout(() => {
      if (Object.keys(pendingUpdatesRef.current).length > 0) {
        updateConfig(pendingUpdatesRef.current);
        pendingUpdatesRef.current = {};
        lastUpdateTimeRef.current = Date.now();
      }
    }, delay);
  }, [updateConfig, delay, immediate]);
  
  // Force flush pending updates
  const flushUpdates = useCallback(() => {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
    
    if (Object.keys(pendingUpdatesRef.current).length > 0) {
      updateConfig(pendingUpdatesRef.current);
      pendingUpdatesRef.current = {};
      lastUpdateTimeRef.current = Date.now();
    }
  }, [updateConfig]);
  
  return {
    debouncedUpdate,
    flushUpdates,
    hasPendingUpdates: () => Object.keys(pendingUpdatesRef.current).length > 0
  };
}