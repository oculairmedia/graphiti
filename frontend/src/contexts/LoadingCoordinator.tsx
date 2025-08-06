/**
 * LoadingCoordinator - Unified loading state management
 * Coordinates all loading stages to provide a single smooth loading experience
 */

import React, { createContext, useContext, useState, useCallback, useEffect, ReactNode } from 'react';
import { logger } from '../utils/logger';

export interface LoadingStage {
  id: string;
  label: string;
  status: 'pending' | 'loading' | 'complete' | 'error';
  progress?: number;
  error?: Error;
  metadata?: any;
}

interface LoadingCoordinatorState {
  stages: Map<string, LoadingStage>;
  isFullyLoaded: boolean;
  currentStage: string | null;
  overallProgress: number;
  startTime: number;
  loadTime: number | null;
  error: Error | null;
}

interface LoadingCoordinatorContextValue extends LoadingCoordinatorState {
  registerStage: (id: string, label: string) => void;
  updateStage: (id: string, updates: Partial<LoadingStage>) => void;
  setStageComplete: (id: string, metadata?: any) => void;
  setStageError: (id: string, error: Error) => void;
  reset: () => void;
  getStageStatus: (id: string) => LoadingStage['status'] | undefined;
  isStageComplete: (id: string) => boolean;
  areAllStagesComplete: () => boolean;
}

const LoadingCoordinatorContext = createContext<LoadingCoordinatorContextValue | null>(null);

export const useLoadingCoordinator = () => {
  const context = useContext(LoadingCoordinatorContext);
  if (!context) {
    throw new Error('useLoadingCoordinator must be used within LoadingCoordinatorProvider');
  }
  return context;
};

interface LoadingCoordinatorProviderProps {
  children: ReactNode;
  requiredStages?: string[];
}

export const LoadingCoordinatorProvider: React.FC<LoadingCoordinatorProviderProps> = ({ 
  children,
  requiredStages = ['services', 'data']
}) => {
  const [state, setState] = useState<LoadingCoordinatorState>({
    stages: new Map(),
    isFullyLoaded: false,
    currentStage: null,
    overallProgress: 0,
    startTime: Date.now(),
    loadTime: null,
    error: null
  });

  // Register a loading stage
  const registerStage = useCallback((id: string, label: string) => {
    setState(prev => {
      const newStages = new Map(prev.stages);
      if (!newStages.has(id)) {
        newStages.set(id, {
          id,
          label,
          status: 'pending',
          progress: 0
        });
        logger.log(`[LoadingCoordinator] Registered stage: ${id} - ${label}`);
      }
      return { ...prev, stages: newStages };
    });
  }, []);

  // Update a stage
  const updateStage = useCallback((id: string, updates: Partial<LoadingStage>) => {
    setState(prev => {
      const newStages = new Map(prev.stages);
      const stage = newStages.get(id);
      if (stage) {
        newStages.set(id, { ...stage, ...updates });
        
        // Update current stage if loading
        const currentStage = updates.status === 'loading' ? id : prev.currentStage;
        
        // Calculate overall progress
        const overallProgress = calculateOverallProgress(newStages);
        
        return { 
          ...prev, 
          stages: newStages,
          currentStage,
          overallProgress
        };
      }
      return prev;
    });
  }, []);

  // Mark a stage as complete
  const setStageComplete = useCallback((id: string, metadata?: any) => {
    setState(prev => {
      const newStages = new Map(prev.stages);
      const stage = newStages.get(id);
      if (stage) {
        newStages.set(id, {
          ...stage,
          status: 'complete',
          progress: 100,
          metadata
        });
        
        logger.log(`[LoadingCoordinator] Stage complete: ${id}`);
        
        // Check if all required stages are complete
        const allComplete = requiredStages.every(stageId => {
          const s = newStages.get(stageId);
          return s && s.status === 'complete';
        });
        
        const overallProgress = calculateOverallProgress(newStages);
        const loadTime = allComplete ? Date.now() - prev.startTime : null;
        
        if (allComplete && !prev.isFullyLoaded) {
          logger.log(`[LoadingCoordinator] All stages complete in ${loadTime}ms`);
        }
        
        return {
          ...prev,
          stages: newStages,
          isFullyLoaded: allComplete,
          overallProgress,
          loadTime,
          currentStage: allComplete ? null : prev.currentStage
        };
      }
      return prev;
    });
  }, [requiredStages]);

  // Mark a stage as errored
  const setStageError = useCallback((id: string, error: Error) => {
    setState(prev => {
      const newStages = new Map(prev.stages);
      const stage = newStages.get(id);
      if (stage) {
        newStages.set(id, {
          ...stage,
          status: 'error',
          error
        });
        
        logger.error(`[LoadingCoordinator] Stage error: ${id}`, error);
        
        return {
          ...prev,
          stages: newStages,
          error,
          currentStage: null
        };
      }
      return prev;
    });
  }, []);

  // Reset all stages
  const reset = useCallback(() => {
    setState({
      stages: new Map(),
      isFullyLoaded: false,
      currentStage: null,
      overallProgress: 0,
      startTime: Date.now(),
      loadTime: null,
      error: null
    });
    logger.log('[LoadingCoordinator] Reset all stages');
  }, []);

  // Get status of a specific stage
  const getStageStatus = useCallback((id: string): LoadingStage['status'] | undefined => {
    return state.stages.get(id)?.status;
  }, [state.stages]);

  // Check if a stage is complete
  const isStageComplete = useCallback((id: string): boolean => {
    return state.stages.get(id)?.status === 'complete';
  }, [state.stages]);

  // Check if all stages are complete
  const areAllStagesComplete = useCallback((): boolean => {
    return requiredStages.every(id => isStageComplete(id));
  }, [requiredStages, isStageComplete]);

  // Auto-register required stages on mount
  useEffect(() => {
    requiredStages.forEach(id => {
      const labels: Record<string, string> = {
        'services': 'Initializing services',
        'data': 'Loading graph data',
        'config': 'Loading configuration',
        'websocket': 'Connecting to server'
      };
      registerStage(id, labels[id] || id);
    });
  }, [requiredStages, registerStage]);

  const contextValue: LoadingCoordinatorContextValue = {
    ...state,
    registerStage,
    updateStage,
    setStageComplete,
    setStageError,
    reset,
    getStageStatus,
    isStageComplete,
    areAllStagesComplete
  };

  return (
    <LoadingCoordinatorContext.Provider value={contextValue}>
      {children}
    </LoadingCoordinatorContext.Provider>
  );
};

// Helper function to calculate overall progress
function calculateOverallProgress(stages: Map<string, LoadingStage>): number {
  if (stages.size === 0) return 0;
  
  let totalProgress = 0;
  stages.forEach(stage => {
    if (stage.status === 'complete') {
      totalProgress += 100;
    } else if (stage.status === 'loading' && stage.progress) {
      totalProgress += stage.progress;
    }
  });
  
  return Math.round(totalProgress / stages.size);
}