import React, { forwardRef, useImperativeHandle, useRef, useEffect } from 'react';
import { Cosmograph, CosmographRef } from '@cosmograph/react';
import { GraphNode } from '../../../api/types';
import { GraphLink } from '../../../types/graph';
import { logger } from '../../../utils/logger';

interface GraphRendererProps {
  nodes: GraphNode[];
  links: GraphLink[];
  
  // Visual configuration
  nodeColor?: string | ((node: GraphNode) => string);
  nodeSize?: number | ((node: GraphNode) => number);
  nodeLabel?: (node: GraphNode) => string;
  linkColor?: string | ((link: GraphLink) => string);
  linkWidth?: number | ((link: GraphLink) => number);
  
  // Interaction callbacks
  onNodeClick?: (node: GraphNode | null) => void;
  onNodeHover?: (node: GraphNode | null) => void;
  onNodeDoubleClick?: (node: GraphNode | null) => void;
  onZoom?: (zoomLevel: number) => void;
  
  // Performance options
  showFPSMonitor?: boolean;
  simulationGravity?: number;
  simulationRepulsion?: number;
  simulationFriction?: number;
  pixelRatio?: number;
  
  // Layout
  initialZoomLevel?: number;
  fitViewOnInit?: boolean;
}

export interface GraphRendererRef {
  zoomIn: () => void;
  zoomOut: () => void;
  fitView: () => void;
  getZoomLevel: () => number;
  selectNode: (nodeId: string) => void;
  highlightNodes: (nodeIds: string[]) => void;
  clearHighlights: () => void;
  pauseSimulation: () => void;
  resumeSimulation: () => void;
  restartSimulation: () => void;
  getCosmographRef: () => CosmographRef | null;
}

/**
 * GraphRenderer - Pure Cosmograph wrapper component
 * 
 * This component is a thin wrapper around Cosmograph with no business logic.
 * All data transformations and state management should be handled externally.
 */
export const GraphRenderer = forwardRef<GraphRendererRef, GraphRendererProps>(
  (
    {
      nodes,
      links,
      nodeColor = '#6366f1',
      nodeSize = 4,
      nodeLabel = (node) => node.label || node.id,
      linkColor = '#94a3b8',
      linkWidth = 1,
      onNodeClick,
      onNodeHover,
      onNodeDoubleClick,
      onZoom,
      showFPSMonitor = false,
      simulationGravity = 0,
      simulationRepulsion = 0.5,
      simulationFriction = 0.85,
      pixelRatio = 2,
      initialZoomLevel = 1,
      fitViewOnInit = true
    },
    ref
  ) => {
    const cosmographRef = useRef<CosmographRef>(null);

    // Expose methods via ref
    useImperativeHandle(
      ref,
      () => ({
        zoomIn: () => {
          if (cosmographRef.current) {
            const currentZoom = cosmographRef.current.getZoomLevel();
            cosmographRef.current.setZoomLevel(currentZoom * 1.2);
            logger.debug('GraphRenderer: Zoomed in');
          }
        },
        zoomOut: () => {
          if (cosmographRef.current) {
            const currentZoom = cosmographRef.current.getZoomLevel();
            cosmographRef.current.setZoomLevel(currentZoom * 0.8);
            logger.debug('GraphRenderer: Zoomed out');
          }
        },
        fitView: () => {
          if (cosmographRef.current) {
            cosmographRef.current.fitView();
            logger.debug('GraphRenderer: Fit view');
          }
        },
        getZoomLevel: () => {
          return cosmographRef.current?.getZoomLevel() || 1;
        },
        selectNode: (nodeId: string) => {
          if (cosmographRef.current) {
            const node = nodes.find(n => n.id === nodeId);
            if (node) {
              cosmographRef.current.selectNode(node);
              logger.debug('GraphRenderer: Selected node:', nodeId);
            }
          }
        },
        highlightNodes: (nodeIds: string[]) => {
          if (cosmographRef.current) {
            const nodesToHighlight = nodes.filter(n => nodeIds.includes(n.id));
            cosmographRef.current.highlightNodes(nodesToHighlight);
            logger.debug('GraphRenderer: Highlighted nodes:', nodeIds);
          }
        },
        clearHighlights: () => {
          if (cosmographRef.current) {
            cosmographRef.current.unselectNodes();
            logger.debug('GraphRenderer: Cleared highlights');
          }
        },
        pauseSimulation: () => {
          if (cosmographRef.current) {
            cosmographRef.current.pause();
            logger.debug('GraphRenderer: Paused simulation');
          }
        },
        resumeSimulation: () => {
          if (cosmographRef.current) {
            cosmographRef.current.start();
            logger.debug('GraphRenderer: Resumed simulation');
          }
        },
        restartSimulation: () => {
          if (cosmographRef.current) {
            cosmographRef.current.restart();
            logger.debug('GraphRenderer: Restarted simulation');
          }
        },
        getCosmographRef: () => cosmographRef.current
      }),
      [nodes]
    );

    // Fit view on mount if requested
    useEffect(() => {
      if (fitViewOnInit && cosmographRef.current) {
        // Small delay to ensure Cosmograph is fully initialized
        const timer = setTimeout(() => {
          cosmographRef.current?.fitView();
          logger.debug('GraphRenderer: Initial fit view');
        }, 100);
        
        return () => clearTimeout(timer);
      }
    }, [fitViewOnInit]);

    // Handle zoom changes
    useEffect(() => {
      if (!cosmographRef.current || !onZoom) return;

      const handleZoomEnd = () => {
        const zoomLevel = cosmographRef.current?.getZoomLevel();
        if (zoomLevel !== undefined) {
          onZoom(zoomLevel);
        }
      };

      // Cosmograph doesn't expose zoom events directly, so we'd need to poll or use a different approach
      // This is a simplified version - in production, you'd want proper event handling
      
      return () => {
        // Cleanup
      };
    }, [onZoom]);

    // Log render stats
    useEffect(() => {
      logger.debug('GraphRenderer: Rendering', {
        nodes: nodes.length,
        links: links.length,
        showFPSMonitor
      });
    }, [nodes.length, links.length, showFPSMonitor]);

    return (
      <Cosmograph
        ref={cosmographRef}
        nodes={nodes}
        links={links}
        nodeColor={nodeColor}
        nodeSize={nodeSize}
        nodeLabelAccessor={nodeLabel}
        linkColor={linkColor}
        linkWidth={linkWidth}
        onClick={onNodeClick}
        onMouseMove={onNodeHover}
        onDblClick={onNodeDoubleClick}
        showFPSMonitor={showFPSMonitor}
        simulationGravity={simulationGravity}
        simulationRepulsion={simulationRepulsion}
        simulationFriction={simulationFriction}
        pixelRatio={pixelRatio}
        initialZoomLevel={initialZoomLevel}
        disableSimulation={false}
        space={{
          padding: 0.1
        }}
        scaleNodesOnZoom={true}
        curvedLinks={false}
        showDynamicLabels={true}
        hoveredNodeLabelClassName="text-white bg-black/80 px-2 py-1 rounded"
      />
    );
  }
);

GraphRenderer.displayName = 'GraphRenderer';

export default GraphRenderer;