import { useState, useCallback, useRef } from 'react';
import { GraphNode } from '../api/types';
import { GraphLink } from '../types/graph';

interface GraphCanvasHandle {
  clearSelection: () => void;
  selectNode: (node: GraphNode) => void;
  selectNodes: (nodes: GraphNode[]) => void;
  getConnectedPointIndices: (index: number) => number[] | undefined;
}

export function useNodeSelection(
  transformedData: { nodes: GraphNode[], links: GraphLink[] },
  graphCanvasRef: React.RefObject<GraphCanvasHandle>
) {
  const [selectedNodes, setSelectedNodes] = useState<string[]>([]);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [highlightedNodes, setHighlightedNodes] = useState<string[]>([]);
  const [hoveredNode, setHoveredNode] = useState<GraphNode | null>(null);
  const [hoveredConnectedNodes, setHoveredConnectedNodes] = useState<string[]>([]);

  const handleNodeSelect = useCallback((nodeId: string) => {
    if (selectedNodes.includes(nodeId)) {
      setSelectedNodes(selectedNodes.filter(id => id !== nodeId));
    } else {
      setSelectedNodes([...selectedNodes, nodeId]);
    }
  }, [selectedNodes]);

  const handleNodeClick = useCallback((node: GraphNode) => {
    setSelectedNode(node);
  }, []);

  const handleNodeSelectWithCosmograph = useCallback((node: GraphNode) => {
    // Set React state
    setSelectedNode(node);
    handleNodeSelect(node.id);
    
    // Also select in Cosmograph for visual effects
    if (graphCanvasRef.current && typeof graphCanvasRef.current.selectNode === 'function') {
      graphCanvasRef.current.selectNode(node);
    }
  }, [handleNodeSelect, graphCanvasRef]);

  const handleHighlightNodes = useCallback((nodes: GraphNode[]) => {
    const nodeIds = nodes.map(node => node.id);
    setHighlightedNodes(nodeIds);
  }, []);

  const handleSelectNodes = useCallback((nodes: GraphNode[]) => {
    // Select multiple nodes with Cosmograph visual effects
    if (graphCanvasRef.current && typeof graphCanvasRef.current.selectNodes === 'function') {
      graphCanvasRef.current.selectNodes(nodes);
    }
    
    // Update React state - for multiple selection, we'll select the first node for the modal
    // and add all to the selectedNodes array
    if (nodes.length > 0) {
      setSelectedNode(nodes[0]); // Show modal for first node
      const nodeIds = nodes.map(node => node.id);
      setSelectedNodes(nodeIds);
    }
  }, [graphCanvasRef]);

  const handleShowNeighbors = useCallback((nodeId: string) => {
    // Start with nodes to explore - if we have highlighted nodes, use all of them
    // Otherwise, just use the clicked node
    const nodesToExplore = highlightedNodes.length > 0 ? highlightedNodes : [nodeId];
    const newNeighborIds = new Set<string>();
    
    // Find neighbors for all nodes we're exploring
    nodesToExplore.forEach(currentNodeId => {
      transformedData.links.forEach(edge => {
        if (edge.source === currentNodeId) {
          newNeighborIds.add(edge.target);
        } else if (edge.target === currentNodeId) {
          newNeighborIds.add(edge.source);
        }
      });
    });
    
    // Remove nodes we're already exploring to get only NEW neighbors
    nodesToExplore.forEach(id => newNeighborIds.delete(id));
    
    // Find the actual neighbor nodes from our data
    const newNeighborNodes = transformedData.nodes.filter(node => 
      newNeighborIds.has(node.id)
    );
    
    if (newNeighborNodes.length > 0) {
      // Combine existing highlighted nodes with new neighbors
      const allHighlightedIds = [...new Set([...nodesToExplore, ...Array.from(newNeighborIds)])];
      setHighlightedNodes(allHighlightedIds);
      
      // Select all highlighted nodes with visual effects
      const allHighlightedNodes = transformedData.nodes.filter(node => 
        allHighlightedIds.includes(node.id)
      );
      
      if (graphCanvasRef.current && typeof graphCanvasRef.current.selectNodes === 'function') {
        graphCanvasRef.current.selectNodes(allHighlightedNodes);
      }
    }
  }, [highlightedNodes, transformedData, graphCanvasRef]);

  const handleNodeHover = useCallback((node: GraphNode | null) => {
    setHoveredNode(node);
    
    if (node && graphCanvasRef.current) {
      // Find connected nodes
      const nodeIndex = transformedData.nodes.findIndex(n => n.id === node.id);
      if (nodeIndex !== -1) {
        const connectedIndices = graphCanvasRef.current.getConnectedPointIndices(nodeIndex);
        if (connectedIndices && connectedIndices.length > 0) {
          const connectedNodeIds = connectedIndices
            .map(idx => transformedData.nodes[idx]?.id)
            .filter(Boolean);
          setHoveredConnectedNodes(connectedNodeIds);
        } else {
          setHoveredConnectedNodes([]);
        }
      }
    } else {
      setHoveredConnectedNodes([]);
    }
  }, [transformedData.nodes, graphCanvasRef]);

  const clearAllSelections = useCallback(() => {
    // Only update state if there's actually something to clear
    const hasSelections = selectedNodes.length > 0 || selectedNode !== null || highlightedNodes.length > 0;
    
    if (hasSelections) {
      // Batch state updates to prevent multiple re-renders
      setSelectedNodes([]); // Clear multi-selection
      setSelectedNode(null); // Clear single selection and close modal
      setHighlightedNodes([]); // Clear search highlights
    }
    
    // Clear GraphCanvas selection using direct ref (only for clearing)
    if (graphCanvasRef.current && typeof graphCanvasRef.current.clearSelection === 'function') {
      graphCanvasRef.current.clearSelection();
    }
  }, [selectedNodes.length, selectedNode, highlightedNodes.length, graphCanvasRef]);

  return {
    selectedNodes,
    selectedNode,
    highlightedNodes,
    hoveredNode,
    hoveredConnectedNodes,
    handleNodeSelect,
    handleNodeClick,
    handleNodeSelectWithCosmograph,
    handleHighlightNodes,
    handleSelectNodes,
    handleShowNeighbors,
    handleNodeHover,
    clearAllSelections,
  };
}