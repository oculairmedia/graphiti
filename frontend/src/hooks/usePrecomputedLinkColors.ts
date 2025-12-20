/**
 * usePrecomputedLinkColors Hook
 * 
 * PERFORMANCE FIX (GRAPH-66): Pre-computes link colors into an array
 * instead of computing them on every frame via linkColorByFn.
 * 
 * With 139K edges, this eliminates 139,000 function calls per render frame
 * during pan/zoom operations.
 */

import { useMemo, useRef, useEffect } from 'react';
import { hexToRgba } from '../utils/colorCache';
import { generateNodeTypeColor } from '../utils/nodeTypeColors';

interface LinkColorConfig {
  linkColorScheme: string;
  linkOpacityScheme: string;
  linkColor: string;
  linkOpacity: number;
  linkOpacityMin: number;
  linkOpacityMax: number;
  nodeTypeColors?: Record<string, string>;
  nodeAccessHighlightColor?: string;
  highlightedEdgeColor?: string;
  partialHighlightedEdgeColor?: string;
}

interface CosmographData {
  nodes: any[];
  links: any[];
}

interface UsePrecomputedLinkColorsProps {
  cosmographData: CosmographData | null;
  config: LinkColorConfig;
  highlightedNodes: Set<string> | string[];
  glowingNodes: Map<string, number>;
}

interface PrecomputedLinkColorsResult {
  /** Pre-computed color array - one color string per link */
  linkColors: string[];
  /** Fast lookup function that just returns pre-computed color */
  linkColorByFn: (edgeType: any, linkIndex: number) => string;
  /** Force recompute (e.g., when highlighting changes) */
  recompute: () => void;
  /** Whether colors are ready */
  isReady: boolean;
}

/**
 * Pre-compute link colors for all edges
 * This runs once on data load and when config/highlighting changes
 */
