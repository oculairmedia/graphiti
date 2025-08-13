/**
 * Graph Visual Effects Hook
 * Handles visual effects, animations, transitions, and particle effects for graph visualization
 */

import { useState, useCallback, useRef, useEffect, useMemo } from 'react';
import { GraphNode } from '../api/types';
import { GraphLink } from '../types/graph';

/**
 * Effect types
 */
export type EffectType = 
  | 'highlight'
  | 'pulse'
  | 'glow'
  | 'fade'
  | 'ripple'
  | 'particle'
  | 'trail'
  | 'shake'
  | 'bounce'
  | 'spin';

/**
 * Animation easing types
 */
export type EasingType = 
  | 'linear'
  | 'ease-in'
  | 'ease-out'
  | 'ease-in-out'
  | 'bounce'
  | 'elastic'
  | 'back';

/**
 * Visual effect configuration
 */
export interface VisualEffect {
  id: string;
  type: EffectType;
  target: 'node' | 'link' | 'cluster';
  targetIds: string[];
  duration: number;
  delay?: number;
  easing?: EasingType;
  repeat?: number | 'infinite';
  params?: Record<string, any>;
  onComplete?: () => void;
}

/**
 * Particle system configuration
 */
export interface ParticleSystem {
  id: string;
  enabled: boolean;
  position: { x: number; y: number };
  particleCount: number;
  particleSize: number;
  particleSpeed: number;
  particleLifetime: number;
  emissionRate: number;
  spread: number;
  gravity?: { x: number; y: number };
  color?: string | string[];
  shape?: 'circle' | 'square' | 'star';
}

/**
 * Transition configuration
 */
export interface TransitionConfig {
  duration: number;
  easing: EasingType;
  stagger?: number;
  cascade?: boolean;
}

/**
 * Visual style
 */
export interface VisualStyle {
  nodes?: {
    fill?: string | ((node: GraphNode) => string);
    stroke?: string | ((node: GraphNode) => string);
    strokeWidth?: number;
    opacity?: number;
    radius?: number | ((node: GraphNode) => number);
    shape?: 'circle' | 'square' | 'diamond' | 'hexagon';
  };
  links?: {
    stroke?: string | ((link: GraphLink) => string);
    strokeWidth?: number | ((link: GraphLink) => number);
    opacity?: number;
    dashArray?: string;
    arrowSize?: number;
  };
  labels?: {
    fontSize?: number;
    fontFamily?: string;
    color?: string;
    background?: boolean;
    backgroundColor?: string;
  };
}

/**
 * Hook configuration
 */
export interface UseGraphVisualEffectsConfig {
  // Enable/disable effects
  enabled?: boolean;
  
  // Performance
  maxConcurrentEffects?: number;
  useGPU?: boolean;
  quality?: 'low' | 'medium' | 'high';
  
  // Default styles
  defaultNodeStyle?: VisualStyle['nodes'];
  defaultLinkStyle?: VisualStyle['links'];
  defaultLabelStyle?: VisualStyle['labels'];
  
  // Transitions
  defaultTransition?: TransitionConfig;
  
  // Callbacks
  onEffectStart?: (effect: VisualEffect) => void;
  onEffectComplete?: (effect: VisualEffect) => void;
  onStyleChange?: (style: VisualStyle) => void;
  
  // Debug
  debug?: boolean;
}

/**
 * Animation frame data
 */
interface AnimationFrame {
  effect: VisualEffect;
  startTime: number;
  currentTime: number;
  progress: number;
  iteration: number;
}

/**
 * Easing functions
 */
const easingFunctions: Record<EasingType, (t: number) => number> = {
  linear: (t) => t,
  'ease-in': (t) => t * t,
  'ease-out': (t) => t * (2 - t),
  'ease-in-out': (t) => t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t,
  bounce: (t) => {
    const n1 = 7.5625;
    const d1 = 2.75;
    if (t < 1 / d1) {
      return n1 * t * t;
    } else if (t < 2 / d1) {
      return n1 * (t -= 1.5 / d1) * t + 0.75;
    } else if (t < 2.5 / d1) {
      return n1 * (t -= 2.25 / d1) * t + 0.9375;
    } else {
      return n1 * (t -= 2.625 / d1) * t + 0.984375;
    }
  },
  elastic: (t) => {
    if (t === 0 || t === 1) return t;
    const p = 0.3;
    const s = p / 4;
    return Math.pow(2, -10 * t) * Math.sin((t - s) * (2 * Math.PI) / p) + 1;
  },
  back: (t) => {
    const c1 = 1.70158;
    const c3 = c1 + 1;
    return c3 * t * t * t - c1 * t * t;
  }
};

/**
 * Graph Visual Effects Hook
 */
