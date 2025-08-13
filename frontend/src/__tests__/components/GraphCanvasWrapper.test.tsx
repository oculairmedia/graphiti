/**
 * Test suite for GraphCanvas interface using test wrapper
 * This tests the API contract that the refactored components must maintain
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React, { createRef } from 'react';
import { GraphCanvasTestWrapper } from './GraphCanvasTestWrapper';
import { GraphNode } from '../../api/types';

interface GraphLink {
  source: string;
  target: string;
  name?: string;
}

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

describe('GraphCanvas Interface Contract', () => {
  let user: ReturnType<typeof userEvent.setup>;

  beforeEach(() => {
    user = userEvent.setup();
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('Component Rendering', () => {
    it('should render with required props', () => {
      render(
        <GraphCanvasTestWrapper
          nodes={mockNodes}
          links={mockLinks}
          onNodeClick={vi.fn()}
          onNodeSelect={vi.fn()}
          selectedNodes={[]}
          highlightedNodes={[]}
        />
      );

      expect(screen.getByTestId('graph-canvas')).toBeInTheDocument();
      expect(screen.getByText('Nodes: 3, Links: 2')).toBeInTheDocument();
    });

    it('should apply custom className', () => {
      render(
        <GraphCanvasTestWrapper
          nodes={mockNodes}
          links={mockLinks}
          onNodeClick={vi.fn()}
          onNodeSelect={vi.fn()}
          selectedNodes={[]}
          highlightedNodes={[]}
          className="custom-class"
        />
      );

      expect(screen.getByTestId('graph-canvas')).toHaveClass('custom-class');
    });

    it('should display all nodes', () => {
      render(
        <GraphCanvasTestWrapper
          nodes={mockNodes}
          links={mockLinks}
          onNodeClick={vi.fn()}
          onNodeSelect={vi.fn()}
          selectedNodes={[]}
          highlightedNodes={[]}
        />
      );

      mockNodes.forEach(node => {
        expect(screen.getByTestId(`node-${node.id}`)).toBeInTheDocument();
        expect(screen.getByText(node.name)).toBeInTheDocument();
      });
    });
  });

  describe('Selection Management', () => {
    it('should handle single node selection', async () => {
      const onNodeSelect = vi.fn();
      const onNodeClick = vi.fn();

      render(
        <GraphCanvasTestWrapper
          nodes={mockNodes}
          links={mockLinks}
          onNodeClick={onNodeClick}
          onNodeSelect={onNodeSelect}
          selectedNodes={[]}
          highlightedNodes={[]}
        />
      );

      const node1 = screen.getByTestId('node-node1');
      await user.click(node1);

      expect(onNodeClick).toHaveBeenCalledWith(mockNodes[0]);
      expect(onNodeSelect).toHaveBeenCalledWith('node1');
    });

    it('should visually indicate selected nodes', () => {
      render(
        <GraphCanvasTestWrapper
          nodes={mockNodes}
          links={mockLinks}
          onNodeClick={vi.fn()}
          onNodeSelect={vi.fn()}
          selectedNodes={['node1', 'node2']}
          highlightedNodes={[]}
        />
      );

      expect(screen.getByTestId('node-node1')).toHaveClass('selected');
      expect(screen.getByTestId('node-node2')).toHaveClass('selected');
      expect(screen.getByTestId('node-node3')).not.toHaveClass('selected');
    });

    it('should visually indicate highlighted nodes', () => {
      render(
        <GraphCanvasTestWrapper
          nodes={mockNodes}
          links={mockLinks}
          onNodeClick={vi.fn()}
          onNodeSelect={vi.fn()}
          selectedNodes={[]}
          highlightedNodes={['node2', 'node3']}
        />
      );

      expect(screen.getByTestId('node-node2')).toHaveClass('highlighted');
      expect(screen.getByTestId('node-node3')).toHaveClass('highlighted');
      expect(screen.getByTestId('node-node1')).not.toHaveClass('highlighted');
    });

    it('should clear selection via ref', () => {
      const ref = createRef<any>();
      const onClearSelection = vi.fn();

      render(
        <GraphCanvasTestWrapper
          ref={ref}
          nodes={mockNodes}
          links={mockLinks}
          onNodeClick={vi.fn()}
          onNodeSelect={vi.fn()}
          onClearSelection={onClearSelection}
          selectedNodes={['node1']}
          highlightedNodes={[]}
        />
      );

      ref.current?.clearSelection();
      expect(onClearSelection).toHaveBeenCalled();
    });
  });

  describe('Event Handlers', () => {
    it('should handle node hover', async () => {
      const onNodeHover = vi.fn();

      render(
        <GraphCanvasTestWrapper
          nodes={mockNodes}
          links={mockLinks}
          onNodeClick={vi.fn()}
          onNodeSelect={vi.fn()}
          onNodeHover={onNodeHover}
          selectedNodes={[]}
          highlightedNodes={[]}
        />
      );

      const node1 = screen.getByTestId('node-node1');
      
      // Hover over node
      await user.hover(node1);
      expect(onNodeHover).toHaveBeenCalledWith(mockNodes[0]);

      // Hover out
      await user.unhover(node1);
      expect(onNodeHover).toHaveBeenCalledWith(null);
    });

    it('should notify when context is ready', async () => {
      const onContextReady = vi.fn();

      render(
        <GraphCanvasTestWrapper
          nodes={mockNodes}
          links={mockLinks}
          onNodeClick={vi.fn()}
          onNodeSelect={vi.fn()}
          onContextReady={onContextReady}
          selectedNodes={[]}
          highlightedNodes={[]}
        />
      );

      await waitFor(() => {
        expect(onContextReady).toHaveBeenCalledWith(true);
      });
    });
  });

  describe('Imperative API via Ref', () => {
    it('should expose zoom controls', () => {
      const ref = createRef<any>();

      render(
        <GraphCanvasTestWrapper
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

    it('should handle zoom operations', () => {
      const ref = createRef<any>();

      render(
        <GraphCanvasTestWrapper
          ref={ref}
          nodes={mockNodes}
          links={mockLinks}
          onNodeClick={vi.fn()}
          onNodeSelect={vi.fn()}
          selectedNodes={[]}
          highlightedNodes={[]}
        />
      );

      const canvas = screen.getByTestId('graph-canvas');
      
      // Initial zoom
      expect(canvas.getAttribute('data-zoom')).toBe('1');

      // Zoom in
      ref.current?.zoomIn();
      expect(canvas.getAttribute('data-zoom')).toBe('1.2');

      // Zoom out
      ref.current?.zoomOut();
      expect(canvas.getAttribute('data-zoom')).toBe('1');

      // Fit view resets zoom
      ref.current?.zoomIn();
      ref.current?.zoomIn();
      ref.current?.fitView();
      expect(canvas.getAttribute('data-zoom')).toBe('1');
    });

    it('should expose data management methods', () => {
      const ref = createRef<any>();

      render(
        <GraphCanvasTestWrapper
          ref={ref}
          nodes={mockNodes}
          links={mockLinks}
          onNodeClick={vi.fn()}
          onNodeSelect={vi.fn()}
          selectedNodes={[]}
          highlightedNodes={[]}
        />
      );

      expect(ref.current.setData).toBeDefined();
      expect(ref.current.addIncrementalData).toBeDefined();
      expect(ref.current.updateNodes).toBeDefined();
      expect(ref.current.removeNodes).toBeDefined();
    });

    it('should expose simulation controls', () => {
      const ref = createRef<any>();

      render(
        <GraphCanvasTestWrapper
          ref={ref}
          nodes={mockNodes}
          links={mockLinks}
          onNodeClick={vi.fn()}
          onNodeSelect={vi.fn()}
          selectedNodes={[]}
          highlightedNodes={[]}
        />
      );

      expect(ref.current.startSimulation).toBeDefined();
      expect(ref.current.pauseSimulation).toBeDefined();
      expect(ref.current.resumeSimulation).toBeDefined();
      expect(ref.current.keepSimulationRunning).toBeDefined();
    });
  });

  describe('Data Management', () => {
    it('should handle incremental data addition', () => {
      const ref = createRef<any>();
      const onStatsUpdate = vi.fn();

      render(
        <GraphCanvasTestWrapper
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

      const newNode: GraphNode = {
        id: 'node4',
        name: 'Node 4',
        node_type: 'event',
        created_at: '2024-01-01'
      };

      const newLink: GraphLink = {
        source: 'node3',
        target: 'node4',
        name: 'triggers'
      };

      onStatsUpdate.mockClear();
      ref.current?.addIncrementalData([newNode], [newLink]);

      expect(onStatsUpdate).toHaveBeenCalledWith({
        nodeCount: 4,
        edgeCount: 3,
        lastUpdated: expect.any(Number)
      });
    });

    it('should handle node updates', () => {
      const ref = createRef<any>();
      const onStatsUpdate = vi.fn();

      render(
        <GraphCanvasTestWrapper
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

      const updatedNode: GraphNode = {
        ...mockNodes[0],
        name: 'Updated Node 1'
      };

      ref.current?.updateNodes([updatedNode]);

      // Stats should reflect the same count (no new nodes)
      expect(onStatsUpdate).toHaveBeenLastCalledWith({
        nodeCount: 3,
        edgeCount: 2,
        lastUpdated: expect.any(Number)
      });
    });

    it('should handle node removal', () => {
      const ref = createRef<any>();
      const onStatsUpdate = vi.fn();

      render(
        <GraphCanvasTestWrapper
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
      ref.current?.removeNodes(['node1']);

      // Should remove node and its connected links
      expect(onStatsUpdate).toHaveBeenCalledWith({
        nodeCount: 2,
        edgeCount: 1, // One link should be removed
        lastUpdated: expect.any(Number)
      });
    });

    it('should replace all data', () => {
      const ref = createRef<any>();
      const onStatsUpdate = vi.fn();

      render(
        <GraphCanvasTestWrapper
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

      const newNodes: GraphNode[] = [
        { id: 'new1', name: 'New 1', node_type: 'test', created_at: '2024-01-01' },
        { id: 'new2', name: 'New 2', node_type: 'test', created_at: '2024-01-01' },
      ];

      const newLinks: GraphLink[] = [
        { source: 'new1', target: 'new2', name: 'connects' }
      ];

      onStatsUpdate.mockClear();
      ref.current?.setData(newNodes, newLinks);

      expect(onStatsUpdate).toHaveBeenCalledWith({
        nodeCount: 2,
        edgeCount: 1,
        lastUpdated: expect.any(Number)
      });
    });
  });

  describe('Statistics Tracking', () => {
    it('should report initial statistics', () => {
      const onStatsUpdate = vi.fn();

      render(
        <GraphCanvasTestWrapper
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

    it('should provide live stats via ref', () => {
      const ref = createRef<any>();

      render(
        <GraphCanvasTestWrapper
          ref={ref}
          nodes={mockNodes}
          links={mockLinks}
          onNodeClick={vi.fn()}
          onNodeSelect={vi.fn()}
          selectedNodes={[]}
          highlightedNodes={[]}
        />
      );

      const stats = ref.current?.getLiveStats();
      expect(stats).toEqual({
        nodeCount: 3,
        edgeCount: 2,
        lastUpdated: expect.any(Number)
      });
    });
  });

  describe('Simulation Control', () => {
    it('should start simulation', () => {
      const ref = createRef<any>();

      render(
        <GraphCanvasTestWrapper
          ref={ref}
          nodes={mockNodes}
          links={mockLinks}
          onNodeClick={vi.fn()}
          onNodeSelect={vi.fn()}
          selectedNodes={[]}
          highlightedNodes={[]}
        />
      );

      const canvas = screen.getByTestId('graph-canvas');
      expect(canvas.getAttribute('data-simulation')).toBe('false');

      ref.current?.startSimulation();
      expect(canvas.getAttribute('data-simulation')).toBe('true');
    });

    it('should pause and resume simulation', () => {
      const ref = createRef<any>();

      render(
        <GraphCanvasTestWrapper
          ref={ref}
          nodes={mockNodes}
          links={mockLinks}
          onNodeClick={vi.fn()}
          onNodeSelect={vi.fn()}
          selectedNodes={[]}
          highlightedNodes={[]}
        />
      );

      const canvas = screen.getByTestId('graph-canvas');
      
      ref.current?.startSimulation();
      expect(canvas.getAttribute('data-simulation')).toBe('true');

      ref.current?.pauseSimulation();
      expect(canvas.getAttribute('data-simulation')).toBe('false');

      ref.current?.resumeSimulation();
      expect(canvas.getAttribute('data-simulation')).toBe('true');
    });

    it('should keep simulation running', () => {
      const ref = createRef<any>();

      render(
        <GraphCanvasTestWrapper
          ref={ref}
          nodes={mockNodes}
          links={mockLinks}
          onNodeClick={vi.fn()}
          onNodeSelect={vi.fn()}
          selectedNodes={[]}
          highlightedNodes={[]}
        />
      );

      const canvas = screen.getByTestId('graph-canvas');
      
      expect(canvas.getAttribute('data-keep-running')).toBe('false');

      ref.current?.keepSimulationRunning(true);
      expect(canvas.getAttribute('data-keep-running')).toBe('true');
      expect(canvas.getAttribute('data-simulation')).toBe('true');

      ref.current?.keepSimulationRunning(false);
      expect(canvas.getAttribute('data-keep-running')).toBe('false');
    });
  });

  describe('Performance', () => {
    it('should handle large datasets', () => {
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
        <GraphCanvasTestWrapper
          nodes={largeNodes}
          links={largeLinks}
          onNodeClick={vi.fn()}
          onNodeSelect={vi.fn()}
          selectedNodes={[]}
          highlightedNodes={[]}
        />
      );

      const renderTime = performance.now() - startTime;
      
      // Should render quickly even with large dataset
      expect(renderTime).toBeLessThan(500);
      expect(screen.getByText('Nodes: 1000, Links: 2000')).toBeInTheDocument();
    });
  });
});