import React, { useState, useCallback, useEffect, useMemo, useRef } from 'react';
import { GraphNode, GraphEdge } from '../../../api/types';

type LayoutAlgorithm = 'force' | 'hierarchical' | 'circular' | 'radial' | 'grid' | 'spectral' | 'tree' | 'custom';

interface LayoutConfig {
  algorithm: LayoutAlgorithm;
  animated?: boolean;
  animationDuration?: number;
  iterations?: number;
  nodeSpacing?: number;
  levelDistance?: number;
  gravity?: number;
  repulsion?: number;
  springLength?: number;
  springStrength?: number;
  customLayoutFn?: (nodes: GraphNode[], edges: GraphEdge[]) => LayoutResult;
}

interface LayoutResult {
  nodes: Array<{ id: string; x: number; y: number }>;
  bounds?: { minX: number; minY: number; maxX: number; maxY: number };
  metadata?: Record<string, any>;
}

interface GraphLayoutAlgorithmsProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  config?: Partial<LayoutConfig>;
  onLayoutComplete?: (result: LayoutResult) => void;
  onLayoutProgress?: (progress: number) => void;
  children?: React.ReactNode;
}

interface LayoutState {
  isLayouting: boolean;
  currentAlgorithm: LayoutAlgorithm | null;
  progress: number;
  layoutResult: LayoutResult | null;
  error: Error | null;
}

/**
 * GraphLayoutAlgorithms - Advanced graph layout algorithms
 * Provides multiple layout strategies for optimal graph visualization
 */
