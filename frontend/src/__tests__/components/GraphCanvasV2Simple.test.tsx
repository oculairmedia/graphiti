/**
 * Simple test for GraphCanvasV2 to isolate issues
 */

import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';
import React from 'react';
import GraphCanvasV2 from '../../components/GraphCanvasV2';

// Must export raw context objects for useGraphConfigHooks
vi.mock('../../contexts/GraphConfigProvider', async () => {
  const React = await import('react');

  const defaultConfig = {
    nodeSize: 5, linkWidth: 1, backgroundColor: '#ffffff', showLabels: true,
    labelSize: 12, simulationEnabled: true, simulationGravity: 0.1,
    simulationCenter: 0.1, simulationRepulsion: -300, simulationLinkDistance: 30,
    simulationLinkSpring: 1, simulationFriction: 0.9, simulationDecay: 0.4,
    gravity: 0.25, repulsion: 0.5, centerForce: 0.1, friction: 0.9,
    linkSpring: 0.1, linkDistance: 10, linkDistRandomVariationRange: [1, 1.1],
    mouseRepulsion: 0.2, simulationRepulsionTheta: 1.7, simulationCluster: 0.05,
    spaceSize: 8192, useQuadtree: true, useClassicQuadtree: false, quadtreeLevels: 12,
    disableSimulation: false, renderLinks: true, showHoveredNodeLabel: true,
    showDynamicLabels: false, showTopLabels: false, showTopLabelsLimit: 50,
    nodeTypeColors: {}, nodeTypeVisibility: {}, nodeAccessHighlightColor: '#FFD700',
    sizeMapping: 'uniform', clusteringEnabled: false, pointClusterBy: 'node_type',
    pointClusterStrengthBy: 'clusterStrength', clusteringMethod: 'none',
    centralityMetric: 'degree', clusterStrength: 0.3, queryType: 'entire_graph',
    nodeLimit: 100000, searchTerm: '', layout: 'force', hierarchyDirection: 'TB',
    radialCenter: 'most_connected', circularOrdering: 'degree', clusterBy: 'community',
    fitViewOnInit: true, fitViewDelay: 1500, fitViewPadding: 0.2, fitViewDuration: 1000,
    renderLabels: true, edgeArrows: false, edgeArrowScale: 1, pointsOnEdge: false,
    advancedOptionsEnabled: false, pixelationThreshold: 100000,
    renderSelectedNodesOnTop: true, performanceMode: false,
    showFPS: false, showNodeCount: true, showDebugInfo: false,
    enableHoverEffects: true, enablePanOnDrag: true, enableZoomOnScroll: true,
    enableClickSelection: true, enableDoubleClickFocus: true,
    enableKeyboardShortcuts: true, followSelectedNode: false,
    filteredNodeTypes: [], minDegree: 0, maxDegree: 100,
    minPagerank: 0, maxPagerank: 1, minBetweenness: 0, maxBetweenness: 1,
    minEigenvector: 0, maxEigenvector: 1, minConnections: 0, maxConnections: 1000,
    startDate: '', endDate: '', colorScheme: 'by-type',
    gradientHighColor: '#FF0000', gradientLowColor: '#0000FF',
    scalingMethod: 'winsorized', useQuantileScaling: true, useThresholdScaling: false,
    quantileBins: 7, minNodeSize: 4, maxNodeSize: 30, sizeMultiplier: 1,
    nodeOpacity: 0.9, borderWidth: 2, labelBy: 'label', labelColor: '#FFFFFF',
    hoveredLabelColor: '#FFFFFF', labelOpacity: 0.8, labelVisibilityThreshold: 0.5,
    labelFontWeight: 400, labelBackgroundColor: 'rgba(0,0,0,0.7)',
    hoveredLabelSize: 14, hoveredLabelFontWeight: 600,
    hoveredLabelBackgroundColor: 'rgba(0,0,0,0.9)',
    hoveredPointCursor: 'pointer', renderHoveredPointRing: false,
    hoveredPointRingColor: '#FFD700', focusedPointRingColor: '#FF6B6B',
    linkWidthBy: 'weight', linkWidthScheme: 'uniform', linkWidthScale: 0.5,
    linkWidthMin: 0.1, linkWidthMax: 5, linkOpacity: 0.85,
    linkOpacityScheme: 'uniform', linkOpacityMin: 0.1, linkOpacityMax: 1,
    linkGreyoutOpacity: 0.1, linkColor: '#9CA3AF', linkColorScheme: 'uniform',
    scaleLinksOnZoom: true, linkVisibilityDistance: [50, 200],
    linkVisibilityMinTransparency: 0.05, linkArrows: false, linkArrowsSizeScale: 1,
    curvedLinks: false, curvedLinkSegments: 10, curvedLinkWeight: 0.5,
    curvedLinkControlPointDistance: 0.5, linkStrengthEnabled: true,
    entityEntityStrength: 1.5, episodicStrength: 0.5, defaultLinkStrength: 1.0,
    linkAnimationEnabled: false, linkAnimationAmplitude: 0.15,
    linkAnimationFrequency: 0.5,
  };

  const StableConfigContext = React.createContext({
    config: defaultConfig,
    updateConfig: vi.fn(),
  });
  const DynamicConfigContext = React.createContext({
    config: defaultConfig,
    updateConfig: vi.fn(),
    batchUpdate: vi.fn(),
  });
  const GraphControlContext = React.createContext({
    cosmographRef: { current: null },
    setCosmographRef: vi.fn(),
    zoomIn: vi.fn(),
    zoomOut: vi.fn(),
    fitView: vi.fn(),
    applyLayout: vi.fn(),
    isApplyingLayout: false,
    updateNodeTypeConfigurations: vi.fn(),
  });

  return {
    StableConfigContext,
    DynamicConfigContext,
    GraphControlContext,
    useGraphConfig: vi.fn(() => ({
      config: defaultConfig,
      setCosmographRef: vi.fn(),
      updateConfig: vi.fn(),
      cosmographRef: { current: null },
      zoomIn: vi.fn(),
      zoomOut: vi.fn(),
      fitView: vi.fn(),
      applyLayout: vi.fn(),
      isApplyingLayout: false,
      updateNodeTypeConfigurations: vi.fn(),
    })),
    useStableConfig: vi.fn(() => ({
      config: defaultConfig,
      updateConfig: vi.fn(),
    })),
    useDynamicConfig: vi.fn(() => ({
      config: defaultConfig,
      updateConfig: vi.fn(),
      batchUpdate: vi.fn(),
    })),
    useGraphControl: vi.fn(() => ({
      cosmographRef: { current: null },
      setCosmographRef: vi.fn(),
      zoomIn: vi.fn(),
      zoomOut: vi.fn(),
      fitView: vi.fn(),
      applyLayout: vi.fn(),
      isApplyingLayout: false,
      updateNodeTypeConfigurations: vi.fn(),
    })),
    GraphConfigProvider: ({ children }: { children: React.ReactNode }) => children,
  };
});

