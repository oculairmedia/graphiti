/**
 * Unit tests for useGraphSimulation hook
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useGraphSimulation, useSimpleSimulation } from '../../hooks/useGraphSimulation';
import { GraphNode } from '../../api/types';
import { GraphLink } from '../../types/graph';

describe('useGraphSimulation', () => {
  const mockNodes: GraphNode[] = [
    { id: 'node1', name: 'Node 1', node_type: 'person', x: 0, y: 0 },
    { id: 'node2', name: 'Node 2', node_type: 'organization', x: 100, y: 0 },
    { id: 'node3', name: 'Node 3', node_type: 'location', x: 50, y: 50 },
  ];

  const mockLinks: GraphLink[] = [
    { source: 'node1', target: 'node2', edge_type: 'knows' },
    { source: 'node2', target: 'node3', edge_type: 'located_at' },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  describe('Initialization', () => {
    it('should initialize with default state', () => {
      const { result } = renderHook(() => useGraphSimulation([], []));
      
      expect(result.current.isRunning).toBe(false);
      expect(result.current.alpha).toBe(1);
      expect(result.current.iterations).toBe(0);
    });

    it('should initialize node physics', () => {
      const { result } = renderHook(() => useGraphSimulation(mockNodes, mockLinks));
      
      const physics = result.current.getNodePhysics('node1');
      expect(physics).toBeDefined();
      expect(physics?.vx).toBe(0);
      expect(physics?.vy).toBe(0);
      expect(physics?.mass).toBe(1);
    });

    it('should auto-start when configured', () => {
      const onSimulationStart = vi.fn();
      renderHook(() => 
        useGraphSimulation(mockNodes, mockLinks, {
          autoStart: true,
          onSimulationStart
        })
      );
      
      expect(onSimulationStart).toHaveBeenCalled();
    });
  });

  describe('Simulation controls', () => {
    it('should start simulation', () => {
      const onSimulationStart = vi.fn();
      const { result } = renderHook(() => 
        useGraphSimulation(mockNodes, mockLinks, { onSimulationStart })
      );
      
      act(() => {
        result.current.start();
      });
      
      expect(result.current.isRunning).toBe(true);
      expect(onSimulationStart).toHaveBeenCalled();
    });

    it('should stop simulation', () => {
      const onSimulationEnd = vi.fn();
      const { result } = renderHook(() => 
        useGraphSimulation(mockNodes, mockLinks, { 
          autoStart: true,
          onSimulationEnd 
        })
      );
      
      act(() => {
        result.current.stop();
      });
      
      expect(result.current.isRunning).toBe(false);
      expect(onSimulationEnd).toHaveBeenCalled();
    });

    it('should restart simulation', () => {
      const { result } = renderHook(() => 
        useGraphSimulation(mockNodes, mockLinks, { autoStart: true })
      );
      
      const initialIterations = result.current.iterations;
      
      act(() => {
        result.current.restart();
      });
      
      // After restart, should reset iterations
      act(() => {
        vi.advanceTimersByTime(0);
      });
      
      expect(result.current.isRunning).toBe(true);
    });

    it('should reheat simulation', () => {
      const { result } = renderHook(() => 
        useGraphSimulation(mockNodes, mockLinks)
      );
      
      act(() => {
        result.current.reheat(0.5);
      });
      
      expect(result.current.alpha).toBe(0.5);
      expect(result.current.isRunning).toBe(true);
    });
  });

  describe('Force management', () => {
    it('should update force configuration', () => {
      const { result } = renderHook(() => 
        useGraphSimulation(mockNodes, mockLinks)
      );
      
      act(() => {
        result.current.updateForce('charge', { strength: -500 });
      });
      
      const chargeForce = result.current.simulationState.forces.find(f => f.type === 'charge');
      expect(chargeForce?.strength).toBe(-500);
    });

    it('should set all forces', () => {
      const { result } = renderHook(() => 
        useGraphSimulation(mockNodes, mockLinks)
      );
      
      const newForces = [
        { type: 'charge' as const, strength: -200, enabled: true },
        { type: 'link' as const, strength: 2, enabled: true }
      ];
      
      act(() => {
        result.current.setForces(newForces);
      });
      
      expect(result.current.simulationState.forces).toEqual(newForces);
    });

    it('should disable forces', () => {
      const { result } = renderHook(() => 
        useGraphSimulation(mockNodes, mockLinks)
      );
      
      act(() => {
        result.current.updateForce('charge', { enabled: false });
      });
      
      const chargeForce = result.current.simulationState.forces.find(f => f.type === 'charge');
      expect(chargeForce?.enabled).toBe(false);
    });
  });

  describe('Layouts', () => {
    it('should apply circular layout', () => {
      const onLayoutComplete = vi.fn();
      const { result } = renderHook(() => 
        useGraphSimulation(mockNodes, mockLinks, { onLayoutComplete })
      );
      
      act(() => {
        result.current.applyLayout({
          type: 'circular',
          params: { radius: 100 }
        });
      });
      
      // Verify nodes are arranged in a circle
      const node1 = mockNodes[0];
      const node2 = mockNodes[1];
      expect(Math.abs(Math.sqrt(node1.x! * node1.x! + node1.y! * node1.y!) - 100)).toBeLessThan(1);
      expect(Math.abs(Math.sqrt(node2.x! * node2.x! + node2.y! * node2.y!) - 100)).toBeLessThan(1);
      expect(onLayoutComplete).toHaveBeenCalledWith('circular');
    });

    it('should apply grid layout', () => {
      const { result } = renderHook(() => 
        useGraphSimulation(mockNodes, mockLinks)
      );
      
      act(() => {
        result.current.applyLayout({
          type: 'grid',
          params: { columns: 2, spacing: 50 }
        });
      });
      
      // First node should be at (0, 0)
      expect(mockNodes[0].x).toBe(0);
      expect(mockNodes[0].y).toBe(0);
      
      // Second node should be at (50, 0)
      expect(mockNodes[1].x).toBe(50);
      expect(mockNodes[1].y).toBe(0);
      
      // Third node should be at (0, 50)
      expect(mockNodes[2].x).toBe(0);
      expect(mockNodes[2].y).toBe(50);
    });

    it('should apply random layout', () => {
      const { result } = renderHook(() => 
        useGraphSimulation(mockNodes, mockLinks)
      );
      
      const initialPositions = mockNodes.map(n => ({ x: n.x, y: n.y }));
      
      act(() => {
        result.current.applyLayout({
          type: 'random',
          params: { width: 200, height: 200 }
        });
      });
      
      // Positions should have changed
      mockNodes.forEach((node, i) => {
        expect(node.x).not.toBe(initialPositions[i].x);
        expect(node.y).not.toBe(initialPositions[i].y);
        
        // Should be within bounds
        expect(node.x).toBeGreaterThanOrEqual(-100);
        expect(node.x).toBeLessThanOrEqual(100);
        expect(node.y).toBeGreaterThanOrEqual(-100);
        expect(node.y).toBeLessThanOrEqual(100);
      });
    });

    it('should apply hierarchical layout', () => {
      const { result } = renderHook(() => 
        useGraphSimulation(mockNodes, mockLinks)
      );
      
      act(() => {
        result.current.applyLayout({
          type: 'hierarchical',
          params: { levelSpacing: 100, nodeSpacing: 50 }
        });
      });
      
      // First node should be at level 0
      expect(mockNodes[0].y).toBe(0);
      
      // Connected nodes should be at different levels
      const node2Y = mockNodes[1].y;
      const node3Y = mockNodes[2].y;
      expect(node2Y).not.toBe(undefined);
      expect(node3Y).not.toBe(undefined);
    });

    it('should animate layout when configured', () => {
      const { result } = renderHook(() => 
        useGraphSimulation(mockNodes, mockLinks)
      );
      
      act(() => {
        result.current.applyLayout({
          type: 'circular',
          animate: true
        });
      });
      
      expect(result.current.isRunning).toBe(true);
      expect(result.current.alpha).toBe(0.5); // Reheated
    });
  });

  describe('Alpha parameters', () => {
    it('should update alpha target', () => {
      const { result } = renderHook(() => 
        useGraphSimulation(mockNodes, mockLinks)
      );
      
      act(() => {
        result.current.setAlphaTarget(0.5);
      });
      
      expect(result.current.simulationState.alphaTarget).toBe(0.5);
    });

    it('should update alpha decay', () => {
      const { result } = renderHook(() => 
        useGraphSimulation(mockNodes, mockLinks)
      );
      
      act(() => {
        result.current.setAlphaDecay(0.05);
      });
      
      expect(result.current.simulationState.alphaDecay).toBe(0.05);
    });

    it('should update velocity decay', () => {
      const { result } = renderHook(() => 
        useGraphSimulation(mockNodes, mockLinks)
      );
      
      act(() => {
        result.current.setVelocityDecay(0.6);
      });
      
      expect(result.current.simulationState.velocityDecay).toBe(0.6);
    });
  });

  describe('Node physics', () => {
    it('should get node physics', () => {
      const { result } = renderHook(() => 
        useGraphSimulation(mockNodes, mockLinks)
      );
      
      const physics = result.current.getNodePhysics('node1');
      expect(physics).toBeDefined();
      expect(physics?.vx).toBe(0);
      expect(physics?.vy).toBe(0);
    });

    it('should set node physics', () => {
      const { result } = renderHook(() => 
        useGraphSimulation(mockNodes, mockLinks)
      );
      
      act(() => {
        result.current.setNodePhysics('node1', {
          vx: 10,
          vy: 20,
          mass: 2
        });
      });
      
      const physics = result.current.getNodePhysics('node1');
      expect(physics?.vx).toBe(10);
      expect(physics?.vy).toBe(20);
      expect(physics?.mass).toBe(2);
    });
  });

  describe('Metrics', () => {
    it('should calculate metrics', () => {
      const { result } = renderHook(() => 
        useGraphSimulation(mockNodes, mockLinks)
      );
      
      const metrics = result.current.getMetrics();
      expect(metrics).toBeDefined();
      expect(metrics.totalEnergy).toBe(0); // No velocity initially
      expect(metrics.averageVelocity).toBe(0);
      expect(metrics.centerOfMass).toBeDefined();
    });

    it('should update metrics during simulation', async () => {
      const { result } = renderHook(() => 
        useGraphSimulation(mockNodes, mockLinks, {
          autoStart: true
        })
      );
      
      // Let simulation run for a bit
      act(() => {
        vi.advanceTimersByTime(100);
      });
      
      const metrics = result.current.getMetrics();
      expect(metrics.totalEnergy).toBeGreaterThanOrEqual(0);
    });
  });

  describe('Viewport constraints', () => {
    it('should constrain nodes to viewport', () => {
      const viewportBounds = {
        minX: -50,
        maxX: 50,
        minY: -50,
        maxY: 50
      };
      
      const nodes = [
        { id: 'node1', name: 'Node 1', node_type: 'test' as any, x: 0, y: 0 }
      ];
      
      const { result } = renderHook(() => 
        useGraphSimulation(nodes, [], {
          constrainToViewport: true,
          viewportBounds
        })
      );
      
      // Try to move node outside viewport
      act(() => {
        result.current.setNodePhysics('node1', { vx: 200, vy: 200 });
        result.current.start();
      });
      
      act(() => {
        vi.advanceTimersByTime(100);
      });
      
      // Node should be constrained
      expect(nodes[0].x).toBeLessThanOrEqual(50);
      expect(nodes[0].y).toBeLessThanOrEqual(50);
    });
  });

  describe('Callbacks', () => {
    it('should call simulation tick callback', () => {
      const onSimulationTick = vi.fn();
      const { result } = renderHook(() => 
        useGraphSimulation(mockNodes, mockLinks, {
          onSimulationTick
        })
      );
      
      act(() => {
        result.current.start();
      });
      
      act(() => {
        vi.advanceTimersByTime(50);
      });
      
      expect(onSimulationTick).toHaveBeenCalled();
    });

    it('should call node position update callback', () => {
      const onNodePositionUpdate = vi.fn();
      const { result } = renderHook(() => 
        useGraphSimulation(mockNodes, mockLinks, {
          onNodePositionUpdate
        })
      );
      
      act(() => {
        result.current.setNodePhysics('node1', { vx: 10, vy: 10 });
        result.current.start();
      });
      
      act(() => {
        vi.advanceTimersByTime(50);
      });
      
      expect(onNodePositionUpdate).toHaveBeenCalled();
    });
  });
});

describe('useSimpleSimulation', () => {
  const mockNodes: GraphNode[] = [
    { id: 'node1', name: 'Node 1', node_type: 'person', x: 0, y: 0 },
    { id: 'node2', name: 'Node 2', node_type: 'organization', x: 100, y: 0 },
  ];

  const mockLinks: GraphLink[] = [
    { source: 'node1', target: 'node2', edge_type: 'knows' },
  ];

  it('should provide basic simulation controls', () => {
    const { result } = renderHook(() => 
      useSimpleSimulation(mockNodes, mockLinks, false)
    );
    
    expect(result.current.isRunning).toBe(false);
    
    act(() => {
      result.current.start();
    });
    
    expect(result.current.isRunning).toBe(true);
    
    act(() => {
      result.current.stop();
    });
    
    expect(result.current.isRunning).toBe(false);
  });

  it('should auto-start when configured', () => {
    const { result } = renderHook(() => 
      useSimpleSimulation(mockNodes, mockLinks, true)
    );
    
    expect(result.current.isRunning).toBe(true);
  });
});