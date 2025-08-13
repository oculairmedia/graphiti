/**
 * Unit tests for useGraphVisualEffects hook
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useGraphVisualEffects, useSimpleVisualEffects } from '../../hooks/useGraphVisualEffects';
import { GraphNode } from '../../api/types';
import { GraphLink } from '../../types/graph';

describe('useGraphVisualEffects', () => {
  const mockNodes: GraphNode[] = [
    { id: 'node1', name: 'Node 1', node_type: 'person' },
    { id: 'node2', name: 'Node 2', node_type: 'organization' },
    { id: 'node3', name: 'Node 3', node_type: 'location' },
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

  describe('Effect management', () => {
    it('should add visual effect', () => {
      const onEffectStart = vi.fn();
      const { result } = renderHook(() => 
        useGraphVisualEffects(mockNodes, mockLinks, { onEffectStart })
      );
      
      let effectId: string;
      act(() => {
        effectId = result.current.addEffect({
          type: 'highlight',
          target: 'node',
          targetIds: ['node1'],
          duration: 1000
        });
      });
      
      expect(result.current.activeEffects).toHaveLength(1);
      expect(result.current.activeEffects[0].type).toBe('highlight');
      expect(onEffectStart).toHaveBeenCalled();
    });

    it('should remove visual effect', () => {
      const onEffectComplete = vi.fn();
      const { result } = renderHook(() => 
        useGraphVisualEffects(mockNodes, mockLinks, { onEffectComplete })
      );
      
      let effectId: string;
      act(() => {
        effectId = result.current.addEffect({
          type: 'pulse',
          target: 'node',
          targetIds: ['node1'],
          duration: 1000
        });
      });
      
      act(() => {
        result.current.removeEffect(effectId);
      });
      
      expect(result.current.activeEffects).toHaveLength(0);
      expect(onEffectComplete).toHaveBeenCalled();
    });

    it('should clear all effects', () => {
      const { result } = renderHook(() => 
        useGraphVisualEffects(mockNodes, mockLinks)
      );
      
      act(() => {
        result.current.addEffect({
          type: 'highlight',
          target: 'node',
          targetIds: ['node1'],
          duration: 1000
        });
        result.current.addEffect({
          type: 'pulse',
          target: 'node',
          targetIds: ['node2'],
          duration: 1000
        });
      });
      
      expect(result.current.activeEffects).toHaveLength(2);
      
      act(() => {
        result.current.clearEffects();
      });
      
      expect(result.current.activeEffects).toHaveLength(0);
    });

    it('should queue effects when max concurrent reached', () => {
      const { result } = renderHook(() => 
        useGraphVisualEffects(mockNodes, mockLinks, {
          maxConcurrentEffects: 2
        })
      );
      
      act(() => {
        // Add 3 effects (max is 2)
        for (let i = 0; i < 3; i++) {
          result.current.addEffect({
            type: 'highlight',
            target: 'node',
            targetIds: [`node${i}`],
            duration: 1000
          });
        }
      });
      
      // Only 2 should be active
      expect(result.current.activeEffects).toHaveLength(2);
    });
  });

  describe('Highlight effects', () => {
    it('should highlight nodes', () => {
      const { result } = renderHook(() => 
        useGraphVisualEffects(mockNodes, mockLinks)
      );
      
      act(() => {
        result.current.highlightNodes(['node1', 'node2']);
      });
      
      expect(result.current.highlightedNodes).toContain('node1');
      expect(result.current.highlightedNodes).toContain('node2');
      expect(result.current.isNodeHighlighted('node1')).toBe(true);
      expect(result.current.isNodeHighlighted('node3')).toBe(false);
    });

    it('should highlight links', () => {
      const { result } = renderHook(() => 
        useGraphVisualEffects(mockNodes, mockLinks)
      );
      
      act(() => {
        result.current.highlightLinks(['node1-node2']);
      });
      
      expect(result.current.highlightedLinks).toContain('node1-node2');
      expect(result.current.isLinkHighlighted('node1', 'node2')).toBe(true);
      expect(result.current.isLinkHighlighted('node2', 'node3')).toBe(false);
    });

    it('should clear highlights after duration', () => {
      const { result } = renderHook(() => 
        useGraphVisualEffects(mockNodes, mockLinks)
      );
      
      act(() => {
        result.current.highlightNodes(['node1'], 100);
      });
      
      expect(result.current.isNodeHighlighted('node1')).toBe(true);
      
      // Advance time past duration
      act(() => {
        vi.advanceTimersByTime(150);
      });
      
      // Highlight should be cleared after effect completes
      expect(result.current.highlightedNodes).toHaveLength(0);
    });
  });

  describe('Other effects', () => {
    it('should create pulse effect', () => {
      const { result } = renderHook(() => 
        useGraphVisualEffects(mockNodes, mockLinks)
      );
      
      act(() => {
        result.current.pulseNodes(['node1', 'node2'], {
          duration: 500,
          repeat: 3,
          color: '#ff0000'
        });
      });
      
      const pulseEffect = result.current.activeEffects.find(e => e.type === 'pulse');
      expect(pulseEffect).toBeDefined();
      expect(pulseEffect?.targetIds).toEqual(['node1', 'node2']);
      expect(pulseEffect?.repeat).toBe(3);
      expect(pulseEffect?.params?.color).toBe('#ff0000');
    });

    it('should create ripple effect', () => {
      const { result } = renderHook(() => 
        useGraphVisualEffects(mockNodes, mockLinks)
      );
      
      act(() => {
        result.current.createRipple({ x: 100, y: 100 }, {
          duration: 1000,
          radius: 50,
          color: '#00ff00'
        });
      });
      
      const rippleEffect = result.current.activeEffects.find(e => e.type === 'ripple');
      expect(rippleEffect).toBeDefined();
      expect(rippleEffect?.params?.position).toEqual({ x: 100, y: 100 });
      expect(rippleEffect?.params?.radius).toBe(50);
    });
  });

  describe('Particle systems', () => {
    it('should add particle system', () => {
      const { result } = renderHook(() => 
        useGraphVisualEffects(mockNodes, mockLinks)
      );
      
      let systemId: string;
      act(() => {
        systemId = result.current.addParticleSystem({
          enabled: true,
          position: { x: 0, y: 0 },
          particleCount: 100,
          particleSize: 2,
          particleSpeed: 5,
          particleLifetime: 1000,
          emissionRate: 10,
          spread: 45
        });
      });
      
      expect(result.current.particleSystems).toHaveLength(1);
      expect(result.current.particleSystems[0].particleCount).toBe(100);
    });

    it('should remove particle system', () => {
      const { result } = renderHook(() => 
        useGraphVisualEffects(mockNodes, mockLinks)
      );
      
      let systemId: string;
      act(() => {
        systemId = result.current.addParticleSystem({
          enabled: true,
          position: { x: 0, y: 0 },
          particleCount: 50,
          particleSize: 2,
          particleSpeed: 5,
          particleLifetime: 1000,
          emissionRate: 10,
          spread: 45
        });
      });
      
      act(() => {
        result.current.removeParticleSystem(systemId);
      });
      
      expect(result.current.particleSystems).toHaveLength(0);
    });
  });

  describe('Visual styles', () => {
    it('should update visual style', () => {
      const onStyleChange = vi.fn();
      const { result } = renderHook(() => 
        useGraphVisualEffects(mockNodes, mockLinks, { onStyleChange })
      );
      
      act(() => {
        result.current.updateStyle({
          nodes: {
            fill: '#ff0000',
            strokeWidth: 2
          }
        });
      });
      
      expect(result.current.visualStyle.nodes?.fill).toBe('#ff0000');
      expect(result.current.visualStyle.nodes?.strokeWidth).toBe(2);
      expect(onStyleChange).toHaveBeenCalled();
    });

    it('should transition style with animation', () => {
      const { result } = renderHook(() => 
        useGraphVisualEffects(mockNodes, mockLinks)
      );
      
      act(() => {
        result.current.transitionStyle({
          nodes: { opacity: 0.5 }
        }, {
          duration: 500,
          easing: 'ease-in-out'
        });
      });
      
      const fadeEffect = result.current.activeEffects.find(e => e.type === 'fade');
      expect(fadeEffect).toBeDefined();
      expect(fadeEffect?.duration).toBe(500);
    });

    it('should get node style with highlights', () => {
      const { result } = renderHook(() => 
        useGraphVisualEffects(mockNodes, mockLinks, {
          defaultNodeStyle: {
            fill: '#0000ff',
            strokeWidth: 1
          }
        })
      );
      
      act(() => {
        result.current.highlightNodes(['node1']);
      });
      
      const node1Style = result.current.getNodeStyle(mockNodes[0]);
      expect(node1Style.stroke).toBe('#ff0000'); // Highlight color
      expect(node1Style.strokeWidth).toBe(2); // Doubled for highlight
      
      const node2Style = result.current.getNodeStyle(mockNodes[1]);
      expect(node2Style.fill).toBe('#0000ff'); // Default color
      expect(node2Style.strokeWidth).toBe(1); // Default width
    });

    it('should get link style with highlights', () => {
      const { result } = renderHook(() => 
        useGraphVisualEffects(mockNodes, mockLinks, {
          defaultLinkStyle: {
            stroke: '#cccccc',
            strokeWidth: 1
          }
        })
      );
      
      act(() => {
        result.current.highlightLinks(['node1-node2']);
      });
      
      const link1Style = result.current.getLinkStyle(mockLinks[0]);
      expect(link1Style.stroke).toBe('#ff0000'); // Highlight color
      expect(link1Style.strokeWidth).toBe(2); // Doubled for highlight
      
      const link2Style = result.current.getLinkStyle(mockLinks[1]);
      expect(link2Style.stroke).toBe('#cccccc'); // Default color
    });

    it('should apply function-based styles', () => {
      const { result } = renderHook(() => 
        useGraphVisualEffects(mockNodes, mockLinks, {
          defaultNodeStyle: {
            fill: (node: GraphNode) => node.node_type === 'person' ? '#ff0000' : '#0000ff',
            radius: (node: GraphNode) => node.name.length
          }
        })
      );
      
      const node1Style = result.current.getNodeStyle(mockNodes[0]); // person type
      expect(node1Style.fill).toBe('#ff0000');
      expect(node1Style.radius).toBe(mockNodes[0].name.length);
      
      const node2Style = result.current.getNodeStyle(mockNodes[1]); // organization type
      expect(node2Style.fill).toBe('#0000ff');
    });
  });

  describe('Animation control', () => {
    it('should track animation state', () => {
      const { result } = renderHook(() => 
        useGraphVisualEffects(mockNodes, mockLinks)
      );
      
      expect(result.current.isAnimating).toBe(false);
      
      act(() => {
        result.current.addEffect({
          type: 'pulse',
          target: 'node',
          targetIds: ['node1'],
          duration: 1000
        });
      });
      
      expect(result.current.isAnimating).toBe(true);
    });

    it('should pause and resume animations', () => {
      const { result } = renderHook(() => 
        useGraphVisualEffects(mockNodes, mockLinks)
      );
      
      act(() => {
        result.current.addEffect({
          type: 'pulse',
          target: 'node',
          targetIds: ['node1'],
          duration: 1000
        });
      });
      
      act(() => {
        result.current.pauseAnimations();
      });
      
      // Animation should be paused (we can't directly test RAF cancellation)
      
      act(() => {
        result.current.resumeAnimations();
      });
      
      // Animation should be resumed
      expect(result.current.isAnimating).toBe(true);
    });

    it('should track effect progress', () => {
      const { result } = renderHook(() => 
        useGraphVisualEffects(mockNodes, mockLinks)
      );
      
      let effectId: string;
      act(() => {
        effectId = result.current.addEffect({
          type: 'fade',
          target: 'node',
          targetIds: ['node1'],
          duration: 1000
        });
      });
      
      // Initial progress should be 0
      expect(result.current.getEffectProgress(effectId)).toBe(0);
      
      // Note: Testing actual progress would require mocking RAF and time
    });
  });
});

describe('useSimpleVisualEffects', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('should highlight nodes', () => {
    const onHighlight = vi.fn();
    const { result } = renderHook(() => 
      useSimpleVisualEffects(onHighlight)
    );
    
    act(() => {
      result.current.highlight(['node1', 'node2']);
    });
    
    expect(result.current.highlightedNodes).toEqual(['node1', 'node2']);
    expect(result.current.isHighlighted('node1')).toBe(true);
    expect(onHighlight).toHaveBeenCalledWith(['node1', 'node2']);
  });

  it('should auto-clear highlights after 2 seconds', () => {
    const { result } = renderHook(() => useSimpleVisualEffects());
    
    act(() => {
      result.current.highlight(['node1']);
    });
    
    expect(result.current.highlightedNodes).toEqual(['node1']);
    
    act(() => {
      vi.advanceTimersByTime(2000);
    });
    
    expect(result.current.highlightedNodes).toEqual([]);
  });

  it('should manually clear highlights', () => {
    const { result } = renderHook(() => useSimpleVisualEffects());
    
    act(() => {
      result.current.highlight(['node1', 'node2']);
    });
    
    act(() => {
      result.current.clearHighlight();
    });
    
    expect(result.current.highlightedNodes).toEqual([]);
  });
});