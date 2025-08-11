import React, { useState, useCallback, useMemo, useEffect } from 'react';
import { GraphNode, GraphEdge } from '../../../api/types';

type ColorScheme = 'type' | 'centrality' | 'temporal' | 'community' | 'custom' | 'gradient' | 'categorical';
type SizeStrategy = 'uniform' | 'degree' | 'centrality' | 'pagerank' | 'temporal' | 'custom';
type ShapeStrategy = 'circle' | 'square' | 'triangle' | 'diamond' | 'hexagon' | 'star' | 'custom';

interface ColorConfig {
  scheme: ColorScheme;
  palette?: string[];
  gradientStart?: string;
  gradientEnd?: string;
  opacity?: number;
  customColorFn?: (node: GraphNode) => string;
}

interface SizeConfig {
  strategy: SizeStrategy;
  minSize?: number;
  maxSize?: number;
  scaleFactor?: number;
  customSizeFn?: (node: GraphNode) => number;
}

interface ShapeConfig {
  strategy: ShapeStrategy;
  customShapeFn?: (node: GraphNode) => string;
}

interface EdgeStyleConfig {
  color?: string;
  colorByType?: boolean;
  width?: number;
  widthByWeight?: boolean;
  opacity?: number;
  curveStyle?: 'straight' | 'curved' | 'step';
  arrowSize?: number;
}

interface VisualizationConfig {
  color: ColorConfig;
  size: SizeConfig;
  shape: ShapeConfig;
  edge: EdgeStyleConfig;
  enableAnimations?: boolean;
  animationDuration?: number;
}

interface VisualizationStrategiesProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  config?: Partial<VisualizationConfig>;
  onNodesStyled?: (nodes: StyledNode[]) => void;
  onEdgesStyled?: (edges: StyledEdge[]) => void;
  children?: React.ReactNode;
}

interface StyledNode extends GraphNode {
  color: string;
  size: number;
  shape: string;
  opacity: number;
  borderColor?: string;
  borderWidth?: number;
  glow?: boolean;
  glowColor?: string;
}

interface StyledEdge extends GraphEdge {
  color: string;
  width: number;
  opacity: number;
  curveStyle: string;
  arrowSize: number;
  dashArray?: string;
  animated?: boolean;
}

/**
 * VisualizationStrategies - Advanced styling system for graph elements
 * Provides multiple color schemes, size strategies, and shape mappings
 */
