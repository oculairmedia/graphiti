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
    
    return true;
  } catch (error) {
    
    // Handle quota exceeded
    if (error instanceof Error && error.name === 'QuotaExceededError') {
      try {
        localStorage.removeItem(STORAGE_KEYS.BACKUP_CONFIG);
        localStorage.setItem(STORAGE_KEYS.MAIN_CONFIG, JSON.stringify(config));
        return true;
      } catch {
        // Save failed even after clearing backup
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
    
    // Try backup
    try {
      const backup = localStorage.getItem(STORAGE_KEYS.BACKUP_CONFIG);
      if (backup) {
        const parsed = JSON.parse(backup) as PersistedConfig;
        return parsed;
      }
    } catch (backupError) {
      // Backup recovery failed
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
  
  for (const key in current) {
    // Special handling for nodeTypeColors and nodeTypeVisibility
    // Always include them if they have any content, even if default is empty object
    if (key === 'nodeTypeColors' || key === 'nodeTypeVisibility') {
      if (current[key] && typeof current[key] === 'object' && Object.keys(current[key]).length > 0) {
        diff[key] = current[key];
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
  
  return diff;
};

// Utility to merge differential config back with defaults
export const mergeDifferentialConfig = <T extends Record<string, unknown>>(
  defaults: T,
  diff: Partial<T>
): T => {
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