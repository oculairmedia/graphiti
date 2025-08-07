import React from 'react';
import { useWebSocketContext } from '../contexts/WebSocketProvider';
import { cn } from '../lib/utils';

export const WebSocketStatus: React.FC<{ className?: string; showDetails?: boolean }> = ({ 
  className,
  showDetails = false 
}) => {
  const { isConnected, connectionQuality, latency } = useWebSocketContext();
  
  const getStatusColor = () => {
    if (!isConnected) return "bg-red-500";
    switch (connectionQuality) {
      case 'excellent': return "bg-green-500";
      case 'good': return "bg-yellow-500";
      case 'poor': return "bg-orange-500";
      default: return "bg-gray-500";
    }
  };
  
  const getStatusText = () => {
    if (!isConnected) return 'Disconnected';
    if (showDetails && latency > 0) {
      return `${connectionQuality} (${latency}ms)`;
    }
    return connectionQuality || 'Connected';
  };
  
  return (
    <div className={cn("flex items-center gap-2 text-xs", className)}>
      <div 
        className={cn(
          "w-2 h-2 rounded-full transition-colors duration-300",
          getStatusColor()
        )}
      />
      <span className="text-muted-foreground capitalize">
        {getStatusText()}
      </span>
    </div>
  );
};