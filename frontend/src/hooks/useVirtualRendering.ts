/**
 * Virtual rendering hook for efficient large graph visualization
 * Only renders nodes/edges visible in the viewport
 */

import { useEffect, useMemo, useRef, useState, useCallback } from 'react';
import { GraphNode } from '../api/types';
import { GraphLink } from '../types/graph';
import { SpatialIndex } from '../utils/spatialIndex';
import { useGraphConfig } from '../contexts/GraphConfigProvider';
import { logger } from '../utils/logger';

interface ViewportBounds {
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
  zoom: number;
}

interface VirtualRenderingOptions {
  enableVirtualization?: boolean;
  virtualThreshold?: number; // Node count threshold to enable virtualization
  overscan?: number; // Render nodes slightly outside viewport
  updateDebounce?: number; // Debounce viewport updates
  lod?: {
    enabled: boolean;
    levels: Array<{
      minZoom: number;
      maxZoom: number;
      nodeDetail: 'full' | 'simplified' | 'point';
      edgeDetail: 'full' | 'simplified' | 'hidden';
    }>;
  };
}

const DEFAULT_OPTIONS: VirtualRenderingOptions = {
  enableVirtualization: true,
  virtualThreshold: 5000,
  overscan: 1.2, // Render 20% outside viewport
  updateDebounce: 50,
  lod: {
    enabled: true,
    levels: [
      { minZoom: 0, maxZoom: 0.3, nodeDetail: 'point', edgeDetail: 'hidden' },
      { minZoom: 0.3, maxZoom: 0.7, nodeDetail: 'simplified', edgeDetail: 'simplified' },
      { minZoom: 0.7, maxZoom: 10, nodeDetail: 'full', edgeDetail: 'full' }
    ]
  }
};

