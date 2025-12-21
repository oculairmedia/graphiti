/**
 * Persisted Configuration Hooks
 * 
 * GRAPH-83: Uses canonical useDebouncedCallback instead of inline implementation
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useDebouncedCallback } from './useDebouncedCallback';
import { 
  saveConfigToStorage, 
  loadConfigFromStorage, 
  createDifferentialConfig,
  mergeDifferentialConfig,
  clearPersistedConfig,
  exportConfigToFile,
  importConfigFromFile,
  getStorageUsage,
  type PersistedConfig,
  type PersistedGraphConfig,
  type PersistedNodeDetailsConfig 
} from '@/utils/configPersistence';
import type { SectionConfig } from '@/components/ui/CollapsibleSection';

// ============================================================================
// usePersistedSections - NodeDetailsPanel section state
// ============================================================================

export const usePersistedSections = (defaultSections: SectionConfig[]) => {
  // PERFORMANCE FIX: Use ref to track if we've initialized to avoid re-running effect
  const hasInitializedRef = useRef(false);
  const [sections, setSections] = useState<SectionConfig[]>(defaultSections);
  const [isLoaded, setIsLoaded] = useState(false);
  
  // Load from storage on mount - only run once
  useEffect(() => {
    // PERFORMANCE FIX: Only run initialization once
    if (hasInitializedRef.current) return;
    hasInitializedRef.current = true;
    
    const stored = loadConfigFromStorage();
    if (stored?.nodeDetailsSections) {
      try {
        // Merge stored preferences with default sections
        const mergedSections = defaultSections.map(defaultSection => {
          const storedSection = stored.nodeDetailsSections![defaultSection.id];
          if (storedSection) {
            return {
              ...defaultSection,
              isCollapsed: storedSection.isCollapsed,
              order: storedSection.order,
              isVisible: storedSection.isVisible
            };
          }
          return defaultSection;
        });
        
        // Sort by order
        mergedSections.sort((a, b) => a.order - b.order);
        setSections(mergedSections);
      } catch (error) {
        // Failed to load sections, use defaults
      }
    }
    setIsLoaded(true);
  }, []); // Empty deps - only run once on mount
  
  // Save to storage function
  const saveSections = useCallback(() => {
    if (!isLoaded) return;
    
    try {
      const existing = loadConfigFromStorage() || { version: 1, timestamp: Date.now() };
      
      // Convert sections to storage format
      const sectionsConfig: PersistedNodeDetailsConfig = {};
      sections.forEach(section => {
        sectionsConfig[section.id] = {
          isCollapsed: section.isCollapsed,
          order: section.order,
          isVisible: section.isVisible
        };
      });
      
      const updated: PersistedConfig = {
        ...existing,
        nodeDetailsSections: sectionsConfig
      };
      
      saveConfigToStorage(updated);
    } catch (error) {
      // Failed to save sections
    }
  }, [sections, isLoaded]);
  
  // GRAPH-83: Use canonical debounced callback
  const debouncedSave = useDebouncedCallback(saveSections, 300);
  
  // Enhanced setter that triggers save
  const setPersistedSections = useCallback((newSections: SectionConfig[] | ((prev: SectionConfig[]) => SectionConfig[])) => {
    setSections(prev => {
      const updated = typeof newSections === 'function' ? newSections(prev) : newSections;
      // Trigger save after state update
      setTimeout(debouncedSave, 0);
      return updated;
    });
  }, [debouncedSave]);
  
  return [sections, setPersistedSections, isLoaded] as const;
};

// ============================================================================
// usePersistedGraphConfig - Graph visualization config
// ============================================================================

export const usePersistedGraphConfig = <T extends Record<string, unknown>>(defaultConfig: T) => {
  const [config, setConfig] = useState<T>(defaultConfig);
  const [isLoaded, setIsLoaded] = useState(false);
  const isInitialMount = useRef(true);
  
  // Load from storage on mount
  useEffect(() => {
    if (!isInitialMount.current) return;
    isInitialMount.current = false;
    
    const loadPersistedData = async () => {
      try {
        const stored = loadConfigFromStorage();
        if (stored?.graphConfig) {
          console.log('usePersistedGraphConfig: Loading stored config', stored.graphConfig);
          const merged = mergeDifferentialConfig(defaultConfig, stored.graphConfig as Partial<T>);
          setConfig(merged);
        }
      } catch (error) {
        console.error('usePersistedGraphConfig: Failed to load config', error);
      } finally {
        setIsLoaded(true);
      }
    };
    
    loadPersistedData();
  }, []);
  
  // Save to storage function
  const saveConfig = useCallback(() => {
    if (!isLoaded) return;
    
    try {
      const existing = loadConfigFromStorage() || { version: 1, timestamp: Date.now() };
      const diff = createDifferentialConfig(config, defaultConfig);
      
      const updated: PersistedConfig = {
        ...existing,
        graphConfig: {
          ...(existing.graphConfig || {}),
          ...diff
        } as PersistedGraphConfig
      };
      
      saveConfigToStorage(updated);
    } catch (error) {
      console.error('usePersistedGraphConfig: Failed to save config', error);
    }
  }, [config, defaultConfig, isLoaded]);
  
  // GRAPH-83: Use canonical debounced callback
  const debouncedSave = useDebouncedCallback(saveConfig, 300);
  
  // Enhanced setter that triggers save
  const setPersistedConfig = useCallback((newConfig: T | ((prev: T) => T)) => {
    setConfig(newConfig);
  }, []);
  
  // Save config when it changes (after initial load)
  const isFirstRender = useRef(true);
  useEffect(() => {
    if (isFirstRender.current) {
      isFirstRender.current = false;
      return;
    }
    
    if (isLoaded) {
      debouncedSave();
    }
  }, [config, isLoaded, debouncedSave]);
  
  return [config, setPersistedConfig, isLoaded] as const;
};

// ============================================================================
// useConfigPersistence - Config management utilities
// ============================================================================

export const useConfigPersistence = () => {
  const resetAllConfig = useCallback(() => {
    try {
      clearPersistedConfig();
      window.location.reload();
    } catch (error) {
      // Failed to clear config
    }
  }, []);
  
  const exportConfig = useCallback(() => {
    try {
      const stored = loadConfigFromStorage();
      if (stored) {
        exportConfigToFile(stored);
      }
    } catch (error) {
      // Export failed
    }
  }, []);
  
  const importConfig = useCallback(async (file: File) => {
    try {
      const config = await importConfigFromFile(file);
      
      if (config) {
        saveConfigToStorage(config);
        window.location.reload();
        return true;
      }
      return false;
    } catch (error) {
      return false;
    }
  }, []);
  
  const getStorageInfo = useCallback(() => {
    try {
      return getStorageUsage();
    } catch (error) {
      return { used: 0, available: 0 };
    }
  }, []);
  
  return {
    resetAllConfig,
    exportConfig,
    importConfig,
    getStorageInfo
  };
};

// ============================================================================
// usePersistedNodeTypes - Node type color/visibility persistence
// ============================================================================

export const usePersistedNodeTypes = (
  currentNodeTypeColors: Record<string, string>,
  currentNodeTypeVisibility: Record<string, boolean>
) => {
  const [isLoaded, setIsLoaded] = useState(false);
  
  // Load persisted node type settings and merge with current types
  const mergeWithPersisted = useCallback((
    providedColors?: Record<string, string>,
    providedVisibility?: Record<string, boolean>
  ) => {
    const stored = loadConfigFromStorage();
    const storedColors = stored?.graphConfig?.nodeTypeColors || {};
    const storedVisibility = stored?.graphConfig?.nodeTypeVisibility || {};
    
    const baseColors = providedColors || {};
    const baseVisibility = providedVisibility || {};
    
    try {
      // Start with base values, then overlay ALL stored values
      const mergedColors = { ...baseColors };
      const mergedVisibility = { ...baseVisibility };
      
      // Apply ALL stored colors
      Object.entries(storedColors).forEach(([type, color]) => {
        mergedColors[type] = color;
      });
      
      // Apply ALL stored visibility
      Object.entries(storedVisibility).forEach(([type, visible]) => {
        mergedVisibility[type] = visible;
      });
      
      return { colors: mergedColors, visibility: mergedVisibility };
    } catch (error) {
      return { 
        colors: { ...baseColors, ...storedColors }, 
        visibility: { ...baseVisibility, ...storedVisibility } 
      };
    }
  }, []);
  
  useEffect(() => {
    setIsLoaded(true);
  }, []);
  
  return { mergeWithPersisted, isLoaded };
};
