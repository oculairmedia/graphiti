import React from 'react';

interface GraphLoadingStateProps {
  message?: string;
  progress?: number;
  className?: string;
}

/**
 * Loading state component for the graph visualization
 */
export const GraphLoadingState: React.FC<GraphLoadingStateProps> = ({
  message = 'Loading...',
  progress,
  className = ''
}) => {
  return (
    <div className={`flex flex-col items-center justify-center min-h-[400px] p-8 ${className}`}>
      <div className="relative">
        {/* Animated spinner */}
        <div className="w-16 h-16 relative">
          <div className="absolute inset-0 border-4 border-gray-200 rounded-full"></div>
          <div className="absolute inset-0 border-4 border-blue-500 rounded-full border-t-transparent animate-spin"></div>
        </div>
        
        {/* Progress indicator if provided */}
        {progress !== undefined && (
          <div className="absolute -bottom-2 -right-2 bg-white rounded-full p-1 shadow-lg">
            <div className="text-xs font-semibold text-gray-700">
              {Math.round(progress)}%
            </div>
          </div>
        )}
      </div>
      
      {/* Loading message */}
      <p className="mt-4 text-gray-600 text-sm animate-pulse">
        {message}
      </p>
      
      {/* Progress bar if provided */}
      {progress !== undefined && (
        <div className="mt-4 w-64">
          <div className="bg-gray-200 rounded-full h-2 overflow-hidden">
            <div
              className="bg-blue-500 h-full rounded-full transition-all duration-300 ease-out"
              style={{ width: `${Math.min(100, Math.max(0, progress))}%` }}
            />
          </div>
        </div>
      )}
    </div>
  );
};