vi.mock('../../contexts/LoadingCoordinator', () => ({
  LoadingCoordinatorProvider: ({ children }: { children: React.ReactNode }) => children,
  useLoadingCoordinator: vi.fn(() => ({
    setInitialized: vi.fn(),
    setError: vi.fn(),
    resetError: vi.fn(),
    isInitialized: true,
    error: null,
    updateStage: vi.fn(),
    updateStatus: vi.fn(),
    completeStage: vi.fn(),
    setStageComplete: vi.fn(),
    getStageStatus: vi.fn(() => 'complete'),
    isStageComplete: vi.fn().mockReturnValue(false),
    getStageProgress: vi.fn().mockReturnValue(0),
    stages: {},
    startLoading: vi.fn(),
    stopLoading: vi.fn(),
    isLoading: false,
  }))
}));

vi.mock('../../contexts/DuckDBProvider', () => ({
  useDuckDB: vi.fn(() => ({
    service: null,
    isInitialized: false,
    getDuckDBConnection: vi.fn()
  }))
}));

vi.mock('../../contexts/WebSocketProvider', () => ({
  useWebSocketContext: vi.fn(() => ({
    isConnected: true,
    connectionQuality: 'good' as const,
    latency: 50,
    subscribe: vi.fn(() => vi.fn()),
    subscribeToNodeAccess: vi.fn(() => vi.fn()),
    subscribeToGraphUpdate: vi.fn(() => vi.fn()),
    subscribeToDeltaUpdate: vi.fn(() => vi.fn()),
    subscribeToCacheInvalidate: vi.fn(() => vi.fn())
  }))
}));

vi.mock('../../contexts/RustWebSocketProvider', () => ({
  useRustWebSocket: vi.fn(() => ({
    isConnected: true,
    subscribe: vi.fn(() => vi.fn()),
    sendMessage: vi.fn()
  }))
}));

vi.mock('@cosmograph/react', () => ({
  Cosmograph: vi.fn(() => <div data-testid="cosmograph-mock" />),
  prepareCosmographData: vi.fn((data) => data)
}));

vi.mock('../../utils/nodeTypeColors', () => ({
  generateNodeTypeColor: vi.fn(() => '#000000')
}));

vi.mock('../../utils/logger', () => ({
  logger: {
    debug: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn()
  }
}));

vi.mock('../../utils/colorCache', () => ({
  hexToRgba: vi.fn((hex) => hex),
  generateHSLColor: vi.fn(() => 'hsl(0, 100%, 50%)')
}));

// Mock utility modules that might have issues
vi.mock('../../utils/graphNodeOperations', () => ({
  calculateNodeStats: vi.fn(() => ({
    byType: new Map(),
    avgCentrality: 0,
    maxCentrality: 0,
    minCentrality: 0
  })),
  calculateNodeDegrees: vi.fn(() => new Map())
}));

vi.mock('../../utils/graphLinkOperations', () => ({
  calculateLinkStats: vi.fn(() => ({
    byType: new Map(),
    avgWeight: 0,
    selfLoops: 0
  }))
}));

vi.mock('../../utils/graphMetrics', () => ({
  calculateGraphMetrics: vi.fn(() => ({
    density: 0,
    avgDegree: 0,
    maxDegree: 0,
    minDegree: 0
  }))
}));

describe('GraphCanvasV2 Simple Test', () => {
  it('should render without crashing', () => {
    const props = {
      nodes: [],
      links: [],
      onNodeClick: vi.fn(),
      onNodeSelect: vi.fn(),
      selectedNodes: [],
      highlightedNodes: []
    };
    
    const { container } = render(<GraphCanvasV2 {...props} />);
    expect(container).toBeTruthy();
  });
});