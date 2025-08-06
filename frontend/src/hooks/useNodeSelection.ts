import { useState, useCallback, useRef, useMemo, useOptimistic, startTransition } from 'react';
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
  const [optimisticSelectedNodes, addOptimisticSelectedNode] = useOptimistic(
    selectedNodes,
    (state: string[], newNodeId: string | { remove: string }) => {
      if (typeof newNodeId === 'string') {
        return state.includes(newNodeId) 
          ? state.filter(id => id !== newNodeId)
          : [...state, newNodeId];
      } else {
        // Handle removal
        return state.filter(id => id !== newNodeId.remove);
      }
    }
  );
  
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [optimisticSelectedNode, setOptimisticSelectedNode] = useOptimistic(
    selectedNode,
    (_state: GraphNode | null, newNode: GraphNode | null) => newNode
  );
  
  const [highlightedNodes, setHighlightedNodes] = useState<string[]>([]);
  const [optimisticHighlightedNodes, addOptimisticHighlightedNodes] = useOptimistic(
    highlightedNodes,
    (_state: string[], newNodeIds: string[]) => newNodeIds
  );
  
  const [hoveredNode, setHoveredNode] = useState<GraphNode | null>(null);
  const [hoveredConnectedNodes, setHoveredConnectedNodes] = useState<string[]>([]);

  const handleNodeSelect = useCallback(async (nodeId: string) => {
    // Wrap optimistic update in startTransition to avoid React 19 warning
    startTransition(() => {
      addOptimisticSelectedNode(nodeId);
    });
    
    // Simulate async operation (e.g., API call, graph update)
    await new Promise(resolve => setTimeout(resolve, 100));
    
    // Actually update the state
    setSelectedNodes(prev => {
      if (prev.includes(nodeId)) {
        return prev.filter(id => id !== nodeId);
      } else {
        return [...prev, nodeId];
      }
    });
  }, [addOptimisticSelectedNode]);

  const handleNodeClick = useCallback(async (node: GraphNode) => {
    console.log('[useNodeSelection] handleNodeClick called with node:', node.id);
    
    // Wrap optimistic update in startTransition to avoid React 19 warning
    startTransition(() => {
      setOptimisticSelectedNode(node);
    });
    
    // Simulate async operation
    await new Promise(resolve => setTimeout(resolve, 50));
    
    // Actually update the state
    setSelectedNode(node);
  }, [setOptimisticSelectedNode]);

  const handleNodeSelectWithCosmograph = useCallback(async (node: GraphNode) => {
    // Check if this is the same node to prevent duplicate animations
    if (selectedNode?.id === node.id) {
      return; // Node is already selected, no need to re-select
    }
    
    // Optimistically update immediately
    setOptimisticSelectedNode(node);
    addOptimisticSelectedNode(node.id);
    
    // Also select in Cosmograph for visual effects
    if (graphCanvasRef.current && typeof graphCanvasRef.current.selectNode === 'function') {
      graphCanvasRef.current.selectNode(node);
    }
    
    // Update both the selected nodes list and the selected node
    // Use Promise.all to ensure both complete before continuing
    await Promise.all([
      handleNodeSelect(node.id),
      handleNodeClick(node)
    ]);
  }, [selectedNode, handleNodeSelect, handleNodeClick, graphCanvasRef, setOptimisticSelectedNode, addOptimisticSelectedNode]);

  const handleHighlightNodes = useCallback(async (nodes: GraphNode[]) => {
    const nodeIds = nodes.map(node => node.id);
    
    // Optimistically update immediately
    addOptimisticHighlightedNodes(nodeIds);
    
    // Simulate async operation
    await new Promise(resolve => setTimeout(resolve, 50));
    
    // Actually update the state
    setHighlightedNodes(nodeIds);
  }, [addOptimisticHighlightedNodes]);

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
    // Check current state using refs to avoid dependencies
    setSelectedNodes(prev => {
      if (prev.length > 0) return [];
      return prev;
    });
    setSelectedNode(prev => {
      if (prev !== null) return null;
      return prev;
    });
    setHighlightedNodes(prev => {
      if (prev.length > 0) return [];
      return prev;
    });
    
    // Clear GraphCanvas selection using direct ref (only for clearing)
    if (graphCanvasRef.current && typeof graphCanvasRef.current.clearSelection === 'function') {
      graphCanvasRef.current.clearSelection();
    }
  }, [graphCanvasRef]);

  // Memoize the return object to prevent unnecessary re-renders
  return useMemo(() => ({
    selectedNodes: optimisticSelectedNodes,
    selectedNode: optimisticSelectedNode,
    highlightedNodes: optimisticHighlightedNodes,
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
  }), [
    optimisticSelectedNodes,
    optimisticSelectedNode,
    optimisticHighlightedNodes,
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
  ]);
}