/**
 * Graph Simulation Hook
 * Handles force-directed graph simulation, physics, and layout algorithms
 */

import { useState, useCallback, useRef, useEffect, useMemo } from 'react';
import { GraphNode } from '../api/types';
import { GraphLink } from '../types/graph';

/**
 * Simulation force types
 */
export type ForceType = 
  | 'charge'
  | 'link'
  | 'center'
  | 'collision'
  | 'x'
  | 'y'
  | 'gravity'
  | 'friction';

/**
 * Force configuration
 */
export interface Force {
  type: ForceType;
  strength: number;
  enabled: boolean;
  params?: Record<string, any>;
}

/**
 * Layout algorithm types
 */
export type LayoutType = 
  | 'force-directed'
  | 'hierarchical'
  | 'circular'
  | 'grid'
  | 'radial'
  | 'tree'
  | 'random'
  | 'custom';

/**
 * Layout configuration
 */
export interface LayoutConfig {
  type: LayoutType;
  params?: Record<string, any>;
  animate?: boolean;
  duration?: number;
}

/**
 * Simulation state
 */
export interface SimulationState {
  running: boolean;
  alpha: number;
  alphaTarget: number;
  alphaMin: number;
  alphaDecay: number;
  velocityDecay: number;
  forces: Force[];
  iterations: number;
  temperature: number;
}

/**
 * Node physics properties
 */
export interface NodePhysics {
  vx: number;
  vy: number;
  fx?: number | null;
  fy?: number | null;
  mass?: number;
  radius?: number;
  charge?: number;
}

/**
 * Simulation metrics
 */
export interface SimulationMetrics {
  totalEnergy: number;
  kineticEnergy: number;
  potentialEnergy: number;
  averageVelocity: number;
  maxVelocity: number;
  centerOfMass: { x: number; y: number };
  convergenceRate: number;
}

/**
 * Hook configuration
 */
export interface UseGraphSimulationConfig {
  // Enable/disable simulation
  enabled?: boolean;
  autoStart?: boolean;
  
  // Alpha parameters
  initialAlpha?: number;
  alphaTarget?: number;
  alphaMin?: number;
  alphaDecay?: number;
  
  // Velocity decay (friction)
  velocityDecay?: number;
  
  // Force configuration
  forces?: Force[];
  
  // Constraints
  constrainToViewport?: boolean;
  viewportBounds?: {
    minX: number;
    maxX: number;
    minY: number;
    maxY: number;
  };
  
  // Performance
  maxIterations?: number;
  simulationQuality?: 'low' | 'medium' | 'high';
  useWebWorker?: boolean;
  
  // Callbacks
  onSimulationStart?: () => void;
  onSimulationTick?: (alpha: number) => void;
  onSimulationEnd?: () => void;
  onNodePositionUpdate?: (nodeId: string, position: { x: number; y: number }) => void;
  onLayoutComplete?: (layout: LayoutType) => void;
  
  // Debug
  debug?: boolean;
}

/**
 * Default forces
 */
const defaultForces: Force[] = [
  { type: 'charge', strength: -300, enabled: true },
  { type: 'link', strength: 1, enabled: true },
  { type: 'center', strength: 0.1, enabled: true },
  { type: 'collision', strength: 0.5, enabled: false },
  { type: 'gravity', strength: 0.1, enabled: false }
];

/**
 * Graph Simulation Hook
 */
