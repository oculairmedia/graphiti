import React from 'react';
import { RefreshCw, AlertTriangle, Home } from 'lucide-react';
import ErrorBoundary from './ErrorBoundary';

interface GraphErrorFallbackProps {
  error?: Error;
  resetError: () => void;
}

const GraphErrorFallback: React.FC<GraphErrorFallbackProps> = ({ error, resetError }) => {
  const isWebGLError = error?.message.includes('WebGL') || error?.message.includes('canvas');
  const isDataError = error?.message.includes('nodes') || error?.message.includes('edges');
  
  return (
    <div className="h-full flex items-center justify-center bg-background/50 backdrop-blur-sm">
      <div className="max-w-lg mx-auto text-center p-8 bg-card border border-border rounded-lg shadow-lg">
        <AlertTriangle className="w-16 h-16 text-destructive mx-auto mb-4" />
        
        <h2 className="text-xl font-semibold text-foreground mb-2">
          Graph Visualization Error
        </h2>
        
        <p className="text-muted-foreground mb-6">
          {isWebGLError && "WebGL or canvas rendering failed. Your browser may not support hardware acceleration."}
          {isDataError && "Graph data processing failed. The data may be corrupted or in an unexpected format."}
          {!isWebGLError && !isDataError && "An unexpected error occurred while rendering the graph."}
        </p>

        <div className="space-y-3">
          <button 
            onClick={resetError}
            className="w-full flex items-center justify-center gap-2 bg-primary text-primary-foreground hover:bg-primary/90 px-4 py-2 rounded-md transition-colors"
          >
            <RefreshCw className="w-4 h-4" />
            Retry Graph Rendering
          </button>
          
          <button 
            onClick={() => window.location.reload()}
            className="w-full flex items-center justify-center gap-2 bg-secondary text-secondary-foreground hover:bg-secondary/80 px-4 py-2 rounded-md transition-colors"
          >
            <Home className="w-4 h-4" />
            Reload Application
          </button>
        </div>

        {isWebGLError && (
          <div className="mt-4 p-3 bg-warning/10 border border-warning/20 rounded text-sm">
            <p className="text-warning-foreground">
              <strong>WebGL Support Required:</strong> Please ensure your browser supports WebGL and hardware acceleration is enabled.
            </p>
          </div>
        )}

        {process.env.NODE_ENV === 'development' && error && (
          <details className="mt-6 text-left">
            <summary className="cursor-pointer text-sm text-muted-foreground mb-2">
              Developer Info
            </summary>
            <pre className="text-xs bg-muted p-3 rounded overflow-auto max-h-32 whitespace-pre-wrap">
              {error.stack}
            </pre>
          </details>
        )}
      </div>
    </div>
  );
};

interface GraphErrorBoundaryProps {
  children: React.ReactNode;
}

const GraphErrorBoundary: React.FC<GraphErrorBoundaryProps> = ({ children }) => {
  return (
    <ErrorBoundary 
      fallback={GraphErrorFallback}
      onError={(error, errorInfo) => {
        // Additional graph-specific error reporting could go here
        console.error('Graph visualization error:', error, errorInfo);
      }}
    >
      {children}
    </ErrorBoundary>
  );
};

export default GraphErrorBoundary;