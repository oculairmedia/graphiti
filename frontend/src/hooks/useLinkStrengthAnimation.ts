import { useEffect, useRef, useCallback } from 'react';
import { useGraphConfig } from '../contexts/GraphConfigProvider';
import type { GraphLink } from '../types/graph';

// Simple Perlin-like noise function for smooth random variation
function noise(x: number): number {
  const X = Math.floor(x) & 255;
  x -= Math.floor(x);
  const u = fade(x);
  return lerp(u, grad(X, x), grad(X + 1, x - 1)) * 2;
}

function fade(t: number): number {
  return t * t * t * (t * (t * 6 - 15) + 10);
}

function lerp(t: number, a: number, b: number): number {
  return a + t * (b - a);
}

function grad(hash: number, x: number): number {
  const h = hash & 15;
  const grad = 1 + (h & 7);
  return (h & 8 ? -grad : grad) * x;
}

export function useLinkStrengthAnimation(
  links: GraphLink[],
  onUpdate: (animatedLinks: GraphLink[]) => void,
  enabled: boolean = true
) {
  const { config } = useGraphConfig();
  const animationFrameRef = useRef<number>();
  const timeRef = useRef<number>(0);
  const baseStrengthsRef = useRef<Map<string, number>>(new Map());
  
  // Store base strength values
  useEffect(() => {
    const baseStrengths = new Map<string, number>();
    links.forEach(link => {
      const linkId = `${link.source}-${link.target}`;
      const baseStrength = link.strength || 1.0;
      baseStrengths.set(linkId, baseStrength);
    });
    baseStrengthsRef.current = baseStrengths;
  }, [links]);
  
  const animate = useCallback(() => {
    if (!config.linkAnimationEnabled || !enabled) {
      return;
    }
    
    const time = timeRef.current;
    const amplitude = config.linkAnimationAmplitude || 0.15;
    const frequency = config.linkAnimationFrequency || 0.5;
    
    // Create animated links with noise-based strength variation
    const animatedLinks = links.map((link, index) => {
      const linkId = `${link.source}-${link.target}`;
      const baseStrength = baseStrengthsRef.current.get(linkId) || link.strength || 1.0;
      
      // Use different noise offsets for each link to create variation
      const noiseOffset = index * 0.1;
      const noiseValue = noise((time * frequency) + noiseOffset);
      
      // Apply amplitude to create variation around base strength
      const variation = noiseValue * amplitude;
      const animatedStrength = baseStrength * (1 + variation);
      
      // Clamp to reasonable values
      const clampedStrength = Math.max(0.1, Math.min(3.0, animatedStrength));
      
      return {
        ...link,
        strength: clampedStrength
      };
    });
    
    onUpdate(animatedLinks);
    
    // Increment time
    timeRef.current += 0.016; // ~60fps
    
    // Continue animation
    animationFrameRef.current = requestAnimationFrame(animate);
  }, [links, onUpdate, config.linkAnimationEnabled, config.linkAnimationAmplitude, config.linkAnimationFrequency, enabled]);
  
  // Start/stop animation based on config
  useEffect(() => {
    if (config.linkAnimationEnabled && enabled) {
      animate();
    } else {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
    }
    
    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
    };
  }, [animate, config.linkAnimationEnabled, enabled]);
  
  // Return control functions
  return {
    start: () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
      animate();
    },
    stop: () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
    },
    reset: () => {
      timeRef.current = 0;
    }
  };
}