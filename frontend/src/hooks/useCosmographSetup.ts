import { useMemo } from 'react';
import { useStableConfig, useDynamicConfig } from '../contexts/GraphConfigProvider';
import type { GraphNode } from '../types/graph';

export function useCosmographSetup() {
  const { config: stableConfig } = useStableConfig();
  const { config: dynamicConfig } = useDynamicConfig();
  
  // Combine configs for easier access
  const config = { ...stableConfig, ...dynamicConfig };
  
  // Point color strategy based on config
  const pointColorStrategy = useMemo(() => {
    switch (config.colorScheme) {
      case 'nodetype':
        return 'byColumn';
      case 'gradient':
        return 'byMetric';
      case 'uniform':
      default:
        return 'auto';
    }
  }, [config.colorScheme]);
  
  // Point color palette
  const pointColorPalette = useMemo(() => {
    if (config.colorScheme === 'gradient') {
      return [config.gradientLowColor, config.gradientHighColor];
    }
    // Default palette for node types
    return [
      '#3B82F6', '#EF4444', '#10B981', '#F59E0B', '#8B5CF6',
      '#EC4899', '#14B8A6', '#F97316', '#6366F1', '#84CC16'
    ];
  }, [config.colorScheme, config.gradientLowColor, config.gradientHighColor]);
  
  // Point color function
  const pointColorFn = useMemo(() => {
    if (config.colorScheme === 'nodetype') {
      return (node: GraphNode) => {
        const nodeType = node.node_type || 'Unknown';
        return config.nodeTypeColors[nodeType] || '#94A3B8';
      };
    }
    return undefined;
  }, [config.colorScheme, config.nodeTypeColors]);
  
  // Point size function (uniform sizing)
  const pointSizeFn = () => 1;
  
  // Simplified overrides - remove problematic physics and visibility settings
  const cosmographOverrides = {
    // Basic physics - adjusted to keep nodes closer
    simulationRepulsion: 0.1,  // Much weaker repulsion
    simulationGravity: 0.5,    // Stronger gravity to pull nodes together
    simulationCenter: 0.5,     // Stronger centering force
    simulationLinkDistance: 1.0,  // Shorter link distance
    
    // Basic appearance
    pointSize: 10,  // Larger points
    nodeOpacity: 1
  };
  
  return {
    config,
    stableConfig,
    dynamicConfig,
    pointColorStrategy,
    pointColorPalette,
    pointColorFn,
    pointSizeFn,
    cosmographOverrides
  };
}