export function useGraphVisualEffects(
  nodes: GraphNode[],
  links: GraphLink[],
  config: UseGraphVisualEffectsConfig = {}
) {
  const {
    enabled = true,
    maxConcurrentEffects = 10,
    useGPU = true,
    quality = 'medium',
    defaultNodeStyle = {},
    defaultLinkStyle = {},
    defaultLabelStyle = {},
    defaultTransition = { duration: 300, easing: 'ease-in-out' },
    onEffectStart,
    onEffectComplete,
    onStyleChange,
    debug = false
  } = config;

  // Active effects
  const [activeEffects, setActiveEffects] = useState<Map<string, VisualEffect>>(new Map());
  const [particleSystems, setParticleSystems] = useState<Map<string, ParticleSystem>>(new Map());
  
  // Visual styles
  const [visualStyle, setVisualStyle] = useState<VisualStyle>({
    nodes: defaultNodeStyle,
    links: defaultLinkStyle,
    labels: defaultLabelStyle
  });

  // Animation tracking
  const animationFramesRef = useRef<Map<string, AnimationFrame>>(new Map());
  const rafRef = useRef<number | null>(null);
  
  // Effect queue
  const effectQueueRef = useRef<VisualEffect[]>([]);
  
  // Highlighted elements
  const [highlightedNodes, setHighlightedNodes] = useState<Set<string>>(new Set());
  const [highlightedLinks, setHighlightedLinks] = useState<Set<string>>(new Set());

  /**
   * Log debug message
   */
  const log = useCallback((message: string, ...args: any[]) => {
    if (debug) {
      console.debug(`[useGraphVisualEffects] ${message}`, ...args);
    }
  }, [debug]);

  /**
   * Generate effect ID
   */
  const generateEffectId = useCallback(() => {
    return `effect-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  }, []);

  /**
   * Apply easing to progress
   */
  const applyEasing = useCallback((progress: number, easing: EasingType = 'linear'): number => {
    return easingFunctions[easing](progress);
  }, []);

  /**
   * Add visual effect
   */
  const addEffect = useCallback((effect: Omit<VisualEffect, 'id'>): string => {
    if (!enabled) return '';
    
    const id = generateEffectId();
    const fullEffect: VisualEffect = { ...effect, id };
    
    setActiveEffects(prev => {
      // Check concurrent effects limit
      if (prev.size >= maxConcurrentEffects) {
        log(`Queueing effect ${id} (max concurrent effects reached)`);
        effectQueueRef.current.push(fullEffect);
        return prev;
      }
      
      log(`Adding effect ${id} of type ${effect.type}`);
      
      // Initialize animation frame
      animationFramesRef.current.set(id, {
        effect: fullEffect,
        startTime: Date.now() + (effect.delay || 0),
        currentTime: Date.now(),
        progress: 0,
        iteration: 0
      });
      
      if (onEffectStart) {
        onEffectStart(fullEffect);
      }
      
      return new Map(prev).set(id, fullEffect);
    });
    
    return id;
  }, [enabled, maxConcurrentEffects, generateEffectId, onEffectStart, log]);

  /**
   * Remove visual effect
   */
  const removeEffect = useCallback((effectId: string) => {
    log(`Removing effect ${effectId}`);
    
    setActiveEffects(prev => {
      const next = new Map(prev);
      const effect = next.get(effectId);
      
      if (effect && onEffectComplete) {
        onEffectComplete(effect);
      }
      
      next.delete(effectId);
      return next;
    });
    
    animationFramesRef.current.delete(effectId);
    
    // Process queued effects
    if (effectQueueRef.current.length > 0) {
      const nextEffect = effectQueueRef.current.shift();
      if (nextEffect) {
        addEffect(nextEffect);
      }
    }
  }, [onEffectComplete, addEffect, log]);

  /**
   * Clear all effects
   */
  const clearEffects = useCallback(() => {
    log('Clearing all effects');
    
    activeEffects.forEach(effect => {
      if (onEffectComplete) {
        onEffectComplete(effect);
      }
    });
    
    setActiveEffects(new Map());
    animationFramesRef.current.clear();
    effectQueueRef.current = [];
  }, [activeEffects, onEffectComplete, log]);

  /**
   * Highlight nodes
   */
  const highlightNodes = useCallback((nodeIds: string[], duration: number = 1000) => {
    log(`Highlighting ${nodeIds.length} nodes`);
    
    setHighlightedNodes(new Set(nodeIds));
    
    return addEffect({
      type: 'highlight',
      target: 'node',
      targetIds: nodeIds,
      duration,
      onComplete: () => setHighlightedNodes(new Set())
    });
  }, [addEffect, log]);

  /**
   * Highlight links
   */
  const highlightLinks = useCallback((linkIds: string[], duration: number = 1000) => {
    log(`Highlighting ${linkIds.length} links`);
    
    setHighlightedLinks(new Set(linkIds));
    
    return addEffect({
      type: 'highlight',
      target: 'link',
      targetIds: linkIds,
      duration,
      onComplete: () => setHighlightedLinks(new Set())
    });
  }, [addEffect, log]);

  /**
   * Pulse effect
   */
  const pulseNodes = useCallback((nodeIds: string[], options?: {
    duration?: number;
    repeat?: number;
    color?: string;
  }) => {
    return addEffect({
      type: 'pulse',
      target: 'node',
      targetIds: nodeIds,
      duration: options?.duration || 1000,
      repeat: options?.repeat || 3,
      params: { color: options?.color }
    });
  }, [addEffect]);

  /**
   * Ripple effect
   */
  const createRipple = useCallback((position: { x: number; y: number }, options?: {
    duration?: number;
    radius?: number;
    color?: string;
  }) => {
    return addEffect({
      type: 'ripple',
      target: 'node',
      targetIds: [],
      duration: options?.duration || 1000,
      params: {
        position,
        radius: options?.radius || 100,
        color: options?.color || '#007bff'
      }
    });
  }, [addEffect]);

  /**
   * Add particle system
   */
  const addParticleSystem = useCallback((config: Omit<ParticleSystem, 'id'>): string => {
    const id = generateEffectId();
    const system: ParticleSystem = { ...config, id };
    
    log(`Adding particle system ${id}`);
    
    setParticleSystems(prev => new Map(prev).set(id, system));
    
    return id;
  }, [generateEffectId, log]);

  /**
   * Remove particle system
   */
  const removeParticleSystem = useCallback((systemId: string) => {
    log(`Removing particle system ${systemId}`);
    
    setParticleSystems(prev => {
      const next = new Map(prev);
      next.delete(systemId);
      return next;
    });
  }, [log]);

  /**
   * Update visual style
   */
  const updateStyle = useCallback((updates: Partial<VisualStyle>) => {
    log('Updating visual style');
    
    setVisualStyle(prev => {
      const next = { ...prev, ...updates };
      
      if (onStyleChange) {
        onStyleChange(next);
      }
      
      return next;
    });
  }, [onStyleChange, log]);

  /**
   * Animate style transition
   */
  const transitionStyle = useCallback((
    newStyle: Partial<VisualStyle>,
    transition: TransitionConfig = defaultTransition
  ) => {
    log('Transitioning visual style');
    
    return addEffect({
      type: 'fade',
      target: 'node',
      targetIds: nodes.map(n => n.id),
      duration: transition.duration,
      easing: transition.easing,
      params: { newStyle },
      onComplete: () => updateStyle(newStyle)
    });
  }, [nodes, defaultTransition, addEffect, updateStyle, log]);

  /**
   * Get node style
   */
  const getNodeStyle = useCallback((node: GraphNode): any => {
    const baseStyle = { ...visualStyle.nodes };
    
    // Apply function-based styles
    if (typeof baseStyle.fill === 'function') {
      baseStyle.fill = baseStyle.fill(node);
    }
    if (typeof baseStyle.stroke === 'function') {
      baseStyle.stroke = baseStyle.stroke(node);
    }
    if (typeof baseStyle.radius === 'function') {
      baseStyle.radius = baseStyle.radius(node);
    }
    
    // Apply highlight
    if (highlightedNodes.has(node.id)) {
      baseStyle.stroke = '#ff0000';
      baseStyle.strokeWidth = (baseStyle.strokeWidth || 1) * 2;
      baseStyle.opacity = 1;
    }
    
    return baseStyle;
  }, [visualStyle.nodes, highlightedNodes]);

  /**
   * Get link style
   */
  const getLinkStyle = useCallback((link: GraphLink): any => {
    const baseStyle = { ...visualStyle.links };
    
    // Apply function-based styles
    if (typeof baseStyle.stroke === 'function') {
      baseStyle.stroke = baseStyle.stroke(link);
    }
    if (typeof baseStyle.strokeWidth === 'function') {
      baseStyle.strokeWidth = baseStyle.strokeWidth(link);
    }
    
    // Apply highlight
    if (highlightedLinks.has(`${link.source}-${link.target}`)) {
      baseStyle.stroke = '#ff0000';
      baseStyle.strokeWidth = (baseStyle.strokeWidth || 1) * 2;
      baseStyle.opacity = 1;
    }
    
    return baseStyle;
  }, [visualStyle.links, highlightedLinks]);

  /**
   * Animation loop
   */
  const animate = useCallback(() => {
    const now = Date.now();
    const completedEffects: string[] = [];
    
    animationFramesRef.current.forEach((frame, effectId) => {
      const elapsed = now - frame.startTime;
      
      if (elapsed < 0) return; // Effect hasn't started yet (delay)
      
      const duration = frame.effect.duration;
      let progress = Math.min(elapsed / duration, 1);
      
      // Apply easing
      progress = applyEasing(progress, frame.effect.easing);
      
      // Update frame
      frame.currentTime = now;
      frame.progress = progress;
      
      // Check if effect is complete
      if (progress >= 1) {
        if (frame.effect.repeat === 'infinite') {
          // Reset for infinite repeat
          frame.startTime = now;
          frame.iteration++;
        } else if (typeof frame.effect.repeat === 'number' && frame.iteration < frame.effect.repeat - 1) {
          // Reset for finite repeat
          frame.startTime = now;
          frame.iteration++;
        } else {
          // Effect is complete
          completedEffects.push(effectId);
          
          // Call onComplete callback if present
          if (frame.effect.onComplete) {
            frame.effect.onComplete();
          }
        }
      }
    });
    
    // Remove completed effects
    completedEffects.forEach(removeEffect);
    
    // Continue animation if there are still active effects or frames
    if (activeEffects.size > 0 || animationFramesRef.current.size > 0) {
      rafRef.current = requestAnimationFrame(animate);
    } else {
      rafRef.current = null;
    }
  }, [applyEasing, removeEffect, activeEffects.size]);

  /**
   * Start animation loop when effects are added
   */
  useEffect(() => {
    if (activeEffects.size > 0 && !rafRef.current) {
      rafRef.current = requestAnimationFrame(animate);
    }
  }, [activeEffects.size, animate]);

  /**
   * Cleanup on unmount
   */
  useEffect(() => {
    return () => {
      if (rafRef.current) {
        cancelAnimationFrame(rafRef.current);
      }
      clearEffects();
    };
  }, []);

  /**
   * Get effect progress
   */
  const getEffectProgress = useCallback((effectId: string): number => {
    const frame = animationFramesRef.current.get(effectId);
    return frame?.progress || 0;
  }, []);

  /**
   * Check if node is highlighted
   */
  const isNodeHighlighted = useCallback((nodeId: string): boolean => {
    return highlightedNodes.has(nodeId);
  }, [highlightedNodes]);

  /**
   * Check if link is highlighted
   */
  const isLinkHighlighted = useCallback((source: string, target: string): boolean => {
    return highlightedLinks.has(`${source}-${target}`) || highlightedLinks.has(`${target}-${source}`);
  }, [highlightedLinks]);

  return {
    // Effects
    activeEffects: Array.from(activeEffects.values()),
    addEffect,
    removeEffect,
    clearEffects,
    
    // Common effects
    highlightNodes,
    highlightLinks,
    pulseNodes,
    createRipple,
    
    // Particle systems
    particleSystems: Array.from(particleSystems.values()),
    addParticleSystem,
    removeParticleSystem,
    
    // Styles
    visualStyle,
    updateStyle,
    transitionStyle,
    getNodeStyle,
    getLinkStyle,
    
    // State checks
    isNodeHighlighted,
    isLinkHighlighted,
    highlightedNodes: Array.from(highlightedNodes),
    highlightedLinks: Array.from(highlightedLinks),
    
    // Progress tracking
    getEffectProgress,
    
    // Animation control
    isAnimating: activeEffects.size > 0,
    pauseAnimations: () => {
      if (rafRef.current) {
        cancelAnimationFrame(rafRef.current);
        rafRef.current = null;
      }
    },
    resumeAnimations: () => {
      if (!rafRef.current && activeEffects.size > 0) {
        rafRef.current = requestAnimationFrame(animate);
      }
    }
  };
}

/**
 * Simple visual effects hook
 */
export function useSimpleVisualEffects(
  onHighlight?: (nodeIds: string[]) => void
) {
  const [highlightedNodes, setHighlightedNodes] = useState<Set<string>>(new Set());
  
  const highlight = useCallback((nodeIds: string[]) => {
    setHighlightedNodes(new Set(nodeIds));
    if (onHighlight) {
      onHighlight(nodeIds);
    }
    
    // Auto-clear after 2 seconds
    setTimeout(() => {
      setHighlightedNodes(new Set());
    }, 2000);
  }, [onHighlight]);
  
  const clearHighlight = useCallback(() => {
    setHighlightedNodes(new Set());
  }, []);
  
  return {
    highlightedNodes: Array.from(highlightedNodes),
    isHighlighted: (nodeId: string) => highlightedNodes.has(nodeId),
    highlight,
    clearHighlight
  };
}