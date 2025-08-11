import { useContext, useMemo } from 'react';
import { StableConfigContext, DynamicConfigContext, GraphControlContext } from '../contexts/GraphConfigProvider';
import type { GraphConfig } from '../contexts/configTypes';

export function useStableConfig() {
  const context = useContext(StableConfigContext);
  if (!context) {
    throw new Error('useStableConfig must be used within GraphConfigProvider');
  }
  return context;
}

export function useDynamicConfig() {
  const context = useContext(DynamicConfigContext);
  if (!context) {
    throw new Error('useDynamicConfig must be used within GraphConfigProvider');
  }
  return context;
}

export function useGraphControl() {
  const context = useContext(GraphControlContext);
  if (!context) {
    throw new Error('useGraphControl must be used within GraphConfigProvider');
  }
  return context;
}

// Combined hook for backward compatibility
export function useGraphConfig() {
  const { config: stableConfig, updateConfig: updateStable } = useStableConfig();
  const { config: dynamicConfig, updateConfig: updateDynamic } = useDynamicConfig();
  const control = useGraphControl();
  
  // CRITICAL: Memoize the combined config to prevent recreation on every render
  // This was causing massive re-renders of GraphCanvas and Cosmograph
  const combinedConfig = useMemo(
    () => ({ ...stableConfig, ...dynamicConfig } as GraphConfig),
    [stableConfig, dynamicConfig]
  );
  
  // Memoize the update function to keep it stable
  const updateConfig = useMemo(
    () => (updates: Partial<GraphConfig>) => {
        const stableUpdates: Partial<typeof stableConfig> = {};
        const dynamicUpdates: Partial<typeof dynamicConfig> = {};
        
        Object.entries(updates).forEach(([key, value]) => {
          if (key in stableConfig) {
            Object.assign(stableUpdates, { [key]: value });
          } else {
            Object.assign(dynamicUpdates, { [key]: value });
          }
        });
        
        if (Object.keys(stableUpdates).length > 0) {
          updateStable(stableUpdates);
        }
        if (Object.keys(dynamicUpdates).length > 0) {
          updateDynamic(dynamicUpdates);
        }
      },
    [stableConfig, dynamicConfig, updateStable, updateDynamic]
  );
  
  return {
    config: combinedConfig,
    updateConfig,
    ...control
  };
}