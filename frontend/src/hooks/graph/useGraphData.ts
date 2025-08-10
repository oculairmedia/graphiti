import { useState, useCallback, useRef, useEffect, useMemo } from 'react';
import { GraphNode } from '../../api/types';

// Define graph data types
export interface GraphLink {
  source: string;
  target: string;
  sourceIndex?: number;
  targetIndex?: number;
  edge_type?: string;
  weight?: number;
  created_at?: string;
  updated_at?: string;
  properties?: Record<string, unknown>;
}

export interface GraphDataState {
  nodes: GraphNode[];
  links: GraphLink[];
  loading: boolean;
  error: string | null;
  stats: {
    totalNodes: number;
    totalEdges: number;
    nodeTypes: Record<string, number>;
    lastUpdated: number;
  };
}

export interface GraphDataActions {
  setNodes: (nodes: GraphNode[]) => void;
  setLinks: (links: GraphLink[]) => void;
  updateNode: (nodeId: string, updates: Partial<GraphNode>) => void;
  updateNodes: (updates: Map<string, Partial<GraphNode>>) => void;
  addNodes: (nodes: GraphNode[]) => void;
  removeNodes: (nodeIds: string[]) => void;
  addLinks: (links: GraphLink[]) => void;
  removeLinks: (linkIds: string[]) => void;
  applyDelta: (delta: GraphDelta) => void;
  reset: () => void;
  setError: (error: string | null) => void;
  setLoading: (loading: boolean) => void;
}

export interface GraphDelta {
  addedNodes?: GraphNode[];
  updatedNodes?: Map<string, Partial<GraphNode>>;
  removedNodeIds?: string[];
  addedLinks?: GraphLink[];
  removedLinkIds?: string[];
  timestamp: number;
}

export interface UseGraphDataOptions {
  initialNodes?: GraphNode[];
  initialLinks?: GraphLink[];
  enableDeltaProcessing?: boolean;
  maxHistorySize?: number;
}

/**
 * Custom hook for managing graph data state with optimized delta processing
 */
export function useGraphData(options: UseGraphDataOptions = {}): [GraphDataState, GraphDataActions] {
  const {
    initialNodes = [],
    initialLinks = [],
    enableDeltaProcessing = true,
    maxHistorySize = 10
  } = options;

  // Main state
  const [nodes, setNodesState] = useState<GraphNode[]>(initialNodes);
  const [links, setLinksState] = useState<GraphLink[]>(initialLinks);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Refs for performance optimization
  const nodeMapRef = useRef<Map<string, GraphNode>>(new Map());
  const linkMapRef = useRef<Map<string, GraphLink>>(new Map());
  const deltaHistoryRef = useRef<GraphDelta[]>([]);

  // Update node map when nodes change
  useEffect(() => {
    const nodeMap = new Map<string, GraphNode>();
    nodes.forEach(node => {
      nodeMap.set(node.id, node);
    });
    nodeMapRef.current = nodeMap;
  }, [nodes]);

  // Update link map when links change
  useEffect(() => {
    const linkMap = new Map<string, GraphLink>();
    links.forEach(link => {
      const linkId = `${link.source}-${link.target}`;
      linkMap.set(linkId, link);
    });
    linkMapRef.current = linkMap;
  }, [links]);

  // Calculate stats
  const stats = useMemo(() => {
    const nodeTypes: Record<string, number> = {};
    nodes.forEach(node => {
      const type = node.node_type || 'Unknown';
      nodeTypes[type] = (nodeTypes[type] || 0) + 1;
    });

    return {
      totalNodes: nodes.length,
      totalEdges: links.length,
      nodeTypes,
      lastUpdated: Date.now()
    };
  }, [nodes, links]);

  // Actions
  const setNodes = useCallback((newNodes: GraphNode[]) => {
    setNodesState(newNodes);
    setError(null);
  }, []);

  const setLinks = useCallback((newLinks: GraphLink[]) => {
    setLinksState(newLinks);
    setError(null);
  }, []);

  const updateNode = useCallback((nodeId: string, updates: Partial<GraphNode>) => {
    setNodesState(prevNodes => 
      prevNodes.map(node => 
        node.id === nodeId ? { ...node, ...updates } : node
      )
    );
  }, []);

  const updateNodes = useCallback((updates: Map<string, Partial<GraphNode>>) => {
    if (updates.size === 0) return;
    
    setNodesState(prevNodes => 
      prevNodes.map(node => {
        const nodeUpdate = updates.get(node.id);
        return nodeUpdate ? { ...node, ...nodeUpdate } : node;
      })
    );
  }, []);

  const addNodes = useCallback((newNodes: GraphNode[]) => {
    if (newNodes.length === 0) return;
    
    setNodesState(prevNodes => {
      const existingIds = new Set(prevNodes.map(n => n.id));
      const uniqueNewNodes = newNodes.filter(n => !existingIds.has(n.id));
      return [...prevNodes, ...uniqueNewNodes];
    });
  }, []);

  const removeNodes = useCallback((nodeIds: string[]) => {
    if (nodeIds.length === 0) return;
    
    const idsToRemove = new Set(nodeIds);
    setNodesState(prevNodes => 
      prevNodes.filter(node => !idsToRemove.has(node.id))
    );
    
    // Also remove connected links
    setLinksState(prevLinks =>
      prevLinks.filter(link => 
        !idsToRemove.has(link.source) && !idsToRemove.has(link.target)
      )
    );
  }, []);

  const addLinks = useCallback((newLinks: GraphLink[]) => {
    if (newLinks.length === 0) return;
    
    setLinksState(prevLinks => {
      const existingLinkIds = new Set(
        prevLinks.map(l => `${l.source}-${l.target}`)
      );
      const uniqueNewLinks = newLinks.filter(
        l => !existingLinkIds.has(`${l.source}-${l.target}`)
      );
      return [...prevLinks, ...uniqueNewLinks];
    });
  }, []);

  const removeLinks = useCallback((linkIds: string[]) => {
    if (linkIds.length === 0) return;
    
    const idsToRemove = new Set(linkIds);
    setLinksState(prevLinks =>
      prevLinks.filter(link => {
        const linkId = `${link.source}-${link.target}`;
        return !idsToRemove.has(linkId);
      })
    );
  }, []);

  const applyDelta = useCallback((delta: GraphDelta) => {
    if (!enableDeltaProcessing) return;

    // Store delta in history
    deltaHistoryRef.current.push(delta);
    if (deltaHistoryRef.current.length > maxHistorySize) {
      deltaHistoryRef.current.shift();
    }

    // Apply delta operations in order
    if (delta.removedNodeIds?.length) {
      removeNodes(delta.removedNodeIds);
    }
    
    if (delta.removedLinkIds?.length) {
      removeLinks(delta.removedLinkIds);
    }

    if (delta.updatedNodes?.size) {
      updateNodes(delta.updatedNodes);
    }

    if (delta.addedNodes?.length) {
      addNodes(delta.addedNodes);
    }

    if (delta.addedLinks?.length) {
      addLinks(delta.addedLinks);
    }
  }, [
    enableDeltaProcessing,
    maxHistorySize,
    removeNodes,
    removeLinks,
    updateNodes,
    addNodes,
    addLinks
  ]);

  const reset = useCallback(() => {
    setNodesState([]);
    setLinksState([]);
    setError(null);
    setLoading(false);
    deltaHistoryRef.current = [];
  }, []);

  // Create state object
  const state: GraphDataState = {
    nodes,
    links,
    loading,
    error,
    stats
  };

  // Create actions object
  const actions: GraphDataActions = {
    setNodes,
    setLinks,
    updateNode,
    updateNodes,
    addNodes,
    removeNodes,
    addLinks,
    removeLinks,
    applyDelta,
    reset,
    setError,
    setLoading
  };

  return [state, actions];
}

