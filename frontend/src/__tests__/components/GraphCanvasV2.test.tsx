/**
 * Unit tests for GraphCanvasV2 component
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import React from 'react';
import GraphCanvasV2 from '../../components/GraphCanvasV2';
import { GraphNode } from '../../api/types';

// Mock the contexts - must export raw context objects for useGraphConfigHooks
vi.mock('../../contexts/GraphConfigProvider', async () => {
  const React = await import('react');

  const defaultConfig = {
    nodeSize: 5,
    linkWidth: 1,
    backgroundColor: '#ffffff',
    showLabels: true,
    labelSize: 12,
    simulationEnabled: true,
    simulationGravity: 0.1,
    simulationCenter: 0.1,
    simulationRepulsion: -300,
    simulationLinkDistance: 30,
    simulationLinkSpring: 1,
    simulationFriction: 0.9,
    simulationDecay: 0.4,
    gravity: 0.25,
    repulsion: 0.5,
    centerForce: 0.1,
    friction: 0.9,
    linkSpring: 0.1,
    linkDistance: 10,
    linkDistRandomVariationRange: [1, 1.1],
    mouseRepulsion: 0.2,
    simulationRepulsionTheta: 1.7,
    simulationCluster: 0.05,
    spaceSize: 8192,
    useQuadtree: true,
    useClassicQuadtree: false,
    quadtreeLevels: 12,
    disableSimulation: false,
    renderLinks: true,
    showHoveredNodeLabel: true,
    showDynamicLabels: false,
    showTopLabels: false,
    showTopLabelsLimit: 50,
    nodeTypeColors: {},
    nodeTypeVisibility: {},
    nodeAccessHighlightColor: '#FFD700',
    sizeMapping: 'uniform',
    clusteringEnabled: false,
    pointClusterBy: 'node_type',
    pointClusterStrengthBy: 'clusterStrength',
    clusteringMethod: 'none',
    centralityMetric: 'degree',
    clusterStrength: 0.3,
    queryType: 'entire_graph',
    nodeLimit: 100000,
    searchTerm: '',
    layout: 'force',
    hierarchyDirection: 'TB',
    radialCenter: 'most_connected',
    circularOrdering: 'degree',
    clusterBy: 'community',
    fitViewOnInit: true,
    fitViewDelay: 1500,
    fitViewPadding: 0.2,
    fitViewDuration: 1000,
    renderLabels: true,
    edgeArrows: false,
    edgeArrowScale: 1,
    pointsOnEdge: false,
    advancedOptionsEnabled: false,
    pixelationThreshold: 100000,
    renderSelectedNodesOnTop: true,
    performanceMode: false,
    showFPS: false,
    showNodeCount: true,
    showDebugInfo: false,
    enableHoverEffects: true,
    enablePanOnDrag: true,
    enableZoomOnScroll: true,
    enableClickSelection: true,
    enableDoubleClickFocus: true,
    enableKeyboardShortcuts: true,
    followSelectedNode: false,
    filteredNodeTypes: [],
    minDegree: 0,
    maxDegree: 100,
    minPagerank: 0,
    maxPagerank: 1,
    minBetweenness: 0,
    maxBetweenness: 1,
    minEigenvector: 0,
    maxEigenvector: 1,
    minConnections: 0,
    maxConnections: 1000,
    startDate: '',
    endDate: '',
    colorScheme: 'by-type',
    gradientHighColor: '#FF0000',
    gradientLowColor: '#0000FF',
    scalingMethod: 'winsorized',
    useQuantileScaling: true,
    useThresholdScaling: false,
    quantileBins: 7,
    minNodeSize: 4,
    maxNodeSize: 30,
    sizeMultiplier: 1,
    nodeOpacity: 0.9,
    borderWidth: 2,
    labelBy: 'label',
    labelColor: '#FFFFFF',
    hoveredLabelColor: '#FFFFFF',
    labelOpacity: 0.8,
    labelVisibilityThreshold: 0.5,
    labelFontWeight: 400,
    labelBackgroundColor: 'rgba(0,0,0,0.7)',
    hoveredLabelSize: 14,
    hoveredLabelFontWeight: 600,
    hoveredLabelBackgroundColor: 'rgba(0,0,0,0.9)',
    hoveredPointCursor: 'pointer',
    renderHoveredPointRing: false,
    hoveredPointRingColor: '#FFD700',
    focusedPointRingColor: '#FF6B6B',
    linkWidthBy: 'weight',
    linkWidthScheme: 'uniform',
    linkWidthScale: 0.5,
    linkWidthMin: 0.1,
    linkWidthMax: 5,
    linkOpacity: 0.85,
    linkOpacityScheme: 'uniform',
    linkOpacityMin: 0.1,
    linkOpacityMax: 1,
    linkGreyoutOpacity: 0.1,
    linkColor: '#9CA3AF',
    linkColorScheme: 'uniform',
    scaleLinksOnZoom: true,
    linkVisibilityDistance: [50, 200],
    linkVisibilityMinTransparency: 0.05,
    linkArrows: false,
    linkArrowsSizeScale: 1,
    curvedLinks: false,
    curvedLinkSegments: 10,
    curvedLinkWeight: 0.5,
    curvedLinkControlPointDistance: 0.5,
    linkStrengthEnabled: true,
    entityEntityStrength: 1.5,
    episodicStrength: 0.5,
    defaultLinkStrength: 1.0,
    linkAnimationEnabled: false,
    linkAnimationAmplitude: 0.15,
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

// Mock WebSocket contexts
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

vi.mock('../../hooks/useGraphWebSocket', () => ({
  useGraphWebSocket: vi.fn(() => ({
    connectionStatus: 'connected',
    isConnected: true,
    statistics: {},
    triggerNodeAccess: vi.fn(),
    triggerGraphUpdate: vi.fn(),
    triggerDeltaUpdate: vi.fn(),
    getRecentEvents: vi.fn(() => [])
  }))
}));

vi.mock('../../hooks/useGraphCamera', () => ({
  useGraphCamera: vi.fn(() => ({
    cameraState: {},
    controls: {},
    zoomIn: vi.fn(),
    zoomOut: vi.fn(),
    zoomTo: vi.fn(),
    pan: vi.fn(),
    panTo: vi.fn(),
    reset: vi.fn(),
    fitToView: vi.fn(),
    fitToNodes: vi.fn(),
    centerOnNode: vi.fn(),
    centerOnNodes: vi.fn(),
    isAnimating: false
  }))
}));

vi.mock('../../hooks/useGraphInteractions', () => ({
  useGraphInteractions: vi.fn(() => ({
    hoveredNode: null,
    handleNodeClick: vi.fn(),
    handleNodeHover: vi.fn(),
    isInteracting: false
  }))
}));

vi.mock('../../hooks/useGraphSimulation', () => ({
  useGraphSimulation: vi.fn(() => ({
    simulationState: {},
    isRunning: false,
    start: vi.fn(),
    stop: vi.fn(),
    restart: vi.fn(),
    reheat: vi.fn(),
    applyLayout: vi.fn()
  }))
}));

vi.mock('../../hooks/useGraphVisualEffects', () => ({
  useGraphVisualEffects: vi.fn(() => ({
    activeEffects: [],
    highlightNodes: vi.fn(),
    highlightLinks: vi.fn(),
    pulseNodes: vi.fn(),
    createRipple: vi.fn(),
    visualStyle: {},
    updateStyle: vi.fn(),
    isNodeHighlighted: vi.fn(() => false),
    isAnimating: false
  }))
}));

vi.mock('../../hooks/useCosmographIncrementalUpdates', () => ({
  useCosmographIncrementalUpdates: vi.fn(() => ({
    applyDelta: vi.fn(async () => false),
    replaceDataWithConfig: vi.fn(async () => false),
    metrics: {},
    isReady: false
  }))
}));

vi.mock('../../hooks/useCosmographVisualization', () => ({
  useCosmographVisualization: vi.fn(() => ({
    pointSizeRange: [4, 20],
    linkWidthRange: [1, 4],
    nodeColorConfig: {
      colorBy: 'node_type',
      strategy: 'direct',
      colorMap: {}
    },
    linkWidthByFn: vi.fn(() => 1),
    linkColorByFn: vi.fn(() => '#999')
  }))
}));

vi.mock('../../hooks/useGraphGlowEffects', () => ({
  useGraphGlowEffects: vi.fn(() => ({
    glowingNodes: new Map(),
    setGlowingNodes: vi.fn(),
    addGlowingNodes: vi.fn(),
    clearGlowingNodes: vi.fn(),
    glowTimeoutRef: { current: null }
  }))
}));

vi.mock('../../hooks/useGraphLiveCounts', () => ({
  useGraphLiveCounts: vi.fn(() => ({
    liveNodeCount: 0,
    liveEdgeCount: 0,
    resetCounts: vi.fn()
  }))
}));

vi.mock('../../hooks/useGraphNodeIndex', () => ({
  useGraphNodeIndex: vi.fn((nodes = []) => {
    const nodeIndexMap = new Map<string, number>();
    nodes.forEach((node: { id: string }, index: number) => nodeIndexMap.set(node.id, index));
    return {
      nodeIndexMap,
      getNodeIndex: (id: string) => nodeIndexMap.get(id),
      getNodeIndices: (ids: string[]) => ids.map(id => nodeIndexMap.get(id)).filter((v): v is number => typeof v === 'number')
    };
  })
}));

vi.mock('../../hooks/useGraphSelection', async () => {
  const React = await import('react');
  return { useGraphSelection: vi.fn(() => {
    const [selectedNodeIds, setSelectedNodeIds] = React.useState(new Set<string>());

    const selectNode = React.useCallback((id: string) => {
      setSelectedNodeIds((prev: Set<string>) => {
        const next = new Set(prev);
        next.add(id);
        return next;
      });
    }, []);

    const selectNodes = React.useCallback((ids: string[]) => {
      setSelectedNodeIds(new Set(ids));
    }, []);

    const deselectNode = React.useCallback((id: string) => {
      setSelectedNodeIds((prev: Set<string>) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
    }, []);

    const clearSelection = React.useCallback(() => {
      setSelectedNodeIds(new Set<string>());
    }, []);

    return {
      selectedNodeIds,
      selectedLinkIds: new Set<string>(),
      selectNode,
      selectNodes,
      deselectNode,
      clearSelection,
      toggleNodeSelection: vi.fn(),
      selectAll: vi.fn(),
      invertSelection: vi.fn(),
      selectConnectedNodes: vi.fn(),
      isNodeSelected: vi.fn(() => false),
      getSelectedNodes: vi.fn(() => [])
    };
  }) };
});

// Mock Cosmograph
vi.mock('@cosmograph/react', async () => {
  const React = await import('react');
  return { Cosmograph: React.forwardRef(({ onClick, onPointMouseOver, onPointMouseOut, onReady }: any, ref: any) => {

    React.useEffect(() => {
      if (onReady) {
        setTimeout(() => onReady(), 0);
      }
    }, []);

    React.useImperativeHandle(ref, () => ({
      selectPoint: vi.fn(),
      selectPoints: vi.fn(),
      unselectAllPoints: vi.fn(),
      fitView: vi.fn(),
      getZoomLevel: vi.fn(() => 1),
      setZoomLevel: vi.fn(),
      restart: vi.fn(),
      start: vi.fn(),
      pause: vi.fn(),
      setData: vi.fn(),
      fitViewByIndices: vi.fn(),
      zoomToPoint: vi.fn(),
      trackPointPositionsByIndices: vi.fn(),
      getTrackedPointPositionsMap: vi.fn(),
    }));

    return (
      <div
        data-testid="cosmograph-mock"
        onClick={() => onClick?.(0)}
        onMouseEnter={() => onPointMouseOver?.(0, [0, 0])}
        onMouseLeave={() => onPointMouseOut?.()}
      />
    );
  }),
  prepareCosmographData: vi.fn((data) => data)
  };
});

// Mock utility functions
vi.mock('../../utils/nodeTypeColors', () => ({
  generateNodeTypeColor: vi.fn((type) => '#' + Math.floor(Math.random()*16777215).toString(16))
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
  hexToRgba: vi.fn((hex, alpha) => hex),
  generateHSLColor: vi.fn(() => 'hsl(0, 100%, 50%)'),
  interpolateColor: vi.fn((color1, color2, ratio) => color1)
}));

describe('GraphCanvasV2', () => {
  const mockNodes: GraphNode[] = [
    { id: 'node1', name: 'Node 1', node_type: 'person' },
    { id: 'node2', name: 'Node 2', node_type: 'organization' },
    { id: 'node3', name: 'Node 3', node_type: 'location' }
  ];

  const mockLinks = [
    { source: 'node1', target: 'node2', from: 'node1', to: 'node2', edge_type: 'knows' },
    { source: 'node2', target: 'node3', from: 'node2', to: 'node3', edge_type: 'located_at' }
  ];

  const defaultProps = {
    nodes: mockNodes,
    links: mockLinks,
    onNodeClick: vi.fn(),
    onNodeSelect: vi.fn(),
    onSelectNodes: vi.fn(),
    onClearSelection: vi.fn(),
    onNodeHover: vi.fn(),
    onStatsUpdate: vi.fn(),
    onContextReady: vi.fn(),
    selectedNodes: [],
    highlightedNodes: [],
    className: 'test-canvas'
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Rendering', () => {
    it('should render the component', () => {
      const { container } = render(<GraphCanvasV2 {...defaultProps} />);
      expect(container.querySelector('.test-canvas')).toBeTruthy();
    });

    it('should render Cosmograph component', async () => {
      render(<GraphCanvasV2 {...defaultProps} />);
      
      await waitFor(() => {
        expect(screen.getByTestId('cosmograph-mock')).toBeTruthy();
      });
    });

    it('should show loading state when data is not ready', () => {
      const { container } = render(
        <GraphCanvasV2 {...defaultProps} nodes={[]} links={[]} />
      );
      
      // Component should handle empty data gracefully
      expect(container.querySelector('.test-canvas')).toBeTruthy();
    });

    it('should call onContextReady when component is ready', async () => {
      const onContextReady = vi.fn();
      render(
        <GraphCanvasV2 {...defaultProps} onContextReady={onContextReady} />
      );
      
      await waitFor(() => {
        expect(onContextReady).toHaveBeenCalledWith(true);
      }, { timeout: 2500 });
    });
  });

  describe('Node interactions', () => {
    it('should handle node click', async () => {
      const onNodeClick = vi.fn();
      const onNodeSelect = vi.fn();
      
      render(
        <GraphCanvasV2 
          {...defaultProps} 
          onNodeClick={onNodeClick}
          onNodeSelect={onNodeSelect}
        />
      );

      const cosmograph = await screen.findByTestId('cosmograph-mock');
      fireEvent.click(cosmograph);

      await waitFor(() => {
        expect(onNodeClick).toHaveBeenCalledWith(expect.objectContaining({ id: 'node1' }));
        expect(onNodeSelect).toHaveBeenCalledWith('node1');
      });
    });

    it('should handle node hover', async () => {
      const onNodeHover = vi.fn();
      
      render(
        <GraphCanvasV2 {...defaultProps} onNodeHover={onNodeHover} />
      );

      const cosmograph = await screen.findByTestId('cosmograph-mock');
      fireEvent.mouseEnter(cosmograph);
      fireEvent.mouseLeave(cosmograph);

      await waitFor(() => {
        expect(onNodeHover).not.toHaveBeenCalled();
      });
    });
  });

  describe('Selection management', () => {
    it('should handle selected nodes prop', () => {
      const { rerender } = render(
        <GraphCanvasV2 {...defaultProps} selectedNodes={['node1']} />
      );
      
      // Update selected nodes
      rerender(
        <GraphCanvasV2 {...defaultProps} selectedNodes={['node1', 'node2']} />
      );

      expect(screen.getByTestId('cosmograph-mock')).toBeTruthy();
    });

    it('should handle highlighted nodes prop', () => {
      const { rerender } = render(
        <GraphCanvasV2 {...defaultProps} highlightedNodes={[]} />
      );
      
      // Update highlighted nodes
      rerender(
        <GraphCanvasV2 {...defaultProps} highlightedNodes={['node1', 'node3']} />
      );

      expect(screen.getByTestId('cosmograph-mock')).toBeTruthy();
    });
  });

  describe('Statistics updates', () => {
    it('should call onStatsUpdate with current statistics', async () => {
      const onStatsUpdate = vi.fn();
      
      render(
        <GraphCanvasV2 {...defaultProps} onStatsUpdate={onStatsUpdate} />
      );
      
      await waitFor(() => {
        expect(
          onStatsUpdate.mock.calls.some(([stats]) =>
            stats?.nodeCount === mockNodes.length &&
            stats?.edgeCount === mockLinks.length &&
            typeof stats?.lastUpdated === 'number'
          )
        ).toBe(true);
      });
    });
  });

  describe('Imperative handle methods', () => {
    it('should expose imperative methods via ref', async () => {
      const ref = React.createRef<any>();
      
      render(
        <GraphCanvasV2 {...defaultProps} ref={ref} />
      );
      
      await waitFor(() => {
        expect(ref.current).toBeDefined();
        expect(ref.current.clearSelection).toBeDefined();
        expect(ref.current.selectNode).toBeDefined();
        expect(ref.current.selectNodes).toBeDefined();
        expect(ref.current.zoomIn).toBeDefined();
        expect(ref.current.zoomOut).toBeDefined();
        expect(ref.current.fitView).toBeDefined();
        expect(ref.current.setData).toBeDefined();
        expect(ref.current.restart).toBeDefined();
        expect(ref.current.getLiveStats).toBeDefined();
        expect(ref.current.startSimulation).toBeDefined();
        expect(ref.current.pauseSimulation).toBeDefined();
      });
    });

    it('should handle clearSelection via ref', async () => {
      const ref = React.createRef<any>();
      const onClearSelection = vi.fn();
      
      render(
        <GraphCanvasV2 
          {...defaultProps} 
          ref={ref}
          onClearSelection={onClearSelection}
        />
      );
      
      await waitFor(() => {
        expect(ref.current).toBeDefined();
      });

      act(() => {
        expect(() => ref.current.clearSelection()).not.toThrow();
      });
    });

    it('should handle selectNode via ref', async () => {
      const ref = React.createRef<any>();
      
      render(
        <GraphCanvasV2 {...defaultProps} ref={ref} />
      );
      
      await waitFor(() => {
        expect(ref.current).toBeDefined();
      });

      act(() => {
        expect(() => ref.current.selectNode(mockNodes[0])).not.toThrow();
      });
    });

    it('should handle getLiveStats via ref', async () => {
      const ref = React.createRef<any>();
      
      render(
        <GraphCanvasV2 {...defaultProps} ref={ref} />
      );
      
      await waitFor(() => {
        const stats = ref.current?.getLiveStats();
        expect(stats?.nodeCount).toBe(mockNodes.length);
        expect(stats?.edgeCount).toBe(mockLinks.length);
        expect(typeof stats?.lastUpdated).toBe('number');
      });
    });

    it('should handle setData via ref', async () => {
      const ref = React.createRef<any>();
      const onStatsUpdate = vi.fn();
      
      render(
        <GraphCanvasV2 {...defaultProps} ref={ref} onStatsUpdate={onStatsUpdate} />
      );
      
      const newNodes = [
        { id: 'node4', name: 'Node 4', node_type: 'test' }
      ];
      const newLinks = [
        { source: 'node1', target: 'node4', from: 'node1', to: 'node4', edge_type: 'test' }
      ];
      
      await waitFor(() => {
        expect(ref.current).toBeDefined();
      });

      act(() => {
        ref.current.setData(newNodes, newLinks);
      });

      await waitFor(() => {
        expect(
          onStatsUpdate.mock.calls.some(([stats]) => stats?.nodeCount === 1 && stats?.edgeCount === 0)
        ).toBe(true);
      });
    });
  });

  describe('Data updates', () => {
    it('should handle incremental node additions', async () => {
      const ref = React.createRef<any>();
      const onStatsUpdate = vi.fn();
      
      render(
        <GraphCanvasV2 {...defaultProps} ref={ref} onStatsUpdate={onStatsUpdate} />
      );
      
      const newNodes = [
        { id: 'node4', name: 'Node 4', node_type: 'test' }
      ];
      
      await waitFor(() => {
        expect(ref.current).toBeDefined();
      });

      act(() => {
        ref.current.addIncrementalData(newNodes, []);
      });

      await waitFor(() => {
        expect(
          onStatsUpdate.mock.calls.some(([stats]) => stats?.nodeCount === 4 && stats?.edgeCount === 2)
        ).toBe(true);
      });
    });

    it('should handle node updates', async () => {
      const ref = React.createRef<any>();
      
      render(
        <GraphCanvasV2 {...defaultProps} ref={ref} onNodeClick={defaultProps.onNodeClick} />
      );
      
      const updatedNodes = [
        { ...mockNodes[0], name: 'Updated Node 1' }
      ];
      
      await waitFor(() => {
        expect(ref.current).toBeDefined();
      });

      act(() => {
        ref.current.updateNodes(updatedNodes);
      });

      fireEvent.click(screen.getByTestId('cosmograph-mock'));

      await waitFor(() => {
        expect(defaultProps.onNodeClick).toHaveBeenCalledWith(
          expect.objectContaining({ id: 'node1', name: 'Updated Node 1' })
        );
      });
    });

    it('should handle node removal', async () => {
      const ref = React.createRef<any>();
      const onStatsUpdate = vi.fn();
      
      render(
        <GraphCanvasV2 {...defaultProps} ref={ref} onStatsUpdate={onStatsUpdate} />
      );

      await waitFor(() => {
        expect(ref.current).toBeDefined();
      });

      act(() => {
        ref.current.removeNodes(['node1']);
      });

      await waitFor(() => {
        expect(
          onStatsUpdate.mock.calls.some(([stats]) => stats?.nodeCount === 2 && stats?.edgeCount === 1)
        ).toBe(true);
      });
    });
  });

  describe('Simulation control', () => {
    it('should start simulation via ref', async () => {
      const ref = React.createRef<any>();
      
      render(
        <GraphCanvasV2 {...defaultProps} ref={ref} />
      );

      await waitFor(() => {
        expect(ref.current).toBeDefined();
      });

      const cgRef = ref.current.getCosmographRef();
      act(() => {
        ref.current.startSimulation(0.5);
      });

      expect(cgRef.current.start).toHaveBeenCalledWith(0.5);
    });

    it('should pause and resume simulation', async () => {
      const ref = React.createRef<any>();
      
      render(
        <GraphCanvasV2 {...defaultProps} ref={ref} />
      );

      await waitFor(() => {
        expect(ref.current).toBeDefined();
      });

      const cgRef = ref.current.getCosmographRef();
      act(() => {
        ref.current.startSimulation();
        ref.current.pauseSimulation();
        ref.current.resumeSimulation();
      });

      expect(cgRef.current.start).toHaveBeenCalled();
      expect(cgRef.current.pause).toHaveBeenCalled();
    });
  });
});
