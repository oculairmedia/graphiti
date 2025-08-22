/**
 * UI Preferences Management
 * 
 * Centralized localStorage management for UI state preferences
 * that should persist across page reloads
 */

// Storage keys
export const UI_STORAGE_KEYS = {
  LEFT_PANEL_COLLAPSED: 'graphiti.ui.leftPanelCollapsed',
  SHOW_FILTER_PANEL: 'graphiti.ui.showFilterPanel',
  SHOW_STATS_PANEL: 'graphiti.ui.showStatsPanel',
  IS_SIMULATION_RUNNING: 'graphiti.ui.isSimulationRunning',
  TIMELINE_EXPANDED: 'graphiti.timeline.expanded',
  TIMELINE_ANIMATION_SPEED: 'graphiti.timeline.animationSpeed',
  TIMELINE_IS_LOOPING: 'graphiti.timeline.isLooping',
  CONTROL_PANEL_ACTIVE_TAB: 'graphiti.controlPanel.activeTab',
  TIMELINE_VISIBLE: 'graphiti.timeline.visible', // Already exists but included for completeness
} as const;

// UI Preferences interface
export interface UIPreferences {
  leftPanelCollapsed: boolean;
  showFilterPanel: boolean;
  showStatsPanel: boolean;
  isSimulationRunning: boolean;
  timelineExpanded: boolean;
  timelineAnimationSpeed: number;
  timelineIsLooping: boolean;
  controlPanelActiveTab: string;
  timelineVisible: boolean;
}

// Default UI preferences
export const DEFAULT_UI_PREFERENCES: UIPreferences = {
  leftPanelCollapsed: false,
  showFilterPanel: false,
  showStatsPanel: false,
  isSimulationRunning: true,
  timelineExpanded: true,
  timelineAnimationSpeed: 200,
  timelineIsLooping: false,
  controlPanelActiveTab: 'query',
  timelineVisible: true,
};

/**
 * Check if localStorage is available
 */
function isLocalStorageAvailable(): boolean {
  try {
    const test = '__storage_test__';
    localStorage.setItem(test, test);
    localStorage.removeItem(test);
    return true;
  } catch {
    return false;
  }
}

/**
 * Safely get a value from localStorage
 */
function getStorageValue<T>(key: string, defaultValue: T): T {
  if (!isLocalStorageAvailable()) {
    return defaultValue;
  }

  try {
    const item = localStorage.getItem(key);
    if (item === null) {
      return defaultValue;
    }

    // Handle boolean values
    if (typeof defaultValue === 'boolean') {
      return (item === 'true') as T;
    }

    // Handle number values
    if (typeof defaultValue === 'number') {
      const parsed = parseFloat(item);
      return (isNaN(parsed) ? defaultValue : parsed) as T;
    }

    // Handle string values
    if (typeof defaultValue === 'string') {
      return item as T;
    }

    // For other types, try JSON parsing
    return JSON.parse(item);
  } catch (error) {
    console.warn(`Failed to load UI preference for key ${key}:`, error);
    return defaultValue;
  }
}

/**
 * Safely set a value in localStorage
 */
function setStorageValue<T>(key: string, value: T): void {
  if (!isLocalStorageAvailable()) {
    return;
  }

  try {
    const stringValue = typeof value === 'string' ? value : String(value);
    localStorage.setItem(key, stringValue);
  } catch (error) {
    console.warn(`Failed to save UI preference for key ${key}:`, error);
  }
}

/**
 * Load all UI preferences from localStorage
 */
