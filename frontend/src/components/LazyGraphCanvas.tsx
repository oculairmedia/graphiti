import React, { Suspense } from 'react';
import { Skeleton } from './ui/skeleton';

import type { GraphCanvasRef } from '@/types/graphCanvas';
import type { GraphCanvasComponentProps } from './GraphCanvasV2';

// Lazy load GraphCanvasV2 AND CosmographProvider together so the entire
// @cosmograph/react library stays out of the main bundle.
const GraphCanvasWithProvider = React.lazy(() =>
  Promise.all([
    import('./GraphCanvasV2'),
    import('@cosmograph/react'),
  ]).then(([canvasModule, cosmographModule]) => ({
    default: React.forwardRef<GraphCanvasRef, GraphCanvasComponentProps>((props, ref) => (
      <cosmographModule.CosmographProvider>
        <canvasModule.default ref={ref} {...props} />
      </cosmographModule.CosmographProvider>
    )),
  }))
);

const GraphCanvasLoader: React.FC = () => (
  <div className="w-full h-full bg-background flex items-center justify-center">
    <div className="text-center space-y-4">
      <Skeleton className="w-48 h-48 rounded-full mx-auto" />
      <div className="space-y-2">
        <Skeleton className="h-4 w-32 mx-auto" />
        <p className="text-sm text-muted-foreground">Loading graph visualization...</p>
      </div>
    </div>
  </div>
);

export const LazyGraphCanvas = React.forwardRef<GraphCanvasRef, GraphCanvasComponentProps>((props, ref) => {
  return (
    <Suspense fallback={<GraphCanvasLoader />}>
      <GraphCanvasWithProvider ref={ref} {...props} />
    </Suspense>
  );
});

LazyGraphCanvas.displayName = 'LazyGraphCanvas';