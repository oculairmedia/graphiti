import { useState, useEffect, useCallback, useRef } from 'react';
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
          const stored = stored.nodeDetailsSections![defaultSection.id];
          if (stored) {
            return {
              ...defaultSection,
              isCollapsed: stored.isCollapsed,
              order: stored.order,
              isVisible: stored.isVisible
            };
          }
          return defaultSection;
        });
        
        // Sort by order
        mergedSections.sort((a, b) => a.order - b.order);
        setSections(mergedSections);
        console.log('usePersistedSections: Loaded sections from storage');
      } catch (error) {
        console.error('usePersistedSections: Failed to merge stored sections:', error);
      }
    }
    setIsLoaded(true);
  }, []);
  
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
      console.error('usePersistedSections: Failed to save sections:', error);
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
export const usePersistedGraphConfig = <T extends Record<string, any>>(defaultConfig: T) => {
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
        console.log('usePersistedGraphConfig: Loaded configuration from storage');
      } catch (error) {
        console.error('usePersistedGraphConfig: Failed to merge stored config:', error);
      }
    }
    setIsLoaded(true);
  }, []);
  
  // Save to storage function
  const saveConfig = useCallback(() => {
    if (!isLoaded) return; // Don't save during initial load
    
    try {
      const existing = loadConfigFromStorage() || { version: 1, timestamp: Date.now() };
      
      // Only store differences from defaults
      const diff = createDifferentialConfig(config, defaultConfig);
      
      const updated: PersistedConfig = {
        ...existing,
        graphConfig: diff as PersistedGraphConfig
      };
      
      saveConfigToStorage(updated);
    } catch (error) {
      console.error('usePersistedGraphConfig: Failed to save config:', error);
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
      console.error('useConfigPersistence: Failed to reset configuration:', error);
    }
  }, []);
  
  const exportConfig = useCallback(() => {
    try {
      const stored = loadConfigFromStorage();
      if (stored) {
        exportConfigToFile(stored);
      } else {
        console.warn('useConfigPersistence: No configuration to export');
      }
    } catch (error) {
      console.error('useConfigPersistence: Failed to export configuration:', error);
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
      console.error('useConfigPersistence: Failed to import configuration:', error);
      return false;
    }
  }, []);
  
  const getStorageInfo = useCallback(() => {
    try {
      return getStorageUsage();
    } catch (error) {
      console.error('useConfigPersistence: Failed to get storage info:', error);
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
  const mergeWithPersisted = useCallback(() => {
    if (isLoaded) return { colors: currentNodeTypeColors, visibility: currentNodeTypeVisibility };
    
    const stored = loadConfigFromStorage();
    if (!stored?.graphConfig?.nodeTypeColors && !stored?.graphConfig?.nodeTypeVisibility) {
      setIsLoaded(true);
      return { colors: currentNodeTypeColors, visibility: currentNodeTypeVisibility };
    }
    
    try {
      const mergedColors = { ...currentNodeTypeColors };
      const mergedVisibility = { ...currentNodeTypeVisibility };
      
      // Apply stored colors for existing types, keep defaults for new types
      if (stored.graphConfig.nodeTypeColors) {
        Object.entries(stored.graphConfig.nodeTypeColors).forEach(([type, color]) => {
          if (type in currentNodeTypeColors) {
            mergedColors[type] = color;
          }
        });
      }
      
      // Apply stored visibility for existing types, keep defaults for new types
      if (stored.graphConfig.nodeTypeVisibility) {
        Object.entries(stored.graphConfig.nodeTypeVisibility).forEach(([type, visible]) => {
          if (type in currentNodeTypeVisibility) {
            mergedVisibility[type] = visible;
          }
        });
      }
      
      setIsLoaded(true);
      console.log('usePersistedNodeTypes: Merged node type configurations');
      return { colors: mergedColors, visibility: mergedVisibility };
    } catch (error) {
      console.error('usePersistedNodeTypes: Failed to merge node type configs:', error);
      setIsLoaded(true);
      return { colors: currentNodeTypeColors, visibility: currentNodeTypeVisibility };
    }
  }, [currentNodeTypeColors, currentNodeTypeVisibility, isLoaded]);
  
  return { mergeWithPersisted, isLoaded };
};