export const GraphLayoutAlgorithms: React.FC<GraphLayoutAlgorithmsProps> = ({
  nodes,
  edges,
  config = {},
  onLayoutComplete,
  onLayoutProgress,
  children
}) => {
  const [state, setState] = useState<LayoutState>({
    isLayouting: false,
    currentAlgorithm: null,
    progress: 0,
    layoutResult: null,
    error: null
  });

  const workerRef = useRef<Worker | null>(null);
  const animationFrameRef = useRef<number | null>(null);

  // Default configuration
  const fullConfig: LayoutConfig = {
    algorithm: config.algorithm || 'force',
    animated: config.animated ?? true,
    animationDuration: config.animationDuration ?? 1000,
    iterations: config.iterations ?? 100,
    nodeSpacing: config.nodeSpacing ?? 50,
    levelDistance: config.levelDistance ?? 100,
    gravity: config.gravity ?? 0.1,
    repulsion: config.repulsion ?? 1000,
    springLength: config.springLength ?? 100,
    springStrength: config.springStrength ?? 0.1,
    customLayoutFn: config.customLayoutFn
  };

  // Force-directed layout (Fruchterman-Reingold)
  const forceDirectedLayout = useCallback((
    nodes: GraphNode[],
    edges: GraphEdge[],
    config: LayoutConfig
  ): LayoutResult => {
    const positions = new Map<string, { x: number; y: number; vx: number; vy: number }>();
    const area = Math.sqrt(nodes.length) * 1000;
    const k = Math.sqrt(area / nodes.length);
    
    // Initialize positions
    nodes.forEach((node, i) => {
      const angle = (i / nodes.length) * 2 * Math.PI;
      positions.set(node.id, {
        x: node.x || Math.cos(angle) * 200,
        y: node.y || Math.sin(angle) * 200,
        vx: 0,
        vy: 0
      });
    });
    
    // Create adjacency for efficiency
    const adjacency = new Map<string, Set<string>>();
    edges.forEach(edge => {
      if (!adjacency.has(edge.from)) adjacency.set(edge.from, new Set());
      if (!adjacency.has(edge.to)) adjacency.set(edge.to, new Set());
      adjacency.get(edge.from)!.add(edge.to);
      adjacency.get(edge.to)!.add(edge.from);
    });
    
    // Run iterations
    for (let iter = 0; iter < config.iterations!; iter++) {
      const temperature = 1 - iter / config.iterations!;
      
      // Calculate repulsive forces
      nodes.forEach(nodeA => {
        const posA = positions.get(nodeA.id)!;
        let fx = 0, fy = 0;
        
        nodes.forEach(nodeB => {
          if (nodeA.id === nodeB.id) return;
          
          const posB = positions.get(nodeB.id)!;
          const dx = posA.x - posB.x;
          const dy = posA.y - posB.y;
          const distance = Math.max(0.01, Math.sqrt(dx * dx + dy * dy));
          
          const repulsiveForce = (k * k) / distance;
          fx += (dx / distance) * repulsiveForce;
          fy += (dy / distance) * repulsiveForce;
        });
        
        posA.vx = fx * temperature;
        posA.vy = fy * temperature;
      });
      
      // Calculate attractive forces
      edges.forEach(edge => {
        const posFrom = positions.get(edge.from);
        const posTo = positions.get(edge.to);
        
        if (!posFrom || !posTo) return;
        
        const dx = posTo.x - posFrom.x;
        const dy = posTo.y - posFrom.y;
        const distance = Math.max(0.01, Math.sqrt(dx * dx + dy * dy));
        
        const attractiveForce = (distance * distance) / k;
        const fx = (dx / distance) * attractiveForce * config.springStrength!;
        const fy = (dy / distance) * attractiveForce * config.springStrength!;
        
        posFrom.vx += fx * temperature;
        posFrom.vy += fy * temperature;
        posTo.vx -= fx * temperature;
        posTo.vy -= fy * temperature;
      });
      
      // Apply gravity towards center
      nodes.forEach(node => {
        const pos = positions.get(node.id)!;
        pos.vx -= pos.x * config.gravity! * temperature;
        pos.vy -= pos.y * config.gravity! * temperature;
      });
      
      // Update positions
      nodes.forEach(node => {
        const pos = positions.get(node.id)!;
        pos.x += pos.vx;
        pos.y += pos.vy;
      });
    }
    
    // Convert to result format
    const result: LayoutResult = {
      nodes: Array.from(positions.entries()).map(([id, pos]) => ({
        id,
        x: pos.x,
        y: pos.y
      }))
    };
    
    // Calculate bounds
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    result.nodes.forEach(node => {
      minX = Math.min(minX, node.x);
      minY = Math.min(minY, node.y);
      maxX = Math.max(maxX, node.x);
      maxY = Math.max(maxY, node.y);
    });
    
    result.bounds = { minX, minY, maxX, maxY };
    
    return result;
  }, []);

  // Hierarchical layout (Sugiyama)
  const hierarchicalLayout = useCallback((
    nodes: GraphNode[],
    edges: GraphEdge[],
    config: LayoutConfig
  ): LayoutResult => {
    // Assign layers using longest path
    const layers = new Map<string, number>();
    const inDegree = new Map<string, number>();
    const adjacency = new Map<string, string[]>();
    
    // Build adjacency and calculate in-degrees
    nodes.forEach(node => {
      inDegree.set(node.id, 0);
      adjacency.set(node.id, []);
    });
    
    edges.forEach(edge => {
      adjacency.get(edge.from)?.push(edge.to);
      inDegree.set(edge.to, (inDegree.get(edge.to) || 0) + 1);
    });
    
    // Find roots (nodes with no incoming edges)
    const roots = nodes.filter(node => inDegree.get(node.id) === 0);
    const queue = [...roots];
    roots.forEach(root => layers.set(root.id, 0));
    
    // BFS to assign layers
    while (queue.length > 0) {
      const nodeId = queue.shift()!;
      const currentLayer = layers.get(nodeId) || 0;
      
      adjacency.get(nodeId)?.forEach(childId => {
        if (!layers.has(childId) || layers.get(childId)! < currentLayer + 1) {
          layers.set(childId, currentLayer + 1);
          queue.push(childId);
        }
      });
    }
    
    // Group nodes by layer
    const layerGroups = new Map<number, GraphNode[]>();
    nodes.forEach(node => {
      const layer = layers.get(node.id) || 0;
      if (!layerGroups.has(layer)) {
        layerGroups.set(layer, []);
      }
      layerGroups.get(layer)!.push(node);
    });
    
    // Position nodes
    const result: LayoutResult = { nodes: [] };
    const levelDistance = config.levelDistance!;
    const nodeSpacing = config.nodeSpacing!;
    
    layerGroups.forEach((layerNodes, layer) => {
      const y = layer * levelDistance;
      const totalWidth = layerNodes.length * nodeSpacing;
      const startX = -totalWidth / 2;
      
      layerNodes.forEach((node, index) => {
        result.nodes.push({
          id: node.id,
          x: startX + index * nodeSpacing,
          y
        });
      });
    });
    
    return result;
  }, []);

  // Circular layout
  const circularLayout = useCallback((
    nodes: GraphNode[],
    edges: GraphEdge[],
    config: LayoutConfig
  ): LayoutResult => {
    const radius = Math.max(200, nodes.length * 10);
    const angleStep = (2 * Math.PI) / nodes.length;
    
    const result: LayoutResult = {
      nodes: nodes.map((node, index) => ({
        id: node.id,
        x: Math.cos(index * angleStep) * radius,
        y: Math.sin(index * angleStep) * radius
      }))
    };
    
    return result;
  }, []);

  // Radial layout
  const radialLayout = useCallback((
    nodes: GraphNode[],
    edges: GraphEdge[],
    config: LayoutConfig
  ): LayoutResult => {
    // Find central nodes (highest degree)
    const degrees = new Map<string, number>();
    nodes.forEach(node => degrees.set(node.id, 0));
    
    edges.forEach(edge => {
      degrees.set(edge.from, (degrees.get(edge.from) || 0) + 1);
      degrees.set(edge.to, (degrees.get(edge.to) || 0) + 1);
    });
    
    // Sort by degree
    const sortedNodes = [...nodes].sort((a, b) => 
      (degrees.get(b.id) || 0) - (degrees.get(a.id) || 0)
    );
    
    // Place highest degree node at center
    const center = sortedNodes[0];
    const rings: GraphNode[][] = [[center]];
    const visited = new Set<string>([center.id]);
    
    // Build rings using BFS
    let currentRing = [center];
    while (visited.size < nodes.length) {
      const nextRing: GraphNode[] = [];
      
      currentRing.forEach(node => {
        edges.forEach(edge => {
          let neighbor: string | null = null;
          if (edge.from === node.id && !visited.has(edge.to)) {
            neighbor = edge.to;
          } else if (edge.to === node.id && !visited.has(edge.from)) {
            neighbor = edge.from;
          }
          
          if (neighbor) {
            const neighborNode = nodes.find(n => n.id === neighbor);
            if (neighborNode) {
              nextRing.push(neighborNode);
              visited.add(neighbor);
            }
          }
        });
      });
      
      if (nextRing.length > 0) {
        rings.push(nextRing);
        currentRing = nextRing;
      } else {
        // Add remaining unconnected nodes
        const remaining = nodes.filter(n => !visited.has(n.id));
        if (remaining.length > 0) {
          rings.push(remaining);
          remaining.forEach(n => visited.add(n.id));
        }
        break;
      }
    }
    
    // Position nodes in rings
    const result: LayoutResult = { nodes: [] };
    const ringDistance = config.levelDistance!;
    
    rings.forEach((ring, ringIndex) => {
      if (ringIndex === 0) {
        // Center node
        result.nodes.push({ id: ring[0].id, x: 0, y: 0 });
      } else {
        const radius = ringIndex * ringDistance;
        const angleStep = (2 * Math.PI) / ring.length;
        
        ring.forEach((node, index) => {
          result.nodes.push({
            id: node.id,
            x: Math.cos(index * angleStep) * radius,
            y: Math.sin(index * angleStep) * radius
          });
        });
      }
    });
    
    return result;
  }, []);

  // Grid layout
  const gridLayout = useCallback((
    nodes: GraphNode[],
    edges: GraphEdge[],
    config: LayoutConfig
  ): LayoutResult => {
    const cols = Math.ceil(Math.sqrt(nodes.length));
    const rows = Math.ceil(nodes.length / cols);
    const spacing = config.nodeSpacing!;
    
    const result: LayoutResult = {
      nodes: nodes.map((node, index) => {
        const col = index % cols;
        const row = Math.floor(index / cols);
        
        return {
          id: node.id,
          x: (col - cols / 2) * spacing,
          y: (row - rows / 2) * spacing
        };
      })
    };
    
    return result;
  }, []);

  // Apply layout algorithm
  const applyLayout = useCallback(async (
    algorithm: LayoutAlgorithm,
    nodes: GraphNode[],
    edges: GraphEdge[]
  ): Promise<LayoutResult> => {
    setState(prev => ({
      ...prev,
      isLayouting: true,
      currentAlgorithm: algorithm,
      progress: 0,
      error: null
    }));
    
    try {
      let result: LayoutResult;
      
      switch (algorithm) {
        case 'force':
          result = forceDirectedLayout(nodes, edges, fullConfig);
          break;
        
        case 'hierarchical':
          result = hierarchicalLayout(nodes, edges, fullConfig);
          break;
        
        case 'circular':
          result = circularLayout(nodes, edges, fullConfig);
          break;
        
        case 'radial':
          result = radialLayout(nodes, edges, fullConfig);
          break;
        
        case 'grid':
          result = gridLayout(nodes, edges, fullConfig);
          break;
        
        case 'custom':
          if (fullConfig.customLayoutFn) {
            result = fullConfig.customLayoutFn(nodes, edges);
          } else {
            throw new Error('Custom layout function not provided');
          }
          break;
        
        default:
          result = forceDirectedLayout(nodes, edges, fullConfig);
      }
      
      setState(prev => ({
        ...prev,
        layoutResult: result,
        progress: 100,
        isLayouting: false
      }));
      
      onLayoutComplete?.(result);
      
      return result;
      
    } catch (error) {
      setState(prev => ({
        ...prev,
        error: error as Error,
        isLayouting: false
      }));
      throw error;
    }
  }, [fullConfig, forceDirectedLayout, hierarchicalLayout, circularLayout, radialLayout, gridLayout, onLayoutComplete]);

  // Animate layout transition
  const animateLayoutTransition = useCallback((
    fromPositions: LayoutResult,
    toPositions: LayoutResult,
    duration: number
  ) => {
    const startTime = Date.now();
    const nodeMap = new Map<string, { from: any; to: any }>();
    
    // Build position maps
    fromPositions.nodes.forEach(node => {
      const toNode = toPositions.nodes.find(n => n.id === node.id);
      if (toNode) {
        nodeMap.set(node.id, {
          from: { x: node.x, y: node.y },
          to: { x: toNode.x, y: toNode.y }
        });
      }
    });
    
    const animate = () => {
      const elapsed = Date.now() - startTime;
      const progress = Math.min(elapsed / duration, 1);
      
      // Easing function (ease-in-out)
      const eased = progress < 0.5 
        ? 2 * progress * progress 
        : -1 + (4 - 2 * progress) * progress;
      
      const interpolated: LayoutResult = {
        nodes: Array.from(nodeMap.entries()).map(([id, positions]) => ({
          id,
          x: positions.from.x + (positions.to.x - positions.from.x) * eased,
          y: positions.from.y + (positions.to.y - positions.from.y) * eased
        }))
      };
      
      setState(prev => ({
        ...prev,
        layoutResult: interpolated,
        progress: progress * 100
      }));
      
      onLayoutProgress?.(progress * 100);
      
      if (progress < 1) {
        animationFrameRef.current = requestAnimationFrame(animate);
      } else {
        setState(prev => ({
          ...prev,
          layoutResult: toPositions,
          isLayouting: false
        }));
        onLayoutComplete?.(toPositions);
      }
    };
    
    animationFrameRef.current = requestAnimationFrame(animate);
  }, [onLayoutProgress, onLayoutComplete]);

  // Apply layout when algorithm changes
  useEffect(() => {
    if (nodes.length > 0) {
      applyLayout(fullConfig.algorithm, nodes, edges);
    }
    
    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
    };
  }, [fullConfig.algorithm, nodes, edges, applyLayout]);

  // Context value
  const contextValue = useMemo(() => ({
    ...state,
    applyLayout: (algorithm: LayoutAlgorithm) => applyLayout(algorithm, nodes, edges),
    animateTransition: animateLayoutTransition,
    config: fullConfig
  }), [state, nodes, edges, applyLayout, animateLayoutTransition, fullConfig]);

  return (
    <LayoutContext.Provider value={contextValue}>
      {children}
    </LayoutContext.Provider>
  );
};

// Context
const LayoutContext = React.createContext<any>({});

export const useLayout = () => React.useContext(LayoutContext);