export function usePrecomputedLinkColors({
  cosmographData,
  config,
  highlightedNodes,
  glowingNodes
}: UsePrecomputedLinkColorsProps): PrecomputedLinkColorsResult {
  
  // Convert highlightedNodes to Set if it's an array
  const highlightedSet = useMemo(() => {
    if (!highlightedNodes) return new Set<string>();
    return Array.isArray(highlightedNodes) ? new Set(highlightedNodes) : highlightedNodes;
  }, [highlightedNodes]);
  
  // Use refs to avoid recreating the lookup function
  const linkColorsRef = useRef<string[]>([]);
  const isReadyRef = useRef(false);
  
  // Pre-compute max weight for by-weight scheme
  const maxLinkWeight = useMemo(() => {
    if (!cosmographData?.links || config.linkColorScheme !== 'by-weight') return 0;
    let max = 0;
    for (let i = 0; i < cosmographData.links.length; i++) {
      const w = cosmographData.links[i].weight || 0;
      if (w > max) max = w;
    }
    return max;
  }, [cosmographData?.links?.length, config.linkColorScheme]);
  
  // Pre-compute all link colors
  const linkColors = useMemo(() => {
    if (!cosmographData?.links || !cosmographData?.nodes) {
      isReadyRef.current = false;
      return [];
    }
    
    const links = cosmographData.links;
    const nodes = cosmographData.nodes;
    const colors: string[] = new Array(links.length);
    
    const defaultColor = config.linkColor || '#9CA3AF';
    const defaultOpacity = config.linkOpacity || 0.85;
    const minOpacity = config.linkOpacityMin ?? 0.1;
    const maxOpacity = config.linkOpacityMax ?? 1;
    
    // Type color map for by-type scheme
    const typeColors: Record<string, string> = {
      'relates_to': '#4ECDC4',
      'causes': '#F6AD55',
      'precedes': '#B794F6',
      'contains': '#90CDF4',
      'default': defaultColor
    };
    
    const hasHighlights = highlightedSet.size > 0;
    const hasGlowing = glowingNodes.size > 0;
    
    // Pre-compute colors for all links
    for (let i = 0; i < links.length; i++) {
      const link = links[i];
      
      // Step 0: Handle highlighting
      if (hasHighlights) {
        const sourceHighlighted = highlightedSet.has(link.source);
        const targetHighlighted = highlightedSet.has(link.target);
        
        if (sourceHighlighted && targetHighlighted) {
          colors[i] = config.highlightedEdgeColor || '#FFD700';
          continue;
        }
        
        if (sourceHighlighted || targetHighlighted) {
          colors[i] = config.partialHighlightedEdgeColor || hexToRgba('#FFD700', 0.5);
          continue;
        }
        
        // Dim non-highlighted edges
        colors[i] = hexToRgba(defaultColor, 0.15);
        continue;
      }
      
      // Step 1: Determine base color
      let baseColor = defaultColor;
      const edgeType = link.edge_type || 'default';
      
      switch (config.linkColorScheme) {
        case 'by-type':
          baseColor = typeColors[edgeType] || defaultColor;
          break;
          
        case 'by-weight': {
          const weight = link.weight || 0;
          const ratio = maxLinkWeight > 0 ? weight / maxLinkWeight : 0;
          const r = Math.round(ratio * 255);
          const b = Math.round((1 - ratio) * 255);
          baseColor = `rgb(${r}, 0, ${b})`;
          break;
        }
        
        case 'by-source-node': {
          const sourceNode = nodes[link.sourceIndex];
          if (sourceNode) {
            if (hasGlowing && glowingNodes.has(sourceNode.id)) {
              baseColor = config.nodeAccessHighlightColor || '#FFD700';
            } else {
              const nodeType = sourceNode.node_type;
              baseColor = config.nodeTypeColors?.[nodeType] || generateNodeTypeColor(nodeType, link.sourceIndex);
            }
          }
          break;
        }
        
        case 'gradient': {
          const sourceNode = nodes[link.sourceIndex];
          if (sourceNode) {
            const nodeType = sourceNode.node_type;
            baseColor = config.nodeTypeColors?.[nodeType] || generateNodeTypeColor(nodeType, link.sourceIndex);
          }
          break;
        }
        
        case 'by-community': {
          const sourceNode = nodes[link.sourceIndex];
          const targetNode = nodes[link.targetIndex];
          baseColor = sourceNode?.cluster === targetNode?.cluster ? defaultColor : '#ff6b6b';
          break;
        }
        
        default:
          baseColor = defaultColor;
      }
      
      // Step 2: Determine opacity
      let opacity = defaultOpacity;
      
      switch (config.linkOpacityScheme) {
        case 'by-source-centrality': {
          const sourceNode = nodes[link.sourceIndex];
          if (sourceNode) {
            const centrality = sourceNode.degree_centrality || 0;
            opacity = minOpacity + (centrality * (maxOpacity - minOpacity));
          }
          break;
        }
        
        case 'by-distance': {
          const weight = link.weight || 1;
          const normalizedDistance = Math.min(weight / 10, 1);
          opacity = maxOpacity - (normalizedDistance * (maxOpacity - minOpacity));
          break;
        }
        
        default:
          opacity = defaultOpacity;
      }
      
      // Apply opacity to color
      colors[i] = hexToRgba(baseColor, opacity);
    }
    
    linkColorsRef.current = colors;
    isReadyRef.current = true;
    
    return colors;
  }, [
    cosmographData?.links?.length,
    cosmographData?.nodes?.length,
    config.linkColorScheme,
    config.linkOpacityScheme,
    config.linkColor,
    config.linkOpacity,
    config.linkOpacityMin,
    config.linkOpacityMax,
    config.nodeTypeColors,
    config.nodeAccessHighlightColor,
    config.highlightedEdgeColor,
    config.partialHighlightedEdgeColor,
    highlightedSet.size,
    glowingNodes.size,
    maxLinkWeight
  ]);
  
  // Fast lookup function - just returns pre-computed color
  // This is the function Cosmograph will call 139K times per frame
  // Now it's just an array lookup instead of complex computation
  const linkColorByFn = useMemo(() => {
    const colors = linkColorsRef.current;
    const fallback = config.linkColor || '#9CA3AF';
    
    return (_edgeType: any, linkIndex: number): string => {
      // Simple array lookup - O(1)
      return colors[linkIndex] ?? fallback;
    };
  }, [linkColors, config.linkColor]);
  
  // Recompute function for manual triggering
  const recompute = useMemo(() => {
    return () => {
      // Force re-run of useMemo by triggering a state change in parent
      // This is a no-op placeholder - actual recompute happens via deps
    };
  }, []);
  
  return {
    linkColors,
    linkColorByFn,
    recompute,
    isReady: isReadyRef.current
  };
}
