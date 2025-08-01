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
  renderLabels?: boolean;
  showLabels?: boolean;
  showHoveredNodeLabel?: boolean;
  labelColor?: string;
  hoveredLabelColor?: string;
  labelSize?: number;
  labelOpacity?: number;
  labelVisibilityThreshold?: number;
  labelFontWeight?: string;
  labelBackgroundColor?: string;
  hoveredLabelSize?: number;
  hoveredLabelFontWeight?: string;
  hoveredLabelBackgroundColor?: string;
  
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
  
  // Query
  queryType?: string;
  nodeLimit?: number;
  searchTerm?: string;
  
  // Filters
  filteredNodeTypes?: string[];
  minDegree?: number;
  maxDegree?: number;
  minPagerank?: number;
  maxPagerank?: number;
  minBetweenness?: number;
  maxBetweenness?: number;
  minEigenvector?: number;
  maxEigenvector?: number;
  minConnections?: number;
  maxConnections?: number;
  startDate?: string;
  endDate?: string;
  
  // Advanced rendering options
  edgeArrows?: boolean;
  edgeArrowScale?: number;
  pointsOnEdge?: boolean;
  advancedOptionsEnabled?: boolean;
  pixelationThreshold?: number;
  renderSelectedNodesOnTop?: boolean;
  
  // Display settings
  showFPS?: boolean;
  showNodeCount?: boolean;
  showDebugInfo?: boolean;
  
  // Interaction settings
  enableHoverEffects?: boolean;
  enablePanOnDrag?: boolean;
  enableZoomOnScroll?: boolean;
  enableClickSelection?: boolean;
  enableDoubleClickFocus?: boolean;
  enableKeyboardShortcuts?: boolean;
  
  // Performance
  performanceMode?: boolean;
  
  // Link configuration
  linkWidthBy?: string;
  linkColorScheme?: string;
  
  // Additional physics properties
  linkDistRandomVariationRange?: [number, number];
  simulationCluster?: number;
  simulationClusterStrength?: number;
  simulationImpulse?: number;
  useQuadtree?: boolean;
  useClassicQuadtree?: boolean;
  quadtreeLevels?: number;
  
  // Link visibility
  linkVisibilityDistance?: [number, number];
  linkVisibilityMinTransparency?: number;
  linkArrows?: boolean;
  linkArrowsSizeScale?: number;
  
  // Curved links
  curvedLinks?: boolean;
  curvedLinkSegments?: number;
  curvedLinkWeight?: number;
  curvedLinkControlPointDistance?: number;
  
  // Hover and focus
  hoveredPointCursor?: string;
  renderHoveredPointRing?: boolean;
  hoveredPointRingColor?: string;
  focusedPointRingColor?: string;
  focusedPointIndex?: number;
  renderLinks?: boolean;
  
  // Fit view
  fitViewDuration?: number;
  fitViewPadding?: number;
  
  // Border
  borderWidth?: number;
  
  // Link greyout
  linkGreyoutOpacity?: number;
  scaleLinksOnZoom?: boolean;
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
    if (Object.prototype.hasOwnProperty.call(localStorage, key)) {
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
    console.warn('configPersistence: localStorage not available for saving');
    return false;
  }

  try {
    // Validate config before saving
    if (!validatePersistedConfig(config)) {
      console.error('configPersistence: Attempted to save invalid config', config);
      return false;
    }
    
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
    
    console.log('configPersistence: Successfully saved config', {
      version: configWithTimestamp.version,
      hasNodeDetails: !!config.nodeDetailsSections,
      hasGraphConfig: !!config.graphConfig,
      size: serialized.length
    });
    
    return true;
  } catch (error) {
    console.error('configPersistence: Failed to save config', error);
    
    // Handle quota exceeded
    if (error instanceof Error && error.name === 'QuotaExceededError') {
      console.warn('configPersistence: localStorage quota exceeded, clearing backup');
      try {
        localStorage.removeItem(STORAGE_KEYS.BACKUP_CONFIG);
        const serialized = JSON.stringify(config);
        localStorage.setItem(STORAGE_KEYS.MAIN_CONFIG, serialized);
        console.log('configPersistence: Saved after clearing backup');
        return true;
      } catch (retryError) {
        console.error('configPersistence: Save failed even after clearing backup', retryError);
      }
    }
    
    return false;
  }
};

// Validate configuration structure
const validatePersistedConfig = (config: unknown): config is PersistedConfig => {
  if (!config || typeof config !== 'object') return false;
  const cfg = config as Record<string, unknown>;
  
  // Check required fields
  if (typeof cfg.version !== 'number' || typeof cfg.timestamp !== 'number') {
    return false;
  }
  
  // Validate optional sections if present
  if (cfg.nodeDetailsSections && typeof cfg.nodeDetailsSections !== 'object') {
    return false;
  }
  
  if (cfg.graphConfig && typeof cfg.graphConfig !== 'object') {
    return false;
  }
  
  return true;
};

