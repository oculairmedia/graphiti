/**
 * Graph Camera Hook
 * Handles camera controls, zoom, pan, and view management for graph visualization
 */

import { useState, useCallback, useRef, useEffect, useMemo } from 'react';
import { GraphNode } from '../api/types';

/**
 * Camera state
 */
export interface CameraState {
  zoom: number;
  position: { x: number; y: number };
  rotation: number;
  minZoom: number;
  maxZoom: number;
  bounds: {
    minX: number;
    maxX: number;
    minY: number;
    maxY: number;
  } | null;
}

/**
 * Camera animation
 */
export interface CameraAnimation {
  targetZoom?: number;
  targetPosition?: { x: number; y: number };
  targetRotation?: number;
  duration: number;
  easing?: 'linear' | 'ease-in' | 'ease-out' | 'ease-in-out';
  onComplete?: () => void;
}

/**
 * Camera preset
 */
export interface CameraPreset {
  name: string;
  zoom: number;
  position: { x: number; y: number };
  rotation?: number;
}

/**
 * Camera controls
 */
export interface CameraControls {
  // Basic controls
  zoomIn: (factor?: number) => void;
  zoomOut: (factor?: number) => void;
  zoomTo: (level: number, animate?: boolean) => void;
  pan: (deltaX: number, deltaY: number) => void;
  panTo: (x: number, y: number, animate?: boolean) => void;
  rotate: (angle: number) => void;
  rotateTo: (angle: number, animate?: boolean) => void;
  reset: (animate?: boolean) => void;
  
  // Fit to content
  fitToView: (padding?: number, animate?: boolean) => void;
  fitToNodes: (nodes: GraphNode[], padding?: number, animate?: boolean) => void;
  centerOnNode: (nodeId: string, zoom?: number, animate?: boolean) => void;
  centerOnNodes: (nodeIds: string[], padding?: number, animate?: boolean) => void;
  
  // Animation
  animateTo: (animation: CameraAnimation) => void;
  stopAnimation: () => void;
  
  // Presets
  savePreset: (name: string) => void;
  loadPreset: (name: string, animate?: boolean) => void;
  deletePreset: (name: string) => void;
}

/**
 * Hook configuration
 */
export interface UseGraphCameraConfig {
  // Initial state
  initialZoom?: number;
  initialPosition?: { x: number; y: number };
  initialRotation?: number;
  
  // Zoom limits
  minZoom?: number;
  maxZoom?: number;
  zoomStep?: number;
  
  // Pan limits
  enableBounds?: boolean;
  bounds?: CameraState['bounds'];
  
  // Controls
  enableZoom?: boolean;
  enablePan?: boolean;
  enableRotation?: boolean;
  enableKeyboardControls?: boolean;
  enableMouseWheel?: boolean;
  enableTouchGestures?: boolean;
  
  // Animation
  animationDuration?: number;
  animationEasing?: CameraAnimation['easing'];
  
  // Callbacks
  onZoomChange?: (zoom: number) => void;
  onPositionChange?: (position: { x: number; y: number }) => void;
  onRotationChange?: (rotation: number) => void;
  onAnimationStart?: () => void;
  onAnimationComplete?: () => void;
  
  // Persistence
  persistState?: boolean;
  storageKey?: string;
  
  // Debug
  debug?: boolean;
}

/**
 * Easing functions
 */
const easingFunctions = {
  linear: (t: number) => t,
  'ease-in': (t: number) => t * t,
  'ease-out': (t: number) => t * (2 - t),
  'ease-in-out': (t: number) => t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t
};

/**
 * Graph Camera Hook
 */
