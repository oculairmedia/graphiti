import React from 'react';
import { useWebSocketContext } from '../contexts/WebSocketProvider';
import { cn } from '../lib/utils';

export const WebSocketStatus: React.FC<{ className?: string }> = ({ className }) => {
  const { isConnected } = useWebSocketContext();
  
  return (
    <div className={cn("flex items-center gap-2 text-xs", className)}>
      <div 
        className={cn(
          "w-2 h-2 rounded-full transition-colors duration-300",
          isConnected ? "bg-green-500" : "bg-red-500"
        )}
      />
      <span className="text-muted-foreground">
        {isConnected ? 'Connected' : 'Disconnected'}
      </span>
    </div>
  );
};