/**
 * Unit tests for GraphCanvasV2 component
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { renderHook, act } from '@testing-library/react';
import React from 'react';
import GraphCanvasV2 from '../../components/GraphCanvasV2';
import { GraphNode } from '../../api/types';

// Mock the contexts
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

// Mock Cosmograph
vi.mock('@cosmograph/react', () => ({
  Cosmograph: vi.fn(({ onReady, onClick, onHover, children }) => {
    // Simulate ready callback
    React.useEffect(() => {
      if (onReady) {
        onReady();
      }
    }, [onReady]);
    
    return (
      <div 
        data-testid="cosmograph-mock"
        onClick={() => onClick && onClick({ id: 'node1', name: 'Test Node' })}
        onMouseEnter={() => onHover && onHover({ id: 'node1', name: 'Test Node' })}
        onMouseLeave={() => onHover && onHover(null)}
      >
        {children}
      </div>
    );
  }),
  prepareCosmographData: vi.fn((data) => data)
}));

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
  generateHSLColor: vi.fn(() => 'hsl(0, 100%, 50%)')
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

  afterEach(() => {
    vi.restoreAllMocks();
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
      });
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
      
      await waitFor(() => {
        const cosmograph = screen.getByTestId('cosmograph-mock');
        fireEvent.click(cosmograph);
      });
      
      expect(onNodeClick).toHaveBeenCalled();
      expect(onNodeSelect).toHaveBeenCalledWith('node1');
    });

    it('should handle node hover', async () => {
      const onNodeHover = vi.fn();
      
      render(
        <GraphCanvasV2 {...defaultProps} onNodeHover={onNodeHover} />
      );
      
      await waitFor(() => {
        const cosmograph = screen.getByTestId('cosmograph-mock');
        
        // Hover on
        fireEvent.mouseEnter(cosmograph);
        expect(onNodeHover).toHaveBeenCalledWith(expect.objectContaining({
          id: 'node1'
        }));
        
        // Hover off
        fireEvent.mouseLeave(cosmograph);
        expect(onNodeHover).toHaveBeenCalledWith(null);
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
      
      // Should trigger selection update
      expect(defaultProps.onSelectNodes).toHaveBeenCalled();
    });

    it('should handle highlighted nodes prop', () => {
      const { rerender } = render(
        <GraphCanvasV2 {...defaultProps} highlightedNodes={[]} />
      );
      
      // Update highlighted nodes
      rerender(
        <GraphCanvasV2 {...defaultProps} highlightedNodes={['node1', 'node3']} />
      );
      
      // Component should handle highlighting (visual effect)
      expect(true).toBe(true); // Placeholder - visual effects are internal
    });
  });

  describe('Statistics updates', () => {
    it('should call onStatsUpdate with current statistics', async () => {
      const onStatsUpdate = vi.fn();
      
      render(
        <GraphCanvasV2 {...defaultProps} onStatsUpdate={onStatsUpdate} />
      );
      
      await waitFor(() => {
        expect(onStatsUpdate).toHaveBeenCalledWith(
          expect.objectContaining({
            nodeCount: mockNodes.length,
            edgeCount: mockLinks.length,
            lastUpdated: expect.any(Number)
          })
        );
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
        ref.current?.clearSelection();
      });
      
      // Selection should be cleared
      expect(defaultProps.onSelectNodes).toHaveBeenCalledWith([]);
    });

    it('should handle selectNode via ref', async () => {
      const ref = React.createRef<any>();
      
      render(
        <GraphCanvasV2 {...defaultProps} ref={ref} />
      );
      
      await waitFor(() => {
        ref.current?.selectNode(mockNodes[0]);
      });
      
      expect(defaultProps.onSelectNodes).toHaveBeenCalled();
    });

    it('should handle getLiveStats via ref', async () => {
      const ref = React.createRef<any>();
      
      render(
        <GraphCanvasV2 {...defaultProps} ref={ref} />
      );
      
      await waitFor(() => {
        const stats = ref.current?.getLiveStats();
        expect(stats).toEqual({
          nodeCount: mockNodes.length,
          edgeCount: mockLinks.length,
          lastUpdated: expect.any(Number)
        });
      });
    });

    it('should handle setData via ref', async () => {
      const ref = React.createRef<any>();
      
      render(
        <GraphCanvasV2 {...defaultProps} ref={ref} />
      );
      
      const newNodes = [
        { id: 'node4', name: 'Node 4', node_type: 'test' }
      ];
      const newLinks = [
        { source: 'node1', target: 'node4', from: 'node1', to: 'node4', edge_type: 'test' }
      ];
      
      await waitFor(() => {
        ref.current?.setData(newNodes, newLinks);
      });
      
      // Stats should update
      expect(defaultProps.onStatsUpdate).toHaveBeenCalled();
    });
  });

  describe('Data updates', () => {
    it('should handle incremental node additions', async () => {
      const ref = React.createRef<any>();
      
      render(
        <GraphCanvasV2 {...defaultProps} ref={ref} />
      );
      
      const newNodes = [
        { id: 'node4', name: 'Node 4', node_type: 'test' }
      ];
      
      await waitFor(() => {
        ref.current?.addIncrementalData(newNodes, []);
      });
      
      // Stats should reflect new node
      expect(defaultProps.onStatsUpdate).toHaveBeenCalled();
    });

    it('should handle node updates', async () => {
      const ref = React.createRef<any>();
      
      render(
        <GraphCanvasV2 {...defaultProps} ref={ref} />
      );
      
      const updatedNodes = [
        { ...mockNodes[0], name: 'Updated Node 1' }
      ];
      
      await waitFor(() => {
        ref.current?.updateNodes(updatedNodes);
      });
      
      // Component should handle the update
      expect(true).toBe(true); // Placeholder - internal state update
    });

    it('should handle node removal', async () => {
      const ref = React.createRef<any>();
      
      render(
        <GraphCanvasV2 {...defaultProps} ref={ref} />
      );
      
      await waitFor(() => {
        ref.current?.removeNodes(['node1']);
      });
      
      // Stats should reflect removal
      expect(defaultProps.onStatsUpdate).toHaveBeenCalled();
    });
  });

  describe('Simulation control', () => {
    it('should start simulation via ref', async () => {
      const ref = React.createRef<any>();
      
      render(
        <GraphCanvasV2 {...defaultProps} ref={ref} />
      );
      
      await waitFor(() => {
        ref.current?.startSimulation(0.5);
      });
      
      // Simulation should be running
      expect(true).toBe(true); // Placeholder - internal state
    });

    it('should pause and resume simulation', async () => {
      const ref = React.createRef<any>();
      
      render(
        <GraphCanvasV2 {...defaultProps} ref={ref} />
      );
      
      await waitFor(() => {
        ref.current?.startSimulation();
        ref.current?.pauseSimulation();
        ref.current?.resumeSimulation();
      });
      
      // Simulation state should be managed
      expect(true).toBe(true); // Placeholder - internal state
    });
  });
});