import { useMemo, useRef, useEffect } from 'react';
import { NodeColorManager, getGlobalColorManager, generateNodeTypeColor } from '../utils/NodeColorManager';
import { hexToRgba, interpolateColor } from '../utils/NodeColorManager';
import { TransformedGraphNode, TransformedGraphLink } from '../types/graph';
import { GraphConfig } from '../contexts/configTypes';

import { usePrecomputedLinkColors } from './usePrecomputedLinkColors';

// PERFORMANCE FIX: Module-level constant to avoid array recreation on each render
const COMMUNITY_COLORS = [
  '#e74c3c', '#3498db', '#2ecc71', '#f39c12', '#9b59b6',
  '#1abc9c', '#34495e', '#e67e22', '#95a5a6', '#d35400',
  '#16a085', '#27ae60', '#2980b9', '#8e44ad', '#2c3e50',
  '#f1c40f', '#e74c3c', '#ecf0f1', '#95a5a6', '#34495e'
] as const;

interface CosmographData {
  nodes: TransformedGraphNode[];
  links: TransformedGraphLink[];
}

interface VisualizationConfig {
  pointSizeRange: [number, number];
  linkWidthRange: [number, number];
  nodeColorConfig: {
    colorBy: string;
    strategy: string;
    colorMap: Record<string, string>;
    colorFn?: (value: number | string) => string;
  };
  linkWidthByFn?: (edgeType: string, linkIndex: number) => number;
  linkColorByFn?: (edgeType: string, linkIndex: number) => string;
}

interface UseCosmographVisualizationProps {
  config: GraphConfig;
  cosmographData: CosmographData | null;
  glowingNodes: Map<string, number>;
  /** Set of highlighted node IDs (from search results) - edges connecting these nodes will be highlighted */
  highlightedNodes?: Set<string> | string[];
}

/**
 * Hook that computes all visualization configuration for Cosmograph
 * including size ranges, colors, and dynamic functions for links and nodes
 */
