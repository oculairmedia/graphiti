/**
 * Hook for virtual rendering with spatial indexing
 * Only renders nodes/links visible in viewport for performance
 */

import { useState, useCallback, useEffect, useRef, useMemo } from 'react';
import { GraphNode } from '../../../api/types';
import { GraphLink } from '../../../types/graph';
import { SpatialIndex, Bounds, IndexedNode } from '../utils/spatialIndex';
import { debounceWithCleanup, throttleWithCleanup } from '../utils/memoryUtils';
import { logger } from '../../../utils/logger';

interface UseVirtualRenderingOptions {
  enabled?: boolean;
  overscan?: number;
  updateDebounce?: number;
  levelOfDetail?: boolean;
  maxVisibleNodes?: number;
  maxVisibleLinks?: number;
}

interface UseVirtualRenderingReturn {
  visibleNodes: IndexedNode[];
  visibleLinks: GraphLink[];
  viewport: Bounds;
  totalNodes: number;
  totalLinks: number;
  culledNodes: number;
  culledLinks: number;
  updateViewport: (bounds: Bounds) => void;
  updateNodePositions: (positions: Map<string, { x: number; y: number }>) => void;
  forceUpdate: () => void;
  getNodeLOD: (node: IndexedNode) => 'high' | 'medium' | 'low';
}

/**
 * Hook for virtual rendering with spatial indexing
 */
