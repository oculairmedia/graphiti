import React from 'react';
import { logger } from '../utils/logger';

interface ErrorBoundaryState {
  hasError: boolean;
  error?: Error;
  errorInfo?: React.ErrorInfo;
}

interface ErrorBoundaryProps {
  children: React.ReactNode;
  fallback?: React.ComponentType<{ error?: Error; resetError: () => void }>;
  onError?: (error: Error, errorInfo: React.ErrorInfo) => void;
}

class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    this.setState({ error, errorInfo });
    
    // Log error for debugging - always log to console for visibility
    console.error('=== ErrorBoundary caught an error ===');
    console.error('Error:', error);
    console.error('Error message:', error.message);
    console.error('Error stack:', error.stack);
    console.error('Component stack:', errorInfo.componentStack);
    console.error('=====================================');
    
    // Also expose to window for easy retrieval
    (window as unknown as Record<string, unknown>).__GRAPHITI_LAST_ERROR__ = {
      error: error.toString(),
      message: error.message,
      stack: error.stack,
      componentStack: errorInfo.componentStack,
      timestamp: new Date().toISOString(),
    };
    
    logger.error('ErrorBoundary caught an error:', error, errorInfo);
    
    // Call custom error handler if provided
    this.props.onError?.(error, errorInfo);
  }

  resetError = () => {
    this.setState({ hasError: false, error: undefined, errorInfo: undefined });
  };

  render() {
    if (this.state.hasError) {
      const FallbackComponent = this.props.fallback;
      
      if (FallbackComponent) {
        return <FallbackComponent error={this.state.error} resetError={this.resetError} />;
      }

      // Default error UI
      return (
        <div className="min-h-screen flex items-center justify-center bg-background">
          <div className="max-w-md mx-auto text-center p-6">
            <div className="text-destructive text-6xl mb-4">⚠️</div>
            <h1 className="text-2xl font-bold text-foreground mb-2">Something went wrong</h1>
            <p className="text-muted-foreground mb-6">
              An unexpected error occurred in the application. Please try refreshing the page.
            </p>
            
            <div className="space-y-3">
              <button 
                onClick={this.resetError}
                className="w-full bg-primary text-primary-foreground hover:bg-primary/90 px-4 py-2 rounded-md transition-colors"
              >
                Try Again
              </button>
              
              <button 
                onClick={() => window.location.reload()}
                className="w-full bg-secondary text-secondary-foreground hover:bg-secondary/80 px-4 py-2 rounded-md transition-colors"
              >
                Refresh Page
              </button>
            </div>

            {this.state.error && (
              <details className="mt-6 text-left" open>
                <summary className="cursor-pointer text-sm text-muted-foreground mb-2">
                  Error Details (check browser console for full stack)
                </summary>
                <div className="space-y-2">
                  <div className="text-xs bg-red-900/20 border border-red-500/30 p-3 rounded">
                    <strong className="text-red-400">Error:</strong>
                    <pre className="mt-1 text-red-300 whitespace-pre-wrap break-all">
                      {this.state.error.message || this.state.error.toString()}
                    </pre>
                  </div>
                  <div className="text-xs bg-muted p-3 rounded overflow-auto max-h-48">
                    <strong className="text-muted-foreground">Stack Trace:</strong>
                    <pre className="mt-1 whitespace-pre-wrap break-all">
                      {this.state.error.stack}
                    </pre>
                  </div>
                  {this.state.errorInfo?.componentStack && (
                    <div className="text-xs bg-muted p-3 rounded overflow-auto max-h-32">
                      <strong className="text-muted-foreground">Component Stack:</strong>
                      <pre className="mt-1 whitespace-pre-wrap">
                        {this.state.errorInfo.componentStack}
                      </pre>
                    </div>
                  )}
                  <p className="text-xs text-muted-foreground mt-2">
                    Tip: Run <code className="bg-muted px-1 rounded">window.__GRAPHITI_LAST_ERROR__</code> in console for full error object
                  </p>
                </div>
              </details>
            )}
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;