export function useVirtualRendering(
  nodes: GraphNode[],
  links: GraphLink[],
  cosmographRef: React.RefObject<any>,
  options: VirtualRenderingOptions = {}
) {
  const opts = { ...DEFAULT_OPTIONS, ...options };
  const { config } = useGraphConfig();
  
  const [visibleNodes, setVisibleNodes] = useState<GraphNode[]>(nodes);
  const [visibleLinks, setVisibleLinks] = useState<GraphLink[]>(links);
  const [viewport, setViewport] = useState<ViewportBounds | null>(null);
  const [renderStats, setRenderStats] = useState({
    totalNodes: 0,
    visibleNodes: 0,
    totalEdges: 0,
    visibleEdges: 0,
    culledNodes: 0,
    culledEdges: 0,
    lodLevel: 'full'
  });

  const spatialIndexRef = useRef<SpatialIndex>(new SpatialIndex());
  const updateTimerRef = useRef<NodeJS.Timeout | null>(null);
  const nodePositionsRef = useRef<Map<string, { x: number; y: number }>>(new Map());
  const lastUpdateRef = useRef<number>(0);

  // Determine if virtualization should be enabled
  const shouldVirtualize = useMemo(() => {
    return opts.enableVirtualization && nodes.length > opts.virtualThreshold;
  }, [opts.enableVirtualization, opts.virtualThreshold, nodes.length]);

  // Build spatial index when nodes change
  useEffect(() => {
    if (!shouldVirtualize) {
      setVisibleNodes(nodes);
      setVisibleLinks(links);
      return;
    }

    // Get initial positions from Cosmograph if available
    if (cosmographRef.current?.getNodePositionsMap) {
      try {
        const positions = cosmographRef.current.getNodePositionsMap();
        if (positions && positions.size > 0) {
          nodePositionsRef.current = positions;
          spatialIndexRef.current.build(nodes, positions);
          logger.log('[VirtualRendering] Spatial index built with', nodes.length, 'nodes');
        }
      } catch (error) {
        logger.error('[VirtualRendering] Failed to get node positions:', error);
      }
    }

    // Set initial visible nodes (all for now, will be culled on first viewport update)
    setVisibleNodes(nodes);
    setVisibleLinks(links);
  }, [nodes, links, shouldVirtualize, cosmographRef]);

  // Update viewport bounds
  const updateViewport = useCallback(() => {
    if (!cosmographRef.current || !shouldVirtualize) return;

    try {
      // Get viewport information from Cosmograph
      const zoom = cosmographRef.current.getZoomLevel?.() || 1;
      const canvas = cosmographRef.current._canvasElement;
      
      if (!canvas) return;

      const rect = canvas.getBoundingClientRect();
      const centerX = rect.width / 2;
      const centerY = rect.height / 2;
      
      // Calculate viewport bounds with overscan
      const viewportSize = Math.max(rect.width, rect.height) / zoom;
      const overscanSize = viewportSize * opts.overscan!;
      
      const newViewport: ViewportBounds = {
        minX: centerX - overscanSize / 2,
        maxX: centerX + overscanSize / 2,
        minY: centerY - overscanSize / 2,
        maxY: centerY + overscanSize / 2,
        zoom
      };

      setViewport(newViewport);

      // Update node positions if available
      if (cosmographRef.current.getNodePositionsMap) {
        const positions = cosmographRef.current.getNodePositionsMap();
        if (positions && positions.size > 0) {
          nodePositionsRef.current = positions;
          
          // Rebuild spatial index periodically (every 5 seconds)
          const now = Date.now();
          if (now - lastUpdateRef.current > 5000) {
            spatialIndexRef.current.build(nodes, positions);
            lastUpdateRef.current = now;
          }
        }
      }

      // Perform viewport culling
      performCulling(newViewport);
    } catch (error) {
      logger.error('[VirtualRendering] Failed to update viewport:', error);
    }
  }, [nodes, shouldVirtualize, opts.overscan]);

  // Perform viewport culling
  const performCulling = useCallback((viewport: ViewportBounds) => {
    if (!shouldVirtualize) return;

    const startTime = performance.now();

    // Query spatial index for visible nodes
    const visibleNodeSet = new Set<string>();
    const culledNodes = spatialIndexRef.current.query({
      minX: viewport.minX,
      maxX: viewport.maxX,
      minY: viewport.minY,
      maxY: viewport.maxY
    });

    culledNodes.forEach(node => visibleNodeSet.add(node.id));

    // Determine LOD level based on zoom
    let lodLevel = 'full';
    if (opts.lod?.enabled) {
      const level = opts.lod.levels.find(l => 
        viewport.zoom >= l.minZoom && viewport.zoom < l.maxZoom
      );
      if (level) {
        lodLevel = level.nodeDetail;
      }
    }

    // Apply LOD to nodes
    let processedNodes = culledNodes;
    if (lodLevel === 'simplified') {
      // Simplify node data
      processedNodes = culledNodes.map(node => ({
        ...node,
        properties: {} // Remove properties for simplified view
      }));
    } else if (lodLevel === 'point') {
      // Ultra-simplified - just positions
      processedNodes = culledNodes.map(node => ({
        id: node.id,
        label: '',
        node_type: node.node_type,
        properties: {}
      } as GraphNode));
    }

    // Filter edges to only include those with both endpoints visible
    const visibleEdges = links.filter(edge => 
      visibleNodeSet.has(edge.source) && visibleNodeSet.has(edge.target)
    );

    // Apply LOD to edges
    let processedEdges = visibleEdges;
    if (lodLevel === 'point' || (lodLevel === 'simplified' && viewport.zoom < 0.5)) {
      processedEdges = []; // Hide edges at low zoom
    }

    const cullingTime = performance.now() - startTime;

    // Update stats
    setRenderStats({
      totalNodes: nodes.length,
      visibleNodes: processedNodes.length,
      totalEdges: links.length,
      visibleEdges: processedEdges.length,
      culledNodes: nodes.length - processedNodes.length,
      culledEdges: links.length - processedEdges.length,
      lodLevel
    });

    // Only update if there's a significant change
    if (Math.abs(processedNodes.length - visibleNodes.length) > 10 ||
        Math.abs(processedEdges.length - visibleLinks.length) > 20) {
      setVisibleNodes(processedNodes);
      setVisibleLinks(processedEdges);
      
      logger.log(`[VirtualRendering] Culling completed in ${cullingTime.toFixed(2)}ms:`, {
        visible: processedNodes.length,
        culled: nodes.length - processedNodes.length,
        edges: processedEdges.length,
        lod: lodLevel
      });
    }
  }, [nodes, links, visibleNodes.length, visibleLinks.length, shouldVirtualize, opts.lod]);

  // Set up viewport monitoring
  useEffect(() => {
    if (!cosmographRef.current || !shouldVirtualize) return;

    const handleViewportChange = () => {
      // Debounce viewport updates
      if (updateTimerRef.current) {
        clearTimeout(updateTimerRef.current);
      }
      
      updateTimerRef.current = setTimeout(() => {
        updateViewport();
      }, opts.updateDebounce);
    };

    // Listen to Cosmograph events
    const cosmograph = cosmographRef.current;
    
    // Initial viewport update
    handleViewportChange();

    // Set up event listeners (these would need to be implemented in Cosmograph)
    // For now, we'll use a polling approach
    const intervalId = setInterval(handleViewportChange, 100);

    return () => {
      clearInterval(intervalId);
      if (updateTimerRef.current) {
        clearTimeout(updateTimerRef.current);
      }
    };
  }, [cosmographRef, shouldVirtualize, updateViewport, opts.updateDebounce]);

  // Return virtualized or original data
  return {
    nodes: shouldVirtualize ? visibleNodes : nodes,
    links: shouldVirtualize ? visibleLinks : links,
    isVirtualized: shouldVirtualize,
    viewport,
    stats: renderStats,
    // Utility functions
    queryVisibleNodes: useCallback((bounds: ViewportBounds) => {
      return spatialIndexRef.current.query(bounds);
    }, []),
    queryNearestNodes: useCallback((x: number, y: number, k: number) => {
      return spatialIndexRef.current.knn(x, y, k);
    }, []),
    forceUpdate: updateViewport
  };
}