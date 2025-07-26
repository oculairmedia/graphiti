import type { SectionConfig } from '@/components/ui/CollapsibleSection';

// Storage keys
export const STORAGE_KEYS = {
  MAIN_CONFIG: 'graphiti.config.v1',
  BACKUP_CONFIG: 'graphiti.config.backup',
  SCHEMA_VERSION: 'graphiti.schema.version'
} as const;

// Current schema version for migrations
export const CURRENT_SCHEMA_VERSION = 1;

// Configuration interfaces
export interface PersistedNodeDetailsConfig {
  [sectionId: string]: {
    isCollapsed: boolean;
    order: number;
    isVisible: boolean;
  };
}

export interface PersistedGraphConfig {
  // Physics
  gravity?: number;
  repulsion?: number;
  centerForce?: number;
  friction?: number;
  linkSpring?: number;
  linkDistance?: number;
  mouseRepulsion?: number;
  simulationDecay?: number;
  simulationRepulsionTheta?: number;
  disableSimulation?: boolean;
  spaceSize?: number;
  
  // Appearance
  linkWidth?: number;
  linkWidthScale?: number;
  linkOpacity?: number;
  linkColor?: string;
  backgroundColor?: string;
  
  // Node sizing
  minNodeSize?: number;
  maxNodeSize?: number;
  sizeMultiplier?: number;
  nodeOpacity?: number;
  sizeMapping?: string;
  
  // Node types (only user-customized colors/visibility)
  nodeTypeColors?: Record<string, string>;
  nodeTypeVisibility?: Record<string, boolean>;
  
  // Labels
  showLabels?: boolean;
  showHoveredNodeLabel?: boolean;
  labelColor?: string;
  labelSize?: number;
  labelOpacity?: number;
  
  // Visual preferences
  colorScheme?: string;
  gradientHighColor?: string;
  gradientLowColor?: string;
  
  // Layout
  layout?: string;
  hierarchyDirection?: string;
  radialCenter?: string;
  circularOrdering?: string;
  clusterBy?: string;
  
  // Filters
  filteredNodeTypes?: string[];
  minDegree?: number;
  maxDegree?: number;
  minPagerank?: number;
  maxPagerank?: number;
  minConnections?: number;
  maxConnections?: number;
  startDate?: string;
  endDate?: string;
}

export interface PersistedConfig {
  version: number;
  timestamp: number;
  nodeDetailsSections?: PersistedNodeDetailsConfig;
  graphConfig?: PersistedGraphConfig;
}

// Utility functions
export const isStorageAvailable = (): boolean => {
  try {
    const test = '__storage_test__';
    localStorage.setItem(test, test);
    localStorage.removeItem(test);
    return true;
  } catch {
    return false;
  }
};

export const getStorageUsage = (): { used: number; available: number } => {
  if (!isStorageAvailable()) return { used: 0, available: 0 };
  
  let used = 0;
  for (const key in localStorage) {
    if (localStorage.hasOwnProperty(key)) {
      used += localStorage[key].length + key.length;
    }
  }
  
  // localStorage limit is typically 5-10MB, we'll assume 5MB conservatively
  const available = 5 * 1024 * 1024;
  return { used, available };
};

// Core persistence functions
export const saveConfigToStorage = (config: PersistedConfig): boolean => {
  if (!isStorageAvailable()) {
    console.warn('ConfigPersistence: localStorage not available');
    return false;
  }

  try {
    // Create backup of current config before saving new one
    const existing = localStorage.getItem(STORAGE_KEYS.MAIN_CONFIG);
    if (existing) {
      localStorage.setItem(STORAGE_KEYS.BACKUP_CONFIG, existing);
    }

    const configWithTimestamp = {
      ...config,
      version: CURRENT_SCHEMA_VERSION,
      timestamp: Date.now()
    };

    const serialized = JSON.stringify(configWithTimestamp);
    localStorage.setItem(STORAGE_KEYS.MAIN_CONFIG, serialized);
    
    console.log('ConfigPersistence: Configuration saved successfully');
    return true;
  } catch (error) {
    console.error('ConfigPersistence: Failed to save configuration:', error);
    
    // Handle quota exceeded
    if (error instanceof Error && error.name === 'QuotaExceededError') {
      console.warn('ConfigPersistence: Storage quota exceeded, clearing backup');
      try {
        localStorage.removeItem(STORAGE_KEYS.BACKUP_CONFIG);
        localStorage.setItem(STORAGE_KEYS.MAIN_CONFIG, JSON.stringify(config));
        return true;
      } catch {
        console.error('ConfigPersistence: Could not save even after clearing backup');
      }
    }
    
    return false;
  }
};