export const loadConfigFromStorage = (): PersistedConfig | null => {
  if (!isStorageAvailable()) {
    console.warn('configPersistence: localStorage not available');
    return null;
  }

  try {
    const stored = localStorage.getItem(STORAGE_KEYS.MAIN_CONFIG);
    if (!stored) {
      console.log('configPersistence: No stored config found');
      return null;
    }

    const parsed = JSON.parse(stored);
    
    // Validate basic structure
    if (!validatePersistedConfig(parsed)) {
      console.error('configPersistence: Invalid config structure', parsed);
      return null;
    }

    // Handle version migrations if needed
    if (parsed.version < CURRENT_SCHEMA_VERSION) {
      console.log(`configPersistence: Migrating config from v${parsed.version} to v${CURRENT_SCHEMA_VERSION}`);
      const migrated = migrateConfig(parsed);
      if (migrated) {
        saveConfigToStorage(migrated); // Save migrated version
        return migrated;
      }
    }

    console.log('configPersistence: Successfully loaded config', {
      version: parsed.version,
      hasNodeDetails: !!parsed.nodeDetailsSections,
      hasGraphConfig: !!parsed.graphConfig
    });
    return parsed;
  } catch (error) {
    console.error('configPersistence: Failed to load main config', error);
    
    // Try backup
    try {
      const backup = localStorage.getItem(STORAGE_KEYS.BACKUP_CONFIG);
      if (backup) {
        const parsed = JSON.parse(backup);
        if (validatePersistedConfig(parsed)) {
          console.log('configPersistence: Restored from backup');
          // Restore backup to main
          localStorage.setItem(STORAGE_KEYS.MAIN_CONFIG, backup);
          return parsed;
        }
      }
    } catch (backupError) {
      console.error('configPersistence: Backup recovery failed', backupError);
    }
    
    return null;
  }
};

export const clearPersistedConfig = (): void => {
  if (!isStorageAvailable()) return;
  
  try {
    localStorage.removeItem(STORAGE_KEYS.MAIN_CONFIG);
    localStorage.removeItem(STORAGE_KEYS.BACKUP_CONFIG);
  } catch (error) {
    // Clear failed, ignore
  }
};

// Migration system for future schema changes
const migrateConfig = (config: PersistedConfig): PersistedConfig | null => {
  try {
    const migrated = { ...config };
    
    // Version 0 to 1 migration (if needed in future)
    if (config.version === 0) {
      // Add any migration logic here
      migrated.version = 1;
    }
    
    return migrated;
  } catch (error) {
    return null;
  }
};

// Utility to create differential config (only store changes from defaults)
export const createDifferentialConfig = <T extends Record<string, unknown>>(
  current: T,
  defaults: T
): Partial<T> => {
  const diff: Partial<T> = {};
  
  // Always include certain critical fields
  const alwaysIncludeFields = ['nodeTypeColors', 'nodeTypeVisibility', 'filteredNodeTypes'];
  
  for (const key in current) {
    // Special handling for fields that should always be included if they have content
    if (alwaysIncludeFields.includes(key)) {
      const value = current[key];
      if (value && typeof value === 'object') {
        // For objects, only include if non-empty
        if (Array.isArray(value) ? value.length > 0 : Object.keys(value).length > 0) {
          diff[key] = value;
        }
      } else if (value !== undefined && value !== null) {
        diff[key] = value;
      }
      continue;
    }
    
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
  
  // Ensure we're not returning a completely empty object
  if (Object.keys(diff).length === 0) {
    console.log('createDifferentialConfig: No differences found from defaults');
  }
  
  return diff;
};

// Utility to merge differential config back with defaults
export const mergeDifferentialConfig = <T extends Record<string, unknown>>(
  defaults: T,
  diff: Partial<T>
): T => {
  // If diff is empty or undefined, return defaults
  if (!diff || Object.keys(diff).length === 0) {
    console.log('mergeDifferentialConfig: No differences found, returning defaults');
    return defaults;
  }
  
  const merged = { ...defaults };
  
  for (const key in diff) {
    if (diff[key] !== undefined) {
      // Handle nested objects
      if (typeof diff[key] === 'object' && diff[key] !== null && !Array.isArray(diff[key]) &&
          typeof defaults[key] === 'object' && defaults[key] !== null && !Array.isArray(defaults[key])) {
        merged[key] = mergeDifferentialConfig(defaults[key] as Record<string, unknown>, diff[key] as Record<string, unknown>) as T[Extract<keyof T, string>];
      } else {
        merged[key] = diff[key] as T[typeof key];
      }
    }
  }
  
  console.log('mergeDifferentialConfig: Merged config', { 
    diffKeys: Object.keys(diff), 
    mergedKeys: Object.keys(merged).filter(k => merged[k] !== defaults[k]) 
  });
  
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
    // Export failed
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
          resolve(null);
        }
      } catch (error) {
        resolve(null);
      }
    };
    reader.onerror = () => {
      resolve(null);
    };
    reader.readAsText(file);
  });
};