/**
 * Simple test for GraphCanvasV2 to isolate issues
 */

import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';
import React from 'react';
import GraphCanvasV2 from '../../components/GraphCanvasV2';

// Mock all contexts and dependencies first
vi.mock('../../contexts/GraphConfigProvider', () => ({
  useGraphConfig: vi.fn(() => ({
    config: {
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
      simulationDecay: 0.4
    },
    setCosmographRef: vi.fn(),
    updateConfig: vi.fn()
  }))
}));

vi.mock('../../contexts/LoadingCoordinator', () => ({
  useLoadingCoordinator: vi.fn(() => ({
    startLoading: vi.fn(),
    stopLoading: vi.fn(),
    isLoading: false
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