export const loadConfigFromStorage = (): PersistedConfig | null => {
  if (!isStorageAvailable()) {
    return null;
  }

  try {
    const stored = localStorage.getItem(STORAGE_KEYS.MAIN_CONFIG);
    if (!stored) {
      return null;
    }

    const parsed = JSON.parse(stored) as PersistedConfig;
    
    // Validate basic structure
    if (!parsed || typeof parsed !== 'object' || typeof parsed.version !== 'number') {
      console.warn('ConfigPersistence: Invalid configuration structure, ignoring');
      return null;
    }

    // Handle version migrations if needed
    if (parsed.version < CURRENT_SCHEMA_VERSION) {
      const migrated = migrateConfig(parsed);
      if (migrated) {
        saveConfigToStorage(migrated); // Save migrated version
        return migrated;
      }
    }

    return parsed;
  } catch (error) {
    console.error('ConfigPersistence: Failed to load configuration:', error);
    
    // Try backup
    try {
      const backup = localStorage.getItem(STORAGE_KEYS.BACKUP_CONFIG);
      if (backup) {
        console.log('ConfigPersistence: Loading from backup');
        const parsed = JSON.parse(backup) as PersistedConfig;
        return parsed;
      }
    } catch (backupError) {
      console.error('ConfigPersistence: Backup also corrupted:', backupError);
    }
    
    return null;
  }
};

export const clearPersistedConfig = (): void => {
  if (!isStorageAvailable()) return;
  
  try {
    localStorage.removeItem(STORAGE_KEYS.MAIN_CONFIG);
    localStorage.removeItem(STORAGE_KEYS.BACKUP_CONFIG);
    console.log('ConfigPersistence: All configuration cleared');
  } catch (error) {
    console.error('ConfigPersistence: Failed to clear configuration:', error);
  }
};

// Migration system for future schema changes
const migrateConfig = (config: PersistedConfig): PersistedConfig | null => {
  try {
    let migrated = { ...config };
    
    // Version 0 to 1 migration (if needed in future)
    if (config.version === 0) {
      // Add any migration logic here
      migrated.version = 1;
    }
    
    return migrated;
  } catch (error) {
    console.error('ConfigPersistence: Migration failed:', error);
    return null;
  }
};

// Utility to create differential config (only store changes from defaults)
export const createDifferentialConfig = <T extends Record<string, any>>(
  current: T,
  defaults: T
): Partial<T> => {
  const diff: Partial<T> = {};
  
  for (const key in current) {
    if (current[key] !== defaults[key]) {
      // Handle nested objects
      if (typeof current[key] === 'object' && current[key] !== null && !Array.isArray(current[key])) {
        const nestedDiff = createDifferentialConfig(current[key], defaults[key] || {});
        if (Object.keys(nestedDiff).length > 0) {
          diff[key] = nestedDiff as T[typeof key];
        }
      } else {
        diff[key] = current[key];
      }
    }
  }
  
  return diff;
};

// Utility to merge differential config back with defaults
export const mergeDifferentialConfig = <T extends Record<string, any>>(
  defaults: T,
  diff: Partial<T>
): T => {
  const merged = { ...defaults };
  
  for (const key in diff) {
    if (diff[key] !== undefined) {
      // Handle nested objects
      if (typeof diff[key] === 'object' && diff[key] !== null && !Array.isArray(diff[key]) &&
          typeof defaults[key] === 'object' && defaults[key] !== null && !Array.isArray(defaults[key])) {
        merged[key] = mergeDifferentialConfig(defaults[key], diff[key] as any);
      } else {
        merged[key] = diff[key] as T[typeof key];
      }
    }
  }
  
  return merged;
};

// Export configuration as JSON file
export const exportConfigToFile = (config: PersistedConfig): void => {
  try {
    const blob = new Blob([JSON.stringify(config, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `graphiti-config-${new Date().toISOString().split('T')[0]}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  } catch (error) {
    console.error('ConfigPersistence: Failed to export configuration:', error);
  }
};

// Import configuration from file
export const importConfigFromFile = (file: File): Promise<PersistedConfig | null> => {
  return new Promise((resolve) => {
    const reader = new FileReader();
    reader.onload = (event) => {
      try {
        const content = event.target?.result as string;
        const config = JSON.parse(content) as PersistedConfig;
        
        // Validate structure
        if (config && typeof config === 'object' && typeof config.version === 'number') {
          resolve(config);
        } else {
          console.error('ConfigPersistence: Invalid configuration file structure');
          resolve(null);
        }
      } catch (error) {
        console.error('ConfigPersistence: Failed to parse configuration file:', error);
        resolve(null);
      }
    };
    reader.onerror = () => {
      console.error('ConfigPersistence: Failed to read configuration file');
      resolve(null);
    };
    reader.readAsText(file);
  });
};