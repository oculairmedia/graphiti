import React, { useState, useCallback, useEffect, useRef } from 'react';
import { logger } from '../../../utils/logger';

interface SimulationConfig {
  gravity: number;
  repulsion: number;
  friction: number;
  linkStrength: number;
  linkDistance: number;
  theta: number;
  alpha: number;
  alphaDecay: number;
  alphaMin: number;
  velocityDecay: number;
}

interface SimulationManagerProps {
  onConfigChange?: (config: SimulationConfig) => void;
  onSimulationTick?: (alpha: number) => void;
  onSimulationEnd?: () => void;
  defaultConfig?: Partial<SimulationConfig>;
  autoStart?: boolean;
  targetFPS?: number;
}

interface SimulationState {
  isRunning: boolean;
  isPaused: boolean;
  currentAlpha: number;
  tickCount: number;
  fps: number;
}

/**
 * SimulationManager - Controls physics simulation for graph layout
 * 
 * Features:
 * - Physics parameter control
 * - Simulation play/pause/restart
 * - Performance monitoring
 * - Adaptive quality settings
 */
export const SimulationManager: React.FC<SimulationManagerProps> = ({
  onConfigChange,
  onSimulationTick,
  onSimulationEnd,
  defaultConfig = {},
  autoStart = true,
  targetFPS = 60
}) => {
  const [config, setConfig] = useState<SimulationConfig>({
    gravity: defaultConfig.gravity ?? 0,
    repulsion: defaultConfig.repulsion ?? 0.5,
    friction: defaultConfig.friction ?? 0.85,
    linkStrength: defaultConfig.linkStrength ?? 0.3,
    linkDistance: defaultConfig.linkDistance ?? 50,
    theta: defaultConfig.theta ?? 0.9,
    alpha: defaultConfig.alpha ?? 1,
    alphaDecay: defaultConfig.alphaDecay ?? 0.01,
    alphaMin: defaultConfig.alphaMin ?? 0.001,
    velocityDecay: defaultConfig.velocityDecay ?? 0.4
  });

  const [state, setState] = useState<SimulationState>({
    isRunning: autoStart,
    isPaused: false,
    currentAlpha: config.alpha,
    tickCount: 0,
    fps: 0
  });

  // Refs for animation loop
  const animationFrameRef = useRef<number | null>(null);
  const lastFrameTimeRef = useRef<number>(0);
  const fpsCounterRef = useRef<number[]>([]);

  // Update configuration
  const updateConfig = useCallback((updates: Partial<SimulationConfig>) => {
    setConfig(prev => {
      const newConfig = { ...prev, ...updates };
      onConfigChange?.(newConfig);
      logger.log('SimulationManager: Config updated', updates);
      return newConfig;
    });
  }, [onConfigChange]);

  // Start simulation
  const start = useCallback(() => {
    setState(prev => ({
      ...prev,
      isRunning: true,
      isPaused: false,
      currentAlpha: config.alpha
    }));
    logger.log('SimulationManager: Simulation started');
  }, [config.alpha]);

  // Pause simulation
  const pause = useCallback(() => {
    setState(prev => ({
      ...prev,
      isPaused: true
    }));
    logger.log('SimulationManager: Simulation paused');
  }, []);

  // Resume simulation
  const resume = useCallback(() => {
    setState(prev => ({
      ...prev,
      isPaused: false
    }));
    logger.log('SimulationManager: Simulation resumed');
  }, []);

  // Stop simulation
  const stop = useCallback(() => {
    setState(prev => ({
      ...prev,
      isRunning: false,
      isPaused: false,
      currentAlpha: 0,
      tickCount: 0
    }));
    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current);
      animationFrameRef.current = null;
    }
    logger.log('SimulationManager: Simulation stopped');
  }, []);

  // Restart simulation
  const restart = useCallback(() => {
    setState(prev => ({
      ...prev,
      isRunning: true,
      isPaused: false,
      currentAlpha: config.alpha,
      tickCount: 0
    }));
    logger.log('SimulationManager: Simulation restarted');
  }, [config.alpha]);

  // Adjust quality based on performance
  const adjustQuality = useCallback((currentFPS: number) => {
    if (currentFPS < targetFPS * 0.5) {
      // Low performance - reduce quality
      updateConfig({
        theta: Math.min(config.theta + 0.1, 1),
        alphaDecay: Math.min(config.alphaDecay * 1.2, 0.1)
      });
      logger.debug('SimulationManager: Reduced quality for performance');
    } else if (currentFPS > targetFPS * 0.9 && config.theta > 0.5) {
      // Good performance - increase quality
      updateConfig({
        theta: Math.max(config.theta - 0.05, 0.5),
        alphaDecay: Math.max(config.alphaDecay * 0.95, 0.001)
      });
      logger.debug('SimulationManager: Increased quality');
    }
  }, [targetFPS, config.theta, config.alphaDecay, updateConfig]);

  // Simulation tick
  const tick = useCallback(() => {
    if (!state.isRunning || state.isPaused) return;

    const currentTime = performance.now();
    const deltaTime = currentTime - lastFrameTimeRef.current;
    
    // Calculate FPS
    if (deltaTime > 0) {
      const fps = 1000 / deltaTime;
      fpsCounterRef.current.push(fps);
      
      // Keep last 60 frames for average
      if (fpsCounterRef.current.length > 60) {
        fpsCounterRef.current.shift();
      }
      
      // Calculate average FPS
      const avgFPS = fpsCounterRef.current.reduce((a, b) => a + b, 0) / fpsCounterRef.current.length;
      
      setState(prev => ({
        ...prev,
        fps: Math.round(avgFPS)
      }));

      // Adjust quality if needed
      if (fpsCounterRef.current.length === 60) {
        adjustQuality(avgFPS);
      }
    }
    
    lastFrameTimeRef.current = currentTime;

    // Update alpha
    setState(prev => {
      const newAlpha = Math.max(prev.currentAlpha - config.alphaDecay, config.alphaMin);
      
      // Check if simulation should end
      if (newAlpha <= config.alphaMin) {
        onSimulationEnd?.();
        return {
          ...prev,
          isRunning: false,
          currentAlpha: 0
        };
      }

      // Notify tick
      onSimulationTick?.(newAlpha);

      return {
        ...prev,
        currentAlpha: newAlpha,
        tickCount: prev.tickCount + 1
      };
    });

    // Schedule next frame
    animationFrameRef.current = requestAnimationFrame(tick);
  }, [
    state.isRunning,
    state.isPaused,
    config.alphaDecay,
    config.alphaMin,
    adjustQuality,
    onSimulationTick,
    onSimulationEnd
  ]);

  // Run simulation loop
  useEffect(() => {
    if (state.isRunning && !state.isPaused) {
      lastFrameTimeRef.current = performance.now();
      animationFrameRef.current = requestAnimationFrame(tick);
    } else if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current);
      animationFrameRef.current = null;
    }

    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
    };
  }, [state.isRunning, state.isPaused, tick]);

  // Preset configurations
  const applyPreset = useCallback((preset: 'tight' | 'loose' | 'circular' | 'grid') => {
    const presets: Record<string, Partial<SimulationConfig>> = {
      tight: {
        gravity: 0.1,
        repulsion: 0.3,
        friction: 0.9,
        linkStrength: 0.5,
        linkDistance: 30
      },
      loose: {
        gravity: 0,
        repulsion: 0.8,
        friction: 0.7,
        linkStrength: 0.1,
        linkDistance: 100
      },
      circular: {
        gravity: 0.2,
        repulsion: 1,
        friction: 0.5,
        linkStrength: 0,
        linkDistance: 150
      },
      grid: {
        gravity: 0,
        repulsion: 0.5,
        friction: 0.95,
        linkStrength: 1,
        linkDistance: 50
      }
    };

    const presetConfig = presets[preset];
    if (presetConfig) {
      updateConfig(presetConfig);
      logger.log('SimulationManager: Applied preset', preset);
    }
  }, [updateConfig]);

  // Expose state for monitoring
  useEffect(() => {
    logger.debug('SimulationManager state:', {
      isRunning: state.isRunning,
      isPaused: state.isPaused,
      alpha: state.currentAlpha.toFixed(4),
      ticks: state.tickCount,
      fps: state.fps
    });
  }, [state]);

  return null; // This is a non-visual component
};

// Hook for simulation control
export const useSimulation = () => {
  const [isRunning, setIsRunning] = useState(false);
  const [alpha, setAlpha] = useState(1);

  const start = useCallback(() => {
    setIsRunning(true);
    setAlpha(1);
  }, []);

  const stop = useCallback(() => {
    setIsRunning(false);
    setAlpha(0);
  }, []);

  const restart = useCallback(() => {
    setIsRunning(true);
    setAlpha(1);
  }, []);

  return {
    isRunning,
    alpha,
    start,
    stop,
    restart
  };
};

export default SimulationManager;