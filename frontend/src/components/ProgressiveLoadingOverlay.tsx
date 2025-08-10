import React from 'react';
import { Progress } from './ui/progress';

interface ProgressiveLoadingOverlayProps {
  phase: string;
  loaded: number;
  total: number;
  isVisible: boolean;
}

export const ProgressiveLoadingOverlay: React.FC<ProgressiveLoadingOverlayProps> = ({
  phase,
  loaded,
  total,
  isVisible
}) => {
  if (!isVisible || !phase) return null;
  
  const percentage = total > 0 ? (loaded / total) * 100 : 0;
  const phaseLabels: Record<string, string> = {
    'core': 'Loading core structure',
    'secondary': 'Loading connected nodes',
    'peripheral': 'Loading peripheral nodes'
  };
  
  return (
    <div className="absolute top-4 left-1/2 transform -translate-x-1/2 z-50 bg-background/95 backdrop-blur-sm border rounded-lg p-4 shadow-lg transition-all duration-300">
      <div className="flex flex-col gap-2 min-w-[300px]">
        <div className="text-sm font-medium">
          {phaseLabels[phase] || `Loading ${phase}`}
        </div>
        <Progress value={percentage} className="h-2" />
        <div className="text-xs text-muted-foreground text-center">
          {loaded.toLocaleString()} / {total.toLocaleString()} nodes
        </div>
      </div>
    </div>
  );
};