export function useGraphSimulation(
  nodes: GraphNode[],
  links: GraphLink[],
  config: UseGraphSimulationConfig = {}
) {
  const {
    enabled = true,
    autoStart = false,
    initialAlpha = 1,
    alphaTarget = 0,
    alphaMin = 0.001,
    alphaDecay = 0.0228,
    velocityDecay = 0.4,
    forces = defaultForces,
    constrainToViewport = false,
    viewportBounds,
    maxIterations = 300,
    simulationQuality = 'medium',
    useWebWorker = false,
    onSimulationStart,
    onSimulationTick,
    onSimulationEnd,
    onNodePositionUpdate,
    onLayoutComplete,
    debug = false
  } = config;

  // Simulation state
  const [simulationState, setSimulationState] = useState<SimulationState>({
    running: false,
    alpha: initialAlpha,
    alphaTarget,
    alphaMin,
    alphaDecay,
    velocityDecay,
    forces,
    iterations: 0,
    temperature: 1
  });

  // Node physics data
  const nodePhysicsRef = useRef<Map<string, NodePhysics>>(new Map());
  const animationFrameRef = useRef<number | null>(null);
  const startTimeRef = useRef<number>(0);
  const metricsRef = useRef<SimulationMetrics>({
    totalEnergy: 0,
    kineticEnergy: 0,
    potentialEnergy: 0,
    averageVelocity: 0,
    maxVelocity: 0,
    centerOfMass: { x: 0, y: 0 },
    convergenceRate: 0
  });

  /**
   * Log debug message
   */
  const log = useCallback((message: string, ...args: any[]) => {
    if (debug) {
      console.debug(`[useGraphSimulation] ${message}`, ...args);
    }
  }, [debug]);

  /**
   * Initialize node physics
   */
  useEffect(() => {
    nodes.forEach(node => {
      if (!nodePhysicsRef.current.has(node.id)) {
        nodePhysicsRef.current.set(node.id, {
          vx: 0,
          vy: 0,
          fx: null,
          fy: null,
          mass: 1,
          radius: 5,
          charge: -30
        });
      }
    });
    
    // Clean up removed nodes
    const nodeIds = new Set(nodes.map(n => n.id));
    Array.from(nodePhysicsRef.current.keys()).forEach(id => {
      if (!nodeIds.has(id)) {
        nodePhysicsRef.current.delete(id);
      }
    });
  }, [nodes]);

  /**
   * Calculate forces
   */
  const calculateForces = useCallback(() => {
    // Reset forces
    nodePhysicsRef.current.forEach(physics => {
      physics.fx = 0;
      physics.fy = 0;
    });

    forces.forEach(force => {
      if (!force.enabled) return;

      switch (force.type) {
        case 'charge':
          // Repulsive force between all nodes
          nodes.forEach((nodeA, i) => {
            const physicsA = nodePhysicsRef.current.get(nodeA.id);
            if (!physicsA || nodeA.x === undefined || nodeA.y === undefined) return;

            nodes.forEach((nodeB, j) => {
              if (i >= j) return;
              const physicsB = nodePhysicsRef.current.get(nodeB.id);
              if (!physicsB || nodeB.x === undefined || nodeB.y === undefined) return;

              const dx = nodeB.x - nodeA.x;
              const dy = nodeB.y - nodeA.y;
              const dist2 = dx * dx + dy * dy;
              
              if (dist2 === 0) return;
              
              const dist = Math.sqrt(dist2);
              const forceStrength = (force.strength * (physicsA.charge || -30) * (physicsB.charge || -30)) / dist2;
              
              const fx = (dx / dist) * forceStrength;
              const fy = (dy / dist) * forceStrength;
              
              physicsA.fx! -= fx;
              physicsA.fy! -= fy;
              physicsB.fx! += fx;
              physicsB.fy! += fy;
            });
          });
          break;

        case 'link':
          // Spring force along links
          links.forEach(link => {
            const sourceNode = nodes.find(n => n.id === link.source);
            const targetNode = nodes.find(n => n.id === link.target);
            
            if (!sourceNode || !targetNode) return;
            if (sourceNode.x === undefined || sourceNode.y === undefined) return;
            if (targetNode.x === undefined || targetNode.y === undefined) return;
            
            const sourcePhysics = nodePhysicsRef.current.get(sourceNode.id);
            const targetPhysics = nodePhysicsRef.current.get(targetNode.id);
            
            if (!sourcePhysics || !targetPhysics) return;
            
            const dx = targetNode.x - sourceNode.x;
            const dy = targetNode.y - sourceNode.y;
            const dist = Math.sqrt(dx * dx + dy * dy);
            
            if (dist === 0) return;
            
            const desiredDist = force.params?.distance || 30;
            const forceStrength = force.strength * (dist - desiredDist) / dist;
            
            const fx = dx * forceStrength;
            const fy = dy * forceStrength;
            
            sourcePhysics.fx! += fx;
            sourcePhysics.fy! += fy;
            targetPhysics.fx! -= fx;
            targetPhysics.fy! -= fy;
          });
          break;

        case 'center':
          // Centering force
          let centerX = 0, centerY = 0, count = 0;
          
          nodes.forEach(node => {
            if (node.x !== undefined && node.y !== undefined) {
              centerX += node.x;
              centerY += node.y;
              count++;
            }
          });
          
          if (count > 0) {
            centerX /= count;
            centerY /= count;
            
            nodes.forEach(node => {
              const physics = nodePhysicsRef.current.get(node.id);
              if (!physics || node.x === undefined || node.y === undefined) return;
              
              physics.fx! -= (node.x - centerX) * force.strength;
              physics.fy! -= (node.y - centerY) * force.strength;
            });
          }
          break;

        case 'gravity':
          // Gravity towards center
          const gravityCenter = force.params?.center || { x: 0, y: 0 };
          
          nodes.forEach(node => {
            const physics = nodePhysicsRef.current.get(node.id);
            if (!physics || node.x === undefined || node.y === undefined) return;
            
            const dx = gravityCenter.x - node.x;
            const dy = gravityCenter.y - node.y;
            const dist = Math.sqrt(dx * dx + dy * dy);
            
            if (dist > 0) {
              physics.fx! += (dx / dist) * force.strength * (physics.mass || 1);
              physics.fy! += (dy / dist) * force.strength * (physics.mass || 1);
            }
          });
          break;
      }
    });
  }, [nodes, links, forces]);

  /**
   * Update positions
   */
  const updatePositions = useCallback((alpha: number) => {
    nodes.forEach(node => {
      const physics = nodePhysicsRef.current.get(node.id);
      if (!physics || node.x === undefined || node.y === undefined) return;
      
      // Apply forces
      physics.vx += (physics.fx || 0) * alpha;
      physics.vy += (physics.fy || 0) * alpha;
      
      // Apply velocity decay (friction)
      physics.vx *= velocityDecay;
      physics.vy *= velocityDecay;
      
      // Update position
      const newX = node.x + physics.vx;
      const newY = node.y + physics.vy;
      
      // Apply viewport constraints if enabled
      if (constrainToViewport && viewportBounds) {
        node.x = Math.max(viewportBounds.minX, Math.min(viewportBounds.maxX, newX));
        node.y = Math.max(viewportBounds.minY, Math.min(viewportBounds.maxY, newY));
      } else {
        node.x = newX;
        node.y = newY;
      }
      
      if (onNodePositionUpdate) {
        onNodePositionUpdate(node.id, { x: node.x, y: node.y });
      }
    });
  }, [nodes, velocityDecay, constrainToViewport, viewportBounds, onNodePositionUpdate]);

  /**
   * Calculate metrics
   */
  const calculateMetrics = useCallback(() => {
    let totalKE = 0;
    let totalVelocity = 0;
    let maxVel = 0;
    let centerX = 0, centerY = 0;
    let count = 0;
    
    nodes.forEach(node => {
      const physics = nodePhysicsRef.current.get(node.id);
      if (!physics) return;
      
      const v2 = physics.vx * physics.vx + physics.vy * physics.vy;
      const v = Math.sqrt(v2);
      
      totalKE += 0.5 * (physics.mass || 1) * v2;
      totalVelocity += v;
      maxVel = Math.max(maxVel, v);
      
      if (node.x !== undefined && node.y !== undefined) {
        centerX += node.x * (physics.mass || 1);
        centerY += node.y * (physics.mass || 1);
        count += (physics.mass || 1);
      }
    });
    
    metricsRef.current = {
      totalEnergy: totalKE,
      kineticEnergy: totalKE,
      potentialEnergy: 0, // Would need to calculate based on forces
      averageVelocity: nodes.length > 0 ? totalVelocity / nodes.length : 0,
      maxVelocity: maxVel,
      centerOfMass: count > 0 ? { x: centerX / count, y: centerY / count } : { x: 0, y: 0 },
      convergenceRate: simulationState.alphaDecay
    };
  }, [nodes, simulationState.alphaDecay]);

  /**
   * Simulation tick
   */
  const tick = useCallback(() => {
    setSimulationState(prev => {
      if (!prev.running) return prev;
      
      calculateForces();
      updatePositions(prev.alpha);
      calculateMetrics();
      
      // Update alpha
      const newAlpha = prev.alpha + (prev.alphaTarget - prev.alpha) * prev.alphaDecay;
      
      if (onSimulationTick) {
        onSimulationTick(newAlpha);
      }
      
      // Check stopping conditions
      if (newAlpha < prev.alphaMin || prev.iterations >= maxIterations) {
        log('Simulation stopped', {
          reason: newAlpha < prev.alphaMin ? 'alpha threshold' : 'max iterations',
          iterations: prev.iterations
        });
        
        if (onSimulationEnd) {
          onSimulationEnd();
        }
        
        return {
          ...prev,
          running: false,
          alpha: newAlpha,
          iterations: prev.iterations + 1
        };
      } else {
        animationFrameRef.current = requestAnimationFrame(tick);
        
        return {
          ...prev,
          alpha: newAlpha,
          iterations: prev.iterations + 1
        };
      }
    });
  }, [
    calculateForces,
    updatePositions,
    calculateMetrics,
    maxIterations,
    onSimulationTick,
    onSimulationEnd,
    log
  ]);

  /**
   * Start simulation
   */
  const start = useCallback(() => {
    if (simulationState.running || !enabled) return;
    
    log('Starting simulation');
    
    startTimeRef.current = Date.now();
    
    setSimulationState(prev => ({
      ...prev,
      running: true,
      alpha: initialAlpha,
      iterations: 0
    }));
    
    if (onSimulationStart) {
      onSimulationStart();
    }
    
    animationFrameRef.current = requestAnimationFrame(tick);
  }, [enabled, simulationState.running, initialAlpha, onSimulationStart, tick, log]);

  /**
   * Stop simulation
   */
  const stop = useCallback(() => {
    log('Stopping simulation');
    
    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current);
      animationFrameRef.current = null;
    }
    
    setSimulationState(prev => ({
      ...prev,
      running: false
    }));
    
    if (onSimulationEnd) {
      onSimulationEnd();
    }
  }, [onSimulationEnd, log]);

  /**
   * Restart simulation
   */
  const restart = useCallback(() => {
    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current);
      animationFrameRef.current = null;
    }
    
    setSimulationState(prev => ({
      ...prev,
      running: false
    }));
    
    // Reset and start in next tick
    setTimeout(() => {
      setSimulationState(prev => ({
        ...prev,
        running: true,
        alpha: initialAlpha,
        iterations: 0
      }));
      
      if (onSimulationStart) {
        onSimulationStart();
      }
      
      animationFrameRef.current = requestAnimationFrame(tick);
    }, 0);
  }, [initialAlpha, onSimulationStart, tick]);

  /**
   * Reheat simulation
   */
  const reheat = useCallback((alpha: number = 0.3) => {
    log(`Reheating simulation to alpha=${alpha}`);
    
    setSimulationState(prev => ({
      ...prev,
      alpha,
      running: true
    }));
    
    if (!animationFrameRef.current) {
      if (onSimulationStart) {
        onSimulationStart();
      }
      animationFrameRef.current = requestAnimationFrame(tick);
    }
  }, [onSimulationStart, tick, log]);

  /**
   * Update force
   */
  const updateForce = useCallback((type: ForceType, updates: Partial<Force>) => {
    setSimulationState(prev => ({
      ...prev,
      forces: prev.forces.map(force =>
        force.type === type ? { ...force, ...updates } : force
      )
    }));
  }, []);

  /**
   * Apply layout
   */
  const applyLayout = useCallback((layout: LayoutConfig) => {
    log(`Applying ${layout.type} layout`);
    
    switch (layout.type) {
      case 'circular':
        const radius = layout.params?.radius || 200;
        const angleStep = (2 * Math.PI) / nodes.length;
        
        nodes.forEach((node, i) => {
          node.x = radius * Math.cos(i * angleStep);
          node.y = radius * Math.sin(i * angleStep);
        });
        break;
        
      case 'grid':
        const cols = layout.params?.columns || Math.ceil(Math.sqrt(nodes.length));
        const spacing = layout.params?.spacing || 50;
        
        nodes.forEach((node, i) => {
          node.x = (i % cols) * spacing;
          node.y = Math.floor(i / cols) * spacing;
        });
        break;
        
      case 'random':
        const width = layout.params?.width || 800;
        const height = layout.params?.height || 600;
        
        nodes.forEach(node => {
          node.x = Math.random() * width - width / 2;
          node.y = Math.random() * height - height / 2;
        });
        break;
        
      case 'hierarchical':
        // Simple hierarchical layout - would need more complex implementation
        const levels = new Map<string, number>();
        const visited = new Set<string>();
        
        // BFS to assign levels
        const queue: string[] = [];
        if (nodes.length > 0) {
          queue.push(nodes[0].id);
          levels.set(nodes[0].id, 0);
          visited.add(nodes[0].id);
        }
        
        while (queue.length > 0) {
          const current = queue.shift()!;
          const currentLevel = levels.get(current) || 0;
          
          links.forEach(link => {
            let neighbor: string | null = null;
            if (link.source === current && !visited.has(link.target)) {
              neighbor = link.target;
            } else if (link.target === current && !visited.has(link.source)) {
              neighbor = link.source;
            }
            
            if (neighbor) {
              visited.add(neighbor);
              levels.set(neighbor, currentLevel + 1);
              queue.push(neighbor);
            }
          });
        }
        
        // Position nodes by level
        const levelCounts = new Map<number, number>();
        const levelSpacing = layout.params?.levelSpacing || 100;
        const nodeSpacing = layout.params?.nodeSpacing || 50;
        
        nodes.forEach(node => {
          const level = levels.get(node.id) || 0;
          const count = levelCounts.get(level) || 0;
          
          node.x = count * nodeSpacing;
          node.y = level * levelSpacing;
          
          levelCounts.set(level, count + 1);
        });
        break;
    }
    
    if (onLayoutComplete) {
      onLayoutComplete(layout.type);
    }
    
    if (layout.animate && !simulationState.running) {
      reheat(0.5);
    }
  }, [nodes, links, simulationState.running, reheat, onLayoutComplete, log]);

  /**
   * Get metrics
   */
  const getMetrics = useCallback((): SimulationMetrics => {
    return { ...metricsRef.current };
  }, []);

  /**
   * Auto-start simulation
   */
  useEffect(() => {
    if (autoStart && enabled && !simulationState.running) {
      start();
    }
  }, [autoStart, enabled]);

  /**
   * Cleanup
   */
  useEffect(() => {
    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
    };
  }, []);

  return {
    // State
    simulationState,
    isRunning: simulationState.running,
    alpha: simulationState.alpha,
    iterations: simulationState.iterations,
    
    // Controls
    start,
    stop,
    restart,
    reheat,
    
    // Force management
    updateForce,
    setForces: (forces: Force[]) => setSimulationState(prev => ({ ...prev, forces })),
    
    // Layouts
    applyLayout,
    
    // Metrics
    metrics: metricsRef.current,
    getMetrics,
    
    // Node physics access
    getNodePhysics: (nodeId: string) => nodePhysicsRef.current.get(nodeId),
    setNodePhysics: (nodeId: string, physics: Partial<NodePhysics>) => {
      const current = nodePhysicsRef.current.get(nodeId);
      if (current) {
        nodePhysicsRef.current.set(nodeId, { ...current, ...physics });
      }
    },
    
    // Configuration
    setAlphaTarget: (target: number) => setSimulationState(prev => ({ ...prev, alphaTarget: target })),
    setAlphaDecay: (decay: number) => setSimulationState(prev => ({ ...prev, alphaDecay: decay })),
    setVelocityDecay: (decay: number) => setSimulationState(prev => ({ ...prev, velocityDecay: decay }))
  };
}

/**
 * Simple force simulation hook
 */
export function useSimpleSimulation(
  nodes: GraphNode[],
  links: GraphLink[],
  autoStart: boolean = false
) {
  const simulation = useGraphSimulation(nodes, links, {
    autoStart,
    forces: [
      { type: 'charge', strength: -100, enabled: true },
      { type: 'link', strength: 0.5, enabled: true },
      { type: 'center', strength: 0.1, enabled: true }
    ]
  });
  
  return {
    isRunning: simulation.isRunning,
    start: simulation.start,
    stop: simulation.stop,
    restart: simulation.restart
  };
}