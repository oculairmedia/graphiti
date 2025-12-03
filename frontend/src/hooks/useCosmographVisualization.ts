import { useMemo, useRef, useEffect } from 'react';
import { NodeColorManager, getGlobalColorManager } from '../utils/NodeColorManager';
import { hexToRgba, interpolateColor } from '../utils/colorCache';
import { generateNodeTypeColor } from '../utils/nodeTypeColors';

// GraphConfig type - we'll use any for now since it's dynamically typed
type GraphConfig = any;

// PERFORMANCE FIX: Module-level constant to avoid array recreation on each render
const COMMUNITY_COLORS = [
  '#e74c3c', '#3498db', '#2ecc71', '#f39c12', '#9b59b6',
  '#1abc9c', '#34495e', '#e67e22', '#95a5a6', '#d35400',
  '#16a085', '#27ae60', '#2980b9', '#8e44ad', '#2c3e50',
  '#f1c40f', '#e74c3c', '#ecf0f1', '#95a5a6', '#34495e'
] as const;

interface CosmographData {
  nodes: any[];
  links: any[];
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
  linkWidthByFn?: (edgeType: any, linkIndex: number) => number;
  linkColorByFn?: (edgeType: any, linkIndex: number) => string;
}

interface UseCosmographVisualizationProps {
  config: GraphConfig;
  cosmographData: CosmographData | null;
  glowingNodes: Map<string, number>;
}

/**
 * Hook that computes all visualization configuration for Cosmograph
 * including size ranges, colors, and dynamic functions for links and nodes
 */
export function useCosmographVisualization({
  config,
  cosmographData,
  glowingNodes
}: UseCosmographVisualizationProps): VisualizationConfig {
  
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
  const colorManagerRef = useRef<NodeColorManager>(getGlobalColorManager({
    scheme: config.colorScheme || 'by-type',
    gradientHighColor: config.gradientHighColor,
    gradientLowColor: config.gradientLowColor,
    nodeTypeColors: config.nodeTypeColors,
    normalizeMetrics: true
  }));
  
  useEffect(() => {
    colorManagerRef.current.updateConfig({
      scheme: config.colorScheme || 'by-type',
      gradientHighColor: config.gradientHighColor,
      gradientLowColor: config.gradientLowColor,
      nodeTypeColors: config.nodeTypeColors,
      normalizeMetrics: true
    });
  }, [config.colorScheme, config.gradientHighColor, config.gradientLowColor, config.nodeTypeColors]);
  
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
    
    return (edgeType: any, linkIndex: number) => {
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
  const linkColorByFn = useMemo(() => {
    if (config.linkColorScheme === 'uniform' && config.linkOpacityScheme === 'uniform') {
      return undefined;
    }
    
    return (edgeType: any, linkIndex: number) => {
      if (!cosmographData?.links || !cosmographData?.nodes) return config.linkColor || '#9CA3AF';
      const link = cosmographData.links[linkIndex];
      if (!link) return config.linkColor || '#9CA3AF';
      
      // Step 1: Determine base color
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
          const maxWeight = Math.max(...cosmographData.links.map(l => l.weight || 0));
          const ratio = maxWeight > 0 ? weight / maxWeight : 0;
          const r = Math.round(ratio * 255);
          const b = Math.round((1 - ratio) * 255);
          baseColor = `rgb(${r}, 0, ${b})`;
          break;
        }
        case 'by-source-node': {
          const sourceNode = cosmographData.nodes[link.sourceIndex];
          if (sourceNode) {
            if (glowingNodes.size > 0 && glowingNodes.has(sourceNode.id)) {
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
    glowingNodes,
    config.nodeAccessHighlightColor
  ]);
  
  return {
    pointSizeRange,
    linkWidthRange,
    nodeColorConfig,
    linkWidthByFn,
    linkColorByFn
  };
}
