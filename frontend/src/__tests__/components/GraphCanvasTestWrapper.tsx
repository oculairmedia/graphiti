/**
 * Test wrapper for GraphCanvas to isolate it from complex dependencies
 */

import React, { forwardRef, useImperativeHandle, useRef, useState, useEffect } from 'react';
import { GraphNode } from '../../api/types';

interface GraphLink {
  source: string;
  target: string;
  name?: string;
}

interface GraphCanvasProps {
  nodes: GraphNode[];
  links: GraphLink[];
  onNodeClick: (node: GraphNode) => void;
  onNodeSelect: (nodeId: string) => void;
  onSelectNodes?: (nodes: GraphNode[]) => void;
  onClearSelection?: () => void;
  onNodeHover?: (node: GraphNode | null) => void;
  onStatsUpdate?: (stats: { nodeCount: number; edgeCount: number; lastUpdated: number }) => void;
  onContextReady?: (isReady: boolean) => void;
  selectedNodes: string[];
  highlightedNodes: string[];
  className?: string;
}

interface GraphCanvasHandle {
  clearSelection: () => void;
  selectNode: (node: GraphNode) => void;
  selectNodes: (nodes: GraphNode[]) => void;
  focusOnNodes: (nodeIds: string[], duration?: number, padding?: number) => void;
  zoomIn: () => void;
  zoomOut: () => void;
  fitView: (duration?: number, padding?: number) => void;
  setData: (nodes: GraphNode[], links: GraphLink[], runSimulation?: boolean) => void;
  restart: () => void;
  getLiveStats: () => { nodeCount: number; edgeCount: number; lastUpdated: number };
  addIncrementalData: (newNodes: GraphNode[], newLinks: GraphLink[], runSimulation?: boolean) => void;
  updateNodes: (updatedNodes: GraphNode[]) => void;
  removeNodes: (nodeIds: string[]) => void;
  startSimulation: (alpha?: number) => void;
  pauseSimulation: () => void;
  resumeSimulation: () => void;
  keepSimulationRunning: (enable: boolean) => void;
}

/**
 * Simplified GraphCanvas for testing
 * This version has all the same interface but without complex dependencies
 */
