/**
 * Comprehensive test suite for GraphCanvas component
 * Tests all major functionality before refactoring
 */

import { describe, it, expect, beforeEach, afterEach, vi, Mock } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React from 'react';
import { GraphNode } from '../../api/types';

// Define GraphLink interface here
interface GraphLink {
  source: string;
  target: string;
  name?: string;
  [key: string]: any;
}

// Mock Cosmograph
vi.mock('@cosmograph/react', () => ({
  Cosmograph: vi.fn(({ children, ...props }) => {
    // Store props for testing
    mockCosmographProps.current = props;
    return (
      <div data-testid="cosmograph-canvas" {...props}>
        {children}
      </div>
    );
  }),
  prepareCosmographData: vi.fn((nodes, links) => ({ nodes, links })),
  useCosmographInternal: vi.fn(() => ({
    cosmograph: mockCosmographInstance
  }))
}));

// Mock contexts
vi.mock('../../contexts/GraphConfigProvider', () => ({
  useGraphConfig: vi.fn(() => mockGraphConfig)
}));

vi.mock('../../contexts/WebSocketProvider', () => ({
  useWebSocketContext: vi.fn(() => mockWebSocketContext)
}));

vi.mock('../../contexts/RustWebSocketProvider', () => ({
  useRustWebSocket: vi.fn(() => mockRustWebSocket)
}));

vi.mock('../../contexts/DuckDBProvider', () => ({
  useDuckDB: vi.fn(() => mockDuckDBContext)
}));

vi.mock('../../contexts/LoadingCoordinator', () => ({
  useLoadingCoordinator: vi.fn(() => mockLoadingCoordinator)
}));

// Test data
const mockNodes: GraphNode[] = [
  { id: 'node1', name: 'Node 1', node_type: 'person', created_at: '2024-01-01' },
  { id: 'node2', name: 'Node 2', node_type: 'organization', created_at: '2024-01-01' },
  { id: 'node3', name: 'Node 3', node_type: 'location', created_at: '2024-01-01' },
];

const mockLinks: GraphLink[] = [
  { source: 'node1', target: 'node2', name: 'works_at' },
  { source: 'node2', target: 'node3', name: 'located_in' },
];

// Mock instances
const mockCosmographProps = { current: null as any };
const mockCosmographInstance = {
  setZoomLevel: vi.fn(),
  getZoomLevel: vi.fn(() => 1),
  fitView: vi.fn(),
  fitViewByPointIndices: vi.fn(),
  zoomToPoint: vi.fn(),
  selectNode: vi.fn(),
  selectNodes: vi.fn(),
  getSelectedNodes: vi.fn(() => []),
  unselectAll: vi.fn(),
  focusNode: vi.fn(),
  getNodePositions: vi.fn(() => ({})),
  restart: vi.fn(),
  start: vi.fn(),
  pause: vi.fn(),
  dataManager: {
    addPoints: vi.fn(),
    addLinks: vi.fn(),
    removePointsByIds: vi.fn(),
    removeLinksByPointIdPairs: vi.fn(),
  }
};

const mockGraphConfig = {
  config: {
    layout: 'force',
    labelSize: 12,
    nodeSize: 5,
    linkWidth: 1,
    showLabels: true,
    darkMode: false,
  },
  setCosmographRef: vi.fn(),
  updateConfig: vi.fn(),
};

const mockWebSocketContext = {
  subscribe: vi.fn(() => vi.fn()),
  subscribeToDeltaUpdate: vi.fn(() => vi.fn()),
  subscribeToGraphUpdate: vi.fn(() => vi.fn()),
  send: vi.fn(),
};

const mockRustWebSocket = {
  isConnected: true,
  subscribe: vi.fn(() => vi.fn()),
};

const mockDuckDBContext = {
  service: null,
  isInitialized: false,
  getDuckDBConnection: vi.fn(),
};

const mockLoadingCoordinator = {
  setLoadingState: vi.fn(),
  getLoadingState: vi.fn(() => ({ isLoading: false })),
  updateStage: vi.fn(),
  getStageStatus: vi.fn(() => 'complete'),
  reset: vi.fn(),
};

