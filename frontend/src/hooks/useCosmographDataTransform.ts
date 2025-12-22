/**
 * useCosmographDataTransform Hook
 * 
 * Handles transformation of graph nodes and links into Cosmograph format.
 * Extracted from GraphCanvasV2 to improve testability and separation of concerns.
 * 
 * PERFORMANCE FIX (GRAPH-67): Uses length-based and content-hash dependencies
 * instead of direct array references to prevent unnecessary re-processing.
 */

import { useMemo, useRef } from 'react';
import { GraphNode, GraphLink } from '../types/graph';
import {
  CosmographDataPreparer,
  getGlobalDataPreparer,
  sanitizeNode,
  sanitizeLink
} from '../utils/cosmographDataPreparer';

interface TransformConfig {
  clusteringMethod?: string;
  centralityMetric?: string;
  clusterStrength?: number;
}

// Using indexed access type to allow any node/link shape for Cosmograph
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type CosmographNodeType = any;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type CosmographLinkType = any;

interface CosmographData {
  nodes: CosmographNodeType[];
  links: CosmographLinkType[];
}

/**
 * Generate a lightweight content hash for nodes
 * Only checks IDs to detect actual data changes vs reference changes
 */
function generateNodesHash(nodes: GraphNode[]): string {
  if (!nodes || nodes.length === 0) return '';
  // Sample first, middle, and last nodes for quick hash
  const first = nodes[0]?.id || '';
  const mid = nodes[Math.floor(nodes.length / 2)]?.id || '';
  const last = nodes[nodes.length - 1]?.id || '';
  return `${nodes.length}:${first}:${mid}:${last}`;
}

/**
 * Generate a lightweight content hash for links
 */
function generateLinksHash(links: GraphLink[]): string {
  if (!links || links.length === 0) return '';
  const first = links[0];
  const last = links[links.length - 1];
  const firstKey = first ? `${first.source || first.from}-${first.target || first.to}` : '';
  const lastKey = last ? `${last.source || last.from}-${last.target || last.to}` : '';
  return `${links.length}:${firstKey}:${lastKey}`;
}

export const useCosmographDataTransform = (
  nodes: GraphNode[],
  links: GraphLink[],
  config: TransformConfig
): CosmographData => {
  // Ensure nodes and links are always arrays to prevent .map() errors
  const safeNodes = Array.isArray(nodes) ? nodes : [];
  const safeLinks = Array.isArray(links) ? links : [];

  // Debug: Only log once when data first arrives (not on every render)

  // Reference to the data preparer (singleton pattern)
  const dataPreparerRef = useRef<CosmographDataPreparer>(
    getGlobalDataPreparer({
      clusteringMethod: config.clusteringMethod,
      centralityMetric: config.centralityMetric,
      clusterStrength: config.clusterStrength
    })
  );

  // PERFORMANCE FIX (GRAPH-67): Use content-based hashes instead of array references
  // This prevents re-processing when arrays are recreated with same content
  const nodesHash = useMemo(() => generateNodesHash(safeNodes), [safeNodes]);
  const linksHash = useMemo(() => generateLinksHash(safeLinks), [safeLinks]);

  // Store previous result to return stable reference when content hasn't changed
  const prevResultRef = useRef<CosmographData>({ nodes: [], links: [] });
  const prevHashRef = useRef<string>('');

  // Memoized transformation of nodes and links
  const cosmographData = useMemo(() => {
    const currentHash = `${nodesHash}|${linksHash}|${config.clusteringMethod}|${config.centralityMetric}|${config.clusterStrength}`;

    // PERFORMANCE FIX: Return previous result if content hash matches
    if (currentHash === prevHashRef.current && prevResultRef.current.nodes.length > 0) {
      return prevResultRef.current;
    }

    const preparer = dataPreparerRef.current;

    // Reset preparer state for clean transformation
    preparer.reset();

    // Build index maps for efficient lookups
    const nodeIdToIndex = new Map<string, number>();
    const nodeTypeIndexMap = new Map<string, number>();

    // Transform nodes with sanitization
    const transformedNodes = safeNodes.map((node, index) => {
      nodeIdToIndex.set(node.id, index);

      // Track node type for color generation
      const nodeType = node.node_type || 'Unknown';
      if (!nodeTypeIndexMap.has(nodeType)) {
        nodeTypeIndexMap.set(nodeType, nodeTypeIndexMap.size);
      }

      // Sanitize and transform node for Cosmograph
      return sanitizeNode(node, index, {
        clusteringMethod: config.clusteringMethod,
        centralityMetric: config.centralityMetric,
        clusterStrength: config.clusterStrength,
        nodeTypeIndexMap
      });
    });

    // Transform links with sanitization and filtering
    const transformedLinks = safeLinks
      .map(link => sanitizeLink(link, nodeIdToIndex))
      .filter(link => link !== null);

    const result = {
      nodes: transformedNodes,
      links: transformedLinks
    };

    // Debug: Only log when data is first ready (not on every transform)
    if (transformedNodes.length > 0 && prevResultRef.current.nodes.length === 0) {
      console.log('[useCosmographDataTransform] Data ready:', transformedNodes.length, 'nodes,', transformedLinks.length, 'links');
    }

    // Store for future comparison
    prevHashRef.current = currentHash;
    prevResultRef.current = result;

    return result;
  }, [nodesHash, linksHash, config.clusteringMethod, config.centralityMetric, config.clusterStrength]);

  return cosmographData;
};
