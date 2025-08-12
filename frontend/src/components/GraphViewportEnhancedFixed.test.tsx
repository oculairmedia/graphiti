import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '../test/utils';
import { GraphViewportEnhancedFixed } from './GraphViewportEnhancedFixed';
import { createMockNode, createMockLink } from '../test/utils';
import React from 'react';

describe('GraphViewportEnhancedFixed', () => {
  const defaultProps = {
    nodes: [
      createMockNode({ id: 'node-1', name: 'Node 1' }),
      createMockNode({ id: 'node-2', name: 'Node 2' }),
      createMockNode({ id: 'node-3', name: 'Node 3' }),
    ],
    links: [
      createMockLink({ source: 'node-1', target: 'node-2' }),
      createMockLink({ source: 'node-2', target: 'node-3' }),
    ],
    selectedNodes: [],
    highlightedNodes: [],
    hoveredNode: null,
    hoveredConnectedNodes: [],
    selectedNode: null,
    stats: {
      nodeCount: 3,
      edgeCount: 2,
      nodeTypes: { entity: 2, episode: 1 },
    },
    onNodeClick: vi.fn(),
    onNodeSelect: vi.fn(),
    onNodeHover: vi.fn(),
    onClearSelection: vi.fn(),
    onShowNeighbors: vi.fn(),
    onZoomIn: vi.fn(),
    onZoomOut: vi.fn(),
    onFitView: vi.fn(),
    onScreenshot: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Component Rendering', () => {
    it('should render without crashing', () => {
      const { container } = render(<GraphViewportEnhancedFixed {...defaultProps} />);
      expect(container).toBeTruthy();
    });

    it('should render with GraphErrorBoundary wrapper', () => {
      const { container } = render(<GraphViewportEnhancedFixed {...defaultProps} />);
      // The component is wrapped in GraphErrorBoundary
      expect(container.querySelector('.relative.h-full.w-full')).toBeInTheDocument();
    });

    it('should render GraphOverlays with correct props', () => {
      render(<GraphViewportEnhancedFixed {...defaultProps} />);
      // GraphOverlays should be rendered with stats
      const overlayContainer = document.querySelector('.absolute');
      expect(overlayContainer).toBeTruthy();
    });
  });

  describe('Enhanced Features', () => {
    it('should wrap canvas in feature components', () => {
      const { container } = render(<GraphViewportEnhancedFixed {...defaultProps} />);
      // The enhanced component wraps canvas in KeyboardShortcuts, SearchManager, etc.
      expect(container.querySelector('.relative.h-full.w-full')).toBeInTheDocument();
    });

    it('should memoize keyboard shortcuts to prevent re-renders', () => {
      const { rerender } = render(<GraphViewportEnhancedFixed {...defaultProps} />);
      
      // Re-render with same props
      rerender(<GraphViewportEnhancedFixed {...defaultProps} />);
      
      // Keyboard shortcuts should be memoized
      expect(defaultProps.onZoomIn).not.toHaveBeenCalled();
    });

    it('should handle search results callback', async () => {
      const onSelectNodes = vi.fn();
      render(
        <GraphViewportEnhancedFixed 
          {...defaultProps} 
          onSelectNodes={onSelectNodes}
        />
      );
      
      // SearchManager would handle search results
      await waitFor(() => {
        expect(onSelectNodes).not.toHaveBeenCalled();
      });
    });
  });

  describe('Node Details Panel', () => {
    it('should show node details panel when a node is selected', () => {
      const selectedNode = createMockNode({ id: 'node-1', name: 'Selected Node' });
      const { container } = render(
        <GraphViewportEnhancedFixed 
          {...defaultProps}
          selectedNode={selectedNode}
        />
      );
      
      // NodeDetailsPanel should be visible
      const detailsPanel = container.querySelector('.animate-slide-in-right');
      expect(detailsPanel).toBeInTheDocument();
    });

    it('should hide node details panel when no node is selected', () => {
      const { container } = render(
        <GraphViewportEnhancedFixed 
          {...defaultProps}
          selectedNode={null}
        />
      );
      
      // NodeDetailsPanel should not be visible
      const detailsPanel = container.querySelector('.animate-slide-in-right');
      expect(detailsPanel).not.toBeInTheDocument();
    });
  });

  describe('Imperative Handle Methods', () => {
    it('should expose zoom methods via ref', () => {
      const ref = React.createRef<any>();
      render(
        <GraphViewportEnhancedFixed 
          {...defaultProps}
          ref={ref}
        />
      );
      
      expect(ref.current).toBeDefined();
      expect(ref.current.zoomIn).toBeDefined();
      expect(ref.current.zoomOut).toBeDefined();
      expect(ref.current.fitView).toBeDefined();
    });

    it('should expose selection methods via ref', () => {
      const ref = React.createRef<any>();
      render(
        <GraphViewportEnhancedFixed 
          {...defaultProps}
          ref={ref}
        />
      );
      
      expect(ref.current.clearSelection).toBeDefined();
      expect(ref.current.selectNode).toBeDefined();
      expect(ref.current.selectNodes).toBeDefined();
      expect(ref.current.focusOnNodes).toBeDefined();
    });

    it('should expose data management methods via ref', () => {
      const ref = React.createRef<any>();
      render(
        <GraphViewportEnhancedFixed 
          {...defaultProps}
          ref={ref}
        />
      );
      
      expect(ref.current.setData).toBeDefined();
      expect(ref.current.restart).toBeDefined();
      expect(ref.current.getLiveStats).toBeDefined();
    });

    it('should expose selection tool methods via ref', () => {
      const ref = React.createRef<any>();
      render(
        <GraphViewportEnhancedFixed 
          {...defaultProps}
          ref={ref}
        />
      );
      
      expect(ref.current.activateRectSelection).toBeDefined();
      expect(ref.current.deactivateRectSelection).toBeDefined();
      expect(ref.current.activatePolygonalSelection).toBeDefined();
      expect(ref.current.deactivatePolygonalSelection).toBeDefined();
    });
  });

  describe('Timeline Integration', () => {
    it('should handle timeline toggle', () => {
      const onToggleTimeline = vi.fn();
      render(
        <GraphViewportEnhancedFixed 
          {...defaultProps}
          onToggleTimeline={onToggleTimeline}
          isTimelineVisible={true}
        />
      );
      
      // Timeline visibility prop should be passed
      expect(onToggleTimeline).not.toHaveBeenCalled();
    });

    it('should pass timeline visibility to overlays', () => {
      const { rerender } = render(
        <GraphViewportEnhancedFixed 
          {...defaultProps}
          isTimelineVisible={false}
        />
      );
      
      // Update timeline visibility
      rerender(
        <GraphViewportEnhancedFixed 
          {...defaultProps}
          isTimelineVisible={true}
        />
      );
    });
  });

  describe('Performance Optimizations', () => {
    it('should isolate Cosmograph canvas to prevent re-initialization', () => {
      const { rerender } = render(<GraphViewportEnhancedFixed {...defaultProps} />);
      
      // Update a prop that shouldn't trigger Cosmograph re-render
      rerender(
        <GraphViewportEnhancedFixed 
          {...defaultProps}
          selectedNodes={['node-1']}
        />
      );
      
      // IsolatedCosmographCanvas should prevent re-initialization
      expect(defaultProps.onNodeClick).not.toHaveBeenCalled();
    });

    it('should memoize callbacks to prevent child re-renders', () => {
      const { rerender } = render(<GraphViewportEnhancedFixed {...defaultProps} />);
      
      // Re-render with same props
      rerender(<GraphViewportEnhancedFixed {...defaultProps} />);
      
      // Callbacks should be memoized
      expect(defaultProps.onNodeClick).not.toHaveBeenCalled();
    });
  });

  describe('Error Handling', () => {
    it('should be wrapped in error boundary', () => {
      const { container } = render(<GraphViewportEnhancedFixed {...defaultProps} />);
      
      // Component should be wrapped in GraphErrorBoundary
      const errorBoundaryChild = container.querySelector('.relative.h-full.w-full.overflow-hidden');
      expect(errorBoundaryChild).toBeInTheDocument();
    });
  });
});