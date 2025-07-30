import React, { useState, useEffect, useCallback, useRef } from 'react';
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

// Debounced save hook
const useDebouncedSave = (callback: () => void, delay: number) => {
  const timeoutRef = useRef<NodeJS.Timeout>();
  
  const debouncedSave = useCallback(() => {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
    }
    
    timeoutRef.current = setTimeout(() => {
      callback();
    }, delay);
  }, [callback, delay]);
  
  useEffect(() => {
    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, []);
  
  return debouncedSave;
};

// Hook for persisted NodeDetailsPanel sections
export const usePersistedSections = (defaultSections: SectionConfig[]) => {
  const [sections, setSections] = useState<SectionConfig[]>(defaultSections);
  const [isLoaded, setIsLoaded] = useState(false);
  
  // Load from storage on mount
  useEffect(() => {
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
  }, [defaultSections]);
  
  // Save to storage function
  const saveSections = useCallback(() => {
    if (!isLoaded) return; // Don't save during initial load
    
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
  
  // Debounced save
  const debouncedSave = useDebouncedSave(saveSections, 1000);
  
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

// Hook for persisted graph configuration
export const usePersistedGraphConfig = <T extends Record<string, unknown>>(defaultConfig: T) => {
  const [config, setConfig] = useState<T>(defaultConfig);
  const [isLoaded, setIsLoaded] = useState(false);
  
  // Load from storage on mount
  useEffect(() => {
    const stored = loadConfigFromStorage();
    if (stored?.graphConfig) {
      try {
        // Merge stored config with defaults
        const merged = mergeDifferentialConfig(defaultConfig, stored.graphConfig as Partial<T>);
        setConfig(merged);
      } catch (error) {
        // Failed to load sections, use defaults
      }
    }
    setIsLoaded(true);
  }, [defaultConfig]);
  
  // Save to storage function
  const saveConfig = useCallback(() => {
    if (!isLoaded) return; // Don't save during initial load
    
    try {
      const existing = loadConfigFromStorage() || { version: 1, timestamp: Date.now() };
      
      // Only store differences from defaults
      // Note: createDifferentialConfig now handles nodeTypeColors/nodeTypeVisibility specially
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
      // Failed to save config
    }
  }, [config, defaultConfig, isLoaded]);
  
  // Debounced save
  const debouncedSave = useDebouncedSave(saveConfig, 1000);
  
  // Enhanced setter that triggers save
  const setPersistedConfig = useCallback((newConfig: T | ((prev: T) => T)) => {
    setConfig(prev => {
      const updated = typeof newConfig === 'function' ? newConfig(prev) : newConfig;
      // Trigger save after state update
      setTimeout(debouncedSave, 0);
      return updated;
    });
  }, [debouncedSave]);
  
  return [config, setPersistedConfig, isLoaded] as const;
};

// Hook for complete configuration management
export const useConfigPersistence = () => {
  const resetAllConfig = useCallback(() => {
    try {
      clearPersistedConfig();
      // Force page reload to reset all state
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
      } else {
        // No config to export
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
        // Force page reload to apply imported configuration
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

// Hook specifically for node type configurations with special handling
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
    // Always load from storage to get the latest persisted values
    const stored = loadConfigFromStorage();
    const storedColors = stored?.graphConfig?.nodeTypeColors || {};
    const storedVisibility = stored?.graphConfig?.nodeTypeVisibility || {};
    
    // Use provided values as base, or empty objects if not provided
    const baseColors = providedColors || {};
    const baseVisibility = providedVisibility || {};
    
    try {
      // Start with base values, then overlay ALL stored values
      // This ensures we never lose persisted colors for types not in current graph
      const mergedColors = { ...baseColors };
      const mergedVisibility = { ...baseVisibility };
      
      // Apply ALL stored colors (not just for types in baseColors)
      Object.entries(storedColors).forEach(([type, color]) => {
        mergedColors[type] = color;
      });
      
      // Apply ALL stored visibility (not just for types in baseVisibility)
      Object.entries(storedVisibility).forEach(([type, visible]) => {
        mergedVisibility[type] = visible;
      });
      
      return { colors: mergedColors, visibility: mergedVisibility };
    } catch (error) {
      // Fallback to at least returning stored values
      return { colors: { ...baseColors, ...storedColors }, visibility: { ...baseVisibility, ...storedVisibility } };
    }
  }, []); // Remove dependencies to make it stable
  
  // Set isLoaded on mount
  React.useEffect(() => {
    setIsLoaded(true);
  }, []);
  
  return { mergeWithPersisted, isLoaded };
};