export const VisualizationStrategies: React.FC<VisualizationStrategiesProps> = React.memo(({
  nodes,
  edges,
  config = {},
  onNodesStyled,
  onEdgesStyled,
  children
}) => {
  const [styledNodes, setStyledNodes] = useState<StyledNode[]>([]);
  const [styledEdges, setStyledEdges] = useState<StyledEdge[]>([]);

  // Memoize the default palette to prevent recreation
  const defaultPalette = useMemo(() => getDefaultPalette(), []);

  // Memoize configuration to prevent infinite loops
  const fullConfig: VisualizationConfig = useMemo(() => ({
    color: {
      scheme: config.color?.scheme || 'type',
      palette: config.color?.palette || defaultPalette,
      gradientStart: config.color?.gradientStart || '#4F46E5',
      gradientEnd: config.color?.gradientEnd || '#EF4444',
      opacity: config.color?.opacity ?? 1,
      customColorFn: config.color?.customColorFn
    },
    size: {
      strategy: config.size?.strategy || 'degree',
      minSize: config.size?.minSize ?? 3,
      maxSize: config.size?.maxSize ?? 20,
      scaleFactor: config.size?.scaleFactor ?? 1,
      customSizeFn: config.size?.customSizeFn
    },
    shape: {
      strategy: config.shape?.strategy || 'circle',
      customShapeFn: config.shape?.customShapeFn
    },
    edge: {
      color: config.edge?.color || '#94A3B8',
      colorByType: config.edge?.colorByType ?? false,
      width: config.edge?.width ?? 1,
      widthByWeight: config.edge?.widthByWeight ?? false,
      opacity: config.edge?.opacity ?? 0.6,
      curveStyle: config.edge?.curveStyle || 'straight',
      arrowSize: config.edge?.arrowSize ?? 4
    },
    enableAnimations: config.enableAnimations ?? true,
    animationDuration: config.animationDuration ?? 300
  }), [config, defaultPalette]);

  // Get default color palette
  function getDefaultPalette(): string[] {
    return [
      '#4F46E5', // Indigo
      '#10B981', // Emerald
      '#F59E0B', // Amber
      '#EF4444', // Red
      '#8B5CF6', // Violet
      '#06B6D4', // Cyan
      '#F97316', // Orange
      '#EC4899', // Pink
      '#14B8A6', // Teal
      '#84CC16'  // Lime
    ];
  }

  // Apply color scheme to node
  const applyColorScheme = useCallback((node: GraphNode, config: ColorConfig): string => {
    if (config.customColorFn) {
      return config.customColorFn(node);
    }

    switch (config.scheme) {
      case 'type':
        return getTypeColor(node, config.palette!);
      
      case 'centrality':
        return getCentralityColor(node, config.gradientStart!, config.gradientEnd!);
      
      case 'temporal':
        return getTemporalColor(node, config.gradientStart!, config.gradientEnd!);
      
      case 'community':
        return getCommunityColor(node, config.palette!);
      
      case 'gradient':
        return getGradientColor(node, config.gradientStart!, config.gradientEnd!);
      
      case 'categorical':
        return getCategoricalColor(node, config.palette!);
      
      default:
        return config.palette![0];
    }
  }, []);

  // Get color by node type
  function getTypeColor(node: GraphNode, palette: string[]): string {
    const typeMap: Record<string, number> = {
      'Entity': 0,
      'Event': 1,
      'Relation': 2,
      'Episodic': 3,
      'Person': 4,
      'Organization': 5,
      'Location': 6,
      'Document': 7,
      'Concept': 8
    };
    
    const index = typeMap[node.node_type] ?? 9;
    return palette[index % palette.length];
  }

  // Get color by centrality value
  function getCentralityColor(node: GraphNode, startColor: string, endColor: string): string {
    const centrality = node.properties?.eigenvector_centrality || 
                      node.properties?.degree_centrality || 0;
    return interpolateColor(startColor, endColor, centrality);
  }

  // Get color by temporal position
  function getTemporalColor(node: GraphNode, startColor: string, endColor: string): string {
    if (!node.created_at) return startColor;
    
    const now = Date.now();
    const nodeTime = new Date(node.created_at).getTime();
    const age = now - nodeTime;
    const maxAge = 30 * 24 * 60 * 60 * 1000; // 30 days
    const ratio = Math.min(age / maxAge, 1);
    
    return interpolateColor(startColor, endColor, ratio);
  }

  // Get color by community
  function getCommunityColor(node: GraphNode, palette: string[]): string {
    const community = node.properties?.community || 0;
    return palette[community % palette.length];
  }

  // Get gradient color
  function getGradientColor(node: GraphNode, startColor: string, endColor: string): string {
    const value = node.properties?.value || Math.random();
    return interpolateColor(startColor, endColor, value);
  }

  // Get categorical color
  function getCategoricalColor(node: GraphNode, palette: string[]): string {
    const category = node.properties?.category || node.node_type;
    const hash = hashString(category);
    return palette[hash % palette.length];
  }

  // Apply size strategy to node
  const applySizeStrategy = useCallback((node: GraphNode, config: SizeConfig): number => {
    if (config.customSizeFn) {
      return config.customSizeFn(node) * config.scaleFactor!;
    }

    let baseSize: number;
    
    switch (config.strategy) {
      case 'uniform':
        baseSize = (config.minSize! + config.maxSize!) / 2;
        break;
      
      case 'degree':
        const degree = node.degree || node.properties?.degree || 0;
        baseSize = config.minSize! + Math.log(degree + 1) * 2;
        break;
      
      case 'centrality':
        const centrality = node.properties?.eigenvector_centrality || 0;
        baseSize = config.minSize! + (config.maxSize! - config.minSize!) * centrality;
        break;
      
      case 'pagerank':
        const pagerank = node.properties?.pagerank_centrality || node.pagerank || 0;
        baseSize = config.minSize! + (config.maxSize! - config.minSize!) * pagerank;
        break;
      
      case 'temporal':
        if (!node.created_at) {
          baseSize = config.minSize!;
        } else {
          const age = Date.now() - new Date(node.created_at).getTime();
          const ageRatio = Math.max(0, 1 - age / (30 * 24 * 60 * 60 * 1000));
          baseSize = config.minSize! + (config.maxSize! - config.minSize!) * ageRatio;
        }
        break;
      
      default:
        baseSize = config.minSize!;
    }
    
    // Clamp to min/max and apply scale factor
    return Math.min(config.maxSize!, Math.max(config.minSize!, baseSize)) * config.scaleFactor!;
  }, []);

  // Apply shape strategy to node
  const applyShapeStrategy = useCallback((node: GraphNode, config: ShapeConfig): string => {
    if (config.customShapeFn) {
      return config.customShapeFn(node);
    }

    if (config.strategy === 'custom') {
      // Map node types to shapes
      const shapeMap: Record<string, string> = {
        'Entity': 'circle',
        'Event': 'square',
        'Relation': 'diamond',
        'Episodic': 'triangle',
        'Person': 'circle',
        'Organization': 'hexagon',
        'Location': 'square',
        'Document': 'square',
        'Concept': 'star'
      };
      
      return shapeMap[node.node_type] || 'circle';
    }

    return config.strategy;
  }, []);

  // Style edges
  const styleEdges = useCallback((
    edges: GraphEdge[],
    nodes: StyledNode[],
    config: EdgeStyleConfig
  ): StyledEdge[] => {
    const nodeMap = new Map(nodes.map(n => [n.id, n]));
    
    return edges.map(edge => {
      let color = config.color!;
      let width = config.width!;
      
      // Color by type if enabled
      if (config.colorByType && edge.relation_type) {
        const typeColors: Record<string, string> = {
          'RELATED_TO': '#94A3B8',
          'CAUSED_BY': '#F59E0B',
          'LEADS_TO': '#10B981',
          'PART_OF': '#8B5CF6',
          'BELONGS_TO': '#06B6D4'
        };
        color = typeColors[edge.relation_type] || config.color!;
      }
      
      // Width by weight if enabled
      if (config.widthByWeight && edge.weight !== undefined) {
        width = Math.max(0.5, Math.min(5, edge.weight * 2));
      }
      
      // Check if edge connects high-centrality nodes
      const sourceNode = nodeMap.get(edge.from);
      const targetNode = nodeMap.get(edge.to);
      const isImportant = sourceNode && targetNode && 
        (sourceNode.properties?.eigenvector_centrality || 0) > 0.5 &&
        (targetNode.properties?.eigenvector_centrality || 0) > 0.5;
      
      return {
        ...edge,
        color,
        width,
        opacity: config.opacity!,
        curveStyle: config.curveStyle!,
        arrowSize: config.arrowSize!,
        dashArray: edge.relation_type === 'POTENTIAL' ? '5,5' : undefined,
        animated: isImportant
      };
    });
  }, []);

  // Color interpolation helper
  function interpolateColor(start: string, end: string, ratio: number): string {
    const startRgb = hexToRgb(start);
    const endRgb = hexToRgb(end);
    
    if (!startRgb || !endRgb) return start;
    
    const r = Math.round(startRgb.r + (endRgb.r - startRgb.r) * ratio);
    const g = Math.round(startRgb.g + (endRgb.g - startRgb.g) * ratio);
    const b = Math.round(startRgb.b + (endRgb.b - startRgb.b) * ratio);
    
    return `rgb(${r}, ${g}, ${b})`;
  }

  // Hex to RGB conversion
  function hexToRgb(hex: string): { r: number; g: number; b: number } | null {
    const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
    return result ? {
      r: parseInt(result[1], 16),
      g: parseInt(result[2], 16),
      b: parseInt(result[3], 16)
    } : null;
  }

  // String hash function
  function hashString(str: string): number {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
      const char = str.charCodeAt(i);
      hash = ((hash << 5) - hash) + char;
      hash = hash & hash; // Convert to 32-bit integer
    }
    return Math.abs(hash);
  }

  // Apply styles to nodes and edges in a single effect to prevent double renders
  useEffect(() => {
    // Style nodes
    const styledNodesList = nodes.map(node => {
      const color = applyColorScheme(node, fullConfig.color);
      const size = applySizeStrategy(node, fullConfig.size);
      const shape = applyShapeStrategy(node, fullConfig.shape);
      
      // Add special effects for important nodes
      const isImportant = (node.properties?.eigenvector_centrality || 0) > 0.7;
      
      return {
        ...node,
        color,
        size,
        shape,
        opacity: fullConfig.color.opacity!,
        borderColor: isImportant ? '#FFD700' : undefined,
        borderWidth: isImportant ? 2 : undefined,
        glow: isImportant,
        glowColor: isImportant ? color : undefined
      } as StyledNode;
    });
    
    // Style edges using the styled nodes
    const styledEdgesList = styleEdges(edges, styledNodesList, fullConfig.edge);
    
    // Update state and notify callbacks in a single batch
    setStyledNodes(styledNodesList);
    setStyledEdges(styledEdgesList);
    onNodesStyled?.(styledNodesList);
    onEdgesStyled?.(styledEdgesList);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes, edges]); // Only re-run when nodes/edges change, not callbacks

  // Context value
  const contextValue = useMemo(() => ({
    styledNodes,
    styledEdges,
    config: fullConfig,
    applyColorScheme,
    applySizeStrategy,
    applyShapeStrategy,
    updateColorScheme: (scheme: ColorScheme) => {
      // This would trigger re-render with new scheme
    },
    updateSizeStrategy: (strategy: SizeStrategy) => {
      // This would trigger re-render with new strategy
    }
  }), [styledNodes, styledEdges, fullConfig, applyColorScheme, applySizeStrategy, applyShapeStrategy]);

  return (
    <VisualizationContext.Provider value={contextValue}>
      {children}
    </VisualizationContext.Provider>
  );
}, (prevProps, nextProps) => {
  // Custom comparison to prevent unnecessary re-renders
  return (
    prevProps.nodes === nextProps.nodes &&
    prevProps.edges === nextProps.edges &&
    prevProps.config === nextProps.config &&
    prevProps.children === nextProps.children &&
    prevProps.onNodesStyled === nextProps.onNodesStyled &&
    prevProps.onEdgesStyled === nextProps.onEdgesStyled
  );
});

// Context
const VisualizationContext = React.createContext<any>({});

export const useVisualization = () => React.useContext(VisualizationContext);