/**
 * Create a graph delta by comparing two states
 */
export function createGraphDelta(
  oldState: { nodes: GraphNode[]; links: GraphLink[] },
  newState: { nodes: GraphNode[]; links: GraphLink[] }
): GraphDelta {
  const oldNodeMap = new Map(oldState.nodes.map(n => [n.id, n]));
  const newNodeMap = new Map(newState.nodes.map(n => [n.id, n]));
  const oldLinkMap = new Map(oldState.links.map(l => [`${l.source}-${l.target}`, l]));
  const newLinkMap = new Map(newState.links.map(l => [`${l.source}-${l.target}`, l]));

  const delta: GraphDelta = {
    timestamp: Date.now()
  };

  // Find added nodes
  const addedNodes: GraphNode[] = [];
  const updatedNodes = new Map<string, Partial<GraphNode>>();
  
  newNodeMap.forEach((node, id) => {
    const oldNode = oldNodeMap.get(id);
    if (!oldNode) {
      addedNodes.push(node);
    } else if (JSON.stringify(oldNode) !== JSON.stringify(node)) {
      // Simple deep comparison - could be optimized
      updatedNodes.set(id, node);
    }
  });

  // Find removed nodes
  const removedNodeIds: string[] = [];
  oldNodeMap.forEach((_, id) => {
    if (!newNodeMap.has(id)) {
      removedNodeIds.push(id);
    }
  });

  // Find added links
  const addedLinks: GraphLink[] = [];
  newLinkMap.forEach((link, id) => {
    if (!oldLinkMap.has(id)) {
      addedLinks.push(link);
    }
  });

  // Find removed links
  const removedLinkIds: string[] = [];
  oldLinkMap.forEach((_, id) => {
    if (!newLinkMap.has(id)) {
      removedLinkIds.push(id);
    }
  });

  // Only include non-empty fields
  if (addedNodes.length > 0) delta.addedNodes = addedNodes;
  if (updatedNodes.size > 0) delta.updatedNodes = updatedNodes;
  if (removedNodeIds.length > 0) delta.removedNodeIds = removedNodeIds;
  if (addedLinks.length > 0) delta.addedLinks = addedLinks;
  if (removedLinkIds.length > 0) delta.removedLinkIds = removedLinkIds;

  return delta;
}