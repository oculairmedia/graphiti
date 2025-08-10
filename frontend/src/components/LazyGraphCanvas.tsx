import React, { Suspense } from 'react';
import { Skeleton } from './ui/skeleton';

// Lazy load the heavy GraphCanvas component
const GraphCanvas = React.lazy(() => 
  import('./GraphCanvas').then(module => ({
    default: module.GraphCanvas
  }))
);

// Loading placeholder that matches the graph canvas appearance
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

// Export a wrapped version that handles lazy loading
export const LazyGraphCanvas = React.forwardRef<any, any>((props, ref) => {
  return (
    <Suspense fallback={<GraphCanvasLoader />}>
      <GraphCanvas ref={ref} {...props} />
    </Suspense>
  );
});

LazyGraphCanvas.displayName = 'LazyGraphCanvas';