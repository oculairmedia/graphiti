import { useRef, useMemo } from 'react';
import { GraphNode } from '../api/types';
import type { GraphLink } from '../types/graph';
import { logger } from '../utils/logger';

interface GraphDataDiff {
  addedNodes: GraphNode[];
  updatedNodes: GraphNode[];
  removedNodeIds: string[];
  addedLinks: GraphLink[];
  updatedLinks: GraphLink[];
  removedLinkIds: string[];
  hasChanges: boolean;
  changeCount: number;
  isInitialLoad: boolean;
}

interface GraphData {
  nodes: GraphNode[];
  edges: GraphLink[];
}

/**
 * Custom hook that detects changes between current and previous graph data
 * Returns structured diff information for incremental updates
 */
export const useGraphDataDiff = (currentData: GraphData | null): GraphDataDiff => {
  const previousDataRef = useRef<GraphData | null>(null);
  const previousNodeMapRef = useRef<Map<string, GraphNode>>(new Map());
  const previousLinkMapRef = useRef<Map<string, GraphLink>>(new Map());

  const diff = useMemo(() => {
    // Initialize empty diff
    const emptyDiff: GraphDataDiff = {
      addedNodes: [],
      updatedNodes: [],
      removedNodeIds: [],
      addedLinks: [],
      updatedLinks: [],
      removedLinkIds: [],
      hasChanges: false,
      changeCount: 0,
      isInitialLoad: false
    };

    // Return empty diff if no current data
    if (!currentData) {
      return emptyDiff;
    }

    const previousData = previousDataRef.current;
    
    // First time loading - mark as initial load, don't trigger incremental updates
    if (!previousData) {
      return {
        addedNodes: currentData.nodes,
        updatedNodes: [],
        removedNodeIds: [],
        addedLinks: currentData.edges,
        updatedLinks: [],
        removedLinkIds: [],
        hasChanges: false, // Don't trigger incremental updates on initial load
        changeCount: 0, // Don't count initial load as changes
        isInitialLoad: true
      };
    }

    // Build maps for efficient comparison
    const currentNodeMap = new Map(currentData.nodes.map(node => [node.id, node]));
    const currentLinkMap = new Map(currentData.edges.map(link => [`${link.source || link.from}-${link.target || link.to}`, link]));
    
    const previousNodeMap = previousNodeMapRef.current;
    const previousLinkMap = previousLinkMapRef.current;

    // Find node changes
    const addedNodes: GraphNode[] = [];
    const updatedNodes: GraphNode[] = [];
    const removedNodeIds: string[] = [];

    // Check for added and updated nodes
    for (const [nodeId, currentNode] of currentNodeMap) {
      const previousNode = previousNodeMap.get(nodeId);
      
      if (!previousNode) {
        // Node is new
        addedNodes.push(currentNode);
      } else {
        // Check if node was updated by comparing key properties
        const currentPropertiesHash = JSON.stringify(currentNode.properties);
        const hasChanges = (
          previousNode.label !== currentNode.label ||
          previousNode.node_type !== currentNode.node_type ||
          previousNode.size !== currentNode.size ||
          (previousNode as any).propertiesHash !== currentPropertiesHash
        );
        
        if (hasChanges) {
          updatedNodes.push(currentNode);
        }
      }
    }

    // Check for removed nodes
    for (const [nodeId] of previousNodeMap) {
      if (!currentNodeMap.has(nodeId)) {
        removedNodeIds.push(nodeId);
      }
    }

    // Find link changes
    const addedLinks: GraphLink[] = [];
    const updatedLinks: GraphLink[] = [];
    const removedLinkIds: string[] = [];

    // Check for added and updated links
    for (const [linkKey, currentLink] of currentLinkMap) {
      const previousLink = previousLinkMap.get(linkKey);
      
      if (!previousLink) {
        // Link is new
        addedLinks.push(currentLink);
      } else {
        // Check if link was updated by comparing properties
        const hasChanges = (
          previousLink.weight !== currentLink.weight ||
          previousLink.edge_type !== currentLink.edge_type ||
          JSON.stringify(previousLink.properties) !== JSON.stringify(currentLink.properties)
        );
        
        if (hasChanges) {
          updatedLinks.push(currentLink);
        }
      }
    }

    // Check for removed links
    for (const [linkKey] of previousLinkMap) {
      if (!currentLinkMap.has(linkKey)) {
        removedLinkIds.push(linkKey);
      }
    }

    const changeCount = addedNodes.length + updatedNodes.length + removedNodeIds.length + 
                       addedLinks.length + updatedLinks.length + removedLinkIds.length;
    
    const hasChanges = changeCount > 0;

    // Only log when there are actual changes to reduce console noise
    if (hasChanges) {
    }

    return {
      addedNodes,
      updatedNodes,
      removedNodeIds,
      addedLinks,
      updatedLinks,
      removedLinkIds,
      hasChanges,
      changeCount,
      isInitialLoad: false
    };
  }, [currentData]);

  // Update refs after diff calculation - store minimal data for comparison
  if (currentData) {
    previousDataRef.current = currentData; // Store reference, not copy
    
    // Update node map with only essential properties for comparison
    previousNodeMapRef.current = new Map(
      currentData.nodes.map(node => [
        node.id, 
        {
          id: node.id,
          label: node.label,
          node_type: node.node_type,
          size: node.size,
          // Store properties hash instead of full object to save memory
          propertiesHash: JSON.stringify(node.properties)
        } as any
      ])
    );
    
    // Update link map with minimal data
    previousLinkMapRef.current = new Map(
      currentData.edges.map(link => [
        `${link.source || link.from}-${link.target || link.to}`, 
        {
          from: link.from,
          to: link.to,
          source: link.source,
          target: link.target,
          edge_type: link.edge_type,
          weight: link.weight
        } as any
      ])
    );
  }

  return diff;
};

export type { GraphDataDiff };