export function useVirtualRendering(
  nodes: GraphNode[],
  links: GraphLink[],
  options: UseVirtualRenderingOptions = {}
): UseVirtualRenderingReturn {
  const {
    enabled = true,
    overscan = 1.2,
    updateDebounce = 16,
    levelOfDetail = true,
    maxVisibleNodes = 5000,
    maxVisibleLinks = 10000
  } = options;

  // State
  const [viewport, setViewport] = useState<Bounds>({
    minX: -1000,
    minY: -1000,
    maxX: 1000,
    maxY: 1000
  });
  
  const [visibleNodes, setVisibleNodes] = useState<IndexedNode[]>([]);
  const [visibleLinks, setVisibleLinks] = useState<GraphLink[]>([]);
  const [culledNodes, setCulledNodes] = useState(0);
  const [culledLinks, setCulledLinks] = useState(0);

  // Refs
  const spatialIndex = useRef(new SpatialIndex());
  const nodePositions = useRef<Map<string, { x: number; y: number }>>(new Map());
  const linkIndex = useRef<Map<string, GraphLink[]>>(new Map());
  const lastUpdateTime = useRef(0);
  const updateCounter = useRef(0);

  // Create indexed nodes with positions
  const indexedNodes = useMemo(() => {
    const indexed: IndexedNode[] = [];
    
    for (const node of nodes) {
      const pos = nodePositions.current.get(node.id);
      if (pos) {
        indexed.push({
          ...node,
          x: pos.x,
          y: pos.y
        });
      }
    }
    
    return indexed;
  }, [nodes, nodePositions.current.size]); // Update when positions change

  // Build link index for fast lookup
  useEffect(() => {
    const index = new Map<string, GraphLink[]>();
    
    for (const link of links) {
      // Index by source
      if (!index.has(link.source)) {
        index.set(link.source, []);
      }
      index.get(link.source)!.push(link);
      
      // Index by target
      if (!index.has(link.target)) {
        index.set(link.target, []);
      }
      index.get(link.target)!.push(link);
    }
    
    linkIndex.current = index;
  }, [links]);

  // Rebuild spatial index when nodes change
  useEffect(() => {
    if (!enabled || indexedNodes.length === 0) return;
    
    const startTime = performance.now();
    spatialIndex.current.build(indexedNodes);
    const buildTime = performance.now() - startTime;
    
    logger.log('useVirtualRendering: Spatial index built', {
      nodes: indexedNodes.length,
      time: `${buildTime.toFixed(2)}ms`,
      stats: spatialIndex.current.getStats()
    });
  }, [enabled, indexedNodes]);

  // Calculate visible elements
  const calculateVisible = useCallback((viewportBounds: Bounds) => {
    if (!enabled) {
      setVisibleNodes(indexedNodes);
      setVisibleLinks(links);
      setCulledNodes(0);
      setCulledLinks(0);
      return;
    }

    const startTime = performance.now();
    
    // Apply overscan to viewport
    const width = viewportBounds.maxX - viewportBounds.minX;
    const height = viewportBounds.maxY - viewportBounds.minY;
    const overscanX = (width * (overscan - 1)) / 2;
    const overscanY = (height * (overscan - 1)) / 2;
    
    const expandedBounds: Bounds = {
      minX: viewportBounds.minX - overscanX,
      minY: viewportBounds.minY - overscanY,
      maxX: viewportBounds.maxX + overscanX,
      maxY: viewportBounds.maxY + overscanY
    };
    
    // Query spatial index for visible nodes
    let visibleNodeList = spatialIndex.current.queryViewport(expandedBounds);
    
    // Apply max visible nodes limit
    if (visibleNodeList.length > maxVisibleNodes) {
      // Sort by distance from viewport center and take closest
      const centerX = (viewportBounds.minX + viewportBounds.maxX) / 2;
      const centerY = (viewportBounds.minY + viewportBounds.maxY) / 2;
      
      visibleNodeList.sort((a, b) => {
        const distA = Math.pow(a.x - centerX, 2) + Math.pow(a.y - centerY, 2);
        const distB = Math.pow(b.x - centerX, 2) + Math.pow(b.y - centerY, 2);
        return distA - distB;
      });
      
      visibleNodeList = visibleNodeList.slice(0, maxVisibleNodes);
    }
    
    // Create set of visible node IDs for link filtering
    const visibleNodeIds = new Set(visibleNodeList.map(n => n.id));
    
    // Find visible links (both endpoints must be visible)
    const visibleLinkList: GraphLink[] = [];
    const processedLinks = new Set<string>();
    
    for (const node of visibleNodeList) {
      const connectedLinks = linkIndex.current.get(node.id) || [];
      
      for (const link of connectedLinks) {
        const linkKey = `${link.source}-${link.target}`;
        
        if (!processedLinks.has(linkKey)) {
          processedLinks.add(linkKey);
          
          if (visibleNodeIds.has(link.source) && visibleNodeIds.has(link.target)) {
            visibleLinkList.push(link);
            
            if (visibleLinkList.length >= maxVisibleLinks) {
              break;
            }
          }
        }
      }
      
      if (visibleLinkList.length >= maxVisibleLinks) {
        break;
      }
    }
    
    const queryTime = performance.now() - startTime;
    
    // Update state
    setVisibleNodes(visibleNodeList);
    setVisibleLinks(visibleLinkList);
    setCulledNodes(indexedNodes.length - visibleNodeList.length);
    setCulledLinks(links.length - visibleLinkList.length);
    
    // Log performance
    if (updateCounter.current % 60 === 0) {
      logger.debug('useVirtualRendering: Viewport update', {
        visible: {
          nodes: visibleNodeList.length,
          links: visibleLinkList.length
        },
        culled: {
          nodes: indexedNodes.length - visibleNodeList.length,
          links: links.length - visibleLinkList.length
        },
        time: `${queryTime.toFixed(2)}ms`
      });
    }
    
    updateCounter.current++;
  }, [enabled, indexedNodes, links, overscan, maxVisibleNodes, maxVisibleLinks]);

  // Debounced viewport update
  const [updateViewportDebounced, cleanupViewportDebounce] = debounceWithCleanup(
    (bounds: Bounds) => {
      setViewport(bounds);
      calculateVisible(bounds);
    },
    updateDebounce
  );

  // Cleanup debounce on unmount
  useEffect(() => {
    return cleanupViewportDebounce;
  }, [cleanupViewportDebounce]);

  // Update viewport
  const updateViewport = useCallback((bounds: Bounds) => {
    updateViewportDebounced(bounds);
  }, [updateViewportDebounced]);

  // Update node positions
  const updateNodePositions = useCallback((positions: Map<string, { x: number; y: number }>) => {
    nodePositions.current = new Map(positions);
    
    // Rebuild indexed nodes
    const newIndexedNodes: IndexedNode[] = [];
    for (const node of nodes) {
      const pos = positions.get(node.id);
      if (pos) {
        newIndexedNodes.push({
          ...node,
          x: pos.x,
          y: pos.y
        });
      }
    }
    
    // Rebuild spatial index
    if (newIndexedNodes.length > 0) {
      spatialIndex.current.build(newIndexedNodes);
      calculateVisible(viewport);
    }
  }, [nodes, viewport, calculateVisible]);

  // Force update
  const forceUpdate = useCallback(() => {
    calculateVisible(viewport);
  }, [viewport, calculateVisible]);

  // Get level of detail for a node
  const getNodeLOD = useCallback((node: IndexedNode): 'high' | 'medium' | 'low' => {
    if (!levelOfDetail) return 'high';
    
    const centerX = (viewport.minX + viewport.maxX) / 2;
    const centerY = (viewport.minY + viewport.maxY) / 2;
    const viewportSize = Math.max(
      viewport.maxX - viewport.minX,
      viewport.maxY - viewport.minY
    );
    
    const distance = Math.sqrt(
      Math.pow(node.x - centerX, 2) + 
      Math.pow(node.y - centerY, 2)
    );
    
    const relativeDistance = distance / viewportSize;
    
    if (relativeDistance < 0.2) return 'high';
    if (relativeDistance < 0.5) return 'medium';
    return 'low';
  }, [viewport, levelOfDetail]);

  // Initial calculation
  useEffect(() => {
    calculateVisible(viewport);
  }, []);

  return {
    visibleNodes,
    visibleLinks,
    viewport,
    totalNodes: indexedNodes.length,
    totalLinks: links.length,
    culledNodes,
    culledLinks,
    updateViewport,
    updateNodePositions,
    forceUpdate,
    getNodeLOD
  };
}