export function useGraphCamera(
  nodes: GraphNode[],
  config: UseGraphCameraConfig = {}
) {
  const {
    initialZoom = 1,
    initialPosition = { x: 0, y: 0 },
    initialRotation = 0,
    minZoom = 0.1,
    maxZoom = 10,
    zoomStep = 0.1,
    enableBounds = false,
    bounds = null,
    enableZoom = true,
    enablePan = true,
    enableRotation = false,
    enableKeyboardControls = true,
    enableMouseWheel = true,
    enableTouchGestures = true,
    animationDuration = 300,
    animationEasing = 'ease-in-out',
    onZoomChange,
    onPositionChange,
    onRotationChange,
    onAnimationStart,
    onAnimationComplete,
    persistState = false,
    storageKey = 'graph-camera',
    debug = false
  } = config;

  // Camera state
  const [cameraState, setCameraState] = useState<CameraState>(() => {
    // Load persisted state if enabled
    if (persistState && typeof window !== 'undefined') {
      try {
        const saved = localStorage.getItem(storageKey);
        if (saved) {
          const parsed = JSON.parse(saved);
          return {
            ...parsed,
            minZoom,
            maxZoom,
            bounds: bounds || parsed.bounds
          };
        }
      } catch (e) {
        console.error('Failed to load camera state:', e);
      }
    }
    
    return {
      zoom: initialZoom,
      position: initialPosition,
      rotation: initialRotation,
      minZoom,
      maxZoom,
      bounds
    };
  });

  // Animation state
  const animationRef = useRef<{
    active: boolean;
    startTime: number;
    startState: Partial<CameraState>;
    targetState: Partial<CameraState>;
    duration: number;
    easing: CameraAnimation['easing'];
    onComplete?: () => void;
    animationFrame?: number;
  } | null>(null);

  // Presets storage
  const presetsRef = useRef<Map<string, CameraPreset>>(new Map());

  // Node positions cache
  const nodePositionsRef = useRef<Map<string, { x: number; y: number }>>(new Map());

  /**
   * Log debug message
   */
  const log = useCallback((message: string, ...args: any[]) => {
    if (debug) {
      console.debug(`[useGraphCamera] ${message}`, ...args);
    }
  }, [debug]);

  /**
   * Update node positions cache
   */
  useEffect(() => {
    nodePositionsRef.current.clear();
    nodes.forEach(node => {
      if (node.x !== undefined && node.y !== undefined) {
        nodePositionsRef.current.set(node.id, { x: node.x, y: node.y });
      }
    });
  }, [nodes]);

  /**
   * Clamp value between min and max
   */
  const clamp = (value: number, min: number, max: number): number => {
    return Math.min(Math.max(value, min), max);
  };

  /**
   * Apply bounds to position
   */
  const applyBounds = useCallback((position: { x: number; y: number }): { x: number; y: number } => {
    if (!enableBounds || !cameraState.bounds) {
      return position;
    }
    
    return {
      x: clamp(position.x, cameraState.bounds.minX, cameraState.bounds.maxX),
      y: clamp(position.y, cameraState.bounds.minY, cameraState.bounds.maxY)
    };
  }, [enableBounds, cameraState.bounds]);

  /**
   * Update camera state
   */
  const updateCameraState = useCallback((updates: Partial<CameraState>) => {
    setCameraState(prev => {
      const newState = { ...prev };
      
      if (updates.zoom !== undefined && enableZoom) {
        newState.zoom = clamp(updates.zoom, prev.minZoom, prev.maxZoom);
        if (onZoomChange && newState.zoom !== prev.zoom) {
          onZoomChange(newState.zoom);
        }
      }
      
      if (updates.position !== undefined && enablePan) {
        newState.position = applyBounds(updates.position);
        if (onPositionChange && 
            (newState.position.x !== prev.position.x || 
             newState.position.y !== prev.position.y)) {
          onPositionChange(newState.position);
        }
      }
      
      if (updates.rotation !== undefined && enableRotation) {
        newState.rotation = updates.rotation % 360;
        if (onRotationChange && newState.rotation !== prev.rotation) {
          onRotationChange(newState.rotation);
        }
      }
      
      return newState;
    });
  }, [enableZoom, enablePan, enableRotation, applyBounds, onZoomChange, onPositionChange, onRotationChange]);

  /**
   * Animate camera
   */
  const animate = useCallback(() => {
    const animation = animationRef.current;
    if (!animation || !animation.active) return;
    
    const now = Date.now();
    const elapsed = now - animation.startTime;
    const progress = Math.min(elapsed / animation.duration, 1);
    
    // Apply easing
    const easedProgress = easingFunctions[animation.easing || 'linear'](progress);
    
    // Interpolate values
    const updates: Partial<CameraState> = {};
    
    if (animation.startState.zoom !== undefined && animation.targetState.zoom !== undefined) {
      updates.zoom = animation.startState.zoom + 
        (animation.targetState.zoom - animation.startState.zoom) * easedProgress;
    }
    
    if (animation.startState.position && animation.targetState.position) {
      updates.position = {
        x: animation.startState.position.x + 
          (animation.targetState.position.x - animation.startState.position.x) * easedProgress,
        y: animation.startState.position.y + 
          (animation.targetState.position.y - animation.startState.position.y) * easedProgress
      };
    }
    
    if (animation.startState.rotation !== undefined && animation.targetState.rotation !== undefined) {
      updates.rotation = animation.startState.rotation + 
        (animation.targetState.rotation - animation.startState.rotation) * easedProgress;
    }
    
    updateCameraState(updates);
    
    if (progress < 1) {
      animation.animationFrame = requestAnimationFrame(animate);
    } else {
      animation.active = false;
      if (animation.onComplete) {
        animation.onComplete();
      }
      if (onAnimationComplete) {
        onAnimationComplete();
      }
    }
  }, [updateCameraState, onAnimationComplete]);

  /**
   * Start animation
   */
  const startAnimation = useCallback((
    targetState: Partial<CameraState>,
    duration: number = animationDuration,
    easing: CameraAnimation['easing'] = animationEasing,
    onComplete?: () => void
  ) => {
    // Cancel current animation
    if (animationRef.current?.animationFrame) {
      cancelAnimationFrame(animationRef.current.animationFrame);
    }
    
    animationRef.current = {
      active: true,
      startTime: Date.now(),
      startState: {
        zoom: cameraState.zoom,
        position: { ...cameraState.position },
        rotation: cameraState.rotation
      },
      targetState,
      duration,
      easing,
      onComplete
    };
    
    if (onAnimationStart) {
      onAnimationStart();
    }
    
    animate();
  }, [cameraState, animationDuration, animationEasing, animate, onAnimationStart]);

  /**
   * Stop animation
   */
  const stopAnimation = useCallback(() => {
    if (animationRef.current) {
      animationRef.current.active = false;
      if (animationRef.current.animationFrame) {
        cancelAnimationFrame(animationRef.current.animationFrame);
      }
      animationRef.current = null;
    }
  }, []);

  /**
   * Camera controls implementation
   */
  const controls: CameraControls = useMemo(() => ({
    zoomIn: (factor = 1 + zoomStep) => {
      log(`Zooming in by factor ${factor}`);
      updateCameraState({ zoom: cameraState.zoom * factor });
    },
    
    zoomOut: (factor = 1 - zoomStep) => {
      log(`Zooming out by factor ${factor}`);
      updateCameraState({ zoom: cameraState.zoom * factor });
    },
    
    zoomTo: (level: number, animate = true) => {
      log(`Zooming to level ${level}`);
      if (animate) {
        startAnimation({ zoom: level });
      } else {
        updateCameraState({ zoom: level });
      }
    },
    
    pan: (deltaX: number, deltaY: number) => {
      log(`Panning by ${deltaX}, ${deltaY}`);
      updateCameraState({
        position: {
          x: cameraState.position.x + deltaX,
          y: cameraState.position.y + deltaY
        }
      });
    },
    
    panTo: (x: number, y: number, animate = true) => {
      log(`Panning to ${x}, ${y}`);
      if (animate) {
        startAnimation({ position: { x, y } });
      } else {
        updateCameraState({ position: { x, y } });
      }
    },
    
    rotate: (angle: number) => {
      log(`Rotating by ${angle} degrees`);
      updateCameraState({ rotation: cameraState.rotation + angle });
    },
    
    rotateTo: (angle: number, animate = true) => {
      log(`Rotating to ${angle} degrees`);
      if (animate) {
        startAnimation({ rotation: angle });
      } else {
        updateCameraState({ rotation: angle });
      }
    },
    
    reset: (animate = true) => {
      log('Resetting camera');
      const target = {
        zoom: initialZoom,
        position: initialPosition,
        rotation: initialRotation
      };
      
      if (animate) {
        startAnimation(target);
      } else {
        updateCameraState(target);
      }
    },
    
    fitToView: (padding = 50, animate = true) => {
      log('Fitting to view');
      
      if (nodes.length === 0) return;
      
      // Calculate bounding box
      let minX = Infinity, maxX = -Infinity;
      let minY = Infinity, maxY = -Infinity;
      
      nodes.forEach(node => {
        const pos = nodePositionsRef.current.get(node.id);
        if (pos) {
          minX = Math.min(minX, pos.x);
          maxX = Math.max(maxX, pos.x);
          minY = Math.min(minY, pos.y);
          maxY = Math.max(maxY, pos.y);
        }
      });
      
      if (minX === Infinity) return;
      
      const width = maxX - minX + padding * 2;
      const height = maxY - minY + padding * 2;
      const centerX = (minX + maxX) / 2;
      const centerY = (minY + maxY) / 2;
      
      // Calculate zoom to fit
      // This is simplified - actual calculation depends on viewport size
      const zoom = Math.min(1000 / width, 1000 / height);
      
      const target = {
        zoom: clamp(zoom, minZoom, maxZoom),
        position: { x: centerX, y: centerY }
      };
      
      if (animate) {
        startAnimation(target);
      } else {
        updateCameraState(target);
      }
    },
    
    fitToNodes: (targetNodes: GraphNode[], padding = 50, animate = true) => {
      log(`Fitting to ${targetNodes.length} nodes`);
      
      if (targetNodes.length === 0) return;
      
      // Calculate bounding box for specific nodes
      let minX = Infinity, maxX = -Infinity;
      let minY = Infinity, maxY = -Infinity;
      
      targetNodes.forEach(node => {
        const pos = nodePositionsRef.current.get(node.id);
        if (pos) {
          minX = Math.min(minX, pos.x);
          maxX = Math.max(maxX, pos.x);
          minY = Math.min(minY, pos.y);
          maxY = Math.max(maxY, pos.y);
        }
      });
      
      if (minX === Infinity) return;
      
      const width = maxX - minX + padding * 2;
      const height = maxY - minY + padding * 2;
      const centerX = (minX + maxX) / 2;
      const centerY = (minY + maxY) / 2;
      
      const zoom = Math.min(1000 / width, 1000 / height);
      
      const target = {
        zoom: clamp(zoom, minZoom, maxZoom),
        position: { x: centerX, y: centerY }
      };
      
      if (animate) {
        startAnimation(target);
      } else {
        updateCameraState(target);
      }
    },
    
    centerOnNode: (nodeId: string, zoom?: number, animate = true) => {
      log(`Centering on node ${nodeId}`);
      
      const pos = nodePositionsRef.current.get(nodeId);
      if (!pos) {
        log(`Node ${nodeId} not found`);
        return;
      }
      
      const target: Partial<CameraState> = {
        position: pos
      };
      
      if (zoom !== undefined) {
        target.zoom = zoom;
      }
      
      if (animate) {
        startAnimation(target);
      } else {
        updateCameraState(target);
      }
    },
    
    centerOnNodes: (nodeIds: string[], padding = 50, animate = true) => {
      log(`Centering on ${nodeIds.length} nodes`);
      
      const positions = nodeIds
        .map(id => nodePositionsRef.current.get(id))
        .filter(pos => pos !== undefined) as { x: number; y: number }[];
      
      if (positions.length === 0) return;
      
      // Calculate center
      const centerX = positions.reduce((sum, pos) => sum + pos.x, 0) / positions.length;
      const centerY = positions.reduce((sum, pos) => sum + pos.y, 0) / positions.length;
      
      // Calculate zoom to fit all nodes
      let minX = Infinity, maxX = -Infinity;
      let minY = Infinity, maxY = -Infinity;
      
      positions.forEach(pos => {
        minX = Math.min(minX, pos.x);
        maxX = Math.max(maxX, pos.x);
        minY = Math.min(minY, pos.y);
        maxY = Math.max(maxY, pos.y);
      });
      
      const width = maxX - minX + padding * 2;
      const height = maxY - minY + padding * 2;
      const zoom = Math.min(1000 / width, 1000 / height);
      
      const target = {
        zoom: clamp(zoom, minZoom, maxZoom),
        position: { x: centerX, y: centerY }
      };
      
      if (animate) {
        startAnimation(target);
      } else {
        updateCameraState(target);
      }
    },
    
    animateTo: (animation: CameraAnimation) => {
      log('Starting custom animation');
      const target: Partial<CameraState> = {};
      
      if (animation.targetZoom !== undefined) {
        target.zoom = animation.targetZoom;
      }
      if (animation.targetPosition) {
        target.position = animation.targetPosition;
      }
      if (animation.targetRotation !== undefined) {
        target.rotation = animation.targetRotation;
      }
      
      startAnimation(target, animation.duration, animation.easing, animation.onComplete);
    },
    
    stopAnimation,
    
    savePreset: (name: string) => {
      log(`Saving preset: ${name}`);
      presetsRef.current.set(name, {
        name,
        zoom: cameraState.zoom,
        position: { ...cameraState.position },
        rotation: cameraState.rotation
      });
    },
    
    loadPreset: (name: string, animate = true) => {
      log(`Loading preset: ${name}`);
      const preset = presetsRef.current.get(name);
      if (!preset) {
        log(`Preset ${name} not found`);
        return;
      }
      
      const target = {
        zoom: preset.zoom,
        position: preset.position,
        rotation: preset.rotation || 0
      };
      
      if (animate) {
        startAnimation(target);
      } else {
        updateCameraState(target);
      }
    },
    
    deletePreset: (name: string) => {
      log(`Deleting preset: ${name}`);
      presetsRef.current.delete(name);
    }
  }), [
    cameraState, 
    nodes,
    initialZoom, 
    initialPosition, 
    initialRotation,
    minZoom,
    maxZoom,
    zoomStep,
    updateCameraState,
    startAnimation,
    stopAnimation,
    log
  ]);

  /**
   * Get viewport info
   */
  const getViewport = useCallback(() => ({
    zoom: cameraState.zoom,
    position: cameraState.position,
    rotation: cameraState.rotation,
    bounds: cameraState.bounds,
    isAnimating: animationRef.current?.active || false
  }), [cameraState]);

  /**
   * Get visible nodes
   */
  const getVisibleNodes = useCallback((viewport: { width: number; height: number }): GraphNode[] => {
    const halfWidth = viewport.width / 2 / cameraState.zoom;
    const halfHeight = viewport.height / 2 / cameraState.zoom;
    
    const visibleBounds = {
      minX: cameraState.position.x - halfWidth,
      maxX: cameraState.position.x + halfWidth,
      minY: cameraState.position.y - halfHeight,
      maxY: cameraState.position.y + halfHeight
    };
    
    return nodes.filter(node => {
      const pos = nodePositionsRef.current.get(node.id);
      if (!pos) return false;
      
      return pos.x >= visibleBounds.minX &&
             pos.x <= visibleBounds.maxX &&
             pos.y >= visibleBounds.minY &&
             pos.y <= visibleBounds.maxY;
    });
  }, [cameraState, nodes]);

  /**
   * Screen to world coordinates
   */
  const screenToWorld = useCallback((screenX: number, screenY: number, viewport: { width: number; height: number }) => {
    const worldX = (screenX - viewport.width / 2) / cameraState.zoom + cameraState.position.x;
    const worldY = (screenY - viewport.height / 2) / cameraState.zoom + cameraState.position.y;
    
    // Apply rotation if enabled
    if (cameraState.rotation !== 0) {
      const rad = -cameraState.rotation * Math.PI / 180;
      const cos = Math.cos(rad);
      const sin = Math.sin(rad);
      const dx = worldX - cameraState.position.x;
      const dy = worldY - cameraState.position.y;
      
      return {
        x: cameraState.position.x + dx * cos - dy * sin,
        y: cameraState.position.y + dx * sin + dy * cos
      };
    }
    
    return { x: worldX, y: worldY };
  }, [cameraState]);

  /**
   * World to screen coordinates
   */
  const worldToScreen = useCallback((worldX: number, worldY: number, viewport: { width: number; height: number }) => {
    let x = worldX;
    let y = worldY;
    
    // Apply rotation if enabled
    if (cameraState.rotation !== 0) {
      const rad = cameraState.rotation * Math.PI / 180;
      const cos = Math.cos(rad);
      const sin = Math.sin(rad);
      const dx = worldX - cameraState.position.x;
      const dy = worldY - cameraState.position.y;
      
      x = cameraState.position.x + dx * cos - dy * sin;
      y = cameraState.position.y + dx * sin + dy * cos;
    }
    
    return {
      x: (x - cameraState.position.x) * cameraState.zoom + viewport.width / 2,
      y: (y - cameraState.position.y) * cameraState.zoom + viewport.height / 2
    };
  }, [cameraState]);

  // Keyboard controls
  useEffect(() => {
    if (!enableKeyboardControls) return;
    
    const handleKeyDown = (e: KeyboardEvent) => {
      switch (e.key) {
        case '+':
        case '=':
          controls.zoomIn();
          break;
        case '-':
        case '_':
          controls.zoomOut();
          break;
        case '0':
          if (e.ctrlKey || e.metaKey) {
            e.preventDefault();
            controls.reset(true);
          }
          break;
        case 'ArrowUp':
          controls.pan(0, -10);
          break;
        case 'ArrowDown':
          controls.pan(0, 10);
          break;
        case 'ArrowLeft':
          controls.pan(-10, 0);
          break;
        case 'ArrowRight':
          controls.pan(10, 0);
          break;
        case 'f':
          if (e.ctrlKey || e.metaKey) {
            e.preventDefault();
            controls.fitToView(50, true);
          }
          break;
      }
    };
    
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [enableKeyboardControls, controls]);

  // Persist state
  useEffect(() => {
    if (persistState && typeof window !== 'undefined') {
      const toSave = {
        zoom: cameraState.zoom,
        position: cameraState.position,
        rotation: cameraState.rotation,
        bounds: cameraState.bounds
      };
      
      try {
        localStorage.setItem(storageKey, JSON.stringify(toSave));
      } catch (e) {
        console.error('Failed to persist camera state:', e);
      }
    }
  }, [persistState, storageKey, cameraState]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      stopAnimation();
    };
  }, [stopAnimation]);

  return {
    // Camera state
    cameraState,
    zoom: cameraState.zoom,
    position: cameraState.position,
    rotation: cameraState.rotation,
    
    // Controls
    controls,
    ...controls,
    
    // Viewport utilities
    getViewport,
    getVisibleNodes,
    screenToWorld,
    worldToScreen,
    
    // Presets
    presets: Array.from(presetsRef.current.values()),
    
    // Animation state
    isAnimating: animationRef.current?.active || false
  };
}

/**
 * Simple camera hook for basic pan and zoom
 */
export function useSimpleCamera(initialZoom: number = 1) {
  const [zoom, setZoom] = useState(initialZoom);
  const [position, setPosition] = useState({ x: 0, y: 0 });
  
  const zoomIn = useCallback(() => setZoom(z => Math.min(z * 1.2, 10)), []);
  const zoomOut = useCallback(() => setZoom(z => Math.max(z * 0.8, 0.1)), []);
  const pan = useCallback((dx: number, dy: number) => {
    setPosition(p => ({ x: p.x + dx, y: p.y + dy }));
  }, []);
  const reset = useCallback(() => {
    setZoom(initialZoom);
    setPosition({ x: 0, y: 0 });
  }, [initialZoom]);
  
  return {
    zoom,
    position,
    zoomIn,
    zoomOut,
    pan,
    reset
  };
}