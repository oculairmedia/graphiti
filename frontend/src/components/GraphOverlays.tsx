import React from 'react';
import { useGraphConfig } from '../contexts/GraphConfigProvider';
import { Card } from '@/components/ui/card';

interface GraphOverlaysProps {
  nodeCount: number;
  edgeCount: number;
  visibleNodes?: number;
  selectedNodes?: number;
  fps?: number;
}

export const GraphOverlays: React.FC<GraphOverlaysProps> = ({
  nodeCount,
  edgeCount,
  visibleNodes,
  selectedNodes,
  fps
}) => {
  const { config } = useGraphConfig();
  
  // Don't render anything if all overlays are disabled
  if (!config.showNodeCount && !config.showDebugInfo && !config.showFPS) {
    return null;
  }
  
  return (
    <div className="absolute top-4 left-4 z-10 space-y-2 pointer-events-none">
      {/* Node Count Overlay */}
      {config.showNodeCount && (
        <Card className="bg-background/80 backdrop-blur-sm border-border/50 p-2 px-3">
          <div className="text-sm space-y-1">
            <div className="flex items-center justify-between gap-4">
              <span className="text-muted-foreground">Nodes:</span>
              <span className="font-mono font-medium">{nodeCount.toLocaleString()}</span>
            </div>
            <div className="flex items-center justify-between gap-4">
              <span className="text-muted-foreground">Edges:</span>
              <span className="font-mono font-medium">{edgeCount.toLocaleString()}</span>
            </div>
            {visibleNodes !== undefined && visibleNodes !== nodeCount && (
              <div className="flex items-center justify-between gap-4">
                <span className="text-muted-foreground">Visible:</span>
                <span className="font-mono font-medium">{visibleNodes.toLocaleString()}</span>
              </div>
            )}
            {selectedNodes !== undefined && selectedNodes > 0 && (
              <div className="flex items-center justify-between gap-4">
                <span className="text-muted-foreground">Selected:</span>
                <span className="font-mono font-medium">{selectedNodes}</span>
              </div>
            )}
          </div>
        </Card>
      )}
      
      {/* FPS Counter */}
      {config.showFPS && fps !== undefined && (
        <Card className="bg-background/80 backdrop-blur-sm border-border/50 p-2 px-3">
          <div className="text-sm flex items-center gap-2">
            <span className="text-muted-foreground">FPS:</span>
            <span className={`font-mono font-medium ${
              fps >= 50 ? 'text-green-500' : 
              fps >= 30 ? 'text-yellow-500' : 
              'text-red-500'
            }`}>
              {Math.round(fps)}
            </span>
          </div>
        </Card>
      )}
      
      {/* Debug Info Overlay */}
      {config.showDebugInfo && (
        <Card className="bg-background/80 backdrop-blur-sm border-border/50 p-2 px-3">
          <div className="text-xs space-y-1 font-mono">
            <div className="text-muted-foreground font-semibold mb-1">Debug Info</div>
            <div>Memory: {getMemoryUsage()}</div>
            <div>Renderer: WebGL</div>
            <div>Layout: {config.layout || 'force'}</div>
            <div>Color: {config.colorScheme}</div>
            <div>Simulation: {config.disableSimulation ? 'paused' : 'running'}</div>
            {visibleNodes !== undefined && visibleNodes < nodeCount && (
              <div className="text-yellow-500">
                Virtualized: {((visibleNodes / nodeCount) * 100).toFixed(1)}%
              </div>
            )}
          </div>
        </Card>
      )}
    </div>
  );
};

// Helper function to get memory usage if available
function getMemoryUsage(): string {
  if ('memory' in performance) {
    const memory = (performance as any).memory;
    const used = memory.usedJSHeapSize / 1048576; // Convert to MB
    const total = memory.jsHeapSizeLimit / 1048576;
    const percentage = ((used / total) * 100).toFixed(1);
    return `${used.toFixed(1)}MB (${percentage}%)`;
  }
  return 'N/A';
}

export default GraphOverlays;