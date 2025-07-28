// Configuration type definitions split into stable and dynamic parts

export interface StableConfig {
  // Physics settings (rarely changed)
  gravity: number;
  repulsion: number;
  centerForce: number;
  friction: number;
  linkSpring: number;
  linkDistance: number;
  linkDistRandomVariationRange: [number, number];
  mouseRepulsion: number;
  simulationDecay: number;
  simulationRepulsionTheta: number;
  simulationCluster: number;
  simulationClusterStrength?: number;
  simulationImpulse?: number;
  spaceSize: number;
  randomSeed?: number | string;
  
  // Quadtree optimization
  useQuadtree: boolean;
  useClassicQuadtree: boolean;
  quadtreeLevels: number;
  
  // Static appearance settings
  linkWidth: number;
  linkWidthBy: string;
  linkWidthScale: number;
  linkOpacity: number;
  linkGreyoutOpacity: number;
  linkColor: string;
  linkColorScheme: string;
  scaleLinksOnZoom: boolean;
  backgroundColor: string;
  
  // Link Visibility
  linkVisibilityDistance: [number, number];
  linkVisibilityMinTransparency: number;
  linkArrows: boolean;
  linkArrowsSizeScale: number;
  
  // Curved Links
  curvedLinks: boolean;
  curvedLinkSegments: number;
  curvedLinkWeight: number;
  curvedLinkControlPointDistance: number;
  
  // Node sizing defaults
  minNodeSize: number;
  maxNodeSize: number;
  sizeMultiplier: number;
  nodeOpacity: number;
  borderWidth: number;
  
  // Label defaults
  labelColor: string;
  hoveredLabelColor: string;
  labelSize: number;
  labelOpacity: number;
  
  // Visual defaults
  colorScheme: string;
  gradientHighColor: string;
  gradientLowColor: string;
  
  // Hover and focus styling
  hoveredPointCursor: string;
  renderHoveredPointRing: boolean;
  hoveredPointRingColor: string;
  focusedPointRingColor: string;
  
  // Fit view configuration
  fitViewDuration: number;
  fitViewPadding: number;
}

export interface DynamicConfig {
  // Frequently toggled settings
  disableSimulation: boolean | null;
  renderLinks: boolean;
  showLabels: boolean;
  showHoveredNodeLabel: boolean;
  
  // Dynamic node configuration
  nodeTypeColors: Record<string, string>;
  nodeTypeVisibility: Record<string, boolean>;
  sizeMapping: string;
  
  // Current focus
  focusedPointIndex?: number;
  
  // Query parameters
  queryType: string;
  nodeLimit: number;
  
  // Layout
  layout: string;
  hierarchyDirection: string;
  radialCenter: string;
  circularOrdering: string;
  clusterBy: string;
  
  // Filters
  filteredNodeTypes: string[];
  minDegree: number;
  maxDegree: number;
  minPagerank: number;
  maxPagerank: number;
  minBetweenness: number;
  maxBetweenness: number;
  minEigenvector: number;
  maxEigenvector: number;
  minConnections: number;
  maxConnections: number;
  startDate: string;
  endDate: string;
}

export type GraphConfig = StableConfig & DynamicConfig;

// Helper to check if a config key is stable
export const isStableConfigKey = (key: string): boolean => {
  const stableKeys = new Set<keyof StableConfig>([
    'gravity', 'repulsion', 'centerForce', 'friction', 'linkSpring',
    'linkDistance', 'linkDistRandomVariationRange', 'mouseRepulsion',
    'simulationDecay', 'simulationRepulsionTheta', 'simulationCluster',
    'simulationClusterStrength', 'simulationImpulse', 'spaceSize',
    'randomSeed', 'useQuadtree', 'useClassicQuadtree', 'quadtreeLevels',
    'linkWidth', 'linkWidthBy', 'linkWidthScale', 'linkOpacity',
    'linkGreyoutOpacity', 'linkColor', 'linkColorScheme', 'scaleLinksOnZoom',
    'backgroundColor', 'linkVisibilityDistance', 'linkVisibilityMinTransparency',
    'linkArrows', 'linkArrowsSizeScale', 'curvedLinks', 'curvedLinkSegments',
    'curvedLinkWeight', 'curvedLinkControlPointDistance', 'minNodeSize',
    'maxNodeSize', 'sizeMultiplier', 'nodeOpacity', 'borderWidth',
    'labelColor', 'hoveredLabelColor', 'labelSize', 'labelOpacity',
    'colorScheme', 'gradientHighColor', 'gradientLowColor', 'hoveredPointCursor',
    'renderHoveredPointRing', 'hoveredPointRingColor', 'focusedPointRingColor',
    'fitViewDuration', 'fitViewPadding'
  ]);
  
  return stableKeys.has(key as keyof StableConfig);
};

// Helper to split a config object
export const splitConfig = (config: GraphConfig): { stable: StableConfig; dynamic: DynamicConfig } => {
  const stable = {} as StableConfig;
  const dynamic = {} as DynamicConfig;
  
  Object.entries(config).forEach(([key, value]) => {
    if (isStableConfigKey(key)) {
      (stable as any)[key] = value;
    } else {
      (dynamic as any)[key] = value;
    }
  });
  
  return { stable, dynamic };
};