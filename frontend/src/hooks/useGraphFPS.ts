/**
 * useGraphFPS Hook
 * Tracks FPS with optimized state updates to minimize re-renders
 * Extracted from GraphCanvasV2 for better separation of concerns (GRAPH-35)
 * 
 * PERFORMANCE FIX (GRAPH-40): Updates React state every 2 seconds instead of 1
 * to reduce unnecessary re-renders
 */

import { useState, useRef, useEffect } from 'react';

interface FPSOptions {
  enabled?: boolean;
  stateUpdateInterval?: number;  // How often to update React state (ms)
  hasData?: boolean;  // Whether there's data to track
}

interface FPSReturn {
  fps: number;
  fpsRef: React.MutableRefObject<number>;
}

export function useGraphFPS(options: FPSOptions = {}): FPSReturn {
  const { enabled = false, stateUpdateInterval = 2000, hasData = false } = options;
  
  const [fps, setFps] = useState<number>(60);
  const fpsRef = useRef<number>(60);
  
  useEffect(() => {
    if (!enabled || !hasData) return;
    
    let animationFrameId: number;
    let lastTime = performance.now();
    let frameCount = 0;
    let lastStateUpdate = performance.now();
    
    const calculateFPS = () => {
      const now = performance.now();
      const delta = now - lastTime;
      frameCount++;
      
      // Calculate FPS every second (stored in ref, no re-render)
      if (delta >= 1000) {
        fpsRef.current = Math.round((frameCount * 1000) / delta);
        frameCount = 0;
        lastTime = now;
        
        // Only update React state at specified interval to minimize re-renders
        if (now - lastStateUpdate >= stateUpdateInterval) {
          setFps(fpsRef.current);
          lastStateUpdate = now;
        }
      }
      
      animationFrameId = requestAnimationFrame(calculateFPS);
    };
    
    animationFrameId = requestAnimationFrame(calculateFPS);
    
    return () => {
      if (animationFrameId) {
        cancelAnimationFrame(animationFrameId);
      }
    };
  }, [enabled, hasData, stateUpdateInterval]);
  
  return { fps, fpsRef };
}
