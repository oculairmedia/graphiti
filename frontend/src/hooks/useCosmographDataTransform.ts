/**
 * useCosmographDataTransform Hook
 * 
 * Handles transformation of graph nodes and links into Cosmograph format.
 * Extracted from GraphCanvasV2 to improve testability and separation of concerns.
 * 
 * PERFORMANCE FIX (GRAPH-67): Uses length-based and content-hash dependencies
 * instead of direct array references to prevent unnecessary re-processing.
 */

import { useMemo, useRef, useCallback } from 'react';
import { GraphNode, GraphLink } from '../types/graph';
import {
  CosmographDataPreparer,
  getGlobalDataPreparer,
  sanitizeNode,
  sanitizeLink,
  SanitizedNode,
  SanitizedLink,
} from '../utils/cosmographDataPreparer';

interface TransformConfig {
  clusteringMethod?: string;
  centralityMetric?: string;
  clusterStrength?: number;
}

export interface CosmographData {
  nodes: SanitizedNode[];
  links: SanitizedLink[];
}

export interface CosmographDataTransformResult extends CosmographData {
  /** Call after a successful incremental Cosmograph addPoints to prevent
   *  the next hash-change from triggering a full 57K-node re-sanitization. */
  markIncrementalSync: () => void;
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
): CosmographDataTransformResult => {
  const safeNodes = Array.isArray(nodes) ? nodes : [];
  const safeLinks = Array.isArray(links) ? links : [];

  const dataPreparerRef = useRef<CosmographDataPreparer>(
    getGlobalDataPreparer({
      clusteringMethod: config.clusteringMethod,
      centralityMetric: config.centralityMetric,
      clusterStrength: config.clusterStrength
    })
  );

  // When set, the next useMemo invocation will update the stored hash
  // but return the cached result — preventing a full re-sanitization.
  const skipNextRef = useRef(false);

  // PERFORMANCE FIX (GRAPH-67 + GRAPH-182): Content-based hashes computed directly
  // (no useMemo wrapper — hash functions are O(1) and avoid unstable array deps)
  const nodesHash = generateNodesHash(safeNodes);
  const linksHash = generateLinksHash(safeLinks);

  // Stable ref to source arrays for use inside useMemo without adding them as deps
  const safeNodesRef = useRef(safeNodes);
  const safeLinksRef = useRef(safeLinks);
  safeNodesRef.current = safeNodes;
  safeLinksRef.current = safeLinks;

  // Store previous result to return stable reference when content hasn't changed
  const prevResultRef = useRef<CosmographData>({ nodes: [], links: [] });
  const prevHashRef = useRef<string>('');

  const cosmographData = useMemo(() => {
    const currentHash = `${nodesHash}|${linksHash}|${config.clusteringMethod}|${config.centralityMetric}|${config.clusterStrength}`;

    if (currentHash === prevHashRef.current && prevResultRef.current.nodes.length > 0) {
      return prevResultRef.current;
    }

    // PERF: After a successful incremental addPoints, React state changes
    // but Cosmograph already has the data. Accept the new hash without
    // re-sanitizing the full dataset.
    if (skipNextRef.current && prevResultRef.current.nodes.length > 0) {
      skipNextRef.current = false;
      prevHashRef.current = currentHash;
      return prevResultRef.current;
    }

    const preparer = dataPreparerRef.current;
    preparer.reset();

    const currentNodes = safeNodesRef.current;
    const currentLinks = safeLinksRef.current;

    const nodeIdToIndex = new Map<string, number>();
    const nodeTypeIndexMap = new Map<string, number>();

    const transformedNodes = currentNodes.map((node, index) => {
      nodeIdToIndex.set(node.id, index);

      const nodeType = node.node_type || 'Unknown';
      if (!nodeTypeIndexMap.has(nodeType)) {
        nodeTypeIndexMap.set(nodeType, nodeTypeIndexMap.size);
      }

      return sanitizeNode(node, index, {
        clusteringMethod: config.clusteringMethod,
        centralityMetric: config.centralityMetric,
        clusterStrength: config.clusterStrength,
        nodeTypeIndexMap
      });
    });

    const transformedLinks = currentLinks
      .map(link => sanitizeLink(link, nodeIdToIndex))
      .filter((link): link is SanitizedLink => link !== null);

    const result: CosmographData = {
      nodes: transformedNodes,
      links: transformedLinks
    };

    if (transformedNodes.length > 0 && prevResultRef.current.nodes.length === 0) {
      console.log('[useCosmographDataTransform] Data ready:', transformedNodes.length, 'nodes,', transformedLinks.length, 'links');
    }

    prevHashRef.current = currentHash;
    prevResultRef.current = result;

    return result;
  }, [nodesHash, linksHash, config.clusteringMethod, config.centralityMetric, config.clusterStrength]);

  const markIncrementalSync = useCallback(() => {
    skipNextRef.current = true;
  }, []);

  return { ...cosmographData, markIncrementalSync };
};
