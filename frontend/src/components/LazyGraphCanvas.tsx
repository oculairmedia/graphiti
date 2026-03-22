import React, { Suspense } from 'react';
import { Skeleton } from './ui/skeleton';

import type { GraphCanvasRef } from '@/types/graphCanvas';
import type { GraphCanvasComponentProps } from './GraphCanvasV2';

const GraphCanvas = React.lazy(() => import('./GraphCanvasV2'));

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
      <GraphCanvas ref={ref} {...props} />
    </Suspense>
  );
});

LazyGraphCanvas.displayName = 'LazyGraphCanvas';