export function useCosmographVisualization({
  config,
  cosmographData,
  glowingNodes,
  highlightedNodes
}: UseCosmographVisualizationProps): VisualizationConfig {
  
  // PERFORMANCE FIX: Use ref for glowingNodes to avoid function recreation
  const glowingNodesRef = useRef(glowingNodes);
  glowingNodesRef.current = glowingNodes;
  
  // Use ref for highlighted nodes to avoid function recreation on every highlight change
  const highlightedNodesRef = useRef<Set<string>>(new Set());
  // Convert array to Set if needed
  if (highlightedNodes) {
    highlightedNodesRef.current = Array.isArray(highlightedNodes) 
      ? new Set(highlightedNodes) 
      : highlightedNodes;
  } else {
    highlightedNodesRef.current = new Set();
  }
  
  // === POINT SIZE CONFIGURATION ===
  const pointSizeRange = useMemo(() => {
    const baseMin = config.minNodeSize || 2;
    const baseMax = config.maxNodeSize || 8;
    const multiplier = config.sizeMultiplier || 1;
    
    let adjustedMin: number;
    let adjustedMax: number;
    
    switch (config.sizeMapping) {
      case 'uniform':
        const uniformSize = (baseMin + baseMax) / 2;
        adjustedMin = uniformSize;
        adjustedMax = uniformSize + 0.1;
        break;
      
      case 'degree':
      case 'connections':
        adjustedMin = baseMin;
        adjustedMax = baseMax;
        break;
      
      case 'betweenness':
        adjustedMin = baseMin * 0.5;
        adjustedMax = baseMax * 2.0;
        break;
      
      case 'pagerank':
      case 'importance':
        adjustedMin = baseMin * 0.8;
        adjustedMax = baseMax * 1.2;
        break;
      
      case 'custom':
        adjustedMin = baseMin * 0.7;
        adjustedMax = baseMax * 1.5;
        break;
      
      default:
        adjustedMin = baseMin;
        adjustedMax = baseMax;
        break;
    }
    
    const finalRange: [number, number] = [adjustedMin * multiplier, adjustedMax * multiplier];
    return finalRange;
  }, [config.sizeMapping, config.minNodeSize, config.maxNodeSize, config.sizeMultiplier]);
  
  // === NODE COLOR CONFIGURATION ===
  // Cast colorScheme to the expected type for NodeColorManager
  type ColorScheme = 'by-type' | 'by-centrality' | 'by-pagerank' | 'by-degree' | 'by-betweenness' | 'by-eigenvector' | 'by-community' | 'by-temporal' | 'custom';
  const colorScheme = (config.colorScheme || 'by-type') as ColorScheme;
  
  const colorManagerRef = useRef<NodeColorManager>(getGlobalColorManager({
    scheme: colorScheme,
    gradientHighColor: config.gradientHighColor,
    gradientLowColor: config.gradientLowColor,
    nodeTypeColors: config.nodeTypeColors,
    normalizeMetrics: true
  }));
  
  useEffect(() => {
    colorManagerRef.current.updateConfig({
      scheme: colorScheme,
      gradientHighColor: config.gradientHighColor,
      gradientLowColor: config.gradientLowColor,
      nodeTypeColors: config.nodeTypeColors,
      normalizeMetrics: true
    });
  }, [colorScheme, config.gradientHighColor, config.gradientLowColor, config.nodeTypeColors]);
  
  useEffect(() => {
    if (cosmographData?.nodes) {
      colorManagerRef.current.setNodes(cosmographData.nodes);
    }
  }, [cosmographData?.nodes]);
  
  const nodeColorConfig = useMemo(() => {
    let colorByColumn = 'node_type';
    let useDirectColoring = false;
    
    switch (config.colorScheme) {
      case 'by-type':
      default:
        return {
          colorBy: 'node_type',
          strategy: 'map',
          colorMap: config.nodeTypeColors || {},
          colorFn: undefined
        };
      
      case 'by-centrality':
      case 'by-degree':
        colorByColumn = 'degree_centrality';
        useDirectColoring = true;
        break;
        
      case 'by-pagerank':
        colorByColumn = 'pagerank_centrality';
        useDirectColoring = true;
        break;
        
      case 'by-betweenness':
        colorByColumn = 'betweenness_centrality';
        useDirectColoring = true;
        break;
        
      case 'by-eigenvector':
        colorByColumn = 'eigenvector_centrality';
        useDirectColoring = true;
        break;
        
      case 'by-community':
        colorByColumn = 'cluster';
        useDirectColoring = true;
        break;
        
      case 'custom':
        colorByColumn = 'colorValue';
        useDirectColoring = true;
        break;
    }
    
    if (useDirectColoring) {
      return {
        colorBy: colorByColumn,
        strategy: 'direct',
        colorMap: {},
        colorFn: (value: number | string) => {
          const numValue = typeof value === 'number' ? value : parseFloat(String(value)) || 0;
          const highColor = config.gradientHighColor || '#FF6B6B';
          const lowColor = config.gradientLowColor || '#4ECDC4';
          
          if (config.colorScheme === 'by-community') {
            let hash = 0;
            const clusterStr = String(value);
            for (let i = 0; i < clusterStr.length; i++) {
              hash = ((hash << 5) - hash) + clusterStr.charCodeAt(i);
              hash = hash & hash;
            }
            const index = Math.abs(hash) % COMMUNITY_COLORS.length;
            return COMMUNITY_COLORS[index];
          }
          
          if (config.gradientMidColor) {
            if (numValue < 0.5) {
              return interpolateColor(lowColor, config.gradientMidColor, numValue * 2);
            } else {
              return interpolateColor(config.gradientMidColor, highColor, (numValue - 0.5) * 2);
            }
          }
          return interpolateColor(lowColor, highColor, numValue);
        }
      };
    }
    
    return {
      colorBy: 'node_type',
      strategy: 'map',
      colorMap: config.nodeTypeColors || {},
      colorFn: undefined
    };
  }, [config.colorScheme, config.nodeTypeColors, config.gradientHighColor, config.gradientLowColor, config.gradientMidColor]);
  
  // === LINK WIDTH CONFIGURATION ===
  const linkWidthByFn = useMemo(() => {
    if (config.linkWidthScheme === 'uniform') {
      return undefined;
    }
    
    const minWidth = config.linkWidthMin ?? 0.1;
    const maxWidth = config.linkWidthMax ?? 5;
    
    return (_edgeType: string, linkIndex: number) => {
      if (!cosmographData?.links || !cosmographData?.nodes) return minWidth;
      const link = cosmographData.links[linkIndex];
      if (!link) return minWidth;
      
      switch (config.linkWidthScheme) {
        case 'by-source-pagerank': {
          const sourceNode = cosmographData.nodes[link.sourceIndex];
          if (!sourceNode) return minWidth;
          const pagerank = sourceNode.pagerank_centrality || sourceNode.pagerank || 0;
          return minWidth + (pagerank * (maxWidth - minWidth));
        }
        
        case 'by-source-centrality': {
          const sourceNode = cosmographData.nodes[link.sourceIndex];
          if (!sourceNode) return minWidth;
          const centrality = sourceNode.degree_centrality || 0;
          return minWidth + (centrality * (maxWidth - minWidth));
        }
        
        case 'by-source-betweenness': {
          const sourceNode = cosmographData.nodes[link.sourceIndex];
          if (!sourceNode) return minWidth;
          const betweenness = sourceNode.betweenness_centrality || 0;
          return minWidth + (betweenness * (maxWidth - minWidth));
        }
        
        case 'by-weight': {
          const weight = link.weight || 1;
          const normalizedWeight = Math.min(weight / 10, 1);
          return minWidth + (normalizedWeight * (maxWidth - minWidth));
        }
        
        default:
          return minWidth;
      }
    };
  }, [config.linkWidthScheme, config.linkWidth, config.linkWidthMin, config.linkWidthMax]);
  
  const linkWidthRange = useMemo(() => {
    const baseValue = config.linkWidth || 2;
    
    switch (config.linkWidthScheme) {
      case 'uniform':
        return [baseValue, baseValue] as [number, number];
      
      case 'by-source-centrality':
      case 'by-source-pagerank':
        return [0.5, baseValue * 3] as [number, number];
      
      case 'by-source-betweenness':
        return [0.5, baseValue * 4] as [number, number];
      
      case 'by-weight':
        return [0.5, baseValue * 3] as [number, number];
      
      default:
        return [baseValue, baseValue] as [number, number];
    }
  }, [config.linkWidthScheme, config.linkWidth]);
  
  // === LINK COLOR CONFIGURATION ===
  
  // PERFORMANCE FIX: Pre-compute maxWeight once instead of for every link
  const maxLinkWeight = useMemo(() => {
    if (!cosmographData?.links || config.linkColorScheme !== 'by-weight') return 0;
    let max = 0;
    for (let i = 0; i < cosmographData.links.length; i++) {
      const w = cosmographData.links[i].weight || 0;
      if (w > max) max = w;
    }
    return max;
  }, [cosmographData?.links, config.linkColorScheme]);
  
  const linkColorByFn = useMemo(() => {
    // Note: We always provide a function now to support edge highlighting
    // The function will short-circuit to baseColor for non-highlighted edges
    
    return (edgeType: string, linkIndex: number) => {
      if (!cosmographData?.links || !cosmographData?.nodes) return config.linkColor || '#9CA3AF';
      const link = cosmographData.links[linkIndex];
      if (!link) return config.linkColor || '#9CA3AF';
      
      // Step 0: Check if this edge connects highlighted nodes (from search)
      const currentHighlightedNodes = highlightedNodesRef.current;
      if (currentHighlightedNodes.size > 0) {
        const sourceHighlighted = currentHighlightedNodes.has(link.source);
        const targetHighlighted = currentHighlightedNodes.has(link.target);
        
        // If both endpoints are highlighted, use bright highlight color
        if (sourceHighlighted && targetHighlighted) {
          return config.highlightedEdgeColor || '#FFD700'; // Gold for edges between highlighted nodes
        }
        
        // If only one endpoint is highlighted, use a dimmer version
        if (sourceHighlighted || targetHighlighted) {
          return config.partialHighlightedEdgeColor || hexToRgba('#FFD700', 0.5); // Semi-transparent gold
        }
        
        // If there are highlighted nodes but this edge isn't connected, dim it
        return hexToRgba(config.linkColor || '#9CA3AF', 0.15); // Very dim for non-highlighted edges
      }
      
      // Step 1: Determine base color (no highlighting active)
      let baseColor = config.linkColor || '#9CA3AF';
      
      switch (config.linkColorScheme) {
        case 'by-type': {
          const typeColors: Record<string, string> = {
            'relates_to': '#4ECDC4',
            'causes': '#F6AD55',
            'precedes': '#B794F6',
            'contains': '#90CDF4',
            'default': config.linkColor || '#9CA3AF'
          };
          baseColor = typeColors[edgeType] || (config.linkColor || '#9CA3AF');
          break;
        }
        case 'by-weight': {
          const weight = link.weight || 0;
          // PERFORMANCE FIX: Use pre-computed maxWeight instead of O(n) scan per link
          const ratio = maxLinkWeight > 0 ? weight / maxLinkWeight : 0;
          const r = Math.round(ratio * 255);
          const b = Math.round((1 - ratio) * 255);
          baseColor = `rgb(${r}, 0, ${b})`;
          break;
        }
        case 'by-source-node': {
          const sourceNode = cosmographData.nodes[link.sourceIndex];
          if (sourceNode) {
            // PERFORMANCE FIX: Read from ref to avoid dependency on glowingNodes
            const currentGlowing = glowingNodesRef.current;
            if (currentGlowing.size > 0 && currentGlowing.has(sourceNode.id)) {
              baseColor = config.nodeAccessHighlightColor || '#FFD700';
            } else {
              const nodeType = sourceNode.node_type;
              baseColor = config.nodeTypeColors?.[nodeType] || generateNodeTypeColor(nodeType, link.sourceIndex);
            }
          }
          break;
        }
        case 'gradient': {
          const sourceNode = cosmographData.nodes[link.sourceIndex];
          if (sourceNode) {
            const nodeType = sourceNode.node_type;
            baseColor = config.nodeTypeColors?.[nodeType] || generateNodeTypeColor(nodeType, link.sourceIndex);
          }
          break;
        }
        case 'by-community': {
          const sourceNode = cosmographData.nodes[link.sourceIndex];
          const targetNode = cosmographData.nodes[link.targetIndex];
          baseColor = sourceNode?.cluster === targetNode?.cluster ? 
            (config.linkColor || '#9CA3AF') : '#ff6b6b';
          break;
        }
        case 'by-distance':
          break;
      }
      
      // Step 2: Determine opacity
      let opacity = config.linkOpacity || 0.85;
      const minOpacity = config.linkOpacityMin ?? 0.1;
      const maxOpacity = config.linkOpacityMax ?? 1;
      
      switch (config.linkOpacityScheme) {
        case 'by-source-centrality': {
          const sourceNode = cosmographData.nodes[link.sourceIndex];
          if (!sourceNode) break;
          const centrality = sourceNode.degree_centrality || 0;
          opacity = minOpacity + (centrality * (maxOpacity - minOpacity));
          break;
        }
        case 'by-distance': {
          const weight = link.weight || 1;
          const normalizedDistance = Math.min(weight / 10, 1);
          opacity = maxOpacity - (normalizedDistance * (maxOpacity - minOpacity));
          break;
        }
        case 'uniform':
        default:
          opacity = config.linkOpacity || 0.85;
          break;
      }
      
      return hexToRgba(baseColor, opacity);
    };
  }, [
    config.linkColorScheme, 
    config.linkOpacityScheme, 
    config.linkColor, 
    config.linkOpacity,
    config.linkOpacityMin,
    config.linkOpacityMax,
    config.nodeTypeColors,
    // PERFORMANCE FIX: Removed glowingNodes from deps - now uses ref
    config.nodeAccessHighlightColor,
    maxLinkWeight // Pre-computed max weight for by-weight scheme
  ]);
  
  // PERFORMANCE FIX (GRAPH-66): Use pre-computed link colors instead of per-frame function
  // This eliminates 139K function calls per frame during pan/zoom
  const { linkColorByFn: precomputedLinkColorByFn } = usePrecomputedLinkColors({
    cosmographData,
    config: {
      linkColorScheme: config.linkColorScheme,
      linkOpacityScheme: config.linkOpacityScheme,
      linkColor: config.linkColor,
      linkOpacity: config.linkOpacity,
      linkOpacityMin: config.linkOpacityMin,
      linkOpacityMax: config.linkOpacityMax,
      nodeTypeColors: config.nodeTypeColors,
      nodeAccessHighlightColor: config.nodeAccessHighlightColor,
      highlightedEdgeColor: config.highlightedEdgeColor as string | undefined,
      partialHighlightedEdgeColor: config.partialHighlightedEdgeColor as string | undefined,
    },
    highlightedNodes: highlightedNodesRef.current,
    glowingNodes: glowingNodesRef.current
  });
  
  return {
    pointSizeRange,
    linkWidthRange,
    nodeColorConfig,
    linkWidthByFn,
    // Use pre-computed colors for better performance
    linkColorByFn: precomputedLinkColorByFn
  };
}