/**
 * Hook for dynamic level of detail
 */
export function useLevelOfDetail(
  viewport: Bounds,
  zoomLevel: number
): {
  nodeDetail: 'full' | 'simplified' | 'dot';
  linkDetail: 'full' | 'simplified' | 'hidden';
  labelVisibility: 'all' | 'selected' | 'none';
  shouldRenderShadows: boolean;
  shouldRenderGlow: boolean;
} {
  return useMemo(() => {
    // Determine detail levels based on zoom
    let nodeDetail: 'full' | 'simplified' | 'dot' = 'full';
    let linkDetail: 'full' | 'simplified' | 'hidden' = 'full';
    let labelVisibility: 'all' | 'selected' | 'none' = 'all';
    let shouldRenderShadows = true;
    let shouldRenderGlow = true;
    
    if (zoomLevel < 0.1) {
      // Very zoomed out
      nodeDetail = 'dot';
      linkDetail = 'hidden';
      labelVisibility = 'none';
      shouldRenderShadows = false;
      shouldRenderGlow = false;
    } else if (zoomLevel < 0.3) {
      // Zoomed out
      nodeDetail = 'simplified';
      linkDetail = 'simplified';
      labelVisibility = 'selected';
      shouldRenderShadows = false;
      shouldRenderGlow = false;
    } else if (zoomLevel < 0.6) {
      // Medium zoom
      nodeDetail = 'simplified';
      linkDetail = 'full';
      labelVisibility = 'selected';
      shouldRenderShadows = false;
      shouldRenderGlow = true;
    } else {
      // Zoomed in
      nodeDetail = 'full';
      linkDetail = 'full';
      labelVisibility = 'all';
      shouldRenderShadows = true;
      shouldRenderGlow = true;
    }
    
    return {
      nodeDetail,
      linkDetail,
      labelVisibility,
      shouldRenderShadows,
      shouldRenderGlow
    };
  }, [zoomLevel]);
}

export default useVirtualRendering;