export const GraphCanvasTestWrapper = forwardRef<GraphCanvasHandle, GraphCanvasProps>(
  (props, ref) => {
    const {
      nodes,
      links,
      onNodeClick,
      onNodeSelect,
      onSelectNodes,
      onClearSelection,
      onNodeHover,
      onStatsUpdate,
      onContextReady,
      selectedNodes,
      highlightedNodes,
      className
    } = props;

    const [currentNodes, setCurrentNodes] = useState<GraphNode[]>(nodes);
    const [currentLinks, setCurrentLinks] = useState<GraphLink[]>(links);
    const [zoomLevel, setZoomLevel] = useState(1);
    const [isSimulationRunning, setIsSimulationRunning] = useState(false);
    const [keepRunning, setKeepRunning] = useState(false);

    // Update when props change
    useEffect(() => {
      setCurrentNodes(nodes);
      setCurrentLinks(links);
    }, [nodes, links]);

    // Report stats
    useEffect(() => {
      if (onStatsUpdate) {
        onStatsUpdate({
          nodeCount: currentNodes.length,
          edgeCount: currentLinks.length,
          lastUpdated: Date.now()
        });
      }
    }, [currentNodes, currentLinks, onStatsUpdate]);

    // Report context ready
    useEffect(() => {
      if (onContextReady) {
        setTimeout(() => onContextReady(true), 100);
      }
    }, [onContextReady]);

    // Expose imperative handle
    useImperativeHandle(ref, () => ({
      clearSelection: () => {
        if (onClearSelection) onClearSelection();
      },
      selectNode: (node: GraphNode) => {
        onNodeSelect(node.id);
      },
      selectNodes: (nodes: GraphNode[]) => {
        if (onSelectNodes) onSelectNodes(nodes);
      },
      focusOnNodes: (nodeIds: string[], duration?: number, padding?: number) => {
        // Mock implementation
        console.log('Focusing on nodes:', nodeIds);
      },
      zoomIn: () => {
        setZoomLevel(prev => prev * 1.2);
      },
      zoomOut: () => {
        setZoomLevel(prev => prev / 1.2);
      },
      fitView: (duration?: number, padding?: number) => {
        setZoomLevel(1);
      },
      setData: (nodes: GraphNode[], links: GraphLink[], runSimulation?: boolean) => {
        setCurrentNodes(nodes);
        setCurrentLinks(links);
        if (runSimulation) setIsSimulationRunning(true);
      },
      restart: () => {
        setIsSimulationRunning(true);
      },
      getLiveStats: () => ({
        nodeCount: currentNodes.length,
        edgeCount: currentLinks.length,
        lastUpdated: Date.now()
      }),
      addIncrementalData: (newNodes: GraphNode[], newLinks: GraphLink[], runSimulation?: boolean) => {
        setCurrentNodes(prev => [...prev, ...newNodes]);
        setCurrentLinks(prev => [...prev, ...newLinks]);
        if (runSimulation) setIsSimulationRunning(true);
      },
      updateNodes: (updatedNodes: GraphNode[]) => {
        setCurrentNodes(prev => {
          const nodeMap = new Map(prev.map(n => [n.id, n]));
          updatedNodes.forEach(n => nodeMap.set(n.id, n));
          return Array.from(nodeMap.values());
        });
      },
      removeNodes: (nodeIds: string[]) => {
        const idsToRemove = new Set(nodeIds);
        setCurrentNodes(prev => prev.filter(n => !idsToRemove.has(n.id)));
        setCurrentLinks(prev => prev.filter(l => 
          !idsToRemove.has(l.source) && !idsToRemove.has(l.target)
        ));
      },
      startSimulation: (alpha?: number) => {
        setIsSimulationRunning(true);
      },
      pauseSimulation: () => {
        setIsSimulationRunning(false);
      },
      resumeSimulation: () => {
        setIsSimulationRunning(true);
      },
      keepSimulationRunning: (enable: boolean) => {
        setKeepRunning(enable);
        if (enable) setIsSimulationRunning(true);
      }
    }), [currentNodes, currentLinks, onNodeSelect, onSelectNodes, onClearSelection]);

    // Handle node clicks
    const handleNodeClick = (node: GraphNode) => {
      onNodeClick(node);
      onNodeSelect(node.id);
    };

    return (
      <div 
        className={`graph-canvas-test-wrapper ${className || ''}`}
        data-testid="graph-canvas"
        data-zoom={zoomLevel}
        data-simulation={isSimulationRunning}
        data-keep-running={keepRunning}
      >
        <div className="nodes-container">
          {currentNodes.map(node => (
            <div
              key={node.id}
              className={`node ${selectedNodes.includes(node.id) ? 'selected' : ''} ${highlightedNodes.includes(node.id) ? 'highlighted' : ''}`}
              onClick={() => handleNodeClick(node)}
              onMouseEnter={() => onNodeHover?.(node)}
              onMouseLeave={() => onNodeHover?.(null)}
              data-testid={`node-${node.id}`}
            >
              {node.name}
            </div>
          ))}
        </div>
        <div className="links-container">
          {currentLinks.map((link, idx) => (
            <div
              key={`${link.source}-${link.target}-${idx}`}
              className="link"
              data-testid={`link-${link.source}-${link.target}`}
            >
              {link.source} → {link.target}
            </div>
          ))}
        </div>
        <div className="stats">
          Nodes: {currentNodes.length}, Links: {currentLinks.length}
        </div>
      </div>
    );
  }
);

GraphCanvasTestWrapper.displayName = 'GraphCanvasTestWrapper';