export function loadUIPreferences(): UIPreferences {
  return {
    leftPanelCollapsed: getStorageValue(UI_STORAGE_KEYS.LEFT_PANEL_COLLAPSED, DEFAULT_UI_PREFERENCES.leftPanelCollapsed),
    showFilterPanel: getStorageValue(UI_STORAGE_KEYS.SHOW_FILTER_PANEL, DEFAULT_UI_PREFERENCES.showFilterPanel),
    showStatsPanel: getStorageValue(UI_STORAGE_KEYS.SHOW_STATS_PANEL, DEFAULT_UI_PREFERENCES.showStatsPanel),
    isSimulationRunning: getStorageValue(UI_STORAGE_KEYS.IS_SIMULATION_RUNNING, DEFAULT_UI_PREFERENCES.isSimulationRunning),
    timelineExpanded: getStorageValue(UI_STORAGE_KEYS.TIMELINE_EXPANDED, DEFAULT_UI_PREFERENCES.timelineExpanded),
    timelineAnimationSpeed: getStorageValue(UI_STORAGE_KEYS.TIMELINE_ANIMATION_SPEED, DEFAULT_UI_PREFERENCES.timelineAnimationSpeed),
    timelineIsLooping: getStorageValue(UI_STORAGE_KEYS.TIMELINE_IS_LOOPING, DEFAULT_UI_PREFERENCES.timelineIsLooping),
    controlPanelActiveTab: getStorageValue(UI_STORAGE_KEYS.CONTROL_PANEL_ACTIVE_TAB, DEFAULT_UI_PREFERENCES.controlPanelActiveTab),
    timelineVisible: getStorageValue(UI_STORAGE_KEYS.TIMELINE_VISIBLE, DEFAULT_UI_PREFERENCES.timelineVisible),
  };
}

/**
 * Save a specific UI preference
 */
export function saveUIPreference<K extends keyof UIPreferences>(
  key: K,
  value: UIPreferences[K]
): void {
  const storageKey = getStorageKeyForPreference(key);
  if (storageKey) {
    setStorageValue(storageKey, value);
  }
}

/**
 * Save multiple UI preferences at once
 */
export function saveUIPreferences(preferences: Partial<UIPreferences>): void {
  Object.entries(preferences).forEach(([key, value]) => {
    saveUIPreference(key as keyof UIPreferences, value);
  });
}

/**
 * Get the localStorage key for a specific preference
 */
function getStorageKeyForPreference(key: keyof UIPreferences): string | null {
  const keyMap: Record<keyof UIPreferences, string> = {
    leftPanelCollapsed: UI_STORAGE_KEYS.LEFT_PANEL_COLLAPSED,
    showFilterPanel: UI_STORAGE_KEYS.SHOW_FILTER_PANEL,
    showStatsPanel: UI_STORAGE_KEYS.SHOW_STATS_PANEL,
    isSimulationRunning: UI_STORAGE_KEYS.IS_SIMULATION_RUNNING,
    timelineExpanded: UI_STORAGE_KEYS.TIMELINE_EXPANDED,
    timelineAnimationSpeed: UI_STORAGE_KEYS.TIMELINE_ANIMATION_SPEED,
    timelineIsLooping: UI_STORAGE_KEYS.TIMELINE_IS_LOOPING,
    controlPanelActiveTab: UI_STORAGE_KEYS.CONTROL_PANEL_ACTIVE_TAB,
    timelineVisible: UI_STORAGE_KEYS.TIMELINE_VISIBLE,
  };

  return keyMap[key] || null;
}

/**
 * Clear all UI preferences
 */
export function clearUIPreferences(): void {
  if (!isLocalStorageAvailable()) {
    return;
  }

  Object.values(UI_STORAGE_KEYS).forEach(key => {
    try {
      localStorage.removeItem(key);
    } catch (error) {
      console.warn(`Failed to clear UI preference for key ${key}:`, error);
    }
  });
}

/**
 * Hook for using UI preferences with automatic persistence
 */
export function useUIPreference<K extends keyof UIPreferences>(
  key: K
): [UIPreferences[K], (value: UIPreferences[K]) => void] {
  const currentValue = getStorageValue(
    getStorageKeyForPreference(key)!,
    DEFAULT_UI_PREFERENCES[key]
  );

  const setValue = (value: UIPreferences[K]) => {
    saveUIPreference(key, value);
  };

  return [currentValue, setValue];
}