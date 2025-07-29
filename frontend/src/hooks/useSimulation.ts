import { useCallback, useRef, useState } from 'react';
import { logger } from '../utils/logger';

interface CosmographRef {
  start?: (alpha?: number) => void;
  pause?: () => void;
  restart?: () => void;
}

interface SimulationConfig {
  defaultAlpha?: number;
  resumeAlpha?: number;
  restartAlpha?: number;
}

export function useSimulation(
  cosmographRef: React.RefObject<CosmographRef | null>,
  config: SimulationConfig = {}
) {
  const {
    defaultAlpha = 1.0,
    resumeAlpha = 0.3,
    restartAlpha = 1.0,
  } = config;

  const [isRunning, setIsRunning] = useState(true);
  const [keepRunning, setKeepRunning] = useState(false);
  const lastResumeTimeRef = useRef<number>(0);
  const keepRunningIntervalRef = useRef<NodeJS.Timeout | null>(null);

  /**
   * Start the simulation with specified alpha (energy level)
   */
  const startSimulation = useCallback((alpha = defaultAlpha) => {
    if (cosmographRef.current?.start) {
      cosmographRef.current.start(alpha);
      setIsRunning(true);
      logger.log(`Started simulation with alpha: ${alpha}`);
    }
  }, [cosmographRef, defaultAlpha]);

  /**
   * Pause the simulation
   */
  const pauseSimulation = useCallback(() => {
    if (cosmographRef.current?.pause) {
      cosmographRef.current.pause();
      setIsRunning(false);
      logger.log('Paused simulation');
    }
    
    // Clear the keep-running timer
    if (keepRunningIntervalRef.current) {
      clearInterval(keepRunningIntervalRef.current);
      keepRunningIntervalRef.current = null;
    }
  }, [cosmographRef]);

  /**
   * Resume the simulation with moderate energy
   */
  const resumeSimulation = useCallback(() => {
    if (cosmographRef.current?.start) {
      const currentTime = Date.now();
      lastResumeTimeRef.current = currentTime;
      
      cosmographRef.current.start(resumeAlpha);
      setIsRunning(true);
      logger.log(`Resumed simulation with alpha: ${resumeAlpha}`);
      
      // If keep running is enabled, set up the interval
      if (keepRunning && !keepRunningIntervalRef.current) {
        keepRunningIntervalRef.current = setInterval(() => {
          if (cosmographRef.current?.start && Date.now() - lastResumeTimeRef.current > 5000) {
            cosmographRef.current.start(0.1); // Gentle nudge
            logger.log('Keeping simulation running with gentle nudge');
          }
        }, 3000);
      }
    }
  }, [cosmographRef, resumeAlpha, keepRunning]);

  /**
   * Restart the simulation with full energy
   */
  const restartSimulation = useCallback(() => {
    if (cosmographRef.current?.restart) {
      cosmographRef.current.restart();
      setIsRunning(true);
      logger.log('Restarted simulation');
    } else if (cosmographRef.current?.start) {
      // Fallback to start with high alpha
      cosmographRef.current.start(restartAlpha);
      setIsRunning(true);
      logger.log(`Restarted simulation with alpha: ${restartAlpha}`);
    }
  }, [cosmographRef, restartAlpha]);

  /**
   * Toggle keep simulation running mode
   */
  const keepSimulationRunning = useCallback((enable: boolean) => {
    setKeepRunning(enable);
    logger.log(`Keep simulation running: ${enable}`);
    
    if (!enable && keepRunningIntervalRef.current) {
      clearInterval(keepRunningIntervalRef.current);
      keepRunningIntervalRef.current = null;
    } else if (enable && isRunning && !keepRunningIntervalRef.current) {
      // Start the keep-running interval
      keepRunningIntervalRef.current = setInterval(() => {
        if (cosmographRef.current?.start) {
          cosmographRef.current.start(0.1); // Gentle nudge
        }
      }, 3000);
    }
  }, [cosmographRef, isRunning]);

  /**
   * Toggle simulation running state
   */
  const toggleSimulation = useCallback(() => {
    if (isRunning) {
      pauseSimulation();
    } else {
      resumeSimulation();
    }
  }, [isRunning, pauseSimulation, resumeSimulation]);

  /**
   * Cleanup function to clear intervals
   */
  const cleanup = useCallback(() => {
    if (keepRunningIntervalRef.current) {
      clearInterval(keepRunningIntervalRef.current);
      keepRunningIntervalRef.current = null;
    }
  }, []);

  return {
    isRunning,
    keepRunning,
    startSimulation,
    pauseSimulation,
    resumeSimulation,
    restartSimulation,
    keepSimulationRunning,
    toggleSimulation,
    cleanup,
  };
}