describe('GraphCanvas Component', () => {
  let user: ReturnType<typeof userEvent.setup>;

  beforeEach(() => {
    user = userEvent.setup();
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('Rendering', () => {
    it('should render the canvas container', () => {
      const { container } = render(
        <GraphCanvas
          nodes={mockNodes}
          links={mockLinks}
          onNodeClick={vi.fn()}
          onNodeSelect={vi.fn()}
          selectedNodes={[]}
          highlightedNodes={[]}
        />
      );

      expect(screen.getByTestId('cosmograph-canvas')).toBeInTheDocument();
      expect(container.querySelector('.graph-canvas-container')).toBeInTheDocument();
    });

    it('should apply custom className', () => {
      const { container } = render(
        <GraphCanvas
          nodes={mockNodes}
          links={mockLinks}
          onNodeClick={vi.fn()}
          onNodeSelect={vi.fn()}
          selectedNodes={[]}
          highlightedNodes={[]}
          className="custom-graph"
        />
      );

      expect(container.querySelector('.custom-graph')).toBeInTheDocument();
    });

    it('should display loading overlay during data preparation', async () => {
      render(
        <GraphCanvas
          nodes={mockNodes}
          links={mockLinks}
          onNodeClick={vi.fn()}
          onNodeSelect={vi.fn()}
          selectedNodes={[]}
          highlightedNodes={[]}
        />
      );

      // Loading overlay should appear briefly during initialization
      await waitFor(() => {
        expect(mockLoadingCoordinator.setLoadingState).toHaveBeenCalled();
      });
    });
  });

  describe('Data Management', () => {
    it('should prepare and pass data to Cosmograph', async () => {
      render(
        <GraphCanvas
          nodes={mockNodes}
          links={mockLinks}
          onNodeClick={vi.fn()}
          onNodeSelect={vi.fn()}
          selectedNodes={[]}
          highlightedNodes={[]}
        />
      );

      await waitFor(() => {
        expect(mockCosmographProps.current).toBeTruthy();
        expect(mockCosmographProps.current.nodes).toHaveLength(3);
        expect(mockCosmographProps.current.links).toHaveLength(2);
      });
    });

    it('should handle empty data gracefully', () => {
      render(
        <GraphCanvas
          nodes={[]}
          links={[]}
          onNodeClick={vi.fn()}
          onNodeSelect={vi.fn()}
          selectedNodes={[]}
          highlightedNodes={[]}
        />
      );

      expect(screen.getByTestId('cosmograph-canvas')).toBeInTheDocument();
    });

    it('should update when nodes prop changes', async () => {
      const { rerender } = render(
        <GraphCanvas
          nodes={mockNodes}
          links={mockLinks}
          onNodeClick={vi.fn()}
          onNodeSelect={vi.fn()}
          selectedNodes={[]}
          highlightedNodes={[]}
        />
      );

      const newNodes = [...mockNodes, { 
        id: 'node4', 
        name: 'Node 4', 
        node_type: 'event',
        created_at: '2024-01-01' 
      }];

      rerender(
        <GraphCanvas
          nodes={newNodes}
          links={mockLinks}
          onNodeClick={vi.fn()}
          onNodeSelect={vi.fn()}
          selectedNodes={[]}
          highlightedNodes={[]}
        />
      );

      await waitFor(() => {
        expect(mockCosmographProps.current.nodes).toHaveLength(4);
      });
    });
  });

  describe('Selection Functionality', () => {
    it('should handle node selection', async () => {
      const onNodeSelect = vi.fn();
      const onSelectNodes = vi.fn();

      render(
        <GraphCanvas
          nodes={mockNodes}
          links={mockLinks}
          onNodeClick={vi.fn()}
          onNodeSelect={onNodeSelect}
          onSelectNodes={onSelectNodes}
          selectedNodes={[]}
          highlightedNodes={[]}
        />
      );

      // Simulate node selection via Cosmograph
      const selectEvent = new CustomEvent('nodeSelect', {
        detail: { node: mockNodes[0] }
      });
      
      await waitFor(() => {
        expect(mockCosmographInstance.selectNode).toBeDefined();
      });

      // Call the selection handler
      mockCosmographInstance.selectNode(mockNodes[0]);
      expect(onNodeSelect).toHaveBeenCalledWith('node1');
    });

    it('should handle multiple node selection', () => {
      const onSelectNodes = vi.fn();

      render(
        <GraphCanvas
          nodes={mockNodes}
          links={mockLinks}
          onNodeClick={vi.fn()}
          onNodeSelect={vi.fn()}
          onSelectNodes={onSelectNodes}
          selectedNodes={[]}
          highlightedNodes={[]}
        />
      );

      mockCosmographInstance.selectNodes([mockNodes[0], mockNodes[1]]);
      expect(onSelectNodes).toHaveBeenCalledWith([mockNodes[0], mockNodes[1]]);
    });

    it('should clear selection', () => {
      const onClearSelection = vi.fn();

      const { rerender } = render(
        <GraphCanvas
          nodes={mockNodes}
          links={mockLinks}
          onNodeClick={vi.fn()}
          onNodeSelect={vi.fn()}
          onClearSelection={onClearSelection}
          selectedNodes={['node1']}
          highlightedNodes={[]}
        />
      );

      // Clear selection
      rerender(
        <GraphCanvas
          nodes={mockNodes}
          links={mockLinks}
          onNodeClick={vi.fn()}
          onNodeSelect={vi.fn()}
          onClearSelection={onClearSelection}
          selectedNodes={[]}
          highlightedNodes={[]}
        />
      );

      expect(mockCosmographInstance.unselectAll).toHaveBeenCalled();
    });

    it('should highlight selected nodes', () => {
      render(
        <GraphCanvas
          nodes={mockNodes}
          links={mockLinks}
          onNodeClick={vi.fn()}
          onNodeSelect={vi.fn()}
          selectedNodes={['node1', 'node2']}
          highlightedNodes={[]}
        />
      );

      // Check that selection is applied
      expect(mockCosmographProps.current.selectedPointIds).toEqual(['node1', 'node2']);
    });
  });

  describe('Event Handlers', () => {
    it('should handle node click', async () => {
      const onNodeClick = vi.fn();

      render(
        <GraphCanvas
          nodes={mockNodes}
          links={mockLinks}
          onNodeClick={onNodeClick}
          onNodeSelect={vi.fn()}
          selectedNodes={[]}
          highlightedNodes={[]}
        />
      );

      // Simulate click event from Cosmograph
      const clickHandler = mockCosmographProps.current?.onClick;
      if (clickHandler) {
        clickHandler({ node: mockNodes[0], index: 0 });
      }

      expect(onNodeClick).toHaveBeenCalledWith(mockNodes[0]);
    });

    it('should handle node hover', () => {
      const onNodeHover = vi.fn();

      render(
        <GraphCanvas
          nodes={mockNodes}
          links={mockLinks}
          onNodeClick={vi.fn()}
          onNodeSelect={vi.fn()}
          onNodeHover={onNodeHover}
          selectedNodes={[]}
          highlightedNodes={[]}
        />
      );

      const hoverHandler = mockCosmographProps.current?.onMouseOver;
      if (hoverHandler) {
        hoverHandler({ node: mockNodes[0], index: 0 });
      }

      expect(onNodeHover).toHaveBeenCalledWith(mockNodes[0]);

      // Test hover out
      const hoverOutHandler = mockCosmographProps.current?.onMouseOut;
      if (hoverOutHandler) {
        hoverOutHandler();
      }

      expect(onNodeHover).toHaveBeenCalledWith(null);
    });

    it('should distinguish double-click from single click', async () => {
      vi.useFakeTimers();
      const onNodeClick = vi.fn();
      const onNodeSelect = vi.fn();

      render(
        <GraphCanvas
          nodes={mockNodes}
          links={mockLinks}
          onNodeClick={onNodeClick}
          onNodeSelect={onNodeSelect}
          selectedNodes={[]}
          highlightedNodes={[]}
        />
      );

      const clickHandler = mockCosmographProps.current?.onClick;
      
      // First click
      clickHandler({ node: mockNodes[0], index: 0 });
      
      // Second click within double-click threshold
      clickHandler({ node: mockNodes[0], index: 0 });
      
      // Should trigger double-click behavior (zoom to node)
      expect(mockCosmographInstance.zoomToPoint).toHaveBeenCalled();
      
      vi.useRealTimers();
    });
  });

  describe('Camera Controls', () => {
    it('should expose zoom controls via ref', () => {
      const ref = { current: null as any };

      render(
        <GraphCanvas
          ref={ref}
          nodes={mockNodes}
          links={mockLinks}
          onNodeClick={vi.fn()}
          onNodeSelect={vi.fn()}
          selectedNodes={[]}
          highlightedNodes={[]}
        />
      );

      expect(ref.current).toBeDefined();
      expect(ref.current.zoomIn).toBeDefined();
      expect(ref.current.zoomOut).toBeDefined();
      expect(ref.current.fitView).toBeDefined();
    });

    it('should zoom in when zoomIn is called', () => {
      const ref = { current: null as any };

      render(
        <GraphCanvas
          ref={ref}
          nodes={mockNodes}
          links={mockLinks}
          onNodeClick={vi.fn()}
          onNodeSelect={vi.fn()}
          selectedNodes={[]}
          highlightedNodes={[]}
        />
      );

      mockCosmographInstance.getZoomLevel.mockReturnValue(1);
      ref.current.zoomIn();

      expect(mockCosmographInstance.setZoomLevel).toHaveBeenCalledWith(1.2, 250);
    });

    it('should fit view to all nodes', () => {
      const ref = { current: null as any };

      render(
        <GraphCanvas
          ref={ref}
          nodes={mockNodes}
          links={mockLinks}
          onNodeClick={vi.fn()}
          onNodeSelect={vi.fn()}
          selectedNodes={[]}
          highlightedNodes={[]}
        />
      );

      ref.current.fitView();
      expect(mockCosmographInstance.fitView).toHaveBeenCalled();
    });

    it('should focus on specific nodes', () => {
      const ref = { current: null as any };

      render(
        <GraphCanvas
          ref={ref}
          nodes={mockNodes}
          links={mockLinks}
          onNodeClick={vi.fn()}
          onNodeSelect={vi.fn()}
          selectedNodes={[]}
          highlightedNodes={[]}
        />
      );

      ref.current.focusOnNodes(['node1', 'node2']);
      expect(mockCosmographInstance.fitViewByPointIndices).toHaveBeenCalled();
    });
  });

  describe('WebSocket Integration', () => {
    it('should subscribe to WebSocket updates', () => {
      render(
        <GraphCanvas
          nodes={mockNodes}
          links={mockLinks}
          onNodeClick={vi.fn()}
          onNodeSelect={vi.fn()}
          selectedNodes={[]}
          highlightedNodes={[]}
        />
      );

      expect(mockWebSocketContext.subscribe).toHaveBeenCalled();
      expect(mockWebSocketContext.subscribeToDeltaUpdate).toHaveBeenCalled();
    });

    it('should handle incremental node updates', async () => {
      const ref = { current: null as any };

      render(
        <GraphCanvas
          ref={ref}
          nodes={mockNodes}
          links={mockLinks}
          onNodeClick={vi.fn()}
          onNodeSelect={vi.fn()}
          selectedNodes={[]}
          highlightedNodes={[]}
        />
      );

      const newNode = { 
        id: 'node4', 
        name: 'Node 4', 
        node_type: 'event',
        created_at: '2024-01-01'
      };

      ref.current.addIncrementalData([newNode], []);

      await waitFor(() => {
        expect(mockCosmographInstance.dataManager.addPoints).toHaveBeenCalled();
      });
    });

    it('should handle node removal', async () => {
      const ref = { current: null as any };

      render(
        <GraphCanvas
          ref={ref}
          nodes={mockNodes}
          links={mockLinks}
          onNodeClick={vi.fn()}
          onNodeSelect={vi.fn()}
          selectedNodes={[]}
          highlightedNodes={[]}
        />
      );

      ref.current.removeNodes(['node1']);

      await waitFor(() => {
        expect(mockCosmographInstance.dataManager.removePointsByIds)
          .toHaveBeenCalledWith(['node1']);
      });
    });

    it('should batch delta updates for performance', async () => {
      vi.useFakeTimers();
      const ref = { current: null as any };

      render(
        <GraphCanvas
          ref={ref}
          nodes={mockNodes}
          links={mockLinks}
          onNodeClick={vi.fn()}
          onNodeSelect={vi.fn()}
          selectedNodes={[]}
          highlightedNodes={[]}
        />
      );

      // Send multiple updates quickly
      for (let i = 0; i < 5; i++) {
        ref.current.addIncrementalData([{
          id: `new-node-${i}`,
          name: `New Node ${i}`,
          node_type: 'test',
          created_at: '2024-01-01'
        }], []);
      }

      // Advance timers to trigger batch processing
      vi.advanceTimersByTime(100);

      // Should batch into single update
      expect(mockCosmographInstance.dataManager.addPoints).toHaveBeenCalledTimes(1);

      vi.useRealTimers();
    });
  });

  describe('Statistics Tracking', () => {
    it('should track live statistics', () => {
      const onStatsUpdate = vi.fn();

      render(
        <GraphCanvas
          nodes={mockNodes}
          links={mockLinks}
          onNodeClick={vi.fn()}
          onNodeSelect={vi.fn()}
          onStatsUpdate={onStatsUpdate}
          selectedNodes={[]}
          highlightedNodes={[]}
        />
      );

      expect(onStatsUpdate).toHaveBeenCalledWith({
        nodeCount: 3,
        edgeCount: 2,
        lastUpdated: expect.any(Number)
      });
    });

    it('should update statistics after incremental changes', async () => {
      const onStatsUpdate = vi.fn();
      const ref = { current: null as any };

      render(
        <GraphCanvas
          ref={ref}
          nodes={mockNodes}
          links={mockLinks}
          onNodeClick={vi.fn()}
          onNodeSelect={vi.fn()}
          onStatsUpdate={onStatsUpdate}
          selectedNodes={[]}
          highlightedNodes={[]}
        />
      );

      onStatsUpdate.mockClear();

      ref.current.addIncrementalData([{
        id: 'node4',
        name: 'Node 4',
        node_type: 'test',
        created_at: '2024-01-01'
      }], []);

      await waitFor(() => {
        expect(onStatsUpdate).toHaveBeenCalledWith({
          nodeCount: 4,
          edgeCount: 2,
          lastUpdated: expect.any(Number)
        });
      });
    });
  });

  describe('Simulation Control', () => {
    it('should start simulation', () => {
      const ref = { current: null as any };

      render(
        <GraphCanvas
          ref={ref}
          nodes={mockNodes}
          links={mockLinks}
          onNodeClick={vi.fn()}
          onNodeSelect={vi.fn()}
          selectedNodes={[]}
          highlightedNodes={[]}
        />
      );

      ref.current.startSimulation();
      expect(mockCosmographInstance.restart).toHaveBeenCalled();
    });

    it('should pause simulation', () => {
      const ref = { current: null as any };

      render(
        <GraphCanvas
          ref={ref}
          nodes={mockNodes}
          links={mockLinks}
          onNodeClick={vi.fn()}
          onNodeSelect={vi.fn()}
          selectedNodes={[]}
          highlightedNodes={[]}
        />
      );

      ref.current.pauseSimulation();
      expect(mockCosmographInstance.pause).toHaveBeenCalled();
    });

    it('should keep simulation running when enabled', () => {
      vi.useFakeTimers();
      const ref = { current: null as any };

      render(
        <GraphCanvas
          ref={ref}
          nodes={mockNodes}
          links={mockLinks}
          onNodeClick={vi.fn()}
          onNodeSelect={vi.fn()}
          selectedNodes={[]}
          highlightedNodes={[]}
        />
      );

      ref.current.keepSimulationRunning(true);

      // Advance time to trigger keep-alive
      vi.advanceTimersByTime(1000);

      expect(mockCosmographInstance.restart).toHaveBeenCalled();

      vi.useRealTimers();
    });
  });

  describe('Error Handling', () => {
    it('should handle data loading errors gracefully', async () => {
      // Mock an error in data preparation
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

      render(
        <GraphCanvas
          nodes={null as any} // Invalid data
          links={mockLinks}
          onNodeClick={vi.fn()}
          onNodeSelect={vi.fn()}
          selectedNodes={[]}
          highlightedNodes={[]}
        />
      );

      await waitFor(() => {
        expect(consoleSpy).toHaveBeenCalled();
      });

      consoleSpy.mockRestore();
    });

    it('should handle WebSocket disconnection', () => {
      const localMockWebSocket = {
        ...mockWebSocketContext,
        subscribe: vi.fn((cb) => {
          // Simulate disconnection event
          cb({ type: 'disconnected' });
          return vi.fn();
        })
      };

      vi.mocked(useWebSocketContext).mockReturnValue(localMockWebSocket as any);

      render(
        <GraphCanvas
          nodes={mockNodes}
          links={mockLinks}
          onNodeClick={vi.fn()}
          onNodeSelect={vi.fn()}
          selectedNodes={[]}
          highlightedNodes={[]}
        />
      );

      // Component should handle disconnection gracefully
      expect(screen.getByTestId('cosmograph-canvas')).toBeInTheDocument();
    });
  });

  describe('Performance', () => {
    it('should not re-render unnecessarily', () => {
      const renderSpy = vi.fn();
      
      const TestWrapper = ({ children }: { children: React.ReactNode }) => {
        renderSpy();
        return <>{children}</>;
      };

      const { rerender } = render(
        <TestWrapper>
          <GraphCanvas
            nodes={mockNodes}
            links={mockLinks}
            onNodeClick={vi.fn()}
            onNodeSelect={vi.fn()}
            selectedNodes={[]}
            highlightedNodes={[]}
          />
        </TestWrapper>
      );

      renderSpy.mockClear();

      // Re-render with same props
      rerender(
        <TestWrapper>
          <GraphCanvas
            nodes={mockNodes}
            links={mockLinks}
            onNodeClick={vi.fn()}
            onNodeSelect={vi.fn()}
            selectedNodes={[]}
            highlightedNodes={[]}
          />
        </TestWrapper>
      );

      // Should minimize re-renders
      expect(renderSpy).toHaveBeenCalledTimes(1);
    });

    it('should handle large datasets efficiently', async () => {
      const largeNodes = Array.from({ length: 1000 }, (_, i) => ({
        id: `node${i}`,
        name: `Node ${i}`,
        node_type: 'test',
        created_at: '2024-01-01'
      }));

      const largeLinks = Array.from({ length: 2000 }, (_, i) => ({
        source: `node${i % 1000}`,
        target: `node${(i + 1) % 1000}`,
        name: 'link'
      }));

      const startTime = performance.now();

      render(
        <GraphCanvas
          nodes={largeNodes}
          links={largeLinks}
          onNodeClick={vi.fn()}
          onNodeSelect={vi.fn()}
          selectedNodes={[]}
          highlightedNodes={[]}
        />
      );

      const renderTime = performance.now() - startTime;

      // Should render large datasets quickly
      expect(renderTime).toBeLessThan(1000); // 1 second
    });
  });
});

describe('GraphCanvas Integration Tests', () => {
  it('should integrate with all contexts correctly', () => {
    render(
      <GraphCanvas
        nodes={mockNodes}
        links={mockLinks}
        onNodeClick={vi.fn()}
        onNodeSelect={vi.fn()}
        selectedNodes={[]}
        highlightedNodes={[]}
      />
    );

    // Verify all context hooks were called
    expect(vi.mocked(useGraphConfig)).toHaveBeenCalled();
    expect(vi.mocked(useWebSocketContext)).toHaveBeenCalled();
    expect(vi.mocked(useRustWebSocket)).toHaveBeenCalled();
    expect(vi.mocked(useDuckDB)).toHaveBeenCalled();
    expect(vi.mocked(useLoadingCoordinator)).toHaveBeenCalled();
  });

  it('should coordinate between multiple features', async () => {
    const ref = { current: null as any };
    const onNodeSelect = vi.fn();
    const onStatsUpdate = vi.fn();

    render(
      <GraphCanvas
        ref={ref}
        nodes={mockNodes}
        links={mockLinks}
        onNodeClick={vi.fn()}
        onNodeSelect={onNodeSelect}
        onStatsUpdate={onStatsUpdate}
        selectedNodes={[]}
        highlightedNodes={[]}
      />
    );

    // Select a node
    ref.current.selectNode(mockNodes[0]);
    expect(onNodeSelect).toHaveBeenCalledWith('node1');

    // Add new data
    ref.current.addIncrementalData([{
      id: 'node4',
      name: 'Node 4',
      node_type: 'test',
      created_at: '2024-01-01'
    }], [{
      source: 'node1',
      target: 'node4',
      name: 'connects'
    }]);

    // Stats should update
    await waitFor(() => {
      expect(onStatsUpdate).toHaveBeenCalledWith({
        nodeCount: 4,
        edgeCount: 3,
        lastUpdated: expect.any(Number)
      });
    });

    // Zoom to the new node
    ref.current.focusOnNodes(['node4']);
    expect(mockCosmographInstance.fitViewByPointIndices).toHaveBeenCalled();
  });
});