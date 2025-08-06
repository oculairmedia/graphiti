/**
 * UnifiedLoadingScreen - Single loading experience for the entire app
 * Shows progress across all loading stages with smooth transitions
 */

import React, { useMemo } from 'react';
import { useLoadingCoordinator } from '../contexts/LoadingCoordinator';
import { Progress } from './ui/progress';
import { CheckCircle2, Circle, Loader2, AlertCircle } from 'lucide-react';

interface UnifiedLoadingScreenProps {
  className?: string;
}

export const UnifiedLoadingScreen: React.FC<UnifiedLoadingScreenProps> = ({ className = '' }) => {
  const {
    stages,
    isFullyLoaded,
    currentStage,
    overallProgress,
    loadTime,
    error
  } = useLoadingCoordinator();

  // Get sorted stages for display
  const sortedStages = useMemo(() => {
    const stageOrder = ['services', 'data', 'canvas', 'config', 'websocket'];
    return Array.from(stages.values()).sort((a, b) => {
      const aIndex = stageOrder.indexOf(a.id);
      const bIndex = stageOrder.indexOf(b.id);
      return aIndex - bIndex;
    });
  }, [stages]);

  // Get current stage label
  const currentStageLabel = useMemo(() => {
    if (error) return 'Error loading application';
    if (isFullyLoaded) return 'Loading complete! Preparing interface...';
    
    const current = stages.get(currentStage || '');
    if (current) {
      // Add metadata to label if available
      if (current.id === 'data' && current.metadata) {
        const { nodeCount, edgeCount } = current.metadata;
        if (nodeCount) {
          return `${current.label} (${nodeCount.toLocaleString()} nodes, ${edgeCount?.toLocaleString() || 0} edges)`;
        }
      }
      return current.label;
    }
    
    return 'Initializing...';
  }, [stages, currentStage, isFullyLoaded, error]);

  return (
    <div className={`fixed inset-0 z-50 flex items-center justify-center bg-background ${className}`}>
      <div className="w-full max-w-md px-8">
        {/* Main loading indicator */}
        <div className="flex flex-col items-center mb-8">
          {error ? (
            <AlertCircle className="h-16 w-16 text-destructive mb-4" />
          ) : (
            <div className="relative mb-4">
              <Loader2 className="h-16 w-16 text-primary animate-spin" />
              {/* Progress ring */}
              <svg className="absolute inset-0 h-16 w-16 -rotate-90">
                <circle
                  cx="32"
                  cy="32"
                  r="28"
                  stroke="currentColor"
                  strokeWidth="4"
                  fill="none"
                  className="text-secondary"
                />
                <circle
                  cx="32"
                  cy="32"
                  r="28"
                  stroke="currentColor"
                  strokeWidth="4"
                  fill="none"
                  strokeDasharray={`${(overallProgress / 100) * 176} 176`}
                  className="text-primary transition-all duration-300"
                />
              </svg>
            </div>
          )}
          
          {/* Current stage label - single line with ellipsis if too long */}
          <h2 className="text-lg font-medium text-foreground mb-2 whitespace-nowrap overflow-hidden text-ellipsis max-w-full px-4">
            {currentStageLabel}
          </h2>
          
          {/* Overall progress bar */}
          <div className="w-full mb-6">
            <div className="flex justify-between text-xs text-muted-foreground mb-1">
              <span>Progress</span>
              <span>{overallProgress}%</span>
            </div>
            <Progress value={overallProgress} className="h-2" />
          </div>
        </div>

        {/* Stage list */}
        <div className="space-y-3">
          {sortedStages.map(stage => (
            <div key={stage.id} className="flex items-center space-x-3">
              {/* Stage icon */}
              <div className="flex-shrink-0">
                {stage.status === 'complete' ? (
                  <CheckCircle2 className="h-5 w-5 text-green-500" />
                ) : stage.status === 'loading' ? (
                  <Loader2 className="h-5 w-5 text-primary animate-spin" />
                ) : stage.status === 'error' ? (
                  <AlertCircle className="h-5 w-5 text-destructive" />
                ) : (
                  <Circle className="h-5 w-5 text-muted-foreground" />
                )}
              </div>
              
              {/* Stage label */}
              <div className="flex-1">
                <p className={`text-sm ${
                  stage.status === 'complete' ? 'text-muted-foreground' :
                  stage.status === 'loading' ? 'text-foreground font-medium' :
                  stage.status === 'error' ? 'text-destructive' :
                  'text-muted-foreground/60'
                }`}>
                  {stage.label}
                  {stage.status === 'loading' && stage.progress && stage.progress < 100 && (
                    <span className="ml-2 text-xs">({stage.progress}%)</span>
                  )}
                </p>
                {stage.error && (
                  <p className="text-xs text-destructive mt-1">{stage.error.message}</p>
                )}
              </div>
            </div>
          ))}
        </div>

        {/* Error message and retry */}
        {error && (
          <div className="mt-6 p-4 bg-destructive/10 rounded-lg">
            <p className="text-sm text-destructive mb-2">{error.message}</p>
            <button
              onClick={() => window.location.reload()}
              className="text-xs text-primary hover:underline"
            >
              Reload application
            </button>
          </div>
        )}

        {/* Loading time display */}
        {loadTime && (
          <p className="text-xs text-muted-foreground text-center mt-4">
            Loaded in {(loadTime / 1000).toFixed(2)}s
          </p>
        )}
      </div>
    </div>
  );
};

export default UnifiedLoadingScreen;